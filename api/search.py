from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from storage.search import get_search_client
from params import public_cache

router = APIRouter(prefix="/api/v1", tags=["search"], dependencies=[Depends(public_cache)])

class SearchSnippet(BaseModel):
    field: str
    text: str

class SearchResultItem(BaseModel):
    identifier: str
    heading: Optional[str] = None
    num: Optional[str] = None
    level: Optional[str] = None
    type: str # "section" or "structure"
    snippets: List[SearchSnippet] = []

class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    total: int

@router.get("/search", response_model=SearchResponse, summary="Search US Code sections and structure")
def search(
    q: str = Query(..., description="The keyword or phrase to search for."),
    release: Optional[int] = Query(None, description="Optional release ID to filter sections by."),
    limit: int = Query(20, description="Max number of results to return.", ge=1, le=100),
    offset: int = Query(0, description="Pagination offset.", ge=0)
):
    client = get_search_client()
    
    body = {
        "from": offset,
        "size": limit,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": q,
                            "fields": ["heading^2", "xml_text"],
                            "fuzziness": "AUTO"
                        }
                    }
                ]
            }
        },
        "highlight": {
            "fields": {
                "heading": {},
                "xml_text": {}
            }
        }
    }
    
    if release is not None:
        body["query"]["bool"]["filter"] = [
            {
                "bool": {
                    "should": [
                        { "term": { "release_id": release } },
                        { "bool": { "must_not": { "exists": { "field": "release_id" } } } }
                    ]
                }
            }
        ]

    try:
        res = client.search(index="uscode_sections,uscode_structure", body=body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")
    
    hits = res["hits"]["hits"]
    total = res["hits"]["total"]["value"] if isinstance(res["hits"]["total"], dict) else res["hits"]["total"]
    
    results = []
    for hit in hits:
        source = hit["_source"]
        index_name = hit["_index"]
        type_str = "section" if "sections" in index_name else "structure"
        
        snippets = []
        highlight = hit.get("highlight", {})
        for field, texts in highlight.items():
            for text in texts:
                snippets.append(SearchSnippet(field=field, text=text))
                
        results.append(SearchResultItem(
            identifier=source.get("identifier"),
            heading=source.get("heading"),
            num=source.get("num") or source.get("num_value"),
            level=source.get("level"),
            type=type_str,
            snippets=snippets
        ))
        
    return SearchResponse(results=results, total=total)
