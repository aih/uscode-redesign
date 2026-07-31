"""The syntax guide and the query parser must describe the same thing.

A search syntax guide is a promise, and this is the one kind of promise that
rots silently. `api/search.py` enables a named set of `simple_query_string`
flags; `frontend/src/lib/searchsyntax.ts` is the list the guide page renders.
If a flag is dropped from the API, the guide goes on describing an operator the
cluster now treats as a literal character — and the reader has no way to tell
that apart from a query that legitimately found nothing.

Nothing else checks this. The Python tests do not read the frontend and the
Vitest suite does not read Python, so without this file the two sit in different
languages with no link between them but a comment.

The test reads the TypeScript as text rather than importing it, deliberately:
adding a Node build step to the Python suite to check a list of nine strings
would cost more than it is worth, and the regex fails loudly if the file's shape
changes rather than quietly matching nothing (see `test_guide_is_not_empty`).
"""

import re
from pathlib import Path

import pytest

from api.search import QUERY_SYNTAX_FLAGS

GUIDE = Path(__file__).resolve().parent.parent / "frontend/src/lib/searchsyntax.ts"

FLAG_RE = re.compile(r'^\s*flag:\s*"([A-Z]+)"', re.MULTILINE)


def documented_flags() -> set[str]:
    return set(FLAG_RE.findall(GUIDE.read_text(encoding="utf-8")))


def enabled_flags() -> set[str]:
    return set(QUERY_SYNTAX_FLAGS.split("|"))


def test_guide_file_exists() -> None:
    assert GUIDE.is_file(), f"the syntax guide's operator list is missing: {GUIDE}"


def test_guide_is_not_empty() -> None:
    """Guards the regex itself.

    Every other assertion here compares two sets, and a regex that stopped
    matching would make the documented set empty — which would turn the
    "nothing undocumented" test green while the guide described nothing at all.
    """
    assert len(documented_flags()) >= 5


def test_every_enabled_flag_is_documented() -> None:
    missing = enabled_flags() - documented_flags()
    assert not missing, (
        f"{sorted(missing)} are enabled in api/search.py but absent from the "
        f"syntax guide, so readers are not told the operators exist"
    )


def test_no_flag_is_documented_that_is_not_enabled() -> None:
    extra = documented_flags() - enabled_flags()
    assert not extra, (
        f"the syntax guide documents {sorted(extra)}, which api/search.py does "
        f"not enable — the operator would be matched as literal text"
    )


@pytest.mark.parametrize(
    "flag",
    ["AND", "OR", "NOT", "PHRASE", "PREFIX", "FUZZY", "PRECEDENCE", "WHITESPACE"],
)
def test_the_operators_the_guide_is_for_stay_enabled(flag: str) -> None:
    """The specific flags the product decision depends on.

    ADR-0031 made the search strict and pointed the reader at `~` for
    misspellings; dropping FUZZY would remove the escape hatch the guide sends
    them to. WHITESPACE is here because it is the one that looks safe to remove
    and is not: without it the parser does not split on spaces at all, and
    `water -pollution` silently becomes `water AND pollution` — the opposite of
    what was asked. That was a real mistake made while writing this, caught only
    by `_validate/query?explain=true`, because the query is valid either way.
    """
    assert flag in enabled_flags()
