import logging
from typing import Any
import re
from opensearchpy import helpers
from storage.search import get_search_client

logger = logging.getLogger(__name__)

def strip_xml_tags(xml_str: str) -> str:
    """A simple fallback regex to strip xml tags for text indexing."""
    if not xml_str:
        return ""
    text = re.sub(r'<[^>]+>', ' ', xml_str)
    return re.sub(r'\s+', ' ', text).strip()

def create_indices():
    """Create OpenSearch indices if they do not exist."""
    import os
    if os.environ.get("DISABLE_SEARCH_SYNC") == "1":
        return
        
    client = get_search_client()
    
    sections_mapping = {
        "mappings": {
            "properties": {
                "identifier": {"type": "keyword"},
                "num": {"type": "keyword"},
                "heading": {"type": "text", "boost": 2.0},
                "xml_text": {"type": "text"},
                "status": {"type": "keyword"},
                "release_id": {"type": "integer"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": 768,
                    "method": {
                        "name": "hnsw",
                        "space_type": "l2",
                        "engine": "nmslib"
                    }
                }
            }
        },
        "settings": {
            "index": {
                "knn": True
            }
        }
    }
    
    structure_mapping = {
        "mappings": {
            "properties": {
                "identifier": {"type": "keyword"},
                "level": {"type": "keyword"},
                "num_value": {"type": "keyword"},
                "heading": {"type": "text", "boost": 2.0}
            }
        }
    }
    
    try:
        if not client.indices.exists(index="uscode_sections"):
            client.indices.create(index="uscode_sections", body=sections_mapping)
        if not client.indices.exists(index="uscode_structure"):
            client.indices.create(index="uscode_structure", body=structure_mapping)
    except Exception as e:
        logger.warning(f"Could not create OpenSearch indices: {e}")

def sync_sections(versions: list[dict[str, Any]]):
    """Bulk index a list of section versions."""
    import os
    if os.environ.get("DISABLE_SEARCH_SYNC") == "1":
        return
        
    client = get_search_client()
    actions = []
    for v in versions:
        action = {
            "_index": "uscode_sections",
            "_id": f"{v['identifier']}_{v['release_id']}",
            "_source": {
                "identifier": v["identifier"],
                "num": v.get("num"),
                "heading": v.get("heading"),
                "xml_text": strip_xml_tags(v.get("xml")),
                "status": v.get("status"),
                "release_id": v["release_id"],
            }
        }
        actions.append(action)
    if actions:
        try:
            helpers.bulk(client, actions)
        except Exception as e:
            logger.warning(f"Failed to bulk index sections: {e}")

def sync_structure_nodes(nodes: list[dict[str, Any]]):
    """Bulk index structure nodes."""
    import os
    if os.environ.get("DISABLE_SEARCH_SYNC") == "1":
        return
        
    client = get_search_client()
    actions = []
    for n in nodes:
        action = {
            "_index": "uscode_structure",
            "_id": n["identifier"],
            "_source": {
                "identifier": n["identifier"],
                "level": n.get("level"),
                "num_value": n.get("num_value"),
                "heading": n.get("heading"),
            }
        }
        actions.append(action)
    if actions:
        try:
            helpers.bulk(client, actions)
        except Exception as e:
            logger.warning(f"Failed to bulk index structure nodes: {e}")
