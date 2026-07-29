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
