"""Shared fixture paths, and the API test client.

`SLICE` is what the default test run parses (878 KB, ~20 ms). The full-corpus
samples belong to `@pytest.mark.slow` tests only — CLAUDE.md test speed rule.

The `client` fixture needs a Postgres with Title 16 ingested at both release
points. It skips rather than fails when there isn't one, so `make test` is still
green on a fresh clone — but it is the API's real contract test, and CI must run
it against a loaded database (`docker compose up -d db && make dev-data`).
"""

import os
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


REQUIRED_RELEASES = {"119-99", "119-102not101"}


def _unavailable(reason: str) -> None:
    """Skip locally, fail loudly where the suite is *supposed* to be complete.

    A skip is right on a fresh clone with no Postgres. It is exactly wrong in
    CI: a misconfigured database would turn the API's real contract tests into
    silent no-ops and the run would still go green. `USC_REQUIRE_INTEGRATION=1`
    is CI saying "these must actually run" — so there, absence is a failure.
    """
    if os.environ.get("USC_REQUIRE_INTEGRATION"):
        pytest.fail(f"USC_REQUIRE_INTEGRATION is set but {reason}", pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def loaded_database() -> None:
    """Skip the integration suite unless Title 16 is loaded at both release points."""
    try:
        from sqlalchemy import select

        from db.base import SessionLocal
        from db.models import ReleasePoint, Title, TitleVersion

        with SessionLocal() as session:
            labels = set(
                session.scalars(
                    select(ReleasePoint.label)
                    .join(TitleVersion, TitleVersion.release_id == ReleasePoint.id)
                    .join(Title, Title.id == TitleVersion.title_id)
                    .where(Title.num == "16")
                )
            )
    except Exception as exc:  # pragma: no cover - environment-dependent
        _unavailable(f"no database: {exc}")

    missing = REQUIRED_RELEASES - labels
    if missing:  # pragma: no cover - environment-dependent
        _unavailable(
            "Title 16 is not loaded at "
            + ", ".join(sorted(missing))
            + " — run `make dev-data`"
        )


@pytest.fixture(scope="session")
def client(loaded_database):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def fresh_client(loaded_database):
    """A `TestClient` of its own, function-scoped — auth tests set cookies, and
    the session-scoped `client` fixture is shared with every other test module,
    so logging in on it would leak a session into unrelated tests."""
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client
