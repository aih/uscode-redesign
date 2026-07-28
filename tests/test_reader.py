"""The reader's pages, against a stub repository.

These run with no database, which is the point: `web/` depends on the
`Repository` interface and nothing else (CLAUDE.md architecture rule 1), so a
hand-built set of the frozen dataclasses `storage` returns is a complete input.
If one of these ever needs Postgres to pass, the boundary has leaked.

What they check is mostly the three facts a reader is tempted to drop — the
release-point caveat, the served-from note, and status badges — plus the anchor
that makes a provision URL land on its provision.
"""

from __future__ import annotations

import datetime

import pytest

from storage import (
    Neighbors,
    Provision,
    ReleaseRef,
    ResolvedRelease,
    SectionResult,
    TitleInfo,
    TocEntry,
    TocResult,
)
from web import reader

USLM1 = "http://xml.house.gov/schemas/uslm/1.0"

CURRENT = ReleaseRef(
    label="119-102not101",
    currency_date=datetime.date(2026, 7, 12),
    seq=382,
    congress=119,
    law_num=102,
    excluded_laws=(101,),
    titles_affected=("16",),
    ingested_titles=("16",),
)
EARLIER = ReleaseRef(
    label="119-99",
    currency_date=datetime.date(2026, 6, 12),
    seq=380,
    congress=119,
    law_num=99,
    titles_affected=("16",),
    ingested_titles=("16",),
)
BETWEEN = ReleaseRef(
    label="119-100",
    currency_date=datetime.date(2026, 6, 20),
    seq=381,
    congress=119,
    law_num=100,
    titles_affected=("47",),
)

SECTION_XML = f"""<section xmlns="{USLM1}" identifier="/us/usc/t16/s45f" id="idsec"
                           class="section">
  <num value="45f">§ 45f.</num>
  <heading>Mineral King Valley addition</heading>
  <subsection identifier="/us/usc/t16/s45f/c" class="indent1">
    <num value="c">(c)</num>
    <paragraph identifier="/us/usc/t16/s45f/c/5" class="indent2">
      <num value="5">(5)</num>
      <content>Severance damages.</content>
    </paragraph>
  </subsection>
</section>"""


class StubRepository:
    """Just enough `Repository` for the reader — no SQL, no session, no models."""

    def __init__(self, *, neighbors: Neighbors | None = None, toc: TocResult | None = None):
        self._neighbors = neighbors
        self._toc = toc

    def list_releases(self, *, title_num=None):
        return [CURRENT, BETWEEN, EARLIER]

    def list_titles(self):
        return [
            TitleInfo(
                num="16",
                name="CONSERVATION",
                is_positive_law=False,
                ingested_releases=("119-99", "119-102not101"),
            )
        ]

    def neighbors(self, identifier, release):
        return self._neighbors

    def get_toc(self, identifier, release):
        return self._toc


def section(
    *,
    served_from: ReleaseRef = CURRENT,
    release: ReleaseRef = CURRENT,
    status: str | None = None,
    provision: Provision | None = None,
    parent_identifier: str | None = None,
) -> SectionResult:
    return SectionResult(
        identifier="/us/usc/t16/s45f",
        title_num="16",
        num="§ 45f.",
        heading="Mineral King Valley addition",
        status=status,
        xml=SECTION_XML,
        content_hash="abc123",
        source_credit="(Pub. L. 95–625.)",
        seq_in_title=42,
        parent_identifier=parent_identifier,
        guid="id0b32dfeb-810c-11f1-b7ce-bdea3d14cbdd",
        release=release,
        served_from=served_from,
        content_first_seen=EARLIER,
        provision=provision,
    )


def resolved(release: ReleaseRef = CURRENT, note: str | None = None) -> ResolvedRelease:
    return ResolvedRelease(release=release, requested_label=release.label, note=note)


def entry(identifier: str, num: str, heading: str, status: str | None = None) -> TocEntry:
    return TocEntry(
        identifier=identifier,
        level="section",
        num=num,
        heading=heading,
        status=status,
        is_section=True,
    )


# ------------------------------------------------------------------- sections


def render(repository=None, **kwargs) -> str:
    return reader.render_section(
        repository or StubRepository(),
        kwargs.pop("section_result", section()),
        kwargs.pop("resolved_release", resolved()),
        requested_identifier=kwargs.pop("requested_identifier", "/us/usc/t16/s45f"),
        **kwargs,
    )


def test_the_provision_the_url_named_is_the_only_thing_highlighted():
    """ADR-0001: the whole section comes back, with (c)(5) marked inside it."""
    html = render(
        section_result=section(
            provision=Provision(identifier="/us/usc/t16/s45f/c/5", found=True, xml="<p/>")
        ),
        requested_identifier="/us/usc/t16/s45f/c/5",
    )

    assert 'id="/us/usc/t16/s45f/c/5"' in html
    assert html.count(' target"') == 1  # exactly one element wears the highlight
    assert "Severance damages." in html
    assert "(c)(5)" in html


