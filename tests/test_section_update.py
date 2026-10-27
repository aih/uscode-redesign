"""The section-level update path (ADR-0095): plan from the classification
tables, fetch the named sections, carry the rest forward.

The pure parts — the window, coverage, ordering, URL templates, the sources —
run without a database. The integration tests build their own scratch
database, load the Title 16 slice as the base release point and assemble the
next one, so they never touch the shared fixture corpus; they skip without a
Postgres (and fail under `USC_REQUIRE_INTEGRATION`, like the rest).
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import urllib.error
import zipfile
from datetime import date
from pathlib import Path

import pytest

from ingest import section_update as su
from ingest.parser import parser_for
from ingest.version_changes import ReleaseFacts
from tests.conftest import REPO_ROOT, SLICE, _unavailable, require


def _facts(label: str, *, id: int = 0, seq: int = 0) -> ReleaseFacts:
    from ingest.release_label import parse_label

    parsed = parse_label(label)
    return ReleaseFacts(
        id=id,
        seq=seq,
        label=label,
        congress=parsed.congress,
        law_num=parsed.law_num,
        excluded=frozenset(parsed.excluded_laws),
    )


# --------------------------------------------------------------------- window


def test_the_window_holds_the_laws_after_the_base_and_skips_the_exclusion():
    laws = su.window_laws(_facts("119-99"), _facts("119-102not101"), {})
    assert laws == [(119, 100), (119, 102)]


def test_a_not_law_entering_is_in_the_window():
    laws = su.window_laws(_facts("119-102not101"), _facts("119-103"), {})
    assert laws == [(119, 101), (119, 103)]


def test_a_window_across_congresses_reads_the_earlier_congress_to_its_last_law():
    laws = su.window_laws(_facts("118-270"), _facts("119-2"), {118: 274})
    assert laws == [(118, 271), (118, 272), (118, 273), (118, 274), (119, 1), (119, 2)]


def test_coverage_is_read_from_the_segments():
    ranges = {119: [(70, 70), (74, 102)]}
    assert su.is_covered(ranges, 119, 70)
    assert not su.is_covered(ranges, 119, 71)
    assert su.is_covered(ranges, 119, 102)
    assert not su.is_covered(ranges, 119, 103)
    assert not su.is_covered(ranges, 118, 80)


# ------------------------------------------------------------------- ordering


def test_section_numbers_sort_naturally_with_either_dash():
    identifiers = ["/us/usc/t16/s100", "/us/usc/t16/s45f–1", "/us/usc/t16/s45f", "/us/usc/t16/s46", "/us/usc/t16/s9"]
    assert sorted(identifiers, key=su.section_sort_key) == [
        "/us/usc/t16/s9",
        "/us/usc/t16/s45f",
        "/us/usc/t16/s45f–1",
        "/us/usc/t16/s46",
        "/us/usc/t16/s100",
    ]
    assert su.section_sort_key("/us/usc/t16/s45f-1") == su.section_sort_key("/us/usc/t16/s45f–1")


def _record(identifier: str, ancestors=()):
    from ingest.records import SectionRecord

    return SectionRecord(
        identifier=identifier, guid="", temporal_id=None, num=None, num_value=None,
        heading=None, status=None, seq=0, xml="<section/>", content_key="",
        source_credit=None, notes=(), guid_refs=(), ancestors=tuple(ancestors),
        schema_version="uslm-1.0.15",
    )


BASE = [
    ("/us/usc/t16/s1", 11, "/us/usc/t16/ch1"),
    ("/us/usc/t16/s2", 12, "/us/usc/t16/ch1"),
    ("/us/usc/t16/s10", 13, "/us/usc/t16/ch2"),
]


def test_a_fetched_section_replaces_its_base_entry_in_place():
    placed = su.assemble_order(BASE, {"/us/usc/t16/s2": (_record("/us/usc/t16/s2"),)})
    assert [p.identifier for p in placed] == ["/us/usc/t16/s1", "/us/usc/t16/s2", "/us/usc/t16/s10"]
    assert placed[1].record is not None and placed[1].version_id is None
    assert placed[1].parent_identifier == "/us/usc/t16/ch1"
    assert placed[0].version_id == 11 and placed[2].version_id == 13


def test_a_new_section_goes_after_its_nearest_lower_neighbour_and_takes_its_parent():
    placed = su.assemble_order(BASE, {"/us/usc/t16/s2a": (_record("/us/usc/t16/s2a"),)})
    assert [p.identifier for p in placed] == [
        "/us/usc/t16/s1", "/us/usc/t16/s2", "/us/usc/t16/s2a", "/us/usc/t16/s10",
    ]
    assert placed[2].parent_identifier == "/us/usc/t16/ch1"


def test_a_new_section_below_every_other_goes_first():
    placed = su.assemble_order(BASE, {"/us/usc/t16/s0": (_record("/us/usc/t16/s0"),)})
    assert placed[0].identifier == "/us/usc/t16/s0"


def test_a_fetched_documents_own_ancestors_win_over_the_neighbours():
    record = _record("/us/usc/t16/s11", ancestors=[("chapter", "/us/usc/t16/ch3")])
    placed = su.assemble_order(BASE, {"/us/usc/t16/s11": (record,)})
    assert placed[-1].identifier == "/us/usc/t16/s11"
    assert placed[-1].parent_identifier == "/us/usc/t16/ch3"


def test_a_repeated_identifier_is_replaced_by_every_fetched_occurrence_once():
    base = BASE[:2] + [("/us/usc/t16/s2", 14, "/us/usc/t16/ch1")] + BASE[2:]
    fetched = (_record("/us/usc/t16/s2"), _record("/us/usc/t16/s2"))
    placed = su.assemble_order(base, {"/us/usc/t16/s2": fetched})
    assert [p.identifier for p in placed].count("/us/usc/t16/s2") == 2
    assert all(p.record is not None for p in placed if p.identifier == "/us/usc/t16/s2")


# --------------------------------------------------------------------- sources


def test_the_url_template_takes_four_placeholders():
    template = "https://example.test/{title_padded}/{title}/{section}?id={identifier}"
    assert su.section_url(template, "/us/usc/t16/s45f") == (
        "https://example.test/16/16/45f?id=/us/usc/t16/s45f"
    )
    assert su.section_url(template, "/us/usc/t5a/s3").startswith("https://example.test/05a/5a/3")
    assert "%E2%80%93" in su.section_url("{section}", "/us/usc/t16/s45a–1")


def test_a_non_section_identifier_is_refused():
    with pytest.raises(su.SectionUpdateError):
        su.section_url("{section}", "/us/usc/t16/ch1")


@pytest.fixture(scope="module")
def s45f_xml() -> str:
    for record in parser_for(require(SLICE)).iter_sections(SLICE):
        if record.identifier == "/us/usc/t16/s45f":
            return record.xml
    raise AssertionError("s45f is not in the slice")


def test_a_bare_section_document_reads_as_its_section(s45f_xml):
    records, schema_version = su.records_from_document(s45f_xml.encode(), "/us/usc/t16/s45f")
    assert [r.identifier for r in records] == ["/us/usc/t16/s45f"]
    assert schema_version.startswith("uslm-1")


def test_a_whole_title_document_yields_only_the_asked_for_section():
    records, _ = su.records_from_document(require(SLICE).read_bytes(), "/us/usc/t16/s45f")
    assert [r.identifier for r in records] == ["/us/usc/t16/s45f"]
    assert records[0].ancestors  # a whole document carries the hierarchy


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_url_source_reads_a_section_caches_it_and_reads_404_as_absent(tmp_path, s45f_xml, monkeypatch):
    monkeypatch.setattr(su, "throttle", lambda: None)
    calls: list[str] = []

    def opener(request, timeout):
        calls.append(request.full_url)
        assert "uscode-redesign" in request.get_header("User-agent")
        if request.full_url.endswith("s45f"):
            return _Response(s45f_xml.encode())
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    source = su.UrlSectionSource("https://example.test{identifier}", cache_dir=tmp_path, opener=opener)
    first = source.fetch("/us/usc/t16/s45f")
    again = source.fetch("/us/usc/t16/s45f")
    assert first is not None and again is not None
    assert first.records[0].identifier == "/us/usc/t16/s45f"
    assert first.sha256 == again.sha256
    assert calls == ["https://example.test/us/usc/t16/s45f"]
    assert source.fetch("/us/usc/t16/s99999") is None


def test_the_url_source_refuses_a_page_that_is_not_uslm(tmp_path, monkeypatch):
    monkeypatch.setattr(su, "throttle", lambda: None)
    source = su.UrlSectionSource(
        "https://example.test{identifier}",
        opener=lambda request, timeout: _Response(b"<html><body>Page Not Found</body></html>"),
    )
    with pytest.raises(su.SectionUpdateError, match="not a USLM document"):
        source.fetch("/us/usc/t16/s45f")


def test_the_directory_source_names_files_by_identifier(tmp_path, s45f_xml):
    (tmp_path / su.directory_filename("/us/usc/t16/s45f")).write_text(s45f_xml)
    assert su.directory_filename("/us/usc/t16/s45a–1") == "t16-s45a–1.xml"
    source = su.DirectorySectionSource(tmp_path)
    assert source.fetch("/us/usc/t16/s45f") is not None
    assert source.fetch("/us/usc/t16/s1") is None


def test_the_title_file_source_reads_a_zip_member(tmp_path):
    archive = tmp_path / "xml_uscAll@119-102not101.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("usc01.xml", "<nothing/>")
        handle.write(require(SLICE), "usc16.xml")
    source = su.TitleFileSource(archive, "16")
    fetched = source.fetch("/us/usc/t16/s45f")
    assert fetched is not None and fetched.records[0].identifier == "/us/usc/t16/s45f"
    assert source.fetch("/us/usc/t16/s99999") is None


# ----------------------------------------------------------------- integration


SCRATCH_DB = f"uscode_section_update_{os.getpid()}"

BASE_LABEL = "119-99"
TARGET_LABEL = "119-102not101"


def _alembic(url: str, *args: str) -> None:
    env = dict(os.environ, DATABASE_URL=url)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def scratch_sessions():
    """A migrated scratch database, its sessionmaker, and the slice loaded as
    Title 16 at 119-99 with 119-102not101 as the next release point."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from db.config import settings

    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
            conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    except Exception as exc:  # pragma: no cover - environment-dependent
        _unavailable(f"cannot create a scratch database: {exc}")
    finally:
        admin.dispose()

    url = settings.database_url.rsplit("/", 1)[0] + f"/{SCRATCH_DB}"
    engine = create_engine(url)
    try:
        _alembic(url, "upgrade", "head")
        factory = sessionmaker(bind=engine)
        from db.models import ReleasePoint
        from ingest.load import load_release

        with factory() as session:
            for seq, label, day in ((1, BASE_LABEL, date(2026, 6, 12)), (2, TARGET_LABEL, date(2026, 7, 12))):
                from ingest.release_label import parse_label

                parsed = parse_label(label)
                session.add(ReleasePoint(
                    congress=parsed.congress, law_num=parsed.law_num,
                    excluded_laws=list(parsed.excluded_laws), update_num=parsed.update_num,
                    label=label, currency_date=day, seq=seq,
                ))
            session.commit()
            load_release(require(SLICE), BASE_LABEL, session)
        yield factory
    finally:
        engine.dispose()
        admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _classify(session, rows, *, covered=("74-102",)):
    """Replace the scratch database's 119-2 table with `rows`:
    (law, section_norm, action, is_note)."""
    from sqlalchemy import delete

    from db.models import ClassificationEntry, ClassificationFile

    session.execute(delete(ClassificationEntry))
    session.execute(delete(ClassificationFile))
    file = ClassificationFile(
        kind="pl", congress=119, session=2, source_url="file:///tbl119pl_2nd.html",
        source_filename="tbl119pl_2nd.html", covered_laws_text="test",
        covered_ranges=list(covered), first_law=74, last_law=102,
        content_hash="0", row_count=len(rows), skipped_lines=0,
    )
    session.add(file)
    session.flush()
    for seq, (law, section_norm, action, is_note) in enumerate(rows):
        session.add(ClassificationEntry(
            file_id=file.id, row_seq=seq, raw_line="", title_raw="16", title_num="16",
            section_raw=section_norm, section_norm=section_norm, description_raw=action or "",
            is_note=is_note, action=action,
            usc_identifier=f"/us/usc/t16/s{section_norm.replace('-', '–')}",
            pl_congress=119, pl_num=law, pl_section_raw="1",
        ))
    session.commit()


