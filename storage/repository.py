"""The `Repository` interface — the only thing `api/` and `web/` are allowed to know.

CLAUDE.md architecture rule 1: Postgres is implementation v1, XCiteDB becomes a
second implementation with no API or UI change. So nothing below mentions a table,
a column, or SQL; the results are plain frozen dataclasses, and every
version-resolution decision (which release point, which version of a section,
which fragment of it) happens behind this line rather than in a route handler.

The vocabulary of release points is the part worth reading carefully, because
three different release points can be involved in answering one request:

  * **requested** — what the URL asked for, as a label or a `?date=`.
  * **served_from** — the newest *ingested* release point at or before the
    requested one that carries this title. Every release point republishes all
    titles but few change any (gotcha 10), so an un-ingested release point's text
    is exactly the text of the last ingested one before it — a fact worth
    answering with, rather than 404ing on, as long as the answer says so.
  * **content_first_seen** — the release point whose bytes are stored, which may be
    older still, because identical content is deduped across release points
    (ADR-0007).

For `/us/usc/t16/s45f` at `?release=119-100`, those are 119-100, 119-99 and 119-99:
119-100 changed only title 47, so nothing about Title 16 moved, and saying so is
more useful than pretending 119-100 was never published.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


class RepositoryError(Exception):
    """Base for the errors a repository raises rather than returning None."""


class RepositoryUnavailableError(RepositoryError):
    """The store cannot answer right now — it is at capacity, not broken.

    Raised when every connection is in use and the wait for one expired
    (ADR-0073). It is a distinct error because the honest answer to it is 503
    and a retry, where every other `RepositoryError` here describes something
    about the request. An implementation over XCiteDB would raise this for its
    own equivalent; nothing outside `storage/` names the database library's.
    """


class ReleaseNotFoundError(RepositoryError):
    """No release point matches the requested label or date."""


class AmbiguousReleaseError(RepositoryError):
    """A bare label matches several release points and none of them exactly.

    Real case: `119-102` is not itself a published release point — `119-102not101`
    is. One candidate is a match with a note; several is a question for the caller.
    """

    def __init__(self, requested: str, candidates: list[str]):
        super().__init__(
            f"release {requested!r} matches {len(candidates)} release points: "
            + ", ".join(candidates)
        )
        self.requested = requested
        self.candidates = candidates


@dataclass(frozen=True, slots=True)
class ReleaseRef:
    """One release point, as everything outside storage sees it."""

    label: str
    currency_date: datetime.date
    seq: int
    congress: int
    law_num: int
    excluded_laws: tuple[int, ...] = ()
    update_num: int | None = None
    titles_affected: tuple[str, ...] = ()
    ingested_titles: tuple[str, ...] = ()

    @property
    def is_partial(self) -> bool:
        """True when the label excludes laws — `119-102not101`.

        Gotcha 5: at such a release point the text is *not* fully current through
        its date, and a UI that shows only the date is lying by omission.
        """
        return bool(self.excluded_laws)

    @property
    def caveat(self) -> str | None:
        """Human-readable form of `is_partial`, for the UI to surface verbatim."""
        if not self.excluded_laws:
            return None
        excluded = ", ".join(f"{self.congress}-{law}" for law in self.excluded_laws)
        return (
            f"Current through Public Law {self.congress}-{self.law_num} "
            f"({self.currency_date:%m/%d/%Y}), except {excluded}."
        )


@dataclass(frozen=True, slots=True)
class ResolvedRelease:
    """The outcome of `?release=` / `?date=` resolution (PLAN §3 step 1)."""

    release: ReleaseRef
    requested_label: str | None = None
    requested_date: datetime.date | None = None
    note: str | None = None
    """Set when the answer isn't literally what was asked for — a bare `119-102`
    resolving to `119-102not101`, or a date landing between release points."""

    @property
    def is_exact(self) -> bool:
        return self.requested_label is None or self.requested_label == self.release.label


@dataclass(frozen=True, slots=True)
class TocEntry:
    """A child of a TOC node: a structural node, or a section leaf."""

    identifier: str
    level: str
    """`chapter`, `subchapter`, … or `section` for a leaf."""

    num: str | None
    heading: str | None
    status: str | None = None
    is_section: bool = False


@dataclass(frozen=True, slots=True)
class Provision:
    """A sub-section provision extracted from its section at request time (ADR-0001)."""

    identifier: str
    found: bool
    xml: str | None = None


@dataclass(frozen=True, slots=True)
class DuplicateOccurrence:
    """A further element the source published under the *same* `@identifier` at the
    same release point.

    OLRC's XML occasionally repeats a section: Title 19 at 117-80 carries three
    `<section identifier="/us/usc/t19/s2502">` elements — two empty stubs headed
    "Purposes" and then the real "Congressional statement of purposes" — and
    Title 54 at 113-296not287 repeats three sections with differing amounts of
    notes. These are not the quoted statutory text an amending act carries, which
    the parser drops (gotcha 12, ADR-0005): they hold real `@identifier` and
    `@id` values, so the parser is right to emit them and storage right to keep
    them.

    Because they are indistinguishable by identifier, no rule picks a winner
    honestly — so every occurrence is served and the reader says so (ADR-0021).
    """

    num: str | None
    heading: str | None
    status: str | None
    xml: str
    content_hash: str
    guid: str | None
    seq_in_title: int
    source_credit: str | None


@dataclass(frozen=True, slots=True)
class SectionResult:
    """One section at one release point, plus the provision the URL pointed at."""

    identifier: str
    title_num: str
    num: str | None
    heading: str | None
    status: str | None
    xml: str
    content_hash: str
    """Hex sha256 of the guid-stripped content (ADR-0007). Stable per (section,
    text) across release points, which makes it the natural ETag."""

    source_credit: str | None
    seq_in_title: int
    parent_identifier: str | None

    ancestors: tuple[TocEntry, ...]
    """Breadcrumb from the title root down to the section's parent, inclusive.

    Carried on the section because the alternative — the reader fetching the
    parent's whole TOC to keep two fields of it — cost a chapter-wide section
    query per section page (PLAN Day 6b). Bounded by the structural depth of the
    Code, so two to four entries.

    Approximate in the same way the TOC is: `structure_nodes` holds one row per
    node, the newest loaded release's view (ADR-0006), so a chapter renamed
    between release points shows its current name here.
    """

    guid: str | None
    """The section's `@id` at `served_from` — the stable citation for this text at
    this release point (ADR-0003)."""

    release: ReleaseRef
    served_from: ReleaseRef
    content_first_seen: ReleaseRef
    provision: Provision | None = None

    duplicates: tuple[DuplicateOccurrence, ...] = ()
    """Further elements published under this identifier at this release point, in
    source reading order after this one. Empty for all but a handful of
    title-releases — see `DuplicateOccurrence` and ADR-0021."""

    @property
    def is_duplicated(self) -> bool:
        """True when the source published this identifier more than once here."""
        return bool(self.duplicates)

    @property
    def occurrence_count(self) -> int:
        return 1 + len(self.duplicates)

    @property
    def is_exact(self) -> bool:
        """False when the requested release point isn't ingested and an earlier one
        answered for it."""
        return self.release.label == self.served_from.label


@dataclass(frozen=True, slots=True)
class TocResult:
    node: TocEntry
    ancestors: tuple[TocEntry, ...]
    """Breadcrumb from the title root down to the node's parent."""

    children: tuple[TocEntry, ...]
    """Structural children, in document order."""

    sections: tuple[TocEntry, ...]
    """Sections whose immediate parent is this node, in reading order — repealed and
    omitted ones included and badged (gotcha 9)."""

    release: ReleaseRef
    served_from: ReleaseRef


