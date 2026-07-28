"""The Postgres `Repository` implementation — where all the SQL lives.

Everything version-resolution-related is in this file and nothing outside it
(CLAUDE.md architecture rule 1), so the XCiteDB implementation that replaces it
has one file's worth of behaviour to match and a suite of contract tests to match
it against.

Resolution follows PLAN §3 exactly:

  1. `?date=` → newest release point with `currency_date <= date`; `?release=` →
     label match, with a bare `119-102` matching `119-102not101` and saying so.
  2. Longest-prefix match strips a provision path down to its section.
  3. `section_release_map` → the section version that release point publishes.
  4. XPath the fragment out of the stored XML by `@identifier`.
"""

from __future__ import annotations

import datetime
import re

from lxml import etree
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models import (
    GuidMap,
    ReleasePoint,
    Section,
    SectionReleaseMap,
    SectionVersion,
    StructureNode,
    Title,
    TitleVersion,
)
from storage.repository import (
    AmbiguousReleaseError,
    GuidResolution,
    Neighbors,
    Provision,
    ReleaseNotFoundError,
    ReleaseRef,
    ResolvedRelease,
    SectionResult,
    SectionVersionInfo,
    TitleInfo,
    TocEntry,
    TocResult,
)

_TITLE_IN_IDENTIFIER = re.compile(r"^/us/usc/t(?P<num>[0-9]+[a-zA-Z]?)(?:/|$)")
_MIN_IDENTIFIER_PARTS = 4  # us, usc, tNN, sXX — anything shorter is not a section


def title_num_from_identifier(identifier: str) -> str | None:
    """`/us/usc/t16/s45f/c/5` → `16`. None when the path isn't a US Code path."""
    match = _TITLE_IN_IDENTIFIER.match(identifier)
    return match.group("num") if match else None


