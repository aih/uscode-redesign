"""What a search query means, and the OpenSearch body it becomes.

This is one module rather than code inside `api/search.py` because the ranking
has to be *measurable*. `scripts/search_eval.py` scores the profiles below
against `docs/verification/search-judgements.json`, and a measurement is only
worth reading if it ran the query the site actually sends. A second copy of the
query builder in the harness would measure the harness.

Nothing here talks to a cluster or to Postgres. `parse_query` turns a reader's
string into filters and residual text; `build_search_body` turns that into a
request body. Release *resolution* stays where it belongs — the caller resolves
`release:119-99` through the Repository and passes a seq in (architecture rule
1), because a label like `119-102` disambiguating to `119-102not101` is a
version-resolution question and this module is not allowed to answer it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

QUERY_SYNTAX_FLAGS = "AND|OR|NOT|PHRASE|PRECEDENCE|PREFIX|FUZZY|SLOP|ESCAPE|WHITESPACE"
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
query is valid either way and simply means something else.
"""

# ---------------------------------------------------------------- the operators

SCOPE_FIELDS: dict[str, str] = {
    "heading": "heading",
    "title": "title_num",
    "chapter": "chapter",
    "status": "status",
}
"""`field:value` prefixes this site implements itself, and the index field each
one filters.

They are not `simple_query_string` syntax. That parser has no notion of a field,
and the one that does — `query_string` — throws on malformed input, which
ADR-0031 rejected for an endpoint anyone can type into. So these are lifted out
of the query string before it reaches the cluster, and what is left is parsed
exactly as strictly as before.

`heading` is the odd one: it scopes a *term* to a field rather than filtering,
so it becomes its own matching clause instead of a filter.
"""

TIME_SCOPES = ("release", "date")
"""`release:119-99` and `date:07/12/2026`. Extracted here, resolved by the
caller — see the module docstring."""

_SCOPE_TOKEN = re.compile(r"^([a-z]+):(.*)$", re.IGNORECASE)

_TOKENS = re.compile(r'[a-zA-Z]+:"[^"]*"|"[^"]*"|\S+')
"""Whitespace-separated tokens, except that a double-quoted run is one token —
including one carrying a scope prefix.

That first alternative is not redundant, and leaving it out is a bug this
comment exists to prevent. `"[^"]*"|\\S+` only recognises a quoted run when the
quote opens the token, so `heading:"wild horses"` matched `heading:"wild` and
then `horses"`: the scope took a value of `"wild` and the second word fell
through to the free text. The query was still valid and simply meant something
else, which is the same shape as ADR-0031's `WHITESPACE` flag. Caught by
`frontend/tests/searchscope.test.ts`, which asserts the round trip."""


