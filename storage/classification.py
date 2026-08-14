"""The `ClassificationRepository` interface — OLRC's Classification Tables (ADR-0067).

The third storage protocol, on the ADR-0017 pattern. What lives here is neither
version resolution (`Repository`) nor account CRUD (`AccountsRepository`): it is
a mirror of a set of published documents saying which provision of which public
law was classified to which Code section. It gets its own module for ADR-0017's
reason — `Repository`'s whole shape is "how do we answer for a provision at a
release point", and none of these questions have a release point in them — and
the same rule holds across all three: no SQL and no database session in `api/`.

A section number is spelled two ways here and the spellings are not
interchangeable (gotcha 17):

  * **`section_norm`** is the table's own hyphen, lowercased — `254c-15`. It is
    what typed input is matched against, so a route taking a `?section=` or a
    path segment normalizes to it with `normalize_section_input`.
  * **`usc_identifier`** is the corpus's spelling, with an EN DASH —
    `/us/usc/t42/s254c–15`. A route matching an incoming `@identifier` has to
    try both, because no keyboard has that key and a link may arrive either way
    (`identifier_variants`).

Measured over the loaded corpus: 143,304 of the 144,837 rows derive a
`usc_identifier`, naming 40,967 distinct identifiers. 9,163 of those rows
contain an EN DASH, across 3,398 distinct identifiers, and **none contains a
plain hyphen** — so an identifier typed with one matches nothing unless
something tries the variant.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from storage.repository import SOURCE_CHECK_STALE_AFTER

CLASSIFICATION_SOURCE_URL = "https://uscode.house.gov/classification/tables.shtml"
"""The Classification Tables entry page, and the only thing
`/api/v1/classifications/tables` can name as the source when no check has ever
run. Defined here rather than in `ingest` so the API can name it without
importing the ingest layer, which is the `SOURCE_URL` precedent in
`storage/repository.py`; `ingest.classification` imports it back."""

#: U+2013 EN DASH, U+2011 NON-BREAKING HYPHEN → the plain hyphen `section_norm`
#: holds. The same folding the parser applied on the way in, so input typed on a
#: keyboard and text copied out of the Code both land on the stored spelling.
_DASHES = {"–": "-", "‑": "-", "—": "-"}

EN_DASH = "–"


class ClassificationError(Exception):
    """Base for the errors this interface raises rather than returning None."""


class UnknownPublicLawError(ClassificationError):
    """No classification table covers this public law.

    Distinct from "a table covers it and it classified nothing", which is an
    empty page and a 200. `covered_ranges` is gap-aware — the 119th's first
    session file covers `1-69` and `71-73` while its second covers `70-70` and
    `74-102` — so the two answers are both real and mean different things: one
    says the source has not published this law's table yet, the other says the
    law amended nothing that lands in the Code.
    """

    def __init__(self, congress: int, law_num: int):
        super().__init__(
            f"no classification table covers Public Law {congress}-{law_num}"
        )
        self.congress = congress
        self.law_num = law_num


def normalize_section_input(section: str) -> str:
    """Typed section number → the `section_norm` spelling: lowercased, dashes folded.

    `254C–15` and `254c-15` are the same section, and the second is what the
    database holds.
    """
    text = section.strip().lower()
    for dash, plain in _DASHES.items():
        text = text.replace(dash, plain)
    return text


def identifier_variants(identifier: str) -> tuple[str, ...]:
    """Every spelling of a US Code identifier worth looking up, as given first.

    The corpus writes `/us/usc/t42/s254c–15` with an EN DASH and never with a
    plain hyphen, and `usc_identifier` is derived to match it. A caller handing
    us a path typed on a keyboard, or one that survived a round trip through a
    system that folded the dash, would otherwise match nothing.
    """
    variants = [identifier]
    swapped = identifier.replace("-", EN_DASH)
    if swapped != identifier:
        variants.append(swapped)
    plain = identifier.replace(EN_DASH, "-")
    if plain not in variants:
        variants.append(plain)
    return tuple(variants)


def session_label(session: int) -> str:
    """`1` | `2` | `all` — the spelling the reader's URLs use for a session.

    `0` is the 104th's single whole-congress file, which the database holds as a
    sentinel because the unique key that makes a re-fetch update a row in place
    could not use a NULL.
    """
    return "all" if session == 0 else str(session)


def law_in_ranges(law_num: int, ranges: Iterable[str]) -> bool:
    """Whether a law number falls inside any `'70-70'`-style covered segment.

    The predicate behind `UnknownPublicLawError`, and behind the parser's own
    check that a file's rows stay inside the range its header claims. It lives
    on this side of the boundary so both may import it: `ingest` already reaches
    into `storage.repository` for `SOURCE_URL`, and the reverse direction would
    make the API depend on the scraper.
    """
    return any(
        int(segment.split("-")[0]) <= law_num <= int(segment.split("-")[1])
        for segment in ranges
    )


@dataclass(frozen=True, slots=True)
class ClassificationFileInfo:
    """One source document in the registry — a `pl` table or an ECCT.

    `session` is 1 or 2 with **0 for the 104th's single whole-congress file**.
    The reader's URL vocabulary spells that `all` (spec §5); the database never
    holds a NULL here, because the unique key that makes a re-fetch update in
    place would not work if it did.
    """

    kind: str
    """`'pl'` | `'ecct'` — a string and not an enum, because the source has
    already added one document type to this family."""

    congress: int
    session: int
    source_url: str
    source_filename: str
    covered_laws_text: str | None
    covered_ranges: tuple[str, ...]
    """Gap-aware segments (`('70-70', '74-102')`). What `law_in_ranges` reads."""

    first_law: int | None
    last_law: int | None
    prepared_date: datetime.date | None
    stat_volume: int | None
    """The Statutes at Large volume from the column header. None for the 104th,
    whose congress spans two volumes and whose header therefore names neither."""

    content_hash: str
    fetched_at: datetime.datetime
    row_count: int
    skipped_lines: int

    @property
    def session_label(self) -> str:
        """`1` | `2` | `all` — the spelling the reader's URLs use for `session`."""
        return session_label(self.session)


