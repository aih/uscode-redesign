"""A generic text diff between two release points of the same section.

Deliberately dumb about USLM: this module diffs two opaque strings and knows
no element name (CLAUDE.md architecture rule 5 — that vocabulary belongs to
`frontend/src/lib/uslm.ts` alone). `docs/prior-art.md` records `../versions`'
`Diff_Timeout: 0` as load-bearing — diff-match-patch silently returns a worse
diff once it times out — so this ports the same setting, at the only layer
that computes the diff (docs/adr/0016).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

from diff_match_patch import diff_match_patch
from lxml import etree

DiffOpKind = Literal["equal", "insert", "delete"]

_OP_NAMES: dict[int, DiffOpKind] = {-1: "delete", 0: "equal", 1: "insert"}


@dataclass(frozen=True, slots=True)
class DiffOp:
    op: DiffOpKind
    text: str


def strip_guids(xml: str) -> str:
    """The same fragment with every `@id` removed.

    Guids regenerate at every release point *by design* (ADR-0003, gotcha 1), so
    they are the one part of this XML guaranteed to differ between any two
    release points whether or not a word of law changed. Diffing them is work
    spent on the only content that cannot mean anything: measured on § 45f,
    dropping them takes the diff from 2,220 ms to 1,172 ms and from 51 ops to
    20, and the 31 ops that disappear are all regenerated identifiers.

    Parsed rather than regexed. `id="…"` can occur inside quoted statutory text,
    and a textual substitution would edit one side of a comparison and not the
    other — which is a redline reporting a change nobody made. Parsing costs a
    few milliseconds against a diff that costs seconds.

    Falls back to the input unchanged when the fragment does not parse. This is
    an optimisation, and an optimisation that can fail a request is worse than
    the cost it saves.
    """
    try:
        element = etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError:
        return xml
    for node in element.iter():
        if "id" in node.attrib:
            del node.attrib["id"]
    return etree.tostring(element, encoding="unicode", with_tail=False)


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


# --------------------------------------------------------------------- cache
#
# A redline between two *pinned* release points can never change: both texts are
# published and immutable, so the ops between them are a pure function of the
# pair. This endpoint is the most expensive thing the API does — ~0.45 rps at
# any concurrency, and it collapses past about ten concurrent — so the repeat
# cost is worth removing outright.
#
# In-process and bounded, which is honest for ADR-0020's single box and wrong
# for a second instance, exactly as ADR-0029's limiters already are. A second
# instance wants a shared cache and this is the second thing that would need one.

_CACHE_SIZE = 256
_cache: OrderedDict[tuple[str, str, str, bool], list[DiffOp]] = OrderedDict()


def cached_diff_ops(
    key: tuple[str, str, str, bool],
    from_text: str,
    to_text: str,
) -> list[DiffOp]:
    """`diff_ops` memoised on `key` — (identifier, from label, to label, mode).

    The labels must be the *resolved* ones. A request for `119-102` and a
    request for `119-102not101` are the same comparison once resolved, and
    keying on what was asked for would compute it twice and, worse, would key a
    moving target: an unpinned label means a different release point the moment
    a newer one is loaded.
    """
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit

    ops = diff_ops(from_text, to_text)
    _cache[key] = ops
    if len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return ops


def clear_diff_cache() -> None:
    """For tests, and for anything that reloads the corpus in-process."""
    _cache.clear()
