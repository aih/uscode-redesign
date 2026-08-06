# ADR-0003: GUID = (provision, release point) pin; identifier = cross-release identity

**Date:** 2026-07-27 · **Status:** Accepted

## Decision

Two complementary keys, two jobs:

- `@identifier` (`/us/usc/t16/s45f/c/5`) is the **cross-release identity** of a provision and the basis of the URL scheme. Version selection is by `?release=` or `?date=`.
- `@id` GUIDs are **intentionally regenerated at each release point**: a GUID uniquely names the pair *(provision, release point)*. We maintain a global `guid_map(guid → identifier, release)` index over every element id in every ingested file. `GET /us/usc/?id={guid}` therefore needs no version parameter — the GUID is a permanent citation to exact text at an exact point in time.

## Rationale

Observed in the data: OLRC's converter assigns fresh GUIDs per publication (usc16.xml @ 119-102not101, `USCConverter 1.7.2`). Verified: `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` ↔ `/us/usc/t16/s45f/c/5` in that release. Treating regeneration as a feature (a version pin) rather than a defect gives the site stable deep citations for free — valuable for scholars citing "the text as it stood."

## Consequences

`guid_map` is large (every element × every RP with changed content) — index it well and populate during ingest. GUIDs must never be used to correlate a provision across releases; that's `@identifier`'s job, with renumbering/transfer handled by a redirects table (PLAN §9.3, renumbered from §9.2 on 2026-08-06).
