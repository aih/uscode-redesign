import pytest

from ingest.release_label import InvalidReleaseLabelError, parse_release_label


def test_parses_congress_law_and_no_exclusions():
    assert parse_release_label("119-94") == (119, 94, [])


def test_parses_a_single_not_exclusion():
    assert parse_release_label("119-102not101") == (119, 102, [101])


def test_parses_compound_not_exclusions():
    """Gotcha 4: skip labels compound (`277not255not268`-shaped)."""
    assert parse_release_label("119-277not255not268") == (119, 277, [255, 268])


@pytest.mark.parametrize(
    "label",
    ["not-a-label", "119", "119-", "119-102-not101", ""],
)
def test_rejects_malformed_labels(label):
    with pytest.raises(InvalidReleaseLabelError):
        parse_release_label(label)
