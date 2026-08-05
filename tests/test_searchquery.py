"""What a query string means, and what it becomes — ADR-0049.

`tests/test_search.py` covers the endpoint's contract with a mocked cluster.
This covers the module underneath it, which is the part `scripts/search_eval.py`
also runs: if the parser and the body builder are wrong, the measurement is
wrong in exactly the same way and agrees with itself.
"""

import pytest

from storage.searchquery import (
    COLLAPSED_TOTAL,
    CANDIDATES,
    DEPLOYED,
    NO_STATUS,
    SCOPE_FIELDS,
    build_earlier_versions_body,
    build_search_body,
    parse_query,
    unparse_query,
    with_filter,
    without_filter,
)


def filters_of(body) -> list:
    return body["query"]["bool"]["filter"]


def must_of(body) -> list:
    return body["query"]["bool"].get("must", [])


class TestParsing:
    def test_a_plain_query_is_all_text(self):
        parsed = parse_query("navigable waters")
        assert parsed.text == "navigable waters"
        assert parsed.filters == {}

    def test_a_scope_is_lifted_out_of_the_text(self):
        parsed = parse_query("conservation title:16")
        assert parsed.text == "conservation"
        assert parsed.filters == {"title_num": ("16",)}

    def test_a_quoted_value_survives_its_prefix(self):
        """The tokenizer's first alternative earns its place here.

        `"[^"]*"|\\S+` only recognises a quoted run when the quote opens the
        token, so this parsed to a scope value of `"wild` plus a stray `horses"`
        in the free text — a valid query meaning something else.
        """
        parsed = parse_query('heading:"wild horses"')
        assert parsed.heading_terms == ("wild horses",)
        assert parsed.text == ""

    def test_a_bare_phrase_is_still_a_phrase(self):
        parsed = parse_query('"navigable waters" title:33')
        assert parsed.text == '"navigable waters"'
        assert parsed.filters == {"title_num": ("33",)}

    def test_an_unknown_prefix_stays_in_the_text(self):
        # Forgiveness, for the reason ADR-0031 chose `simple_query_string`: a
        # reader's colon should not turn into an empty result set.
        assert parse_query("see: also").text == "see: also"

    def test_a_scope_with_no_value_stays_in_the_text(self):
        assert parse_query("water title:").text == "water title:"

    def test_a_title_is_accepted_both_ways(self):
        assert parse_query("x title:t16").filters == {"title_num": ("16",)}
        assert parse_query("x title:16").filters == {"title_num": ("16",)}

    def test_repeated_values_of_one_field_are_kept(self):
        assert parse_query("x title:16 title:33").filters == {"title_num": ("16", "33")}

    def test_time_scopes_are_extracted_not_resolved(self):
        # Resolution is the Repository's (architecture rule 1); this module
        # only reports what was asked for.
        parsed = parse_query("conservation release:119-99 date:07/12/2026")
        assert (parsed.release, parsed.date) == ("119-99", "07/12/2026")

    def test_a_query_of_only_scopes_is_not_empty(self):
        assert not parse_query("title:16").is_empty()

    def test_a_query_of_nothing_is_empty(self):
        assert parse_query("   ").is_empty()


class TestRoundTrip:
    @pytest.mark.parametrize(
        "query",
        [
            "conservation title:16",
            'heading:"wild horses"',
            "conservation status:repealed release:119-99",
            "water title:16 title:33",
        ],
    )
    def test_unparse_reproduces_a_query_that_parses_the_same(self, query):
        assert parse_query(unparse_query(parse_query(query))) == parse_query(query)

    def test_adding_a_filter_is_idempotent(self):
        once = with_filter(parse_query("water"), "title", "16")
        assert with_filter(once, "title", "t16") == once

    def test_removing_the_last_value_removes_the_field(self):
        parsed = with_filter(parse_query("water"), "title", "16")
        assert without_filter(parsed, "title", "16").filters == {}


