# ADR-0082 — A load that did not finish is not a load

**Status:** accepted (2026-09-16)

**Task:** The deployed site was missing most of title 42 — `/us/usc/t42/s1395b–2` answered 404,
`/us/usc/t42/ch6` listed no sections — while every alarm read `OK` and `/api/v1/status` said
`behind_by: 0`.

**Amends:** ADR-0014 (the resume marker, which the serving path now honours as well as the
loader); ADR-0036 (which measures whether the site *looks* for new law, and now also whether it
*holds* what it found).

## Context

OLRC published release point 119-102 on 2026-07-12, changing titles 7, 12, 15 and 42. The box's
daily check found it on 2026-09-10, downloaded the four zips, pushed them to the mirror, and ran
`load-all`. Titles 7, 12 and 15 loaded in three minutes. Title 42 ran for 2h47m and the kernel
killed it:

```
Out of memory: Killed process 1451592 (python3) total-vm:8979744kB, anon-rss:4784300kB
```

The weekly `--force` sweep on 2026-09-14 redid it and was killed the same way at 5.7 GB. Both runs
logged one line — `could not read the loaded count from load-all — assuming it loaded` — and
exited before the verify gate, whose `incomplete_loads` check is the one that would have named the
problem.

What the two kills left behind is the failure a reader saw. `load_release` writes the
`title_versions` row and the structure pass in its first commit and stamps `sections_loaded` last
(ADR-0014), so title 42 at 119-102 was a row with no sections behind it: `section_release_map`
held 0 rows for the pair. Every query that decides which release point to serve a title from
joined `title_versions` without looking at the marker:

- `_served_from` — the gotcha-10 fallback — picked 119-102 for title 42, the newest row at or
  before the request, and found nothing there. A section 404'd with "nothing at … in release point
  119-102"; a chapter rendered with no sections.
- `_latest_release(title_num)` made 119-102 the default release point for the title, so a bare URL
  hit the same row.
- `list_releases` reported title 42 as ingested at 119-102, so `/app/releases` showed no dagger and
  `/api/v1/status` counted the release point as loaded, `behind_by: 0`.

`load_all.completed_pairs` and `ingest verify` already treated a NULL marker as "not loaded". The
loader and the reader disagreed about what a row meant, and the reader was wrong.

### Why the loader ran out of memory

`load_release` looks up every stored version of the title once, to decide whether each section's
text is new. It selected the `SectionVersion` rows:

```python
for version in session.scalars(select(SectionVersion).where(SectionVersion.section_id.in_(ids))):
    existing_versions.setdefault(version.section_id, {})[version.content_hash] = version
```

A `SectionVersion` row carries `xml`, the stored text. Title 42 has 136,213 versions and 3.8 GB of
it, held in one dictionary for the length of the load. On the development machine (17 GB) that
fits. On the site box, 7.8 GB shared with Postgres, OpenSearch, Redis and a second project's
stack, it does not. The dedupe loop reads two fields of each row — `id` and `first_release_id` —
and never the text.

`scripts/load_memory.py` measures the lookup alone, both ways, for title 42
(`docs/verification/load-memory.json`):

| lookup | versions | peak RSS |
|---|---|---|
| `SectionVersion` rows | 136,213 | 5.48 GB |
| four columns | 136,213 | 0.17 GB |

### Why nothing said so

- The chain exited at `load-all failed`, before `ingest verify` and its `incomplete_loads` gate.
- `USCode/SourceCheckStale` was 0: the check had run and succeeded. It measures looking, not
  holding.
- `USCode/SiteUp` was 1: `/health` and `/us/usc/t16/s45f` answered.
- `/api/v1/status` counted a release point with any `title_versions` row as loaded.
- The daily cron's exit status goes to a log file; the weekly Actions run went red on 2026-09-14
  and that was the only signal, four days after the first failure.

## Decision

### 1. Every serving query carries the completion marker

`_served_from`, `_latest_release`, `list_releases` and `list_titles` join `title_versions` through
one predicate, `_load_finished()` — `sections_loaded IS NOT NULL`. A row without it is a load in
progress or a load that died, and either way its sections are not all there. With the marker
honoured, the half-loaded row is inert: title 42 is served from 119-83, the newest complete load,
with `served_from` saying so, exactly as if 119-102 had never been attempted.

`tests/test_load_all.py` plants a `title_versions` row with a NULL marker at a release point
newer than anything loaded and asserts that a section and a TOC are served from the release
before it, that neither listing counts the row, and that the health report names it.

### 2. The loader keeps ids and hashes, not rows

`known_versions_statement(title_id)` selects `(section_id, id, content_hash, first_release_id)`,
and the dedupe dictionary holds a two-field `_KnownVersion`. `existing_sections` likewise maps an
identifier to a section id rather than a `Section` row, which also stops each post-commit access
from re-selecting the expired row. A test holds the statement to those four columns.

### 3. The corpus reports whether it holds what it should

`Repository.corpus_health()` returns `incomplete_loads` — `label/title` pairs with a NULL marker
— and `unloaded_titles` — pairs newer than the newest release point at which every changed title
is loaded, that the inventory says changed and no completed load covers. The walk stops at the
first fully loaded release point on purpose: the 44 title-releases OLRC never published
(`unavailable` in the backfill ledger) would otherwise sit in the list forever and the list would
be ignored.

`/api/v1/status` carries both under `corpus`, plus `newest_complete_release`. The reader's
currency note reports them ahead of `behind_by` and stale: "Title 42 at release point 119-102 is
not loaded here yet. Those pages are served from the release point before it."

### 4. Every run of `update-corpus.sh` publishes the count, and an alarm reads it

An `EXIT` trap publishes `USCode/CorpusIncomplete` — `incomplete_loads + unloaded_titles` — on
every path out of the script, the early `exit 1` after a failed `load-all` included.
`uscode-corpus-incomplete` alarms after two daily periods above zero and treats missing data as
breaching. A failed load-all also logs its exit status, and names the OOM killer for 137, since a
killed loader prints nothing at all.

## Consequences

**The reader is honest about a half-loaded title but not about a half-loaded release point.**
Titles 7, 12 and 15 at 119-102 are complete and are served from it; title 42 is served from
119-83 with a note. `/app/releases` shows the dagger on title 42 alone. That is the truth of the
database and better than the alternative of hiding the three that worked, but a reader comparing
titles at "119-102" is reading two different currency dates.

**`unloaded_titles` measures from the newest fully loaded release point**, so a gap older than
that is invisible to it. The backfill ledger and `ingest verify --deep` are the record of those;
this report is for what the daily poll just did.

**The alarm's period is a day**, so a gap is reported by the run that leaves it and paged on the
second consecutive day. A new release point whose load fails on the day it appears is mail the
day after. That is the daily cadence ADR-0036 chose, and it is six days faster than what happened.

**The trap publishes once per run, after the lock.** An overlapping scheduled run exits before
the trap is set and publishes nothing, so the reading is always the run that held the lock. A
`--check-only` run publishes what the corpus holds at that moment, which during a multi-hour load
is a transient nonzero, absorbed by the two-period evaluation.

**The box is still shared and still 8 GB.** The lookup is 32x smaller; the load itself was not
measured on the box, only on the development machine (`BUILDLOG` 101). A future title larger than
42, or a second project growing on the same box, is the same failure again; the alarm is what
turns it into mail rather than into six quiet days.

**The half-loaded row on the box is deleted by hand**, not by this change: the reader ignores it
either way, and `load-all` redoes any pair without the marker on its next run, which is the weekly
sweep or the next new release point. The command is in `docs/deploy-status.md`.
