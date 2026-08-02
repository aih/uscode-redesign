"""The release-point inventory: what release points exist, when, and what changed.

This is the seed for `release_points` and the driver for every later ingest.
PLAN §1 calls it "the RP inventory JSON" after `uscreleasepoints.json` from
[dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb); the
shape kept here — `{name, date, titlesAffected, url}` per RP — is deliberately
that one's, so the existing tooling and this project can read each other's files.

Source: <https://uscode.house.gov/download/priorreleasepoints.htm>, one `<li>` per
release point, newest first. Everything structured comes out of the link href
(`releasepoints/us/pl/119/102not101/usc-rp@119-102not101.htm` → label
`119-102not101`); the link *text* is prose written by a human and is only mined
for the currency date and the affected titles. Things the real page does that a
guessed parser would get wrong, all covered by tests:

  * **Page order is the ordering.** Labels don't sort (gotcha 4) and dates tie, but
    the page is strictly newest-to-oldest, so `seq` is assigned from position —
    oldest RP is 0. Verified: no date on the page is later than the one above it.
  * **`u1` update labels** (`118-22u1`) — see `ingest.release_label`.
  * **Duplicate entries.** Three labels are listed twice, and `113-165` carries
    *different* affected titles in its two entries (25 vs 39, 49). Duplicates merge
    and their title lists union; taking the first would silently drop titles.
  * **Prose drift.** "affecting title 47" (singular), "…, 47, and 50" (Oxford
    "and"), "Pub. L. 116-155 (8/8/2020)" (unpadded date, no "Public Law"),
    "…, and including Public Law 119-1 (January 29, 2025)" (a second date that is
    *not* the currency date — the first `MM/DD/YYYY` wins), and commented-out `<li>`
    entries for release points that were never published (`119-102` itself).
  * **Appendix titles** appear as `18A`, normalized here to `18a` to match the
    `usc18a.xml` / `xml_usc18a@…zip` file naming (CLAUDE.md gotcha 7).
"""

from __future__ import annotations

import json
import re
import urllib.request
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ReleasePoint, SourceCheck
from ingest.release_label import parse_label
from storage.repository import SOURCE_URL

PRIOR_RELEASE_POINTS_URL = SOURCE_URL
"""Defined in `storage.repository` so `/api/v1/status` can name the source
without importing the ingest layer. Re-exported under this name because that is
what the CLI and the tests have always called it."""
DOWNLOAD_BASE_URL = "https://uscode.house.gov/download/"
INVENTORY_PATH = Path("data/uscreleasepoints.json")

