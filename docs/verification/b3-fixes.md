# B3's fixes, verified

What each of task B3's accepted fixes changed, as commands anyone can re-run.

The deployed re-measurement is done — PR #24 merged, `deploy.yml` ran, and all three artifacts beside
this file were regenerated against the box. The comparison is in "Before and after" at the end.

The local checks below are kept because two of them isolate a single fix, which the deployed
comparison cannot: the deploy carried B1 and B2 as well.

## Fix 4 — the `structure_nodes.identifier` index

The local table holds **9,916 rows, the same count as the deployed corpus** (`spine-explain.json`,
`table_rows_estimated.structure_nodes`), because `structure_nodes` is the newest loaded release's
view of the hierarchy rather than something that grows per release point (ADR-0006). So the plan
change measured here is the plan change on the box.

```bash
docker compose exec -T db psql -U uscode -d uscode -c \
  "explain (analyze, buffers) select * from structure_nodes where identifier = '/us/usc/t16/ch1/schVI'"
```

Before (index dropped):

```
Seq Scan on structure_nodes  (cost=0.00..360.95 rows=1 width=120) (actual time=0.280..1.497 rows=1 loops=1)
  Filter: ((identifier)::text = '/us/usc/t16/ch1/schVI'::text)
  Rows Removed by Filter: 9915
```

After:

```
Index Scan using ix_structure_nodes_identifier on structure_nodes  (cost=0.29..8.30 rows=1 width=120) (actual time=0.134..0.135 rows=1 loops=1)
  Index Cond: ((identifier)::text = '/us/usc/t16/ch1/schVI'::text)
  Buffers: shared hit=3
```

**1.497 ms → 0.135 ms**, and 9,915 rows no longer read to find one. The deployed measurement of the
same scan was 1.3 ms, inside `get_section`, both `get_toc` paths and `resolve_id` — so a section view
paid it two or three times.

This is a small share of a reader's wait and is not claimed to be more: the whole of Postgres was
under 2 ms per repository call before the index. It is here because it was the only sequential scan
on the spine and it cost one migration.

## Fix 2 — the release list out of the per-view fan-out (ADR-0045)

Counted from the API's own access log, so it counts requests that were actually made rather than
requests the reader believes it makes.

```bash
docker compose restart frontend && sleep 6
START=$(date -u +%Y-%m-%dT%H:%M:%S)
for i in $(seq 1 8); do curl -s -o /dev/null \
  "http://localhost:8000/app/us/usc/t16/s45f?release=119-102not101" & done; wait
docker compose logs --since "${START}Z" api | grep -oE 'GET /api/v1[^ ]*' | sed 's/?.*//' | sort | uniq -c
```

Eight concurrent views against a **cold** cache:

```
   8 GET /api/v1/us/usc/t16/s45f
   8 GET /api/v1/us/usc/t16/ch1/schVI
   8 GET /api/v1/sections/us/usc/t16/s45f/neighbors
   8 GET /api/v1/labels
   1 GET /api/v1/releases
```

One release call for eight views, not eight: entries hold the in-flight promise, so concurrent misses
collapse into a single request. Repeating the loop against a warm cache produces **zero**.

Before this change the last line read `8 GET /api/v1/releases`, one per view, each costing the API
27.0 ms and 44,255 bytes at the container (`navprofile.json`, `loadtest.json`).

## Fix 3 — the byte budget (ADR-0046)

`make test-web`. The measured bytes land in `js-bytes.json` beside this file; the ceilings are
`docs/js-budgets.json`. That the ratchet bites was checked by injecting 600 bytes into a component on
every route's graph — 16 routes failed, each naming its islands — and it passes again with the bytes
removed.

## Fix 1 — declined

ADR-0047, with the measurement that declines it.

## Before and after, on the deployed box

**What the two runs actually compare.** The previous deploy was `387ff3a`, which is the commit this
branch was cut from — so the *before* box was running main with **none of B1, B2 or B3**, and the
*after* box has all three. This is not a clean A/B for B3. The after box's section page carries a
whole `ChapterRail`, a `ReleaseContext` band and a `ReleasePicker` that the before box did not, and
it makes **five** API calls where the before page made four (`fetchToc` for the rail is new; the
release list is now usually a cache hit). Read the reader-page rows as "workstream B, all of it",
not as "B3's fixes".

**And there is a headwind.** Across the twelve routes this session did not touch and whose URL did
not change, the after run's p50 is a median **1.073×** the before run's (range 0.995–1.123) — same
laptop, same link, different hour. Nothing in this session touches those routes, so that is ambient
drift, and the gains below are understated by roughly that much.

### The spine's query plans (`spine-explain.json`)

Every call that resolves a path through `structure_nodes`, before → after:

| repository call | before | after |
|---|---|---|
| `get_section` | 1.649 ms | **0.348 ms** |
| `get_section`, unpinned | 1.602 ms | **0.345 ms** |
| `get_section`, provision | 1.662 ms | **0.390 ms** |
| `get_toc`, chapter rail | 1.769 ms | **0.446 ms** |
| `get_toc`, title | 1.760 ms | **0.541 ms** |
| `resolve_id` (96 M-row `guid_map`) | 1.388 ms | **0.119 ms** |

`seq_scans_on_large_tables` is now empty for all thirteen calls. The calls that never touched
`structure_nodes` are unchanged: `neighbors` 0.291 → 0.308 ms, `list_titles` 1.518 → 1.591 ms.

This one **is** attributable to B3 alone — nothing else in the deploy touches Postgres.

### The reader's pages under load (`loadtest.json`, 8 concurrent)

| route | before | after |
|---|---|---|
| reader section page | 11.0 rps, 702.4 ms p50 | **15.6 rps, 480.0 ms** |
| reader TOC page | 14.4 rps, 525.5 ms p50 | **35.0 rps, 183.7 ms** |

The table of contents page gained most, which is what the fan-out predicts: it made two API calls and
the release list was the slower of them, so removing it from the per-view path removes most of the
page's API cost. The section page gained less because its critical path still contains four calls.

`releases the picker can offer` moved 30.6 rps → 23.1 rps, but that row changed URL: it now measures
`?ingested_title=`, the parameter the reader actually uses, rather than the cheaper `?title=`. The
endpoint did not get slower; the measurement got correct.

### One reader, no contention (`navprofile.json`, warm p50)

Four clicks down the spine: **823 ms → 801 ms at the edge**, of which the origin is **221 ms →
159 ms**. The network share is unchanged and still dominates, which is ADR-0047's whole argument.

Per step, origin only: title TOC 57.8 → 30.3 ms, chapter TOC 56.5 → 26.4 ms, section 77.8 → 71.2 ms.

**The attribution arithmetic had to be corrected for this run.** `api_cost_ms` counted every call a
page makes, and after ADR-0045 a page does not make the release call — counting it credited a table
of contents page with 41.2 ms of API time when the whole page took 22.1 ms, and printed a *negative*
figure for Astro's own share. `FANOUT` entries now carry a `cached` list, timed and reported with
`per_view: false` but excluded from the critical path. The corrected attribution was re-derived from
the same stored measurements rather than re-measured.
