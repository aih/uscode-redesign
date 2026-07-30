"""Search endpoint contract (ADR-0022).

These run without OpenSearch and without Postgres: the search client is mocked
and the Repository is overridden, so what is under test is the *query* the
handler builds and the shape it returns — which is where the versioning rule
lives.
"""

import datetime

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from main import app
from storage import get_repository
from storage.repository import ReleaseRef, ResolvedRelease

# The identifier the index actually holds is the full USLM `@identifier` — a
# path, not a fragment. A fixture using "t16/s1" is what let the reader ship a
# link of `/us/usc/${identifier}` producing `/us/usc//us/usc/t16/s1`.
IDENTIFIER = "/us/usc/t16/s1"

NEWEST = ReleaseRef(
    label="119-102not101",
    currency_date=datetime.date(2026, 7, 12),
    seq=381,
    congress=119,
    law_num=102,
)
OLDER = ReleaseRef(
    label="119-99",
    currency_date=datetime.date(2026, 5, 8),
    seq=379,
    congress=119,
    law_num=99,
)


def _hit(**source):
    base = {
        "identifier": IDENTIFIER,
        "heading": "National Park Service",
        "num": "§ 1.",
        "first_release_label": "119-99",
        "first_release_seq": 379,
        "is_current": True,
    }
    base.update(source)
    return {
        "_index": "uscode_sections",
        "_source": base,
        "highlight": {"heading": ["<em>National</em> Park Service"]},
    }


def _response(hits):
    return {"hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": hits}}


class FakeRepository:
    """Only the one method the search handler is allowed to reach for."""

    def __init__(self):
        self.asked = []

    def resolve_release(self, *, label=None, on_date=None, title_num=None):
        self.asked.append((label, on_date))
        release = OLDER if label == OLDER.label else NEWEST
        return ResolvedRelease(release=release, requested_label=label)


@pytest.fixture
def repository():
    fake = FakeRepository()
    app.dependency_overrides[get_repository] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_repository, None)


@pytest.fixture
def client(repository):
    return TestClient(app)


@pytest.fixture
def search_client():
    with patch("api.search.get_search_client") as factory:
        os_client = MagicMock()
        os_client.search.return_value = _response([_hit()])
        factory.return_value = os_client
        yield os_client


def _body(search_client):
    return search_client.search.call_args.kwargs["body"]


def test_search_returns_full_identifiers(client, search_client):
    response = client.get("/api/v1/search?q=National")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    result = data["results"][0]
    assert result["identifier"] == IDENTIFIER
    assert result["identifier"].startswith("/us/usc/")
    assert result["heading"] == "National Park Service"
    assert result["type"] == "section"
    assert result["first_release"] == "119-99"
    assert result["snippets"] == [
        {"field": "heading", "text": "<em>National</em> Park Service"}
    ]


def test_search_defaults_to_the_text_in_force(client, search_client, repository):
    client.get("/api/v1/search?q=National")

    filters = _body(search_client)["query"]["bool"]["filter"]
    assert {"term": {"is_current": True}} in filters
    # No release was asked for, so none should have been resolved.
    assert repository.asked == []
    assert "collapse" not in _body(search_client)


def test_search_at_a_release_filters_on_seq_not_row_id(client, search_client, repository):
    response = client.get("/api/v1/search?q=National&release=119-99")
    assert response.status_code == 200

    body = _body(search_client)
    filters = body["query"]["bool"]["filter"]
    assert {"range": {"first_release_seq": {"lte": OLDER.seq}}} in filters
    assert {"term": {"is_current": True}} not in filters
    # Newest text at or before the release asked for — one document per section.
    assert body["collapse"]["field"] == "identifier"
    assert repository.asked == [("119-99", None)]
    assert response.json()["release"] == "119-99"


def test_search_by_date_resolves_through_the_repository(client, search_client, repository):
    response = client.get("/api/v1/search?q=National&date=2026-07-12")
    assert response.status_code == 200
    assert repository.asked == [(None, datetime.date(2026, 7, 12))]
    assert response.json()["release"] == NEWEST.label


def test_a_collapsed_hit_reports_the_version_in_force_at_that_release(
    client, search_client
):
    """Under collapse the outer hit is the best-scoring version; the one actually
    in force is the inner hit, and that is what the result must describe."""
    outer = _hit(first_release_label="119-99", is_current=False)
    outer["inner_hits"] = {
        "at_release": {
            "hits": {
                "hits": [
                    {
                        "_index": "uscode_sections",
                        "_source": {
                            "identifier": IDENTIFIER,
                            "heading": "National Park Service",
                            "first_release_label": "118-1",
                            "is_current": False,
                        },
                        "highlight": {"heading": ["<em>National</em>"]},
                    }
                ]
            }
        }
    }
    search_client.search.return_value = _response([outer])

    result = client.get("/api/v1/search?q=National&release=119-99").json()["results"][0]
    assert result["first_release"] == "118-1"
    assert result["is_current"] is False


def test_structure_hits_are_typed_as_structure(client, search_client):
    hit = {
        "_index": "uscode_structure",
        "_source": {"identifier": "/us/usc/t16/ch1", "num_value": "1", "level": "chapter"},
        "highlight": {},
    }
    search_client.search.return_value = _response([hit])

    result = client.get("/api/v1/search?q=chapter").json()["results"][0]
    assert result["type"] == "structure"
    assert result["level"] == "chapter"
    assert result["num"] == "1"


def test_an_unreachable_cluster_is_503_not_500(client, search_client):
    search_client.search.side_effect = RuntimeError("connection refused")
    response = client.get("/api/v1/search?q=National")
    assert response.status_code == 503
