# B3's fixes, verified

What each of task B3's accepted fixes changed, as commands anyone can re-run.

These are **local** verifications against `make dev-all`. The deployed re-measurement —
`make navprofile`, `BASE=… make loadtest`, `make spine-explain` — has to wait until the branch is
deployed, because the fixes are not on the box; the artifacts beside this file are still the
before picture and say so in their `generated_at`.

Two of the three fixes can be verified faithfully here anyway, for reasons given under each. The
third, ADR-0046's byte budget, is a ratchet in `make test-web` rather than a number, and re-running
that suite is its verification.

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