@dataclass(frozen=True, slots=True)
class ClassificationEntryRef:
    """One row of a Classification Table, plus which document it came from.

    Some fields are nullable for reasons that are not failures, and a caller
    that filters them out is dropping real rows:

      * `usc_identifier` is null for 1,533 of the loaded rows, 1,531 of them
        appendix rows which derive none by rule (ADR-0067 decision 7).
      * `pl_congress`/`pl_num` — and so `pl_label` — are null for 2 rows whose
        Pub. L. cell could not be read. The rows are kept and warned about.
      * `stat_pages` is empty for 6,053 rows that do cite a page, because a page
        of the Statutes at Large is not always a number: `110 Stat. 3009-587`
        and `113 Stat. 1501A-594` are single pages. **`stat_page_labels` is the
        column to display**; `stat_pages` is what a statviewer link can be built
        from, and only alongside a `stat_volume`.
    """

    congress: int
    """The congress of the *file*, which is also the session page this row is on."""

    session: int
    row_seq: int
    raw_line: str
    title_raw: str
    title_num: str
    """A string (`'5a'`). Ordered only through `storage.postgres.title_sort_key`
    (gotcha 16)."""

    is_appendix: bool
    section_raw: str
    section_norm: str
    description_raw: str
    """`''` means the section was amended. An open set otherwise."""

    is_note: bool
    action: str | None
    transfer_counterpart: str | None
    act_name: str | None
    usc_identifier: str | None
    pl_congress: int | None
    pl_num: int | None
    pl_section_raw: str
    new_section_quote: str | None
    stat_volume: int | None
    stat_pages: tuple[int, ...]
    stat_page_labels: tuple[str, ...]

    @property
    def pl_label(self) -> str | None:
        """`'118-35'`, or None when the Pub. L. cell did not parse."""
        if self.pl_congress is None or self.pl_num is None:
            return None
        return f"{self.pl_congress}-{self.pl_num}"

    @property
    def session_label(self) -> str:
        return session_label(self.session)


@dataclass(frozen=True, slots=True)
class EcctEntryRef:
    """One row of the Editorial Classification Change Table: a provision OLRC
    moved without Congress amending it."""

    congress: int
    session: int
    row_seq: int
    former_raw: str
    former_title_num: str | None
    former_section_norm: str | None
    former_is_note: bool
    new_raw: str
    new_title_num: str | None
    new_section_norm: str | None
    new_is_note: bool
    provision_affected: str
    provision_prompting: str
    affected_pl_congress: int | None
    affected_pl_num: int | None
    prompting_pl_congress: int | None
    prompting_pl_num: int | None

    @property
    def session_label(self) -> str:
        return session_label(self.session)


