"""Release-point label parsing (CLAUDE.md gotcha 4 / PLAN §9.4).

Labels like `119-102not101` don't sort lexically, and skip suffixes can
compound (`277not255not268`). Everything that needs release ordering uses the
parsed `(congress, law_num, excluded_laws)` tuple plus the separately assigned
global `release_points.seq` — never the label text.

A third form only shows up once you read the real inventory: a trailing `u{n}`
"update" suffix (`118-22u1`, `116-344not283u1`, `113-145not128u1` — 17 of the 385
published release points). Those are re-issues of the same public law with
non-statutory updates folded in, most often the Court Rules. `118-22` and
`118-22u1` are two distinct release points with two distinct sets of files, so
`(congress, law_num, excluded_laws)` alone neither identifies a release point nor
orders one against the other; `update_num` keeps that distinction addressable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LABEL_RE = re.compile(
    r"^(?P<congress>\d+)-(?P<law_num>\d+)(?P<excluded>(?:not\d+)*)(?:u(?P<update>\d+))?$"
)
_NOT_RE = re.compile(r"not(\d+)")


class InvalidReleaseLabelError(ValueError):
    """Raised when a label doesn't match `{congress}-{law_num}[not{excluded}]*[u{n}]`."""


@dataclass(frozen=True, slots=True)
class ReleaseLabel:
    """A parsed release-point label. `update_num` is None for the ordinary form."""

    congress: int
    law_num: int
    excluded_laws: tuple[int, ...]
    update_num: int | None = None

    def __str__(self) -> str:
        excluded = "".join(f"not{n}" for n in self.excluded_laws)
        update = f"u{self.update_num}" if self.update_num is not None else ""
        return f"{self.congress}-{self.law_num}{excluded}{update}"


def parse_label(label: str) -> ReleaseLabel:
    """Parse `label` into its components. Raises `InvalidReleaseLabelError`."""
    match = _LABEL_RE.match(label)
    if not match:
        raise InvalidReleaseLabelError(
            f"{label!r} does not match "
            "'{congress}-{law_num}[not{excluded}...][u{update}]'"
        )
    update = match.group("update")
    return ReleaseLabel(
        congress=int(match.group("congress")),
        law_num=int(match.group("law_num")),
        excluded_laws=tuple(int(n) for n in _NOT_RE.findall(match.group("excluded"))),
        update_num=int(update) if update is not None else None,
    )


def parse_release_label(label: str) -> tuple[int, int, list[int]]:
    """`(congress, law_num, excluded_laws)` — three of the columns `release_points` keeps."""
    parsed = parse_label(label)
    return parsed.congress, parsed.law_num, list(parsed.excluded_laws)
