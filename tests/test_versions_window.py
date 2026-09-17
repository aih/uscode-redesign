"""A section's history between two dates (ADR-0084).

Two layers under test:

  * `versions_in_window` — the pure cut of a timeline to `[start, end]` by
    release-point `seq`, shared by every `Repository` implementation. No
    database.
  * `GET /sections/{identifier}/versions?from=&to=` — the two ends resolved
    the way `?date=` resolves everywhere, `changed`, the kinds that arrived,
    the diff, the 422s, the 404 before a section existed, and the diff
    route's rate limit. These need the loaded database and skip without it.

Fixture facts (BUILDLOG 006, ADR-0074): /us/usc/t16/s2201 differs between
119-99 (2026-06-12) and 119-102not101 (2026-07-12) and the transition is
`text`; /us/usc/t16/s45f is identical at both.
"""

import datetime

import pytest

from storage.repository import ReleaseRef, SectionVersionInfo, versions_in_window

AMENDED = "/us/usc/t16/s2201"
UNCHANGED = "/us/usc/t16/s45f"
PRIOR_DATE = "2026-06-12"
CURRENT_DATE = "07/12/2026"
PRIOR = "119-99"
CURRENT = "119-102not101"


def _rp(seq: int) -> ReleaseRef:
    return ReleaseRef(
        label=f"119-{seq}",
        currency_date=datetime.date(2026, 1, 1) + datetime.timedelta(days=seq),
        seq=seq,
        congress=119,
        law_num=seq,
    )


def _entry(content: str, seqs: list[int], kind: str | None) -> SectionVersionInfo:
    published = tuple(_rp(seq) for seq in seqs)
    return SectionVersionInfo(
        content_hash=content * 32,
        first_seen=published[0],
        releases=tuple(rp.label for rp in published),
        num="1",
        heading="Specimen",
        status=None,
        published=published,
        change_kind=kind,
    )


# ------------------------------------------------------------------ the cut


def test_the_window_starts_with_the_entry_in_force_at_start_and_lists_each_arrival():
    a = _entry("a", [1, 2, 3], "initial")
    b = _entry("b", [4, 5], "notes")
    c = _entry("c", [6, 7, 8], "text")

    window = versions_in_window([a, b, c], _rp(2), _rp(7))

    # `a` began before the window and is the baseline; `b` and `c` arrived in it.
    assert [v.content_hash for v in window.versions] == [a.content_hash, b.content_hash, c.content_hash]
    assert window.change_kinds == ("notes", "text")
    assert window.changed is True


def test_a_window_inside_one_entry_reports_no_change():
    a = _entry("a", [1, 2, 3, 4], "initial")
    b = _entry("b", [5], "text")

    window = versions_in_window([a, b], _rp(2), _rp(4))

    assert [v.content_hash for v in window.versions] == [a.content_hash]
    assert window.change_kinds == ()
    assert window.changed is False


def test_a_start_between_release_points_takes_the_entry_in_force_before_it():
    """A date resolves to a release point the title may not be loaded at
    (gotcha 10); the entry in force is the one mapped nearest before it."""
    a = _entry("a", [1, 2], "initial")
    b = _entry("b", [6], "text")

    window = versions_in_window([a, b], _rp(4), _rp(6))

    assert [v.content_hash for v in window.versions] == [a.content_hash, b.content_hash]
    assert window.change_kinds == ("text",)


def test_recurring_content_is_followed_where_the_map_says_it_was():
    """ADR-0021: one stored content mapped before and again after another. The
    walk is over the map, so the return counts as a version in force."""
    a = _entry("a", [1, 2, 5, 6], "initial")
    b = _entry("b", [3, 4], "text")

    window = versions_in_window([a, b], _rp(1), _rp(6))

    assert [v.content_hash for v in window.versions] == [
        a.content_hash,
        b.content_hash,
        a.content_hash,
    ]
    # The return carries `a`'s own kind, `initial`, which is the recorded cost.
    assert window.change_kinds == ("text", "initial")
    # Same content at both ends: not a change, whatever happened in between.
    assert window.changed is False


def test_a_section_absent_at_start_begins_with_its_arrival():
    a = _entry("a", [5, 6], "initial")

    window = versions_in_window([a], _rp(1), _rp(6))

    assert [v.content_hash for v in window.versions] == [a.content_hash]
    assert window.change_kinds == ("initial",)
    # One entry, so the cut cannot call it a change; the route does, from the
    # missing text at `start`.
    assert window.changed is False


def test_an_unannotated_corpus_contributes_no_kinds():
    a = _entry("a", [1], None)
    b = _entry("b", [2], None)

    window = versions_in_window([a, b], _rp(1), _rp(2))

    assert window.change_kinds == ()
    assert window.changed is True


# ------------------------------------------------------------- the route