USER_AGENT = (
    "uscode-redesign/0.1 (versioned US Code retrieval; "
    "+https://github.com/aih/uscode-redesign)"
)

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_ENTRY_RE = re.compile(
    r'<li class="releasepoint">\s*<a class="releasepoint" href="([^"]+)"\s*>(.*?)</a>',
    re.DOTALL,
)
_HREF_RE = re.compile(r"releasepoints/us/pl/\d+/[^/]+/usc-rp@(?P<label>[^.]+)\.htm")
_DATE_RE = re.compile(r"(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})")
_LONG_DATE_RE = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|September|October"
    r"|November|December)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})",
    re.IGNORECASE,
)
_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "january february march april may june july august september "
            "october november december"
        ).split(),
        start=1,
    )
}
_TITLES_RE = re.compile(r"affecting titles?\s+(?P<titles>[^.]+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


class InventoryParseError(ValueError):
    """Raised when the release-points page yields nothing parseable — i.e. OLRC
    changed its markup and this module needs revisiting, rather than the site
    having genuinely zero release points."""


@dataclass(frozen=True, slots=True)
class ReleasePointEntry:
    """One release point as the inventory knows it."""

    label: str
    """`119-102not101` — unique, and the `@` suffix in every download URL."""

    currency_date: date
    titles_affected: tuple[str, ...]
    """Title numbers in OLRC's file-naming form: `('05', '16')`, appendices `18a`."""

    url: str
    """The RP's own page on uscode.house.gov."""

    description: str
    """The link text verbatim, kept so a surprising parse can be audited."""

    seq: int = -1
    """Global ordering, oldest = 0. Assigned by `parse_inventory` from page order."""

    def zip_url(self, title_num: str) -> str:
        """Download URL for one title's XML zip at this release point."""
        return title_zip_url(self.label, title_num)

    def as_json(self) -> dict[str, object]:
        """The `uscreleasepoints.json` record shape (loadusc-xcitedb's keys)."""
        return {
            "name": self.label,
            "date": self.currency_date.isoformat(),
            "titlesAffected": list(self.titles_affected),
            "url": self.url,
            "seq": self.seq,
            "description": self.description,
        }

    @classmethod
    def from_json(cls, record: dict[str, object]) -> "ReleasePointEntry":
        return cls(
            label=str(record["name"]),
            currency_date=date.fromisoformat(str(record["date"])),
            titles_affected=tuple(str(t) for t in record.get("titlesAffected", [])),  # type: ignore[union-attr]
            url=str(record.get("url", "")),
            description=str(record.get("description", "")),
            seq=int(record.get("seq", -1)),  # type: ignore[arg-type]
        )


@dataclass
class _Draft:
    """Mutable accumulator so duplicate `<li>` entries can merge before freezing."""

    label: str
    currency_date: date
    url: str
    description: str
    titles: list[str] = field(default_factory=list)


def title_zip_url(release_label: str, title_num: str) -> str:
    """`https://…/releasepoints/us/pl/119/99/xml_usc16@119-99.zip`.

    The path segment is the label's `{congress}/{law_num}[not…][u…]` form, which is
    the label with its `-` replaced by `/` — not a re-derivation, so `u1` and
    compound `not` labels come out right without special cases.
    """
    congress, remainder = release_label.split("-", 1)
    return (
        f"{DOWNLOAD_BASE_URL}releasepoints/us/pl/{congress}/{remainder}/"
        f"xml_usc{normalize_title_num(title_num)}@{release_label}.zip"
    )


def normalize_title_num(title_num: str) -> str:
    """`'16'` → `'16'`, `'5'` → `'05'`, `'18A'` → `'18a'` — OLRC's file-naming form."""
    cleaned = title_num.strip().lower()
    match = re.match(r"^(\d+)(a?)$", cleaned)
    if not match:
        raise ValueError(f"not a title number: {title_num!r}")
    return f"{int(match.group(1)):02d}{match.group(2)}"


def fetch_inventory_html(url: str = PRIOR_RELEASE_POINTS_URL, *, timeout: int = 60) -> str:
    """GET the release-points page. One request, descriptive UA (CLAUDE.md etiquette)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset)


def parse_inventory(html: str) -> list[ReleasePointEntry]:
    """Parse the release-points page into entries, oldest first, `seq` assigned.

    Returned oldest-first because that is the order `seq` counts in and the order a
    backfill should ingest in; the page itself is newest-first.
    """
    body = _COMMENT_RE.sub("", html)
    drafts: dict[str, _Draft] = {}
    order: list[str] = []

    for href, raw_text in _ENTRY_RE.findall(body):
        href_match = _HREF_RE.search(href)
        if href_match is None:
            continue
        label = href_match.group("label")
        parse_label(label)  # reject anything that isn't a release-point label
        text = _clean_text(raw_text)
        entry_date = _parse_date(text)
        if entry_date is None:
            # Dropping a release point silently would leave a hole nothing later
            # notices — the ingest would just never be asked for that RP.
            warnings.warn(
                f"release point {label} has no parseable date, skipping: {text!r}",
                stacklevel=2,
            )
            continue
        titles = _parse_titles(text)

        draft = drafts.get(label)
        if draft is None:
            drafts[label] = _Draft(
                label=label,
                currency_date=entry_date,
                url=DOWNLOAD_BASE_URL + href,
                description=text,
                titles=list(titles),
            )
            order.append(label)
        else:
            # Same RP listed twice: union the titles (113-165's two entries carry
            # different ones), keep the first date and description.
            for title in titles:
                if title not in draft.titles:
                    draft.titles.append(title)

    if not drafts:
        raise InventoryParseError(
            f"no release points found — the markup at {PRIOR_RELEASE_POINTS_URL} "
            "has probably changed"
        )

    oldest_first = [drafts[label] for label in reversed(order)]
    return [
        ReleasePointEntry(
            label=draft.label,
            currency_date=draft.currency_date,
            titles_affected=tuple(draft.titles),
            url=draft.url,
            description=draft.description,
            seq=seq,
        )
        for seq, draft in enumerate(oldest_first)
    ]


def write_inventory(
    entries: list[ReleasePointEntry],
    path: Path = INVENTORY_PATH,
    *,
    source_url: str = PRIOR_RELEASE_POINTS_URL,
) -> Path:
    """Write `uscreleasepoints.json` (newest first, as loadusc-xcitedb wrote it)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "source_url": source_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "releasePoints": [entry.as_json() for entry in reversed(entries)],
    }
    path.write_text(json.dumps(document, indent=2) + "\n")
    return path