@dataclass(frozen=True, slots=True)
class Neighbors:
    """Previous and next section in reading order at one release point."""

    identifier: str
    previous: TocEntry | None
    next: TocEntry | None
    release: ReleaseRef
    served_from: ReleaseRef


@dataclass(frozen=True, slots=True)
class VersionLawRef:
    """A Public Law attributed to one version transition (ADR-0074)."""

    pl_congress: int
    pl_num: int
    in_classification: bool
    """A classification row for this law names this section."""

    is_note_classification: bool
    """Only note rows name it."""

    in_source_credit: bool
    """The citation newly appears in `source_credit` across the transition."""

    classification_actions: tuple[str, ...]
    """Distinct `action` values of the matching rows (`''` = amended, `new`,
    `repealed`, `tr to`, …)."""


@dataclass(frozen=True, slots=True)
class SectionVersionInfo:
    """One entry in a section's change timeline.

    Entries are ordered by the earliest release each is mapped to —
    `releases[0]` — never by `first_seen`, which an incremental load leaves
    high (ADR-0066). `first_seen` stays in the payload for compatibility.

    The change annotations come from `section_version_changes` (ADR-0074) and
    are all `None` when no change row exists for the entry — a corpus loaded
    but not back-filled.
    """

    content_hash: str
    first_seen: ReleaseRef
    releases: tuple[str, ...]
    """Every ingested release point publishing this exact content, oldest first."""

    num: str | None
    heading: str | None
    status: str | None

    change_kind: str | None = None
    """'initial' | 'text' | 'notes' | 'structure'."""

    text_changed: bool | None = None
    notes_changed: bool | None = None
    status_changed: bool | None = None
    concurrent: bool | None = None
    """The two groups' release ranges overlap (ADR-0021, ADR-0074) — window
    arithmetic is unreliable for this transition."""

    attribution: str | None = None
    """'classified' | 'none'."""

    laws: tuple[VersionLawRef, ...] = ()


