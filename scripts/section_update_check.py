"""Assemble Title 16 at 119-102not101 from the classification tables and compare
it with the release point's own file (ADR-0095).

In a scratch database: the release-point inventory from the committed fixture,
Title 16 at 119-99 from its committed zip, and the classification slices `make
ci-classification-data` loads. Then `python -m ingest sections-update` for
119-102not101, reading the sections it plans out of `samples/uslm1/usc16.xml`
(the 119-102not101 file) and nothing else of it. Every section of that file is
then compared, by the guid-stripped content hash the loader dedupes on
(ADR-0007), with the version the assembled release point maps it to.

Writes `docs/verification/section-update-check.json`. Needs a Postgres the
`DATABASE_URL` user can create a database on; no network.

    uv run python scripts/section_update_check.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, select, text

from db.config import settings
from ingest.parser import parser_for
from ingest.verification import VERIFICATION_DIR, write_verification_json

BASE_LABEL = "119-99"
TARGET_LABEL = "119-102not101"
BASE_ZIP = REPO_ROOT / "samples" / "uslm1" / "xml_usc16@119-99.zip"
TARGET_XML = REPO_ROOT / "samples" / "uslm1" / "usc16.xml"
CLASSIFICATION_FILES = {
    "tables_slice.shtml": "tables.html",
    "priortables_slice.shtml": "priortables.html",
    "tbl119pl_2nd_slice.htm": "tbl119pl_2nd.htm",
    "tbl118pl_2nd_slice.htm": "tbl118pl_2nd.htm",
    "tbl110pl_1st_slice.htm": "tbl110pl_1st.htm",
    "tbl104pl_slice.htm": "tbl104pl.htm",
    "ecct.html": "ecct.html",
}
SCRATCH_DB = f"uscode_section_update_check_{os.getpid()}"


def _run(url: str, *args: str) -> str:
    env = dict(os.environ, DATABASE_URL=url, DISABLE_SEARCH_SYNC="1")
    result = subprocess.run(
        [sys.executable, *args], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise SystemExit(f"{' '.join(args)} exited {result.returncode}:\n{result.stderr}")
    return result.stdout


def _content_hashes(path: Path) -> Counter:
    return Counter(
        (record.identifier, hashlib.sha256(record.content_key.encode()).digest())
        for record in parser_for(path).iter_sections(path)
    )


def main() -> int:
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    url = settings.database_url.rsplit("/", 1)[0] + f"/{SCRATCH_DB}"
    work = Path(tempfile.mkdtemp(prefix="section-update-check-"))
    # `ingest load` writes the release point's provenance manifest; the
    # committed one describes the real load and is put back afterwards.
    manifest = REPO_ROOT / "data" / "manifests" / f"{BASE_LABEL}.json"
    manifest_bytes = manifest.read_bytes() if manifest.exists() else None
    try:
        _run(url, "-m", "alembic", "upgrade", "head")
        _run(url, "-m", "ingest", "inventory", "--from-file", "tests/fixtures/releasepoints.json")
        with zipfile.ZipFile(BASE_ZIP) as archive:
            archive.extractall(work / "base")
        _run(
            url, "-m", "ingest", "load", str(work / "base" / "usc16.xml"),
            "--release", BASE_LABEL, "--source-zip", str(BASE_ZIP),
        )
        tables = work / "classification"
        tables.mkdir()
        for fixture, name in CLASSIFICATION_FILES.items():
            shutil.copy(REPO_ROOT / "tests" / "fixtures" / fixture, tables / name)
        _run(
            url, "-m", "ingest", "classification", "--force", "--from-file", str(tables),
            "--out", str(work / "verification"), "--manifest", str(work / "manifest.json"),
        )

        started = time.monotonic()
        _run(
            url, "-m", "ingest", "sections-update", "--release", TARGET_LABEL,
            "--title", "16", "--title-file", str(TARGET_XML),
            "--report", str(work), "--quiet",
        )
        elapsed = time.monotonic() - started
        update = json.loads((work / f"section-update-{TARGET_LABEL}.json").read_text())

        engine = create_engine(url)
        from db.models import ReleasePoint, Section, SectionReleaseMap, SectionVersion

        with engine.connect() as conn:
            assembled = Counter(
                (identifier, bytes(content_hash))
                for identifier, content_hash in conn.execute(
                    select(Section.identifier, SectionVersion.content_hash)
                    .join(SectionVersion, SectionVersion.section_id == Section.id)
                    .join(SectionReleaseMap, SectionReleaseMap.section_version_id == SectionVersion.id)
                    .join(ReleasePoint, ReleasePoint.id == SectionReleaseMap.release_id)
                    .where(ReleasePoint.label == TARGET_LABEL)
                )
            )
        engine.dispose()

        expected = _content_hashes(TARGET_XML)
        base = _content_hashes(work / "base" / "usc16.xml")
        differ_from_base = sorted(
            {i for i, _h in expected} - {i for i, _h in (expected & base)}
        )
        mismatched = sorted({i for i, _h in (expected - assembled) + (assembled - expected)})
        planned = sorted(update["titles"][0]["sections"]) if update["titles"] else []
        report = {
            "base": BASE_LABEL,
            "release": TARGET_LABEL,
            "window_laws": update["window_laws"],
            "uncovered_laws": update["uncovered_laws"],
            "laws_without_rows": update["laws_without_rows"],
            "sections_planned": planned,
            "sections_in_file": sum(expected.values()),
            "sections_assembled": sum(assembled.values()),
            "sections_whose_text_differs_from_base": differ_from_base,
            "sections_mismatched": mismatched,
            "reproduced": not mismatched,
            "update_seconds": round(elapsed, 1),
            "results": update["results"],
            "command": "uv run python scripts/section_update_check.py",
        }
        path = write_verification_json(report, "section-update-check.json", VERIFICATION_DIR)
        print(
            f"{report['sections_assembled']:,} sections assembled from "
            f"{len(planned)} fetched; {len(mismatched)} differ from the file "
            f"({', '.join(mismatched) or 'none'}) -> {path}"
        )
        return 0 if not mismatched else 1
    finally:
        if manifest_bytes is not None:
            manifest.write_bytes(manifest_bytes)
        shutil.rmtree(work, ignore_errors=True)
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
