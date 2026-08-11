# Wave 2 kickoff — classification tables, C2b (the loader)

Paste the block below into a fresh Claude Code session on this repository, with Opus selected.
Everything it needs beyond `CLAUDE.md` is in `docs/classification-spec.md`.

---

Read `CLAUDE.md`, then `docs/classification-spec.md` in full — §2 (schema), §3 (scraper), §6
(verification), § What Wave 1 measured, and the C2b phase prompt. Wave 1 (the parser and the
schema) is merged on `classification-wave1` and open as PR #44; branch from it, not from `main`.

Execute Wave 2 — phase prompt C2b, the loader, CLI and poll. It is one agent's worth of work and
the join point between C1 and C2a, so run it in this session rather than dispatching it. Work in a
worktree on a branch named for the phase, small commits, imperative messages, `Co-Authored-By`
trailer.

What C2b owns:

- `load_file` in `ingest/classification.py` — wholesale replace per file in one transaction: delete
  that file's entries, re-insert every row, update the registry row in place. It commits nothing;
  the CLI owns the transaction. Closed congresses short-circuit on the content hash.
- `poll_classification` + `record_classification_check` — a file link missing from a fetched index
  page fails the check rather than deleting data, the same refusal `poll_source` makes for vanished
  release-point labels.
- The fetch layer: disk cache at `data/classification/`, `.part`-then-rename, the 1 req/s throttle
  and `USER_AGENT` from the existing ingest modules.
- The `classification` and `classification-check` subcommands in `ingest/__main__.py`'s dispatch
  dict, exit codes 0 nothing new / 10 changed / 1 failed.
- Per-file verification JSON in `docs/verification/classification-{congress}-{session}.json` and the
  summary in `data/manifests/classification.json`.
- `make ci-data` loading the committed fixture slices via `--from-file`, so Wave 4's guide scenarios
  can be answered offline.

Five things Wave 1 measured that the spec's earlier sections do not say — § What Wave 1 measured is
the authority where they disagree:

1. `db.models.ClassificationEntry` / `EcctEntry` collide by name with
   `ingest.classification.ClassificationEntry` / `EcctEntry`. A loader importing both must alias one
   side.
2. `classification_files.skipped_lines` is an `Integer`; the parser produces the lines themselves.
   Store the count and let the lines survive in the verification JSON.
3. `ecct_entries` has neither `ondelete="CASCADE"` nor `UniqueConstraint(file_id, row_seq)`, where
   `classification_entries` has both. Delete its rows explicitly, and decide in this phase whether
   the asymmetry stays — it is spec §2's, not an oversight of C2a's.
4. `session = 0` is the 104th's whole-congress file, on both `TableLink` and
   `ParsedClassificationFile`. NULL would defeat `UniqueConstraint(kind, congress, session)`.
5. Every `*_raw` column is NOT NULL with `''` for a blank cell: `description_raw = ''` means
   amended and `pl_section_raw = ''` means a whole-law row. Pass the empty string, never `None`.

Run the full live backfill once — 31 `pl` files plus the ECCT, ~33 polite requests. 28 of those
files have never been through this parser; a vintage whose header tokens moved raises
`ClassificationParseError` rather than storing garbage, so treat a raise as the parser needing a new
offset era and not as a file to skip. Commit the verification artifacts.

Verify, and report each: a re-run of `classification` is a no-op; `classification-check` exits 0
twice, then 10 against an edited covered range; check rows are written on both the success and the
failure path; `make test` green including the new integration tests (`USC_REQUIRE_INTEGRATION=1`);
row counts per file recorded against the parse reports.

End the session by updating `docs/classification-spec.md`'s status line, appending the BUILDLOG
entry, and saying what Wave 3 (C3 the API, C4 the reader pages — two agents in parallel) will need.
Stop before Wave 3.
