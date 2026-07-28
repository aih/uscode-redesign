import json
from pathlib import Path

from ingest.load import LoadStats
from ingest.manifest import write_manifest


def _stats(title_num: str, **overrides) -> LoadStats:
    defaults = dict(
        release_label="119-102not101",
        title_num=title_num,
        schema_version="uslm-1.0.15",
        raw_section_elements=167,
        sections_ingested=158,
        new_section_versions=158,
        deduped_section_versions=0,
        status_counts={"repealed": 111, "omitted": 2, "transferred": 7},
    )
    defaults.update(overrides)
    return LoadStats(**defaults)


def test_write_manifest_creates_file_with_counts(tmp_path: Path):
    xml_path = tmp_path / "usc16.xml"
    xml_path.write_text("<uscDoc/>")

    manifest_path = write_manifest(
        "119-102not101",
        xml_path,
        _stats("16"),
        source_url="https://uscode.house.gov/download/.../xml_usc16@119-102not101.zip",
        manifest_dir=tmp_path / "manifests",
    )

    data = json.loads(manifest_path.read_text())
    assert data["release"] == "119-102not101"
    assert data["source_url"].endswith("xml_usc16@119-102not101.zip")
    assert data["titles"]["16"]["raw_section_elements"] == 167
    assert data["titles"]["16"]["sections_ingested"] == 158
    assert data["titles"]["16"]["status_counts"] == {
        "repealed": 111,
        "omitted": 2,
        "transferred": 7,
    }


def test_write_manifest_accumulates_titles_across_calls(tmp_path: Path):
    manifest_dir = tmp_path / "manifests"
    xml16 = tmp_path / "usc16.xml"
    xml16.write_text("<uscDoc/>")
    xml17 = tmp_path / "usc17.xml"
    xml17.write_text("<uscDoc/>")

    write_manifest("119-102not101", xml16, _stats("16"), manifest_dir=manifest_dir)
    manifest_path = write_manifest(
        "119-102not101", xml17, _stats("17", raw_section_elements=10, sections_ingested=10),
        manifest_dir=manifest_dir,
    )

    data = json.loads(manifest_path.read_text())
    assert set(data["titles"]) == {"16", "17"}