def read_inventory(path: Path = INVENTORY_PATH) -> list[ReleasePointEntry]:
    """Read back `uscreleasepoints.json`, oldest first."""
    document = json.loads(path.read_text())
    entries = [ReleasePointEntry.from_json(r) for r in document["releasePoints"]]
    return sorted(entries, key=lambda e: e.seq)


def latest_release_affecting(
    entries: list[ReleasePointEntry], title_num: str, *, before_seq: int
) -> ReleasePointEntry | None:
    """The newest RP before `before_seq` whose `titlesAffected` includes `title_num`.

    This is how a *meaningfully different* prior release point is chosen (PLAN Day 1
    item 3): most release points leave most titles byte-identical, so an arbitrary
    neighbour would dedupe down to the same `section_versions` rows and demonstrate
    nothing.
    """
    wanted = normalize_title_num(title_num)
    candidates = [
        entry
        for entry in entries
        if entry.seq < before_seq
        and any(normalize_title_num(t) == wanted for t in entry.titles_affected)
    ]
    return max(candidates, key=lambda e: e.seq) if candidates else None


def seed_release_points(session: Session, entries: list[ReleasePointEntry]) -> tuple[int, int]:
    """Upsert `release_points` from the inventory. Returns `(inserted, updated)`.

    Existing rows are updated in place rather than replaced: `119-102not101` was
    ingested before the inventory existed and carries foreign keys from
    `section_versions`, `section_release_map` and `guid_map`. What it gets here is
    its *real* `currency_date` and its true global `seq`, replacing BUILDLOG 005's
    per-ingest stopgap.
    """
    existing = {rp.label: rp for rp in session.scalars(select(ReleasePoint))}
    inserted = updated = 0

    # Two passes over a unique column: clear `seq` on every existing row first, so
    # renumbering can't collide with a value another row still holds.
    offset = max((rp.seq for rp in existing.values()), default=0) + len(entries) + 1
    for row in existing.values():
        row.seq += offset
    session.flush()

    for entry in entries:
        parsed = parse_label(entry.label)
        row = existing.get(entry.label)
        if row is None:
            session.add(
                ReleasePoint(
                    congress=parsed.congress,
                    law_num=parsed.law_num,
                    excluded_laws=list(parsed.excluded_laws),
                    update_num=parsed.update_num,
                    label=entry.label,
                    currency_date=entry.currency_date,
                    seq=entry.seq,
                    titles_affected=list(entry.titles_affected),
                )
            )
            inserted += 1
        else:
            row.congress = parsed.congress
            row.law_num = parsed.law_num
            row.excluded_laws = list(parsed.excluded_laws)
            row.update_num = parsed.update_num
            row.currency_date = entry.currency_date
            row.seq = entry.seq
            row.titles_affected = list(entry.titles_affected)
            updated += 1
    session.flush()
    return inserted, updated


@dataclass(frozen=True, slots=True)
class CheckResult:
    """What one poll of uscode.house.gov found. Mirrors the `source_checks` row."""

    ok: bool
    entries: list[ReleasePointEntry]
    new_labels: tuple[str, ...]
    """Labels on the page that `release_points` did not already hold."""
    inserted: int = 0
    updated: int = 0
    error: str | None = None

    @property
    def has_new_release_points(self) -> bool:
        return bool(self.new_labels)


