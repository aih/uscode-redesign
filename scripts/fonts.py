"""Build the reader's self-hosted webfonts from upstream sources.

The reader serves its own type (ADR-0052). Nothing on a page fetches a font
from another host: not a CDN, not Google Fonts, not a stylesheet that in turn
fetches one. That keeps `font-src` in the CSP (ADR-0030) at `'self'` and puts
the first paint of statutory text on this site's own round trip.

    uv run --with "fonttools[woff]" python scripts/fonts.py

Downloads the upstream TTFs at the commits pinned below, subsets each to the
Latin range the reader uses, converts to WOFF2, and writes them to
`frontend/public/fonts/` alongside each family's OFL licence. It also writes
`docs/verification/fonts.json`: the source URL and sha256 of every input, the
byte size and sha256 of every output, the axes each output kept, and the cap
height read out of the font — which is the number `site.scss` hands USWDS, so
that a face swap does not silently change how large everything renders.

`fonttools` is not a project dependency. This runs once per font change and its
outputs are committed; the reader neither imports it nor needs it installed.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "frontend" / "public" / "fonts"
MANIFEST = ROOT / "docs" / "verification" / "fonts.json"

#: Pinned upstream commits in google/fonts. `main` moves daily; a ref that moves
#: makes this script unrepeatable, and the whole point of it is that someone
#: else can run it and get the bytes that are committed here.
PINS = {
    "archivo": "95f4904fc8bcf26d3420fe315560c96417c6dec7",
    "spectral": "8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5",
}

RAW = "https://raw.githubusercontent.com/google/fonts/{commit}/ofl/{family}/{name}"

#: The Latin subset, as Google Fonts defines it, plus nothing.
#:
#: Two characters in here matter more than the rest and are worth naming. U+00A7
#: is the section sign, which is on every citation the site prints. U+2013 is the
#: EN DASH OLRC writes section numbers with — 5,697 of the corpus's 65,938
#: sections contain one (CLAUDE.md gotcha 17) — so a subset that dropped
#: U+2000-206F would render a tofu box in the middle of `§ 45a–1`.
UNICODES = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
    "U+0304,U+0308,U+0329,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,"
    "U+2212,U+2215,U+FEFF,U+FFFD"
)


@dataclass
class Face:
    """One output file, and what it took to make it."""

    family: str
    source: str
    out: str
    style: str
    weight: str
    #: Axis values to pin before subsetting, dropping those axes from the output.
    pin: dict[str, float] = field(default_factory=dict)


#: What the reader actually renders.
#:
#: Spectral is statute text — the source marks emphasis (`<i>`) and bold (`<b>`)
#: inside provisions, so roman, italic, bold and bold-italic are all reachable
#: from the text of the Code. Archivo is the interface, and ships as one variable
#: file per style covering every weight the stylesheet asks for.
#:
#: Spectral has no variable version upstream: `ofl/spectral/METADATA.pb` declares
#: fourteen static instances and no `axes` block, so the four weights below are
#: four files rather than one.
FACES = [
    Face("archivo", "Archivo[wdth,wght].ttf", "archivo-latin-var.woff2", "normal", "100 900", {"wdth": 100}),
    Face("archivo", "Archivo-Italic[wdth,wght].ttf", "archivo-latin-var-italic.woff2", "italic", "100 900", {"wdth": 100}),
    Face("spectral", "Spectral-Regular.ttf", "spectral-latin-400.woff2", "normal", "400"),
    Face("spectral", "Spectral-Italic.ttf", "spectral-latin-400-italic.woff2", "italic", "400"),
    Face("spectral", "Spectral-Bold.ttf", "spectral-latin-700.woff2", "normal", "700"),
    Face("spectral", "Spectral-BoldItalic.ttf", "spectral-latin-700-italic.woff2", "italic", "700"),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "uscode-redesign font build (scripts/fonts.py)"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def measure(path: Path) -> dict:
    """Cap height, units per em, glyph count and remaining axes.

    USWDS's `$theme-typeface-tokens` carries a cap height per face and normalises
    its whole type scale against it (`normalize-type-scale()`), so that swapping
    a face keeps text the same apparent size rather than the same em size. A face
    declared with the wrong number renders every size on the site slightly wrong.

    The unit is the cap height in px at a 500px font size, which is not
    documented anywhere and is recovered from the fonts USWDS ships: Public Sans
    is 1446/2000 em = 361.5, declared 362; Merriweather is 743/1000 = 371.5,
    declared 371. (Its `source-sans-pro` and `roboto-mono` values do not match
    their own files — 328 declared 340, 355.5 declared 380 — so the convention is
    read off the two that agree.)
    """
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    upem = font["head"].unitsPerEm
    os2 = font["OS/2"]
    cap = getattr(os2, "sCapHeight", None)
    if cap is None:
        raise SystemExit(f"{path.name}: no OS/2.sCapHeight to read a cap height from")
    axes = []
    if "fvar" in font:
        axes = [
            {"tag": a.axisTag, "min": a.minValue, "default": a.defaultValue, "max": a.maxValue}
            for a in font["fvar"].axes
        ]
    return {
        "unitsPerEm": upem,
        "capHeightUnits": cap,
        "capHeight": round(cap * 500 / upem),
        "glyphs": len(font.getGlyphOrder()),
        "axes": axes,
    }


def build(face: Face, work: Path) -> dict:
    url = RAW.format(commit=PINS[face.family], family=face.family, name=face.source)
    print(f"  {face.source} -> {face.out}")
    raw = fetch(url)
    source_path = work / face.source
    source_path.write_bytes(raw)

    subset_input = source_path
    if face.pin:
        pinned = work / f"pinned-{face.source}"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "fontTools.varLib.instancer",
                str(source_path),
                *[f"{tag}={value}" for tag, value in face.pin.items()],
                # Without this the instancer stamps `head.modified` with the
                # wall clock, so every run produces different bytes and the
                # sha256 in the manifest below means nothing.
                "--no-recalc-timestamp",
                "-o",
                str(pinned),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subset_input = pinned

    out_path = OUT_DIR / face.out
    subprocess.run(
        [
            sys.executable,
            "-m",
            "fontTools.subset",
            str(subset_input),
            f"--unicodes={UNICODES}",
            "--flavor=woff2",
            "--layout-features+=ss01",
            "--no-hinting",
            "--desubroutinize",
            f"--output-file={out_path}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )

    measured = measure(out_path)
    return {
        "family": face.family,
        "file": face.out,
        "style": face.style,
        "weight": face.weight,
        "source": {"url": url, "bytes": len(raw), "sha256": sha256(raw)},
        "pinnedAxes": face.pin,
        "bytes": out_path.stat().st_size,
        "sha256": sha256(out_path.read_bytes()),
        **measured,
    }


def main() -> None:
    try:
        import fontTools  # noqa: F401
    except ModuleNotFoundError:
        raise SystemExit(
            'fontTools is not installed. Run this as:\n'
            '  uv run --with "fonttools[woff]" python scripts/fonts.py'
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    faces = []
    licences = {}

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        print("building webfonts")
        for face in FACES:
            faces.append(build(face, work))

        for family, commit in PINS.items():
            url = RAW.format(commit=commit, family=family, name="OFL.txt")
            text = fetch(url)
            (OUT_DIR / f"OFL-{family}.txt").write_bytes(text)
            licences[family] = {"url": url, "file": f"OFL-{family}.txt", "sha256": sha256(text)}

    total = sum(f["bytes"] for f in faces)
    critical = sum(f["bytes"] for f in faces if f["weight"] in ("400", "100 900") and f["style"] == "normal")

    report = {
        "_comment": (
            "Generated by scripts/fonts.py. Do not hand-edit — re-run it. Every file listed "
            "here is committed under frontend/public/fonts and served from this site's own "
            "origin (ADR-0052); nothing on a reader page fetches a font from another host. "
            "capHeight is normalised to a 1000-unit em and is the number site.scss declares "
            "in $theme-typeface-tokens, which USWDS uses to normalise its type scale."
        ),
        "pinnedCommits": PINS,
        "unicodes": UNICODES,
        "licences": licences,
        "faces": faces,
        "summary": {
            "files": len(faces),
            "bytes": total,
            "preloadedBytes": critical,
        },
    }
    MANIFEST.write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n{len(faces)} files, {total:,} bytes total, {critical:,} preloaded")
    for f in faces:
        print(f"  {f['bytes']:>7,}  {f['file']}  cap-height {f['capHeight']}")
    print(f"-> {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