def _republished(xml: str, prefix: str) -> str:
    """`xml` with fresh guids, as the source writes at every release point."""
    return xml.replace('id="id', f'id="id{prefix}').replace('id="fn', f'id="fn{prefix}')


def _amended(xml: str) -> str:
    """s45f with one word of its text changed."""
    assert "Secretary" in xml
    return _republished(xml, "aaaa").replace("Secretary", "Under Secretary", 1)


def _new_section(xml: str) -> str:
    """A section 45f–1 that the base does not hold, cut from s45f's markup."""
    return (
        _republished(xml, "bbbb")
        .replace('identifier="/us/usc/t16/s45f', 'identifier="/us/usc/t16/s45f–1')
        .replace('value="45f"', 'value="45f–1"', 1)
    )


def _items(session):
    from sqlalchemy import select

    from db.models import SectionUpdateItem

    return session.scalars(select(SectionUpdateItem).order_by(SectionUpdateItem.id)).all()


def _map_count(session, label):
    from sqlalchemy import func, select

    from db.models import ReleasePoint, SectionReleaseMap

    return session.scalar(
        select(func.count()).select_from(SectionReleaseMap)
        .join(ReleasePoint, ReleasePoint.id == SectionReleaseMap.release_id)
        .where(ReleasePoint.label == label)
    )


