"""Shared fixture paths.

`SLICE` is what the default test run parses (878 KB, ~20 ms). The full-corpus
samples belong to `@pytest.mark.slow` tests only — CLAUDE.md test speed rule.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"

SLICE = FIXTURES / "usc16_slice.xml"
USLM1_USC16 = REPO_ROOT / "samples" / "uslm1" / "usc16.xml"
USLM2_DIR = REPO_ROOT / "samples" / "uslm2" / "USLM2"
USLM2_USC01 = USLM2_DIR / "usc01.xml"
USLM2_USC16 = USLM2_DIR / "usc16.xml"
USLM2_USC49 = USLM2_DIR / "usc49.xml"


def require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"sample not present: {path}")
    return path


@pytest.fixture(scope="session")
def slice_path() -> Path:
    return require(SLICE)


@pytest.fixture(scope="session")
def uslm2_usc01() -> Path:
    return require(USLM2_USC01)
