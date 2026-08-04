# Workstream B — Navigation, information architecture, retrieval

The complaint to design against, in the operator's words: *clunky; pop-outs to show individual
provisions; navigation extremely slow; hard to search; results not ordered by relevance; not a good
set of search operators; revision history must be interpreted from the editorial notes; nearly
impossible to compare a provision with its equivalent from another release point.*

Several of those are already answered by design in this codebase — ADR-0001 returns the whole
section with the provision anchored in place rather than in a pop-out; the timeline and redline
replace reading amendment history out of the notes. **The task is therefore mostly to make the
answers legible and fast, not to invent them.** Start each task by checking whether the behaviour
already exists and is merely unfindable.

---

## B1 — One IA map, then one navigation chrome

1. Produce `docs/ia-map.md`: every reader route, its purpose, its entry points, and its exits.
   Derive routes from the guide ratchet's `covers.routes`, not from memory. Flag every route with
   no inbound link from a non-search page — those are the "unfindable" ones.
2. From that, specify a single navigation chrome used by every reader page:
   - **breadcrumb** rendering the citation hierarchy, each level a link (title → chapter →
     subchapter → section), with the release context pinned to its right;
   - **a TOC rail** for the current chapter, marking the section being read (`aria-current`) and
     showing status badges inline so a repealed neighbour is visible before it is clicked
     (gotcha 9 keeps them in reading order — show that, don't hide it);
   - **prev/next** at both ends of the section, naming the neighbour, not "→";
   - **the search-and-citation box** in one place on every page (ADR-0023), never duplicated.
3. Delete anything the map shows to be a second way of doing the same thing. Fewer routes into the
   same state is the whole point.

Cost to record in the ADR: a TOC rail on every section page is one more query per view and one
more thing to keep in sync with `structure_nodes`, which is unversioned (CLAUDE.md) — so the rail
shows the newest loaded release's structure even when reading an older release point. Say that in
the UI rather than pretending otherwise.

---

## B2 — Make release context impossible to miss

Every reader page states, in the chrome and not in a footnote: which release point is being read,
its currency date, whether it is the newest, and — for `not` labels — the exception (gotcha 5: at
`119-102not101` the text is *not* fully current through 07/12/2026). When the Repository answered
from an earlier ingested release point, `served_from` must surface as visible provenance, since it
already refuses to do that silently at the API layer.

Add a release switcher next to it: newest / a date / a specific release point, preserving the
provision anchor across the switch. This is the single highest-value navigation change on the site
— it turns "which version am I looking at" from an inference into a fact.

---

## B3 — Navigation speed: measure, then fix, then re-measure

**Measure first.** `docs/verification/loadtest.json` is stale (predates ADR-0029's limiters,
ADR-0026's redline, and ADR-0037's `Disallow: /`). Regenerate it against the deployed box, and
add a *navigation* profile distinct from the load profile: cold and warm TTFB and full-render for
the five journeys in the test plan, at p50/p95, recorded per surface (Caddy → Astro → FastAPI →
Postgres/OpenSearch) so the slow layer is named rather than guessed.

Then, in this order, stopping when the numbers are good enough:
1. **Cache the spine.** Title list, chapter TOCs and section pages at the newest release are the
   hot path and change only when OLRC publishes (ADR-0036 already knows when that is). Audit
   ADR-0018's cache policy against reality; give the spine long `s-maxage` with explicit
   invalidation keyed to the load chain, and let Caddy serve it.
2. **Cut per-view fan-out.** Batch label lookups through the existing `/api/v1/labels` (100 max)
   instead of per-reference calls; one query per region of chrome, not per item.
3. **Astro payload budget.** The reader is server-rendered with small islands — assert that in CI:
   a per-route JS byte budget in `make test-web`, failing on regression. This is what protects
   speed while the design system lands.
4. **Postgres**: check the indexes the spine queries actually use (`EXPLAIN (ANALYZE, BUFFERS)`
   committed to `docs/verification/`), especially anything touching the 96M-row `guid_map`.

Do not add a client-side router. The URL scheme is the product.

---

## B4 — Search relevance, and operators worth having

Today: OpenSearch, strict by default, current-release by default, operators documented at
`/app/search/syntax` (ADR-0028, ADR-0031). Two gaps: ranking and expressiveness.

**Ranking** — write an ADR proposing and measuring a scoring model rather than shipping a hunch:
- field weighting (section `heading` and `num` well above body text), phrase-proximity boost,
  `current` release boost, and collapse of superseded versions so one section occupies one result
  row with "also matched in 4 earlier releases" rather than flooding the page;
- a **relevance judgement set**: 25–40 real queries with the sections a drafter would expect,
  committed to `docs/verification/search-judgements.json`, scored by nDCG@10 before and after. This
  is the only way "ordered by relevance" becomes a checkable claim instead of an opinion.
- explicit sort control: relevance / citation order / most recently amended.
- Note the recorded index caveat (ADR-0021 identifier collisions share an `_id`, so one of two is
  indexed) in the results UI where it can bite.

**Operators** — audit what exists against what this audience asks for, and document each with an
executable scenario: exact phrase; boolean AND/OR/NOT; grouping; proximity; field-scoped
(`heading:`, `title:16`, `chapter:`); status filters (`status:repealed`); release/date scoping
(`release:119-99`, `date:07/12/2026`); and truncation. `/app/search/syntax` claimed an untrue limit
for a fortnight once — this is exactly what ADR-0038's executable guide exists to prevent, so every
operator gets a ```scenario``` block.

Also: filters as facets on the results page (title, status, release), each reflected in the URL so
a search is citable.

---

## B5 — Compare any provision across release points, in two clicks

The machinery exists (ADR-0016 API diff, ADR-0026 reader redline). What is missing is the entry
point and the cost profile.

- Every section header gets **"Compare with…"**, defaulting to the previous release point where
  *this section's text actually changed* — not the previous release point in general. The version
  timeline already knows which those are; use it.
- Deep-link the comparison: `/app/diff?…from=…&to=…` with the provision anchor preserved, so a
  comparison is a citable URL.
- Provision-level compare, not just section-level: comparing `/c/5` should highlight that
  subsection's change within the section's redline, consistent with ADR-0001's "always keep
  context".
- Cost: the API diff is CPU-bound (~0.45 rps, collapsing past ~10 concurrent) and **about half of
  that cost is `@id` churn rather than legal change** — diffing guid-stripped text measured
  2,220 ms → 1,172 ms. Move the endpoint to guid-stripped diffing (the reader already avoids it),
  cache diffs by (identifier, from, to) — they are immutable — and keep ADR-0029's tight limiter.
  Regenerate `loadtest.json` for `/app/diff` afterwards; it is currently stale for exactly this
  reason.

---

## B6 — Dead ends and disappearances

- A repealed, omitted or transferred provision must render its status, its last live text, and
  where the subject matter went — never a bare 404. Identifiers can vanish at a release point
  without being repealed (gotcha 3): consider the redirects table that gotcha suggests, and record
  the decision either way.
- Appendix titles are unreachable by citation (`5 U.S.C. App. 3` → `/us/usc/t5a/s3`, which OLRC
  never publishes). The API explains rather than 404s; the **reader** should too, with the two real
  forms shown as examples.
- 404 and 429 pages get the search box and the breadcrumb of the nearest valid ancestor.