@dataclass(frozen=True)
class ParsedQuery:
    """A reader's query, split into what filters and what matches."""

    text: str = ""
    """What is left after the scopes are lifted out — parsed by the cluster."""

    heading_terms: tuple[str, ...] = ()
    """`heading:water` — matched against the heading field alone."""

    filters: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Index field → the values asked for. Several values of one field are an
    OR (`title:16 title:18` is either), several fields are an AND."""

    release: str | None = None
    date: str | None = None
    """Written in the query rather than passed as `?release=`/`?date=`. The
    caller decides which wins when both arrive; it resolves neither here."""

    def is_empty(self) -> bool:
        return not (self.text or self.heading_terms or self.filters)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def normalise_title(value: str) -> str:
    """`t16` → `16`, `T5a` → `5a`.

    A drafter writing `title:16` and one writing `title:t16` mean the same
    title, and the index holds the bare form because that is what `Title.num`
    holds ('16', '5a' — gotcha 16).
    """
    value = value.strip().lower()
    return value[1:] if value.startswith("t") and value[1:2].isdigit() else value


def parse_query(q: str) -> ParsedQuery:
    """Lift the `field:value` scopes out of a query string.

    A token whose prefix is not a scope this site implements is left in the text
    untouched, so `see: also` searches for those words rather than failing. That
    is the same forgiveness ADR-0031 chose `simple_query_string` for.
    """
    text_parts: list[str] = []
    heading_terms: list[str] = []
    filters: dict[str, list[str]] = {}
    release: str | None = None
    date: str | None = None

    for token in _TOKENS.findall(q):
        match = _SCOPE_TOKEN.match(token)
        if match is None:
            text_parts.append(token)
            continue

        name, value = match.group(1).lower(), _unquote(match.group(2)).strip()
        if not value:
            # `title:` with nothing after it filters on nothing. Treated as text
            # so the reader sees a search rather than an empty result set.
            text_parts.append(token)
        elif name == "release":
            release = value
        elif name == "date":
            date = value
        elif name == "heading":
            heading_terms.append(value)
        elif name == "title":
            filters.setdefault(SCOPE_FIELDS["title"], []).append(normalise_title(value))
        elif name in SCOPE_FIELDS:
            filters.setdefault(SCOPE_FIELDS[name], []).append(value.lower())
        else:
            text_parts.append(token)

    return ParsedQuery(
        text=" ".join(text_parts),
        heading_terms=tuple(heading_terms),
        filters={key: tuple(values) for key, values in filters.items()},
        release=release,
        date=date,
    )


def unparse_query(parsed: ParsedQuery) -> str:
    """A `ParsedQuery` written back as something a reader could have typed.

    The facet links spend this: adding a filter means editing the query, so the
    query string stays the one place a search is written down and a filtered
    search is citable by its URL alone.
    """
    parts: list[str] = []
    if parsed.text:
        parts.append(parsed.text)
    parts.extend(f"heading:{_quote_if_spaced(term)}" for term in parsed.heading_terms)
    for name, index_field in SCOPE_FIELDS.items():
        if index_field == "heading":
            continue
        for value in parsed.filters.get(index_field, ()):
            parts.append(f"{name}:{_quote_if_spaced(value)}")
    if parsed.release:
        parts.append(f"release:{parsed.release}")
    if parsed.date:
        parts.append(f"date:{parsed.date}")
    return " ".join(parts)


def _quote_if_spaced(value: str) -> str:
    return f'"{value}"' if " " in value else value


def with_filter(parsed: ParsedQuery, name: str, value: str) -> ParsedQuery:
    """The same query with one more `name:value` scope. Idempotent."""
    index_field = SCOPE_FIELDS[name]
    value = normalise_title(value) if name == "title" else value.lower()
    existing = parsed.filters.get(index_field, ())
    if value in existing:
        return parsed
    filters = dict(parsed.filters)
    filters[index_field] = existing + (value,)
    return ParsedQuery(
        text=parsed.text,
        heading_terms=parsed.heading_terms,
        filters=filters,
        release=parsed.release,
        date=parsed.date,
    )


def without_filter(parsed: ParsedQuery, name: str, value: str) -> ParsedQuery:
    """The same query with one `name:value` scope removed."""
    index_field = SCOPE_FIELDS[name]
    value = normalise_title(value) if name == "title" else value.lower()
    remaining = tuple(v for v in parsed.filters.get(index_field, ()) if v != value)
    filters = dict(parsed.filters)
    if remaining:
        filters[index_field] = remaining
    else:
        filters.pop(index_field, None)
    return ParsedQuery(
        text=parsed.text,
        heading_terms=parsed.heading_terms,
        filters=filters,
        release=parsed.release,
        date=parsed.date,
    )


# ------------------------------------------------------------------- the profiles


@dataclass(frozen=True)
class Profile:
    """A scoring model, as data, so `scripts/search_eval.py` can measure one
    against another without either of them being a second implementation."""

    name: str
    fields: tuple[str, ...]
    """`simple_query_string` field weights, Lucene's `field^boost` spelling."""

    phrase_boost: float = 0.0
    """Added as a `should` clause matching the whole query as a phrase, so a
    provision saying the words together outranks one that merely contains them
    all. 0 disables it."""

    phrase_slop: int = 2
    heading_phrase_boost: float = 0.0

    scope: Literal["current", "all"] = "current"
    """`current` filters `is_current` and returns the text in force — ADR-0028's
    default. `all` searches superseded text too and collapses to one row per
    section."""

    current_boost: float = 0.0
    """Only meaningful with `scope="all"`: how much a version being in force
    lifts it above one that is not."""


DEPLOYED = Profile(
    name="deployed",
    fields=("heading^4", "xml_text"),
)
"""What the site ranked by before ADR-0049, spelled as the weighting it actually
had rather than the one its source said.

`api/search.py` asked for `heading^2`, and the mapping carried a deprecated
index-time `boost: 2.0` on the same field, which OpenSearch multiplies into the
query-time weight instead of replacing. Measured on the pre-B4 index: with the
index-time boost present, BM25's `boost` factor for a heading term is 4.4 —
2.2 (k1+1) × 2.0 — and `heading^4` against a boost-free mapping reproduces the
old ranking *and its scores* exactly, on all ten queries tried. So this is the
baseline, and it is a faithful one.
"""

