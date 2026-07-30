"""What a person types, turned into a USLM `@identifier`.

`11 usc 523(a)(1)` → `/us/usc/t11/s523/a/1`. That is the whole job, and doing it
is what lets a reader reach a provision without walking down the hierarchy or
knowing that the URL scheme mirrors OLRC's `@identifier` (PLAN §Day-2 has owed
this since the beginning).

Deliberately named `citeparse`, not `citations`: `citation.py` is the ADR-0010
redirector, and two modules a letter apart is a trap.

**This module is pure.** No database, no `storage/`, no `db/`, no HTTP. It cannot
tell you whether Title 11 § 523 exists — only what string names it — and that
separation is what lets the whole accepted-forms table below run as a unit test
with no fixtures. Existence is the API layer's question, answered with the
`labels()` lookup it already has.

Prior art, read before these patterns were written:

  * `loadusc-xcitedb/loadusc/constants.py` `USC_CITE_REGEX` — this project's own
    ancestor, and the one the sibling `versions` service uses. Too narrow to
    adopt: its subsection class is `[a-z0-9]`, so `(B)` does not match; it knows
    no `§`, no `App.`, and no inverted form. Its `#TODO handle plain text
    citations` is the gap this module closes.
  * `unitedstates/citation`, `citations/usc.js` — the fullest published ruleset,
    and the source of the three shapes handled here (standard, `section X of
    title Y`, `Section X, Y U.S.C.`) plus `App.`, `note` and `et seq.`. The rules
    are ported; the output is not — theirs is a JSON citation object, ours is a
    USLM identifier.

Two things that will be gotten wrong if they are not said out loud:

  * **Subdivision case is preserved.** `(B)` becomes `/B`, never `/b`. USLM
    identifiers are case-sensitive, and `/us/usc/t16/s45f/c/5` is the fixture
    this project checks itself against.
  * **`N app.` becomes `tNa`.** The five appendix titles are stored unpadded as
    `5a`, `11a`, `18a`, `28a`, `50a` (gotcha 7), so `5 U.S.C. App. 3` is
    `/us/usc/t5a/s3` — the identifier that citation *names*.

    It is also an identifier that does not exist, and this is worth knowing
    before someone treats it as a bug. OLRC publishes appendix titles under the
    enacting instrument, not a flat section number. Counted across the loaded
    corpus: **0 of 461 appendix sections** use `/us/usc/tNa/sX`; they are
    `/us/usc/t5a/pl/92/463/s1` (public law) or
    `/us/usc/t50a/act/1917-05-18/ch15/s212` (act by date). So an appendix
    citation parses, and then resolves to nothing.

    Rather than guess at a mapping from `App. 3` to a public law, the parse
    carries `appendix=True` and the API says plainly what happened. Getting from
    a citation to the enacting instrument needs a lookup table this project does
    not have yet; inventing one silently would be worse than the gap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["section", "structure", "title"]

# A section number is not a number: `45f`, `2000e-2`, `78j-1`, `1a` are all real.
# Digits first, then letters, digits and internal hyphens — but never a trailing
# one, which would swallow the dash of a range (`§§ 521-523`).
_SECTION_NUM = r"[0-9]+[A-Za-z0-9]*(?:[-–—][A-Za-z0-9]+)*"

# `(a)(1)(B)(ii)`, and the bare-slash form `/a/1/B/ii` a URL path uses.
_PARENS = r"(?:\([A-Za-z0-9]+\))*"

# `U.S.C.`, `USC`, `U. S. C.`, `usc` — with or without any of the periods.
_USC = r"U\.?\s?S\.?\s?C\.?"

# Structural levels a citation can name instead of a section. USLM's own
# abbreviations, which are also what the identifier uses.
_LEVELS = {
    "ch": "ch",
    "chap": "ch",
    "chapter": "ch",
    "subch": "sch",
    "subchap": "sch",
    "subchapter": "sch",
    "pt": "pt",
    "part": "pt",
    "subpt": "spt",
    "subpart": "spt",
    "subtit": "stI",
    "subtitle": "stI",
}
_LEVEL_WORDS = "|".join(sorted(_LEVELS, key=len, reverse=True))

_TRAILER = r"(?:\s*[,;]?\s*(?P<trailer>note|et\.?\s+seq\.?))?"

# `App.` / `app` / `Appendix`, optionally preceded by a comma — the marker that
# turns title 5 into title 5a.
_APP = r"(?:\s*,?\s*(?P<app>App(?:endix|x)?)\.?)?"


@dataclass(frozen=True)
class ParsedCitation:
    """A citation, resolved to the identifier that names it — and nothing more.

    `identifier` is the deepest thing the citation named; `section_identifier` is
    the section containing it, which is what an existence check should ask about
    (a provision path is extracted from the section's XML at request time,
    ADR-0001, so `/us/usc/t11/s523/a/1` is never a row anywhere).
    """

    identifier: str
    section_identifier: str
    title_num: str
    section_num: str | None = None
    subdivisions: tuple[str, ...] = ()
    #: Every spelling of `section_identifier` worth looking up, as-typed first.
    #:
    #: Only dashes vary, and only because OLRC writes section numbers with an
    #: EN DASH: `/us/usc/t16/s45a–1`, U+2013. Measured over the loaded corpus,
    #: **5,697 of 65,938 sections contain one and not a single section contains
    #: a plain hyphen** — so `42 USC 2000e-2`, typed the only way a keyboard
    #: offers, matches nothing at all unless something tries the variant.
    #:
    #: Generating candidates rather than rewriting is what keeps this module
    #: honest: `-` and `–` are different characters, this layer does not know
    #: which one the corpus holds, and the caller's lookup is batched anyway
    #: (`Repository.labels`), so asking for three costs what asking for one did.
    section_variants: tuple[str, ...] = ()
    kind: Kind = "section"
    #: A trailing `note` — recorded, not resolved. This site serves no note routes.
    note: bool = False
    #: A trailing `et seq.` — the citation names a run starting here.
    et_seq: bool = False
    #: One of the five appendix titles (gotcha 7). Worth flagging separately
    #: because the identifier built here is the one the *citation* names, and
    #: OLRC does not publish appendix sections under it — see the class docstring
    #: of `tests/test_citeparse.py::test_an_appendix_section_is_named_but_not_resolvable`.
    appendix: bool = False


@dataclass
class _Parts:
    title: str
    app: bool = False
    section: str | None = None
    subdivisions: list[str] = field(default_factory=list)
    level: str | None = None
    level_num: str | None = None
    note: bool = False
    et_seq: bool = False


def _subdivisions(text: str | None) -> list[str]:
    """`'(a)(1)(B)(ii)'` → `['a', '1', 'B', 'ii']`. Case is kept: USLM
    identifiers distinguish `(b)` from `(B)`."""
    if not text:
        return []
    return re.findall(r"\(([A-Za-z0-9]+)\)", text)


def _title_segment(title: str, app: bool) -> str:
    """`('5', True)` → `t5a`. The appendix titles are stored unpadded."""
    num = title.lstrip("0") or "0"
    if app and not num.lower().endswith("a"):
        return f"t{num}a"
    return f"t{num.lower()}"


def _is_appendix(title_id: str) -> bool:
    return bool(re.search(r"/t[0-9]+a$", title_id))


#: Hyphen-minus, en dash, em dash. OLRC uses the middle one; keyboards offer the
#: first; the third turns up in text pasted out of a word processor.
_DASHES = ("-", "–", "—")


def _dash_variants(identifier: str) -> tuple[str, ...]:
    """Every dash spelling of an identifier, the given one first.

    Order matters: the caller looks these up and takes the first that exists, so
    what the reader actually typed wins any tie.
    """
    if not any(dash in identifier for dash in _DASHES):
        return (identifier,)
    seen: list[str] = [identifier]
    for dash in _DASHES:
        candidate = re.sub(r"[-–—]", dash, identifier)
        if candidate not in seen:
            seen.append(candidate)
    return tuple(seen)


def _build(parts: _Parts) -> ParsedCitation:
    title_id = f"/us/usc/{_title_segment(parts.title, parts.app)}"

    if parts.level and parts.level_num:
        node = f"{title_id}/{parts.level}{parts.level_num}"
        return ParsedCitation(
            identifier=node,
            section_identifier=node,
            title_num=title_id.rsplit("/t", 1)[1],
            kind="structure",
            note=parts.note,
            et_seq=parts.et_seq,
            appendix=_is_appendix(title_id),
            section_variants=_dash_variants(node),
        )

    if not parts.section:
        return ParsedCitation(
            identifier=title_id,
            section_identifier=title_id,
            title_num=title_id.rsplit("/t", 1)[1],
            kind="title",
            note=parts.note,
            et_seq=parts.et_seq,
            appendix=_is_appendix(title_id),
            section_variants=(title_id,),
        )

    section_id = f"{title_id}/s{parts.section}"
    deepest = section_id + "".join(f"/{s}" for s in parts.subdivisions)
    return ParsedCitation(
        identifier=deepest,
        section_identifier=section_id,
        title_num=title_id.rsplit("/t", 1)[1],
        section_num=parts.section,
        subdivisions=tuple(parts.subdivisions),
        kind="section",
        note=parts.note,
        et_seq=parts.et_seq,
        appendix=_is_appendix(title_id),
        section_variants=_dash_variants(section_id),
    )


def _trailer(parts: _Parts, text: str | None) -> None:
    if not text:
        return
    if text.lower().startswith("note"):
        parts.note = True
    else:
        parts.et_seq = True


# ---------------------------------------------------------------- the patterns

# 1. An identifier or a fragment of one, typed straight in: `/us/usc/t11/s523`,
#    `us/usc/t11/s523/a/1`, `t11/s523`. Handled first and separately, because a
#    path is not a citation and running it through the prose patterns would find
#    "11" and "523" by accident and lose the subdivisions.
_PATH = re.compile(
    r"^(?:/?us/usc/)?"
    r"t(?P<title>[0-9]+[a-zA-Z]?)"
    r"(?:/(?P<level>ch|sch|pt|spt|stI|d|sd)(?P<level_num>[A-Za-z0-9]+))?"
    r"(?:/s(?P<section>" + _SECTION_NUM + r"))?"
    r"(?P<rest>(?:/[A-Za-z0-9]+)*)/?$",
    re.IGNORECASE,
)

# 2. `11/523`, `11/523/a/1` — the terse form, and the one nothing else parses.
_SLASHED = re.compile(
    r"^(?P<title>[0-9]+[aA]?)/(?P<section>" + _SECTION_NUM + r")"
    r"(?P<rest>(?:/[A-Za-z0-9]+)*)/?$"
)

# 3. The standard citation: `11 U.S.C. § 523(a)(1)`, `11 usc 523`, `5 USC App. 3`.
_STANDARD = re.compile(
    r"^(?P<title>[0-9]+[aA]?)\s*" + _USC + _APP + r"\s*"
    r"(?:§{1,2}\s*)?"
    r"(?:"
    r"(?P<level>" + _LEVEL_WORDS + r")\.?\s*(?P<level_num>[A-Za-z0-9]+)"
    r"|"
    r"(?P<section>" + _SECTION_NUM + r")(?P<subs>" + _PARENS + r")"
    r")?" + _TRAILER + r"\.?$",
    re.IGNORECASE,
)

# 4. Inverted: `section 523 of title 11`, `Sec. 523(a) of Title 11`.
_INVERTED = re.compile(
    r"^(?:§{1,2}|sec(?:tion)?s?\.?)\s*"
    r"(?P<section>" + _SECTION_NUM + r")(?P<subs>" + _PARENS + r")\s*"
    r"of\s+title\s+(?P<title>[0-9]+[aA]?)" + _APP + _TRAILER + r"\.?$",
    re.IGNORECASE,
)

# 5. Abbreviated inverted: `Section 14123(a)(2), 49 U.S.C.` — the form the House
#    Office of the Law Revision Counsel uses in its own notes.
_TRAILING_TITLE = re.compile(
    r"^(?:§{1,2}|sec(?:tion)?s?\.?)\s*"
    r"(?P<section>" + _SECTION_NUM + r")(?P<subs>" + _PARENS + r")\s*,\s*"
    r"(?P<title>[0-9]+[aA]?)\s*" + _USC + _APP + _TRAILER + r"\.?$",
    re.IGNORECASE,
)

# 6. `title 11`, `11 usc`, `title 5 app.` — a whole title, and a legitimate
#    destination: it is the table of contents.
_TITLE_ONLY = re.compile(
    r"^(?:title\s+(?P<title_a>[0-9]+[aA]?)" + _APP + r"|"
    r"(?P<title_b>[0-9]+[aA]?)\s*" + _USC + r")\.?$",
    re.IGNORECASE,
)

# 7. `11 usc ch. 5` handled by _STANDARD; this is `title 11, chapter 5`.
_TITLE_LEVEL = re.compile(
    r"^title\s+(?P<title>[0-9]+[aA]?)" + _APP + r"\s*,?\s*"
    r"(?P<level>" + _LEVEL_WORDS + r")\.?\s*(?P<level_num>[A-Za-z0-9]+)\.?$",
    re.IGNORECASE,
)


def _wraps_whole(text: str) -> bool:
    """True when the leading `(` is closed by the final `)` — i.e. the parens
    enclose the citation rather than belonging to it."""
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index == len(text) - 1
    return False


def _normalize(text: str) -> str:
    """Collapse whitespace and drop the punctuation a citation can be wrapped in.

    Wrapping parentheses are removed one balanced pair at a time, never by
    `strip()`: `(11 U.S.C. 523)` is a citation in brackets, and
    `11 usc 523(a)(1)` ends in a bracket that is part of the citation. Stripping
    characters blindly turned the second into `11 usc 523(a)(1` and cost six of
    the forms in the table.

    `§` is left alone — it is a signal, not noise.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    while True:
        stripped = cleaned.strip(" ,;\"'[]")
        if stripped.startswith("(") and stripped.endswith(")") and _wraps_whole(stripped):
            stripped = stripped[1:-1]
        if stripped == cleaned:
            return cleaned
        cleaned = stripped