@dataclass(frozen=True, slots=True)
class GuidResolution:
    """What a `?id=` lookup found. No release parameter needed — the guid is one."""

    guid: str
    identifier: str
    release: ReleaseRef
    is_section: bool
    section_identifier: str | None
    """The section to open in order to show this provision; None if the guid names
    a structural node, which is a TOC destination instead."""


@dataclass(frozen=True, slots=True)
class TitleInfo:
    num: str
    name: str
    is_positive_law: bool
    ingested_releases: tuple[str, ...] = field(default=())


SOURCE_URL = "https://uscode.house.gov/download/priorreleasepoints.htm"
"""The page this mirror polls, and the only thing `/api/v1/status` can say
about the source when no check has ever run. Defined here rather than in
`ingest` so the API can name it without importing the ingest layer;
`ingest.inventory` imports it back as `PRIOR_RELEASE_POINTS_URL`."""

SOURCE_CHECK_STALE_AFTER = datetime.timedelta(days=7)
"""How old a successful check may get before the mirror should stop claiming to
be current. This is the *lower* bound on the checking cadence — the schedule
polls daily (deploy/update-corpus.sh), so a week without a successful check
means several consecutive failures or a checker that is no longer running,
either of which a reader deserves to be told about rather than shown a
confident date."""


@dataclass(frozen=True, slots=True)
class SourceCheckInfo:
    """The last time this deployment asked uscode.house.gov what exists.

    Freshness is a property of a *mirror*, not of the law, and it is the one
    thing a reader cannot check for themselves: a corpus that stopped updating
    a month ago looks exactly like a corpus with nothing to update. So the
    answer to "how current is this" has two halves, and both are here — the
    newest release point we hold (`latest_label`) and when we last confirmed
    that is still the newest one OLRC publishes (`checked_at`).
    """

    checked_at: datetime.datetime
    source_url: str
    ok: bool
    release_points_seen: int | None
    new_labels: tuple[str, ...]
    """Release points that check found and this database had not seen before —
    empty on a check that found nothing new, which is the usual answer."""
    latest_label: str | None
    latest_currency_date: datetime.date | None
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
        """A failed check is stale immediately — it did not confirm anything."""
        return not self.ok or self.age(now=now) > SOURCE_CHECK_STALE_AFTER