CANDIDATES: dict[str, Profile] = {
    "deployed": DEPLOYED,
    # Heading weight alone, to find where it stops helping before anything else
    # is changed.
    "heading-6": Profile(name="heading-6", fields=("heading^6", "num.text^2", "xml_text")),
    "heading-10": Profile(name="heading-10", fields=("heading^10", "num.text^2", "xml_text")),
    "heading-16": Profile(name="heading-16", fields=("heading^16", "num.text^2", "xml_text")),
    # The winner of those, plus the phrase-proximity boost.
    "phrase": Profile(
        name="phrase",
        fields=("heading^10", "num.text^2", "xml_text"),
        phrase_boost=4.0,
        heading_phrase_boost=8.0,
    ),
    # And the same over every version rather than the text in force, which is
    # the variant that changes what a result *means*.
    "all-versions": Profile(
        name="all-versions",
        fields=("heading^10", "num.text^2", "xml_text"),
        phrase_boost=4.0,
        heading_phrase_boost=8.0,
        scope="all",
        current_boost=6.0,
    ),
}

SORTS = ("relevance", "citation", "recent")
"""`relevance` is the scoring model. `citation` walks the Code in its own order
(`sort_key`). `recent` is most-recently-amended first — `first_release_seq` is
the release point at which the text on screen first appeared, so for the version
in force that is when it was last changed."""

_PLAIN_WORDS = re.compile(r"^[\w\s]+$", re.UNICODE)


def _phrase_clauses(profile: Profile, text: str) -> list[dict[str, Any]]:
    """The proximity boost, when the query is one a phrase match can mean.

    Skipped for a single word (a phrase of one is the term query already scored)
    and for anything carrying operator characters: `match_phrase` has no operator
    syntax, so `forest | grassland` would be scored as a search for the literal
    word "|", quietly rewarding nothing.
    """
    if not profile.phrase_boost or len(text.split()) < 2 or not _PLAIN_WORDS.match(text):
        return []
    clauses = [
        {"match_phrase": {"xml_text": {"query": text, "slop": profile.phrase_slop,
                                       "boost": profile.phrase_boost}}}
    ]
    if profile.heading_phrase_boost:
        clauses.append(
            {"match_phrase": {"heading": {"query": text, "slop": profile.phrase_slop,
                                          "boost": profile.heading_phrase_boost}}}
        )
    return clauses


def _text_clause(text: str, fields: Iterable[str]) -> dict[str, Any]:
    return {
        "simple_query_string": {
            "query": text,
            "fields": list(fields),
            # Every word must appear. The old default was OR, so a two-word
            # search ranked by "matched either" and buried the documents that
            # matched both.
            "default_operator": "and",
            "flags": QUERY_SYNTAX_FLAGS,
            "analyze_wildcard": True,
        }
    }


def build_search_body(
    parsed: ParsedQuery,
    *,
    profile: Profile = DEPLOYED,
    release_seq: int | None = None,
    sort: str = "relevance",
    limit: int = 20,
    offset: int = 0,
    facets: bool = False,
) -> dict[str, Any]:
    """The OpenSearch request body for one search.

    `release_seq` is the resolved release point, or None for the text in force.
    Passing one switches the version filter from "is in force" to "had appeared
    by then", and collapses to the newest match per section — the same "answer
    from the newest release at or before the one asked for" rule the Repository
    applies (gotcha 10).
    """
    must: list[dict[str, Any]] = []
    if parsed.text:
        must.append(_text_clause(parsed.text, profile.fields))
    for term in parsed.heading_terms:
        must.append(_text_clause(term, ["heading"]))

    should = _phrase_clauses(profile, parsed.text) if parsed.text else []

    filters: list[dict[str, Any]] = [
        {"terms": {index_field: list(values)}}
        if index_field != "status"
        else _status_filter(values)
        for index_field, values in parsed.filters.items()
    ]

    collapse = False
    if release_seq is not None:
        # Point-in-time: the text that had appeared by this release and had not
        # yet been superseded. `first_release_seq <= seq` alone would match every
        # earlier version too, so the newest match per section is picked by
        # collapsing on the identifier.
        filters.append({"range": {"first_release_seq": {"lte": release_seq}}})
        collapse = True
    elif profile.scope == "current":
        # The default, and the only one that reads a single document per section.
        filters.append({"term": {"is_current": True}})
    else:
        collapse = True
        if profile.current_boost:
            should.append({"term": {"is_current": {"value": True,
                                                   "boost": profile.current_boost}}})

    query: dict[str, Any] = {"bool": {"filter": filters}}
    if must:
        query["bool"]["must"] = must
    if should:
        query["bool"]["should"] = should

    highlight = {
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
        "fields": {
            "heading": {"number_of_fragments": 1},
            "xml_text": {"number_of_fragments": 2, "fragment_size": 220},
        },
        "no_match_size": 0,
    }

    body: dict[str, Any] = {
        "from": offset,
        "size": limit,
        "query": query,
        "highlight": highlight,
        # OpenSearch stops counting at 10,000 by default and reports that as
        # the total, so a broad search said "10,000 results" whatever the real
        # number was. On a corpus this size that is most of the interesting
        # queries, and a count a reader cannot trust is worse than no count.
        "track_total_hits": True,
    }

    if sort != "relevance":
        body["sort"] = _sort_clause(sort)

    if collapse:
        body["collapse"] = {
            "field": "identifier",
            "inner_hits": {
                "name": "at_release",
                "size": 1,
                # The newest version at or before the release asked for, which
                # under a `first_release_seq <= seq` filter is the one in force
                # then.
                "sort": [{"first_release_seq": "desc"}],
                "highlight": highlight,
            },
        }
        # `hits.total` counts documents, and collapsing does not change that —
        # so a point-in-time search reported the number of matching *versions*
        # while showing one row per section. At a release point late in the
        # inventory that is several times the number of rows there are to read.
        # Counting distinct identifiers is the number the page is showing.
        body.setdefault("aggs", {})[COLLAPSED_TOTAL] = {
            "cardinality": {"field": "identifier", "precision_threshold": 40000}
        }

    if facets:
        body.setdefault("aggs", {}).update({
            "titles": {"terms": {"field": "title_num", "size": 20}},
            # `missing` is what makes the ordinary operative section countable:
            # the source writes no `@status` on one, so a plain terms
            # aggregation would report only the repealed and omitted ones and
            # read as though the corpus were nothing else.
            "statuses": {"terms": {"field": "status", "size": 10, "missing": NO_STATUS}},
        })

    return body


