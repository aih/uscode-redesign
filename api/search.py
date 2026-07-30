"""Keyword search over the corpus (ADR-0022).

Versioning is the whole difficulty here. The index holds one document per
deduped section *version*, so a section that has been amended four times has
four documents whose text all matches "conservation". Returning all of them is
not a search result list, it is the same section four times. So the default
filters `is_current` — the text in force now — and `?release=`/`?date=` swap that
for a point-in-time filter.

Release resolution goes through the Repository like everywhere else (CLAUDE.md
architecture rule 1): this module turns a label into `release_points.seq` by
asking the repository, never by querying, so `119-102` resolving to
`119-102not101` behaves here exactly as it does on a section page.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from params import (
    DateParam,
    ReleaseParam,
    RepositoryDep,
    parse_date_param,
    public_cache,
    resolve_release_or_404,
)
from storage.search import SECTIONS_INDEX, STRUCTURE_INDEX, get_search_client

router = APIRouter(prefix="/api/v1", tags=["search"], dependencies=[Depends(public_cache)])


class SearchSnippet(BaseModel):
    field: str
    text: str


class SearchResultItem(BaseModel):
    identifier: str
    heading: Optional[str] = None
    num: Optional[str] = None
    level: Optional[str] = None
    type: str  # "section" or "structure"
    snippets: List[SearchSnippet] = []
    first_release: Optional[str] = None
    """The release point this text first appeared at — "unchanged since"."""
    is_current: bool = True


class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    total: int
    release: Optional[str] = None
    """The release point searched, when one was asked for. Absent means the
    default: whatever is in force now."""
    note: Optional[str] = None


@router.get("/search", response_model=SearchResponse, summary="Search US Code sections and structure")
def search(
    repository: RepositoryDep,
    q: str = Query(..., description="The keyword or phrase to search for."),
    release: ReleaseParam = None,
    date: DateParam = None,
    limit: int = Query(20, description="Max number of results to return.", ge=1, le=100),
    offset: int = Query(0, description="Pagination offset.", ge=0),
):
    resolved = None
    note = None
    if release is not None or date is not None:
        resolved = resolve_release_or_404(
            repository, release=release, on_date=parse_date_param(date)
        )
        note = resolved.note

    if resolved is None:
        # The default, and the only one that reads a single document per section.
        version_filter = {"term": {"is_current": True}}
    else:
        # Point-in-time: the text that had appeared by this release and had not
        # yet been superseded. `first_release_seq <= seq` alone would match every
        # earlier version too, so the newest match per section is picked by
        # collapsing on the identifier — the same "newest at or before" rule the
        # Repository applies to a release point that was never ingested
        # (gotcha 10).
        version_filter = {"range": {"first_release_seq": {"lte": resolved.release.seq}}}

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
                ],
                "filter": [version_filter],
            }
        },
        "highlight": {
            "fields": {
                "heading": {},
                "xml_text": {}
            }
        }
    }

    if resolved is not None:
        body["collapse"] = {
            "field": "identifier",
            "inner_hits": {
                "name": "at_release",
                "size": 1,
                "sort": [{"first_release_seq": "desc"}],
                "highlight": body["highlight"],
            },
        }

    try:
        res = get_search_client().search(
            index=f"{SECTIONS_INDEX},{STRUCTURE_INDEX}", body=body
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Search failed: {e}")

    hits = res["hits"]["hits"]
    total = res["hits"]["total"]["value"] if isinstance(res["hits"]["total"], dict) else res["hits"]["total"]

    results = []
    for hit in hits:
        # Under collapse the outer hit is the best-scoring version of the section;
        # the one actually in force at the requested release is the inner hit.
        inner = hit.get("inner_hits", {}).get("at_release", {}).get("hits", {}).get("hits")
        if inner:
            hit = inner[0]

        source = hit["_source"]
        index_name = hit["_index"]
        type_str = "section" if SECTIONS_INDEX in index_name else "structure"

        snippets = []
        for field, texts in hit.get("highlight", {}).items():
            for text in texts:
                snippets.append(SearchSnippet(field=field, text=text))

        results.append(SearchResultItem(
            identifier=source.get("identifier"),
            heading=source.get("heading"),
            num=source.get("num") or source.get("num_value"),
            level=source.get("level"),
            type=type_str,
            snippets=snippets,
            first_release=source.get("first_release_label"),
            is_current=bool(source.get("is_current", True)),
        ))

    return SearchResponse(
        results=results,
        total=total,
        release=resolved.release.label if resolved else None,
        note=note,
    )
