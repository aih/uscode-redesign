"""The Redis client behind the corpus cache (ADR-0078).

Storage owns the client for the same reason it owns the database session and the
OpenSearch client: `api/` depends on a function and receives a handle, and the
connection pool is process state that must be built once, not per request.

The cache is **optional and advisory**. `REDIS_URL` unset means every method is
a no-op and the site runs exactly as it does without this module; a Redis that
stops answering is treated the same way, after a short cooldown so a dead
server costs one timeout per `_COOLDOWN_SECONDS` rather than one per request.
Nothing authoritative lives in Redis — a restart is a cold cache, never a wrong
one — so every failure path here degrades to "compute it again".

Not `params`' constants and not `api`'s: `storage/` may import neither
(tests/test_architecture.py), so the prefix and TTLs it needs are its own.
"""

from __future__ import annotations

import logging
import threading
import time

from db.config import settings

logger = logging.getLogger(__name__)

#: Every key this site writes starts with this, so a shared Redis can be
#: inspected (`SCAN MATCH usc:*`) and flushed without touching a neighbour.
KEY_PREFIX = "usc"

#: How long a Redis error silences the cache. One failed round trip marks the
#: client down; until this passes, every call is a silent miss with no network.
_COOLDOWN_SECONDS = 30.0

#: Tight on purpose (redis-connections guidance: connect shorter than read).
#: A cache that cannot answer in a second is slower than the database it
#: fronts, and a hanging cache must never hold a request hostage.
_CONNECT_TIMEOUT = 0.5
_SOCKET_TIMEOUT = 1.0


def cache_key(*parts: str) -> str:
    """`usc:{part}:{part}:…` — colon-joined, prefix first."""
    return ":".join((KEY_PREFIX, *parts))


class CorpusCache:
    """`get`/`set` over one Redis, failing quiet in both directions.

    `enabled` says whether calling is worth it at all (a URL is configured);
    a `get` that errors returns None, a `set` that errors drops the value, and
    either starts the cooldown. Thread-safe the way the site needs it to be:
    the redis-py client carries its own thread-safe pool, and `_down_until` is
    a float assignment, atomic under the GIL.
    """

    def __init__(self, client: object | None):
        self._client = client
        self._down_until = 0.0

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _available(self) -> bool:
        return self._client is not None and time.monotonic() >= self._down_until

    def _mark_down(self, error: Exception) -> None:
        self._down_until = time.monotonic() + _COOLDOWN_SECONDS
        logger.warning(
            "corpus cache unavailable (%s: %s); serving without it for %.0fs",
            type(error).__name__,
            error,
            _COOLDOWN_SECONDS,
        )

    def get(self, key: str) -> bytes | None:
        if not self._available():
            return None
        try:
            return self._client.get(key)  # type: ignore[attr-defined]
        except Exception as error:  # noqa: BLE001 — any Redis failure is a miss
            self._mark_down(error)
            return None

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        if not self._available():
            return
        try:
            # NX: a concurrent miss computed the same value; first writer wins
            # and the second round trip is spared the payload rewrite.
            self._client.set(key, value, ex=ttl_seconds, nx=True)  # type: ignore[attr-defined]
        except Exception as error:  # noqa: BLE001
            self._mark_down(error)

    def ping(self) -> bool:
        """One health probe, for `/health`. Never raises."""
        if not self._available():
            return False
        try:
            return bool(self._client.ping())  # type: ignore[attr-defined]
        except Exception as error:  # noqa: BLE001
            self._mark_down(error)
            return False


_cache: CorpusCache | None = None
_cache_lock = threading.Lock()


def get_cache() -> CorpusCache:
    """The process's corpus cache. A singleton for the pool it holds, built
    lazily so a Redis that is down at import time delays nothing — the first
    *use* pays the connect timeout and starts the cooldown."""
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = CorpusCache(_build_client())
    return _cache


def _build_client() -> object | None:
    url = settings.redis_url
    if not url:
        return None
    import redis

    return redis.Redis.from_url(
        url,
        socket_connect_timeout=_CONNECT_TIMEOUT,
        socket_timeout=_SOCKET_TIMEOUT,
        max_connections=settings.redis_max_connections,
    )


def cache_status() -> str:
    """`disabled` (no URL), `ok`, or `unavailable` — for `/health`, which must
    report the cache without failing on it (a cache outage must not look like a
    site outage to `deploy/watchdog.sh`)."""
    cache = get_cache()
    if not cache.enabled:
        return "disabled"
    return "ok" if cache.ping() else "unavailable"


def close_cache_client() -> None:
    """Drop the client and its pool. For the app's shutdown, and for tests that
    change the environment (the `reset_search_client` shape)."""
    global _cache
    with _cache_lock:
        if _cache is not None and _cache._client is not None:
            try:
                _cache._client.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — shutdown must not fail on cleanup
                pass
        _cache = None


def set_cache_for_tests(client: object | None) -> None:
    """Install a fake client (fakeredis) or None. Tests only."""
    global _cache
    with _cache_lock:
        _cache = CorpusCache(client)
