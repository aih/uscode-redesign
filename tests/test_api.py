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

import pytest

pytestmark = pytest.mark.integration

DEMO = "/us/usc/t16/s45f/c/5"
SECTION = "/us/usc/t16/s45f"
S45F_C5_GUID_AT_CURRENT = "id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd"
CURRENT = "119-102not101"
PRIOR = "119-99"
BETWEEN = "119-100"  # published, ingested for no title, changed only title 47
AMENDED = "/us/usc/t16/s2201"


# ------------------------------------------------------------------ identifiers


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_the_plan_demo_url(client):
    """PLAN §10's definition of done: a provision, by date, in context."""
    response = client.get(f"{DEMO}?date=07/12/2026")
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
    us = client.get(f"{SECTION}?date=07/12/2026").json()
    iso = client.get(f"{SECTION}?date=2026-07-12").json()

    assert us["served_from"]["label"] == iso["served_from"]["label"] == CURRENT


def test_a_date_between_release_points_resolves_backwards(client):
    body = client.get(f"{SECTION}?date=2026-06-20").json()

    assert body["release"]["label"] == PRIOR
    assert "falls between release points" in body["note"]


def test_a_date_before_the_first_release_point_is_404(client):
    response = client.get(f"{SECTION}?date=1999-01-01")

    assert response.status_code == 404
    assert "no release point on or before" in response.json()["detail"]


def test_a_malformed_date_is_422(client):
    assert client.get(f"{SECTION}?date=yesterday").status_code == 422


def test_the_not_caveat_is_surfaced_not_just_the_date(client):
    """Gotcha 5: at 119-102not101 the text is *not* current through 07/12/2026 —
    Public Law 119-101 is excluded, and a date alone would hide that."""
    response = client.get(f"{SECTION}?release={CURRENT}")
    body = response.json()

    assert body["release"]["is_partial"] is True
    assert body["release"]["excluded_laws"] == [101]
    assert "except 119-101" in body["release"]["caveat"]
    assert "except 119-101" in response.headers["x-release-caveat"]


def test_a_bare_label_resolves_with_a_note(client):
    """`119-102` was never published on its own; `119-102not101` was."""
    body = client.get(f"{SECTION}?release=119-102").json()

    assert body["release"]["label"] == CURRENT
    assert "was published as 119-102not101" in body["note"]


def test_an_unknown_label_is_404(client):
    assert client.get(f"{SECTION}?release=42-1").status_code == 404


def test_a_release_point_we_never_ingested_answers_from_the_one_before_it(client):
    """119-100 exists and changed only title 47, so Title 16's text at 119-100 *is*
    its text at 119-99. Answering is right; answering silently would not be."""
    response = client.get(f"{SECTION}?release={BETWEEN}")
    body = response.json()

    assert response.status_code == 200
    assert body["release"]["label"] == BETWEEN
    assert body["served_from"]["label"] == PRIOR
    assert body["is_exact"] is False
    assert "not ingested" in body["note"]
    assert response.headers["x-served-from"] == PRIOR


def test_an_amended_section_differs_between_the_two_release_points(client):
    old = client.get(f"{AMENDED}?release={PRIOR}").json()
    new = client.get(f"{AMENDED}?release={CURRENT}").json()

    assert old["xml"] != new["xml"]
    assert len(new["xml"]) > len(old["xml"])
    assert old["content_first_seen"]["label"] == PRIOR
    assert new["content_first_seen"]["label"] == CURRENT


def test_an_unchanged_section_is_stored_once_and_served_at_both(client):
    """ADR-0007: identical content deduped across release points. The bytes come
    from the release point they first appeared at, and the response says so."""
    old = client.get(f"{SECTION}?release={PRIOR}").json()
    new = client.get(f"{SECTION}?release={CURRENT}").json()

    assert old["xml"] == new["xml"]
    assert new["content_first_seen"]["label"] == PRIOR
    assert new["served_from"]["label"] == CURRENT


def test_a_missing_section_404s_naming_the_release_point(client):
    response = client.get("/us/usc/t16/s9999")

    assert response.status_code == 404
    assert "119-102not101" in response.json()["detail"]


# ---------------------------------------------------------------------- formats


def test_xml_format_returns_the_requested_fragment_verbatim(client):
    section = client.get(f"{SECTION}?format=xml")
    provision = client.get(f"{DEMO}?format=xml")

    assert section.headers["content-type"].startswith("application/xml")
    assert section.text.startswith("<section")
    assert provision.text.startswith("<paragraph")
    assert f'identifier="{DEMO}"' in provision.text


def test_accept_header_negotiates_xml(client):
    response = client.get(SECTION, headers={"Accept": "application/xml"})

    assert response.headers["content-type"].startswith("application/xml")
    assert response.text.startswith("<section")


