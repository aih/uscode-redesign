"""The interactive API docs must not reach off this origin.

`/docs` and `/redoc` were both answering 200 with an empty body, and no server
log said so. FastAPI's stock docs HTML loads Swagger UI and ReDoc from
`cdn.jsdelivr.net`; the site's CSP is `default-src 'self'` with no CDN named
(ADR-0030), so every asset was blocked and each page rendered an empty div. The
fix is to serve the bundles from here (ADR-0032), and the thing worth testing is
not "does the page return 200" — it always did — but **does the markup name any
host but this one**.

So these assertions are about URLs in the emitted HTML, which is the layer the
bug actually lived in. `tests/test_search_syntax.py` is the sibling in spirit:
both check a claim that would otherwise rot silently, because the failure mode
is a page that looks fine to the server.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import APIDOCS, STATIC, app

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = STATIC / "apidocs" / "MANIFEST.json"

#: Anything with a scheme or a protocol-relative authority in a src/href.
_EXTERNAL = re.compile(r'(?:src|href)\s*=\s*"((?:[a-z][a-z0-9+.-]*:)?//[^"]+)"', re.IGNORECASE)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_the_docs_pages_render(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_no_docs_page_loads_a_third_party_asset(client: TestClient, path: str) -> None:
    """The assertion the CSP would otherwise be making, silently, in a browser.

    A `src` or `href` carrying a scheme or a `//` authority is a request to
    another host, and `default-src 'self'` refuses it. Both pages shipped three
    such URLs each — the scripts, the stylesheet, a favicon on
    fastapi.tiangolo.com, and ReDoc's Google Fonts link.
    """
    external = _EXTERNAL.findall(client.get(path).text)
    assert not external, (
        f"{path} loads {external} from another origin; the CSP in "
        f"deploy/Caddyfile names no host but this one, so the browser will "
        f"block them and the page will render blank (ADR-0032)"
    )


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_every_asset_a_docs_page_names_is_actually_served(
    client: TestClient, path: str
) -> None:
    """A same-origin URL that 404s is the same blank page by a different route."""
    html = client.get(path).text
    assets = re.findall(r'(?:src|href)\s*=\s*"(/[^"]+)"', html)
    assert assets, f"{path} names no assets at all — has the page stopped rendering?"
    for asset in assets:
        assert client.get(asset).status_code == 200, f"{path} names {asset}, which 404s"


def test_the_vendored_bundles_are_the_ones_the_manifest_records() -> None:
    """Guards against an edited-in-place or half-downloaded bundle.

    2.4 MB of committed minified JavaScript is only defensible if anyone can
    check what it is, and this is the check: `scripts/vendor_apidocs.py --check`
    recomputes each sha256 against `MANIFEST.json`.
    """
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "vendor_apidocs.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_the_manifest_names_where_each_bundle_came_from() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["assets"], "the manifest lists no assets"
    for asset in manifest["assets"]:
        for field in ("file", "package", "version", "url", "sha256"):
            assert asset.get(field), f"{asset.get('file')} has no {field}"
        assert (STATIC / "apidocs" / asset["file"]).is_file()


def test_the_bundles_are_served(client: TestClient) -> None:
    for name in ("swagger-ui-bundle.js", "swagger-ui.css", "redoc.standalone.js"):
        response = client.get(f"{APIDOCS}/{name}")
        assert response.status_code == 200, f"{name} is not served"
        assert len(response.content) > 10_000, f"{name} came back suspiciously small"


def test_the_favicon_is_served_from_the_root(client: TestClient) -> None:
    """A browser asks for the site's icon without being told to, at the root.

    It is served here rather than from `frontend/public/` because `/favicon.svg`
    is not under `/app`, and Caddy sends everything that is not to this process.
    """
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b"USC" in response.content


def test_favicon_ico_redirects_rather_than_404s(client: TestClient) -> None:
    response = client.get("/favicon.ico", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/favicon.svg"


def test_the_favicon_is_well_formed_xml() -> None:
    """An SVG is parsed as XML, and a parse error is a blank tab, not a warning.

    The specific trap, met while writing it: an XML comment must not contain a
    double hyphen, so an em dash or a CSS custom property name inside the
    explanatory comment silently breaks the whole file.
    """
    from xml.etree import ElementTree

    ElementTree.parse(STATIC / "favicon.svg")


def test_openapi_json_still_answers(client: TestClient) -> None:
    """Turning off `docs_url` must not have taken the schema with it.

    `/app/docs` — the reference inside the site — is server-rendered from this
    document, so it would go down with it.
    """
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "uscode-redesign"
