"""Score the search ranking against a judgement set — ADR-0049.

"Ordered by relevance" is a claim, and this is what makes it checkable. The
judgement set is `docs/verification/search-judgements.json`: real queries with
the sections a drafter would expect, each graded. This script runs every scoring
profile in `storage/searchquery.py` over that set, computes nDCG@10, and writes
`docs/verification/search-relevance.json`.

The profiles come from the module the API ships, not from a copy here. A harness
with its own query builder measures the harness.

Two subcommands:

    uv run python scripts/search_eval.py pool     # candidates to grade
    uv run python scripts/search_eval.py score    # the artifact

`pool` exists because of the bias nDCG has against whichever configuration you
did not use to gather candidates: an unjudged document scores zero, so a profile
that surfaces something genuinely relevant but ungraded is punished for it.
Pooling asks *every* profile for its top hits and prints the union, so the
grading covers what any of them can find before any of them is scored.

Needs a cluster (`SEARCH_URL`, `SEARCH_PASSWORD`) with the corpus indexed —
`python -m ingest.reindex_search --recreate --all-versions`. It reads nothing
else, and writes only the artifact.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.search import SECTIONS_INDEX, STRUCTURE_INDEX, get_search_client  # noqa: E402
from storage.searchquery import CANDIDATES, build_search_body, parse_query  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
JUDGEMENTS = REPO_ROOT / "docs/verification/search-judgements.json"
ARTIFACT = REPO_ROOT / "docs/verification/search-relevance.json"

CUTOFF = 10
"""nDCG@10. A results page is 20, but the first ten are what a reader reads
before deciding the search failed."""

POOL_DEPTH = 12
"""How deep into each profile's results to pool for grading. Deeper is a better
judgement set and more to grade; twelve covers the ten that are scored plus a
margin for profiles that agree on the top and diverge below it."""


def _search(client, query: str, profile, size: int) -> list[dict[str, Any]]:
    body = build_search_body(parse_query(query), profile=profile, limit=size)
    res = client.search(index=f"{SECTIONS_INDEX},{STRUCTURE_INDEX}", body=body)
    out = []
    for hit in res["hits"]["hits"]:
        source = hit["_source"]
        out.append({
            "identifier": source.get("identifier"),
            "num": source.get("num") or source.get("num_value"),
            "heading": source.get("heading"),
            "status": source.get("status"),
            "is_current": source.get("is_current", True),
            "score": round(hit["_score"], 4) if hit.get("_score") is not None else None,
        })
    return out


def load_judgements() -> dict[str, Any]:
    if not JUDGEMENTS.is_file():
        sys.exit(f"no judgement set at {JUDGEMENTS} — run `pool` first and grade it")
    return json.loads(JUDGEMENTS.read_text(encoding="utf-8"))


def dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at(ranked: list[str], grades: dict[str, int], cutoff: int) -> float:
    """Normalised discounted cumulative gain, binary-exponential gain.

    Gain is `2**grade - 1`, so a 3 is worth 7 and a 1 is worth 1: the difference
    between "the provision they were looking for" and "related, worth a look" is
    deliberately not linear. An identifier nobody graded contributes nothing,
    which is the bias `pool` exists to keep small.
    """
    gains = [2 ** grades.get(identifier, 0) - 1 for identifier in ranked[:cutoff]]
    ideal = sorted((2 ** g - 1 for g in grades.values()), reverse=True)[:cutoff]
    best = dcg([float(g) for g in ideal])
    return round(dcg([float(g) for g in gains]) / best, 4) if best else 0.0


def recall_at(ranked: list[str], grades: dict[str, int], cutoff: int) -> float:
    """How much of what was graded relevant the profile actually put on page one.

    nDCG rewards putting the best result first; this says whether the rest were
    found at all. A profile can win on nDCG while losing provisions.
    """
    relevant = {i for i, g in grades.items() if g > 0}
    if not relevant:
        return 0.0
    return round(len(relevant & set(ranked[:cutoff])) / len(relevant), 4)


def cmd_pool(args) -> int:
    client = get_search_client()
    data = load_judgements()
    profiles = list(CANDIDATES.values())
    for entry in data["queries"]:
        query = entry["q"]
        if args.only and args.only not in query:
            continue
        seen: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            for hit in _search(client, query, profile, POOL_DEPTH):
                seen.setdefault(hit["identifier"], hit)
        graded = entry.get("judgements", {})
        print(f"\n### {query}")
        if entry.get("note"):
            print(f"# {entry['note']}")
        for identifier, hit in seen.items():
            mark = graded.get(identifier, "?")
            current = "" if hit["is_current"] else " [superseded]"
            status = f" [{hit['status']}]" if hit.get("status") else ""
            print(f"{mark}\t{identifier}\t{hit['num'] or ''} {hit['heading'] or ''}"
                  f"{status}{current}")
    return 0


def cmd_score(args) -> int:
    client = get_search_client()
    data = load_judgements()
    queries = data["queries"]

    profiles: list[dict[str, Any]] = []
    for name, profile in CANDIDATES.items():
        per_query = []
        for entry in queries:
            grades = {k: v for k, v in entry.get("judgements", {}).items() if v}
            ranked = [
                hit["identifier"]
                for hit in _search(client, entry["q"], profile, CUTOFF)
            ]
            per_query.append({
                "q": entry["q"],
                "ndcg@10": ndcg_at(ranked, grades, CUTOFF),
                "recall@10": recall_at(ranked, grades, CUTOFF),
                "top": ranked[:3],
            })
        mean = round(sum(r["ndcg@10"] for r in per_query) / len(per_query), 4)
        mean_recall = round(sum(r["recall@10"] for r in per_query) / len(per_query), 4)
        profiles.append({
            "profile": name,
            "fields": list(profile.fields),
            "phrase_boost": profile.phrase_boost,
            "heading_phrase_boost": profile.heading_phrase_boost,
            "scope": profile.scope,
            "current_boost": profile.current_boost,
            "mean_ndcg@10": mean,
            "mean_recall@10": mean_recall,
            "queries": per_query,
        })
        print(f"{name:14s} nDCG@10 {mean:.4f}   recall@10 {mean_recall:.4f}")

    counts = client.count(index=SECTIONS_INDEX)["count"]
    current = client.count(
        index=SECTIONS_INDEX, body={"query": {"term": {"is_current": True}}}
    )["count"]

    artifact = {
        "generated_by": "uv run python scripts/search_eval.py score",
        "judgements": {
            "file": "docs/verification/search-judgements.json",
            "queries": len(queries),
            "graded_documents": sum(len(e.get("judgements", {})) for e in queries),
            "relevant_documents": sum(
                sum(1 for g in e.get("judgements", {}).values() if g > 0) for e in queries
            ),
        },
        "index": {
            "documents": counts,
            "current": current,
            "superseded": counts - current,
        },
        "metric": {
            "name": "nDCG@10",
            "gain": "2**grade - 1",
            "unjudged": "counted as 0",
        },
        "profiles": profiles,
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {ARTIFACT.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pool = sub.add_parser("pool", help="print candidates to grade, from every profile")
    pool.add_argument("--only", help="only queries containing this substring")
    pool.set_defaults(func=cmd_pool)
    score = sub.add_parser("score", help="score every profile and write the artifact")
    score.set_defaults(func=cmd_score)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
