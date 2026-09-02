"""The corpus cache (ADR-0078): the client wrapper, the through-cache, and the
contract — a change committed by ingest is visible to the next request.

The unit half runs anywhere (fakeredis, no services). The integration half
needs the loaded fixture corpus *and* migration `a3f8c2d1e6b7`; it writes to a
corpus table and asserts the very next response reflects it, which is the test
that would have caught `releasecache.ts`'s five-minute window.
"""

from __future__ import annotations

import fakeredis
import pytest
from fastapi import Response

from api.cache import GENERATION_HEADER, STATE_HEADER, ResponseDataCache
from pydantic import TypeAdapter
from storage.cache import CorpusCache, cache_key, set_cache_for_tests


@pytest.fixture()
def fake_cache():
    """A fakeredis-backed corpus cache, uninstalled afterwards so the rest of
    the suite keeps conftest's no-cache default."""
    client = fakeredis.FakeRedis()
    set_cache_for_tests(client)
    yield client
    set_cache_for_tests(None)


@pytest.fixture(autouse=True)
def no_cache_after():
    yield
    set_cache_for_tests(None)


# ---------------------------------------------------------------- cache_key


def test_cache_key_is_prefixed_and_colon_joined():
    assert cache_key("g4", "titles") == "usc:g4:titles"
    assert cache_key("g4", "toc", "/us/usc/t16/ch1", "119-99") == (
        "usc:g4:toc:/us/usc/t16/ch1:119-99"
    )


# -------------------------------------------------------------- CorpusCache


def test_a_cache_without_a_client_is_disabled_and_inert():
    cache = CorpusCache(None)
    assert not cache.enabled
    assert cache.get("usc:g1:titles") is None
    cache.set("usc:g1:titles", b"[]", 60)  # must not raise
    assert not cache.ping()


def test_set_then_get_roundtrips_bytes(fake_cache):
    cache = CorpusCache(fake_cache)
    cache.set("usc:g1:titles", b'[{"num":"16"}]', 60)
    assert cache.get("usc:g1:titles") == b'[{"num":"16"}]'
    assert cache.ping()


def test_set_is_nx_so_the_first_writer_wins(fake_cache):
    cache = CorpusCache(fake_cache)
    cache.set("usc:g1:titles", b"first", 60)
    cache.set("usc:g1:titles", b"second", 60)
    assert cache.get("usc:g1:titles") == b"first"


class _Failing:
    """A client whose every call raises — a Redis that is down."""

    calls = 0

    def get(self, key):
        type(self).calls += 1
        raise ConnectionError("boom")

    set = ping = get


def test_an_error_starts_a_cooldown_rather_than_a_retry_per_request():
    client = _Failing()
    _Failing.calls = 0
    cache = CorpusCache(client)
    assert cache.get("usc:g1:titles") is None  # pays the failure once
    assert cache.get("usc:g1:titles") is None  # inside the cooldown: no call
    cache.set("usc:g1:titles", b"x", 60)
    assert _Failing.calls == 1


# ---------------------------------------------------------- ResponseDataCache


class _Repo:
    """Just enough Repository for the dependency: a settable generation."""

    def __init__(self, generation: int = 7):
        self.generation_value = generation

    def corpus_generation(self) -> int:
        return self.generation_value


_PAYLOAD = TypeAdapter(list[str])


def test_through_computes_once_per_generation(fake_cache):
    repo = _Repo(generation=7)
    computed = []

    def compute() -> list[str]:
        computed.append(True)
        return ["a", "b"]

    first_response = Response()
    first = ResponseDataCache(repo, first_response)
    assert first.through(_PAYLOAD, "demo", ("x",), compute) == ["a", "b"]
    assert first_response.headers[GENERATION_HEADER] == "7"
    assert first_response.headers[STATE_HEADER] == "miss"

    second_response = Response()
    second = ResponseDataCache(repo, second_response)
    assert second.through(_PAYLOAD, "demo", ("x",), compute) == ["a", "b"]
    assert second_response.headers[STATE_HEADER] == "hit"
    assert len(computed) == 1


def test_a_generation_bump_orphans_every_stored_answer(fake_cache):
    repo = _Repo(generation=7)
    calls = []

    def compute() -> list[str]:
        calls.append(True)
        return ["a"]

    ResponseDataCache(repo, Response()).through(_PAYLOAD, "demo", (), compute)
    repo.generation_value = 8  # an ingest write committed
    response = Response()
    ResponseDataCache(repo, response).through(_PAYLOAD, "demo", (), compute)
    assert response.headers[STATE_HEADER] == "miss"
    assert len(calls) == 2


def test_distinct_parts_are_distinct_answers(fake_cache):
    repo = _Repo()
    cache = ResponseDataCache(repo, Response())
    assert cache.through(_PAYLOAD, "demo", ("16",), lambda: ["t16"]) == ["t16"]
    assert cache.through(_PAYLOAD, "demo", ("42",), lambda: ["t42"]) == ["t42"]