def test_a_section_url_highlights_nothing():
    html = render()

    assert ' target"' not in html


def test_a_provision_that_does_not_exist_says_so_and_still_shows_the_section():
    html = render(
        section_result=section(
            provision=Provision(identifier="/us/usc/t16/s45f/c/9", found=False)
        ),
        requested_identifier="/us/usc/t16/s45f/c/9",
    )

    assert "There is no" in html
    assert "(c)(9)" in html
    assert "Severance damages." in html


def test_the_not_law_caveat_is_on_the_page():
    """Gotcha 5: `119-102not101` is not fully current through 07/12/2026, and a
    page showing only the date would be lying by omission."""
    html = render()

    assert "except 119-101" in html
    assert "07/12/2026" in html


def test_serving_from_an_earlier_release_point_is_stated():
    """Gotcha 10: an un-ingested release point is answerable from the newest one
    before it — but never silently."""
    html = render(
        section_result=section(release=BETWEEN, served_from=EARLIER),
        resolved_release=resolved(BETWEEN),
        note="119-100 is not ingested; this is Title 16 as published at 119-99.",
    )

    assert "119-100 is not ingested" in html
    assert "119-99" in html


def test_status_is_badged():
    html = render(section_result=section(status="repealed"))

    assert 'class="status status-repealed"' in html
    assert "repealed" in html


def test_prev_and_next_carry_the_release_point_and_their_badges():
    """Gotcha 9: repealed sections keep their place in reading order."""
    repository = StubRepository(
        neighbors=Neighbors(
            identifier="/us/usc/t16/s45f",
            previous=entry("/us/usc/t16/s45e", "§ 45e.", "Violations", "repealed"),
            next=entry("/us/usc/t16/s45g", "§ 45g.", "Addition to Sequoia"),
            release=CURRENT,
            served_from=CURRENT,
        )
    )
    html = render(repository)

    assert '/us/usc/t16/s45e?release=119-102not101' in html
    assert '/us/usc/t16/s45g?release=119-102not101' in html
    assert "status-repealed" in html


def test_the_release_picker_offers_only_ingested_release_points():
    """Offering all 382 would be offering 380 empty answers until the backfill."""
    html = render()

    assert 'value="119-102not101" selected' in html
    assert 'value="119-99"' in html
    assert "119-100" not in html  # published, but Title 16 isn't ingested there


def test_a_date_request_leaves_release_labels_in_the_links():
    """`?date=` is resolved once; every link on the page then names the release
    point, so what you copy out of the address bar stays unambiguous."""
    html = render(
        resolved_release=ResolvedRelease(
            release=CURRENT, requested_date=datetime.date(2026, 7, 12)
        ),
        section_result=section(
            provision=Provision(identifier="/us/usc/t16/s45f/c/5", found=True, xml="<p/>")
        ),
        requested_identifier="/us/usc/t16/s45f/c/5",
    )

    assert "release=119-102not101" in html
    assert "date=" not in html


def test_breadcrumbs_come_from_the_parent_nodes_own_ancestors():
    toc = TocResult(
        node=TocEntry(
            identifier="/us/usc/t16/ch1/schVI",
            level="subchapter",
            num="SUBCHAPTER VI—",
            heading="SEQUOIA",
        ),
        ancestors=(
            TocEntry(identifier="/us/usc/t16", level="title", num="Title 16—", heading="CONSERVATION"),
            TocEntry(identifier="/us/usc/t16/ch1", level="chapter", num="CHAPTER 1—", heading="PARKS"),
        ),
        children=(),
        sections=(),
        release=CURRENT,
        served_from=CURRENT,
    )
    html = render(
        StubRepository(toc=toc),
        section_result=section(parent_identifier="/us/usc/t16/ch1/schVI"),
    )

    assert ">Title 16<" in html  # the trailing em dash of `<num>` is trimmed
    assert ">CHAPTER 1<" in html
    assert ">SUBCHAPTER VI<" in html


def test_the_citation_guid_links_to_the_guid_lookup():
    """A guid pins (provision, release point), so it is the durable citation."""
    html = render()

    assert "/us/usc/?id=id0b32dfeb-810c-11f1-b7ce-bdea3d14cbdd" in html


# ----------------------------------------------------------------------- tocs


def toc_result(children=(), sections=()) -> TocResult:
    return TocResult(
        node=TocEntry(
            identifier="/us/usc/t16/ch1",
            level="chapter",
            num="CHAPTER 1—",
            heading="NATIONAL PARKS",
        ),
        ancestors=(
            TocEntry(identifier="/us/usc/t16", level="title", num="Title 16—", heading="CONSERVATION"),
        ),
        children=children,
        sections=sections,
        release=CURRENT,
        served_from=CURRENT,
    )