@pytest.mark.integration
def test_a_section_that_changed_between_two_dates_says_so(client):
    body = client.get(
        f"/api/v1/sections{AMENDED}/versions?from={PRIOR_DATE}&to={CURRENT_DATE}"
    ).json()

    window = body["window"]
    assert window["changed"] is True
    assert window["change_kinds"] == ["text"]
    # Both date forms are accepted, and each end says what it resolved to.
    assert window["from"]["date"] == "2026-06-12"
    assert window["from"]["release"]["label"] == PRIOR
    assert window["from"]["exists"] is True
    assert window["from"]["served_from"]["label"] == PRIOR
    assert window["to"]["date"] == "2026-07-12"
    assert window["to"]["exists"] is True
    assert window["to"]["served_from"]["label"] == CURRENT
    assert window["from"]["content_hash"] != window["to"]["content_hash"]
    # The redline is the diff route's, guids stripped.
    assert any(op["op"] != "equal" for op in window["diff"])
    # `versions` is the cut: the text in force at `from`, then the arrival.
    assert [v["first_release"]["label"] for v in body["versions"]][-1] == CURRENT
    assert body["versions"][-1]["change_kind"] == "text"
    assert body["versions"][-1]["last_release"]["currency_date"] == "2026-07-12"


@pytest.mark.integration
def test_the_caveat_of_a_partial_release_point_rides_on_the_end_it_resolves_to(client):
    """Gotcha 5: at 119-102not101 the text is not current through 07/12/2026,
    and a window that ends there has to say so on that end."""
    body = client.get(
        f"/api/v1/sections{AMENDED}/versions?from={PRIOR_DATE}&to={CURRENT_DATE}"
    ).json()

    served = body["window"]["to"]["served_from"]
    assert served["is_partial"] is True
    assert "except" in served["caveat"]
    assert body["versions"][-1]["last_release"]["caveat"] == served["caveat"]


@pytest.mark.integration
def test_an_unchanged_section_says_no_change_and_has_an_all_equal_diff(client):
    body = client.get(
        f"/api/v1/sections{UNCHANGED}/versions?from={PRIOR_DATE}&to={CURRENT_DATE}"
    ).json()

    window = body["window"]
    assert window["changed"] is False
    assert window["change_kinds"] == []
    assert window["from"]["content_hash"] == window["to"]["content_hash"]
    assert all(op["op"] == "equal" for op in window["diff"])
    assert len(body["versions"]) == 1


@pytest.mark.integration
def test_to_defaults_to_today(client):
    body = client.get(f"/api/v1/sections{AMENDED}/versions?from={PRIOR_DATE}").json()

    assert body["window"]["to"]["date"] == datetime.date.today().isoformat()
    assert body["window"]["changed"] is True


@pytest.mark.integration
def test_the_plain_timeline_carries_no_window_and_dates_every_entry(client):
    body = client.get(f"/api/v1/sections{AMENDED}/versions").json()

    assert body["window"] is None
    for entry in body["versions"]:
        assert entry["first_release"]["label"] == entry["releases"][0]
        assert entry["last_release"]["label"] == entry["releases"][-1]
        assert entry["first_release"]["currency_date"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "query, fragment",
    [
        (f"to={CURRENT_DATE}", "needs a `from`"),
        (f"from={CURRENT_DATE}&to={PRIOR_DATE}", "is after"),
        ("from=yesterday", "not YYYY-MM-DD or MM/DD/YYYY"),
    ],
)
def test_a_malformed_window_is_a_422_that_says_why(client, query, fragment):
    response = client.get(f"/api/v1/sections{AMENDED}/versions?{query}")

    assert response.status_code == 422
    assert fragment in response.json()["detail"]


@pytest.mark.integration
def test_a_window_before_the_first_release_point_is_a_404_naming_the_earliest(client):
    response = client.get(
        f"/api/v1/sections{AMENDED}/versions?from=2001-01-01&to={PRIOR_DATE}"
    )

    assert response.status_code == 404
    assert "earliest" in response.json()["detail"]


@pytest.mark.integration
def test_a_window_on_a_structural_node_is_a_404(client):
    response = client.get(f"/api/v1/sections/us/usc/t16/ch1/versions?from={PRIOR_DATE}")

    assert response.status_code == 404


@pytest.mark.integration
def test_a_window_on_a_provision_path_resolves_to_its_section(client):
    body = client.get(
        f"/api/v1/sections{AMENDED}/b/1/versions?from={PRIOR_DATE}&to={CURRENT_DATE}"
    ).json()

    assert body["identifier"] == f"{AMENDED}/b/1"
    assert body["window"]["changed"] is True


@pytest.mark.integration
def test_the_windowed_form_shares_the_diff_limit_and_the_plain_form_does_not(client):
    plain = f"/api/v1/sections{UNCHANGED}/versions"
    windowed = f"{plain}?from={PRIOR_DATE}&to={CURRENT_DATE}"

    assert 429 not in [client.get(plain).status_code for _ in range(40)]
    assert 429 in [client.get(windowed).status_code for _ in range(40)]
