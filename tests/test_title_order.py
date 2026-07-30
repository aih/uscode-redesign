"""Title numbers are strings, and sorting them as strings is wrong.

`Title.num` has to be a string — `5a` is a title number and `5` is a different
one — so `ORDER BY num` collates `1, 10, 11, 11a, 12, … 2, 20`, which is what the
front page listed until `title_sort_key` existed. No database: this is a pure
function, and the whole point is that it can be checked without one.
"""

import pytest

from storage.postgres import title_sort_key

# The 58 titles actually in the corpus (BUILDLOG 023), in the string order the
# database hands back, so the expected list below is a real before/after.
LOADED = [
    "1", "10", "11", "11a", "12", "13", "14", "15", "16", "17", "18", "18a",
    "19", "2", "20", "21", "22", "23", "24", "25", "26", "27", "28", "28a",
    "29", "3", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "4", "40", "41", "42", "43", "44", "45", "46", "47", "48", "49", "5",
    "50", "50a", "51", "52", "54", "5a", "6", "7", "8", "9",
]

IN_CODE_ORDER = [
    "1", "2", "3", "4", "5", "5a", "6", "7", "8", "9", "10", "11", "11a",
    "12", "13", "14", "15", "16", "17", "18", "18a", "19", "20", "21", "22",
    "23", "24", "25", "26", "27", "28", "28a", "29", "30", "31", "32", "33",
    "34", "35", "36", "37", "38", "39", "40", "41", "42", "43", "44", "45",
    "46", "47", "48", "49", "50", "50a", "51", "52", "54",
]


def test_the_whole_corpus_sorts_into_code_order() -> None:
    assert sorted(LOADED, key=title_sort_key) == IN_CODE_ORDER


def test_the_string_order_it_replaces_was_actually_wrong() -> None:
    """Guards the guard: if these two ever agreed, the test above would pass
    while proving nothing."""
    assert sorted(LOADED) != IN_CODE_ORDER
    assert sorted(LOADED)[:3] == ["1", "10", "11"]


@pytest.mark.parametrize(
    ("num", "expected"),
    [
        ("1", (1, "")),
        ("16", (16, "")),
        ("5a", (5, "a")),
        ("50a", (50, "a")),
        ("54", (54, "")),
    ],
)
def test_the_key_splits_number_from_suffix(num: str, expected: tuple[int, str]) -> None:
    assert title_sort_key(num) == expected


@pytest.mark.parametrize(
    ("earlier", "later"),
    [
        ("5", "5a"),  # gotcha 7: an appendix title follows its parent…
        ("5a", "6"),  # …and precedes the next one, rather than sorting to the end
        ("11a", "12"),
        ("9", "10"),  # the bug in one line
        ("50a", "51"),
    ],
)
def test_appendix_titles_sit_beside_their_parent(earlier: str, later: str) -> None:
    assert title_sort_key(earlier) < title_sort_key(later)


def test_case_in_the_suffix_does_not_split_a_title() -> None:
    assert title_sort_key("5A") == title_sort_key("5a")


def test_an_unparseable_number_sorts_last_rather_than_raising() -> None:
    """Ordering a list is not the place to discover that ingest wrote something
    strange — the list still renders, with the oddity at the bottom."""
    assert sorted(["16", "??", "1"], key=title_sort_key) == ["1", "16", "??"]
