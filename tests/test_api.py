"""API integration tests against the loaded Title 16, at both release points.

These talk to the real Postgres from `docker compose` and skip cleanly when it
isn't there or hasn't been ingested, so `make test` stays green on a fresh clone.
They are the contract the XCiteDB repository will have to satisfy too: nothing
here knows a table name.

Fixture facts they rely on (BUILDLOG 006):
  * Title 16 at 119-99 (06/12/2026) and 119-102not101 (07/12/2026).
  * 119-100 (06/26/2026) sits between them and changed only title 47.
  * /us/usc/t16/s2201 and /us/usc/t16/s2206 are the only two sections that differ.
"""

import re

import pytest

pytestmark = pytest.mark.integration

DEMO = "/us/usc/t16/s45f/c/5"
SECTION = "/us/usc/t16/s45f"
S45F_C5_GUID_AT_CURRENT = "id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd"
CURRENT = "119-102not101"
PRIOR = "119-99"
BETWEEN = "119-100"  # published, ingested for no title, changed only title 47
AMENDED = "/us/usc/t16/s2201"
API = "/api/v1"  # the machine surface; the bare citation URL only redirects here


# ------------------------------------------------------------------ identifiers


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_the_plan_demo_url(client):
    """PLAN §10's definition of done: a provision, by date, in context."""
    response = client.get(f"{API}{DEMO}?date=07/12/2026")
    body = response.json()

    assert response.status_code == 200
    assert body["identifier"] == SECTION  # the section, not the paragraph alone
    assert body["heading"] == "Mineral King Valley addition authorized"
    assert body["provision"]["identifier"] == DEMO
    assert body["provision"]["found"] is True
    assert body["release"]["label"] == CURRENT
    assert body["served_from"]["label"] == CURRENT


def test_iso_and_us_dates_agree(client):
    """`07/12/2026` is the form uscode.house.gov prints and PLAN §10 demos."""
    us = client.get(f"{API}{SECTION}?date=07/12/2026").json()
    iso = client.get(f"{API}{SECTION}?date=2026-07-12").json()

    assert us["served_from"]["label"] == iso["served_from"]["label"] == CURRENT


def test_a_date_between_release_points_resolves_backwards(client):
    body = client.get(f"{API}{SECTION}?date=2026-06-20").json()

    assert body["release"]["label"] == PRIOR
    assert "falls between release points" in body["note"]


def test_a_date_before_the_first_release_point_is_404(client):
    response = client.get(f"{API}{SECTION}?date=1999-01-01")

    assert response.status_code == 404
    assert "no release point on or before" in response.json()["detail"]


def test_a_malformed_date_is_422(client):
    assert client.get(f"{API}{SECTION}?date=yesterday").status_code == 422


def test_the_not_caveat_is_surfaced_not_just_the_date(client):
    """Gotcha 5: at 119-102not101 the text is *not* current through 07/12/2026 —
    Public Law 119-101 is excluded, and a date alone would hide that."""
    response = client.get(f"{API}{SECTION}?release={CURRENT}")
    body = response.json()

    assert body["release"]["is_partial"] is True
    assert body["release"]["excluded_laws"] == [101]
    assert "except 119-101" in body["release"]["caveat"]
    assert "except 119-101" in response.headers["x-release-caveat"]


def test_a_bare_label_resolves_with_a_note(client):
    """`119-102` was never published on its own; `119-102not101` was."""
    body = client.get(f"{API}{SECTION}?release=119-102").json()

    assert body["release"]["label"] == CURRENT
    assert "was published as 119-102not101" in body["note"]


def test_an_unknown_label_is_404(client):
    assert client.get(f"{API}{SECTION}?release=42-1").status_code == 404


def test_a_release_point_we_never_ingested_answers_from_the_one_before_it(client):
    """119-100 exists and changed only title 47, so Title 16's text at 119-100 *is*
    its text at 119-99. Answering is right; answering silently would not be."""
    response = client.get(f"{API}{SECTION}?release={BETWEEN}")
    body = response.json()

    assert response.status_code == 200
    assert body["release"]["label"] == BETWEEN
    assert body["served_from"]["label"] == PRIOR
    assert body["is_exact"] is False
    assert "not ingested" in body["note"]
    assert response.headers["x-served-from"] == PRIOR


