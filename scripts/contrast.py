"""Contrast ratios for every colour pair the reader puts on screen.

WCAG 2.1 AA asks for 4.5:1 on body text, 3:1 on large text, and 3:1 on the
non-text parts of a user interface — borders, focus rings, the edge of a
highlight. The reader has two palettes (ADR-0027), so every one of those is two
questions, and "it looks fine" answers neither.

The values are read from `frontend/src/styles/site.scss` rather than typed in
here: the token block is the source of truth, and a table maintained beside it
would be wrong the first time somebody nudged a hex. What *is* declared here is
the list of pairs — which token is painted on which, and what the criterion
asks of that combination — because that is a fact about the design, not about
the file.

    uv run python scripts/contrast.py

Writes docs/verification/contrast.json and exits non-zero if any pair fails, so
it can be run as a check as well as a generator.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLES = ROOT / "frontend" / "src" / "styles" / "site.scss"
OUT = ROOT / "docs" / "verification" / "contrast.json"

#: (foreground token, background token, what it is, required ratio).
#:
#: `AA` on text is 4.5:1; large text and non-text UI parts are 3:1. Where a pair
#: is painted in both roles the stricter number is used.
PAIRS: list[tuple[str, str, str, float]] = [
    ("--ink", "--page", "body text on the page", 4.5),
    ("--ink", "--panel", "body text on a panel or summary box", 4.5),
    ("--ink", "--field", "text typed into a form control", 4.5),
    ("--muted", "--page", "secondary text: notes, source credit, captions", 4.5),
    ("--muted", "--panel", "secondary text inside a panel", 4.5),
    ("--link", "--page", "a link in running text", 4.5),
    ("--link", "--panel", "a link inside a panel", 4.5),
    ("--link", "--field", "a link on a form control", 4.5),
    ("--danger", "--page", "error text", 4.5),
    ("--danger-ink", "--danger", "the repealed / omitted badge's own text", 4.5),
    # The selected sort option and the applied facet are filled pills. Their
    # text is `--danger-ink` for the reason that token exists — text on a filled
    # colour cannot inherit `--ink`, which inverts with the theme while the fill
    # under it does not. Same shape as the badge above, a different fill.
    ("--danger-ink", "--link", "text inside a selected sort or facet pill", 4.5),
    ("--edge", "--field", "the boundary of an input, select or textarea", 3.0),
    ("--edge", "--page", "a control's boundary against the page", 3.0),
    ("--edge", "--panel", "a control's boundary inside a panel", 3.0),
    ("--target-edge", "--page", "the focus ring, and the edge of a highlighted provision", 3.0),
    ("--target-edge", "--panel", "the focus ring over a panel", 3.0),
]

#: Pairs measured and reported, but held to no ratio, with the reason.
#:
#: SC 1.4.11 asks 3:1 of "visual information required to identify user interface
#: components and states" — a control's boundary. A divider between two
#: paragraphs identifies nothing: remove it entirely and the page still says
#: everything it said. Holding it to 3:1 anyway would put every hairline on the
#: site at #949494 or darker, which is a visibly heavier reader bought for no
#: conformance gain. `--edge` above is the half of the old `--rule` that does
#: carry meaning, and it is held to the ratio.
DECORATIVE: list[tuple[str, str, str]] = [
    ("--rule", "--page", "dividers, the edge of a note, table cell borders"),
    ("--rule", "--panel", "a divider drawn on a panel"),
]

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def read_tokens() -> dict[str, dict[str, str]]:
    """The light and dark token blocks, as `{theme: {name: value}}`.

    Light is `:root { … }`; dark is `:root[data-theme="dark"] { … }`. Dark
    inherits every token it does not restate, which is why it is layered onto a
    copy of light rather than read on its own.
    """
    text = STYLES.read_text(encoding="utf-8")

    def block(selector: str) -> dict[str, str]:
        start = text.index(selector)
        # The token block runs to the first line that closes it at column 0.
        end = text.index("\n}", start)
        found = {}
        for name, value in re.findall(r"(--[\w-]+):\s*([^;]+);", text[start:end]):
            found[name] = value.strip()
        return found

    light = block(":root {")
    dark = dict(light)
    dark.update(block(':root[data-theme="dark"] {'))
    return {"light": light, "dark": dark}


def to_rgb(value: str) -> tuple[float, float, float]:
    value = value.strip()
    if HEX.match(value):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    raise ValueError(f"not an opaque colour: {value!r}")


def luminance(rgb: tuple[float, float, float]) -> float:
    def channel(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg: str, bg: str) -> float:
    a, b = luminance(to_rgb(fg)), luminance(to_rgb(bg))
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> None:
    tokens = read_tokens()
    results = []
    failures = []

    def record(fg_name: str, bg_name: str, usage: str, need: float | None) -> None:
        entry: dict = {
            "usage": usage,
            "foreground": fg_name,
            "background": bg_name,
            "requires": need,
        }
        if need is None:
            entry["decorative"] = True
        for theme in ("light", "dark"):
            fg = fg_name if fg_name.startswith("#") else tokens[theme][fg_name]
            bg = bg_name if bg_name.startswith("#") else tokens[theme][bg_name]
            try:
                value = round(ratio(fg, bg), 2)
            except ValueError as error:
                entry[theme] = {"skipped": str(error)}
                continue
            passes = None if need is None else value >= need
            entry[theme] = {"fg": fg, "bg": bg, "ratio": value, "passes": passes}
            if passes is False:
                failures.append(f"{usage} [{theme}]: {fg} on {bg} is {value}:1, needs {need}:1")
        results.append(entry)

    for fg, bg, usage, need in PAIRS:
        record(fg, bg, usage, need)
    for fg, bg, usage in DECORATIVE:
        record(fg, bg, usage, None)

    report = {
        "_comment": (
            "Generated by scripts/contrast.py. Do not hand-edit — re-run it. Token values are "
            "read from frontend/src/styles/site.scss; the list of pairs is declared in the "
            "script, because which colour is painted on which is a fact about the design. "
            "WCAG 2.1 AA: 4.5:1 for text, 3:1 for large text and non-text UI parts (1.4.3, "
            "1.4.11). Pairs whose value is not an opaque colour are reported as skipped rather "
            "than guessed at."
        ),
        "source": str(STYLES.relative_to(ROOT)),
        "tokens": tokens,
        "pairs": results,
        "summary": {
            "pairs": len(results),
            "checks": len(results) * 2,
            "failures": len(failures),
        },
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n")

    print(f"{len(results)} pairs x 2 themes -> {OUT.relative_to(ROOT)}")
    for entry in results:
        for theme in ("light", "dark"):
            data = entry[theme]
            if "skipped" in data:
                print(f"  SKIP {theme:5} {entry['usage']}: {data['skipped']}")
                continue
            mark = {True: "ok  ", False: "FAIL", None: "deco"}[data["passes"]]
            need = "n/a" if entry["requires"] is None else str(entry["requires"])
            print(
                f"  {mark} {theme:5} {data['ratio']:>6.2f}:1 "
                f"(needs {need}) {entry['usage']}"
            )

    if failures:
        print(f"\n{len(failures)} failing:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
