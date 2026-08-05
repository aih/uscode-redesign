#!/usr/bin/env python3
"""`EXPLAIN (ANALYZE, BUFFERS)` for every query the spine actually runs.

Task B3 step 4. The spine is the navigation path a reader takes to reach a
provision — the title list, a TOC, a section, its neighbours, its versions, the
release list, the batched labels, and the `?id=` guid lookup that reaches the
96,185,732-row `guid_map`.

**No SQL is written here.** Transcribing the repository's statements into this
file would make the artifact a record of what someone believed the code sends.
Instead a `before_cursor_execute` listener records every statement and its
parameters as `PostgresRepository`'s own methods run, and each captured
statement is then re-run under `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` with
the same parameters. What is explained is therefore what was executed, by
construction — the same property `scripts/inline_elements.py` gives the USLM
partition (ADR-0040).

Everything it runs is a read.

Where it runs
-------------
On the deployed box, inside the api container, which is the only place with both
the application code and the 27 GB corpus:

    docker exec uscode-redesign-api-1 python /tmp/spine_explain.py

`scripts/spine_explain.sh` is the wrapper that puts it there over SSM and writes
`docs/verification/spine-explain.json`. Locally it runs against whatever
`make dev-data` loaded, which is two release points of one title — useful for
checking the script, useless for a plan shape, and the artifact records the row
counts so the two cannot be confused.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from sqlalchemy import event, text

from db.base import SessionLocal, engine
from storage.postgres import PostgresRepository

#: The provision the rest of `docs/verification/` uses, so these plans line up
#: with the timings in `navprofile.json` and `loadtest.json`.
SECTION = os.environ.get("SPINE_SECTION", "/us/usc/t16/s45f")
PROVISION = os.environ.get("SPINE_PROVISION", "/us/usc/t16/s45f/c/5")
PARENT = os.environ.get("SPINE_PARENT", "/us/usc/t16/ch1/schVI")
TITLE = os.environ.get("SPINE_TITLE", "16")
RELEASE = os.environ.get("SPINE_RELEASE", "119-102not101")

#: Tables big enough that a sequential scan over one is the finding rather than
#: a detail. Row counts are read from the database at run time, never asserted.
WATCH = ["guid_map", "section_versions", "section_release_map", "structure_nodes", "sections"]


class Capture:
    """Records what the repository sends to Postgres, in order."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []
        self.on = False

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        if self.on and statement.lstrip()[:6].upper() == "SELECT":
            self.statements.append((statement, parameters))


def plan_summary(plan: dict) -> dict:
    """The parts of a plan worth committing: cost, scans, and what it read.

    A whole `FORMAT JSON` plan for a five-way join is a few hundred lines and
    nobody re-reads it in a diff. This keeps the shape — every scan node, the
    relation and index it used, its actual time and rows — and the buffer
    counts, which is what says whether the work was in shared_buffers or came
    off the disk.
    """
    scans: list[dict] = []

    def walk(node: dict) -> None:
        kind = node.get("Node Type", "")
        if "Scan" in kind:
            scans.append(
                {
                    "node": kind,
                    "relation": node.get("Relation Name"),
                    "index": node.get("Index Name"),
                    "actual_ms": node.get("Actual Total Time"),
                    "rows": node.get("Actual Rows"),
                    "loops": node.get("Actual Loops"),
                    "shared_hit": node.get("Shared Hit Blocks"),
                    "shared_read": node.get("Shared Read Blocks"),
                }
            )
        for child in node.get("Plans", []) or []:
            walk(child)

    root = plan["Plan"]
    walk(root)
    return {
        "execution_ms": round(plan.get("Execution Time", 0.0), 3),
        "planning_ms": round(plan.get("Planning Time", 0.0), 3),
        "shared_hit_blocks": root.get("Shared Hit Blocks"),
        "shared_read_blocks": root.get("Shared Read Blocks"),
        "scans": scans,
        # A sequential scan over one of the big tables is the thing this whole
        # script exists to find, so it is hoisted rather than left to be spotted.
        "seq_scans_on_large_tables": sorted(
            {s["relation"] for s in scans if s["node"] == "Seq Scan" and s["relation"] in WATCH}
        ),
    }


