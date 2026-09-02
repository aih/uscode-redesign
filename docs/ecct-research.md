# The Editorial Classification Change Table: what exists beyond the two documents loaded

**Status:** research note, 2026-09-02. The loader holds 21 ECCT rows from two documents. This note
records what was checked about the earlier tables, why they were not found, what was built to
find them, and the procedure that finishes the job from a machine that can reach OLRC.

## What the loader holds, and how it found it

`python -m ingest classification` reads two index pages —
`https://uscode.house.gov/classification/tables.shtml` (the current Congress) and
`priortables.shtml` (the 104th to the 118th) — and follows every `href` that matches the
classification-table pattern (`tbl{congress}{pl|cd}[_{1st|2nd}].htm`) or the ECCT pattern. On
2026-08-11 that walk found 31 Public Law tables and **two** ECCT documents
(`data/manifests/classification.json`):

| Document | Session | Rows |
|---|---|---|
| `ecct.html` | 119th, 2nd (named only in the sentence linking it) | 1 |
| `ecct_119-1.html` | 119th, 1st | 20 |

Both are linked from `tables.shtml` only. `priortables.shtml`'s three fixture rows
(`tests/fixtures/priortables_slice.shtml`, the 118th, 109th and 104th) carry no ECCT link, and the
manifest says the full page linked none the loader recognised. `tables.shtml` also carries, in an
HTML comment, a link to two PDFs of note dispositions for the Title 10 part V reorganisation
(`t10NoteDispoPostPartVReorg.pdf` and its reverse) — editorial transfers recorded outside the
ECCT, not reachable by this loader, and not tables of the ECCT's shape.

The ECCT's own explanation (`tests/fixtures/ecct.html`) says which session it describes — *"changes
in classification of earlier laws made in the course of classifying new laws from the 119th
Congress, 2nd Session"* — and that *"other changes in classification of earlier laws are made in
the course of integrating the new laws into a main edition or supplement of the Code, and those
changes will be accounted for in Table III"*. So the ECCT is one rolling page, rewritten each
session, and the changes made while preparing an edition or supplement are in Table III, not here.

## Where the earlier rows would be

Three places, in the order they are worth looking:

1. **Archived copies under a suffixed name.** OLRC archived the 119th's first session as
   `ecct_119-1.html`. If it did the same for earlier sessions — `ecct_118-2.html`,
   `ecct_118-1.html`, back to whenever the table began — those files may exist without an index
   page linking them, or under a spelling the loader's pattern did not accept. The pattern
   required exactly `ecct_{congress}-{session}.html`; an archived copy named `ecct_118-2.htm`
   (the tables' own extension), `ecct118-2.html` or `ecct_118_2.html` was silently dropped.
2. **Earlier captures of the rolling page.** Every capture of `ecct.html` in the Wayback Machine
   describes the session its explanation names. A session whose table was overwritten and never
   archived under a suffixed name survives only there.
3. **Table III.** The changes OLRC folds into an edition or supplement are recorded per Statute
   at Large in Table III (`/table3/`), a different document with a different shape, and out of
   this note's scope.

## What was verifiable from this session, and what was not

Every route to OLRC and to the archives is closed from the container this session ran in: the
egress proxy rejects `uscode.house.gov`, `web.archive.org`, `archive.ph`, `index.commoncrawl.org`,
`govinfo.gov` and the search engines' cached copies. The AWS credentials present in the
environment are not valid (`InvalidClientTokenId`), so neither the deployed box, which polls OLRC
daily, nor the S3 mirror could stand in. The prior-art loader (`dreamproit/loadusc-xcitedb`,
cloned read-only) has no classification-table code to compare against.

What could be established is therefore about the loader, not about OLRC:

- The 2026-08-11 walk did not miss a link matching its pattern. Whether earlier tables exist under
  another name, or only as captures, is the open question.
- The loader could not have found an archived table named with `.htm` or without the underscore.

## What was built

- **Tolerant naming.** `_ECCT_FILENAME_RE` and `_ECCT_HREF_RE` accept `ecct[_-]?{congress}[_-]{session}.htm[l]`
  in any case. `links_on_disk` therefore also picks up an archived copy placed in a `--from-file`
  directory under any of those spellings.
- **The page dates itself.** `ecct_session_from_page(html)` reads the Congress and session out of
  the ECCT's own explanation. A copy of `ecct.html` fetched or captured at any date can be assigned
  to the session it describes, and a suffixed file whose name disagrees with its page is trusted
  by the page and reported.
- **`--probe-ecct`.** `python -m ingest classification --probe-ecct` asks OLRC for every archived
  name below the newest session the index pages know — `ecct_{c}-{s}.html` and `.htm` for each
  session from the 104th up, about sixty requests once, under the shared ~1 req/sec throttle —
  loads whatever answers 200 and parses as an ECCT, and records the 404s
  (`ClassificationLoadReport.probe_misses`) rather than failing on them. Network runs only; a
  `--from-file` run has nothing to probe.
- **`scripts/ecct_wayback.py`.** Queries the Wayback Machine's CDX API for every distinct capture
  of `uscode.house.gov/classification/ecct*`, fetches each raw capture, dates it by its own page,
  writes the latest capture of each session to `data/classification/wayback/ecct_{c}-{s}.html` —
  a directory `python -m ingest classification --from-file` loads as archived tables — and writes
  `docs/verification/ecct-history.json`: every distinct row across every capture with the
  sessions and dates it was seen at. `--from-cache` re-parses fetched captures without querying.

Both the probe and the script are tested against fakes (`tests/test_classification_loader.py`,
`tests/test_classification_parser.py`, `tests/test_ecct_wayback.py`); neither has been run against
the network.

## The procedure, from a networked machine

```bash
# 1. The archived names OLRC may hold, linked or not. Loads what it finds.
uv run python -m ingest classification --probe-ecct

# 2. The rolling page's history from the Wayback Machine.
uv run python scripts/ecct_wayback.py
uv run python -m ingest classification --from-file data/classification/wayback

# 3. Re-derive the attributions with the new rows (ADR-0077), then the report.
uv run python -m ingest version-changes --reattribute
uv run python -m ingest version-changes --report && make sync-verification
```

Step 1's output names every 404; a list of 404s from `ecct_104-1` to `ecct_118-2` is the finding
that OLRC does not archive earlier sessions under that name, and step 2 is then the only source.
Step 2's report says how many sessions the captures cover and how many rows each held. A row
loaded from a capture carries the session its page named; `classification_files` records the
Wayback URL as its `source_url`.

## What the rows would change

`ingest/version_changes.py` attributes a transition `editorial` when an ECCT row's prompting law
arrived with it (ADR-0077). Each recovered session adds its rows to that lookup; the reattribute
pass rewrites the law rows and the `attribution` value without touching the classification of
kinds. The report's `ecct_law_rows` and `editorial` counts, both zero-filled today, are where the
effect shows, and `/app/classification/ecct` lists every loaded session.

What the ECCT will still not cover is the reclassification done while preparing an edition or
supplement (Table III), and the whole-title editorial reclassifications OLRC publishes as
disposition tables on `/editorialreclassification/` — Titles 34, 51, 52 and 54 among them, the
last of which moved most of Title 16's National Park Service provisions in 2014. Those are the
cross-identifier moves gotcha 3 and ADR-0065 describe, they are PDFs, and reading them is its own
task.