class PostgresRepository:
    """`Repository` over the Day-1 Postgres schema."""

    def __init__(self, session: Session):
        self._session = session

    # ------------------------------------------------------------------ releases

    def resolve_release(
        self,
        *,
        label: str | None = None,
        on_date: datetime.date | None = None,
        title_num: str | None = None,
    ) -> ResolvedRelease:
        if label:
            return self._resolve_label(label)
        if on_date:
            return self._resolve_date(on_date)
        return ResolvedRelease(release=self._latest_release(title_num))

    def _resolve_label(self, label: str) -> ResolvedRelease:
        exact = self._session.scalars(
            select(ReleasePoint).where(ReleasePoint.label == label)
        ).first()
        if exact is not None:
            return ResolvedRelease(release=self._ref(exact), requested_label=label)

        # A bare `119-102` is not a published release point; `119-102not101` is.
        # Prefix-match so citations written the obvious way still resolve, and hand
        # back a note rather than pretending the labels were the same thing.
        candidates = list(
            self._session.scalars(
                select(ReleasePoint)
                .where(ReleasePoint.label.startswith(f"{label}not"))
                .order_by(ReleasePoint.seq)
            )
        )
        if not candidates:
            raise ReleaseNotFoundError(f"no release point labelled {label!r}")
        if len(candidates) > 1:
            raise AmbiguousReleaseError(label, [c.label for c in candidates])
        release = candidates[0]
        return ResolvedRelease(
            release=self._ref(release),
            requested_label=label,
            note=(
                f"{label} was published as {release.label} — Public Law "
                f"{release.congress}-{release.law_num} except "
                + ", ".join(f"{release.congress}-{n}" for n in release.excluded_laws)
                + "."
            ),
        )

    def _resolve_date(self, on_date: datetime.date) -> ResolvedRelease:
        release = self._session.scalars(
            select(ReleasePoint)
            .where(ReleasePoint.currency_date <= on_date)
            .order_by(ReleasePoint.seq.desc())
            .limit(1)
        ).first()
        if release is None:
            earliest = self._session.scalars(
                select(ReleasePoint).order_by(ReleasePoint.seq).limit(1)
            ).first()
            raise ReleaseNotFoundError(
                f"no release point on or before {on_date.isoformat()}"
                + (f"; the earliest is {earliest.currency_date}" if earliest else "")
            )
        note = None
        if release.currency_date != on_date:
            note = (
                f"{on_date.isoformat()} falls between release points; showing "
                f"{release.label}, current through {release.currency_date.isoformat()}."
            )
        return ResolvedRelease(
            release=self._ref(release), requested_date=on_date, note=note
        )

    def _latest_release(self, title_num: str | None = None) -> ReleaseRef:
        statement: Select = select(ReleasePoint).order_by(ReleasePoint.seq.desc()).limit(1)
        if title_num is not None:
            title = self._title(title_num)
            if title is not None:
                statement = (
                    select(ReleasePoint)
                    .join(TitleVersion, TitleVersion.release_id == ReleasePoint.id)
                    .where(TitleVersion.title_id == title.id)
                    .order_by(ReleasePoint.seq.desc())
                    .limit(1)
                )
        release = self._session.scalars(statement).first()
        if release is None:
            raise ReleaseNotFoundError("no release points are loaded")
        return self._ref(release)

    def list_releases(self, *, title_num: str | None = None) -> list[ReleaseRef]:
        ingested: dict[int, list[str]] = {}
        for release_id, num in self._session.execute(
            select(TitleVersion.release_id, Title.num).join(
                Title, Title.id == TitleVersion.title_id
            )
        ).all():
            ingested.setdefault(release_id, []).append(num)

        statement = select(ReleasePoint).order_by(ReleasePoint.seq.desc())
        if title_num is not None:
            statement = statement.where(
                ReleasePoint.titles_affected.any(_padded(title_num))
            )
        return [
            self._ref(release, ingested.get(release.id, []))
            for release in self._session.scalars(statement)
        ]

    def list_titles(self) -> list[TitleInfo]:
        releases: dict[int, list[tuple[int, str]]] = {}
        for title_id, seq, label in self._session.execute(
            select(TitleVersion.title_id, ReleasePoint.seq, ReleasePoint.label).join(
                ReleasePoint, ReleasePoint.id == TitleVersion.release_id
            )
        ).all():
            releases.setdefault(title_id, []).append((seq, label))
        return [
            TitleInfo(
                num=title.num,
                name=title.name,
                is_positive_law=title.is_positive_law,
                ingested_releases=tuple(
                    label for _seq, label in sorted(releases.get(title.id, []))
                ),
            )
            for title in self._session.scalars(select(Title).order_by(Title.num))
        ]

    # ------------------------------------------------------------------ sections

    def get_section(
        self, identifier: str, release: ResolvedRelease
    ) -> SectionResult | None:
        match = self._longest_prefix_section(identifier)
        if match is None:
            return None
        section, remainder = match

        served_from = self._served_from(section.title_id, release.release)
        if served_from is None:
            return None
        row = self._session.execute(
            select(SectionVersion, SectionReleaseMap)
            .join(
                SectionReleaseMap,
                SectionReleaseMap.section_version_id == SectionVersion.id,
            )
            .where(
                SectionVersion.section_id == section.id,
                SectionReleaseMap.release_id == served_from.id,
            )
        ).first()
        if row is None:
            return None
        version, placement = row

        title = self._session.get(Title, section.title_id)
        first_seen = self._session.get(ReleasePoint, version.first_release_id)
        assert title is not None and first_seen is not None

        return SectionResult(
            identifier=section.identifier,
            title_num=title.num,
            num=version.num,
            heading=version.heading,
            status=version.status,
            xml=version.xml,
            content_hash=version.content_hash.hex(),
            source_credit=version.source_credit,
            seq_in_title=placement.seq_in_title,
            parent_identifier=placement.parent_identifier,
            guid=self._guid_for(section.identifier, served_from.id),
            release=release.release,
            served_from=self._ref(served_from),
            content_first_seen=self._ref(first_seen),
            provision=(
                self._extract_provision(version.xml, identifier) if remainder else None
            ),
        )

    def _longest_prefix_section(self, identifier: str) -> tuple[Section, str] | None:
        """PLAN §3 step 2, in one query: try every prefix, keep the longest hit."""
        parts = identifier.strip("/").split("/")
        prefixes = [
            "/" + "/".join(parts[:length])
            for length in range(len(parts), _MIN_IDENTIFIER_PARTS - 1, -1)
        ]
        if not prefixes:
            return None
        found = {
            section.identifier: section
            for section in self._session.scalars(
                select(Section).where(Section.identifier.in_(prefixes))
            )
        }
        for prefix in prefixes:  # longest first
            section = found.get(prefix)
            if section is not None:
                return section, identifier[len(prefix) :]
        return None

    @staticmethod
    def _extract_provision(section_xml: str, identifier: str) -> Provision:
        """PLAN §3 step 4: XPath the provision out of its section by `@identifier`.

        Sub-section provisions are not stored separately (ADR-0001) — they are cut
        from the section on request, and the section always comes back with them so
        the reader keeps context.
        """
        root = etree.fromstring(section_xml.encode("utf-8"))
        matches = root.xpath("//*[@identifier=$wanted]", wanted=identifier)
        if not matches:
            return Provision(identifier=identifier, found=False)
        return Provision(
            identifier=identifier,
            found=True,
            xml=etree.tostring(matches[0], encoding="unicode", with_tail=False),
        )

    def resolve_id(self, guid: str) -> GuidResolution | None:
        entry = self._session.get(GuidMap, guid)
        if entry is None:
            return None
        release = self._session.get(ReleasePoint, entry.release_id)
        assert release is not None

        node = self._session.scalars(
            select(StructureNode).where(StructureNode.identifier == entry.identifier)
        ).first()
        section = None
        if node is None:
            match = self._longest_prefix_section(entry.identifier)
            section = match[0] if match else None

        return GuidResolution(
            guid=guid,
            identifier=entry.identifier,
            release=self._ref(release),
            is_section=section is not None and section.identifier == entry.identifier,
            section_identifier=section.identifier if section is not None else None,
        )

    # ---------------------------------------------------------------------- toc

    def get_toc(self, identifier: str, release: ResolvedRelease) -> TocResult | None:
        node = self._session.scalars(
            select(StructureNode).where(StructureNode.identifier == identifier)
        ).first()
        if node is None:
            return None
        served_from = self._served_from(node.title_id, release.release)
        if served_from is None:
            return None

        children = [
            _node_entry(child)
            for child in self._session.scalars(
                select(StructureNode)
                .join(ReleasePoint, ReleasePoint.id == StructureNode.first_release_id)
                .where(
                    StructureNode.parent_id == node.id,
                    # A chapter added later must not appear in an earlier TOC. The
                    # converse — a node gone from a later release point — is not
                    # inferred: see ADR-0006.
                    ReleasePoint.seq <= served_from.seq,
                )
                .order_by(StructureNode.seq)
            )
        ]
        sections = [
            TocEntry(
                identifier=section_identifier,
                level="section",
                num=num,
                heading=heading,
                status=status,
                is_section=True,
            )
            for section_identifier, num, heading, status in self._session.execute(
                select(
                    Section.identifier,
                    SectionVersion.num,
                    SectionVersion.heading,
                    SectionVersion.status,
                )
                .join(SectionVersion, SectionVersion.section_id == Section.id)
                .join(
                    SectionReleaseMap,
                    SectionReleaseMap.section_version_id == SectionVersion.id,
                )
                .where(
                    SectionReleaseMap.release_id == served_from.id,
                    SectionReleaseMap.parent_identifier == identifier,
                )
                .order_by(SectionReleaseMap.seq_in_title)
            ).all()
        ]

        return TocResult(
            node=_node_entry(node),
            ancestors=tuple(self._ancestors(node)),
            children=tuple(children),
            sections=tuple(sections),
            release=release.release,
            served_from=self._ref(served_from),
        )

    def _ancestors(self, node: StructureNode) -> list[TocEntry]:
        chain: list[TocEntry] = []
        current = node
        while current.parent_id is not None:
            parent = self._session.get(StructureNode, current.parent_id)
            if parent is None:  # pragma: no cover - parent_id is a foreign key
                break
            chain.append(_node_entry(parent))
            current = parent
        chain.reverse()
        return chain

    # ---------------------------------------------------------------- neighbours

    def neighbors(self, identifier: str, release: ResolvedRelease) -> Neighbors | None:
        match = self._longest_prefix_section(identifier)
        if match is None:
            return None
        section, _remainder = match
        served_from = self._served_from(section.title_id, release.release)
        if served_from is None:
            return None

        current = self._session.execute(
            select(SectionReleaseMap.seq_in_title)
            .join(
                SectionVersion,
                SectionVersion.id == SectionReleaseMap.section_version_id,
            )
            .where(
                SectionVersion.section_id == section.id,
                SectionReleaseMap.release_id == served_from.id,
            )
        ).scalar_one_or_none()
        if current is None:
            return None

        return Neighbors(
            identifier=section.identifier,
            previous=self._neighbor(section.title_id, served_from.id, current, before=True),
            next=self._neighbor(section.title_id, served_from.id, current, before=False),
            release=release.release,
            served_from=self._ref(served_from),
        )

    def _neighbor(
        self, title_id: int, release_id: int, seq: int, *, before: bool
    ) -> TocEntry | None:
        """The adjacent section in reading order — repealed and omitted included.

        Gotcha 9: they keep their place in the Code and in the reader, badged.
        """
        condition = (
            SectionReleaseMap.seq_in_title < seq
            if before
            else SectionReleaseMap.seq_in_title > seq
        )
        order = (
            SectionReleaseMap.seq_in_title.desc()
            if before
            else SectionReleaseMap.seq_in_title.asc()
        )
        row = self._session.execute(
            select(
                Section.identifier,
                SectionVersion.num,
                SectionVersion.heading,
                SectionVersion.status,
            )
            .join(SectionVersion, SectionVersion.section_id == Section.id)
            .join(
                SectionReleaseMap,
                SectionReleaseMap.section_version_id == SectionVersion.id,
            )
            .where(
                Section.title_id == title_id,
                SectionReleaseMap.release_id == release_id,
                condition,
            )
            .order_by(order)
            .limit(1)
        ).first()
        if row is None:
            return None
        identifier, num, heading, status = row
        return TocEntry(
            identifier=identifier,
            level="section",
            num=num,
            heading=heading,
            status=status,
            is_section=True,
        )

    # ------------------------------------------------------------------ versions

    def versions(self, identifier: str) -> list[SectionVersionInfo]:
        match = self._longest_prefix_section(identifier)
        if match is None:
            return []
        section, _remainder = match

        published: dict[int, list[tuple[int, str]]] = {}
        for version_id, seq, label in self._session.execute(
            select(SectionReleaseMap.section_version_id, ReleasePoint.seq, ReleasePoint.label)
            .join(ReleasePoint, ReleasePoint.id == SectionReleaseMap.release_id)
            .join(
                SectionVersion,
                SectionVersion.id == SectionReleaseMap.section_version_id,
            )
            .where(SectionVersion.section_id == section.id)
        ).all():
            published.setdefault(version_id, []).append((seq, label))

        rows = self._session.execute(
            select(SectionVersion, ReleasePoint)
            .join(ReleasePoint, ReleasePoint.id == SectionVersion.first_release_id)
            .where(SectionVersion.section_id == section.id)
            .order_by(ReleasePoint.seq)
        ).all()
        return [
            SectionVersionInfo(
                content_hash=version.content_hash.hex(),
                first_seen=self._ref(first_release),
                releases=tuple(
                    label for _seq, label in sorted(published.get(version.id, []))
                ),
                num=version.num,
                heading=version.heading,
                status=version.status,
            )
            for version, first_release in rows
        ]

    # ----------------------------------------------------------------- internals

    def _title(self, num: str) -> Title | None:
        return self._session.scalars(select(Title).where(Title.num == num)).first()

    def _served_from(self, title_id: int, release: ReleaseRef) -> ReleasePoint | None:
        """The newest ingested release point at or before `release` for this title.

        This is the whole reason a request for a release point we never ingested
        still answers: release points republish every title but change few, so the
        last ingested one before it holds the same text (gotcha 10). What must not
        happen is answering *silently* — callers compare `served_from` to `release`.
        """
        return self._session.scalars(
            select(ReleasePoint)
            .join(TitleVersion, TitleVersion.release_id == ReleasePoint.id)
            .where(TitleVersion.title_id == title_id, ReleasePoint.seq <= release.seq)
            .order_by(ReleasePoint.seq.desc())
            .limit(1)
        ).first()

    def _guid_for(self, identifier: str, release_id: int) -> str | None:
        return self._session.execute(
            select(GuidMap.guid)
            .where(GuidMap.release_id == release_id, GuidMap.identifier == identifier)
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _ref(release: ReleasePoint, ingested_titles: list[str] | None = None) -> ReleaseRef:
        return ReleaseRef(
            label=release.label,
            currency_date=release.currency_date,
            seq=release.seq,
            congress=release.congress,
            law_num=release.law_num,
            excluded_laws=tuple(release.excluded_laws or ()),
            update_num=release.update_num,
            titles_affected=tuple(release.titles_affected or ()),
            ingested_titles=tuple(sorted(ingested_titles or ())),
        )


def _node_entry(node: StructureNode) -> TocEntry:
    return TocEntry(
        identifier=node.identifier,
        level=node.level,
        num=node.num,
        heading=node.heading,
        status=node.status,
    )


def _padded(title_num: str) -> str:
    """`titles_affected` holds OLRC's file-naming form (`05`, `18a`)."""
    match = re.match(r"^(\d+)([aA]?)$", title_num.strip())
    if not match:
        return title_num
    return f"{int(match.group(1)):02d}{match.group(2).lower()}"
