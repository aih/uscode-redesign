"""A browser's 404 outside `/api` and `/app` is sent to the reader (ADR-0099).

No database: an unmatched route resolves nothing.
"""

import pytest
from fastapi.testclient import TestClient

from main import app

CHROME = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8"


@pytest.fixture(scope="module")
def client():
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def test_a_browser_is_sent_to_the_same_path_under_app(client):
    response = client.get("/about", headers={"Accept": CHROME})
    assert response.status_code == 302
    assert response.headers["location"] == "/app/about"
    assert response.headers["vary"] == "Accept"


def test_the_query_string_rides_along(client):
    response = client.get("/t16/s45f?release=119-99", headers={"Accept": CHROME})
    assert response.headers["location"] == "/app/t16/s45f?release=119-99"


@pytest.mark.parametrize("accept", ["application/json", "*/*", ""])
def test_a_program_keeps_the_json_404(client, accept):
    response = client.get("/about", headers={"Accept": accept})
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_the_api_keeps_the_json_404_for_a_browser(client):
    response = client.get("/api/v1/no-such-route", headers={"Accept": CHROME})
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_app_is_never_redirected_into_itself(client):
    """`make dev` without the proxy answers `/app` from FastAPI."""
    response = client.get("/app/about", headers={"Accept": CHROME})
    assert response.status_code == 404


def test_only_get_and_head_are_redirected(client):
    response = client.post("/about", headers={"Accept": CHROME})
    assert response.status_code in (404, 405)
    assert "location" not in response.headers
