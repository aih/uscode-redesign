"""The Postgres `ClassificationRepository` implementation — the only SQL for the
classification tables.

A sibling of `postgres.py` and `postgres_accounts.py`, not a subclass of either:
`PostgresRepository` answers "which text at which release point" and this file
answers "which public law landed where in the Code", and the two share no query,
no table and no resolution step. Both live under `storage/` so `api/` still holds
no session and no SQL (CLAUDE.md architecture rule 1, docs/adr/0017).

`sort=code` orders in Python rather than in SQL. `title_num` is a *string* and
`ORDER BY` on it gives `1, 10, 11, 11a, 12, … 2, 20` (gotcha 16);
`title_sort_key` is the contract for ordering it, and `_section_sort_key` is the
same rule one level down for the section number. So that sort reads the matching
rows' keys into this process, orders them, and pages the sorted list — see
`entries_for_file`.
"""

from __future__ import annotations

import re

from sqlalchemy import Select, func, nulls_last, select
from sqlalchemy.orm import Session

from db.models import ClassificationEntry as ClassificationEntryRow
from db.models import ClassificationFile as ClassificationFileRow
from db.models import ClassificationSourceCheck
from db.models import EcctEntry as EcctEntryRow
from storage.classification import (
    ClassificationCheckInfo,
    ClassificationEntryRef,
    ClassificationFileInfo,
    ClassificationPage,
    EcctEntryRef,
    UnknownPublicLawError,
    identifier_variants,
    law_in_ranges,
    normalize_section_input,
)
from storage.postgres import title_sort_key

_DIGITS = re.compile(r"(\d+)")


def _section_sort_key(section_norm: str) -> tuple[object, ...]:
    """`'45f'` → `(45, 'f')`, `'2'` → `(2, '')` — a section number's own order.

    The same defect `title_sort_key` exists for, one level down: sorted as text,
    a title's sections read `1, 10, 100, 1001, 101, 11, 2`. Digit runs compare as
    numbers and everything between them as text, so `45a-1` sorts after `45a` and
    before `46`.
    """
    parts = _DIGITS.split(section_norm)
    return tuple(int(part) if part.isdigit() else part for part in parts)