def test_the_plan_names_the_sections_of_the_laws_in_the_window(scratch_sessions):
    with scratch_sessions() as session:
        _classify(session, [
            (99, "45a", None, False),     # incorporated at the base: not in the window
            (100, "45f", None, False),
            (102, "45f", "nt", True),
            (102, "45b", None, False),
        ])
        plan = su.plan_update(session, TARGET_LABEL)
    assert plan.ok
    assert plan.window_laws == [(119, 100), (119, 102)]
    [title] = plan.ready
    assert title.base is not None and title.base.label == BASE_LABEL
    assert list(title.sections) == ["/us/usc/t16/s45b", "/us/usc/t16/s45f"]
    assert [r.law for r in title.sections["/us/usc/t16/s45f"]] == ["119-100", "119-102"]
    assert plan.laws_without_rows == []


def test_a_law_the_tables_do_not_cover_stops_the_plan(scratch_sessions):
    with scratch_sessions() as session:
        _classify(session, [(100, "45f", None, False)], covered=("74-100",))
        plan = su.plan_update(session, TARGET_LABEL)
        assert plan.uncovered_laws == [(119, 102)]
        with pytest.raises(su.SectionUpdateError, match="do not cover"):
            su.apply_plan(session, plan, lambda _t: su.DirectorySectionSource(Path("/nonexistent")))