def test_an_amended_section_differs_between_the_two_release_points(client):
    old = client.get(f"{API}{AMENDED}?release={PRIOR}").json()
    new = client.get(f"{API}{AMENDED}?release={CURRENT}").json()

    assert old["xml"] != new["xml"]
    assert len(new["xml"]) > len(old["xml"])
    assert old["content_first_seen"]["label"] == PRIOR
    assert new["content_first_seen"]["label"] == CURRENT


def test_an_unchanged_section_is_stored_once_and_served_at_both(client):
    """ADR-0007: identical content deduped across release points. The bytes come
    from the release point they first appeared at, and the response says so."""
    old = client.get(f"{API}{SECTION}?release={PRIOR}").json()
    new = client.get(f"{API}{SECTION}?release={CURRENT}").json()

    assert old["xml"] == new["xml"]
    assert new["content_first_seen"]["label"] == PRIOR
    assert new["served_from"]["label"] == CURRENT


def test_a_missing_section_404s_naming_the_release_point(client):
    response = client.get(f"{API}/us/usc/t16/s9999")

    assert response.status_code == 404
    assert "119-102not101" in response.json()["detail"]


# ---------------------------------------------------------------------- formats


def test_xml_format_returns_the_requested_fragment_verbatim(client):
    section = client.get(f"{API}{SECTION}?format=xml")
    provision = client.get(f"{API}{DEMO}?format=xml")

    assert section.headers["content-type"].startswith("application/xml")
    assert section.text.startswith("<section")
    assert provision.text.startswith("<paragraph")
    assert f'identifier="{DEMO}"' in provision.text


def test_accept_header_negotiates_xml(client):
    response = client.get(API + SECTION, headers={"Accept": "application/xml"})

    assert response.headers["content-type"].startswith("application/xml")
    assert response.text.startswith("<section")


def test_a_browser_aimed_at_the_api_gets_a_machine_format_never_a_template(client):
    """ADR-0010: `/api/v1` serves machine formats only.

    Chrome's header asks for HTML at q=1 and XML at q=0.9, so with HTML off this
    surface's menu the honest answer is XML — the client did say it accepts it,
    and ranked it above the `*/*` that covers JSON. What must never happen is a
    template: the reader is at `/app`, and the bare citation URL exists precisely
    so that nobody has to arrive here by hand.
    """
    chrome = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    response = client.get(f"{API}{SECTION}", headers={"accept": chrome})

    assert response.headers["content-type"].startswith("application/xml")
    assert "<!doctype html>" not in response.text
    assert client.get(f"{API}{SECTION}?format=json").json()["identifier"] == SECTION


def test_etag_is_the_content_hash_and_is_stable(client):
    first = client.get(API + SECTION)
    again = client.get(f"{API}{SECTION}?release={CURRENT}")

    assert first.headers["etag"] == again.headers["etag"]
    assert len(first.headers["etag"].strip('"')) == 64


# ---------------------------------------------------------------------- caching

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "public, max-age=300"


def test_a_pinned_release_point_is_cacheable_forever(client):
    """ADR-0018: `?release=119-102not101` can never mean a different release
    point, so what it answers can never change."""
    response = client.get(f"{API}{SECTION}?release={CURRENT}")

    assert response.headers["cache-control"] == IMMUTABLE


def test_an_unpinned_request_is_never_cacheable_forever(client):
    """The heart of ADR-0018. Without a release point the answer is "newest
    ingested at or before now" — which changes the moment a newer release point
    is loaded. Caching that `immutable` would pin superseded law into caches
    with no way to invalidate it."""
    for url in (
        f"{API}{SECTION}",  # no release parameter at all
        f"{API}{SECTION}?date=07/12/2026",  # a date, not a release point
    ):
        assert client.get(url).headers["cache-control"] == REVALIDATE, url


