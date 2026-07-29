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
STORAGE = REPO_ROOT / "storage"
SHARED = [REPO_ROOT / "main.py", REPO_ROOT / "citation.py", REPO_ROOT / "params.py"]


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
    return [
        path
        for root in roots
        for path in ([root] if root.is_file() else list(root.rglob("*.py")))
    ]


def test_the_api_never_imports_the_models():
    """`db.models` is storage's business. The one thing `api/` may take from `db/`
    is a session factory, and only to hand it to a repository."""
    offenders = {
        path.relative_to(REPO_ROOT): sorted(
            name for name in _imports(path) if name.startswith("db.") and name != "db.base"
        )
        for path in _modules(API, *SHARED)
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_only_storage_writes_sql():
    """No `select(...)` outside storage and ingest — a query in a handler is
    version-resolution logic that XCiteDB would have to reimplement in the wrong
    place."""
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in _modules(API, *SHARED)
        if any(name.startswith("sqlalchemy") for name in _imports(path))
    ]
    assert offenders == []


def test_no_python_module_renders_html():
    """ADR-0010, and since Session 7 the strongest form of it: this process has
    no template engine at all.

    The rule is stated directly rather than transitively — not "no Jinja reaches
    the request path" but "nothing imports it" — because the failure it prevents
    is a gradual one: one HTML error page, then one template import, and the
    surface that was supposed to be swappable for a static export is carrying a
    rendering stack again. The reader is an Astro app in `frontend/` (ADR-0011);
    HTML is its job and nothing else's.
    """
    offenders = {
        path.relative_to(REPO_ROOT): sorted(
            name
            for name in _imports(path)
            if name.split(".")[0] in {"jinja2", "web", "starlette.templating"}
        )
        for path in _modules(API, STORAGE, *SHARED)
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_storage_does_not_import_the_api():
    """The dependency runs one way: api -> storage -> db."""
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in _modules(STORAGE)
        if any(name.startswith(("api", "citation", "params")) for name in _imports(path))
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


def test_the_accounts_protocol_and_the_postgres_implementation_agree():
    """Same check as above, for the second storage module (docs/adr/0017):
    users/sessions/watchlists are not version-resolution logic, so they get
    their own protocol rather than new methods on `Repository` — but a missing
    method here is exactly as invisible until request time."""
    from storage.accounts import AccountsRepository
    from storage.postgres_accounts import PostgresAccounts

    required = {
        name
        for name, value in vars(AccountsRepository).items()
        if callable(value) and not name.startswith("_")
    }

    assert required
    assert required <= set(dir(PostgresAccounts))


def test_uslm_element_names_stay_out_of_extraction_code():
    """Architecture rule 2: what a section *is* is decided only by a parser.

    `quotedContent` is the canary — the element that decides what counts as a
    section (ADR-0005). If it appears in storage or in a route, extraction logic has
    escaped the ingest layer.

    There is no longer an exception. `web/uslm_html.py` used to be one — narrow,
    and justified, because presentation has to know element names — but the
    renderer now lives in TypeScript in `frontend/src/lib/uslm.ts` (ADR-0011). No
    Python file outside the parsers knows a USLM element name at all.
    """
    parsers = {"ingest/uslm1.py", "ingest/uslm2.py", "ingest/base.py"}
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _modules(API, STORAGE, REPO_ROOT / "ingest", *SHARED)
        if "quotedContent" in path.read_text()
        and str(path.relative_to(REPO_ROOT)) not in parsers
    ]
    assert offenders == []
