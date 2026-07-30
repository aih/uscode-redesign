"""The accepted-forms table for `parse_citation`. This file *is* the spec.

No database and no fixtures: `citeparse` is pure by design (and
`test_architecture.py` enforces it), so every form a reader might type can be
checked in the default `make test` run.
"""

import pytest

from citeparse import parse_citation

# ---------------------------------------------------------------- the standard

STANDARD = [
    # The same citation, written the six ways people actually write it.
    ("11 usc 523", "/us/usc/t11/s523"),
    ("11 USC 523", "/us/usc/t11/s523"),
    ("11 U.S.C. 523", "/us/usc/t11/s523"),
    ("11 U.S.C. § 523", "/us/usc/t11/s523"),
    ("11 U.S.C.§523", "/us/usc/t11/s523"),
    ("11 USC §§ 523", "/us/usc/t11/s523"),
    ("11 U. S. C. § 523", "/us/usc/t11/s523"),
    # Case and stray punctuation.
    ("11 Usc 523.", "/us/usc/t11/s523"),
    ("  11   usc   523  ", "/us/usc/t11/s523"),
    ("(11 U.S.C. 523)", "/us/usc/t11/s523"),
]

SUBDIVISIONS = [
    ("11 usc 523(a)", "/us/usc/t11/s523/a"),
    ("11 usc 523(a)(1)", "/us/usc/t11/s523/a/1"),
    ("11 usc 523(a)(1)(B)(ii)", "/us/usc/t11/s523/a/1/B/ii"),
    # The project's own fixture, which is the assertion everything else is
    # checked against (CLAUDE.md "known-good assertion").
    ("16 usc 45f(c)(5)", "/us/usc/t16/s45f/c/5"),
    ("16 U.S.C. § 45f(c)(5)", "/us/usc/t16/s45f/c/5"),
]

# A section number is not a number. These are all real.
AWKWARD_SECTION_NUMBERS = [
    ("42 USC 2000e-2", "/us/usc/t42/s2000e-2"),
    ("15 U.S.C. § 78j-1", "/us/usc/t15/s78j-1"),
    ("16 usc 45f", "/us/usc/t16/s45f"),
    ("26 USC 401(k)", "/us/usc/t26/s401/k"),
    ("42 USC 1983", "/us/usc/t42/s1983"),
    ("50 USC 3021", "/us/usc/t50/s3021"),
]

# Gotcha 7: the five appendix titles are separate titles, stored unpadded.
APPENDIX = [
    ("5 U.S.C. App. 3", "/us/usc/t5a/s3"),
    ("5 usc app 3", "/us/usc/t5a/s3"),
    ("5 USC app. § 3", "/us/usc/t5a/s3"),
    ("50 U.S.C. App. 2170", "/us/usc/t50a/s2170"),
    ("5 U.S.C. Appendix 3", "/us/usc/t5a/s3"),
    ("section 3 of title 5 app.", "/us/usc/t5a/s3"),
]

INVERTED = [
    ("section 523 of title 11", "/us/usc/t11/s523"),
    ("Section 523 of Title 11", "/us/usc/t11/s523"),
    ("Sec. 523 of Title 11", "/us/usc/t11/s523"),
    ("sec 523(a)(1) of title 11", "/us/usc/t11/s523/a/1"),
    ("§ 523 of title 11", "/us/usc/t11/s523"),
    # The form OLRC uses in its own notes.
    ("Section 14123(a)(2), 49 U.S.C.", "/us/usc/t49/s14123/a/2"),
    ("Section 14123, 49 USC", "/us/usc/t49/s14123"),
]

# The terse form, and the one no other parser handles.
SLASHED = [
    ("11/523", "/us/usc/t11/s523"),
    ("11/523/a/1", "/us/usc/t11/s523/a/1"),
    ("16/45f/c/5", "/us/usc/t16/s45f/c/5"),
    ("5a/3", "/us/usc/t5a/s3"),
]

# A URL path pasted straight back in — it must round-trip.
PATHS = [
    ("/us/usc/t11/s523", "/us/usc/t11/s523"),
    ("us/usc/t11/s523", "/us/usc/t11/s523"),
    ("t11/s523", "/us/usc/t11/s523"),
    ("/us/usc/t16/s45f/c/5", "/us/usc/t16/s45f/c/5"),
    ("/us/usc/t16/s45f/c/5/", "/us/usc/t16/s45f/c/5"),
    ("/us/usc/t5a/s3", "/us/usc/t5a/s3"),
]

STRUCTURAL = [
    ("11 usc ch. 5", "/us/usc/t11/ch5"),
    ("11 USC chapter 5", "/us/usc/t11/ch5"),
    ("title 11, chapter 5", "/us/usc/t11/ch5"),
    ("16 USC subchapter VI", "/us/usc/t16/schVI"),
    ("/us/usc/t16/ch1", "/us/usc/t16/ch1"),
    ("t16/ch1", "/us/usc/t16/ch1"),
]

TITLE_ONLY = [
    ("title 11", "/us/usc/t11"),
    ("Title 11", "/us/usc/t11"),
    ("11 usc", "/us/usc/t11"),
    ("11 U.S.C.", "/us/usc/t11"),
    ("/us/usc/t11", "/us/usc/t11"),
    ("t11", "/us/usc/t11"),
    ("title 5 app.", "/us/usc/t5a"),
]