COLLAPSED_TOTAL = "sections"
"""Aggregation name holding the distinct-section count under a collapse.

Approximate above 40,000 distinct values by construction — `cardinality` is
HyperLogLog++ — and the threshold is set past the 65,938 sections in the corpus
only in the sense that no realistic query reaches it. A count that is right to
within a fraction of a percent on the widest possible search, and exact on every
ordinary one, beats a count pinned at 10,000."""

NO_STATUS = "none"
"""What `status:` means for a section the source gives no `@status` at all —
which is most of the Code. `@status` is not a closed set and not section-only
(gotcha 13), so this is a bucket name rather than a value the corpus contains."""


def _status_filter(values: Iterable[str]) -> dict[str, Any]:
    """`status:repealed` is a term; `status:none` is the absence of one."""
    wanted = list(values)
    if NO_STATUS not in wanted:
        return {"terms": {"status": wanted}}
    clauses: list[dict[str, Any]] = [{"bool": {"must_not": {"exists": {"field": "status"}}}}]
    rest = [value for value in wanted if value != NO_STATUS]
    if rest:
        clauses.append({"terms": {"status": rest}})
    return {"bool": {"should": clauses, "minimum_should_match": 1}}


def _sort_clause(sort: str) -> list[Any]:
    if sort == "citation":
        # Missing last: a document with no `sort_key` has an identifier this
        # module could not read a title out of, and it belongs at the end rather
        # than at the top of the Code.
        return [{"sort_key": {"order": "asc", "missing": "_last"}}, "_score"]
    if sort == "recent":
        return [{"first_release_seq": {"order": "desc", "missing": "_last"}}, "_score"]
    return ["_score"]


def build_earlier_versions_body(
    parsed: ParsedQuery,
    identifiers: list[str],
    *,
    profile: Profile = DEPLOYED,
) -> dict[str, Any]:
    """How many superseded versions of each of these sections also match.

    A second, cheap request rather than a wider first one. Searching every
    version and collapsing would answer this in one query, but it also changes
    what a result *is*: a section whose current text no longer contains the
    words would become a hit. Keeping the default over the text in force and
    counting the rest separately says "this section used to say that" without
    letting it displace a section that says it now.

    Bounded to the identifiers on the page, so the cost does not grow with the
    result count.
    """
    must: list[dict[str, Any]] = []
    if parsed.text:
        must.append(_text_clause(parsed.text, profile.fields))
    for term in parsed.heading_terms:
        must.append(_text_clause(term, ["heading"]))
    query: dict[str, Any] = {
        "bool": {
            "filter": [
                {"terms": {"identifier": identifiers}},
                {"term": {"is_current": False}},
            ]
        }
    }
    if must:
        query["bool"]["must"] = must
    return {
        "size": 0,
        "query": query,
        "aggs": {
            "by_identifier": {
                "terms": {"field": "identifier", "size": len(identifiers)}
            }
        },
    }
