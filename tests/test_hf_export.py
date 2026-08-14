"""The Hugging Face parquet export (`ingest/hf_export.py`, ADR-0069).

Unit tests need no database. The integration test runs against whatever corpus
is loaded: on the CI fixture corpus (Title 16 at 119-99 and 119-102not101,
`make ci-data`) it exports everything and asserts exact counts; on a larger
corpus it exports with `--limit` and asserts row shape, because a full export
is a half-hour job that belongs in `make hf-export`, not the test suite.
"""

import json

import pytest

pytest.importorskip("pyarrow")

import pyarrow.parquet as pq

from ingest import hf_export
from ingest.hf_export import ExportReport, citation_for, export, _num_value


def test_citation_for_flat_sections():
    assert citation_for("/us/usc/t16/s45f") == "16 U.S.C. § 45f"
    assert citation_for("/us/usc/t42/s1983") == "42 U.S.C. § 1983"


def test_citation_preserves_the_en_dash():
    # OLRC writes section numbers with U+2013, and 5,697 sections carry one
    # (gotcha 17) — the citation must not silently normalize it.
    assert citation_for("/us/usc/t16/s45a–1") == "16 U.S.C. § 45a–1"


def test_citation_declines_appendix_and_act_forms():
    assert citation_for("/us/usc/t5a/pl/92/463/s1") is None
    assert citation_for("/us/usc/t50a/act/1917-05-18/ch15/s212") is None
    assert citation_for("/us/usc/t16/ch1/schI") is None


def test_num_value_reads_the_last_segment():
    assert _num_value("/us/usc/t16/s45a–1") == "45a–1"
    assert _num_value("/us/usc/t5a/pl/92/463/s1") == "1"
    assert _num_value("/us/usc/t16") is None


def test_the_leaked_sigil_identifiers_are_normalized():
    # Four corpus identifiers embed '§ ' (narrow no-break space) in the
    # section segment — a converter quirk, e.g. /us/usc/t2/s §112g.
    quirk = "/us/usc/t2/s § 112g"
    assert citation_for(quirk) == "2 U.S.C. § 112g"
    assert _num_value(quirk) == "112g"


def test_schemas_share_the_identity_columns():
    current = set(hf_export.CURRENT_SCHEMA.names)
    versions = set(hf_export.VERSIONS_SCHEMA.names)
    shared = {name for name, _ in hf_export._SHARED_FIELDS}
    assert shared <= current
    assert shared <= versions


def test_unknown_config_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        export(tmp_path, configs=("both",), session=object())


def test_unchanged_fingerprint_skips(tmp_path, monkeypatch):
    stamp = {"newest_release": {"label": "119-102not101", "seq": 381}, "counts": {}}
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "fingerprint": stamp,
                "configs": {"current": {"rows": 5}, "versions": {"rows": 9}},
            }
        )
    )
    monkeypatch.setattr(hf_export, "fingerprint", lambda session: stamp)
    events: list[str] = []
    report = export(tmp_path, session=object(), on_event=events.append)
    assert report == ExportReport(
        unchanged=True,
        manifest_path=tmp_path / "manifest.json",
        rows={"current": 5, "versions": 9},
    )
    assert any("Nothing changed since 119-102not101" in event for event in events)


def test_changed_fingerprint_does_not_skip(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"fingerprint": {"counts": {"sections": 1}}, "configs": {}})
    )
    monkeypatch.setattr(
        hf_export, "fingerprint", lambda session: {"counts": {"sections": 2}}
    )
    # The gate is passed; the export then needs a real session and fails on the
    # stub — which is the proof it tried to run.
    with pytest.raises(Exception):
        export(tmp_path, session=object(), on_event=lambda _: None)


FIXTURE_CORPUS_RELEASES = {"119-99", "119-102not101"}


@pytest.mark.integration
def test_export_against_the_loaded_corpus(loaded_database, tmp_path):
    from sqlalchemy import func, select

    from db.base import SessionLocal
    from db.models import ReleasePoint, Section, SectionVersion

    with SessionLocal() as session:
        release_labels = set(session.scalars(select(ReleasePoint.label)))
        section_count = session.scalar(select(func.count()).select_from(Section))
        version_count = session.scalar(
            select(func.count()).select_from(SectionVersion)
        )

        fixture_corpus = release_labels <= FIXTURE_CORPUS_RELEASES
        limit = None if fixture_corpus else 300
        report = export(
            tmp_path, session=session, limit=limit, on_event=lambda _: None
        )

    assert not report.unchanged
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert set(manifest["configs"]) == {"current", "versions"}
    assert manifest["partial"] is (not fixture_corpus)

    current = pq.read_table(
        sorted((tmp_path / "current").glob("*.parquet"))[0].parent
    )
    versions = pq.read_table(
        sorted((tmp_path / "versions").glob("*.parquet"))[0].parent
    )
    assert current.schema.names == hf_export.CURRENT_SCHEMA.names
    assert versions.schema.names == hf_export.VERSIONS_SCHEMA.names

    if fixture_corpus:
        # One current row per section, one versions row per stored version —
        # the ci-data corpus is Title 16 alone: 5,095 real sections (ADR-0005).
        assert current.num_rows == section_count == 5095
        assert versions.num_rows == version_count
    else:
        assert current.num_rows == 300
        assert versions.num_rows == 300

    rows = {row["identifier"]: row for row in current.to_pylist()}

    # The reserved subchapter is structure, not a section (gotcha 13).
    assert not any("schXCVII" in identifier for identifier in rows)
    assert all(identifier.startswith("/us/usc/t") for identifier in rows)

    if fixture_corpus:
        s45f = rows["/us/usc/t16/s45f"]
        assert s45f["citation"] == "16 U.S.C. § 45f"
        assert s45f["heading"] == "Mineral King Valley addition authorized"
        assert s45f["release_label"] == "119-102not101"
        assert s45f["text"].startswith(
            "§ 45f. Mineral King Valley addition authorized"
        )
        assert "References in Text" not in s45f["text"]
        assert {note["topic"] for note in s45f["notes"]} >= {
            "amendments",
            "codification",
        }
        assert [a["level"] for a in s45f["ancestors"]][:2] == ["title", "chapter"]

        # 5,697 corpus sections carry an en dash (gotcha 17) — the slice's
        # chapter 1 has plenty; make sure at least one survived to parquet.
        assert any("–" in identifier for identifier in rows)

        by_id = {}
        for row in versions.to_pylist():
            by_id.setdefault(row["identifier"], []).append(row)
        v45f = by_id["/us/usc/t16/s45f"]
        current_versions = [v for v in v45f if v["is_current"]]
        assert len(current_versions) == 1
        # §45f's text did not change between the two fixture release points,
        # so its one version lists both.
        assert set(current_versions[0]["releases"]) == FIXTURE_CORPUS_RELEASES

    # Re-running against the unchanged corpus is a no-op (the update gate).
    if fixture_corpus:
        with SessionLocal() as session:
            rerun = export(tmp_path, session=session, on_event=lambda _: None)
        assert rerun.unchanged
