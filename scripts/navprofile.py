#!/usr/bin/env python3
"""Navigation profile: how long a reader waits, and which surface spent it.

`scripts/loadtest.sh` answers "how many requests per second does this route
hold". This answers the other half of task B3 — "how long does *one* reader
wait to get from A to B, and which of Caddy, Astro, FastAPI and Postgres spent
that time".

Two things make it different from the load test:

* **Journeys, not routes.** A step is timed on a connection the step before it
  opened, which is what a browser does and what timing each URL on its own does
  not. The five journeys come from the "Exits to" column of `docs/ia-map.md`;
  each carries its derivation into the artifact, so the reading is checkable.

* **Four vantage points, so the layer split is measured rather than inferred.**
  The same path is timed from the internet, from the box's own loopback through
  Caddy, and from the box against the Astro and FastAPI containers directly.
  Subtracting adjacent vantages gives each surface its own cost. The box is
  reachable by SSM only (`docs/deploy-status.md`), so this script ships itself
  there rather than asking anyone to install anything on it.

Postgres is the layer not timed here. It is timed by `scripts/spine_explain.sh`,
whose `EXPLAIN (ANALYZE, BUFFERS)` output is the other half of the same
artifact set.

Usage
-----
    uv run python scripts/navprofile.py                  # four vantages, merged
    uv run python scripts/navprofile.py --vantage edge   # one vantage, to stdout

`--vantage` is also how the copy running on the box is invoked; the merge does
that over SSM, so it never has to be typed there.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOST = os.environ.get("NAV_HOST", "uscode.linkedlegislation.org")
INSTANCE = os.environ.get("NAV_INSTANCE", "i-06b433caacd78fd96")
AWS_PROFILE = os.environ.get("NAV_AWS_PROFILE", "uscode-admin")

#: Warm iterations per step. The first is discarded, so the sample is this minus
#: one.
WARM = int(os.environ.get("NAV_WARM", "13"))

#: Cold variants per step — how many distinct URLs of the same shape are each
#: requested exactly once. "Cold" means *not requested during this run*. Whether
#: the rows are resident in Postgres' 1 GB of shared_buffers is a property of
#: the box that this script cannot assert, and the artifact says so rather than
#: claiming a cache was flushed.
COLD = int(os.environ.get("NAV_COLD", "12"))

#: One section per title, taken from the deployed corpus itself:
#:
#:   select distinct on (t.num) s.identifier, m.parent_identifier, t.num
#:     from section_release_map m
#:     join section_versions v on v.id = m.section_version_id
#:     join sections s on s.id = v.section_id
#:     join titles t on t.id = s.title_id
#:     join release_points r on r.id = m.release_id
#:    where m.parent_identifier is not null
#:      and s.identifier !~ '[^ -~]'          -- gotcha 16: keep en dashes out
#:      and m.parent_identifier ~ '^/us/usc/t[0-9]+[a-z]?/ch[0-9]'
#:      and v.status is null
#:    order by t.num, r.seq desc, m.seq_in_title;
#:
#: Spread across titles on purpose: twelve sections of Title 16 would sit in
#: whatever cache the first of them warmed.
POOL: list[tuple[str, str, str]] = [
    ("/us/usc/t1/s1", "/us/usc/t1/ch1", "1"),
    ("/us/usc/t7/s1", "/us/usc/t7/ch1", "7"),
    ("/us/usc/t8/s1101", "/us/usc/t8/ch12/schI", "8"),
    ("/us/usc/t11/s101", "/us/usc/t11/ch1", "11"),
    ("/us/usc/t15/s1", "/us/usc/t15/ch1", "15"),
    ("/us/usc/t20/s41", "/us/usc/t20/ch3/schI", "20"),
    ("/us/usc/t23/s101", "/us/usc/t23/ch1", "23"),
    ("/us/usc/t29/s1", "/us/usc/t29/ch1/schI", "29"),
    ("/us/usc/t33/s1", "/us/usc/t33/ch1/schI", "33"),
    ("/us/usc/t42/s26", "/us/usc/t42/ch1/schI", "42"),
    ("/us/usc/t47/s9", "/us/usc/t47/ch1", "47"),
    ("/us/usc/t50/s1", "/us/usc/t50/ch1", "50"),
]

#: The warm variant. Title 16 § 45f is the fixture the rest of
#: `docs/verification/` uses, so these rows are comparable with those.
WARM_VARIANT = ("/us/usc/t16/s45f", "/us/usc/t16/ch1/schVI", "16")

#: One search term per cold variant, so no two cold search steps ask OpenSearch
#: the same question.
TERMS = [
    "conservation",
    "navigable waters",
    "bankruptcy estate",
    "immigration",
    "commerce",
    "vocational",
    "highway",
    "labor standards",
    "harbor",
    "public health",
    "broadcast",
    "national security",
]

#: Every step's `path` is a template over a variant. `kind` decides which
#: vantages can serve it: an Astro container cannot answer `/api/v1`, and a
#: FastAPI container cannot answer `/app`. `budget` caps a step's requests where
#: a rate limiter would otherwise be the thing measured.
JOURNEYS: list[dict] = [
    {
        "name": "spine",
        "derivation": "ia-map: `/app/` exits to a title TOC, a TOC to its children, and the leaf is a section",
        "steps": [
            {"label": "front page", "path": "/app/", "kind": "app"},
            {"label": "title TOC", "path": "/app{t_toc}", "kind": "app"},
            {"label": "chapter TOC", "path": "/app{parent}", "kind": "app"},
            {"label": "section", "path": "/app{sec}", "kind": "app"},
        ],
    },
    {
        "name": "citation",
        "derivation": "ia-map: `/app/goto` exits to the provision, or to `/app/search`",
        "steps": [
            {
                "label": "goto, redirect followed to the provision",
                "path": "/app/goto?q={cite}",
                "kind": "app",
                "follow": True,
            }
        ],
    },
    {
        "name": "search",
        "derivation": "ia-map: `/app/search` exits to a section per result",
        "steps": [
            {"label": "results page", "path": "/app/search?q={term}", "kind": "app"},
            {"label": "first result", "path": "/app{hit}", "kind": "app"},
        ],
    },
    {
        "name": "read-along",
        "derivation": "ia-map: a section exits to prev/next/up — the SectionBar and ChapterRail path",
        "steps": [
            {"label": "section", "path": "/app{sec}", "kind": "app"},
            {"label": "next section", "path": "/app{next1}", "kind": "app"},
            {"label": "the one after", "path": "/app{next2}", "kind": "app"},
        ],
    },
    {
        "name": "compare",
        "derivation": "ia-map thin path: section → `/app/versions` → `/app/diff`, two hops",
        "steps": [
            {"label": "version history", "path": "/app/versions{sec}", "kind": "app"},
            {
                "label": "redline",
                "path": "/app/diff{sec}?from={from}&to={to}",
                "kind": "app",
                # ADR-0029 gives the reader's redline capacity 8 and 0.5/s
                # (frontend/src/middleware.ts). Four requests 2.2 s apart stay
                # inside that, so this row measures the redline rather than the
                # limiter. The limiter is measured on purpose, elsewhere, by
                # scripts/loadtest.sh.
                "budget": {"n": 4, "interval": 2.2},
            },
        ],
    },
]

#: The API calls each reader page makes, so Astro's own cost can be separated
#: from the API's. Read off the pages — `pages/us/usc/[...identifier].astro` and
#: its siblings — and `sequential` is how many of them run before the rest fan
#: out in one `Promise.all`.
FANOUT: list[dict] = [
    {"page": "front page", "sequential": 1, "calls": ["/api/v1/titles"]},
    {
        "page": "title TOC",
        "sequential": 1,
        "calls": ["/api/v1{t_toc}", "/api/v1/releases?title={t}"],
    },
    {
        "page": "chapter TOC",
        "sequential": 1,
        "calls": ["/api/v1{parent}", "/api/v1/releases?title={t}"],
    },
    {
        # One sequential call, then four in parallel — ADR-0043 put the parent
        # TOC back as the fourth. So the page's API cost is the first call plus
        # the slowest of the other four, not the sum of five.
        "page": "section",
        "sequential": 1,
        "calls": [
            "/api/v1{sec}",
            "/api/v1/labels?identifier={sec}",
            "/api/v1/sections{sec}/neighbors",
            "/api/v1/releases?title={t}",
            "/api/v1{parent}",
        ],
    },
]

#: What `params.py` and `frontend/src/middleware.ts` limit — capacity, refill
#: per second — so the artifact can say which rows sit inside their budget.
LIMITS = {
    "/api/v1/labels": [300, 30.0],
    "/api/v1/search": [120, 10.0],
    "/api/v1/citation": [120, 10.0],
    "/api/v1/sections/*/diff": [5, 0.2],
    "/app/preview/": [60, 5.0],
    "/app/diff/": [8, 0.5],
}


# ------------------------------------------------------------------- plumbing

WRITE_OUT = (
    "%{http_code} %{time_starttransfer} %{time_total} %{size_download} %{num_connects}\\n"
)


def curl(urls: list[str], extra: list[str], *, follow: bool = False) -> list[dict]:
    """One curl over several URLs, so steps after the first reuse the connection.

    `-o /dev/null` is repeated once per URL: given fewer `-o` than URLs, curl
    writes the remaining bodies to stdout, where they land in the middle of the
    `-w` lines being parsed.
    """
    if not urls:
        return []
    # `--compressed` is not a nicety, it is what makes these numbers a reader's.
    # curl sends no `Accept-Encoding` unless asked, and Caddy only compresses
    # what asks (`encode gzip zstd`) — so without it every reader page is timed
    # at its uncompressed size, which for `/app/us/usc/t16/s45f` is 76,021 bytes
    # against the 21,246 a browser actually receives. That is transfer time
    # attributed to the network that no reader ever spends. `%{size_download}`
    # then reports the wire bytes, which is the number worth recording.
    cmd = ["curl", "-sS", "--compressed", "--max-time", "60", "-w", WRITE_OUT, *extra]
    if follow:
        cmd.append("-L")
    for url in urls:
        cmd += ["-o", os.devnull, url]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 5:
            rows.append(
                {
                    "code": int(parts[0]),
                    "ttfb": float(parts[1]),
                    "total": float(parts[2]),
                    "bytes": int(parts[3]),
                    "connects": int(parts[4]),
                }
            )
    # A timeout or a connection failure prints no -w line at all; recording it
    # as code 0 keeps the sample count honest instead of silently shortening it.
    while len(rows) < len(urls):
        rows.append({"code": 0, "ttfb": 0.0, "total": 0.0, "bytes": 0, "connects": 0})
    return rows


def get_json(url: str, extra: list[str]) -> dict:
    proc = subprocess.run(
        ["curl", "-sS", "--max-time", "60", *extra, url], capture_output=True, text=True
    )
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {}


def pct(seconds: list[float], p: float) -> float:
    """Nearest-rank percentile, reported in milliseconds."""
    if not seconds:
        return 0.0
    ordered = sorted(seconds)
    rank = max(1, min(len(ordered), int(p / 100.0 * len(ordered) + 0.5)))
    return round(ordered[rank - 1] * 1000, 1)


def summarise(samples: list[dict]) -> dict:
    codes: dict[str, int] = {}
    for s in samples:
        codes[str(s["code"])] = codes.get(str(s["code"]), 0) + 1
    ok = [s for s in samples if 0 < s["code"] < 400]
    if not ok:
        return {"n": 0, "codes": codes}
    return {
        "n": len(ok),
        "ttfb_p50_ms": pct([s["ttfb"] for s in ok], 50),
        "ttfb_p95_ms": pct([s["ttfb"] for s in ok], 95),
        "total_p50_ms": pct([s["total"] for s in ok], 50),
        "total_p95_ms": pct([s["total"] for s in ok], 95),
        "bytes": int(statistics.median([s["bytes"] for s in ok])),
        # Non-zero means this step opened the connection rather than inheriting
        # one — which is the first step of every journey, and is where the TLS
        # handshake is paid. Recorded so a slow first step is not read as a slow
        # page.
        "connects": int(statistics.median([s["connects"] for s in ok])),
        "codes": codes,
    }


def vantage_config(vantage: str) -> tuple[str | None, str | None, list[str]]:
    """(origin for /app, origin for /api/v1, extra curl arguments).

    `--resolve` is what makes the `caddy` vantage the *same request* as the edge
    one — same host, same TLS, same virtual host — arriving over loopback rather
    than the internet, so the difference between those two rows is the internet
    and nothing else.
    """
    if vantage == "edge":
        return f"https://{HOST}", f"https://{HOST}", []
    if vantage == "caddy":
        return f"https://{HOST}", f"https://{HOST}", ["--resolve", f"{HOST}:443:127.0.0.1", "-k"]
    if vantage == "astro":
        return os.environ["NAV_ASTRO"], None, []
    if vantage == "api":
        return None, os.environ["NAV_API"], []
    raise SystemExit(f"unknown vantage: {vantage}")


# ----------------------------------------------------------------- setup facts
#
# Three journeys need something only the corpus can supply: which section the
# search actually returns, which section comes next in reading order, and which
# two release points the redline should compare. Resolving them here rather than
# hard-coding them is what keeps this re-runnable against a corpus that has
# moved on.


def context(variant: tuple[str, str, str], term: str, api: str, extra: list[str]) -> dict:
    sec, parent, tnum = variant
    ctx = {
        "sec": sec,
        "parent": parent,
        "t": tnum,
        "t_toc": f"/us/usc/t{tnum}",
        "term": term.replace(" ", "+"),
        "cite": f"{tnum}+U.S.C.+{sec.rsplit('/s', 1)[-1]}",
    }

    results = (get_json(f"{api}/api/v1/search?q={ctx['term']}&limit=1", extra) or {}).get(
        "results"
    ) or []
    ctx["hit"] = results[0].get("identifier", sec) if results else sec

    nxt = ((get_json(f"{api}/api/v1/sections{sec}/neighbors", extra).get("next")) or {}).get(
        "identifier"
    ) or sec
    ctx["next1"] = nxt
    ctx["next2"] = (
        (get_json(f"{api}/api/v1/sections{nxt}/neighbors", extra).get("next")) or {}
    ).get("identifier") or nxt

    versions = get_json(f"{api}/api/v1/sections{sec}/versions", extra).get("versions") or []
    labels = [v["release"]["label"] for v in versions if v.get("release")]
    ctx["from"] = labels[-2] if len(labels) > 1 else (labels[0] if labels else "119-99")
    ctx["to"] = labels[-1] if labels else "119-102not101"
    return ctx


# ------------------------------------------------------------- the measurement


def measure(vantage: str) -> dict:
    app_base, api_base, extra = vantage_config(vantage)

    # Setup always asks the API; the `astro` vantage has none to ask, so it
    # borrows the edge for the lookups alone. No timing ever leaves the vantage.
    lookup_base, lookup_extra = (api_base, extra) if api_base else (f"https://{HOST}", [])
    warm_ctx = context(WARM_VARIANT, TERMS[0], lookup_base, lookup_extra)
    cold_ctxs = [
        context(POOL[i % len(POOL)], TERMS[i % len(TERMS)], lookup_base, lookup_extra)
        for i in range(COLD)
    ]

    def url_for(step: dict, ctx: dict) -> str | None:
        base = app_base if step["kind"] == "app" else api_base
        return None if base is None else base + step["path"].format(**ctx)

    out: dict = {"vantage": vantage, "journeys": [], "fanout": []}

    for journey in JOURNEYS:
        rows = []
        for phase, ctxs in (("warm", [warm_ctx] * WARM), ("cold", cold_ctxs)):
            samples: list[list[dict]] = [[] for _ in journey["steps"]]
            for n, ctx in enumerate(ctxs):
                batch, index, follow, pause = [], [], False, 0.0
                for i, step in enumerate(journey["steps"]):
                    budget = step.get("budget")
                    if budget and n >= budget["n"]:
                        continue
                    url = url_for(step, ctx)
                    if url is None:
                        continue
                    batch.append(url)
                    index.append(i)
                    follow = follow or bool(step.get("follow"))
                    pause = max(pause, (budget or {}).get("interval", 0.0))
                if not batch:
                    continue
                # One curl per iteration: every step of the journey on one
                # connection, then transposed back out into per-step samples.
                for result, i in zip(curl(batch, extra, follow=follow), index):
                    samples[i].append(result)
                if pause:
                    time.sleep(pause)
            for i, step in enumerate(journey["steps"]):
                if not samples[i]:
                    continue
                # The first warm iteration opened the connection and warmed
                # whatever the box caches. Reporting that is the cold sample's
                # job, not the warm sample's.
                data = samples[i][1:] if phase == "warm" and len(samples[i]) > 1 else samples[i]
                rows.append({"step": step["label"], "phase": phase, **summarise(data)})
        out["journeys"].append(
            {"name": journey["name"], "derivation": journey["derivation"], "steps": rows}
        )

    if api_base:
        for page in FANOUT:
            calls = []
            for template in page["calls"]:
                url = api_base + template.format(**warm_ctx)
                samples = [curl([url], extra)[0] for _ in range(WARM)][1:]
                calls.append({"call": template, **summarise(samples)})
            # Declaration order is load-bearing: the first `sequential` entries
            # are the calls the page awaits before the rest fan out, so sorting
            # here would make the arithmetic in `attribute` add up the wrong
            # ones.
            out["fanout"].append(
                {"page": page["page"], "sequential": page["sequential"], "calls": calls}
            )

    return out


# ------------------------------------------------------------------- the merge


def run_remote(vantage: str) -> dict:
    """Ship this file to the box and run one vantage there.

    The result comes back gzipped and base64'd because `ssm
    get-command-invocation` truncates its output at 24,000 characters, and a
    silent truncation would look like a short measurement rather than a lost
    one.
    """
    source = base64.b64encode(Path(__file__).read_bytes()).decode()
    script = f"""
set -euo pipefail
echo {source} | base64 -d > /tmp/navprofile.py
FE=$(docker inspect -f '{{{{range .NetworkSettings.Networks}}}}{{{{.IPAddress}}}}{{{{end}}}}' uscode-redesign-frontend-1)
API=$(docker inspect -f '{{{{range .NetworkSettings.Networks}}}}{{{{.IPAddress}}}}{{{{end}}}}' uscode-redesign-api-1)
NAV_ASTRO="http://$FE:4321" NAV_API="http://$API:8001" NAV_WARM={WARM} NAV_COLD={COLD} \
  python3 /tmp/navprofile.py --vantage {vantage} | gzip | base64 -w0
"""
    encoded = base64.b64encode(script.encode()).decode()
    command_id = subprocess.run(
        [
            "aws", "--profile", AWS_PROFILE, "ssm", "send-command",
            "--instance-ids", INSTANCE,
            "--document-name", "AWS-RunShellScript",
            "--parameters",
            json.dumps({"commands": [f"echo {encoded} | base64 -d > /tmp/nav.sh", "bash /tmp/nav.sh"]}),
            "--query", "Command.CommandId", "--output", "text",
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    while True:
        time.sleep(10)
        proc = subprocess.run(
            [
                "aws", "--profile", AWS_PROFILE, "ssm", "get-command-invocation",
                "--command-id", command_id, "--instance-id", INSTANCE,
                "--query", "[Status,StandardOutputContent,StandardErrorContent]",
                "--output", "json",
            ],
            capture_output=True, text=True,
        )
        try:
            status, stdout, stderr = json.loads(proc.stdout)
        except ValueError:
            continue
        if status in ("Pending", "InProgress", "Delayed"):
            print(f"  {vantage}: {status}", file=sys.stderr)
            continue
        if status != "Success":
            raise SystemExit(f"{vantage} failed on the box: {status}\n{stderr}")
        return json.loads(gzip.decompress(base64.b64decode(stdout.strip())))


def step_map(profile: dict) -> dict[tuple[str, str, str], dict]:
    return {
        (j["name"], s["step"], s["phase"]): s for j in profile["journeys"] for s in j["steps"]
    }


def attribute(by_vantage: dict[str, dict]) -> list[dict]:
    """Each surface's own cost, from the difference between adjacent vantages.

    Nested measurements of the same path, so the subtraction is between two
    numbers that differ by one layer:

        edge   = internet + TLS + Caddy + Astro + (its API calls)
        caddy  =                   Caddy + Astro + (its API calls)
        astro  =                           Astro + (its API calls)
        api    =                                   one API call

    Astro's own cost is what is left of `astro` after the API calls that page
    makes — the first call plus the slowest of the parallel four, since they run
    in one `Promise.all`.
    """
    fan = {p["page"]: p for p in by_vantage.get("api", {}).get("fanout", [])}
    maps = {v: step_map(p) for v, p in by_vantage.items()}
    rows = []
    for key in maps.get("edge", {}):
        journey, step, phase = key
        edge = maps.get("edge", {}).get(key, {}).get("total_p50_ms")
        caddy = maps.get("caddy", {}).get(key, {}).get("total_p50_ms")
        astro = maps.get("astro", {}).get(key, {}).get("total_p50_ms")
        if edge is None:
            continue
        row = {
            "journey": journey,
            "step": step,
            "phase": phase,
            "edge_total_p50_ms": edge,
            "caddy_total_p50_ms": caddy,
            "astro_total_p50_ms": astro,
        }
        if caddy is not None:
            row["internet_and_tls_ms"] = round(edge - caddy, 1)
        if caddy is not None and astro is not None:
            row["caddy_own_ms"] = round(caddy - astro, 1)
        page = fan.get(step)
        if page and astro is not None:
            calls = [c for c in page["calls"] if c.get("total_p50_ms") is not None]
            if calls:
                first = page["sequential"]
                parallel = [c["total_p50_ms"] for c in calls[first:]]
                api_cost = sum(c["total_p50_ms"] for c in calls[:first]) + max(parallel or [0])
                row["api_calls"] = len(calls)
                row["api_cost_ms"] = round(api_cost, 1)
                row["astro_own_ms"] = round(astro - api_cost, 1)
                row["slowest_parallel_call"] = max(
                    calls[first:], key=lambda c: c["total_p50_ms"], default={}
                ).get("call")
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vantage", choices=["edge", "caddy", "astro", "api"])
    ap.add_argument("--out", default="docs/verification/navprofile.json")
    args = ap.parse_args()

    if args.vantage:
        print(json.dumps(measure(args.vantage), separators=(",", ":")))
        return 0

    by_vantage = {"edge": measure("edge")}
    for vantage in ("caddy", "astro", "api"):
        print(f"running the {vantage} vantage on {INSTANCE}", file=sys.stderr)
        by_vantage[vantage] = run_remote(vantage)

    artifact = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": HOST,
        "instance": INSTANCE,
        "command": "uv run python scripts/navprofile.py",
        "warm_iterations": WARM - 1,
        "cold_variants": COLD,
        "bytes": "wire bytes: every request sends Accept-Encoding and Caddy compresses (`encode gzip zstd`), so these are what crosses the network, not the rendered size",
        "rate_limits": LIMITS,
        "vantages": {
            "edge": "from a developer laptop over the internet: TLS, HTTP/2, Caddy, Astro, FastAPI, Postgres",
            "caddy": "on the box, over loopback to the same virtual host: everything but the internet",
            "astro": "on the box, to the Astro container's port 4321: no Caddy, no TLS",
            "api": "on the box, to the FastAPI container's port 8001: no Caddy, no Astro",
        },
        "attribution": attribute(by_vantage),
        "profiles": by_vantage,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