def explain(session, statement: str, parameters: Any) -> dict | None:
    try:
        rows = session.connection().exec_driver_sql(
            f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {statement}", parameters
        )
        return plan_summary(rows.scalar_one()[0])
    except Exception as error:  # a plan that will not explain is reported, not hidden
        return {"error": f"{type(error).__name__}: {error}"}


def main() -> int:
    capture = Capture()
    event.listen(engine, "before_cursor_execute", capture)

    with SessionLocal() as session:
        repo = PostgresRepository(session)
        sizes = {
            name: session.execute(
                text("select reltuples::bigint from pg_class where relname = :n"), {"n": name}
            ).scalar()
            for name in WATCH
        }
        guid = session.execute(
            text("select guid from guid_map where identifier = :i limit 1"), {"i": SECTION}
        ).scalar()

        resolved = repo.resolve_release(label=RELEASE)
        newest = repo.resolve_release()

        # Each entry is one repository call — the unit an API route makes, and
        # the unit the fan-out in `navprofile.json` counts.
        calls = [
            ("list_titles (front page)", lambda: repo.list_titles()),
            ("resolve_release, newest", lambda: repo.resolve_release()),
            ("resolve_release, by label", lambda: repo.resolve_release(label=RELEASE)),
            ("get_section", lambda: repo.get_section(SECTION, resolved)),
            ("get_section, unpinned", lambda: repo.get_section(SECTION, newest)),
            ("get_section, provision", lambda: repo.get_section(PROVISION, resolved)),
            ("get_toc, chapter rail", lambda: repo.get_toc(PARENT, resolved)),
            ("get_toc, title", lambda: repo.get_toc(f"/us/usc/t{TITLE}", resolved)),
            ("neighbors", lambda: repo.neighbors(SECTION, resolved)),
            ("versions", lambda: repo.versions(SECTION)),
            ("list_releases, one title", lambda: repo.list_releases(title_num=TITLE)),
            ("labels, batch of 1", lambda: repo.labels([SECTION], resolved)),
            ("resolve_id, guid_map", (lambda: repo.resolve_id(guid)) if guid else None),
        ]

        results = []
        for name, call in calls:
            if call is None:
                results.append({"call": name, "skipped": "no guid found for this identifier"})
                continue
            capture.statements.clear()
            capture.on = True
            try:
                call()
            except Exception as error:
                results.append({"call": name, "error": f"{type(error).__name__}: {error}"})
                capture.on = False
                continue
            capture.on = False
            # The capture has to be off before EXPLAIN runs, or the EXPLAIN's own
            # statement joins the list it is walking.
            captured = list(capture.statements)
            queries = []
            for statement, parameters in captured:
                summary = explain(session, statement, parameters)
                queries.append(
                    {
                        "sql": " ".join(statement.split()),
                        "params": _plain(parameters),
                        **(summary or {}),
                    }
                )
            results.append(
                {
                    "call": name,
                    "queries": len(queries),
                    "execution_ms_total": round(
                        sum(q.get("execution_ms", 0.0) for q in queries), 3
                    ),
                    "plans": queries,
                }
            )

    print(
        json.dumps(
            {
                "section": SECTION,
                "release": RELEASE,
                "table_rows_estimated": sizes,
                "calls": results,
            },
            separators=(",", ":"),
            default=str,
        )
    )
    return 0


def _plain(parameters: Any) -> Any:
    """Parameters trimmed to something a diff can read — an XML fragment is not."""
    if isinstance(parameters, (list, tuple)):
        return [_plain(p) for p in parameters]
    if isinstance(parameters, dict):
        return {k: _plain(v) for k, v in parameters.items()}
    text_form = str(parameters)
    return text_form if len(text_form) <= 120 else text_form[:117] + "..."


if __name__ == "__main__":
    sys.exit(main())