class TestBody:
    def test_the_default_reads_the_text_in_force(self):
        body = build_search_body(parse_query("conservation"))
        assert {"term": {"is_current": True}} in filters_of(body)
        assert "collapse" not in body

    def test_a_release_switches_to_point_in_time_and_collapses(self):
        body = build_search_body(parse_query("conservation"), release_seq=379)
        assert {"range": {"first_release_seq": {"lte": 379}}} in filters_of(body)
        assert {"term": {"is_current": True}} not in filters_of(body)
        assert body["collapse"]["field"] == "identifier"

    def test_a_title_scope_becomes_a_filter_not_a_search_term(self):
        body = build_search_body(parse_query("conservation title:16"))
        assert {"terms": {"title_num": ["16"]}} in filters_of(body)
        assert "title" not in str(must_of(body))

    def test_a_heading_scope_becomes_its_own_clause(self):
        body = build_search_body(parse_query("heading:conservation"))
        clause = must_of(body)[0]["simple_query_string"]
        assert clause["fields"] == ["heading"]
        assert clause["query"] == "conservation"

    def test_status_none_is_the_absence_of_a_status(self):
        body = build_search_body(parse_query(f"x status:{NO_STATUS}"))
        clause = next(f for f in filters_of(body) if "bool" in f)
        assert {"bool": {"must_not": {"exists": {"field": "status"}}}} in clause["bool"][
            "should"
        ]

    def test_status_none_combines_with_a_real_status(self):
        body = build_search_body(parse_query(f"x status:repealed status:{NO_STATUS}"))
        clause = next(f for f in filters_of(body) if "bool" in f)
        assert {"terms": {"status": ["repealed"]}} in clause["bool"]["should"]

    def test_the_phrase_boost_is_a_should_not_a_must(self):
        # It reorders results; it must never remove one. A `must` would turn
        # every two-word search into a phrase search.
        body = build_search_body(parse_query("navigable waters"), profile=CANDIDATES["phrase"])
        assert any("match_phrase" in c for c in body["query"]["bool"]["should"])
        assert not any("match_phrase" in c for c in must_of(body))

    def test_no_phrase_clause_for_a_single_word(self):
        body = build_search_body(parse_query("conservation"), profile=CANDIDATES["phrase"])
        assert not body["query"]["bool"].get("should")

    def test_no_phrase_clause_when_the_query_carries_operators(self):
        """`match_phrase` has no operator syntax, so boosting `forest | grassland`
        as a phrase would score the literal word `|` — rewarding nothing, and
        doing it invisibly."""
        body = build_search_body(
            parse_query("forest | grassland"), profile=CANDIDATES["phrase"]
        )
        assert not body["query"]["bool"].get("should")

    def test_the_deployed_profile_is_the_old_weighting(self):
        body = build_search_body(parse_query("conservation"), profile=DEPLOYED)
        assert body["query"]["bool"]["must"][0]["simple_query_string"]["fields"] == [
            "heading^4",
            "xml_text",
        ]

    @pytest.mark.parametrize("sort,field", [("citation", "sort_key"), ("recent", "first_release_seq")])
    def test_an_explicit_sort_replaces_the_score(self, sort, field):
        body = build_search_body(parse_query("conservation"), sort=sort)
        assert body["sort"][0][field]["missing"] == "_last"

    def test_relevance_sends_no_sort_at_all(self):
        assert "sort" not in build_search_body(parse_query("conservation"))

    def test_facets_count_titles_and_statuses(self):
        body = build_search_body(parse_query("conservation"), facets=True)
        assert body["aggs"]["titles"]["terms"]["field"] == "title_num"
        # Without `missing`, the ordinary operative section — most of the Code —
        # is in no bucket, and the status facet reads as though the corpus were
        # nothing but repealed provisions.
        assert body["aggs"]["statuses"]["terms"]["missing"] == NO_STATUS

    def test_every_scope_field_is_reachable_from_a_query(self):
        """Guards the parse table itself: a name added to `SCOPE_FIELDS` and to
        no branch of `parse_query` would be silently searched as text."""
        for name in SCOPE_FIELDS:
            parsed = parse_query(f"{name}:x")
            assert parsed.text == "", f"{name}: fell through to the free text"


class TestEarlierVersions:
    def test_it_counts_superseded_versions_of_the_page(self):
        body = build_earlier_versions_body(parse_query("conservation"), ["/us/usc/t16/s1"])
        assert body["size"] == 0
        assert {"term": {"is_current": False}} in body["query"]["bool"]["filter"]
        assert {"terms": {"identifier": ["/us/usc/t16/s1"]}} in body["query"]["bool"]["filter"]

    def test_the_aggregation_is_bounded_by_the_page(self):
        # Not by the result count: this runs on every default search, so its
        # cost must not grow with `total`.
        ids = [f"/us/usc/t16/s{n}" for n in range(20)]
        body = build_earlier_versions_body(parse_query("x"), ids)
        assert body["aggs"]["by_identifier"]["terms"]["size"] == 20


class TestCounting:
    def test_the_total_is_not_capped(self):
        """OpenSearch stops counting at 10,000 unless told otherwise and reports
        the cap as the answer, so every broad search claimed exactly 10,000
        results."""
        assert build_search_body(parse_query("conservation"))["track_total_hits"] is True

    def test_a_collapsed_search_counts_sections_not_versions(self):
        # `hits.total` counts documents whether or not the results were
        # collapsed, so a point-in-time search reported its matching versions
        # while listing one row per section.
        body = build_search_body(parse_query("conservation"), release_seq=379)
        assert body["aggs"][COLLAPSED_TOTAL]["cardinality"]["field"] == "identifier"

    def test_an_uncollapsed_search_needs_no_such_count(self):
        body = build_search_body(parse_query("conservation"))
        assert COLLAPSED_TOTAL not in body.get("aggs", {})

    def test_the_facets_survive_alongside_it(self):
        # Both write into `aggs`; the first one to assign used to win.
        body = build_search_body(parse_query("x"), release_seq=379, facets=True)
        assert {"titles", "statuses", COLLAPSED_TOTAL} <= set(body["aggs"])
