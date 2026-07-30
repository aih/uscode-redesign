"""The OpenSearch connection, and the index names both surfaces agree on.

Index names live here rather than in `ingest.search_sync` so that `api/` can
name an index without importing the ingest layer: the dependency runs
ingest → storage ← api (CLAUDE.md architecture rule 4), never api → ingest.
"""

from __future__ import annotations

import os
import threading

from opensearchpy import OpenSearch

SECTIONS_INDEX = "uscode_sections"
STRUCTURE_INDEX = "uscode_structure"

SEARCH_URL = os.environ.get("SEARCH_URL", "https://localhost:9200")
SEARCH_USER = os.environ.get("SEARCH_USER", "admin")


class SearchNotConfigured(RuntimeError):
    """Raised when a cluster is asked for and none is configured.

    Deliberately not a silent fallback. `SEARCH_PASSWORD` used to carry the dev
    stack's literal as its default, which meant a deployment that set neither
    `SEARCH_URL` nor `SEARCH_PASSWORD` did not fail — it quietly tried
    `https://localhost:9200` with a password published in this repository.
    """


def _verify_certs() -> bool:
    """Verify TLS by default; `SEARCH_VERIFY_CERTS=false` opts out.

    The dev stack's OpenSearch presents the self-signed certificate its image
    generates at first boot, so `docker-compose.yml` sets this to false and says
    why. Production must not: an unverified TLS connection carrying admin
    credentials is a connection any host on the path can impersonate, and
    defaulting to "off" made that the state you got by not thinking about it.
    """
    return os.environ.get("SEARCH_VERIFY_CERTS", "true").strip().lower() != "false"


_client: OpenSearch | None = None
_client_lock = threading.Lock()


def get_search_client() -> OpenSearch:
    """The process's OpenSearch client.

    A singleton because it holds a connection pool, and this used to be built
    fresh on **every request** — a new pool, and a new TLS handshake, per
    search. Double-checked under a lock: FastAPI's sync handlers run in a
    threadpool, so two searches really can arrive here at once.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _build_client()
    return _client


def _build_client() -> OpenSearch:
    password = os.environ.get("SEARCH_PASSWORD")
    if not password:
        raise SearchNotConfigured(
            "SEARCH_PASSWORD is not set. Set it (and SEARCH_URL) to point at a "
            "cluster, or set DISABLE_SEARCH_SYNC=1 to run without search."
        )
    verify = _verify_certs()
    return OpenSearch(
        hosts=[SEARCH_URL],
        http_compress=True,  # enables gzip compression for request bodies
        http_auth=(SEARCH_USER, password),
        use_ssl=True,
        verify_certs=verify,
        # Hostname assertion is part of verification, not a separate knob:
        # verifying a certificate without checking it was issued for the host
        # being talked to verifies almost nothing.
        ssl_assert_hostname=verify,
        ssl_show_warn=verify,
    )


def reset_search_client() -> None:
    """Drop the cached client. For tests that change the environment."""
    global _client
    with _client_lock:
        _client = None
