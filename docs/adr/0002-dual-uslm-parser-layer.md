# ADR-0002: Schema-plural parser layer (USLM 1.x and 2.x)

**Date:** 2026-07-27 · **Status:** Accepted

## Decision

Ingest is built around a `UslmParser` protocol with two implementations — `Uslm1Parser` and `Uslm2Parser` — selected by `detect_uslm_version(file)`. Both emit the same normalized `SectionRecord`. All schema-specific knowledge is confined to the parser implementations; storage, API, and UI are schema-agnostic. Raw XML is stored verbatim with a `schema_version` tag.

## Rationale

Current OLRC release points are USLM 1.0 (`USLM-1.0.15.xsd`), but OLRC has announced the move to 2.x and publishes sample USC titles in USLM 2.x ([migration note](https://uscode.house.gov/currency/uslmv2.html), samples in `samples/uslm2/`). Per OLRC, the main USC-relevant differences are tables of contents, tables, and the indent model; 2.0.17 adds MathML. Building the seam now costs little; retrofitting it after OLRC flips would mean touching every ingest call site mid-production.

## Consequences

Fixtures for both schemas live in `samples/`. The exact version-detection rule is **now locked: the root namespace URI decides — see [ADR-0004](0004-uslm-version-detection-by-namespace.md)**, which also records why `xsi:schemaLocation` labels the point version but does not route. What the parsers treat as a section, and the Title 16 count correction that fell out of it, are in [ADR-0005](0005-what-counts-as-a-section.md). `Uslm2Parser` is a stub as of Day 1 (detection, `<meta>`, section extraction — no TOC, tables, or indent model) and reaches parity by Day 7.
