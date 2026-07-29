"""A generic text diff between two release points of the same section.

Deliberately dumb about USLM: this module diffs two opaque strings and knows
no element name (CLAUDE.md architecture rule 5 — that vocabulary belongs to
`frontend/src/lib/uslm.ts` alone). `docs/prior-art.md` records `../versions`'
`Diff_Timeout: 0` as load-bearing — diff-match-patch silently returns a worse
diff once it times out — so this ports the same setting, at the only layer
that computes the diff (docs/adr/0016).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from diff_match_patch import diff_match_patch

DiffOpKind = Literal["equal", "insert", "delete"]

_OP_NAMES: dict[int, DiffOpKind] = {-1: "delete", 0: "equal", 1: "insert"}


@dataclass(frozen=True, slots=True)
class DiffOp:
    op: DiffOpKind
    text: str


def diff_ops(from_text: str, to_text: str) -> list[DiffOp]:
    """A word-level, human-readable diff of two verbatim XML fragments.

    Identical inputs short-circuit to one `equal` chunk rather than paying for
    a diff that can only ever agree with itself.
    """
    if from_text == to_text:
        return [DiffOp(op="equal", text=from_text)] if from_text else []

    dmp = diff_match_patch()
    dmp.Diff_Timeout = 0  # never trade correctness for speed (docs/prior-art.md)
    diffs = dmp.diff_main(from_text, to_text)
    dmp.diff_cleanupSemantic(diffs)
    return [DiffOp(op=_OP_NAMES[op], text=text) for op, text in diffs]