@dataclass(frozen=True, slots=True)
class ClassificationPage:
    """One page of entries, with the size of the whole set it came from.

    `total` counts the rows the filters matched, not the rows returned — it is
    what a pager needs and what a page cannot infer from its own length.
    """

    items: tuple[ClassificationEntryRef, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class ClassificationCheckInfo:
    """The last time this deployment asked OLRC what classification tables exist.

    A sibling of `SourceCheckInfo` and deliberately not a reuse of it:
    `Repository.last_source_check()` reads the newest `source_checks` row
    regardless of URL and feeds `/api/v1/status`, so interleaving the two would
    make the corpus-freshness answer flap between two unrelated sources
    (ADR-0067 decision 4).
    """

    checked_at: datetime.datetime
    source_url: str
    ok: bool
    files_seen: int | None
    changed_files: tuple[str, ...]
    """Source filenames whose covered-law text differs from the registry — the
    answer to "was there anything new", recorded because the next load erases
    the evidence."""

    latest_covered_text: str | None
    error: str | None

    def age(self, *, now: datetime.datetime | None = None) -> datetime.timedelta:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        checked_at = self.checked_at
        # Postgres hands back an aware datetime; SQLite in tests may not, and a
        # naive/aware subtraction raises rather than returning a wrong answer.
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=datetime.timezone.utc)
        return now - checked_at

    def is_stale(self, *, now: datetime.datetime | None = None) -> bool:
        """A failed check is stale immediately — it confirmed nothing."""
        return not self.ok or self.age(now=now) > SOURCE_CHECK_STALE_AFTER


class ClassificationRepository(Protocol):
    """Everything `api/classification.py` needs. Implemented by
    `PostgresClassification` today."""

    def last_classification_check(self) -> ClassificationCheckInfo | None:
        """The most recent poll of the Classification Tables index, successful or
        not. `None` means no check has ever been recorded here."""
        ...

    def list_files(self, *, kind: str | None = None) -> list[ClassificationFileInfo]:
        """The registry, newest congress and session first."""
        ...

    def get_file(
        self, *, congress: int, session: int, kind: str = "pl"
    ) -> ClassificationFileInfo | None:
        """One document by its `(kind, congress, session)` key."""
        ...

    def file_covering_law(
        self, *, congress: int, law_num: int
    ) -> ClassificationFileInfo | None:
        """The `pl` document whose covered ranges contain this law, or None.

        None is what makes a `/classifications/pl/…` request a 404 rather than
        an empty page, and it is also how the lookup decides whether a public
        law has a session page to point at.
        """
        ...

    def entries_for_file(
        self,
        *,
        congress: int,
        session: int,
        sort: str = "pl",
        pl_congress: int | None = None,
        pl_num: int | None = None,
        pl_section: str | None = None,
        title_num: str | None = None,
        section: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ClassificationPage:
        """One session page's rows, filtered and paged.

        `sort='pl'` is the source's own order (`row_seq`). `sort='code'` is the
        Code's order — title through `title_sort_key`, then `section_norm`
        (gotcha 16).
        """
        ...

    def entries_for_law(
        self,
        *,
        congress: int,
        law_num: int,
        section: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ClassificationPage:
        """Everything one public law classified, in source order.

        Raises `UnknownPublicLawError` when no document covers the law, which is
        the answer that differs from an empty page.
        """
        ...

    def entries_for_section(
        self,
        *,
        title_num: str,
        section: str,
        congress: int | None = None,
        exact: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> ClassificationPage:
        """Everything ever classified to one Code section, newest law first —
        which is the order a section's classification history reads in.

        `section` is matched against `section_norm`, so the caller normalizes
        with `normalize_section_input` first.
        """
        ...

    def entries_for_identifier(
        self, identifier: str, *, limit: int = 200, offset: int = 0
    ) -> ClassificationPage:
        """Rows whose derived `usc_identifier` is this one, newest law first.

        Both dash spellings are tried, because the stored value uses an EN DASH
        and a caller's may not (`identifier_variants`).

        Paged like the rest. 14 identifiers carry more than 200 rows and
        `/us/usc/t10/s113` carries 412, so a section's history is longer than one
        page often enough that the page has to be reachable — and the order is
        newest law first, which puts the oldest classifications last.
        """
        ...

    def list_ecct(
        self, *, congress: int | None = None, session: int | None = None
    ) -> list[EcctEntryRef]:
        """The Editorial Classification Change Table, newest session first. Small
        enough to return whole — 21 rows across two documents."""
        ...
