"""Response models — the public JSON contract, and the OpenAPI docs.

These are a deliberate translation of `storage`'s dataclasses rather than a reuse
of them: the wire format is a promise to clients and should not move just because
an internal field was renamed. Nothing here imports from `db`.
"""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.diff import DiffOp
from citeparse import ParsedCitation
from storage import (
    ClassificationCheckInfo,
    ClassificationEntryRef,
    ClassificationFileInfo,
    ClassificationPage,
    EcctEntryRef,
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
    guids: Literal["strip", "keep"] = Field(
        default="strip",
        description=(
            "Whether `@id` guids took part in this diff. They regenerate at "
            "every release point by design (ADR-0003), so `strip` compares what "
            "the section says and `keep` compares the bytes as stored. Reported "
            "rather than assumed: the two answers differ and a caller should "
            "never have to guess which one it got."
        ),
    )
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


# ------------------------------------------------- classification tables (ADR-0067)


class ClassificationFileOut(BaseModel):
    """One source document in the registry — a Public Law order table, or an ECCT."""

    kind: str = Field(
        description="`pl` (Public Law order table) or `ecct` (Editorial "
        "Classification Change Table). A string and not an enum: the source has "
        "already added one document type to this family.",
        examples=["pl"],
    )
    congress: int = Field(examples=[119])
    session: int = Field(
        description="1 or 2, and **0 for the 104th's single whole-congress file**. "
        "The database never holds a NULL here.",
        examples=[2],
    )
    session_label: str = Field(
        description="`1`, `2` or `all` — the same value spelled the way the "
        "reader's URLs do. `all` is session 0.",
        examples=["2"],
    )
    source_url: str
    source_filename: str = Field(examples=["tbl119pl_2nd.htm"])
    covered_laws_text: str | None = Field(
        default=None,
        description="The page header's public-law range, verbatim. Null for an ECCT.",
        examples=["Public Law 119-70 and Public Laws 119-74 through 119-102"],
    )
    covered_ranges: list[str] = Field(
        default_factory=list,
        description="That header parsed into gap-aware segments. A law inside one "
        "of these has a table covering it, whether or not it classified anything.",
        examples=[["70-70", "74-102"]],
    )
    first_law: int | None = None
    last_law: int | None = None
    prepared_date: datetime.date | None = None
    stat_volume: int | None = Field(
        default=None,
        description="The Statutes at Large volume named in the column header. Null "
        "for the 104th, whose congress spans two volumes.",
        examples=[140],
    )
    fetched_at: datetime.datetime
    row_count: int
    skipped_lines: int

    @classmethod
    def of(cls, info: ClassificationFileInfo) -> "ClassificationFileOut":
        return cls(
            kind=info.kind,
            congress=info.congress,
            session=info.session,
            session_label=info.session_label,
            source_url=info.source_url,
            source_filename=info.source_filename,
            covered_laws_text=info.covered_laws_text,
            covered_ranges=list(info.covered_ranges),
            first_law=info.first_law,
            last_law=info.last_law,
            prepared_date=info.prepared_date,
            stat_volume=info.stat_volume,
            fetched_at=info.fetched_at,
            row_count=info.row_count,
            skipped_lines=info.skipped_lines,
        )


class ClassificationCheckOut(BaseModel):
    """When this mirror last asked OLRC what classification tables exist.

    Its own check, and not the one `/api/v1/status` reports: that reads the
    release-point poll, and interleaving the two would make the corpus-freshness
    answer flap between two unrelated sources (ADR-0067).
    """

    url: str = Field(examples=["https://uscode.house.gov/classification/tables.shtml"])
    last_checked_at: datetime.datetime | None = Field(
        default=None, description="null means no check has ever been recorded here."
    )
    hours_since_check: float | None = None
    ok: bool = Field(description="Did the last check reach and parse the page?")
    stale: bool = Field(
        description="True when the last check failed, is over a week old, or has "
        "never happened."
    )
    files_seen: int | None = Field(
        default=None, description="How many documents the entry pages listed."
    )
    changed_files: list[str] = Field(
        default_factory=list,
        description="Source filenames whose covered-law text differed from the "
        "registry at that check. Non-empty means a load is pending.",
    )
    latest_covered_text: str | None = None
    error: str | None = None

    @classmethod
    def of(
        cls, check: ClassificationCheckInfo | None, *, url: str
    ) -> "ClassificationCheckOut":
        if check is None:
            return cls(url=url, ok=False, stale=True)
        return cls(
            url=check.source_url,
            last_checked_at=check.checked_at,
            hours_since_check=round(check.age().total_seconds() / 3600, 2),
            ok=check.ok,
            stale=check.is_stale(),
            files_seen=check.files_seen,
            changed_files=list(check.changed_files),
            latest_covered_text=check.latest_covered_text,
            error=check.error,
        )


class ClassificationTablesOut(BaseModel):
    """The registry of source documents, and how fresh it is."""

    source: ClassificationCheckOut
    files: list[ClassificationFileOut] = Field(
        description="Every document held, newest congress and session first — "
        "both kinds, told apart by `kind`."
    )
    current: ClassificationFileOut | None = Field(
        default=None,
        description="The newest Public Law order table, which is the session "
        "OLRC is still adding to. Null when none is loaded.",
    )
    entry_total: int = Field(
        description="Rows across every Public Law order table held."
    )


class ClassificationEntryOut(BaseModel):
    """One row of a Classification Table: a public-law provision and where it
    landed in the Code."""

    congress: int = Field(
        description="The congress of the *document* this row came from, which is "
        "the session page it appears on. Not necessarily `pl_congress`.",
        examples=[118],
    )
    session: int = Field(examples=[2])
    session_label: str = Field(examples=["2"])
    row_seq: int = Field(description="0-based order within the document.")
    raw_line: str = Field(
        description="The source line, tag-stripped and verbatim. The fallback for "
        "the 129 rows whose columns could not all be read."
    )
    title_raw: str = Field(examples=["18"])
    title_num: str = Field(
        description="A string — `5a` is a title and `5` is a different one. Never "
        "sorted as text.",
        examples=["18"],
    )
    is_appendix: bool
    section_raw: str = Field(examples=["3551"])
    section_norm: str = Field(
        description="Lowercased, with dashes folded to a plain hyphen. The "
        "spelling typed input is matched against.",
        examples=["254c-15"],
    )
    description_raw: str = Field(
        description="The Description cell verbatim. `''` means the section was "
        "amended; the vocabulary otherwise is an open set (`nt`, `new`, `nt new`, "
        "`prec`, `tr fr T/S`, `tr to T/S`, `omitted`, `repealed`, `gen amd`, "
        "`ed chg`, …).",
        examples=["nt"],
    )
    is_note: bool
    action: str | None = None
    transfer_counterpart: str | None = Field(
        default=None, description="The other end of a transfer.", examples=["42/290ee-10"]
    )
    act_name: str | None = Field(
        default=None, description="Named on appendix rows, whose Code citation is an act."
    )
    usc_identifier: str | None = Field(
        default=None,
        description="The USLM `@identifier` this row's citation derives to, "
        "**spelled with an EN DASH** as the corpus spells it. Null for 1,533 of "
        "the loaded rows — 1,531 of them appendix rows, which derive none by rule "
        "— and those rows are rendered without a link rather than dropped.",
        examples=["/us/usc/t18/s3551"],
    )
    pl_congress: int | None = None
    pl_num: int | None = None
    pl_label: str | None = Field(
        default=None,
        description="`pl_congress-pl_num`, or null for the 2 rows whose Pub. L. "
        "cell could not be read. Those rows are kept.",
        examples=["118-35"],
    )
    pl_section_raw: str = Field(
        description="`''` means the row is about the whole law.", examples=["101(3)"]
    )
    new_section_quote: str | None = Field(
        default=None,
        description="The section being added to the underlying act, when the Sec. "
        "cell named one in quotes.",
        examples=["1948"],
    )
    stat_volume: int | None = Field(default=None, examples=[138])
    stat_pages: list[int] = Field(
        default_factory=list,
        description="Pages that have an integer form. **Empty for 6,053 rows that "
        "do cite a page**, because a page of the Statutes at Large is not always a "
        "number. A statviewer link is buildable only from a volume and one of these.",
    )
    stat_page_labels: list[str] = Field(
        default_factory=list,
        description="The Stat. cell's tokens verbatim — the column to display. "
        "`3009-587` and `1501A-594` are single pages, and a range is one token "
        "here where it is two integers in `stat_pages`.",
        examples=[["3009-587"]],
    )

    @classmethod
    def of(cls, entry: ClassificationEntryRef) -> "ClassificationEntryOut":
        return cls(
            congress=entry.congress,
            session=entry.session,
            session_label=entry.session_label,
            row_seq=entry.row_seq,
            raw_line=entry.raw_line,
            title_raw=entry.title_raw,
            title_num=entry.title_num,
            is_appendix=entry.is_appendix,
            section_raw=entry.section_raw,
            section_norm=entry.section_norm,
            description_raw=entry.description_raw,
            is_note=entry.is_note,
            action=entry.action,
            transfer_counterpart=entry.transfer_counterpart,
            act_name=entry.act_name,
            usc_identifier=entry.usc_identifier,
            pl_congress=entry.pl_congress,
            pl_num=entry.pl_num,
            pl_label=entry.pl_label,
            pl_section_raw=entry.pl_section_raw,
            new_section_quote=entry.new_section_quote,
            stat_volume=entry.stat_volume,
            stat_pages=list(entry.stat_pages),
            stat_page_labels=list(entry.stat_page_labels),
        )


class ClassificationPageOut(BaseModel):
    """One page of classification rows, and the size of the set it came from."""

    items: list[ClassificationEntryOut]
    total: int = Field(
        description="Rows the filters matched, not rows returned — what a pager needs."
    )
    limit: int
    offset: int
    sort: str | None = Field(
        default=None,
        description="The ordering in force: `pl` (the source's own order) or "
        "`code` (title through the Code's ordering, then section). Present on the "
        "session-page route alone.",
    )
    file: ClassificationFileOut | None = Field(
        default=None,
        description="The document these rows came from. Present when one document "
        "answered the request — the session page, and the table covering a public "
        "law — and null when the rows span documents.",
    )

    @classmethod
    def of(
        cls,
        page: ClassificationPage,
        *,
        sort: str | None = None,
        file: ClassificationFileInfo | None = None,
    ) -> "ClassificationPageOut":
        return cls(
            items=[ClassificationEntryOut.of(entry) for entry in page.items],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            sort=sort,
            file=ClassificationFileOut.of(file) if file else None,
        )


class EcctEntryOut(BaseModel):
    """One row of the Editorial Classification Change Table: a provision OLRC
    moved without Congress amending it."""

    congress: int
    session: int
    session_label: str
    row_seq: int
    former_raw: str = Field(examples=["42:294t nt"])
    former_title_num: str | None = None
    former_section_norm: str | None = None
    former_is_note: bool = False
    new_raw: str = Field(examples=["42:294u new"])
    new_title_num: str | None = None
    new_section_norm: str | None = None
    new_is_note: bool = False
    provision_affected: str = Field(
        description="The full public-law citation string, verbatim."
    )
    provision_prompting: str
    affected_pl_congress: int | None = None
    affected_pl_num: int | None = None
    prompting_pl_congress: int | None = None
    prompting_pl_num: int | None = None

    @classmethod
    def of(cls, entry: EcctEntryRef) -> "EcctEntryOut":
        return cls(
            congress=entry.congress,
            session=entry.session,
            session_label=entry.session_label,
            row_seq=entry.row_seq,
            former_raw=entry.former_raw,
            former_title_num=entry.former_title_num,
            former_section_norm=entry.former_section_norm,
            former_is_note=entry.former_is_note,
            new_raw=entry.new_raw,
            new_title_num=entry.new_title_num,
            new_section_norm=entry.new_section_norm,
            new_is_note=entry.new_is_note,
            provision_affected=entry.provision_affected,
            provision_prompting=entry.provision_prompting,
            affected_pl_congress=entry.affected_pl_congress,
            affected_pl_num=entry.affected_pl_num,
            prompting_pl_congress=entry.prompting_pl_congress,
            prompting_pl_num=entry.prompting_pl_num,
        )


class EcctOut(BaseModel):
    """The Editorial Classification Change Table, whole."""

    items: list[EcctEntryOut] = Field(
        description="Newest session first, then source order within a document."
    )
    total: int = Field(
        description="Equal to the length of `items`. This table is not paged — it "
        "is 21 rows across two documents."
    )


class ClassificationSuggestionOut(BaseModel):
    """One thing the lookup box can offer for what was typed.

    `href` is a path **relative to the reader's base** (`/app`), always starting
    with `/`: `/classification/119/2?pl=119-70`, `/us/usc/t16/s45f#section-notes`,
    `/classification?title=16&section=45f`. The structured fields beside it carry
    the same answer in pieces, so a caller that builds its own URLs through
    `lib/url.ts` (architecture rule 5) never has to parse this string.
    """

    kind: str = Field(
        description="`pl` — a public law's rows on its session page. "
        "`section-notes` — the section's notes in the reader, where OLRC's own "
        "classification history is printed. `section-classifications` — the "
        "classification rows for that section.",
        examples=["pl"],
    )
    label: str = Field(examples=["Public Law 119-70"])
    detail: str | None = Field(
        default=None,
        description="A second line for the row: what the suggestion leads to.",
        examples=["119th Congress, 2nd session table"],
    )
    href: str
    congress: int | None = None
    session: int | None = Field(
        default=None, description="0 is the 104th's whole-congress file."
    )
    session_label: str | None = Field(
        default=None, description="`1`, `2` or `all` — how `href` spells `session`."
    )
    pl: str | None = Field(default=None, examples=["119-70"])
    pl_section: str | None = Field(
        default=None, description="A provision of that law, when one was typed."
    )
    title_num: str | None = None
    section: str | None = Field(
        default=None, description="The `section_norm` spelling — a plain hyphen."
    )
    identifier: str | None = Field(
        default=None,
        description="The USLM `@identifier`, as the corpus spells it (EN DASH). "
        "Percent-encode it before putting it in a URL.",
        examples=["/us/usc/t16/s45f"],
    )
    fragment: str | None = Field(
        default=None, description="The anchor `href` ends at.", examples=["#section-notes"]
    )
    count: int | None = Field(
        default=None, description="How many rows are behind this suggestion, when known."
    )


class ClassificationSuggestOut(BaseModel):
    """What the lookup box can offer for what was typed."""

    query: str = Field(description="The string that was looked up, as given.")
    suggestions: list[ClassificationSuggestionOut] = Field(
        description="Empty when the string is neither a public law this mirror "
        "covers nor a citation anything is known about, which is an answer rather "
        "than an error."
    )


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