def test_a_label_that_resolved_elsewhere_is_not_pinned(client):
    """`119-102` was never published; it resolves to `119-102not101` with a
    note. The URL asked for something that does not exist yet, so its meaning
    can still change — it is not pinned."""
    response = client.get(f"{API}{SECTION}?release=119-102")

    assert response.headers["cache-control"] == REVALIDATE


def test_a_matching_etag_gets_304_with_no_body(client):
    etag = client.get(f"{API}{SECTION}?release={CURRENT}").headers["etag"]

    response = client.get(
        f"{API}{SECTION}?release={CURRENT}", headers={"If-None-Match": etag}
    )

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == etag
    assert response.headers["cache-control"] == IMMUTABLE


def test_conditional_requests_honour_the_full_if_none_match_grammar(client):
    """A comma-separated list, weak validators, and `*` are all legal and all
    mean "I already have it" (RFC 9110 §13.1.2)."""
    etag = client.get(f"{API}{SECTION}?release={CURRENT}").headers["etag"]

    for header in (etag, f"W/{etag}", f'"other", {etag}', "*"):
        response = client.get(
            f"{API}{SECTION}?release={CURRENT}", headers={"If-None-Match": header}
        )
        assert response.status_code == 304, header

    stale = client.get(
        f"{API}{SECTION}?release={CURRENT}", headers={"If-None-Match": '"stale"'}
    )
    assert stale.status_code == 200


def test_a_diff_between_two_pinned_release_points_is_immutable(client):
    response = client.get(
        f"{API}/sections{AMENDED}/diff?from={PRIOR}&to={CURRENT}"
    )

    assert response.headers["cache-control"] == IMMUTABLE


def test_public_routes_are_cacheable(client):
    for url in (f"{API}/us/usc/t16/ch1", f"{API}/releases", f"{API}/titles"):
        assert client.get(url).headers["cache-control"] == REVALIDATE, url


def test_the_signed_in_surfaces_are_never_stored(client):
    """A shared cache holding one reader's watchlist and handing it to the next
    reader is the failure this guards against. It has to hold on the error
    paths too — a raised HTTPException builds a fresh response, so the 401s are
    the case most likely to regress."""
    for url in (f"{API}/auth/me", f"{API}/watchlist", f"{API}/watchlists"):
        response = client.get(url)
        assert response.headers["cache-control"] == "private, no-store", url
        assert response.headers["vary"] == "Cookie", url


# ------------------------------------------------------------------------ guids


def test_guid_lookup_needs_no_release_parameter(client):
    body = client.get(f"{API}/us/usc/?id={S45F_C5_GUID_AT_CURRENT}").json()

    assert body["identifier"] == DEMO
    assert body["release"]["label"] == CURRENT
    assert body["section_identifier"] == SECTION
    assert body["is_section"] is False


def test_the_same_provision_has_a_different_guid_at_each_release_point(client):
    """ADR-0003: a guid pins (provision, release point). It is never cross-release
    identity — that is @identifier's job."""
    old = client.get(f"{API}{SECTION}?release={PRIOR}").json()
    new = client.get(f"{API}{SECTION}?release={CURRENT}").json()

    assert old["guid"] != new["guid"]
    assert (
        client.get(f"{API}/us/usc/?id={old['guid']}").json()["release"]["label"] == PRIOR
    )
    assert (
        client.get(f"{API}/us/usc/?id={new['guid']}").json()["release"]["label"] == CURRENT
    )


def test_an_unknown_guid_is_404(client):
    assert client.get(f"{API}/us/usc/?id=idnope").status_code == 404


# ------------------------------------------------------------------ breadcrumbs


def test_a_section_carries_its_own_breadcrumb_trail(client):
    body = client.get(f"{API}{SECTION}?release={CURRENT}").json()

    assert [entry["identifier"] for entry in body["ancestors"]] == [
        "/us/usc/t16",
        "/us/usc/t16/ch1",
        "/us/usc/t16/ch1/schVI",
    ]
    assert [entry["level"] for entry in body["ancestors"]] == [
        "title",
        "chapter",
        "subchapter",
    ]


