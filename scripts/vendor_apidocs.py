"""Fetch (or verify) the Swagger UI and ReDoc bundles this site serves itself.

The site's CSP names no CDN — that is not a restriction anyone negotiated, it is
a description of a reader that loads no third-party anything (ADR-0030). FastAPI's
`/docs` and `/redoc` load their JavaScript from `cdn.jsdelivr.net`, so both pages
arrived at the browser and rendered *nothing*: HTTP 200, empty body, every asset
blocked. ADR-0032 is the decision to vendor them instead of poking a hole in the
policy for two pages.

Vendoring means committing ~2.4 MB of minified third-party JavaScript, and the
thing that makes that defensible is being able to say exactly what it is. Hence a
manifest with a URL and a sha256 per file, and a `--check` mode that recomputes
them:

    uv run python scripts/vendor_apidocs.py --check   # do the bytes match?
    uv run python scripts/vendor_apidocs.py           # re-download them
    uv run python scripts/vendor_apidocs.py --update  # accept new hashes

`--check` is what `tests/test_apidocs.py` runs, so a file edited in place — or a
half-finished download committed — fails the suite rather than being discovered
by a reader with a blank page.

Upgrading is deliberate: bump the versions in `static/apidocs/MANIFEST.json`,
run with `--update`, and commit the new hashes alongside the new bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "static" / "apidocs"
MANIFEST = VENDOR / "MANIFEST.json"

USER_AGENT = "uscode-redesign vendor_apidocs (+https://github.com/aih/uscode-redesign)"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def check(manifest: dict) -> int:
    problems = []
    for asset in manifest["assets"]:
        path = VENDOR / asset["file"]
        if not path.is_file():
            problems.append(f"{asset['file']}: missing")
            continue
        actual = sha256(path)
        if actual != asset["sha256"]:
            problems.append(
                f"{asset['file']}: sha256 {actual} != manifest {asset['sha256']}"
            )
    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    if problems:
        print(
            "\nRe-fetch with: uv run python scripts/vendor_apidocs.py",
            file=sys.stderr,
        )
        return 1
    print(f"ok — {len(manifest['assets'])} vendored assets match the manifest")
    return 0


def download(manifest: dict, *, update: bool) -> int:
    VENDOR.mkdir(parents=True, exist_ok=True)
    changed = False
    for asset in manifest["assets"]:
        request = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            body = response.read()
        digest = hashlib.sha256(body).hexdigest()
        if digest != asset["sha256"]:
            if not update:
                print(
                    f"FAIL {asset['file']}: downloaded sha256 {digest} does not match "
                    f"the manifest's {asset['sha256']}. The published file changed under "
                    f"a pinned version, which is worth looking at before accepting — "
                    f"re-run with --update once you have.",
                    file=sys.stderr,
                )
                return 1
            asset["sha256"] = digest
            changed = True
        (VENDOR / asset["file"]).write_bytes(body)
        print(f"{asset['file']}: {len(body):,} bytes, sha256 {digest[:12]}…")
    if changed:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print("manifest updated")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed files against the manifest, downloading nothing",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="accept and record new hashes (use after bumping a version)",
    )
    args = parser.parse_args()

    manifest = load()
    if args.check:
        return check(manifest)
    return download(manifest, update=args.update)


if __name__ == "__main__":
    raise SystemExit(main())
