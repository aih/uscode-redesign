"""The token bucket, and the routes it is attached to (ADR-0029).

Two halves, deliberately. The bucket's arithmetic is a unit test — it owns a
clock, so it can be tested at any speed without sleeping. The wiring is an
integration test that only asserts *that* a route is limited and answers 429
with `Retry-After`, never at what number: the budgets are tuning, and a test
that pinned them would fail every time someone re-tuned rather than every time
someone removed a limit.

`tests/conftest.py` empties every bucket between tests, so this is the one
module where the limits are asserted rather than got out of the way of.
"""

import typing

import pytest

from api.routes import labels as labels_route
from params import RateLimiter


# ------------------------------------------------------------ the bucket


def test_a_full_bucket_admits_its_whole_capacity_then_refuses():
    limiter = RateLimiter(name="t", capacity=3, per_second=1.0)

    assert [limiter.check("a") for _ in range(3)] == [None, None, None]
    assert limiter.check("a") is not None


def test_retry_after_is_at_least_a_second_so_a_client_that_obeys_it_succeeds():
    """Returning a fraction of a second would send an obedient client back for
    a second 429, which teaches it to ignore the header."""
    limiter = RateLimiter(name="t", capacity=1, per_second=100.0)
    limiter.check("a")

    assert limiter.check("a") >= 1.0


def test_each_address_gets_its_own_bucket():
    limiter = RateLimiter(name="t", capacity=1, per_second=1.0)

    assert limiter.check("a") is None
    assert limiter.check("b") is None  # b is not charged for a's request
    assert limiter.check("a") is not None


def test_tokens_refill_at_the_stated_rate(monkeypatch):
    """The sustained limit is `per_second`, and the only way to see that without
    sleeping is to own the clock."""
    now = [1000.0]
    monkeypatch.setattr("params.time.monotonic", lambda: now[0])

    limiter = RateLimiter(name="t", capacity=2, per_second=2.0)
    assert limiter.check("a") is None
    assert limiter.check("a") is None
    assert limiter.check("a") is not None

    now[0] += 0.5  # one token's worth
    assert limiter.check("a") is None
    assert limiter.check("a") is not None


def test_refill_never_exceeds_capacity(monkeypatch):
    """A bucket idle for a week must not grant a week's worth of burst."""
    now = [1000.0]
    monkeypatch.setattr("params.time.monotonic", lambda: now[0])

    limiter = RateLimiter(name="t", capacity=2, per_second=1.0)
    limiter.check("a")
    now[0] += 604800

    assert [limiter.check("a") for _ in range(3)] == [None, None, pytest.approx(1.0)]


def test_refilled_buckets_are_swept_so_the_table_stays_bounded(monkeypatch):
    """The key is an address, so the table is unbounded unless something forgets.
    A bucket that has refilled holds no information and is safe to drop."""
    now = [1000.0]
    monkeypatch.setattr("params.time.monotonic", lambda: now[0])

    limiter = RateLimiter(name="t", capacity=1, per_second=1.0)
    for i in range(50):
        limiter.check(f"10.0.0.{i}")
    assert len(limiter._buckets) == 50

    now[0] += RateLimiter.SWEEP_INTERVAL + 1
    limiter.check("10.0.0.0")

    assert len(limiter._buckets) == 1


def test_a_request_with_no_client_still_gets_a_key():
    """An ASGI transport with no peer — which is what a test client is — must
    not crash the limiter, and must not be exempt from it either."""
    from params import client_key

    class _NoClient:
        client = None

    assert client_key(_NoClient()) == "-"


# ------------------------------------------------------------- the wiring


@pytest.mark.integration
def test_the_diff_route_sheds_load_with_429_and_retry_after(client):
    """The route this work exists for. `api/diff.py` sets `Diff_Timeout = 0`,
    deliberately removing diff-match-patch's only runtime bound, and the load
    test measured ~0.45 rps failing entirely past ~10 concurrent
    (`docs/verification/loadtest.json`). Shedding beats collapsing.
    """
    url = (
        "/api/v1/sections/us/usc/t16/s45f/diff"
        "?from=119-99&to=119-102not101"
    )

    statuses = [client.get(url).status_code for _ in range(40)]

    assert 429 in statuses, "the diff route is not rate limited"
    throttled = next(
        response
        for response in (client.get(url) for _ in range(3))
        if response.status_code == 429
    )
    assert int(throttled.headers["retry-after"]) >= 1
    # The error surface is the same one the login throttle established.
    assert "detail" in throttled.json()


@pytest.mark.integration
def test_the_labels_route_bounds_how_many_identifiers_one_call_may_ask_for():
    """The list fans into one `IN (...)`, so an unbounded list is an unbounded
    query. Asserted without a database: it is a validation error, not a lookup.
    """
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as unloaded:
        query = "&".join(f"identifier=/us/usc/t16/s{i}" for i in range(101))
        assert unloaded.get(f"/api/v1/labels?{query}").status_code == 422


def test_the_reader_batches_to_exactly_the_bound_this_route_enforces():
    """The bound above is only safe because its one caller respects it.

    The reader asked for a whole page's citations in a single request until a
    section with 242 of them (3 U.S.C. § 301) turned this 422 into a 500 on a
    page whose text the reader already had. It now batches — and the batch size
    and the bound are the same number written in two languages, which is
    exactly the pair that drifts silently: raising `max_length` here costs
    nothing visible, and lowering it puts the 500 back.

    Read as text rather than imported, for the reason `test_search_syntax.py`
    gives: a Node build step in the Python suite to check one integer would
    cost more than it is worth, and the regex fails loudly if the file's shape
    changes rather than quietly matching nothing.
    """
    import re
    from pathlib import Path

    api_ts = Path(__file__).resolve().parent.parent / "frontend/src/lib/api.ts"
    found = re.search(
        r"^export const LABELS_PER_REQUEST = (\d+);", api_ts.read_text(encoding="utf-8"), re.M
    )
    assert found, "LABELS_PER_REQUEST is not declared where this test looks for it"

    # `include_extras` keeps the `Query(...)` in the `Annotated`, which is where
    # the bound lives; `api/routes.py` postpones its annotations, so the
    # signature alone would give back the string "Annotated[list[str], Query…]".
    hints = typing.get_type_hints(labels_route, include_extras=True)
    query = hints["identifier"].__metadata__[0]
    # Pydantic keeps it as an `annotated_types.MaxLen` in `Query.metadata`,
    # not as an attribute of the `Query` itself.
    bound = next(m.max_length for m in query.metadata if hasattr(m, "max_length"))
    assert int(found.group(1)) == bound == 100


@pytest.mark.integration
def test_the_search_route_bounds_deep_paging():
    """Past OpenSearch's `max_result_window` a deep `offset` both throws and
    pressures the heap — from a query string, with no cluster of ours involved
    in deciding it."""
    from fastapi.testclient import TestClient

    from main import app
    from api.search import MAX_OFFSET

    with TestClient(app) as unloaded:
        response = unloaded.get(f"/api/v1/search?q=conservation&offset={MAX_OFFSET + 1}")
        assert response.status_code == 422