def test_the_breadcrumb_is_what_the_parent_toc_used_to_supply(client):
    """PLAN Day 6b: the reader used to fetch the parent's whole table of
    contents and keep two fields of it. This is the equivalence that made
    dropping that call safe — same entries, same order, no `get_toc`."""
    section = client.get(f"{API}{SECTION}?release={CURRENT}").json()
    parent = client.get(
        f"{API}{section['parent_identifier']}?release={CURRENT}"
    ).json()

    was = [*parent["ancestors"], parent["node"]]
    assert [(e["identifier"], e["level"], e["num"], e["heading"]) for e in was] == [
        (e["identifier"], e["level"], e["num"], e["heading"])
        for e in section["ancestors"]
    ]


def test_a_provision_request_carries_the_sections_breadcrumb(client):
    """The URL names (c)(5); the breadcrumb belongs to §45f that contains it."""
    body = client.get(f"{API}{DEMO}?release={CURRENT}").json()

    assert [entry["identifier"] for entry in body["ancestors"]] == [
        "/us/usc/t16",
        "/us/usc/t16/ch1",
        "/us/usc/t16/ch1/schVI",
    ]


# -------------------------------------------------------------------------- toc


def test_title_root_lists_its_chapters(client):
    body = client.get(f"{API}/us/usc/t16").json()

    assert body["node"]["heading"] == "CONSERVATION"
    assert len(body["children"]) == 153
    assert body["children"][0]["identifier"] == "/us/usc/t16/ch1"
    assert body["ancestors"] == []


def test_a_chapter_lists_its_sections_in_reading_order_with_badges(client):
    """Gotcha 9: repealed and omitted sections keep their place, badged."""
    body = client.get(f"{API}/us/usc/t16/ch6").json()
    sections = body["sections"]

    assert body["node"]["level"] == "chapter"
    assert [s["identifier"] for s in sections[:2]] == [
        "/us/usc/t16/s671",
        "/us/usc/t16/s672",
    ]
    assert sections[0]["status"] == "repealed"
    assert sections[1]["status"] == "omitted"
    assert all(s["is_section"] for s in sections)


def test_a_subchapter_carries_its_breadcrumb(client):
    body = client.get(f"{API}/us/usc/t16/ch1/schI").json()

    assert [a["identifier"] for a in body["ancestors"]] == [
        "/us/usc/t16",
        "/us/usc/t16/ch1",
    ]


def test_the_reserved_subchapter_is_retrievable_and_badged(client):
    """Title 16's only `reserved` is on a subchapter, not a section (gotcha 13)."""
    body = client.get(f"{API}/us/usc/t16/ch1?release={CURRENT}").json()
    reserved = [c for c in body["children"] if c["status"] == "reserved"]

    assert [c["identifier"] for c in reserved] == ["/us/usc/t16/ch1/schXCVII"]


# --------------------------------------------------------------------- labels


def test_labels_answers_many_identifiers_in_one_request(client):
    """What the reader needs to put hover text on forty cross references without
    asking forty times."""
    body = client.get(
        f"{API}/labels",
        params={
            "identifier": [SECTION, AMENDED, "/us/usc/t16/s1"],
            "release": CURRENT,
        },
    ).json()

    assert body[SECTION]["num"] == "§ 45f."
    assert body[SECTION]["heading"] == "Mineral King Valley addition authorized"
    assert set(body) == {SECTION, AMENDED, "/us/usc/t16/s1"}


def test_labels_carry_status_so_a_citation_can_be_badged(client):
    """Gotcha 9: an omitted or repealed section is still cited, and the citation
    should say so before the reader follows it. Status is whatever the XML said —
    never an enum (gotcha 13) — so the label repeats it rather than mapping it."""
    body = client.get(
        f"{API}/labels", params={"identifier": ["/us/usc/t16/s672"], "release": CURRENT}
    ).json()
    section = client.get(f"{API}/us/usc/t16/s672?release={CURRENT}").json()

    assert body["/us/usc/t16/s672"]["status"] == "omitted"
    assert body["/us/usc/t16/s672"]["status"] == section["status"]


