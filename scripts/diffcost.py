"""What the API's redline costs, with and without the guid churn (task B5).

`@id` guids regenerate at every release point by design (ADR-0003, gotcha 1),
so they are the one part of a section's XML guaranteed to differ between any two
release points whether or not a word of law changed. Diffing them is work spent
on the only content that cannot mean anything — and, because diff-match-patch
short-circuits on a common prefix and suffix, it is not a constant overhead: it
is the difference between two nearly-identical strings and two strings that
differ every few hundred bytes.

This measures that, per section, in process:

    make dev-all                  # or any running API
    uv run python scripts/diffcost.py

Writes docs/verification/diffcost.json. It fetches the two fragments over HTTP
— those routes are unlimited — and times the diff locally, so the rate limiter
on `/diff` (ADR-0029, five in a burst) is not in the way of measuring the thing
underneath it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.diff import diff_ops, strip_guids  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "verification" / "diffcost.json"

#: Sections spanning three orders of magnitude of fragment size, all in the CI
#: fixture title. The pair for each is chosen from its own version timeline, so
#: every row is a comparison across a real amendment rather than across two
#: release points that happen to hold the same text.
SECTIONS = [
    "/us/usc/t16/s45f",
    "/us/usc/t16/s1801",
    "/us/usc/t16/s1536",
    "/us/usc/t16/s668dd",
]

#: How many times to time each diff. Diff-match-patch is deterministic, so this
#: is about the machine rather than about the algorithm.
RUNS = 3


def get(base: str, path: str) -> Any:
    with urllib.request.urlopen(f"{base}{path}") as response:
        return json.load(response)


def pair(base: str, identifier: str) -> tuple[str, str] | None:
    """The last release point before the newest text, and the newest.

    The same rule the reader's "Compare with…" uses (`lib/compare.ts`): the
    group before the current one ends at the last release point holding
    different text.
    """
    versions = get(base, f"/api/v1/sections{identifier}/versions")["versions"]
    if len(versions) < 2:
        return None
    before = versions[-2]["releases"][-1]
    after = versions[-1]["releases"][-1]
    return before, after


def timed(from_xml: str, to_xml: str) -> tuple[float, int]:
    """Best of `RUNS`, and the op count. Best rather than mean: the thing being
    measured is the algorithm, and a slower run is this machine doing something
    else."""
    best = float("inf")
    ops: list[Any] = []
    for _ in range(RUNS):
        start = time.perf_counter()
        ops = diff_ops(from_xml, to_xml)
        best = min(best, time.perf_counter() - start)
    return best * 1000, len(ops)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()

    rows = []
    for identifier in SECTIONS:
        found = pair(args.base, identifier)
        if found is None:
            print(f"{identifier}: only one version, skipping")
            continue
        from_label, to_label = found
        try:
            from_section = get(args.base, f"/api/v1{identifier}?release={from_label}")
            to_section = get(args.base, f"/api/v1{identifier}?release={to_label}")
        except urllib.error.HTTPError as error:
            print(f"{identifier}: {error}")
            continue

        keep_ms, keep_ops = timed(from_section["xml"], to_section["xml"])

        start = time.perf_counter()
        from_stripped = strip_guids(from_section["xml"])
        to_stripped = strip_guids(to_section["xml"])
        strip_ms = (time.perf_counter() - start) * 1000
        diff_ms, strip_ops = timed(from_stripped, to_stripped)

        rows.append(
            {
                "identifier": identifier,
                "from": from_label,
                "to": to_label,
                "fragmentBytes": len(to_section["xml"]),
                "keep": {"ms": round(keep_ms, 1), "ops": keep_ops},
                "strip": {
                    "ms": round(strip_ms + diff_ms, 1),
                    "strippingMs": round(strip_ms, 1),
                    "diffMs": round(diff_ms, 1),
                    "ops": strip_ops,
                },
                "speedup": round(keep_ms / (strip_ms + diff_ms), 1),
            }
        )
        row = rows[-1]
        print(
            f"{identifier:24} {row['fragmentBytes']:>7} B  "
            f"keep {row['keep']['ms']:>8.1f} ms / {row['keep']['ops']:>4} ops   "
            f"strip {row['strip']['ms']:>7.1f} ms / {row['strip']['ops']:>3} ops   "
            f"{row['speedup']}x"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "_comment": (
                    "Generated by `uv run python scripts/diffcost.py` against a running API "
                    "(ADR-0066). Do not hand-edit — re-run it. What the /api/v1/sections/…/diff "
                    "endpoint costs with @id guids in the comparison (`keep`) and with them "
                    "removed first (`strip`, the default since ADR-0066). Timed in process, "
                    "best of 3, because the endpoint is rate limited to five in a burst "
                    "(ADR-0029) and the limiter is not what is being measured. `strippingMs` is "
                    "the lxml parse and re-serialise that `strip` pays before diffing anything."
                ),
                "base": args.base,
                "runs": RUNS,
                "sections": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\n-> {OUT.relative_to(Path.cwd())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
