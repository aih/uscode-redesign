#!/usr/bin/env python
"""Build `tests/fixtures/usc16_slice.xml` from `samples/uslm1/usc16.xml`.

The default `make test` must never parse the 32 MB sample (CLAUDE.md test speed
rule), so unit tests run against a slice that still contains every shape the
parser has to get right:

  * the real `<uscDoc>`/`<meta>`/`<title>` wrapper, verbatim;
  * Title 16 chapter 1, subchapters I-VI, truncated after § 45f (the known-good
    provision `/us/usc/t16/s45f/c/5` -> `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd`);
  * repealed, omitted and transferred sections (subchapter I alone has all three);
  * subchapter XIII, which contains `<section>` elements nested in
    `<quotedContent>` — text quoted from amending acts, not code sections;
  * subchapter XCVII, Title 16's one `status="reserved"` element, which is a
    subchapter rather than a section.

Only two edits are made to the copied XML, both to keep the file small: `<toc>`
bodies are truncated, and unselected siblings are dropped. Nothing is rewritten,
so every retained element is byte-identical to OLRC's output.

Usage: uv run python scripts/extract_fixture.py [--source PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "samples" / "uslm1" / "usc16.xml"
DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "usc16_slice.xml"

USLM = "http://xml.house.gov/schemas/uslm/1.0"
NS = {"u": USLM}

CHAPTER = "/us/usc/t16/ch1"
LAST_SECTION = "/us/usc/t16/s45f"
KEEP_SUBCHAPTERS_THROUGH = "/us/usc/t16/ch1/schVI"
EXTRA_SUBCHAPTERS = (
    "/us/usc/t16/ch1/schXIII",  # sections nested in <quotedContent>
    "/us/usc/t16/ch1/schXCVII",  # status="reserved", on a subchapter
)
TOC_ITEMS_KEPT = 5


def q(local_name: str) -> str:
    return f"{{{USLM}}}{local_name}"


def build_slice(source: Path) -> etree._ElementTree:
    tree = etree.parse(str(source))
    root = tree.getroot()

    title = root.find(f"{q('main')}/{q('title')}")
    chapter = title.find(f"{q('chapter')}[@identifier='{CHAPTER}']")

    keep_through = chapter.find(f"{q('subchapter')}[@identifier='{KEEP_SUBCHAPTERS_THROUGH}']")
    last_kept_index = list(chapter).index(keep_through)
    keep_ids = {
        child.get("identifier")
        for child in list(chapter)[: last_kept_index + 1]
        if child.get("identifier")
    } | set(EXTRA_SUBCHAPTERS)

    # Chapter 1: keep <num>/<heading>/<toc> and the selected subchapters.
    for child in list(chapter):
        identifier = child.get("identifier")
        if child.tag == q("subchapter") and identifier not in keep_ids:
            chapter.remove(child)

    # Subchapter VI: stop after § 45f.
    section = keep_through.find(f"{q('section')}[@identifier='{LAST_SECTION}']")
    for child in list(keep_through)[list(keep_through).index(section) + 1 :]:
        keep_through.remove(child)

    # Title: keep everything except the other 152 chapters.
    for child in list(title):
        if child.tag == q("chapter") and child is not chapter:
            title.remove(child)

    # TOCs are ~90% of the remaining bytes and are not what these tests exercise;
    # keep the first few entries so the element shape survives.
    for toc in root.iter(q("toc")):
        for child in list(toc)[TOC_ITEMS_KEPT:]:
            toc.remove(child)

    return tree


def summarize(tree: etree._ElementTree) -> dict[str, int]:
    root = tree.getroot()
    sections = root.findall(f".//{q('section')}")
    quoted = [
        section
        for section in sections
        if any(a.tag == q("quotedContent") for a in section.iterancestors())
    ]
    real = [s for s in sections if s not in quoted and s.get("identifier")]
    counts = {"section_elements": len(sections), "quoted": len(quoted), "real": len(real)}
    for status in ("repealed", "omitted", "transferred", "reserved"):
        counts[status] = sum(1 for s in real if s.get("status") == status)
    counts["reserved_non_section"] = sum(
        1
        for e in root.iter()
        if e.get("status") == "reserved" and e.tag != q("section")
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    tree = build_slice(args.source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(args.out), encoding="utf-8", xml_declaration=True)

    counts = summarize(tree)
    print(f"wrote {args.out.relative_to(REPO_ROOT)} ({args.out.stat().st_size:,} bytes)")
    for key, value in counts.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