ALL_FORMS = (
    STANDARD
    + SUBDIVISIONS
    + AWKWARD_SECTION_NUMBERS
    + APPENDIX
    + INVERTED
    + SLASHED
    + PATHS
    + STRUCTURAL
    + TITLE_ONLY
)


@pytest.mark.parametrize(("text", "expected"), ALL_FORMS)
def test_every_accepted_form(text: str, expected: str) -> None:
    parsed = parse_citation(text)
    assert parsed is not None, f"{text!r} did not parse"
    assert parsed.identifier == expected


# ---------------------------------------------------------------- the rejects


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "foo",
        "hello world",
        # The one ambiguity worth naming: a section with no title. Resolvable
        # only by guessing, and guessing is worse than asking.
        "523",
        "§ 523",
        "section 523",
        "(a)(1)",
        # Not the US Code.
        "42 CFR 405",
        "Pub. L. 117-58",
        "410 U.S. 113",
    ],
)
def test_what_must_not_parse(text: str) -> None:
    assert parse_citation(text) is None


# ------------------------------------------------------------- the fine detail


def test_subdivision_case_is_preserved() -> None:
    """USLM identifiers are case-sensitive: `(B)` is `/B`, and lowercasing it
    produces a path that resolves to nothing."""
    parsed = parse_citation("11 usc 523(a)(1)(B)(ii)")

    assert parsed.subdivisions == ("a", "1", "B", "ii")
    assert parsed.identifier.endswith("/a/1/B/ii")


def test_the_section_is_reported_apart_from_the_provision() -> None:
    """A provision path is extracted from the section's XML at request time
    (ADR-0001) and is never a row, so an existence check has to ask about the
    section."""
    parsed = parse_citation("11 usc 523(a)(1)")

    assert parsed.identifier == "/us/usc/t11/s523/a/1"
    assert parsed.section_identifier == "/us/usc/t11/s523"
    assert parsed.section_num == "523"
    assert parsed.title_num == "11"


def test_an_appendix_title_is_reported_as_the_title_it_is() -> None:
    parsed = parse_citation("5 U.S.C. App. 3")

    assert parsed.title_num == "5a"
    assert parsed.section_identifier == "/us/usc/t5a/s3"


@pytest.mark.parametrize("text", ["11 usc 523 note", "11 U.S.C. § 523, note"])
def test_a_note_is_recorded_not_resolved(text: str) -> None:
    """This site serves no note routes. The flag lets the caller say so rather
    than silently sending the reader to the section as if nothing was asked."""
    parsed = parse_citation(text)

    assert parsed.identifier == "/us/usc/t11/s523"
    assert parsed.note is True
    assert parsed.et_seq is False


@pytest.mark.parametrize("text", ["11 usc 523 et seq.", "11 usc 523 et seq"])
def test_et_seq_is_recorded(text: str) -> None:
    parsed = parse_citation(text)

    assert parsed.identifier == "/us/usc/t11/s523"
    assert parsed.et_seq is True
    assert parsed.note is False


def test_kinds_are_distinguished() -> None:
    assert parse_citation("11 usc 523").kind == "section"
    assert parse_citation("11 usc ch. 5").kind == "structure"
    assert parse_citation("title 11").kind == "title"


def test_a_path_carrying_a_level_and_a_section_keeps_only_the_section() -> None:
    """`/us/usc/t16/ch1/s45f` is how a person might write "section 45f of
    chapter 1", but the section's own identifier does not carry its chapter —
    keeping it would build a path no row has."""
    parsed = parse_citation("/us/usc/t16/ch1/s45f")

    assert parsed.identifier == "/us/usc/t16/s45f"


def test_a_leading_zero_is_not_a_different_title() -> None:
    """OLRC's *file* names are zero-padded (`05`); its identifiers are not."""
    assert parse_citation("05 usc 552").identifier == "/us/usc/t5/s552"


def test_the_result_is_immutable() -> None:
    """A parsed citation is a value, and gets handed to a template."""
    parsed = parse_citation("11 usc 523")
    with pytest.raises(Exception):
        parsed.identifier = "/us/usc/t99/s1"  # type: ignore[misc]


def test_an_appendix_section_is_named_but_not_resolvable() -> None:
    """The honest half of appendix support, recorded so it is not read as a bug.

    `5 U.S.C. App. 3` genuinely names section 3 of the Appendix to Title 5, and
    `/us/usc/t5a/s3` is the identifier that names it. OLRC does not publish it
    there: counted over the loaded corpus, **0 of 461** appendix sections use the
    flat `/us/usc/tNa/sX` form — they are `/us/usc/t5a/pl/92/463/s1` (public law)
    or `/us/usc/t50a/act/1917-05-18/ch15/s212` (act by date).

    So the parse is right and the lookup will miss. `appendix` is what lets the
    API say that instead of a bare "not found"; inventing a citation-to-public-law
    mapping here would be worse than the gap.
    """
    parsed = parse_citation("5 U.S.C. App. 3")

    assert parsed.identifier == "/us/usc/t5a/s3"
    assert parsed.appendix is True
    assert parse_citation("5 usc 3").appendix is False