def parse_citation(text: str) -> ParsedCitation | None:
    """A citation in any of the forms above → the identifier it names.

    `None` when nothing matches, which includes the one ambiguous case worth
    naming: a bare section number (`523`) with no title. It is unresolvable
    without guessing, and guessing is worse than asking.
    """
    if not text or not text.strip():
        return None
    cleaned = _normalize(text)
    if not cleaned:
        return None

    for pattern in (_PATH, _SLASHED):
        match = pattern.match(cleaned)
        if match:
            groups = match.groupdict()
            rest = [s for s in (groups.get("rest") or "").split("/") if s]
            level = groups.get("level")
            parts = _Parts(
                title=re.sub(r"[aA]$", "", groups["title"]),
                app=bool(re.search(r"[aA]$", groups["title"])),
                section=groups.get("section"),
                subdivisions=rest,
                level=level.lower() if level else None,
                level_num=groups.get("level_num"),
            )
            # `t11/ch5` with no section is a structural node; `t11` alone is the
            # title. `_build` reads that off `level`/`section` directly.
            if parts.level and parts.section:
                # `/us/usc/t16/ch1/s45f` — the level is context the section
                # identifier does not carry, so it is dropped rather than
                # producing a path no row has.
                parts.level = parts.level_num = None
            return _build(parts)

    for pattern in (_TITLE_LEVEL, _TRAILING_TITLE, _INVERTED, _STANDARD):
        match = pattern.match(cleaned)
        if match:
            groups = match.groupdict()
            level = groups.get("level")
            parts = _Parts(
                title=groups["title"],
                app=bool(groups.get("app")),
                section=groups.get("section"),
                subdivisions=_subdivisions(groups.get("subs")),
                level=_LEVELS[level.lower()] if level else None,
                level_num=groups.get("level_num"),
            )
            _trailer(parts, groups.get("trailer"))
            return _build(parts)

    match = _TITLE_ONLY.match(cleaned)
    if match:
        groups = match.groupdict()
        title = groups.get("title_a") or groups.get("title_b")
        return _build(
            _Parts(
                title=re.sub(r"[aA]$", "", title),
                app=bool(groups.get("app")) or bool(re.search(r"[aA]$", title)),
            )
        )

    return None
