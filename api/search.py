"""Keyword search over the corpus (ADR-0028, ADR-0031, ADR-0049).

Versioning is the whole difficulty here. The index holds one document per
deduped section *version*, so a section that has been amended four times has
four documents whose text all matches "conservation". Returning all of them is
not a search result list, it is the same section four times. So the default
filters `is_current` — the text in force now — and `?release=`/`?date=` swap that
for a point-in-time filter. The earlier versions are still counted and reported
per result (`earlier_matches`), which is the difference between "this section
does not mention it" and "this section stopped mentioning it".

Release resolution goes through the Repository like everywhere else (CLAUDE.md
architecture rule 1): this module turns a label into `release_points.seq` by
asking the repository, never by querying, so `119-102` resolving to
`119-102not101` behaves here exactly as it does on a section page.

The query itself is built in `storage/searchquery.py`, not here, so that
`scripts/search_eval.py` can score the ranking that ships rather than a copy of
it (ADR-0049).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from params import (
    DateParam,
    ReleaseParam,
    RepositoryDep,
    parse_date_param,
    public_cache,
    rate_limit,
    resolve_release_or_404,
)
from storage.search import SECTIONS_INDEX, STRUCTURE_INDEX, get_search_client
from storage.searchquery import (
    CANDIDATES,
    QUERY_SYNTAX_FLAGS,
    SORTS,
    build_earlier_versions_body,
    build_search_body,
    parse_query,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["search"], dependencies=[Depends(public_cache)])

_limit_search = rate_limit("search", capacity=120, per_second=10.0)
"""ADR-0029. Sized for a server, not a person: `/app/search` renders on the
server and calls this over HTTP, so the whole readership's searches arrive from
the frontend container's one address. The per-person limit for readers is in
`frontend/src/middleware.ts`; this bounds what a caller hitting `/api/v1`
directly can spend."""

MAX_OFFSET = 1000
"""Deep paging is bounded here rather than left to OpenSearch. Past
`max_result_window` (10,000 by default) the cluster throws — an unbounded
`offset` is therefore both a 500 and heap pressure, from a query string. A
thousand results deep is far past where a keyword search is useful anyway."""

RANKING = CANDIDATES["phrase"]
"""The scoring model in force, chosen by measured nDCG@10 over
`docs/verification/search-judgements.json` — ADR-0049. Changing this line
changes the ranking, so re-run `uv run python scripts/search_eval.py` and commit
what it writes."""

__all__ = ["router", "QUERY_SYNTAX_FLAGS"]


class SearchSnippet(BaseModel):
    field: str
    text: str


class FacetValue(BaseModel):
    value: str
    count: int


class SearchFacets(BaseModel):
    """Counts over the whole result set, not the page. Each one is a filter the
    reader can add to the query (`title:16`, `status:repealed`)."""

    titles: List[FacetValue] = []
    statuses: List[FacetValue] = []


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
    title_num: Optional[str] = None
    status: Optional[str] = None
    earlier_matches: int = 0
    """How many superseded versions of this section also match. Reported rather
    than returned as rows of their own — see the module docstring."""
    id_collision: bool = False
    """The source published more than one provision under this identifier at
    this release point (ADR-0021), and the index holds one of them. Measured
    over the loaded corpus: 49 identifiers in 14 titles."""


class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    total: int
    release: Optional[str] = None
    """The release point searched, when one was asked for. Absent means the
    default: whatever is in force now."""
    note: Optional[str] = None
    sort: str = "relevance"
    facets: SearchFacets = SearchFacets()


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search US Code sections and structure",
    dependencies=[Depends(_limit_search)],
)
def search(
    repository: RepositoryDep,
    q: str = Query(
        ...,
        description=(
            "The keyword or phrase to search for. Accepts the operators at "
            "/app/search/syntax, including the scopes heading:, title:, "
            "chapter:, status:, release: and date:."
        ),
        min_length=1,
        max_length=500,
    ),
    release: ReleaseParam = None,
    date: DateParam = None,
    sort: str = Query(
        "relevance",
        description="relevance, citation (the Code's own order) or recent (most recently amended).",
    ),
    limit: int = Query(20, description="Max number of results to return.", ge=1, le=100),
    offset: int = Query(
        0, description="Pagination offset.", ge=0, le=MAX_OFFSET
    ),
):
    if sort not in SORTS:
        raise HTTPException(
            status_code=400, detail=f"sort must be one of: {', '.join(SORTS)}"
        )

    parsed = parse_query(q)
    if parsed.is_empty():
        # Everything the reader typed was a scope with nothing to scope by, so
        # there is no query left. Answering with the whole corpus would be a
        # worse answer than saying so.
        raise HTTPException(status_code=400, detail="that query has nothing to search for")

    # An explicit parameter beats one written into the query. `?release=` is
    # what the pager and the reader's release context carry, and a query string
    # the reader typed once should not override the moment the page is pinned to.
    want_release = release if release is not None else parsed.release
    want_date = date if date is not None else parsed.date

    resolved = None
    note = None
    if want_release is not None or want_date is not None:
        resolved = resolve_release_or_404(
            repository, release=want_release, on_date=parse_date_param(want_date)
        )
        note = resolved.note

    body = build_search_body(
        parsed,
        profile=RANKING,
        release_seq=resolved.release.seq if resolved else None,
        sort=sort,
        limit=limit,
        offset=offset,
        facets=True,
    )

    client = get_search_client()
    index = f"{SECTIONS_INDEX},{STRUCTURE_INDEX}"
    try:
        res = client.search(index=index, body=body)
    except Exception:
        # The exception goes to the log, not to the caller. An opensearch-py
        # error stringifies to the cluster's internal hostname, port and index
        # names, and a 503 body is a page a stranger can read — the operator
        # needs the detail and the caller needs a status.
        log.exception("search query failed")
        raise HTTPException(
            status_code=503, detail="search is unavailable; try again shortly"
        ) from None

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
            title_num=source.get("title_num"),
            status=source.get("status"),
            id_collision=bool(source.get("id_collision", False)),
        ))

    if resolved is None:
        _count_earlier_matches(client, parsed, results)

    return SearchResponse(
        results=results,
        total=total,
        release=resolved.release.label if resolved else None,
        note=note,
        sort=sort,
        facets=_facets(res.get("aggregations", {})),
    )


def _count_earlier_matches(client, parsed, results: list[SearchResultItem]) -> None:
    """Fill in `earlier_matches` for the sections on this page.

    A failure here is not a failed search: the result list is already built and
    correct, and the count is an extra fact about it. So this logs and leaves the
    counts at zero rather than turning a good answer into a 503.
    """
    identifiers = [r.identifier for r in results if r.type == "section" and r.identifier]
    if not identifiers:
        return
    try:
        res = client.search(
            index=SECTIONS_INDEX,
            body=build_earlier_versions_body(parsed, identifiers, profile=RANKING),
        )
    except Exception:
        log.warning("earlier-version counts unavailable", exc_info=True)
        return
    counts = {
        bucket["key"]: bucket["doc_count"]
        for bucket in res.get("aggregations", {}).get("by_identifier", {}).get("buckets", [])
    }
    for result in results:
        result.earlier_matches = counts.get(result.identifier, 0)


def _facets(aggregations: dict) -> SearchFacets:
    def values(name: str) -> list[FacetValue]:
        buckets = aggregations.get(name, {}).get("buckets", [])
        return [FacetValue(value=str(b["key"]), count=b["doc_count"]) for b in buckets]

    return SearchFacets(titles=values("titles"), statuses=values("statuses"))
