"""Release-point label parsing (CLAUDE.md gotcha 4 / PLAN §9.3).

Labels like `119-102not101` don't sort lexically, and skip suffixes can
compound (`277not255not268`). Everything that needs release ordering uses the
parsed `(congress, law_num, excluded_laws)` tuple plus the separately assigned
global `release_points.seq` — never the label text.
"""

from __future__ import annotations

import re

_LABEL_RE = re.compile(r"^(?P<congress>\d+)-(?P<law_num>\d+)(?P<excluded>(?:not\d+)*)$")
_NOT_RE = re.compile(r"not(\d+)")


class InvalidReleaseLabelError(ValueError):
    """Raised when a label doesn't match `{congress}-{law_num}[not{excluded}]*`."""


def parse_release_label(label: str) -> tuple[int, int, list[int]]:
    """Parse `label` into `(congress, law_num, excluded_laws)`."""
    match = _LABEL_RE.match(label)
    if not match:
        raise InvalidReleaseLabelError(
            f"{label!r} does not match '{{congress}}-{{law_num}}[not{{excluded}}...]'"
        )
    congress = int(match.group("congress"))
    law_num = int(match.group("law_num"))
    excluded = [int(n) for n in _NOT_RE.findall(match.group("excluded"))]
    return congress, law_num, excluded