def test_a_compute_that_raises_stores_nothing(fake_cache):
    repo = _Repo()

    def compute() -> list[str]:
        raise ValueError("no section")

    with pytest.raises(ValueError):
        ResponseDataCache(repo, Response()).through(_PAYLOAD, "demo", (), compute)
    healed = ResponseDataCache(repo, Response()).through(
        _PAYLOAD, "demo", (), lambda: ["found"]
    )
    assert healed == ["found"]


def test_without_redis_the_header_still_carries_the_generation():
    """R1 stands alone: the generation header is a fact about the corpus, not
    about the cache, so the reader's memo works with Redis off."""
    repo = _Repo(generation=3)
    computed = []
    response = Response()
    cache = ResponseDataCache(repo, response)

    def compute() -> list[str]:
        computed.append(True)
        return []

    cache.through(_PAYLOAD, "demo", (), compute)
    cache.through(_PAYLOAD, "demo", (), compute)
    assert response.headers[GENERATION_HEADER] == "3"
    assert STATE_HEADER not in response.headers
    assert len(computed) == 2


def test_the_generation_is_read_once_per_request():
    reads = []

    class CountingRepo:
        def corpus_generation(self) -> int:
            reads.append(True)
            return 5

    cache = ResponseDataCache(CountingRepo(), Response())
    assert cache.generation == 5
    assert cache.generation == 5
    assert len(reads) == 1


# -------------------------------------------------------------------- /health


def test_health_reports_the_cache_without_failing_on_it():
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["redis"] == "disabled"  # conftest clears REDIS_URL


# ---------------------------------------------------- the contract, end to end


@pytest.fixture()
def corpus_state(loaded_database):
    """Skip when migration a3f8c2d1e6b7 has not been applied to the dev DB —
    and fail in CI, where `make ci-data` runs `alembic upgrade head` and a
    missing table means the contract tests silently stopped running."""
    import os

    from sqlalchemy import text

    from db.base import SessionLocal

    with SessionLocal() as session:
        try:
            session.execute(text("SELECT generation FROM corpus_state")).scalar()
        except Exception:
            reason = "corpus_state missing — run `uv run alembic upgrade head`"
            if os.environ.get("USC_REQUIRE_INTEGRATION"):
                pytest.fail(f"USC_REQUIRE_INTEGRATION is set but {reason}", pytrace=False)
            pytest.skip(reason)


def _bump_by_touching_a_release_point() -> None:
    """One committed corpus write, restored in the same transaction it isn't:
    two updates in two transactions, so the trigger fires twice and the data
    ends where it started."""
    from sqlalchemy import text

    from db.base import SessionLocal

    with SessionLocal() as session:
        session.execute(
            text("UPDATE release_points SET seq = seq WHERE label = '119-99'")
        )
        session.commit()


def test_an_ingest_commit_is_visible_to_the_next_request(client, corpus_state, fake_cache):
    """The contract itself, on the reader's own TOC route: warm the cache,
    change what the corpus says in a second connection, and the very next
    request must show the change — no window."""
    from sqlalchemy import text

    from db.base import SessionLocal

    url = "/api/v1/us/usc/t16/ch1"
    warm = client.get(url)
    assert warm.status_code == 200
    assert warm.headers[STATE_HEADER] == "miss"
    original = warm.json()["node"]["heading"]

    hit = client.get(url)
    assert hit.headers[STATE_HEADER] == "hit"
    assert hit.headers[GENERATION_HEADER] == warm.headers[GENERATION_HEADER]

    changed = f"{original} (AMENDED)"
    try:
        with SessionLocal() as session:
            session.execute(
                text("UPDATE structure_nodes SET heading = :h WHERE identifier = :i"),
                {"h": changed, "i": "/us/usc/t16/ch1"},
            )
            session.commit()

        after = client.get(url)
        assert after.headers[STATE_HEADER] == "miss"
        assert int(after.headers[GENERATION_HEADER]) > int(
            warm.headers[GENERATION_HEADER]
        )
        assert after.json()["node"]["heading"] == changed
    finally:
        with SessionLocal() as session:
            session.execute(
                text("UPDATE structure_nodes SET heading = :h WHERE identifier = :i"),
                {"h": original, "i": "/us/usc/t16/ch1"},
            )
            session.commit()


def test_every_corpus_table_write_moves_the_generation(client, corpus_state, fake_cache):
    """A no-op UPDATE on `release_points` still fires the statement trigger, so
    the generation moves and the cached `/titles` answer is orphaned."""
    warm = client.get("/api/v1/titles")
    assert warm.headers[STATE_HEADER] == "miss"
    assert client.get("/api/v1/titles").headers[STATE_HEADER] == "hit"

    _bump_by_touching_a_release_point()

    after = client.get("/api/v1/titles")
    assert after.headers[STATE_HEADER] == "miss"
    assert int(after.headers[GENERATION_HEADER]) > int(warm.headers[GENERATION_HEADER])
    assert after.json() == warm.json()  # nothing actually changed


def test_the_section_response_carries_the_generation(client, corpus_state):
    response = client.get("/api/v1/us/usc/t16/s45f")
    assert response.status_code == 200
    assert int(response.headers[GENERATION_HEADER]) >= 1
    # The section itself is never served from Redis: its ETag and Cache-Control
    # are the origin's own, computed on this request (ADR-0018).
    assert STATE_HEADER not in response.headers
