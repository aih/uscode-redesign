"""The boundaries from CLAUDE.md, enforced instead of remembered.

Rule 1 says API and UI talk only to the `Repository`, with no raw SQL in handlers
and nothing version-resolution-related outside storage — because XCiteDB becomes a
second implementation and every leak is a place that swap would break. A rule this
easy to violate accidentally is worth a test.
"""

import ast
from pathlib import Path

from tests.conftest import REPO_ROOT

API = REPO_ROOT / "api"
WEB = REPO_ROOT / "web"
STORAGE = REPO_ROOT / "storage"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _modules(*roots: Path) -> list[Path]:
    return [p for root in roots for p in root.rglob("*.py")]


def test_api_and_web_never_import_the_models():
    """`db.models` is storage's business. The one thing `api/` may take from `db/`
    is a session factory, and only to hand it to a repository."""
    offenders = {
        path.relative_to(REPO_ROOT): sorted(
            name for name in _imports(path) if name.startswith("db.") and name != "db.base"
        )
        for path in _modules(API, WEB)
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_only_storage_writes_sql():
    """No `select(...)` outside storage and ingest — a query in a handler is
    version-resolution logic that XCiteDB would have to reimplement in the wrong
    place."""
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in _modules(API, WEB)
        if any(name.startswith("sqlalchemy") for name in _imports(path))
    ]
    assert offenders == []


def test_storage_does_not_import_the_api():
    """The dependency runs one way: api -> storage -> db."""
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in _modules(STORAGE)
        if any(name.startswith(("api", "web")) for name in _imports(path))
    ]
    assert offenders == []


def test_the_repository_protocol_and_the_postgres_implementation_agree():
    """A missing method would only surface as an AttributeError at request time."""
    from storage.postgres import PostgresRepository
    from storage.repository import Repository

    required = {
        name
        for name, value in vars(Repository).items()
        if callable(value) and not name.startswith("_")
    }

    assert required
    assert required <= set(dir(PostgresRepository))


def test_uslm_element_names_stay_out_of_extraction_code():
    """Architecture rule 2: what a section *is* is decided only by a parser.

    `quotedContent` is the canary — the element that decides what counts as a
    section (ADR-0005). If it appears in storage or in a route, extraction logic has
    escaped the ingest layer.

    `api/render.py` is the deliberate exception, and a narrow one: it maps element
    names to HTML tags, decides nothing about *what the data is*, and falls back to
    a `<div>` for names it doesn't know (see the renderer tests), so a schema change
    degrades its output rather than breaking retrieval. Presentation has to know
    element names; nothing else does.
    """
    parsers = {"ingest/uslm1.py", "ingest/uslm2.py", "ingest/base.py"}
    presentation = {"api/render.py"}
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _modules(API, WEB, STORAGE, REPO_ROOT / "ingest")
        if "quotedContent" in path.read_text()
        and str(path.relative_to(REPO_ROOT)) not in parsers | presentation
    ]
    assert offenders == []