def record_source_check(
    session: Session,
    *,
    source_url: str,
    ok: bool,
    entries: list[ReleasePointEntry] | None = None,
    new_labels: tuple[str, ...] = (),
    error: str | None = None,
) -> SourceCheck:
    """Write one `source_checks` row. Called on success *and* on failure.

    The failure case is the one that matters: a check that could not reach the
    page still proves the checker itself is alive, and distinguishes "OLRC has
    published nothing new" from "we stopped asking three weeks ago". Nothing
    else in the system can tell those apart.
    """
    newest = entries[-1] if entries else None
    row = SourceCheck(
        source_url=source_url,
        ok=ok,
        release_points_seen=len(entries) if entries is not None else None,
        new_labels=list(new_labels),
        latest_label=newest.label if newest else None,
        latest_currency_date=newest.currency_date if newest else None,
        # Truncated: an error here is a one-line diagnosis, and a stack trace or
        # an HTML error page would push a status response into the kilobytes.
        error=(error[:500] if error else None),
    )
    session.add(row)
    return row


def poll_source(
    session: Session,
    *,
    url: str = PRIOR_RELEASE_POINTS_URL,
    out_path: Path | None = INVENTORY_PATH,
    seed: bool = True,
) -> CheckResult:
    """Fetch the release-points page, seed what is new, and record the check.

    One network request (CLAUDE.md's source etiquette) and one `source_checks`
    row per call, whatever happens. Commits nothing — the caller owns the
    transaction, because on the success path the check row and the release
    points it describes should land together or not at all.
    """
    try:
        html = fetch_inventory_html(url)
        entries = parse_inventory(html)
    except Exception as exc:  # network, HTTP, or InventoryParseError
        record_source_check(session, source_url=url, ok=False, error=f"{type(exc).__name__}: {exc}")
        return CheckResult(ok=False, entries=[], new_labels=(), error=f"{type(exc).__name__}: {exc}")

    if out_path is not None:
        write_inventory(entries, out_path, source_url=url)

    # Computed BEFORE seeding, or seeding would make every label look known.
    known = {label for label in session.scalars(select(ReleasePoint.label))}
    new_labels = tuple(entry.label for entry in entries if entry.label not in known)

    inserted = updated = 0
    if seed:
        inserted, updated = seed_release_points(session, entries)

    record_source_check(
        session, source_url=url, ok=True, entries=entries, new_labels=new_labels
    )
    return CheckResult(
        ok=True,
        entries=entries,
        new_labels=new_labels,
        inserted=inserted,
        updated=updated,
    )


def _clean_text(raw: str) -> str:
    return " ".join(_TAG_RE.sub("", raw).split())


def _parse_date(text: str) -> date | None:
    """The release point's currency date, out of prose.

    First `M/D/YYYY` wins: a later date in the same entry is a qualifier, as in
    118-250's "…and including Public Law 119-1 (January 29, 2025)". A spelled-out
    date is only used when there is no numeric one at all — true for exactly one
    entry, 115-40u1's "(effective July 1, 2017)", which would otherwise be dropped
    from the inventory in silence.
    """
    match = _DATE_RE.search(text)
    if match is not None:
        return date(
            int(match.group("year")), int(match.group("month")), int(match.group("day"))
        )
    long_match = _LONG_DATE_RE.search(text)
    if long_match is None:
        return None
    return date(
        int(long_match.group("year")),
        _MONTHS[long_match.group("month").lower()],
        int(long_match.group("day")),
    )


def _parse_titles(text: str) -> tuple[str, ...]:
    match = _TITLES_RE.search(text)
    if match is None:
        return ()
    titles: list[str] = []
    for token in re.split(r",|\band\b", match.group("titles")):
        token = token.strip()
        if not token:
            continue
        try:
            normalized = normalize_title_num(token)
        except ValueError:
            continue  # e.g. "all titles" prose — recorded in `description`
        if normalized not in titles:
            titles.append(normalized)
    return tuple(titles)