def test_an_unknown_identifier_is_absent_rather_than_an_error(client):
    """A missing label costs the reader a tooltip, not a page.

    Deliberately asserted with identifiers that can never resolve rather than with
    an un-ingested title: which titles are loaded changes as the backfill lands,
    and a test that reads "Title 54 is absent" is a test that fails the day Title
    54 arrives.
    """
    body = client.get(
        f"{API}/labels",
        params={"identifier": [SECTION, "/us/usc/t16/s9999", "/us/usc/t99/s1"]},
    ).json()

    assert SECTION in body
    assert "/us/usc/t16/s9999" not in body  # no such section in a title we hold
    assert "/us/usc/t99/s1" not in body  # no such title, and never will be


def test_labels_resolve_per_title_not_per_request(client):
    """A release point ingested for Title 16 need not exist for another title, so
    the answer is assembled title by title (gotcha 10)."""
    body = client.get(
        f"{API}/labels",
        params={"identifier": [SECTION], "release": BETWEEN},  # never ingested
    ).json()

    assert body[SECTION]["heading"] == "Mineral King Valley addition authorized"


def test_labels_with_no_identifiers_is_a_422(client):
    """The parameter is required: an empty batch is a caller bug, not an empty
    page of citations."""
    assert client.get(f"{API}/labels").status_code == 422


# ------------------------------------------------------------- neighbors, versions


def test_neighbors_are_the_adjacent_sections_in_reading_order(client):
    body = client.get(f"/api/v1/sections{SECTION}/neighbors").json()

    assert body["previous"]["identifier"] == "/us/usc/t16/s45e"
    assert body["next"]["identifier"] == "/us/usc/t16/s45g"


def test_neighbors_do_not_skip_repealed_sections(client):
    body = client.get("/api/v1/sections/us/usc/t16/s672/neighbors").json()

    assert body["previous"]["identifier"] == "/us/usc/t16/s671"
    assert body["previous"]["status"] == "repealed"


def test_the_first_section_of_a_title_has_no_previous(client):
    body = client.get("/api/v1/sections/us/usc/t16/s1/neighbors").json()

    assert body["previous"] is None
    assert body["next"] is not None


def _fixture_versions(body: dict) -> list[dict]:
    """Versions first seen at one of the two fixture release points.

    A bulk load (`ingest load-all`) adds older release points to the same
    database, so these tests filter to the window they are about rather than
    assuming Title 16 exists at exactly two.
    """
    return [v for v in body["versions"] if v["first_seen"]["label"] in {PRIOR, CURRENT}]


def test_versions_lists_one_entry_per_distinct_text(client):
    amended = _fixture_versions(client.get(f"/api/v1/sections{AMENDED}/versions").json())
    unchanged = _fixture_versions(client.get(f"/api/v1/sections{SECTION}/versions").json())

    assert [v["first_seen"]["label"] for v in amended] == [PRIOR, CURRENT]
    assert [[r for r in v["releases"] if r in {PRIOR, CURRENT}] for v in amended] == [
        [PRIOR],
        [CURRENT],
    ]
    # One text, published at both release points — the dedupe, seen from outside.
    assert len(unchanged) == 1
    assert [r for r in unchanged[0]["releases"] if r in {PRIOR, CURRENT}] == [PRIOR, CURRENT]


def test_versions_of_a_provision_path_resolve_to_its_section(client):
    body = client.get(f"/api/v1/sections{DEMO}/versions").json()

    assert body["identifier"] == DEMO
    assert len(_fixture_versions(body)) == 1


# ------------------------------------------------------------------------ titles


def _in_code_order(nums: list[str]) -> bool:
    """Deliberately *not* `storage.postgres.title_sort_key`.

    This file is the contract the XCiteDB repository will have to satisfy too, and
    a test that imports the implementation's own comparator passes whenever the
    two share a bug. Spelled out here, it is an independent check — and short
    enough that being independent costs nothing.
    """
    keyed = [(int(re.match(r"\d+", n).group()), n.lstrip("0123456789")) for n in nums]
    return keyed == sorted(keyed)