def test_a_toc_lists_children_and_sections_with_badges():
    toc = toc_result(
        children=(
            TocEntry(
                identifier="/us/usc/t16/ch1/schXCVII",
                level="subchapter",
                num="SUBCHAPTER XCVII—",
                heading="RESERVED",
                status="reserved",
            ),
        ),
        sections=(entry("/us/usc/t16/s1", "§ 1.", "Repealed", "repealed"),),
    )
    html = reader.render_toc(StubRepository(), toc, resolved())

    assert "Subchapters" in html  # named after what the children actually are
    assert "status-reserved" in html
    assert "status-repealed" in html
    assert "/us/usc/t16/s1?release=119-102not101" in html


def test_an_empty_node_says_it_is_empty_rather_than_rendering_nothing():
    html = reader.render_toc(StubRepository(), toc_result(), resolved())

    assert "Nothing is listed" in html


# ---------------------------------------------------------------- other pages


def test_the_home_page_lists_loaded_titles_and_the_demo():
    html = reader.render_home(StubRepository())

    assert "/us/usc/t16" in html
    assert "CONSERVATION" in html
    assert "2 release points" in html
    assert "/us/usc/t16/s45f/c/5?date=07/12/2026" in html


def test_an_ambiguous_release_offers_the_candidates():
    html = reader.render_error(409, "matches 2 release points", ["119-102not101", "119-102not99"])

    assert "119-102not101" in html
    assert "?release=119-102not99" in html


@pytest.mark.parametrize(
    ("remainder", "expected"),
    [("/c/5", "(c)(5)"), ("/a", "(a)"), ("/b/2/A/i", "(b)(2)(A)(i)")],
)
def test_provision_paths_are_written_the_way_a_lawyer_writes_them(remainder, expected):
    assert reader._provision_label(remainder) == expected


# ---------------------------------------------------- the demo, end to end
#
# PLAN §10's Day-1 definition of done, walked through the real repository:
# open the site, browse to a section, highlight a provision, flip release
# points, page to the neighbour. These need `make dev-data` and skip without it.

DEMO = "/us/usc/t16/s45f/c/5?date=07/12/2026"


@pytest.mark.integration
def test_the_front_page_links_to_the_loaded_title(client):
    response = client.get("/")

    assert response.headers["content-type"].startswith("text/html")
    assert 'href="/us/usc/t16"' in response.text
    assert "CONSERVATION" in response.text


@pytest.mark.integration
def test_the_stylesheet_is_served(client):
    """The reader is one stylesheet away from unreadable, and it is served by the
    app itself — no CDN, no build step."""
    response = client.get("/static/reader.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


@pytest.mark.integration
def test_the_demo_url_is_a_readable_page(client):
    """`/us/usc/t16/s45f/c/5?date=07/12/2026`, in a browser."""
    response = client.get(DEMO, headers={"accept": "text/html"})
    html = response.text

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Mineral King Valley addition authorized" in html
    assert 'id="/us/usc/t16/s45f/c/5"' in html
    assert html.count(' target"') == 1
    assert "except 119-101" in html  # gotcha 5, on the page and not in a tooltip
    assert 'href="/us/usc/t16/ch1?release=119-102not101"' in html  # breadcrumb
    assert "/us/usc/t16/s45e?release=119-102not101" in html  # previous
    assert "/us/usc/t16/s45g?release=119-102not101" in html  # next


@pytest.mark.integration
def test_the_release_picker_switches_release_points(client):
    """What the picker submits is a URL — following it is the whole mechanism."""
    at_current = client.get(
        "/us/usc/t16/s2201?release=119-102not101", headers={"accept": "text/html"}
    ).text
    at_prior = client.get(
        "/us/usc/t16/s2201?release=119-99", headers={"accept": "text/html"}
    ).text

    assert 'value="119-102not101" selected' in at_current
    assert 'value="119-99" selected' in at_prior
    assert "06/12/2026" in at_prior
    assert at_current != at_prior  # s2201 is one of the two amended sections


@pytest.mark.integration
def test_a_browser_gets_html_and_a_program_gets_json_from_one_url(client):
    """Content negotiation is why the citation and the API call are the same URL."""
    chrome = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    browser = client.get("/us/usc/t16/s45f", headers={"accept": chrome})
    program = client.get("/us/usc/t16/s45f")

    assert browser.headers["content-type"].startswith("text/html")
    assert program.headers["content-type"].startswith("application/json")
    # Same URL, same ETag, two representations — a cache needs to be told (ADR-0009).
    assert browser.headers["vary"] == program.headers["vary"] == "Accept"
    assert browser.headers["etag"] == program.headers["etag"]


@pytest.mark.integration
def test_a_chapter_toc_is_browsable(client):
    response = client.get("/us/usc/t16/ch1", headers={"accept": "text/html"})

    assert "Subchapters" in response.text
    assert 'href="/us/usc/t16/ch1/schVI?release=' in response.text


@pytest.mark.integration
def test_a_wrong_citation_gets_a_page_not_a_json_blob(client):
    response = client.get("/us/usc/t16/s9999", headers={"accept": "text/html"})

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "119-102not101" in response.text  # which release point was searched
    assert 'href="/"' in response.text
