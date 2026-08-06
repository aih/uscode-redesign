"""How deep does the subsection ladder go, and how wide are its numbers?

`site.scss` indents every level of a provision by one step of `--indent-step`,
and the numbers hang into that step. Two facts decide whether the step is the
right size, and neither is a matter of taste:

  * **How many steps a real provision spends.** The indent is cumulative, so the
    deepest clause in the corpus is the one that has to still have a column left
    to be read in at 320 CSS px.
  * **How wide a `<num>` gets.** A number wider than the step pushes the text
    beside it instead of wrapping under it, which is the failure the hanging
    indent exists to prevent. `(a)` is three characters; `(viii)` is seven, and
    the step has to be chosen knowing the second one exists.

    uv run python scripts/ladder.py

Writes docs/verification/ladder.json from the committed samples — no database
and no network. `frontend/tests/e2e/typography.spec.ts` reads the depth this
reports and asserts the rendered ladder against it.

Sections quoted inside `<quotedContent>` are excluded throughout (ADR-0005):
they are statutory text quoted by an amending act, they carry no `@identifier`,
and counting their nesting would inflate every number here.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "verification" / "ladder.json"

SAMPLES = [
    ("uslm1", ROOT / "samples" / "uslm1" / "usc16.xml"),
    ("uslm2", ROOT / "samples" / "uslm2" / "USLM2" / "usc16.xml"),
    ("uslm2", ROOT / "samples" / "uslm2" / "USLM2" / "usc49.xml"),
    ("uslm2", ROOT / "samples" / "uslm2" / "USLM2" / "usc01.xml"),
]

#: The rungs of the ladder, below a section. Kept in step with `LEVEL_TAGS` in
#: `frontend/src/lib/uslm.ts`, minus the containers above a section — a chapter
#: never nests inside a provision, and counting one would put the whole title's
#: structure into a depth that only measures the text of one section.
LEVEL_TAGS = {
    "subsection",
    "paragraph",
    "subparagraph",
    "clause",
    "subclause",
    "item",
    "subitem",
    "subdivision",
    "level",
}


def local(tag: Any) -> str:
    """`{ns}subsection` -> `subsection`; comments and PIs have non-string tags."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


#: Editorial footnote bodies. USLM 1.x writes `<note type="footnote">` and 2.x
#: writes `<footnote>`, and both put them *inside* the `<num>` they annotate.
FOOTNOTE_TAGS = {"note", "footnote"}


def designator(num: Any) -> tuple[str, bool]:
    """The text of a `<num>`, and whether a footnote body was taken out of it.

    The source parks editorial footnotes inside the number itself —
    `<num>(d) <ref class="footnoteRef">1</ref><footnote><num><sup>1</sup></num>
    So in original. Two subsecs. (d) have been enacted.</footnote></num>`.
    Counted whole, that designator is 58 characters and the widest at its depth,
    which says nothing about how much room a number needs. The reference marker
    stays — it is what the reader sees beside the number — and the body does not.
    """
    carries_footnote = False
    parts: list[str] = []

    def visit(el: Any, top: bool) -> None:
        nonlocal carries_footnote
        if not top and local(el.tag) in FOOTNOTE_TAGS:
            carries_footnote = True
            if el.tail:
                parts.append(el.tail)
            return
        if el.text:
            parts.append(el.text)
        for child in el:
            visit(child, False)
        if not top and el.tail:
            parts.append(el.tail)

    visit(num, True)
    return " ".join("".join(parts).split()), carries_footnote


