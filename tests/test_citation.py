"""The citation URL, which decides whether a person or a program is asking.

This file used to test `negotiated_format` directly, back when one handler served
both representations. ADR-0010 turned that decision into a **routing** decision:
`/us/usc/…` now 307s to `/app` or `/api/v1`, so the same q-value table is asserted
here against the `Location:` header instead of a format string. The header real
browsers send is still not the header tests usually make up, which is the whole
reason this file exists — a substring match for `application/xml` matches Chrome
and would send every reader to the machine surface.

No database: the redirector resolves nothing and asks the repository nothing.
"""

import pytest
from fastapi.testclient import TestClient

from main import app

CHROME = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8"
CITATION = "/us/usc/t16/s45f/c/5"


@pytest.fixture(scope="module")
def client():
    """Redirects are the subject here, so they are not followed."""
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


@pytest.mark.parametrize(
    ("accept", "surface"),
    [
        # A browser asks for html at q=1 and xml at q=0.9. Reading the header as a
        # substring match — as this did until the reader was built — hands a person
        # the machine surface.
        (CHROME, "/app"),
        ("text/html", "/app"),
        ("application/xhtml+xml", "/app"),
        ("application/xml", "/api/v1"),
        ("text/xml", "/api/v1"),
        ("application/json", "/api/v1"),
        ("*/*", "/api/v1"),  # curl, and anything that doesn't care
        (None, "/api/v1"),
        ("text/html;q=0.2,application/xml;q=0.9", "/api/v1"),  # q-values decide
        ("text/html;q=0,application/json", "/api/v1"),  # q=0 means "not this"
        ("application/pdf", "/api/v1"),  # nothing we serve: fall back, don't 406
    ],
)
def test_accept_decides_which_surface_a_citation_lands_on(client, accept, surface):
    response = client.get(CITATION, headers={"accept": accept} if accept else {})

    assert response.status_code == 307
    assert response.headers["location"] == f"{surface}{CITATION}"


@pytest.mark.parametrize(
    ("wanted", "surface"),
    [("html", "/app"), ("xml", "/api/v1"), ("json", "/api/v1")],
)
def test_the_format_parameter_beats_the_header(client, wanted, surface):
    """`?format=` is explicit, and explicit wins — it is also what makes the
    documented demo URL work from a terminal. It rides along to the surface it
    chose, because `/api/v1` still needs to know json from xml."""
    response = client.get(f"{CITATION}?format={wanted}", headers={"accept": CHROME})

    assert response.status_code == 307
    assert response.headers["location"] == f"{surface}{CITATION}?format={wanted}"


def test_a_redirect_is_307_and_varies_on_accept():
    """307, not 301/302: the answer depends on who asked, so no cache — and no
    browser that once saw one `Accept:` — may treat it as permanent."""
    with TestClient(app, follow_redirects=False) as client:
        response = client.get(CITATION, headers={"accept": "text/html"})

    assert response.status_code == 307
    assert response.headers["vary"] == "Accept"


@pytest.mark.parametrize(
    "query",
    [
        "release=119-102not101",
        "date=07/12/2026",
        "id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd",
        "release=119-102not101&highlight=all",  # parameters we don't know survive too
    ],
)
def test_the_query_string_survives_the_redirect(client, query):
    """The redirector parses `?format=` and copies everything else through
    untouched — `?release=`, `?date=` and the `?id=` guid form are the surfaces'
    business, not its own."""
    response = client.get(f"/us/usc/?{query}", headers={"accept": "text/html"})

    assert response.headers["location"] == f"/app/us/usc/?{query}"


def test_the_guid_form_is_a_citation_like_any_other(client):
    """`/us/usc/?id=…` carries no identifier path, and needs no special case."""
    guid = "id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd"

    assert client.get(f"/us/usc/?id={guid}").headers["location"] == (
        f"/api/v1/us/usc/?id={guid}"
    )


def test_a_toc_identifier_redirects_like_a_section(client):
    """The redirector never asks what an identifier names — that is the surfaces'
    job, and knowing would make it something other than thin."""
    response = client.get("/us/usc/t16/ch1", headers={"accept": "text/html"})

    assert response.headers["location"] == "/app/us/usc/t16/ch1"


def test_the_front_door_is_the_reader(client):
    response = client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/app/"


def test_the_health_check_is_not_behind_a_redirect(client):
    """Ops routes answer where they are: a load balancer should not have to
    follow a redirect to learn the process is alive."""
    assert client.get("/health").json() == {"status": "ok", "redis": "disabled"}
