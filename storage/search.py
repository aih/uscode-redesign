import os
from opensearchpy import OpenSearch

# Index names live here rather than in `ingest.search_sync` so that `api/` can
# name an index without importing the ingest layer: the dependency runs
# ingest → storage ← api (CLAUDE.md architecture rule 4), never api → ingest.
SECTIONS_INDEX = "uscode_sections"
STRUCTURE_INDEX = "uscode_structure"

# Default to the docker-compose service name if not specified
SEARCH_URL = os.environ.get("SEARCH_URL", "https://localhost:9200")
# OpenSearch 2.12+ requires an initial admin password, and its security plugin
# refuses any that resembles the username — so this default must not contain
# "admin". It matches OPENSEARCH_INITIAL_ADMIN_PASSWORD in docker-compose.yml;
# change one and you must change the other.
SEARCH_PASSWORD = os.environ.get("SEARCH_PASSWORD", "Usc0deSearch!Str0ng#2026")

def get_search_client() -> OpenSearch:
    """Return an OpenSearch client instance."""
    # Note: In production, verify_certs should be True and the CA cert provided
    return OpenSearch(
        hosts=[SEARCH_URL],
        http_compress=True, # enables gzip compression for request bodies
        http_auth=("admin", SEARCH_PASSWORD),
        use_ssl=True,
        verify_certs=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
