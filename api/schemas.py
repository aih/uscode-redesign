"""Response models — the public JSON contract, and the OpenAPI docs.

These are a deliberate translation of `storage`'s dataclasses rather than a reuse
of them: the wire format is a promise to clients and should not move just because
an internal field was renamed. Nothing here imports from `db`.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field

from api.diff import DiffOp
from citeparse import ParsedCitation
from storage import (
    GuidResolution,
    Neighbors,
    ReleaseRef,
    SectionResult,
    SectionVersionInfo,
    SourceCheckInfo,
    TitleInfo,
    TocEntry,
    TocResult,
    WatchlistItemRef,
    WatchlistRef,
)


class ReleaseOut(BaseModel):
    label: str = Field(examples=["119-102not101"])
    currency_date: datetime.date
    congress: int
    law_num: int
    excluded_laws: list[int] = Field(
        default_factory=list,
        description="Public laws enacted by the currency date but NOT incorporated.",
    )
    update_num: int | None = Field(
        default=None, description="The `u1` suffix, for re-issued release points."
    )
    seq: int = Field(description="Global ordering. Release-point labels do not sort.")
    is_partial: bool = Field(
        description="True when laws are excluded — the text is not fully current "
        "through currency_date."
    )
    caveat: str | None = None
    titles_affected: list[str] = Field(default_factory=list)
    ingested_titles: list[str] = Field(default_factory=list)

    @classmethod
    def of(cls, release: ReleaseRef) -> "ReleaseOut":
        return cls(
            label=release.label,
            currency_date=release.currency_date,
            congress=release.congress,
            law_num=release.law_num,
            excluded_laws=list(release.excluded_laws),
            update_num=release.update_num,
            seq=release.seq,
            is_partial=release.is_partial,
            caveat=release.caveat,
            titles_affected=list(release.titles_affected),
            ingested_titles=list(release.ingested_titles),
        )


class ProvisionOut(BaseModel):
    identifier: str
    found: bool
    xml: str | None = None


class DuplicateOccurrenceOut(BaseModel):
    """One further element published under the same @identifier at the same release
    point. See `SectionOut.duplicates` and ADR-0021."""

    num: str | None = None
    heading: str | None = None
    status: str | None = None
    xml: str
    content_hash: str
    guid: str | None = None
    seq_in_title: int
    source_credit: str | None = None


class TocEntryOut(BaseModel):
    identifier: str
    level: str
    num: str | None
    heading: str | None
    status: str | None = None
    is_section: bool = False

    @classmethod
    def of(cls, entry: TocEntry) -> "TocEntryOut":
        return cls(
            identifier=entry.identifier,
            level=entry.level,
            num=entry.num,
            heading=entry.heading,
            status=entry.status,
            is_section=entry.is_section,
        )


class SectionOut(BaseModel):
    identifier: str
    title_num: str
    num: str | None
    heading: str | None
    status: str | None = Field(
        default=None, description="repealed | omitted | transferred | … (never an enum)"
    )
    guid: str | None = Field(
        default=None,
        description="The section's @id at served_from — the citation for this exact "
        "text at this exact release point.",
    )
    source_credit: str | None = None
    seq_in_title: int
    parent_identifier: str | None
    ancestors: list[TocEntryOut] = Field(
        default_factory=list,
        description="Breadcrumb from the title root down to the section's parent, "
        "inclusive. Carried here so a reader needn't fetch the parent's table of "
        "contents to draw a breadcrumb trail.",
    )
    xml: str
    provision: ProvisionOut | None = None
    duplicates: list["DuplicateOccurrenceOut"] = Field(
        default_factory=list,
        description="Further elements the source published under this same "
        "@identifier at this same release point, in reading order after this one. "
        "Normally empty; when it isn't, the published XML repeats the section and "
        "every occurrence is returned rather than one being picked (ADR-0021).",
    )
    release: ReleaseOut = Field(description="The release point that was asked for.")
    served_from: ReleaseOut = Field(
        description="The ingested release point this content is published at. Differs "
        "from `release` when the requested release point isn't loaded; its text is "
        "unchanged from this one."
    )
    content_first_seen: ReleaseOut = Field(
        description="Where these bytes first appeared. Identical content is stored "
        "once across release points, so the fragment's @id values are this one's."
    )
    is_exact: bool
    note: str | None = None

    @classmethod
    def of(cls, section: SectionResult, note: str | None = None) -> "SectionOut":
        return cls(
            identifier=section.identifier,
            title_num=section.title_num,
            num=section.num,
            heading=section.heading,
            status=section.status,
            guid=section.guid,
            source_credit=section.source_credit,
            seq_in_title=section.seq_in_title,
            parent_identifier=section.parent_identifier,
            ancestors=[TocEntryOut.of(entry) for entry in section.ancestors],
            xml=section.xml,
            provision=(
                ProvisionOut(
                    identifier=section.provision.identifier,
                    found=section.provision.found,
                    xml=section.provision.xml,
                )
                if section.provision
                else None
            ),
            duplicates=[
                DuplicateOccurrenceOut(
                    num=other.num,
                    heading=other.heading,
                    status=other.status,
                    xml=other.xml,
                    content_hash=other.content_hash,
                    guid=other.guid,
                    seq_in_title=other.seq_in_title,
                    source_credit=other.source_credit,
                )
                for other in section.duplicates
            ],
            release=ReleaseOut.of(section.release),
            served_from=ReleaseOut.of(section.served_from),
            content_first_seen=ReleaseOut.of(section.content_first_seen),
            is_exact=section.is_exact,
            note=note,
        )


class TocOut(BaseModel):
    node: TocEntryOut
    ancestors: list[TocEntryOut]
    children: list[TocEntryOut]
    sections: list[TocEntryOut] = Field(
        description="Sections directly under this node, in reading order. Repealed "
        "and omitted sections keep their place and are badged by `status`."
    )
    release: ReleaseOut
    served_from: ReleaseOut
    note: str | None = None

    @classmethod
    def of(cls, toc: TocResult, note: str | None = None) -> "TocOut":
        return cls(
            node=TocEntryOut.of(toc.node),
            ancestors=[TocEntryOut.of(e) for e in toc.ancestors],
            children=[TocEntryOut.of(e) for e in toc.children],
            sections=[TocEntryOut.of(e) for e in toc.sections],
            release=ReleaseOut.of(toc.release),
            served_from=ReleaseOut.of(toc.served_from),
            note=note,
        )


class NeighborsOut(BaseModel):
    identifier: str
    previous: TocEntryOut | None
    next: TocEntryOut | None
    release: ReleaseOut
    served_from: ReleaseOut

    @classmethod
    def of(cls, neighbors: Neighbors) -> "NeighborsOut":
        return cls(
            identifier=neighbors.identifier,
            previous=(
                TocEntryOut.of(neighbors.previous) if neighbors.previous else None
            ),
            next=TocEntryOut.of(neighbors.next) if neighbors.next else None,
            release=ReleaseOut.of(neighbors.release),
            served_from=ReleaseOut.of(neighbors.served_from),
        )


class VersionOut(BaseModel):
    content_hash: str
    first_seen: ReleaseOut
    releases: list[str]
    num: str | None
    heading: str | None
    status: str | None

    @classmethod
    def of(cls, version: SectionVersionInfo) -> "VersionOut":
        return cls(
            content_hash=version.content_hash,
            first_seen=ReleaseOut.of(version.first_seen),
            releases=list(version.releases),
            num=version.num,
            heading=version.heading,
            status=version.status,
        )


class VersionsOut(BaseModel):
    identifier: str
    versions: list[VersionOut] = Field(
        description="One entry per distinct content, oldest first. Consecutive "
        "release points publishing identical text share an entry."
    )


class DiffOpOut(BaseModel):
    op: str = Field(description="equal | insert | delete")
    text: str

    @classmethod
    def of(cls, op: DiffOp) -> "DiffOpOut":
        return cls(op=op.op, text=op.text)


class DiffSectionOut(BaseModel):
    """One side of a diff: enough to label it, not the whole `SectionOut` —
    the fragment itself only exists as `ops`, never duplicated here."""

    release: ReleaseOut
    num: str | None
    heading: str | None
    status: str | None
    content_hash: str

    @classmethod
    def of(cls, section: SectionResult) -> "DiffSectionOut":
        return cls(
            release=ReleaseOut.of(section.release),
            num=section.num,
            heading=section.heading,
            status=section.status,
            content_hash=section.content_hash,
        )


class DiffOut(BaseModel):
    """A redline between two release points of one section (Day 4).

    Diffs the verbatim XML — a generic text diff, computed here because doing
    so needs no USLM vocabulary at all (docs/adr/0016); wrapping `ops` in
    `<ins>`/`<del>` for the reading column is `frontend/src/lib`'s job.
    """

    model_config = ConfigDict(populate_by_name=True)

    identifier: str
    from_: DiffSectionOut = Field(alias="from")
    to: DiffSectionOut
    ops: list[DiffOpOut]


class GuidOut(BaseModel):
    guid: str
    identifier: str
    release: ReleaseOut
    is_section: bool
    section_identifier: str | None
    url: str | None = Field(
        default=None, description="Where to open this provision in the reader."
    )

    @classmethod
    def of(cls, resolution: GuidResolution) -> "GuidOut":
        return cls(
            guid=resolution.guid,
            identifier=resolution.identifier,
            release=ReleaseOut.of(resolution.release),
            is_section=resolution.is_section,
            section_identifier=resolution.section_identifier,
            url=(
                f"{resolution.identifier}?release={resolution.release.label}"
                if resolution.identifier.startswith("/")
                else None
            ),
        )


class TitleOut(BaseModel):
    num: str
    name: str
    is_positive_law: bool
    ingested_releases: list[str]

    @classmethod
    def of(cls, title: TitleInfo) -> "TitleOut":
        return cls(
            num=title.num,
            name=title.name,
            is_positive_law=title.is_positive_law,
            ingested_releases=list(title.ingested_releases),
        )


class SourceCheckOut(BaseModel):
    """When this mirror last asked uscode.house.gov what exists."""

    url: str = Field(
        examples=["https://uscode.house.gov/download/priorreleasepoints.htm"],
        description="The page that is polled — one request per check.",
    )
    last_checked_at: datetime.datetime | None = Field(
        default=None, description="null means no check has ever been recorded here."
    )
    hours_since_check: float | None = None
    ok: bool = Field(description="Did the last check reach and parse the page?")
    stale: bool = Field(
        description="True when the last check failed, is over a week old, or has "
        "never happened. A stale check does not mean the text is wrong — it means "
        "nobody has confirmed lately that it is still the newest published."
    )
    release_points_seen: int | None = Field(
        default=None, description="How many release points the page listed."
    )
    new_release_points: list[str] = Field(
        default_factory=list,
        description="Release points that check found and this database had not "
        "seen before. Non-empty means an ingest is pending, not that it failed.",
    )
    latest_published_label: str | None = Field(
        default=None, description="The newest release point OLRC published, as of that check."
    )
    latest_published_date: datetime.date | None = None
    error: str | None = Field(
        default=None, description="Why the last check failed, if it did."
    )

    @classmethod
    def of(cls, check: SourceCheckInfo | None, *, url: str) -> "SourceCheckOut":
        if check is None:
            # Never checked. Reported as stale rather than as an error: a corpus
            # restored from a dump onto a box whose schedule has not yet fired is
            # exactly this, and it is honest to say "unconfirmed" out loud.
            return cls(url=url, ok=False, stale=True)
        return cls(
            url=check.source_url,
            last_checked_at=check.checked_at,
            hours_since_check=round(check.age().total_seconds() / 3600, 2),
            ok=check.ok,
            stale=check.is_stale(),
            release_points_seen=check.release_points_seen,
            new_release_points=list(check.new_labels),
            latest_published_label=check.latest_label,
            latest_published_date=check.latest_currency_date,
            error=check.error,
        )


class CorpusStatusOut(BaseModel):
    """What this database actually holds, against what the source publishes."""

    latest_release: str | None = Field(
        default=None, description="Newest release point with content loaded."
    )
    latest_currency_date: datetime.date | None = None
    release_points_known: int = Field(
        description="Rows in the release-point inventory — including ones not yet ingested."
    )
    behind_by: int | None = Field(
        default=None,
        description="Release points published since the newest one loaded here. "
        "null when the last check never succeeded, because then there is nothing "
        "trustworthy to compare against — which is not the same as zero.",
    )


class StatusOut(BaseModel):
    """`GET /api/v1/status` — how current this mirror is, and how it knows.

    Two independent facts, deliberately not collapsed into one "up to date"
    flag: what we hold, and when we last confirmed that is everything there is.
    A mirror can be current and unverified, or verified and behind, and the two
    call for different responses.
    """

    source: SourceCheckOut
    corpus: CorpusStatusOut


class CitationOut(BaseModel):
    """What a typed citation resolved to — the parse, plus whether it is there.

    `identifier` is the deepest thing the citation named; `section_identifier` is
    the section containing it, and the one `exists` is about — a provision path
    is extracted from the section's XML at request time (ADR-0001), so
    `/us/usc/t11/s523/a/1` is never a row and could not be looked up directly.

    `exists` is `False`, not a 404: "Title 99 has no section 1" is an *answer*,
    and the reader that asked deserves to be told which part was wrong rather
    than handed an error page.
    """

    query: str
    identifier: str
    section_identifier: str
    title_num: str
    section_num: str | None = None
    subdivisions: list[str] = Field(default_factory=list)
    kind: str
    note: bool = False
    et_seq: bool = False
    exists: bool = False
    #: Present when the target exists — what to show for it.
    heading: str | None = None
    num: str | None = None
    release: ReleaseOut | None = None
    #: Why a well-formed citation resolved to nothing, when there is something
    #: specific to say. `None` when the answer needs no explaining.
    message: str | None = None

    @classmethod
    def of(
        cls,
        parsed: ParsedCitation,
        query: str,
        *,
        entry: TocEntry | None = None,
        actual: str | None = None,
        release: ReleaseRef | None = None,
        message: str | None = None,
    ) -> "CitationOut":
        # `actual` is the spelling that was found, which need not be the one
        # typed: OLRC writes section numbers with an EN DASH, so `2000e-2`
        # resolves to `/us/usc/t42/s2000e–2`. The reader must be sent to the
        # identifier that exists, not the one they typed, or the redirect 404s.
        section = actual or parsed.section_identifier
        identifier = section + "".join(f"/{part}" for part in parsed.subdivisions)

        return cls(
            message=message,
            query=query,
            identifier=identifier,
            section_identifier=section,
            title_num=parsed.title_num,
            section_num=parsed.section_num,
            subdivisions=list(parsed.subdivisions),
            kind=parsed.kind,
            note=parsed.note,
            et_seq=parsed.et_seq,
            exists=entry is not None,
            heading=entry.heading if entry else None,
            num=entry.num if entry else None,
            release=ReleaseOut.of(release) if release else None,
        )


class ErrorOut(BaseModel):
    detail: str
    candidates: list[str] | None = None


class WatchlistItemOut(BaseModel):
    """One watched provision, enriched with what it currently says (Day 5) — a
    badge that went `repealed`/`transferred` since it was added is just this
    item's current `status`, fetched the same way a page's citations are
    (`Repository.labels`, batched)."""

    id: int
    identifier: str
    title_num: str
    note: str | None
    pinned_release_label: str | None = Field(
        description="An exact release label the user pinned, or null to always "
        "open at the newest release this title is ingested at."
    )
    created_at: datetime.datetime
    num: str | None = Field(default=None, description="Absent when enrichment failed.")
    heading: str | None = None
    status: str | None = None

    @classmethod
    def of(cls, item: WatchlistItemRef, entry: TocEntry | None = None) -> "WatchlistItemOut":
        return cls(
            id=item.id,
            identifier=item.identifier,
            title_num=item.title_num,
            note=item.note,
            pinned_release_label=item.pinned_release_label,
            created_at=item.created_at,
            num=entry.num if entry else None,
            heading=entry.heading if entry else None,
            status=entry.status if entry else None,
        )


class WatchlistSummaryOut(BaseModel):
    id: int
    name: str
    item_count: int

    @classmethod
    def of(cls, watchlist: WatchlistRef) -> "WatchlistSummaryOut":
        return cls(id=watchlist.id, name=watchlist.name, item_count=watchlist.item_count)


class WatchlistOut(BaseModel):
    id: int
    name: str
    items: list[WatchlistItemOut]

    @classmethod
    def of(cls, watchlist: WatchlistRef, items: list[WatchlistItemOut]) -> "WatchlistOut":
        return cls(id=watchlist.id, name=watchlist.name, items=items)


class WatchlistCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WatchlistItemCreateIn(BaseModel):
    identifier: str = Field(description="A US Code identifier, e.g. /us/usc/t16/s45f")
    pinned_release: str | None = Field(
        default=None, description="An exact release label to pin, e.g. 119-99."
    )
    note: str | None = Field(default=None, max_length=4000)


class WatchlistItemUpdateIn(BaseModel):
    pinned_release: str | None = None
    note: str | None = Field(default=None, max_length=4000)