def test_html_format_highlights_the_requested_provision(client):
    response = client.get(f"{DEMO}?format=html")

    assert response.headers["content-type"].startswith("text/html")
    assert "<!doctype html>" in response.text
    assert f'id="{DEMO}"' in response.text
    assert "target" in response.text
    assert "Mineral King Valley" in response.text


def test_etag_is_the_content_hash_and_is_stable(client):
    first = client.get(SECTION)
    again = client.get(f"{SECTION}?release={CURRENT}")

    assert first.headers["etag"] == again.headers["etag"]
    assert len(first.headers["etag"].strip('"')) == 64


# ------------------------------------------------------------------------ guids


def test_guid_lookup_needs_no_release_parameter(client):
    body = client.get(f"/us/usc/?id={S45F_C5_GUID_AT_CURRENT}").json()

    assert body["identifier"] == DEMO
    assert body["release"]["label"] == CURRENT
    assert body["section_identifier"] == SECTION
    assert body["is_section"] is False


def test_the_same_provision_has_a_different_guid_at_each_release_point(client):
    """ADR-0003: a guid pins (provision, release point). It is never cross-release
    identity — that is @identifier's job."""
    old = client.get(f"{SECTION}?release={PRIOR}").json()
    new = client.get(f"{SECTION}?release={CURRENT}").json()

    assert old["guid"] != new["guid"]
    assert (
        client.get(f"/us/usc/?id={old['guid']}").json()["release"]["label"] == PRIOR
    )
    assert (
        client.get(f"/us/usc/?id={new['guid']}").json()["release"]["label"] == CURRENT
    )


def test_an_unknown_guid_is_404(client):
    assert client.get("/us/usc/?id=idnope").status_code == 404


# -------------------------------------------------------------------------- toc


def test_title_root_lists_its_chapters(client):
    body = client.get("/us/usc/t16").json()

    assert body["node"]["heading"] == "CONSERVATION"
    assert len(body["children"]) == 153
    assert body["children"][0]["identifier"] == "/us/usc/t16/ch1"
    assert body["ancestors"] == []


def test_a_chapter_lists_its_sections_in_reading_order_with_badges(client):
    """Gotcha 9: repealed and omitted sections keep their place, badged."""
    body = client.get("/us/usc/t16/ch6").json()
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
    body = client.get("/us/usc/t16/ch1/schI").json()

    assert [a["identifier"] for a in body["ancestors"]] == [
        "/us/usc/t16",
        "/us/usc/t16/ch1",
    ]


def test_the_reserved_subchapter_is_retrievable_and_badged(client):
    """Title 16's only `reserved` is on a subchapter, not a section (gotcha 13)."""
    body = client.get("/us/usc/t16/ch1").json()
    reserved = [c for c in body["children"] if c["status"] == "reserved"]

    assert [c["identifier"] for c in reserved] == ["/us/usc/t16/ch1/schXCVII"]


def test_toc_html_renders(client):
    response = client.get("/us/usc/t16/ch6?format=html")

    assert response.headers["content-type"].startswith("text/html")
    assert "GAME AND BIRD PRESERVES" in response.text


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


def test_versions_lists_one_entry_per_distinct_text(client):
    amended = client.get(f"/api/v1/sections{AMENDED}/versions").json()
    unchanged = client.get(f"/api/v1/sections{SECTION}/versions").json()

    assert [v["first_seen"]["label"] for v in amended["versions"]] == [PRIOR, CURRENT]
    assert [v["releases"] for v in amended["versions"]] == [[PRIOR], [CURRENT]]
    # One text, published at both release points — the dedupe, seen from outside.
    assert len(unchanged["versions"]) == 1
    assert unchanged["versions"][0]["releases"] == [PRIOR, CURRENT]


def test_versions_of_a_provision_path_resolve_to_its_section(client):
    body = client.get(f"/api/v1/sections{DEMO}/versions").json()

    assert body["identifier"] == DEMO
    assert len(body["versions"]) == 1


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
    assert releases[BETWEEN]["ingested_titles"] == []
    assert releases[BETWEEN]["titles_affected"] == ["47"]


def test_titles_lists_what_is_loaded(client):
    """Asserts Title 16's entry, not that it is the only one: `make dev-data` is
    the floor this suite needs, and a database that also holds a bulk load
    (`ingest load-all`) must still pass."""
    titles = {t["num"]: t for t in client.get("/api/v1/titles").json()}

    assert titles["16"] == {
        "num": "16",
        "name": "CONSERVATION",
        "is_positive_law": False,
        "ingested_releases": [PRIOR, CURRENT],
    }


def test_openapi_documents_the_routes(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/us/usc/{identifier}" in paths
    assert "/api/v1/releases" in paths
    assert "/api/v1/sections/{identifier}/versions" in paths
