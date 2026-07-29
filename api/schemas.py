"""Response models — the public JSON contract, and the OpenAPI docs.

These are a deliberate translation of `storage`'s dataclasses rather than a reuse
of them: the wire format is a promise to clients and should not move just because
an internal field was renamed. Nothing here imports from `db`.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field

from api.diff import DiffOp
from storage import (
    GuidResolution,
    Neighbors,
    ReleaseRef,
    SectionResult,
    SectionVersionInfo,
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
    xml: str
    provision: ProvisionOut | None = None
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
            release=ReleaseOut.of(section.release),
            served_from=ReleaseOut.of(section.served_from),
            content_first_seen=ReleaseOut.of(section.content_first_seen),
            is_exact=section.is_exact,
            note=note,
        )


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