class Repository(Protocol):
    """Everything the API needs. Implemented by `PostgresRepository` today."""

    def corpus_generation(self) -> int:
        """The corpus write counter (ADR-0078) — moved by every ingest write.

        Read it **before** any data read whose result will be cached under it:
        under `READ COMMITTED` each statement sees what was committed before it
        began, so a value computed after the generation was read is either
        correct for that generation or stored under a generation no later
        request will ask for. Read after the data, that argument fails.
        """
        ...

    def last_source_check(self) -> SourceCheckInfo | None:
        """The most recent poll of uscode.house.gov, successful or not.

        `None` means no check has ever been recorded — a corpus seeded from a
        dump on a box whose checker has never run, which is a different (and
        louder) answer than "checked, nothing new".
        """
        ...

    def resolve_release(
        self,
        *,
        label: str | None = None,
        on_date: datetime.date | None = None,
        title_num: str | None = None,
    ) -> ResolvedRelease:
        """Turn `?release=` / `?date=` into one release point (PLAN §3 step 1).

        With neither, the newest release point wins. `title_num` only sharpens the
        default: "newest" then means the newest one this title is ingested at, so a
        bare request answers with real content instead of an empty newest release.
        """
        ...

    def list_releases(self, *, title_num: str | None = None) -> list[ReleaseRef]:
        """All known release points, newest first, with changed-title flags."""
        ...

    def list_titles(self) -> list[TitleInfo]:
        """Every ingested title, **in the Code's own order**: `1, 2, … 5, 5a, 6,
        … 11, 11a, 12, …`, each appendix title directly after its parent.

        The ordering is part of the contract, not the caller's problem. A title
        number is a *string* (`5a` is a title and so is `5`), so any
        implementation that sorts it as one produces `1, 10, 11, 11a, 12, … 2,
        20` — which is what this interface shipped until it said otherwise.
        """
        ...

    def get_section(
        self, identifier: str, release: ResolvedRelease
    ) -> SectionResult | None:
        """Resolve an identifier — section or provision path — at a release point.

        Longest-prefix match (PLAN §3 step 2): `/us/usc/t16/s45f/c/5` resolves to
        section `/us/usc/t16/s45f` with `/c/5` extracted from its XML, so the reader
        always gets the provision *in context*.
        """
        ...

    def resolve_id(self, guid: str) -> GuidResolution | None:
        """`GET /us/usc/?id=idXXXX`. A guid pins (provision, release point)."""
        ...

    def get_toc(self, identifier: str, release: ResolvedRelease) -> TocResult | None:
        ...

    def neighbors(self, identifier: str, release: ResolvedRelease) -> Neighbors | None:
        """Prev/next in reading order, skipping nothing (gotcha 9)."""
        ...

    def versions(self, identifier: str) -> list[SectionVersionInfo]:
        """The release points at which a section's content changed, oldest first.

        Ordered by each entry's earliest mapped release (`releases[0]`),
        tie-broken deterministically (ADR-0066).
        """
        ...

    def labels(
        self, identifiers: Sequence[str], release: ResolvedRelease
    ) -> dict[str, TocEntry]:
        """Num, heading and status for many identifiers at once.

        This exists for one reason: a section's text can carry forty cross
        references, and a reader that wants to show what each one *says* — hover
        text, so a citation is legible without following it — must not ask forty
        times. Identifiers that name nothing this database holds are simply absent
        from the result; a missing label is a missing courtesy, never an error.

        The identifiers may span titles, and each title resolves to its own
        served-from release point, because a release point ingested for Title 16
        may not exist for Title 54 (gotcha 10).
        """
        ...