def summarise_widths(num_lengths: dict[int, Counter[int]]) -> dict[str, dict[str, int]]:
    """Characters in the designator at each depth: the median one and the worst."""
    out: dict[str, dict[str, int]] = {}
    for depth, counts in sorted(num_lengths.items()):
        widths = sorted(counts.elements())
        out[str(depth)] = {
            "count": len(widths),
            "median": widths[len(widths) // 2],
            "p99": widths[min(len(widths) - 1, int(0.99 * len(widths)))],
            "max": widths[-1],
        }
    return out


def scan(path: Path) -> dict[str, Any]:
    """Walk one title, recording the ladder under every real code section."""
    #: How many sections bottom out at each depth. Depth 0 is a section with no
    #: subsections at all — a single block of text, which is most of them.
    section_depths: Counter[int] = Counter()
    #: Every level element, by the depth it sits at.
    rungs: Counter[int] = Counter()
    #: The `<num>` strings seen at each depth, longest kept.
    widest: dict[int, str] = {}
    num_lengths: dict[int, Counter[int]] = defaultdict(Counter)
    #: The deepest provision in the file, by identifier, so the claim is checkable.
    deepest = {"depth": 0, "identifier": None}
    #: `@class` values the source writes that this stylesheet has to share a
    #: column with — the second indentation scale, inside notes and tables.
    indent_classes: Counter[str] = Counter()

    sections = 0
    #: Numbers the source has parked an editorial footnote body inside.
    nums_with_footnote = 0
    #: Names of the open elements, outermost first — the ladder as it stands.
    stack: list[str] = []
    quoted_depth = 0
    section_id: str | None = None
    section_max = 0

    for event, el in etree.iterparse(str(path), events=("start", "end"), recover=True):
        name = local(el.tag)
        if not name:
            continue

        if event == "start":
            if name == "quotedContent":
                quoted_depth += 1
            stack.append(name)

            source_class = el.get("class")
            if source_class and "indent" in source_class:
                indent_classes[source_class] += 1

            if quoted_depth:
                continue

            if name == "section":
                # A nested `<section>` outside `<quotedContent>` does not occur
                # in the samples; if it ever does, the inner one wins, which is
                # the conservative reading.
                sections += 1
                section_id = el.get("identifier")
                section_max = 0
            elif name in LEVEL_TAGS and section_id is not None:
                depth = sum(1 for tag in stack[:-1] if tag in LEVEL_TAGS) + 1
                rungs[depth] += 1
                section_max = max(section_max, depth)
            continue

        # end. A `<num>` is only complete here: at its start event lxml has read
        # the tag and nothing inside it, so anything read there is whatever
        # happened to be in the same buffer.
        if name == "num" and not quoted_depth and section_id is not None:
            depth = sum(1 for tag in stack if tag in LEVEL_TAGS)
            parent = el.getparent()
            if depth and parent is not None and local(parent.tag) in LEVEL_TAGS:
                text, carries_footnote = designator(el)
                if carries_footnote:
                    nums_with_footnote += 1
                if text:
                    num_lengths[depth][len(text)] += 1
                    if len(text) > len(widest.get(depth, "")):
                        widest[depth] = text

        if stack and stack[-1] == name:
            stack.pop()
        if name == "quotedContent":
            quoted_depth = max(0, quoted_depth - 1)
        elif name == "section" and not quoted_depth and section_id is not None:
            section_depths[section_max] += 1
            if section_max > deepest["depth"]:
                deepest["depth"] = section_max
                deepest["identifier"] = section_id
            section_id = None

            # Streaming, per gotcha 6: these samples are not the largest thing
            # this will be pointed at. A finished section is dropped whole,
            # rather than the per-element sibling pruning `inline_elements.py`
            # does — that walks up from the element that just ended, and this
            # script asks `getparent()` about a `<num>` to decide whether the
            # thing it numbers is a level, which a partly dismantled ancestor
            # chain answers wrongly. Measured: the widest designator at depth 1
            # came out as a 55-character editorial footnote from three elements
            # away.
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]

    return {
        "sections": sections,
        "sectionsByMaxDepth": {str(d): n for d, n in sorted(section_depths.items())},
        "levelsByDepth": {str(d): n for d, n in sorted(rungs.items())},
        "widestNumByDepth": {str(d): widest[d] for d in sorted(widest)},
        "numCharsByDepth": summarise_widths(num_lengths),
        "numsWithFootnoteBody": nums_with_footnote,
        "deepest": deepest,
        "sourceIndentClasses": dict(sorted(indent_classes.items())),
        # Popped by `main` before the report is written — the raw distribution
        # is only here so the corpus-wide summary is computed from every
        # measurement rather than from four already-summarised ones.
        "_numLengths": num_lengths,
    }


def main() -> None:
    per_file: dict[str, Any] = {}
    all_depths: Counter[int] = Counter()
    all_widest: dict[int, str] = {}
    all_indent_classes: Counter[str] = Counter()
    all_num_chars: dict[int, Counter[int]] = defaultdict(Counter)
    nums_with_footnote = 0
    deepest = {"depth": 0, "identifier": None, "source": None}

    for schema, path in SAMPLES:
        if not path.exists():
            raise SystemExit(f"missing sample: {path}")
        result = scan(path)
        key = f"{schema}:{path.name}"
        for depth, counts in result.pop("_numLengths").items():
            all_num_chars[depth].update(counts)
        nums_with_footnote += result["numsWithFootnoteBody"]
        per_file[key] = result
        for depth, count in result["sectionsByMaxDepth"].items():
            all_depths[int(depth)] += count
        for depth, text in result["widestNumByDepth"].items():
            if len(text) > len(all_widest.get(int(depth), "")):
                all_widest[int(depth)] = text
        for name, count in result["sourceIndentClasses"].items():
            all_indent_classes[name] += count
        if result["deepest"]["depth"] > deepest["depth"]:
            deepest = {**result["deepest"], "source": key}

    total = sum(all_depths.values())
    cumulative = 0
    reach: dict[str, float] = {}
    for depth in sorted(all_depths):
        cumulative += all_depths[depth]
        reach[str(depth)] = round(100 * cumulative / total, 3)

    report = {
        "_comment": (
            "Generated by scripts/ladder.py from the committed samples. Do not hand-edit — "
            "re-run it. Depth counts rungs of the (a)/(1)/(A)/(i) ladder below a section: a "
            "section with no subsections is depth 0. Sections quoted inside <quotedContent> "
            "are excluded (ADR-0005). widestNumByDepth is the longest <num> string seen at "
            "each depth, and numCharsByDepth its length in characters. Editorial footnote "
            "bodies are excluded from both: the source parks them inside the <num> they "
            "annotate, and numsWithFootnoteBody counts how often. sectionsWithin is the "
            "percentage of sections no deeper than that rung."
        ),
        "sources": [str(p.relative_to(ROOT)) for _, p in SAMPLES],
        "sections": total,
        "sectionsByMaxDepth": {str(d): all_depths[d] for d in sorted(all_depths)},
        "sectionsWithin": reach,
        "widestNumByDepth": {str(d): all_widest[d] for d in sorted(all_widest)},
        "numCharsByDepth": summarise_widths(all_num_chars),
        "numsWithFootnoteBody": nums_with_footnote,
        "deepest": deepest,
        "sourceIndentClasses": dict(sorted(all_indent_classes.items())),
        "perFile": per_file,
    }

    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{total} sections -> {OUT.relative_to(ROOT)}")
    for depth in sorted(all_depths):
        print(
            f"  depth {depth}: {all_depths[depth]:>6} sections bottom out here "
            f"({reach[str(depth)]}% within)   num chars "
            f"median {report['numCharsByDepth'].get(str(depth), {}).get('median', '—')} "
            f"max {report['numCharsByDepth'].get(str(depth), {}).get('max', '—')}"
        )
    print(f"  deepest: {deepest['identifier']} at depth {deepest['depth']} ({deepest['source']})")


if __name__ == "__main__":
    main()
