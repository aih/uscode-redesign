# 18. Keyword and Vector Search with OpenSearch

Date: 2026-07-30

## Status

Accepted

## Context

The US Code Redesign needs a robust search functionality that can search across statutory text (sections) and hierarchical structure nodes (titles, chapters). The search must be API-first and support complex ranking (boosting titles). Furthermore, it needs to be extensible for future RAG (Retrieval-Augmented Generation) and semantic smart-search capabilities.

We considered Postgres full-text search (`tsvector`), but while it requires no new infrastructure, it is harder to tune for complex ranking and lacks native out-of-the-box dense vector support without additional extensions like `pgvector` that might not scale as seamlessly for our specific use case as a dedicated search engine.

## Decision

We will use **OpenSearch** (an Apache 2.0 open-source alternative to Elasticsearch) as the search engine for the US Code Redesign.

### Index Strategy

We will maintain two indices:
1. **`uscode_sections`**: For indexing statutory text (`SectionVersion`).
2. **`uscode_structure`**: For indexing hierarchical nodes (`StructureNode`).

#### `uscode_sections` Mapping Strategy
```json
{
  "mappings": {
    "properties": {
      "identifier": { "type": "keyword" },
      "num": { "type": "keyword" },
      "heading": { "type": "text", "boost": 2.0 },
      "xml_text": { "type": "text" },
      "status": { "type": "keyword" },
      "release_id": { "type": "integer" },
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
  }
}
```
*Note: The `embedding` field is defined now to ensure forward compatibility with dense vector RAG pipelines.*

## Consequences

- **Pros**: Native support for advanced text search, fuzzy matching, and highlighting. Easy transition to semantic/vector search with the `knn_vector` field type.
- **Cons**: Adds a new stateful infrastructure component (`opensearch` container) to `docker-compose.yml`, increasing local memory footprint.