def test_titles_are_listed_in_the_codes_own_order(client):
    """Not string order. `Title.num` is a string, so the obvious `ORDER BY` gives
    `1, 10, 11, 11a, 12, … 2, 20` — the first thing a visitor saw on the front
    page. Asserted as a property rather than a fixed list, because which titles
    are loaded changes as the corpus grows.
    """
    nums = [t["num"] for t in client.get(f"{API}/titles").json()]

    assert nums, "no titles loaded"
    assert _in_code_order(nums)
    # Guarded, like the comparison below it: CI loads Title 16 alone (`make
    # ci-data`), so a bare `nums[0] == "1"` asserts the fixture rather than the
    # ordering — which is what the docstring above says this test is not for.
    # It failed in CI from the day the job existed for exactly that reason.
    if "1" in nums:
        assert nums[0] == "1"
    # The one comparison string order gets wrong at the very top of the list.
    if "2" in nums:
        assert nums.index("2") < nums.index("10")


def test_an_appendix_title_follows_its_parent(client):
    """Gotcha 7: `5a` is a separate title, and it belongs between `5` and `6` —
    not at the end of the list, which is where a string sort puts it."""
    nums = [t["num"] for t in client.get(f"{API}/titles").json()]
    appendices = [n for n in nums if not n.isdigit()]
    if not appendices:
        pytest.skip("no appendix titles loaded")

    for appendix in appendices:
        parent = appendix.rstrip("abcdefghijklmnopqrstuvwxyz")
        if parent in nums:
            assert nums.index(parent) == nums.index(appendix) - 1, appendix


def test_ingested_titles_are_ordered_too(client):
    """The same list, reached by a different route (`/app/releases` renders it),
    and so the same bug — `ingested_titles` is the unpadded form."""
    for release in client.get(f"{API}/releases").json():
        held = release["ingested_titles"]
        assert _in_code_order(held), release["label"]


# ---------------------------------------------------------------------- releases


def test_releases_are_listed_newest_first_with_changed_titles(client):
    releases = client.get("/api/v1/releases").json()

    assert releases[0]["label"] == CURRENT
    assert releases[0]["titles_affected"] == ["05", "16"]
    assert releases[0]["seq"] > releases[1]["seq"]
    assert len(releases) > 300


def test_releases_can_be_filtered_to_a_title(client):
    releases = client.get("/api/v1/releases?title=16").json()
    labels = [r["label"] for r in releases]

    assert labels[:2] == [CURRENT, PRIOR]
    assert BETWEEN not in labels  # 119-100 changed only title 47


def test_ingested_titles_are_distinguished_from_affected_titles(client):
    """"OLRC says this release point changed Title 16" and "we hold Title 16 at
    this release point" are different claims."""
    releases = {r["label"]: r for r in client.get("/api/v1/releases").json()}

    assert "16" in releases[CURRENT]["ingested_titles"]
    assert releases[BETWEEN]["titles_affected"] == ["47"]
    # Title 16 is answerable at 119-100 — the resolver serves it from 119-99
    # (gotcha 10) — but it is not *held* here, which is the distinction. Asserted
    # as an absence rather than an empty list: `make dev-data` has ingested
    # nothing at this release point, while the full corpus has ingested exactly
    # the title it affected, and both must pass.
    assert "16" not in releases[BETWEEN]["ingested_titles"]
    assert set(releases[BETWEEN]["ingested_titles"]) <= {"47"}


def test_titles_lists_what_is_loaded(client):
    """Asserts Title 16's entry, not that it is the only one: `make dev-data` is
    the floor this suite needs, and a database that also holds a bulk load
    (`ingest load-all`) must still pass."""
    titles = {t["num"]: t for t in client.get("/api/v1/titles").json()}
    title16 = titles["16"]

    assert title16["name"] == "CONSERVATION"
    assert title16["is_positive_law"] is False
    # Both fixture release points are listed, newest last. A bulk load adds older
    # ones ahead of them; that must not change what this test is asserting.
    assert title16["ingested_releases"][-2:] == [PRIOR, CURRENT]


