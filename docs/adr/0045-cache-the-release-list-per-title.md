# ADR-0045: Cache the release list per title in the reader process

**Date:** 2026-08-04 · **Status:** Accepted · **Implements:** Workstream B task B3, fix 2

## Context

Task B3 asks to cut per-view fan-out. The measurement that motivated it named the call to cut.

A section page makes five API calls: one sequential (`fetchIdentifier`) and then four in a single
`Promise.all` — labels, neighbours, the release list, and the parent table of contents. Since the four
run together, the group costs the slowest of them, not their sum.

Measured at the API container on the deployed box (`docs/verification/navprofile.json`,
`docs/verification/loadtest.json`):

| call | p50 | bytes |
|---|---|---|
| `/api/v1/us/usc/t16/s45f` (sequential) | 15.8 ms | 28,364 |
| `/api/v1/labels?identifier=…` | 10.4 ms | 172 |
| `/api/v1/sections/…/neighbors` | 12.2 ms | 931 |
| `/api/v1/us/usc/t16/ch1/schVI` (the rail, ADR-0043) | 16.0 ms | 9,794 |
| **`/api/v1/releases?ingested_title=16`** | **27.0 ms** | **44,255** |

The release list is the slowest of the four, so it set the whole group's cost. It is also the slowest
unlimited API route under concurrency, at 247 ms p50 and 30.6 rps against 120 ms and 54 rps for the
section itself.

The endpoint earns that cost. `?ingested_title=` does not reach the repository as a filter: the route
asks `list_releases(title_num=None)` for all 382 release points and filters the result in Python, so
the work does not shrink when the answer does.

The list is the same for every section of a title, the same for every reader, and changes only when
the ingest chain loads something — at most once a day (ADR-0036).

## Decision

**Hold one release list per title in the reader process for five minutes.**
`frontend/src/lib/releasecache.ts`; pages call `cachedReleases` in place of `fetchReleases`.

**Entries hold the in-flight promise, not the value.** N concurrent misses for one title produce one
request. That is the case worth having: eight concurrent readers of one title is the shape the load
test measured the box collapsing under (11.0 rps, 702 ms p50), and it is also what a cold cache
immediately after a deploy looks like.

**A rejected fetch is evicted rather than cached**, guarded on the entry still being the current one
so a slow failure cannot delete whatever replaced it. A release list that failed to load must not be
the answer for the next five minutes.

**Five minutes is not a free parameter.** It is `REVALIDATE` from ADR-0018 — the `max-age` this site
already publishes for an unpinned answer. Choosing anything longer would make the reader staler than
what it tells browsers.

## Consequences

**A release point published while an entry is live is invisible to the picker for up to five
minutes.** The picker is the only thing affected. `served_from` — the release point a reader is
actually reading — comes from the section response on every request and is never served from this
cache, so no statutory text and no currency statement passes through it.

**The cache is per process and in memory.** A second instance would keep its own and a restart empties
it, which is the same shape and the same accepted cost as ADR-0029's rate limiters, and honest for
ADR-0020's single box.

**It is memory held per title.** Bounded by the number of titles a process serves in five minutes —
58 at the absolute worst, each a list of at most 382 release points.

**What it does not fix.** Removing 27 ms from a 37 ms parallel group leaves the next slowest call at
16 ms, so a single reader saves about 11 ms of a 78 ms origin cost inside an 823 ms journey. The gain
worth having is the box's: one fewer 44 KB serialization per section view, on two vCPUs, on the route
the load test showed saturating. The alternative fix — making `?ingested_title=` a repository-level
filter rather than a Python one — is a real improvement to the endpoint and is not this ADR; it is
recorded as a candidate task.
