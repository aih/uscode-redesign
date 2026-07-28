"""Content negotiation, which decides whether a URL answers a person or a program.

The identifier is one URL for both (PLAN §4), so `Accept:` is load-bearing —
and the header real browsers send is not the header tests usually make up.
"""

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from api.deps import negotiated_format

CHROME = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8"


def request_with(accept: str | None) -> Request:
    headers = Headers({"accept": accept} if accept is not None else {})
    return Request({"type": "http", "headers": headers.raw, "method": "GET", "path": "/"})


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        # A browser asks for html at q=1 and xml at q=0.9. Reading the header as
        # a substring match — as this did until the reader was built — serves a
        # person raw USLM.
        (CHROME, "html"),
        ("text/html", "html"),
        ("application/xml", "xml"),
        ("text/xml", "xml"),
        ("application/json", "json"),
        ("*/*", "json"),  # curl, and anything that doesn't care
        (None, "json"),
        ("text/html;q=0.2,application/xml;q=0.9", "xml"),  # q-values decide
        ("text/html;q=0,application/json", "json"),  # q=0 means "not this"
        ("application/pdf", "json"),  # nothing we serve: fall back, don't 406
    ],
)
def test_accept_headers_resolve_to_a_format(accept, expected):
    assert negotiated_format(request_with(accept), None) == expected


@pytest.mark.parametrize("wanted", ["html", "xml", "json"])
def test_the_format_parameter_beats_the_header(wanted):
    """`?format=` is explicit, and explicit wins — it is also what makes the
    documented demo URL work from a terminal."""
    assert negotiated_format(request_with(CHROME), wanted) == wanted
