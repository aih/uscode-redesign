"""`api/diff.py` — a generic text diff, and the `/diff` endpoint that serves it.

docs/adr/0016 records the placement: the diff computes here, through the
Repository, because it needs no USLM vocabulary — only presentation (wrapping
`ops` in `<ins>`/`<del>`) belongs to `frontend/src/lib`.
"""

import pytest

from api.diff import DiffOp, cached_diff_ops, clear_diff_cache, diff_ops, strip_guids

# ---------------------------------------------------------------- diff_ops()


def test_identical_text_is_one_equal_chunk_no_diffing_done():
    assert diff_ops("<section>same</section>", "<section>same</section>") == [
        DiffOp(op="equal", text="<section>same</section>")
    ]


def test_two_empty_strings_produce_no_chunks():
    assert diff_ops("", "") == []


def test_an_insertion_is_isolated_from_the_unchanged_text_around_it():
    ops = diff_ops("<p>The Secretary shall act.</p>", "<p>The Secretary shall promptly act.</p>")

    kinds = [op.op for op in ops]
    assert "insert" in kinds
    assert "equal" in kinds
    inserted = "".join(op.text for op in ops if op.op == "insert")
    assert "promptly" in inserted


def test_a_deletion_is_isolated_from_the_unchanged_text_around_it():
    ops = diff_ops("<p>The Secretary shall promptly act.</p>", "<p>The Secretary shall act.</p>")

    deleted = "".join(op.text for op in ops if op.op == "delete")
    assert "promptly" in deleted


def test_reassembling_either_side_from_its_ops_recovers_the_original():
    from_text = "<p>Alpha Bravo Charlie</p>"
    to_text = "<p>Alpha Delta Charlie</p>"
    ops = diff_ops(from_text, to_text)

    assert "".join(op.text for op in ops if op.op in ("equal", "delete")) == from_text
    assert "".join(op.text for op in ops if op.op in ("equal", "insert")) == to_text


# --------------------------------------------------------------- /diff route


AMENDED = "/us/usc/t16/s2201"  # differs between the two fixture release points
SECTION = "/us/usc/t16/s45f"
PRIOR = "119-99"
CURRENT = "119-102not101"
API = "/api/v1"


@pytest.mark.integration
def test_diff_of_a_changed_section_has_both_an_insertion_and_a_deletion(client):
    body = client.get(f"{API}/sections{AMENDED}/diff?from={PRIOR}&to={CURRENT}").json()

    assert body["identifier"] == AMENDED
    assert body["from"]["release"]["label"] == PRIOR
    assert body["to"]["release"]["label"] == CURRENT
    kinds = {op["op"] for op in body["ops"]}
    assert "equal" in kinds
    assert kinds & {"insert", "delete"}


@pytest.mark.integration
def test_diff_of_an_unchanged_section_is_all_equal(client):
    body = client.get(f"{API}/sections{SECTION}/diff?from={PRIOR}&to={CURRENT}").json()

    assert all(op["op"] == "equal" for op in body["ops"])
    assert body["from"]["content_hash"] == body["to"]["content_hash"]


@pytest.mark.integration
def test_diffing_an_unknown_release_point_is_a_404(client):
    response = client.get(f"{API}/sections{SECTION}/diff?from=not-a-release&to={CURRENT}")

    assert response.status_code == 404


# ------------------------------------------------- guid churn, and the cache
#
# Guids regenerate at every release point by design (ADR-0003, gotcha 1), so
# they are the one part of a section's XML guaranteed to differ between any two
# release points whether or not a word of law changed. ADR-0066 drops them
# before diffing, by default.


def test_stripping_guids_removes_every_id_and_nothing_else():
    xml = (
        '<section identifier="/us/usc/t16/s1" id="idAAA">'
        '<num id="idBBB" value="1">§ 1.</num>'
        "<content>Text with an id= mention.</content>"
        "</section>"
    )
    stripped = strip_guids(xml)

    assert "idAAA" not in stripped
    assert "idBBB" not in stripped
    # Everything that is not an `@id` survives, including an `id=` inside text.
    assert 'identifier="/us/usc/t16/s1"' in stripped
    assert 'value="1"' in stripped
    assert "Text with an id= mention." in stripped


def test_two_fragments_differing_only_in_guids_diff_to_nothing_once_stripped():
    """The whole point. Under ADR-0007's dedupe this is the ordinary case."""
    before = '<section id="id111"><content id="id222">Same words.</content></section>'
    after = '<section id="id999"><content id="id888">Same words.</content></section>'

    assert diff_ops(before, after) != [DiffOp(op="equal", text=before)]
    assert diff_ops(strip_guids(before), strip_guids(after)) == [
        DiffOp(op="equal", text=strip_guids(before))
    ]


def test_stripping_a_fragment_that_does_not_parse_returns_it_unchanged():
    """An optimisation that can fail a request is worse than the cost it saves."""
    assert strip_guids("<section><unclosed>") == "<section><unclosed>"


def test_the_cache_answers_the_second_call_without_diffing_again():
    clear_diff_cache()
    key = ("/us/usc/t16/s1", "119-99", "119-102not101", True)

    first = cached_diff_ops(key, "one two three", "one four three")
    # Different inputs under the same key: a second computation would produce a
    # different answer, so an identical one proves nothing was recomputed.
    second = cached_diff_ops(key, "totally", "different")

    assert second is first
    clear_diff_cache()


def test_the_cache_keys_on_the_mode_as_well_as_the_pair():
    """`guids=strip` and `guids=keep` are two different answers to one URL."""
    clear_diff_cache()
    stripped = cached_diff_ops(("/x", "a", "b", True), "one two", "one three")
    kept = cached_diff_ops(("/x", "a", "b", False), "one two", "one four")

    assert stripped is not kept
    clear_diff_cache()


@pytest.mark.integration
def test_the_diff_endpoint_strips_guids_by_default_and_says_so(client):
    body = client.get(f"{API}/sections{AMENDED}/diff?from={PRIOR}&to={CURRENT}").json()
    assert body["guids"] == "strip"


@pytest.mark.integration
def test_keeping_guids_is_available_and_reports_more_ops(client):
    """The verbatim behaviour is still reachable — the reader links to this
    endpoint for the bytes — and the response names which one it gave."""
    stripped = client.get(f"{API}/sections{AMENDED}/diff?from={PRIOR}&to={CURRENT}").json()
    kept = client.get(
        f"{API}/sections{AMENDED}/diff?from={PRIOR}&to={CURRENT}&guids=keep"
    ).json()

    assert kept["guids"] == "keep"
    assert len(kept["ops"]) > len(stripped["ops"])


@pytest.mark.integration
def test_keeping_guids_still_reassembles_the_stored_xml(client):
    """`guids=keep` is the contract ADR-0016 wrote: the ops rebuild both sides
    verbatim. `strip` cannot promise that and does not claim to."""
    body = client.get(
        f"{API}/sections{AMENDED}/diff?from={PRIOR}&to={CURRENT}&guids=keep"
    ).json()

    before = "".join(op["text"] for op in body["ops"] if op["op"] in {"equal", "delete"})
    after = "".join(op["text"] for op in body["ops"] if op["op"] in {"equal", "insert"})
    section = client.get(f"{API}{AMENDED}?release={PRIOR}").json()
    assert before == section["xml"]
    assert after == client.get(f"{API}{AMENDED}?release={CURRENT}").json()["xml"]
