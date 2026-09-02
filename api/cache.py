"""The response-data cache: payloads under a corpus generation (ADR-0078).

What is cached is the **payload** — the Pydantic value a handler was about to
return — never the HTTP response. The handler's header logic (ADR-0018's
`Cache-Control`, the ETag that is a content hash, `Vary`) runs on every request,
hit or miss, so a replayed header can never disagree with the resolution that
should have produced it.

Every key is prefixed with the corpus generation, read from Postgres **before**
the data it guards (`Repository.corpus_generation`'s docstring carries the
ordering argument). An ingest commit moves the generation inside its own
transaction, so it orphans every existing key at the instant the data changes:
the contract is "a change committed by ingest is visible to the next request",
not "within a TTL". The TTL below only bounds how long orphaned generations
occupy memory; it plays no part in freshness.

This module may not import SQLAlchemy (tests/test_architecture.py) — the
generation arrives through the `Repository`, and the Redis handle through
`storage.cache`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Annotated, TypeVar

from fastapi import Depends, Response
from pydantic import TypeAdapter

from params import RepositoryDep
from storage import Repository, get_cache
from storage.cache import cache_key

T = TypeVar("T")

#: On every response whose handler read the generation. The reader keys its own
#: per-title release memo on it (`frontend/src/lib/generation.ts`), which is
#: what retired that memo's five-minute staleness window (ADR-0045's recorded
#: cost). Sent whether or not Redis is configured — the header is a fact about
#: the corpus, not about the cache.
GENERATION_HEADER = "X-Corpus-Generation"

#: `hit` or `miss`, on responses that consulted Redis. Absent when the cache is
#: disabled. For tests and for anyone reading response headers to see whether
#: the cache is doing anything.
STATE_HEADER = "X-Corpus-Cache"

#: A bound on orphaned-generation memory, not on freshness — invalidation is
#: the generation prefix. `allkeys-lru` in the Redis config is the other bound.
WEEK_SECONDS = 7 * 24 * 3600


class ResponseDataCache:
    """Per-request handle: one lazy generation read, then `through()`.

    Lazy so that a request rejected before its handler runs — a 429 from a
    route-level limiter, a 422 from validation — costs no database round trip,
    the property `storage/session.py`'s `after_begin` listener exists to keep.
    """

    def __init__(self, repository: Repository, response: Response):
        self._repository = repository
        self._response = response
        self._generation: int | None = None

    @property
    def generation(self) -> int:
        """The corpus generation, read once per request, stamped on the
        response. Reading it is what fixes the read-before-data order: call
        this (or `through`, which does) before the reads whose result you
        cache."""
        if self._generation is None:
            self._generation = self._repository.corpus_generation()
            self._response.headers[GENERATION_HEADER] = str(self._generation)
        return self._generation

    def through(
        self,
        adapter: TypeAdapter[T],
        name: str,
        parts: Iterable[str],
        compute: Callable[[], T],
        *,
        ttl_seconds: int = WEEK_SECONDS,
    ) -> T:
        """`compute()`, memoised in Redis under the current generation.

        `parts` must determine the payload given the generation — resolved
        labels, never requested ones (the ADR-0066 rule: an unpinned label
        means a different release point the moment a newer one is loaded).
        `compute` may raise; nothing is stored then, so an error is never an
        answer. Serialized `by_alias` so the stored JSON is byte-for-byte what
        FastAPI would put on the wire.
        """
        generation = self.generation
        cache = get_cache()
        if not cache.enabled:
            return compute()

        key = cache_key(f"g{generation}", name, *parts)
        stored = cache.get(key)
        if stored is not None:
            self._response.headers[STATE_HEADER] = "hit"
            return adapter.validate_json(stored)

        value = compute()
        cache.set(key, adapter.dump_json(value, by_alias=True), ttl_seconds)
        self._response.headers[STATE_HEADER] = "miss"
        return value


def get_response_cache(repository: RepositoryDep, response: Response) -> ResponseDataCache:
    return ResponseDataCache(repository, response)


ResponseCacheDep = Annotated[ResponseDataCache, Depends(get_response_cache)]
