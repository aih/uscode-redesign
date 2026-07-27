# ADR-0001: Postgres v1, sections as the storage atom

**Date:** 2026-07-27 · **Status:** Accepted

## Decision

v1 stores each versioned **section** of USLM XML as a row in Postgres. Sub-section provisions (`/us/usc/t16/s45f/c/5`) are extracted from the section XML at request time by `@identifier` XPath, not stored separately. All access goes through a `Repository` interface; XCiteDB (purpose-built for versioned USLM) becomes a second implementation later — building on the existing loader in [dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb) — with no API/UI changes.

## Rationale

Sections are the natural reading unit and the level at which OLRC's change tracking is practical. Storing finer grains would multiply rows ~5–10× (Title 16: 5,393 sections vs ~29,000 subsection/paragraph/clause elements) with no retrieval benefit, since readers need section context anyway. Postgres first because it's boring, operable, and lets the week-1 deadline hold; the Repository interface preserves the XCiteDB path.

## Consequences

Content-hash dedupe across release points is required (each RP republishes all titles). Provision-level anchors depend on `@identifier` fidelity inside stored fragments — parser tests must cover deep nesting.
