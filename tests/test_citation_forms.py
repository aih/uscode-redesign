"""The citation guide and the citation parser must describe the same thing.

`frontend/src/lib/citationforms.ts` is the table `/app/search/syntax` renders:
one row per accepted form, each naming an example and the `@identifier` that
example produces. `citeparse.parse_citation` is the only thing that decides what
a citation *is* (ADR-0023). This file runs every documented example through it.

The sibling is `tests/test_search_syntax.py`, which does the same job for the
OpenSearch operators, and the reasoning is identical: the failure mode of a
wrong syntax guide is not an error, it is a reader typing something the guide
promised and getting nothing back, with no way to tell that apart from a
citation that legitimately names nothing.

Reading the TypeScript as text rather than importing it is the same trade made
there — a Node build step in the Python suite to check a list of strings would
cost more than it is worth, and `test_the_table_is_not_empty` guards the regex
so a shape change fails loudly instead of matching nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from citeparse import parse_citation

GUIDE = Path(__file__).resolve().parent.parent / "frontend/src/lib/citationforms.ts"

#: One `{ … }` object literal per row. The entries hold no nested braces, so a
#: non-greedy match between the outermost pair of each is enough.
_ENTRY = re.compile(r"\{(?P<body>[^{}]+)\}", re.DOTALL)
_EXAMPLE = re.compile(r'example:\s*"((?:[^"\\]|\\.)*)"')
_IDENTIFIER = re.compile(r'identifier:\s*(?:"((?:[^"\\]|\\.)*)"|(null))')


def _rows(section: str) -> list[tuple[str, str | None]]:
    """`(example, identifier)` pairs from one exported array."""
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index(f"export const {section}")
    end = text.find("export const", start + 1)
    body = text[start : end if end != -1 else len(text)]

    rows: list[tuple[str, str | None]] = []
    for entry in _ENTRY.finditer(body):
        example = _EXAMPLE.search(entry.group("body"))
        identifier = _IDENTIFIER.search(entry.group("body"))
        if not example or not identifier:
            continue
        rows.append((example.group(1), identifier.group(1)))
    return rows


FORMS = _rows("CITATION_FORMS")
LIMITS = _rows("CITATION_LIMITS")


def test_the_guide_file_exists() -> None:
    assert GUIDE.is_file(), f"the citation guide's table is missing: {GUIDE}"


def test_the_table_is_not_empty() -> None:
    """Guards the regex itself.

    Every other assertion here is parametrized over what the regex found, so a
    regex that stopped matching would collect nothing and the whole file would
    pass while checking no claim at all.
    """
    assert len(FORMS) >= 10, f"only {len(FORMS)} forms parsed out of the guide"
    assert len(LIMITS) >= 2


@pytest.mark.parametrize(("example", "identifier"), FORMS, ids=[f[0] for f in FORMS])
def test_every_documented_form_parses_to_the_documented_identifier(
    example: str, identifier: str | None
) -> None:
    parsed = parse_citation(example)
    assert parsed is not None, (
        f"the guide offers {example!r} as a citation the box accepts, and "
        f"citeparse does not read it as one at all"
    )
    assert parsed.identifier == identifier, (
        f"the guide says {example!r} means {identifier}, and citeparse makes it "
        f"{parsed.identifier}"
    )


@pytest.mark.parametrize(("example", "identifier"), LIMITS, ids=[f[0] for f in LIMITS])
def test_the_documented_limits_behave_as_documented(
    example: str, identifier: str | None
) -> None:
    """The rows that say "this does not work", checked the same way.

    A limit that quietly starts working is as much a documentation bug as a form
    that quietly stops: the page would be telling a reader not to try something
    that would have answered.
    """
    parsed = parse_citation(example)
    if identifier is None:
        assert parsed is None, (
            f"the guide says {example!r} is not read as a citation, and citeparse "
            f"now makes it {parsed.identifier if parsed else None}"
        )
    else:
        assert parsed is not None and parsed.identifier == identifier


def test_case_is_preserved_in_subdivisions() -> None:
    """The claim the guide makes in prose rather than in a row.

    `(B)` and `(b)` are different provisions and the identifiers distinguish
    them, so a parser that lowercased would send readers to the wrong one
    silently — the URL would resolve, just not to what was asked for.
    """
    parsed = parse_citation("11 U.S.C. § 523(a)(1)(B)(ii)")
    assert parsed is not None
    assert parsed.identifier.endswith("/B/ii")


def test_both_dash_spellings_are_offered_for_lookup() -> None:
    """The other prose claim: type the hyphen you have, land on the en dash.

    5,697 of 65,938 sections contain U+2013 and none contains a plain hyphen, so
    without this a citation like `42 USC 2000e-2` — typed the only way a
    keyboard offers — would match nothing at all (CLAUDE.md gotcha 17).
    """
    parsed = parse_citation("16 usc 45a-1")
    assert parsed is not None
    assert "/us/usc/t16/s45a–1" in parsed.section_variants
