# ADR-0007: Dedupe on guid-stripped content, not on raw XML

**Status:** Accepted — 2026-07-27 (Session 3.5)
**Context:** PLAN.md §3, §9.10 (gotcha 10); ADR-0001 (sections are the storage atom);
ADR-0003 (a guid pins (provision, release point)). Corrects the dedupe rule shipped in
BUILDLOG 005.

## The measurement that forced this

Every release point republishes all 54+ titles, but few titles change, so ingest must
deduplicate identical section content or storage explodes (~324 release points × ~1 GB).
BUILDLOG 005 implemented that as `sha256(section.xml)` and verified it by re-loading the
*same file* under a second label, where it worked perfectly.

Loading a genuinely different release point showed what that test could not. Title 16 at
119-99 (06/12/2026) against Title 16 at 119-102not101 (07/12/2026):

| | count |
|---|---|
| sections in each release point | 5,095 |
| identical raw XML | **0** |
| identical after removing `@id` attributes | **5,093** |
| genuinely amended (`/us/usc/t16/s2201`, `/us/usc/t16/s2206`) | **2** |

Dedupe by raw XML collapsed nothing: two release points of one title produced 10,190
`section_versions` rows and 32 MB, where the truth is 5,097 rows.

The cause is ADR-0003's first sentence. **Guids are regenerated at every release point by
design** — they identify (provision, release point). Every `@id` inside a section therefore
changes at every release point, so the raw XML of an untouched section is *never*
byte-identical between two of them. Gotcha 1 and gotcha 10 were both in CLAUDE.md; what was
missing was the observation that the first one defeats the second one.

## Decision

**`content_hash = sha256(section XML with every `@id` attribute removed)`.**

Parsers emit that form as `SectionRecord.content_key`, alongside the untouched `xml`.
Nothing else is normalized: whitespace, attribute order, `@style`, `@class` and text all
still participate, so any real editorial change still produces a new version. `@id` is
stripped by the parser, not by storage, because knowing that `@id` is USLM's volatile
identity attribute is schema knowledge (CLAUDE.md architecture rule 2).

Result on the same two release points: 5,095 new versions for the first, then **2 new and
5,093 deduped** for the second; `section_versions` drops from 32 MB to 16 MB.

## What this costs, and what it does not

`section_versions.xml` stores the fragment as it was published **at the release point where
that text first appeared**. For the 5,093 unchanged sections, serving them at
119-102not101 returns XML carrying 119-99's guids.

What is unaffected:

- **`?id={guid}` lookups.** `guid_map` indexes every guid of every release point
  independently — 125,410 rows for these two — so any guid still resolves to its provision
  and its release point. That path never reads the stored fragment's attributes.
- **Which text you get.** The text, structure, status and source credit returned for a
  release point are that release point's, byte-for-byte. Only the volatile ids differ.
- **Provenance.** The published zip's sha256 is in `title_versions` and in
  `data/manifests/{release}.json`; anyone can re-download and diff.

The API therefore reports the release a fragment was stored from, rather than implying the
bytes are the requested release's.

Two ways to close the gap exactly, both deferred until something needs it:

1. Store the per-(section, release) guid sequence in document order and re-inject on
   render. Exact, and costs roughly what `guid_map` already costs.
2. Reconstruct from `guid_map` by identifier — cheaper but incomplete, because elements
   like `<p>` carry an `@id` without an `@identifier` of their own and cannot be
   distinguished from their siblings.

## Consequences

- Dedupe is now verified against two real release points, not a re-load of one file. The
  synthetic re-load test remains, but it is no longer the evidence.
- `content_key` is part of the parser contract: a schema whose volatile identity attribute
  is not `@id` supplies its own implementation.
- Any future normalization of the hash (say, ignoring `@style` churn) is a deliberate
  widening of "the same content" and belongs in its own ADR — it is the difference between
  "this text did not change" and "this text did not change *much*".