def test_openapi_documents_the_routes(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/us/usc/{identifier}" in paths
    assert "/api/v1/releases" in paths
    assert "/api/v1/sections/{identifier}/versions" in paths
    # The reader and the redirector are not machine routes and are not documented
    # as such (ADR-0010): the schema describes only what a program should call.
    assert not [path for path in paths if path.startswith(("/app", "/us/usc"))]


# ------------------------------------------------------- repeated identifiers


DUPLICATED = "/us/usc/t19/s2502"
DUPLICATED_RELEASE = "117-80"


def _duplicated_section(client):
    """The corpus-only fixture: skips on a `make dev-data` database, which holds
    Title 16 alone."""
    response = client.get(f"{API}{DUPLICATED}?release={DUPLICATED_RELEASE}")
    if response.status_code != 200:
        pytest.skip(f"{DUPLICATED} at {DUPLICATED_RELEASE} not loaded (needs load-all)")
    return response.json()


def test_a_repeated_identifier_serves_every_occurrence(client):
    """Title 19 at 117-80 publishes three <section> elements under one identifier
    — two byte-identical empty stubs headed "Purposes" and the real section. The
    stubs dedupe to one stored text (ADR-0007), leaving two distinct texts, and
    both are returned rather than one being picked (ADR-0021)."""
    body = _duplicated_section(client)

    assert len(body["duplicates"]) == 1
    texts = [body["xml"]] + [d["xml"] for d in body["duplicates"]]
    headings = [body["heading"]] + [d["heading"] for d in body["duplicates"]]

    assert "Purposes" in headings
    assert "Congressional statement of purposes" in headings
    # The substantive text is served, not just the stub that precedes it.
    assert any("The purposes of this Act are" in xml for xml in texts)


def test_repeated_occurrences_come_back_in_source_order(client):
    """Reading order is the only order the source gives, so it is the one used —
    and it is stable, which the previous unordered query was not."""
    body = _duplicated_section(client)
    seqs = [body["seq_in_title"]] + [d["seq_in_title"] for d in body["duplicates"]]

    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_a_repeated_identifier_is_stable_across_requests(client):
    """The bug this replaced: `.first()` with no ORDER BY handed back whichever
    row Postgres felt like, so the same URL could serve an empty stub one moment
    and the real section the next."""
    def shape(body):
        return tuple(
            (occurrence["heading"], len(occurrence["xml"]))
            for occurrence in [body] + body["duplicates"]
        )

    seen = {shape(_duplicated_section(client)) for _ in range(5)}

    assert len(seen) == 1


def test_a_deep_link_finds_its_provision_in_a_later_occurrence(client):
    """`/s2502/1` exists only in the substantive occurrence; the stub that sorts
    first has no paragraphs at all. Highlighting has to search across the
    occurrences or a deep link lands on nothing."""
    response = client.get(f"{API}{DUPLICATED}/1?release={DUPLICATED_RELEASE}")
    if response.status_code != 200:
        pytest.skip(f"{DUPLICATED} at {DUPLICATED_RELEASE} not loaded (needs load-all)")
    body = response.json()

    assert body["provision"]["identifier"] == f"{DUPLICATED}/1"
    assert body["provision"]["found"] is True


def test_neighbors_of_a_repeated_identifier_bracket_the_group(client):
    """This route used to 500 outright: it asked for the section's one place in
    reading order with `scalar_one_or_none`, and a repeated identifier holds
    several. Every affected section page was unreachable as a result."""
    response = client.get(
        f"{API}/sections{DUPLICATED}/neighbors?release={DUPLICATED_RELEASE}"
    )
    if response.status_code == 404:
        pytest.skip(f"{DUPLICATED} at {DUPLICATED_RELEASE} not loaded (needs load-all)")
    body = response.json()

    assert response.status_code == 200
    # The neighbours are other sections, never another occurrence of this one.
    for side in ("previous", "next"):
        if body[side] is not None:
            assert body[side]["identifier"] != DUPLICATED


def test_an_ordinary_section_has_no_duplicates(client):
    """The overwhelmingly common case stays clean: an empty list, not a null."""
    body = client.get(f"{API}{SECTION}?release={CURRENT}").json()

    assert body["duplicates"] == []


# --------------------------------------------------------------------- citation


def test_a_typed_citation_resolves_to_its_identifier(client):
    body = client.get(f"{API}/citation", params={"q": "16 usc 45f(c)(5)"}).json()

    assert body["identifier"] == DEMO
    assert body["section_identifier"] == SECTION
    assert body["subdivisions"] == ["c", "5"]
    assert body["exists"] is True
    assert body["heading"] == "Mineral King Valley addition authorized"


def test_the_written_forms_all_reach_the_same_place(client):
    """The parser's own table is unit-tested without a database
    (`tests/test_citeparse.py`); this checks the wiring — that each form
    survives the query string, the route and the existence lookup."""
    for form in (
        "16 usc 45f",
        "16 U.S.C. § 45f",
        "section 45f of title 16",
        "16/45f",
        "/us/usc/t16/s45f",
    ):
        body = client.get(f"{API}/citation", params={"q": form}).json()
        assert body["section_identifier"] == SECTION, form
        assert body["exists"] is True, form


def test_a_citation_honours_the_release_point(client):
    body = client.get(
        f"{API}/citation", params={"q": "16 usc 45f", "release": PRIOR}
    ).json()

    assert body["release"]["label"] == PRIOR
    assert body["exists"] is True


def test_text_that_is_not_a_citation_is_a_422(client):
    """Malformed request, not a missing resource — and the detail names the
    forms that would have worked."""
    response = client.get(f"{API}/citation", params={"q": "not a citation"})

    assert response.status_code == 422
    assert "11 usc 523" in response.json()["detail"]


def test_a_bare_section_number_is_refused_rather_than_guessed(client):
    """`523` names a section of *some* title. Picking one would be a guess
    presented as an answer."""
    assert client.get(f"{API}/citation", params={"q": "523"}).status_code == 422


def test_a_citation_naming_nothing_is_an_answer_not_an_error(client):
    """Title 99 does not exist and never will, but "no such thing" is a
    well-formed reply — the reader gets told which part was wrong."""
    response = client.get(f"{API}/citation", params={"q": "99 usc 1"})
    body = response.json()

    assert response.status_code == 200
    assert body["identifier"] == "/us/usc/t99/s1"
    assert body["exists"] is False


def test_an_appendix_citation_explains_why_it_cannot_resolve(client):
    """OLRC publishes appendix titles under the enacting instrument, so
    `/us/usc/t5a/s3` is a well-formed identifier that nothing is stored at
    (`tests/test_citeparse.py` counts it: 0 of 461). A bare "not found" would
    read as a bug in the parser; the message says what actually happened."""
    body = client.get(f"{API}/citation", params={"q": "5 U.S.C. App. 3"}).json()

    assert body["identifier"] == "/us/usc/t5a/s3"
    assert body["exists"] is False
    assert body["message"] is not None
    assert "enacted" in body["message"]


def test_a_typed_hyphen_finds_the_en_dash_identifier(client):
    """OLRC writes section numbers with an EN DASH (`/us/usc/t16/s45a–1`) and no
    keyboard has that key. 5,697 of the corpus's 65,938 sections contain one;
    none contains a plain hyphen. Typing the citation the ordinary way has to
    work, and the reader has to be redirected to the identifier that exists —
    not the one they typed, which would 404 on arrival."""
    body = client.get(f"{API}/citation", params={"q": "16 usc 45a-1"}).json()

    assert body["exists"] is True
    assert body["identifier"] == "/us/usc/t16/s45a–1"


def test_a_structural_node_is_found_rather_than_reported_missing(client):
    """`labels()` answers about sections, so a chapter came back `exists: false`
    while sitting in the database. Structure goes to `get_toc`."""
    chapter = client.get(f"{API}/citation", params={"q": "16 usc ch. 1"}).json()
    title = client.get(f"{API}/citation", params={"q": "title 16"}).json()

    assert chapter["identifier"] == "/us/usc/t16/ch1"
    assert chapter["kind"] == "structure"
    assert chapter["exists"] is True
    assert title["identifier"] == "/us/usc/t16"
    assert title["kind"] == "title"
    assert title["exists"] is True