def test_a_section_the_source_lacks_fails_the_title_and_writes_nothing(scratch_sessions, tmp_path):
    from sqlalchemy import select

    from db.models import ReleasePoint, TitleVersion

    with scratch_sessions() as session:
        _classify(session, [(100, "45f", None, False)])
        plan = su.plan_update(session, TARGET_LABEL)
        [result] = su.apply_plan(session, plan, lambda _t: su.DirectorySectionSource(tmp_path))
        assert result.status == "failed"
        assert result.not_found == ["/us/usc/t16/s45f"]
        target = session.scalar(select(ReleasePoint.id).where(ReleasePoint.label == TARGET_LABEL))
        assert session.scalar(select(TitleVersion).where(TitleVersion.release_id == target)) is None
        assert _map_count(session, TARGET_LABEL) == 0


def test_the_update_fetches_the_named_sections_and_carries_the_rest(scratch_sessions, tmp_path, s45f_xml):
    from sqlalchemy import select

    from db.models import (
        GuidMap,
        ReleasePoint,
        Section,
        SectionReleaseMap,
        SectionVersion,
        TitleVersion,
    )

    (tmp_path / "t16-s45f.xml").write_text(_amended(s45f_xml))
    (tmp_path / "t16-s45f–1.xml").write_text(_new_section(s45f_xml))
    with scratch_sessions() as session:
        _classify(session, [
            (100, "45f", None, False),
            (102, "45f", "nt", True),
            (102, "45f-1", "new", False),
        ])
        plan = su.plan_update(session, TARGET_LABEL)
        [result] = su.apply_plan(session, plan, lambda _t: su.DirectorySectionSource(tmp_path))
        assert result.status == "loaded"
        assert (result.new_versions, result.new_sections, result.unchanged) == (1, 1, 0)

        base_count = _map_count(session, BASE_LABEL)
        assert _map_count(session, TARGET_LABEL) == base_count + 1
        assert result.sections_loaded == base_count + 1

        target_id = session.scalar(select(ReleasePoint.id).where(ReleasePoint.label == TARGET_LABEL))
        base_id = session.scalar(select(ReleasePoint.id).where(ReleasePoint.label == BASE_LABEL))
        tv = session.scalar(select(TitleVersion).where(TitleVersion.release_id == target_id))
        assert tv.load_method == "sections" and tv.base_release_id == base_id
        assert tv.sections_loaded == base_count + 1

        def mapped(release_id):
            return dict(session.execute(
                select(Section.identifier, SectionReleaseMap.section_version_id)
                .join(SectionVersion, SectionVersion.section_id == Section.id)
                .join(SectionReleaseMap, SectionReleaseMap.section_version_id == SectionVersion.id)
                .where(SectionReleaseMap.release_id == release_id)
            ).all())

        before, after = mapped(base_id), mapped(target_id)
        changed = {i for i in after if before.get(i) != after[i]}
        assert changed == {"/us/usc/t16/s45f", "/us/usc/t16/s45f–1"}
        text = session.scalar(select(SectionVersion.xml).where(SectionVersion.id == after["/us/usc/t16/s45f"]))
        assert "Under Secretary" in text

        order = session.execute(
            select(Section.identifier, SectionReleaseMap.parent_identifier)
            .join(SectionVersion, SectionVersion.section_id == Section.id)
            .join(SectionReleaseMap, SectionReleaseMap.section_version_id == SectionVersion.id)
            .where(SectionReleaseMap.release_id == target_id)
            .order_by(SectionReleaseMap.seq_in_title)
        ).all()
        identifiers = [i for i, _p in order]
        at = identifiers.index("/us/usc/t16/s45f")
        assert identifiers[at + 1] == "/us/usc/t16/s45f–1"
        assert order[at + 1][1] == order[at][1]

        guids = session.scalars(select(GuidMap.identifier).where(GuidMap.release_id == target_id)).all()
        assert guids and all(g.startswith("/us/usc/t16/s45f") for g in guids)

        items = [(i.identifier, f"{i.pl_congress}-{i.pl_num}", i.outcome, i.is_note) for i in _items(session)]
        assert items == [
            ("/us/usc/t16/s45f", "119-100", "new-version", False),
            ("/us/usc/t16/s45f", "119-102", "new-version", True),
            ("/us/usc/t16/s45f–1", "119-102", "new-section", False),
        ]

        # Planning again finds the title loaded and fetches nothing.
        assert su.plan_update(session, TARGET_LABEL).ready == []


