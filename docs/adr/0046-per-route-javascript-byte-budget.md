# ADR-0046: A per-route JavaScript byte budget, counted from source

**Date:** 2026-08-04 · **Status:** Accepted · **Implements:** Workstream B task B3, fix 3

## Context

"The reader is server-rendered with a handful of small islands" (ADR-0011, ADR-0022) is a claim
nothing checked. B3 asks for a per-route JS byte budget in `make test-web` that fails on regression,
to protect that property while the design system lands.

The obvious implementation — weigh the built bundles — has nothing to weigh. `astro build` emits **no
client JavaScript at all** for this site: `dist/client/_astro/` holds only CSS. Every island is
`<script is:inline>`, which Astro passes through into the HTML verbatim and never bundles. A live
`/app/us/usc/…` response confirms it: zero `<script src>`, seven inline scripts.

So the thing to measure is inline script bytes per route, and those live in the `.astro` files.

## Decision

**Count from source, and enforce a ceiling per route.** `frontend/tests/jsbudget.test.ts` walks each
page's transitive `.astro` import graph, sums the bytes inside `<script is:inline>`, and fails when a
route exceeds its ceiling in `docs/js-budgets.json`. The measured numbers are written to
`docs/verification/js-bytes.json`, the way `a11y.spec.ts` writes its own artifact.

**Counting from source is what lets it run with no server and no build**, in the existing Vitest
runner. A budget that needs a running stack is a budget nobody runs, and B3 forbids a fourth runner.

**The static count is validated against a rendered page rather than assumed.** Source says 32,150
bytes for `/app/us/usc`; the live page carries 25,474. The 6,676-byte difference is exactly
`AuthNav` (3,239) plus `WatchButton` (3,437), both behind `ACCOUNTS_ENABLED` (ADR-0034).

**Comments inside inline scripts count**, because Astro ships them verbatim and a reader downloads
them. These scripts carry long explanatory comments and that is a real 25 KB on a section page.

**Where two page files serve one route, the ceiling is the heavier**, not the sum:
`us/usc/[...identifier].astro` and `us/usc/index.astro` are both `/app/us/usc`, and a request reaches
one of them.

**Ceilings carry 200 bytes plus rounding to the next 500 of headroom**, so editing a comment does not
fail the build. 600 bytes of growth does, which was checked by injecting it: 16 routes failed, naming
the islands on each.

## Consequences

**The count is what a route *can* ship, not always what it did.** A component behind a false condition
still contributes — that is the whole 6,676-byte gap above. Over-counting is the safe direction for a
ceiling, and the alternative (evaluating conditions statically) is not decidable.

**`CopyColumn`'s `<script type="application/json" data-copy-targets>` is excluded.** Its size is the
section's provision list rather than code, so it varies per URL — 4,278 bytes on
`/app/us/usc/t16/s45f`. A static ceiling over it would be a ceiling on the statute. It is real bytes
to a reader and it is now measured nowhere continuously; that is the cost accepted here, recorded as a
candidate task rather than pretended away.

**Raising a ceiling is a decision, not a chore.** The failure message says to raise it in the same
commit as the growth and say why in the build log, so the edit is the record.

**This measures bytes, not cost.** 25 KB of inline script that never executes is cheaper than 5 KB
that blocks paint, and this budget cannot tell the difference. It guards against the reader quietly
acquiring a framework, which is what ADR-0022 is about.
