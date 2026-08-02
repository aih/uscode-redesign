"""When did this mirror last ask uscode.house.gov what exists?

The unit tests here are about the staleness rule; the integration ones prove
that a poll writes a `source_checks` row on both paths — the one where the page
came back and the one where it didn't. That second case is the whole point of
the table: a corpus that has stopped being checked looks exactly like a corpus
with nothing to check, and only the record of the *attempt* tells them apart.

Nothing here touches the network — `fetch_inventory_html` is monkeypatched — and
nothing here seeds release points. Seeding renumbers `release_points.seq` across
the whole table, which would corrupt the loaded fixture corpus every other
integration test reads from, so these poll with `seed=False` and roll back.
"""

import datetime

import pytest

from ingest import inventory as inventory_mod
from storage.repository import SOURCE_CHECK_STALE_AFTER, SourceCheckInfo

NOW = datetime.datetime(2026, 8, 2, 12, 0, tzinfo=datetime.timezone.utc)


def _check(**overrides) -> SourceCheckInfo:
    defaults = dict(
        checked_at=NOW,
        source_url=inventory_mod.PRIOR_RELEASE_POINTS_URL,
        ok=True,
        release_points_seen=382,
        new_labels=(),
        latest_label="119-102not101",
        latest_currency_date=datetime.date(2026, 7, 12),
        error=None,
    )
    return SourceCheckInfo(**{**defaults, **overrides})


# ----------------------------------------------------------------- staleness


def test_a_fresh_successful_check_is_not_stale():
    assert not _check().is_stale(now=NOW + datetime.timedelta(hours=6))


def test_a_check_older_than_a_week_is_stale():
    """The cadence is daily; a week without one means the checker stopped."""
    just_inside = NOW + SOURCE_CHECK_STALE_AFTER
    assert not _check().is_stale(now=just_inside)
    assert _check().is_stale(now=just_inside + datetime.timedelta(seconds=1))


def test_a_failed_check_is_stale_immediately():
    """It confirmed nothing, so its timestamp is not evidence of currency."""
    failed = _check(ok=False, error="URLError: timed out")
    assert failed.is_stale(now=NOW + datetime.timedelta(minutes=1))


def test_age_tolerates_a_naive_timestamp():
    """Postgres returns aware datetimes; a fixture or another store may not, and
    subtracting a naive from an aware one raises rather than being wrong."""
    naive = _check(checked_at=NOW.replace(tzinfo=None))
    assert naive.age(now=NOW + datetime.timedelta(hours=1)) == datetime.timedelta(hours=1)


# --------------------------------------------------------------- the poll itself

pytestmark_integration = pytest.mark.integration


@pytest.fixture()
def session(loaded_database):
    from db.base import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        # Everything these tests write is rolled back — the fixture corpus is
        # shared with every other integration test in the run.
        session.rollback()
        session.close()


def _fake_page(label: str = "999-1") -> str:
    return (
        '<li class="releasepoint"><a class="releasepoint" '
        f'href="releasepoints/us/pl/999/1/usc-rp@{label}.htm">'
        "Public Law 999-1 (01/02/2099), affecting title 16</a></li>"
    )


@pytest.mark.integration
def test_a_successful_poll_records_the_check(session, monkeypatch):
    monkeypatch.setattr(inventory_mod, "fetch_inventory_html", lambda url, **kw: _fake_page())

    result = inventory_mod.poll_source(session, out_path=None, seed=False)
    session.flush()

    assert result.ok
    assert result.entries[-1].label == "999-1"

    from storage.postgres import PostgresRepository

    check = PostgresRepository(session).last_source_check()
    assert check is not None
    assert check.ok
    assert check.release_points_seen == 1
    assert check.latest_label == "999-1"
    assert not check.is_stale()


@pytest.mark.integration
def test_a_poll_reports_release_points_the_database_has_never_seen(session, monkeypatch):
    """`999-1` is fabricated, so it is new by construction — which is what the
    daily schedule keys off to decide whether to run the full update."""
    monkeypatch.setattr(inventory_mod, "fetch_inventory_html", lambda url, **kw: _fake_page())

    result = inventory_mod.poll_source(session, out_path=None, seed=False)

    assert result.new_labels == ("999-1",)
    assert result.has_new_release_points


@pytest.mark.integration
def test_a_failed_poll_still_records_the_attempt(session, monkeypatch):
    def explode(url, **kw):
        raise OSError("connection reset by peer")

    monkeypatch.setattr(inventory_mod, "fetch_inventory_html", explode)

    result = inventory_mod.poll_source(session, out_path=None, seed=False)
    session.flush()

    assert not result.ok
    assert "connection reset" in (result.error or "")

    from storage.postgres import PostgresRepository

    check = PostgresRepository(session).last_source_check()
    assert check is not None
    assert not check.ok
    assert check.release_points_seen is None  # not zero — the page never parsed
    assert "connection reset" in (check.error or "")
    assert check.is_stale()


@pytest.mark.integration
def test_an_unparseable_page_is_a_failed_check_not_an_empty_inventory(session, monkeypatch):
    """OLRC changing its markup must not read as "there are no release points"."""
    monkeypatch.setattr(inventory_mod, "fetch_inventory_html", lambda url, **kw: "<html/>")

    result = inventory_mod.poll_source(session, out_path=None, seed=False)

    assert not result.ok
    assert "InventoryParseError" in (result.error or "")


# ------------------------------------------------------------------ the route


@pytest.mark.integration
def test_status_reports_the_corpus_and_the_last_check(client):
    body = client.get("/api/v1/status").json()

    assert body["corpus"]["latest_release"] == "119-102not101"
    assert body["corpus"]["release_points_known"] >= 2
    assert body["source"]["url"].startswith("https://uscode.house.gov/")
    # `stale` is always present and always a bool, including on a box that has
    # never run a check — that is the case the reader has to be able to render.
    assert isinstance(body["source"]["stale"], bool)


@pytest.mark.integration
def test_status_is_cacheable_but_not_immutable(client):
    """ADR-0018: this answer changes daily, so it must not be pinned-immutable."""
    cache_control = client.get("/api/v1/status").headers["cache-control"]
    assert "immutable" not in cache_control