def test_the_answer_says_a_title_was_assembled_and_from_where(scratch_sessions):
    """Runs after the update above: s45f was fetched for two laws, s45a was
    carried from the base."""
    from params import served_note
    from storage.postgres import PostgresRepository

    with scratch_sessions() as session:
        repo = PostgresRepository(session)
        resolved = repo.resolve_release(label=TARGET_LABEL)

        fetched = repo.get_section("/us/usc/t16/s45f", resolved)
        assert fetched is not None
        assert fetched.assembled_from is not None and fetched.assembled_from.label == BASE_LABEL
        assert fetched.fetched_for == ("119-100", "119-102")
        assert "fetched from the Code because the tables classify Pub. L. 119-100, Pub. L. 119-102" in served_note(fetched, resolved)
        assert fetched.guid and fetched.guid.startswith("idaaaa")

        carried = repo.get_section("/us/usc/t16/s45a", resolved)
        assert carried is not None
        assert carried.served_from.label == TARGET_LABEL
        assert carried.fetched_for == ()
        assert f"its text as published at {BASE_LABEL}" in served_note(carried, resolved)
        # No guid of its own at the assembled release point: the base's pins the same text.
        base = repo.get_section("/us/usc/t16/s45a", repo.resolve_release(label=BASE_LABEL))
        assert carried.guid is not None and carried.guid == base.guid
        assert base.assembled_from is None and served_note(base, repo.resolve_release(label=BASE_LABEL)) is None


