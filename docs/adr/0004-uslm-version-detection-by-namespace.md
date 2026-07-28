# ADR-0004: Detect the USLM version from the root namespace

**Date:** 2026-07-27 · **Status:** Accepted · **Supersedes the open question in [ADR-0002](0002-dual-uslm-parser-layer.md)**

## Decision

`detect_uslm_version(source)` reads **only the root element's start tag** and selects the parser on the **namespace URI**, nothing else:

| Root namespace | Generation | Parser |
|---|---|---|
| `http://xml.house.gov/schemas/uslm/1.0` | USLM 1.x | `Uslm1Parser` |
| `http://schemas.gpo.gov/xml/uslm` | USLM 2.x | `Uslm2Parser` |

Any other namespace raises `UnknownUslmSchemaError` — an unrecognized schema fails loudly rather than being parsed as a guess.

`xsi:schemaLocation` is read **for the record, not for the routing**: its `.xsd` filename yields the point version (`USLM-1.0.15.xsd` → `uslm-1.0.15`, `uslm-2.0.12.xsd` → `uslm-2.0.12`), stored as `title_versions.schema_version`. When it is absent or unparseable, the schema version degrades to `uslm-1.x` / `uslm-2.x` and detection still works.

## Evidence (repo samples, 2026-07-27)

```
samples/uslm1/usc16.xml           xmlns=http://xml.house.gov/schemas/uslm/1.0
                                  xsi:schemaLocation="… USLM-1.0.15.xsd"
samples/uslm2/USLM2/usc{01,16,49}.xml
                                  xmlns=http://schemas.gpo.gov/xml/uslm
                                  xsi:schemaLocation="… uslm-2.0.12.xsd"
```

The namespace changed **host and path** across the generations (house.gov → gpo.gov), so it is a total, unambiguous discriminator on the sample corpus.

## Rejected alternatives

- **Parse `xsi:schemaLocation` and route on it.** It is optional in XML, and OLRC's own 2.x samples point at a `govinfo.gov` URL rather than a bare filename — a formatting change would silently break routing. It is also *finer* than the parser boundary: 1.0.14 and 1.0.15 must not select different parsers.
- **Root element name.** `<uscDoc>` in both. Carries no version at all.
- **`dc:creator` / `processedBy` converter version** (`USCConverter 1.7.2` vs `4.8.0`). Correlates today, but it names the *tool*, not the *schema*, and CLAUDE.md gotcha 8 warns that 2013–2015 release points came from a different converter build of the *same* schema.
- **Filename or release-point year.** The whole point is that a single ingest run may meet either schema; the file must speak for itself.

## Consequences

- Sniffing a 32 MB title costs one buffered read, so `parser_for()` may be called freely — `iter_sections()` sniffs before streaming and the cost is unmeasurable.
- `Uslm2Parser` becomes reachable the day OLRC flips release points to 2.x, with no ingest change. Detection is exercised by `tests/test_uslm_detect.py`, including a truncated document that proves nothing past the root tag is required.
- The parser layer shares one streaming traversal (`StreamingSectionParser`) that knows **no element names of its own**: each implementation supplies an `ElementNames` vocabulary and its own `<meta>` reader. CLAUDE.md architecture rule 2 ("never hard-code USLM 1.x element paths outside `Uslm1Parser`") is therefore satisfied by construction — the shared code cannot name a 1.x element, because it has no names. The 1.x/2.x differences OLRC actually documents (TOC markup, tables, indent model) are all outside section extraction, which is why one traversal is enough for Day 1; each will land as an override in `Uslm2Parser` on Day 7.
