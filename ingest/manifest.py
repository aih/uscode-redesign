"""Provenance manifests (CLAUDE.md documentation duty 4 / PLAN §11.4).

Every ingest writes `data/manifests/{release}.json` so the load can be
independently re-checked: re-download the source, recompute its sha256, and
compare counts. One manifest per release; each title ingested into that
release adds (or replaces) its own entry, so loading titles one at a time
still ends with a single file per release.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ingest.load import LoadStats

MANIFEST_DIR = Path("data/manifests")


def write_manifest(
    release_label: str,
    xml_path: Path,
    stats: LoadStats,
    *,
    source_url: str | None = None,
    manifest_dir: Path = MANIFEST_DIR,
) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{release_label}.json"

    manifest: dict[str, object] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    manifest["release"] = release_label
    if source_url is not None or "source_url" not in manifest:
        manifest["source_url"] = source_url

    titles = manifest.setdefault("titles", {})
    assert isinstance(titles, dict)
    titles[stats.title_num] = {
        "source_path": str(xml_path),
        "sha256": _sha256_file(xml_path),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": stats.schema_version,
        "raw_section_elements": stats.raw_section_elements,
        "sections_ingested": stats.sections_ingested,
        "new_section_versions": stats.new_section_versions,
        "deduped_section_versions": stats.deduped_section_versions,
        "status_counts": stats.status_counts,
    }

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