def test_a_rerun_over_an_interrupted_update_starts_from_nothing(scratch_sessions, tmp_path, s45f_xml):
    from sqlalchemy import select, update

    from db.models import ReleasePoint, TitleVersion

    (tmp_path / "t16-s45f.xml").write_text(_amended(s45f_xml))
    with scratch_sessions() as session:
        target_id = session.scalar(select(ReleasePoint.id).where(ReleasePoint.label == TARGET_LABEL))
        session.execute(update(TitleVersion).where(TitleVersion.release_id == target_id).values(sections_loaded=None))
        session.commit()
        _classify(session, [(100, "45f", None, False)])
        plan = su.plan_update(session, TARGET_LABEL)
        [result] = su.apply_plan(session, plan, lambda _t: su.DirectorySectionSource(tmp_path))
        assert result.status == "loaded"
        assert _map_count(session, TARGET_LABEL) == _map_count(session, BASE_LABEL)
        assert [(i.identifier, i.outcome) for i in _items(session)] == [("/us/usc/t16/s45f", "new-version")]


def test_the_titles_file_replaces_an_assembled_load(scratch_sessions):
    from sqlalchemy import select

    from db.models import ReleasePoint, TitleVersion
    from ingest.load import load_release
    from ingest.load_all import completed_pairs

    with scratch_sessions() as session:
        assert (TARGET_LABEL, "16") not in completed_pairs(session)
        stats = load_release(require(SLICE), TARGET_LABEL, session)
        target_id = session.scalar(select(ReleasePoint.id).where(ReleasePoint.label == TARGET_LABEL))
        tv = session.scalar(select(TitleVersion).where(TitleVersion.release_id == target_id))
        assert tv.load_method == "release-point" and tv.base_release_id is None
        assert _map_count(session, TARGET_LABEL) == stats.sections_ingested
        assert (TARGET_LABEL, "16") in completed_pairs(session)
