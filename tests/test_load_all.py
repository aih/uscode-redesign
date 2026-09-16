"""Bulk load planning, resume semantics, and verification.

The planning and vocabulary logic is unit-tested with no database. The pieces
that genuinely need Postgres (`run_load_all`, `verify_database`) are marked
`integration` and skip without one, the same contract `tests/test_api.py` uses.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from ingest.backfill import DownloadLedger, LedgerEntry
from ingest.download import FetchStatus
from ingest.inventory import ReleasePointEntry
from ingest.load_all import (
    LoadTask,
    _extracted,
    _file_form,
    plan_loads,
)
from tests.conftest import SLICE


@pytest.fixture
def entries() -> list[ReleasePointEntry]:
    return [
        ReleasePointEntry("113-21", date(2013, 7, 18), ("16", "18"), "u", "", seq=0),
        ReleasePointEntry("113-31", date(2013, 8, 9), ("16",), "u", "", seq=1),
        ReleasePointEntry("113-36", date(2013, 9, 18), ("01",), "u", "", seq=2),
    ]


def _ledger(tmp_path: Path, members: dict[str, str]) -> DownloadLedger:
    """`{"113-21/16": "ok"}` → a ledger with matching files on disk."""
    dest = tmp_path / "releases"
    ledger = DownloadLedger(dest / "ledger.json")
    for key, status in members.items():
        release, title = key.split("/")
        relative = f"{release}/xml_usc{title}@{release}.zip"
        if status == FetchStatus.OK:
            path = dest / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"not-a-real-zip-but-present")
        ledger.record(
            LedgerEntry(
                release_label=release,
                title_num=title,
                status=str(status),
                url=f"https://example/{key}",
                path=relative if status == FetchStatus.OK else None,
            )
        )
    return ledger


# --------------------------------------------------------------------------
# Title-number vocabularies
# --------------------------------------------------------------------------


def test_file_form_pads_single_digit_titles():
    """`Title.num` is the URL form from <docNumber> (`1`); the ledger and every
    OLRC filename use the padded form (`01`). Resume compares them, so this is
    the difference between skipping loaded work and reloading titles 1-9 forever."""
    assert _file_form("1") == "01"
    assert _file_form("16") == "16"
    assert _file_form("5a") == "05a"


def test_file_form_passes_through_what_it_cannot_parse():
    """An odd docNumber becomes a reported mismatch, never an exception mid-run."""
    assert _file_form("5 App.") == "5 App."


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


def test_plan_is_ordered_oldest_release_first(tmp_path, entries):
    """Seq order is what puts the baseline before the deltas that assume it, and
    what keeps `first_release_id` on the earliest release carrying a text."""
    ledger = _ledger(
        tmp_path,
        {"113-36/01": FetchStatus.OK, "113-21/16": FetchStatus.OK, "113-31/16": FetchStatus.OK},
    )
    tasks = plan_loads(ledger, entries)
    assert [t.key for t in tasks] == ["113-21/16", "113-31/16", "113-36/01"]


def test_plan_skips_unavailable_entries(tmp_path, entries):
    ledger = _ledger(
        tmp_path, {"113-21/16": FetchStatus.OK, "113-21/18": FetchStatus.UNAVAILABLE}
    )
    assert [t.key for t in plan_loads(ledger, entries)] == ["113-21/16"]


def test_plan_skips_entries_whose_file_is_gone(tmp_path, entries):
    ledger = _ledger(tmp_path, {"113-21/16": FetchStatus.OK, "113-31/16": FetchStatus.OK})
    ledger.resolve_path(ledger.entries["113-31/16"]).unlink()
    assert [t.key for t in plan_loads(ledger, entries)] == ["113-21/16"]


def test_plan_skips_releases_the_inventory_does_not_know(tmp_path, entries):
    """`seq` defines the order; a label without one has no place in it."""
    ledger = _ledger(tmp_path, {"113-21/16": FetchStatus.OK, "999-1/16": FetchStatus.OK})
    assert [t.key for t in plan_loads(ledger, entries)] == ["113-21/16"]


def test_plan_filters_by_title_in_either_vocabulary(tmp_path, entries):
    ledger = _ledger(tmp_path, {"113-36/01": FetchStatus.OK, "113-21/16": FetchStatus.OK})
    assert [t.key for t in plan_loads(ledger, entries, titles={"1"})] == ["113-36/01"]
    assert [t.key for t in plan_loads(ledger, entries, titles={"01"})] == ["113-36/01"]


def test_plan_filters_by_release(tmp_path, entries):
    ledger = _ledger(tmp_path, {"113-21/16": FetchStatus.OK, "113-31/16": FetchStatus.OK})
    tasks = plan_loads(ledger, entries, releases={"113-31"})
    assert [t.key for t in tasks] == ["113-31/16"]


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def test_extracted_yields_the_xml_and_cleans_up(tmp_path):
    """Peak disk stays at one title's XML, not the whole corpus's."""
    zip_path = tmp_path / "t.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("usc16.xml", "<uscDoc/>")
    zip_path.write_bytes(buffer.getvalue())

    with _extracted(zip_path) as xml_path:
        assert xml_path.read_text() == "<uscDoc/>"
        extracted_dir = xml_path.parent
    assert not extracted_dir.exists()


def test_extracted_rejects_an_ambiguous_archive(tmp_path):
    zip_path = tmp_path / "t.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.xml", "<a/>")
        archive.writestr("b.xml", "<b/>")
    zip_path.write_bytes(buffer.getvalue())

    with pytest.raises(ValueError, match="expected one .xml"):
        with _extracted(zip_path):
            pass


# --------------------------------------------------------------------------
# Against a real database
# --------------------------------------------------------------------------


@pytest.fixture
def session_factory():
    try:
        from sqlalchemy import select

        from db.base import SessionLocal
        from db.models import ReleasePoint

        with SessionLocal() as session:
            if not session.scalars(select(ReleasePoint).limit(1)).first():
                pytest.skip("no release points seeded — run `make dev-data`")
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"no database: {exc}")
    return SessionLocal


@pytest.mark.integration
def test_completed_pairs_speaks_the_ledger_vocabulary(session_factory):
    """Whatever is loaded, the pairs come back in padded file-naming form so they
    can be compared to `LoadTask.title_num` directly."""
    from ingest.load_all import completed_pairs

    with session_factory() as session:
        pairs = completed_pairs(session)

    for _, title_num in pairs:
        assert title_num == _file_form(title_num), f"{title_num} is not in file form"


@pytest.mark.integration
def test_run_load_all_skips_what_is_already_complete(session_factory, tmp_path):
    """The resume path: with every task already done, nothing loads."""
    from ingest.load_all import completed_pairs, run_load_all

    with session_factory() as session:
        pairs = sorted(completed_pairs(session))
    if not pairs:
        pytest.skip("nothing loaded yet to resume over")

    label, title_num = pairs[0]
    tasks = [LoadTask(label, title_num, 0, tmp_path / "unused.zip")]
    report = run_load_all(tasks, session_factory, write_manifests=False)

    assert report.loaded == 0
    assert report.skipped == 1
    # The zip was never opened — proof the skip happened before any I/O.
    assert not (tmp_path / "unused.zip").exists()


@pytest.mark.integration
def test_verify_reports_are_internally_consistent(session_factory):
    from ingest.verify import verify_database

    with session_factory() as session:
        report = verify_database(session)

    assert report.title_versions_checked == len(report.checks)
    for check in report.checks:
        # Shallow verification's whole claim: the recorded count is the row count.
        assert check.stored_matches == (check.sections_loaded == check.rows_in_release_map)
    assert report.sound == (not report.count_mismatches and not report.source_mismatches)
    # guid_rows is reported, not left at its default — it was declared on the
    # report and never filled in, so the artifact claimed zero guids for a
    # corpus with millions of them.
    if report.release_map_rows:
        assert report.guid_rows > report.release_map_rows


def test_deep_recount_keys_the_ledger_in_its_own_title_form(tmp_path):
    """`Title.num` is the URL form (`5`); ledger keys use the file-naming form
    (`05`). Looking one up with the other found nothing and returned silently, so
    the deep recount skipped every single-digit title — 504 of 3,153 on the full
    corpus, Title 5 included — while the report still read as if it had checked
    everything."""
    import zipfile

    from ingest.verify import TitleCheck, _recount_from_source

    zip_path = tmp_path / "xml_usc05@119-99.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(SLICE, arcname="usc05.xml")

    ledger = DownloadLedger(path=tmp_path / "ledger.json")
    ledger.entries["119-99/05"] = LedgerEntry(
        release_label="119-99",
        title_num="05",
        status=FetchStatus.OK,
        url="https://example.invalid/xml_usc05@119-99.zip",
        path=zip_path.name,
    )

    # The database spells this title `5`; only the translation to `05` finds it.
    check = TitleCheck(
        release_label="119-99", title_num="5", sections_loaded=0, rows_in_release_map=0
    )
    assert _recount_from_source(check, ledger) is True
    assert check.source_sections is not None and check.source_sections > 0

    # And a title-version with no source file at all reports False, so the caller
    # can name it as unchecked instead of passing over it in silence.
    missing = TitleCheck(
        release_label="119-99", title_num="99", sections_loaded=0, rows_in_release_map=0
    )
    assert _recount_from_source(missing, ledger) is False
    assert missing.source_sections is None


# --------------------------------------------------------------------------
# ADR-0082 — a load that did not finish is not a load
# --------------------------------------------------------------------------


def test_the_dedupe_check_reads_ids_and_hashes_and_never_the_text():
    """`load_release` looks every stored version of the title up once, to decide
    whether a section's text is new. Loading the rows themselves loaded every
    stored text of the title — 3.8 GB for title 42 — and was what the site box
    ran out of memory on (ADR-0082). The statement is held to four columns."""
    from ingest.load import known_versions_statement

    statement = known_versions_statement(1)
    columns = [c.name for c in statement.selected_columns]
    assert columns == ["section_id", "id", "content_hash", "first_release_id"]
    assert "xml" not in str(statement)


@pytest.mark.integration
def test_an_unfinished_load_is_neither_served_nor_counted(session_factory):
    """A `title_versions` row is written at the first commit of a load and its
    completion marker last, so a loader that dies in between leaves a row that
    names a release point holding none of the title's sections. Nothing that
    decides where a title is served from may count that row — and the health
    report must, so it is repaired rather than hidden."""
    from sqlalchemy import func, select

    from db.models import ReleasePoint, Title, TitleVersion
    from storage.postgres import PostgresRepository
    from tests.test_api import CURRENT

    label = "999-1"

    def remove_planted() -> None:
        with session_factory() as session:
            release = session.scalars(
                select(ReleasePoint).where(ReleasePoint.label == label)
            ).first()
            if release is None:
                return
            for row in session.scalars(
                select(TitleVersion).where(TitleVersion.release_id == release.id)
            ):
                session.delete(row)
            # No relationship is declared between the two models, so the unit
            # of work does not know the order; flush the child rows first.
            session.flush()
            session.delete(release)
            session.commit()

    remove_planted()  # a previous run that died mid-test
    with session_factory() as session:
        # Relative to whatever this database holds: a development corpus whose
        # inventory is ahead of its loads is itself "incomplete", honestly.
        baseline = PostgresRepository(session).corpus_health()
        title = session.scalars(select(Title).where(Title.num == "16")).one()
        newest_seq = session.scalar(select(func.max(ReleasePoint.seq)))
        release = ReleasePoint(
            congress=999,
            law_num=1,
            excluded_laws=[],
            label=label,
            currency_date=date(2099, 1, 1),
            seq=newest_seq + 1,
            titles_affected=["16", "47"],
        )
        session.add(release)
        session.flush()
        session.add(
            TitleVersion(
                title_id=title.id,
                release_id=release.id,
                source_zip_sha256="",
                schema_version="uslm-1.0.15",
                sections_loaded=None,
            )
        )
        session.commit()

    try:
        with session_factory() as session:
            repository = PostgresRepository(session)

            # The newest release point *for title 16* is still the newest one
            # it finished loading at, and a request for the planted release
            # point is served from there, out loud.
            assert repository.resolve_release(title_num="16").release.label == CURRENT
            planted = repository.resolve_release(label=label)
            section = repository.get_section("/us/usc/t16/s45f", planted)
            assert section is not None
            assert section.release.label == label
            assert section.served_from.label == CURRENT
            toc = repository.get_toc("/us/usc/t16/ch1", planted)
            assert toc is not None and toc.served_from.label == CURRENT
            assert toc.children or toc.sections

            # Neither listing counts it as ingested.
            by_label = {r.label: r for r in repository.list_releases()}
            assert by_label[label].ingested_titles == ()
            assert label not in next(
                t for t in repository.list_titles() if t.num == "16"
            ).ingested_releases

            # And the health report names it twice: as a load that did not
            # finish, and as a title the release point changed that is not held.
            health = repository.corpus_health()
            assert f"{label}/16" in health.incomplete_loads
            assert set(health.unloaded_titles) >= {f"{label}/16", f"{label}/47"}
            assert health.newest_complete_label == baseline.newest_complete_label
            assert health.problems == baseline.problems + 3
            assert not health.ok
    finally:
        remove_planted()

    with session_factory() as session:
        assert PostgresRepository(session).corpus_health() == baseline
