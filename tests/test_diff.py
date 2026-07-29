"""`api/diff.py` — a generic text diff, and the `/diff` endpoint that serves it.

docs/adr/0016 records the placement: the diff computes here, through the
Repository, because it needs no USLM vocabulary — only presentation (wrapping
`ops` in `<ins>`/`<del>`) belongs to `frontend/src/lib`.
"""

import pytest

from api.diff import DiffOp, diff_ops

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
