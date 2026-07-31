"""Keyword search over the corpus (ADR-0028).

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

QUERY_SYNTAX_FLAGS = (
    "AND|OR|NOT|PHRASE|PRECEDENCE|PREFIX|FUZZY|SLOP|ESCAPE|WHITESPACE"
)
"""Which operators `simple_query_string` will honour — ADR-0031.

Every flag here is a promise the syntax guide makes, and the two must not
drift: a flag left out is an operator the guide describes and the cluster
silently swallows. Naming the set rather than passing `ALL` is what makes that
checkable — `tests/test_search_syntax.py` asserts the guide and this constant
agree.

`WHITESPACE` looks like the one flag a search box would never need, and
leaving it out is the mistake this comment exists to prevent. It does not mean
"treat tabs as operators": it is what makes the parser *split on spaces at
all*. Without it `water -pollution` parses to `+water +pollution` — the `-` is
swallowed and the query returns the opposite of what was asked. Verified
through `_validate/query?explain=true`, which is the only way to see this: the
query is valid either way and simply means something else."""


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
        description="The keyword or phrase to search for.",
        min_length=1,
        max_length=500,
    ),
    release: ReleaseParam = None,
    date: DateParam = None,
    limit: int = Query(20, description="Max number of results to return.", ge=1, le=100),
    offset: int = Query(
        0, description="Pagination offset.", ge=0, le=MAX_OFFSET
    ),
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
                        # Strict by default, loose only when asked — ADR-0031.
                        # This used to be a `multi_match` with `fuzziness:
                        # "AUTO"`, which silently spent two edits on every term:
                        # a search for `compare` returned `compact` and
                        # `company`, both of which are exactly two edits away.
                        # Nobody typing a word into a legal corpus wants a
                        # different word back. `simple_query_string` matches the
                        # terms as typed and leaves the edits to the reader, who
                        # asks for them with `~`.
                        #
                        # It is the forgiving parser of the two on purpose:
                        # `query_string` throws on an unbalanced quote or paren,
                        # which on a public endpoint turns a typo into a 400.
                        # `simple_query_string` treats the stray character as
                        # text and answers.
                        "simple_query_string": {
                            "query": q,
                            "fields": ["heading^2", "xml_text"],
                            # Every word must appear. The old default was OR,
                            # so a two-word search ranked by "matched either"
                            # and buried the documents that matched both.
                            "default_operator": "and",
                            "flags": QUERY_SYNTAX_FLAGS,
                            "analyze_wildcard": True,
                        }
                    }
                ],
                "filter": [version_filter],
            }
        },
        # Every value here was previously a default nobody chose, and the
        # defaults are tuned for a log search rather than for reading.
        #
        # `number_of_fragments` was 5, per field, over two fields — so a single
        # result could carry ten disconnected 100-character shards, which is
        # more text than the provision's own heading and impossible to scan. Two
        # is enough to show the match in context; the section itself is one
        # click away and is the thing actually worth reading.
        #
        # `fragment_size` was 100, which in statutory prose lands mid-clause
        # ("…shall include approximately one"). 220 is roughly two lines at the
        # reading width and usually reaches a sentence boundary.
        #
        # `no_match_size: 0` keeps the old behaviour of showing nothing for a
        # field that did not match, rather than the opening of every section.
        "highlight": {
            "fields": {
                "heading": {"number_of_fragments": 1},
                "xml_text": {"number_of_fragments": 2, "fragment_size": 220},
            },
            "no_match_size": 0,
        },
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
        ))

    return SearchResponse(
        results=results,
        total=total,
        release=resolved.release.label if resolved else None,
        note=note,
    )