def _escape_like(value: str) -> str:
    """`%` and `_` are wildcards; a section number may contain neither, but a
    prefix filter takes whatever was typed."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _file_info(row: ClassificationFileRow) -> ClassificationFileInfo:
    return ClassificationFileInfo(
        kind=row.kind,
        congress=row.congress,
        session=row.session,
        source_url=row.source_url,
        source_filename=row.source_filename,
        covered_laws_text=row.covered_laws_text,
        covered_ranges=tuple(row.covered_ranges or ()),
        first_law=row.first_law,
        last_law=row.last_law,
        prepared_date=row.prepared_date,
        stat_volume=row.stat_volume,
        content_hash=row.content_hash,
        fetched_at=row.fetched_at,
        row_count=row.row_count,
        skipped_lines=row.skipped_lines,
    )


def _entry_ref(
    row: ClassificationEntryRow, congress: int, session: int
) -> ClassificationEntryRef:
    return ClassificationEntryRef(
        congress=congress,
        session=session,
        row_seq=row.row_seq,
        raw_line=row.raw_line,
        title_raw=row.title_raw,
        title_num=row.title_num,
        is_appendix=row.is_appendix,
        section_raw=row.section_raw,
        section_norm=row.section_norm,
        description_raw=row.description_raw,
        is_note=row.is_note,
        action=row.action,
        transfer_counterpart=row.transfer_counterpart,
        act_name=row.act_name,
        usc_identifier=row.usc_identifier,
        pl_congress=row.pl_congress,
        pl_num=row.pl_num,
        pl_section_raw=row.pl_section_raw,
        new_section_quote=row.new_section_quote,
        stat_volume=row.stat_volume,
        stat_pages=tuple(row.stat_pages or ()),
        stat_page_labels=tuple(row.stat_page_labels or ()),
    )


class PostgresClassification:
    """`ClassificationRepository` over the four ADR-0067 tables."""

    def __init__(self, session: Session):
        self._session = session
        # `file_covering_law` is asked twice per public-law request — once by
        # `entries_for_law`, which owes `UnknownPublicLawError` to any caller,
        # and once by the route, which needs the document to name it in the
        # answer. The instance is request-scoped (`storage.get_classification`),
        # so remembering it here is a query saved and nothing kept.
        self._covering: dict[tuple[int, int], ClassificationFileInfo | None] = {}

    # ------------------------------------------------------------- freshness

    def last_classification_check(self) -> ClassificationCheckInfo | None:
        row = self._session.scalars(
            select(ClassificationSourceCheck)
            .order_by(ClassificationSourceCheck.checked_at.desc())
            .limit(1)
        ).first()
        if row is None:
            return None
        return ClassificationCheckInfo(
            checked_at=row.checked_at,
            source_url=row.source_url,
            ok=row.ok,
            files_seen=row.files_seen,
            changed_files=tuple(row.changed_files or ()),
            latest_covered_text=row.latest_covered_text,
            error=row.error,
        )

    # -------------------------------------------------------------- registry

    def list_files(self, *, kind: str | None = None) -> list[ClassificationFileInfo]:
        statement = select(ClassificationFileRow).order_by(
            ClassificationFileRow.congress.desc(),
            ClassificationFileRow.session.desc(),
        )
        if kind is not None:
            statement = statement.where(ClassificationFileRow.kind == kind)
        return [_file_info(row) for row in self._session.scalars(statement)]

    def get_file(
        self, *, congress: int, session: int, kind: str = "pl"
    ) -> ClassificationFileInfo | None:
        row = self._session.scalars(
            select(ClassificationFileRow).where(
                ClassificationFileRow.kind == kind,
                ClassificationFileRow.congress == congress,
                ClassificationFileRow.session == session,
            )
        ).first()
        return _file_info(row) if row else None

    def file_covering_law(
        self, *, congress: int, law_num: int
    ) -> ClassificationFileInfo | None:
        if (congress, law_num) in self._covering:
            return self._covering[(congress, law_num)]
        found = self._covering_law(congress=congress, law_num=law_num)
        self._covering[(congress, law_num)] = found
        return found

    def _covering_law(
        self, *, congress: int, law_num: int
    ) -> ClassificationFileInfo | None:
        rows = self._session.scalars(
            select(ClassificationFileRow)
            .where(
                ClassificationFileRow.kind == "pl",
                ClassificationFileRow.congress == congress,
            )
            .order_by(ClassificationFileRow.session)
        ).all()
        for row in rows:
            if law_in_ranges(law_num, row.covered_ranges or ()):
                return _file_info(row)
        return None

    # --------------------------------------------------------------- entries

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
        file_id = self._session.scalars(
            select(ClassificationFileRow.id).where(
                ClassificationFileRow.kind == "pl",
                ClassificationFileRow.congress == congress,
                ClassificationFileRow.session == session,
            )
        ).first()
        if file_id is None:
            return ClassificationPage(items=(), total=0, limit=limit, offset=offset)

        where = [ClassificationEntryRow.file_id == file_id]
        if pl_congress is not None:
            where.append(ClassificationEntryRow.pl_congress == pl_congress)
        if pl_num is not None:
            where.append(ClassificationEntryRow.pl_num == pl_num)
        if pl_section:
            where.append(
                ClassificationEntryRow.pl_section_raw.like(
                    _escape_like(pl_section) + "%", escape="\\"
                )
            )
        if title_num:
            where.append(ClassificationEntryRow.title_num == title_num.strip().lower())
        if section:
            where.append(
                ClassificationEntryRow.section_norm == normalize_section_input(section)
            )

        if sort == "code":
            return self._code_ordered_page(where, congress, session, limit, offset)

        total = self._count(where)
        rows = self._session.scalars(
            select(ClassificationEntryRow)
            .where(*where)
            .order_by(ClassificationEntryRow.row_seq)
            .limit(limit)
            .offset(offset)
        ).all()
        return ClassificationPage(
            items=tuple(_entry_ref(row, congress, session) for row in rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    def _code_ordered_page(
        self,
        where: list,
        congress: int,
        session: int,
        limit: int,
        offset: int,
    ) -> ClassificationPage:
        """`sort=code`, paged.

        A SQL `OFFSET` can only page an ordering SQL performed, and this one it
        cannot: `title_num` is a string, `title_sort_key` is the contract for
        ordering it (gotcha 16), and reproducing that key as a SQL expression
        would be a second copy of it in a second language. So the ordering runs
        here — over the *keys* alone, one small tuple per matching row (11,737
        for the largest file, the 104th) — and the page is fetched by the ids
        that survive the slice, at the cost of a second query.
        """
        keys = self._session.execute(
            select(
                ClassificationEntryRow.id,
                ClassificationEntryRow.title_num,
                ClassificationEntryRow.section_norm,
                ClassificationEntryRow.row_seq,
            ).where(*where)
        ).all()
        keys.sort(
            key=lambda row: (
                title_sort_key(row.title_num),
                _section_sort_key(row.section_norm),
                row.row_seq,
            )
        )
        wanted = [row.id for row in keys[offset : offset + limit]]
        by_id = {
            row.id: row
            for row in self._session.scalars(
                select(ClassificationEntryRow).where(
                    ClassificationEntryRow.id.in_(wanted)
                )
            )
        }
        return ClassificationPage(
            items=tuple(
                _entry_ref(by_id[entry_id], congress, session)
                for entry_id in wanted
                if entry_id in by_id
            ),
            total=len(keys),
            limit=limit,
            offset=offset,
        )

    def entries_for_law(
        self,
        *,
        congress: int,
        law_num: int,
        section: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ClassificationPage:
        if self.file_covering_law(congress=congress, law_num=law_num) is None:
            raise UnknownPublicLawError(congress, law_num)

        where = [
            ClassificationEntryRow.pl_congress == congress,
            ClassificationEntryRow.pl_num == law_num,
        ]
        if section:
            where.append(
                ClassificationEntryRow.pl_section_raw.like(
                    _escape_like(section) + "%", escape="\\"
                )
            )
        order = (
            ClassificationFileRow.congress,
            ClassificationFileRow.session,
            ClassificationEntryRow.row_seq,
        )
        return self._joined_page(where, order, limit, offset)

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
        wanted = normalize_section_input(section)
        where = [ClassificationEntryRow.title_num == title_num.strip().lower()]
        if exact:
            where.append(ClassificationEntryRow.section_norm == wanted)
        else:
            where.append(
                ClassificationEntryRow.section_norm.like(
                    _escape_like(wanted) + "%", escape="\\"
                )
            )
        if congress is not None:
            where.append(ClassificationEntryRow.pl_congress == congress)
        return self._joined_page(where, self._history_order(), limit, offset)

    def entries_for_title(
        self,
        *,
        title_num: str,
        congress: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ClassificationPage:
        where = [ClassificationEntryRow.title_num == title_num.strip().lower()]
        if congress is not None:
            where.append(ClassificationEntryRow.pl_congress == congress)
        return self._joined_page(where, self._history_order(), limit, offset)

    def entries_for_identifier(
        self, identifier: str, *, limit: int = 200, offset: int = 0
    ) -> ClassificationPage:
        where = [
            ClassificationEntryRow.usc_identifier.in_(identifier_variants(identifier))
        ]
        return self._joined_page(where, self._history_order(), limit, offset)

    @staticmethod
    def _history_order() -> tuple:
        """Newest law first — the order a section's classification history reads
        in. Rows whose Pub. L. cell did not parse sort last rather than first,
        which is what a descending sort would otherwise do with a NULL."""
        return (
            nulls_last(ClassificationEntryRow.pl_congress.desc()),
            nulls_last(ClassificationEntryRow.pl_num.desc()),
            ClassificationEntryRow.row_seq,
        )

    def _joined_page(
        self, where: list, order: tuple, limit: int, offset: int
    ) -> ClassificationPage:
        """A page whose rows may span documents, so each carries its file's
        congress and session — which is the session page the row lives on."""
        total = self._count(where)
        rows = self._session.execute(
            select(
                ClassificationEntryRow,
                ClassificationFileRow.congress,
                ClassificationFileRow.session,
            )
            .join(
                ClassificationFileRow,
                ClassificationFileRow.id == ClassificationEntryRow.file_id,
            )
            .where(*where)
            .order_by(*order)
            .limit(limit)
            .offset(offset)
        ).all()
        return ClassificationPage(
            items=tuple(
                _entry_ref(entry, congress, session)
                for entry, congress, session in rows
            ),
            total=total,
            limit=limit,
            offset=offset,
        )

    def _count(self, where: list) -> int:
        statement: Select = (
            select(func.count())
            .select_from(ClassificationEntryRow)
            .where(*where)
        )
        return self._session.scalar(statement) or 0

    # ------------------------------------------------------------------ ECCT

    def list_ecct(
        self, *, congress: int | None = None, session: int | None = None
    ) -> list[EcctEntryRef]:
        statement = (
            select(
                EcctEntryRow,
                ClassificationFileRow.congress,
                ClassificationFileRow.session,
            )
            .join(
                ClassificationFileRow,
                ClassificationFileRow.id == EcctEntryRow.file_id,
            )
            .order_by(
                ClassificationFileRow.congress.desc(),
                ClassificationFileRow.session.desc(),
                EcctEntryRow.row_seq,
            )
        )
        if congress is not None:
            statement = statement.where(ClassificationFileRow.congress == congress)
        if session is not None:
            statement = statement.where(ClassificationFileRow.session == session)
        return [
            EcctEntryRef(
                congress=file_congress,
                session=file_session,
                row_seq=row.row_seq,
                former_raw=row.former_raw,
                former_title_num=row.former_title_num,
                former_section_norm=row.former_section_norm,
                former_is_note=row.former_is_note,
                new_raw=row.new_raw,
                new_title_num=row.new_title_num,
                new_section_norm=row.new_section_norm,
                new_is_note=row.new_is_note,
                provision_affected=row.provision_affected,
                provision_prompting=row.provision_prompting,
                affected_pl_congress=row.affected_pl_congress,
                affected_pl_num=row.affected_pl_num,
                prompting_pl_congress=row.prompting_pl_congress,
                prompting_pl_num=row.prompting_pl_num,
            )
            for row, file_congress, file_session in self._session.execute(statement)
        ]
