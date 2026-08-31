"""Where `docs/verification/` is and how a JSON artifact is written to it.

Documentation duty 5: a reliability claim is a re-runnable command whose output
is committed. Two ingest jobs write such artifacts — the classification parse
(one per source document) and the version-change classifier — and they had a
directory constant and a write ritual each, which had already drifted apart on
`sort_keys`.

The directory is anchored on the repository root rather than the process's
working directory: a run from a subdirectory used to write a second
`docs/verification/` wherever it happened to start, and the artifact is a
committed file with one home.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

VERIFICATION_DIR = REPO_ROOT / "docs" / "verification"
"""The committed artifact directory. `--out` overrides it per run."""


def write_verification_json(
    document: dict[str, Any], name: str, directory: Path = VERIFICATION_DIR
) -> Path:
    """Write `document` to `directory/name`, creating the directory.

    Keys sorted and two-space indented, with a trailing newline, so a diff
    between two runs is a diff between two measurements rather than between two
    dict orderings.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return path


__all__ = ["REPO_ROOT", "VERIFICATION_DIR", "write_verification_json"]
