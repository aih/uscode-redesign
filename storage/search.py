import os
from opensearchpy import OpenSearch

# Default to the docker-compose service name if not specified
SEARCH_URL = os.environ.get("SEARCH_URL", "https://localhost:9200")
# OpenSearch 2.12+ requires an initial admin password
SEARCH_PASSWORD = os.environ.get("SEARCH_PASSWORD", "Uscode_Search_Admin_123!")

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
