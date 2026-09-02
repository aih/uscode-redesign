"""Build the reader's app icons from the committed favicon.

The reader is installable (ADR-0079), and an install needs raster icons: the
manifest's 192/512 `any` and `maskable` entries and the `apple-touch-icon`.
All five are rendered from `static/favicon.svg` — the one mark the site has —
into `frontend/public/icons/`, so they serve from `/app/icons/` inside the
app's scope.

    uv run --with cairosvg python scripts/icons.py

(macOS with Homebrew needs the C library on the loader path:
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run --with cairosvg python
scripts/icons.py`.)

Like `scripts/fonts.py`, cairosvg is deliberately not a project dependency:
this runs once per mark change, its outputs are committed, and the reader
neither imports it nor needs it installed. It writes
`docs/verification/icons.json` — source sha256, and per output the pixel size,
bytes and sha256 — so the committed binaries are pinned to the committed SVG.

Two things the renderer forces:

* **cairosvg ignores `textLength`/`lengthAdjust`.** The favicon pins the word
  to 56 of its 64 units that way; rendered naively the glyphs run wide and
  clip. So the script measures the text's rendered width on a wide probe
  canvas and applies the same horizontal squeeze `spacingAndGlyphs` would,
  as a `scale()` transform.
* **The glyphs come from whatever font the machine resolves** for the
  favicon's own stack, exactly as they do in a browser tab. The manifest
  records the bytes this run produced; a rebuild on another machine can
  differ in glyph outline while keeping the same geometry.

The five outputs:

* `icon-192.png` / `icon-512.png` — the favicon as drawn (`purpose: any`;
  the corners outside the 6/64 radius stay transparent).
* `icon-maskable-192.png` / `icon-maskable-512.png` — full-bleed background,
  mark scaled so its ink fits the safe-zone circle (`SAFE` of the diameter,
  centred). Separate files: a single `"any maskable"` icon gets cropped in
  its `any` uses.
* `apple-touch-icon-180.png` — opaque full-bleed background (iOS composites
  no alpha).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "static" / "favicon.svg"
OUT_DIR = ROOT / "frontend" / "public" / "icons"
MANIFEST = ROOT / "docs" / "verification" / "icons.json"

#: The width the favicon's own `textLength` pins the word to, in its 64-unit
#: viewBox — read out of the file below, never assumed.
VIEWBOX = 64

#: The maskable safe zone: platform masks are guaranteed to keep a **circle**
#: of 80% of the icon's diameter, centred (w3.org/TR/appmanifest, "icon
#: masks") — not the inner 80% square, whose corners a circular mask shaves.
#: The mark is scaled so its measured ink fits inside that circle; the
#: background bleeds to the edge.
SAFE = 0.8


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_mark() -> dict:
    """The favicon's parts, out of the file rather than retyped.

    String surgery instead of an XML walk because what is wanted is exactly
    five facts, and each is asserted present — a favicon redrawn into a shape
    this does not recognise fails the run rather than shipping a wrong icon.
    """
    svg = SOURCE.read_text()

    def take(pattern: str, what: str) -> str:
        match = re.search(pattern, svg)
        if not match:
            raise SystemExit(f"static/favicon.svg: cannot find {what} ({pattern})")
        return match.group(1)

    return {
        # The light-scheme colours. An app icon is not themed: the OS shows one
        # bitmap in both appearances, and the favicon's dark-scheme rule exists
        # for tab strips, not launchers.
        "bg": take(r"\.bg\s*\{\s*fill:\s*(#[0-9a-fA-F]{3,8})", "the .bg fill"),
        "fg": take(r"\.fg\s*\{\s*fill:\s*(#[0-9a-fA-F]{3,8})", "the .fg fill"),
        "rx": take(r'<rect class="bg"[^/]*\brx="([\d.]+)"', "the corner radius"),
        "word": take(r">([A-Z]+)</text>", "the lettering"),
        "text_length": float(take(r'textLength="([\d.]+)"', "textLength")),
        "font_size": take(r'font-size="([\d.]+)"', "font-size"),
        "font_weight": take(r'font-weight="([\d.]+)"', "font-weight"),
        "font_family": take(r'font-family="([^"]+)"', "font-family"),
        "baseline": take(r'\by="([\d.]+)"', "the baseline"),
        "center": take(r'\bx="([\d.]+)"', "the anchor"),
    }


def text_element(mark: dict) -> str:
    """The lettering, anchored at the origin so a transform can place it."""
    return (
        f'<text fill="{mark["fg"]}" x="0" y="0" text-anchor="middle" '
        f'font-family="{mark["font_family"]}" font-size="{mark["font_size"]}" '
        f'font-weight="{mark["font_weight"]}">{mark["word"]}</text>'
    )


def measure_ink(mark: dict, svg2png) -> dict:
    """The word's rendered geometry, measured rather than assumed.

    cairosvg drops `textLength`, so the word renders at the natural width of
    whatever font answered the stack — wider than the tile. A browser squeezes
    it to `textLength` units; this measures the natural width (alpha bounding
    box on a probe canvas wide enough not to clip) and returns the same
    horizontal scale, plus the ink's vertical extent in tile units — the
    baseline sits at the favicon's own `y`, so the vertical numbers transfer
    to the icon unchanged. The maskable fit below needs both axes.
    """
    from PIL import Image  # cairosvg's own dependency

    probe_units = VIEWBOX * 4
    probe_px = 4096
    probe = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {probe_units} {VIEWBOX}">'
        f'<g transform="translate({probe_units / 2} {mark["baseline"]})">'
        f"{text_element(mark)}</g></svg>"
    )
    png = svg2png(
        bytestring=probe.encode(),
        output_width=probe_px,
        output_height=probe_px * VIEWBOX // probe_units,
    )
    bbox = Image.open(io.BytesIO(png)).getbbox()
    if bbox is None:
        raise SystemExit("the probe render produced no ink to measure")
    per_unit = probe_px / probe_units
    natural = (bbox[2] - bbox[0]) / per_unit
    if natural >= probe_units:
        raise SystemExit("the probe canvas clipped the text; widen it")
    return {
        "squeeze": mark["text_length"] / natural,
        "natural": natural,
        "ink_top": bbox[1] / per_unit,
        "ink_bottom": bbox[3] / per_unit,
    }


def maskable_scale(mark: dict, ink: dict) -> float:
    """How far to shrink the mark so its ink fits the safe-zone circle.

    The guaranteed-visible region of a maskable icon is a centred circle of
    `SAFE` of the icon's diameter. The word's ink, squeezed to `textLength`
    wide and measured `ink_top`..`ink_bottom` tall, has its farthest corner at
    a radius the inner-`SAFE` *square* does not bound — at this aspect ratio
    the corners of an 80%-square fit sit ~3.5% outside the circle, which a
    strictly circular Android mask shaves off the letters.
    """
    center = VIEWBOX / 2
    half_w = ink["squeeze"] * ink["natural"] / 2
    half_h = (ink["ink_bottom"] - ink["ink_top"]) / 2
    off_center = abs((ink["ink_top"] + ink["ink_bottom"]) / 2 - center)
    corner = ((half_w**2) + ((off_center + half_h) ** 2)) ** 0.5
    radius = SAFE * VIEWBOX / 2
    return min(radius / corner, SAFE)


def compose(mark: dict, squeeze: float, *, full_bleed: bool, inset: float = 0.0) -> str:
    """One icon as SVG: the card (or a full-bleed field) and the fitted word.

    `inset` scales the mark into the centre — `(1 - maskable_scale()) / 2`
    each side for the maskable safe zone. With `full_bleed` the background
    reaches every edge; the card's rounded corners then vanish against a
    field of the same colour, which is the point.
    """
    card = f'<rect fill="{mark["bg"]}" width="{VIEWBOX}" height="{VIEWBOX}" rx="{mark["rx"]}"/>'
    word = (
        f'<g transform="translate({mark["center"]} {mark["baseline"]}) scale({squeeze:.5f} 1)">'
        f"{text_element(mark)}</g>"
    )
    content = card + word
    if inset:
        offset = VIEWBOX * inset
        content = f'<g transform="translate({offset} {offset}) scale({1 - 2 * inset})">{content}</g>'
    field = (
        f'<rect fill="{mark["bg"]}" width="{VIEWBOX}" height="{VIEWBOX}"/>' if full_bleed else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}">'
        f"{field}{content}</svg>"
    )


def main() -> None:
    try:
        from cairosvg import svg2png
    except (ModuleNotFoundError, OSError) as error:
        raise SystemExit(
            "cairosvg is not importable. Run this as:\n"
            "  uv run --with cairosvg python scripts/icons.py\n"
            "On macOS with Homebrew, put the C library on the loader path:\n"
            "  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run --with cairosvg "
            "python scripts/icons.py\n"
            f"({error})"
        )

    mark = read_mark()
    ink = measure_ink(mark, svg2png)
    squeeze, natural = ink["squeeze"], ink["natural"]
    fit = maskable_scale(mark, ink)
    print(
        f"mark: {mark['word']} natural width {natural:.2f} units, "
        f"squeezed x{squeeze:.5f} to textLength {mark['text_length']:g}; "
        f"maskable fit x{fit:.5f} inside the {SAFE:g}-diameter circle"
    )

    plain = compose(mark, squeeze, full_bleed=False)
    maskable = compose(mark, squeeze, full_bleed=True, inset=(1 - fit) / 2)
    apple = compose(mark, squeeze, full_bleed=True)

    outputs = [
        ("icon-192.png", plain, 192, "any"),
        ("icon-512.png", plain, 512, "any"),
        ("icon-maskable-192.png", maskable, 192, "maskable"),
        ("icon-maskable-512.png", maskable, 512, "maskable"),
        ("apple-touch-icon-180.png", apple, 180, "apple-touch"),
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for name, svg, px, purpose in outputs:
        path = OUT_DIR / name
        svg2png(bytestring=svg.encode(), write_to=str(path), output_width=px, output_height=px)
        data = path.read_bytes()
        files.append(
            {"file": name, "purpose": purpose, "px": px, "bytes": len(data), "sha256": sha256(data)}
        )
        print(f"  {len(data):>7,}  {name}")

    report = {
        "_comment": (
            "Generated by scripts/icons.py. Do not hand-edit — re-run it. Every file listed "
            "here is committed under frontend/public/icons and declared by "
            "frontend/public/manifest.webmanifest or Base.astro's apple-touch-icon link "
            "(ADR-0079). The glyphs come from the font the rendering machine resolves for the "
            "favicon's stack, so a rebuild elsewhere can differ in outline at the same geometry."
        ),
        "source": {
            "file": "static/favicon.svg",
            "sha256": sha256(SOURCE.read_bytes()),
        },
        "mark": {
            "word": mark["word"],
            "background": mark["bg"],
            "lettering": mark["fg"],
            "naturalWidthUnits": round(natural, 3),
            "squeeze": round(squeeze, 5),
            "maskableSafeZone": SAFE,
            "maskableScale": round(fit, 5),
        },
        "files": files,
    }
    MANIFEST.write_text(json.dumps(report, indent=2) + "\n")
    print(f"-> {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
