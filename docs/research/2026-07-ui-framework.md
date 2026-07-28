# UI framework research — determination for the /app frontend

**Date:** 2026-07-28 · **Requested by:** Ari · **Feeds:** ADR-0010 (reader/API separation), ADR-0011 (proposed adoption)

## The question

Is there a TS/JS framework that (a) ensures accessibility, (b) allows flexible building of
new features (version timelines, diffs, watchlists, search), and (c) fits a citation-first,
document-heavy site whose core value is statutory text rendering identically for everyone —
including no-JS clients, screen readers, and archival crawlers?

## Constraints that decide this

1. **The text must be server-rendered HTML.** A law reader that requires JavaScript to show
   the law fails the site's own robustness claim. This rules out client-first SPAs (CRA-style
   React, plain Vite+React) as the *primary* rendering path.
2. **Accessibility is a compliance target, not a vibe** — this is US federal statutory
   material; WCAG 2.1 AA / Section 508 is the bar users will judge it by.
3. **The API is already the product's backend** (`/api/v1`, ADR-0010). The frontend should
   consume it, not replace it — no second data layer.
4. **Future features are islands of interactivity** in oceans of text: a diff viewer, a
   timeline slider, watchlist buttons, a citation search box. We need per-component
   hydration, not whole-page hydration.

## Candidates (2026 state)

| Framework | Fit | Notes |
|---|---|---|
| **Astro 5 (+ TS)** | **Best fit** | Server-first; **ships zero JS by default** — statutory text stays plain crawlable HTML, matching the current reader's ethos exactly. Islands architecture hydrates only interactive components, and islands can be written in React, Svelte, or plain TS as taste evolves — the framework doesn't lock the component model. First-class TypeScript, SSR adapter for Node behind the same reverse proxy as FastAPI. The consensus 2026 guidance puts it first for document/content-heavy sites by a significant margin. |
| **SvelteKit 2** | Strong runner-up | Excellent SSR, smallest bundles, and the compiler emits **built-in accessibility warnings** at build time. Chooses one component model (Svelte) for everything; a fine choice if the team wants a single full-stack JS idiom, but it makes the whole page a Svelte app where Astro leaves it as HTML. |
| **Next.js 15 (React)** | Capable, heaviest | Biggest ecosystem and hiring pool; RSC gives zero-JS static rendering in principle, but the framework's complexity and React runtime are costs this site doesn't need. Justified only if React-ecosystem components (react-uswds, React Aria) become central. |
| **htmx/Alpine on Jinja** | Cheapest, not TS | Keeps today's stack, adds sprinkles of interactivity. Doesn't answer the TS/component-model question; fine as a bridge, dead-ends before diff viewers and watchlist UI. |

## The design-system layer (this is where accessibility actually comes from)

Frameworks don't ensure accessibility; disciplined markup and a tested design system do.
For a United States Code site the natural choice is **USWDS — the U.S. Web Design System**
(designsystem.digital.gov): the federal government's own toolkit, WCAG 2.1 AA / Section 508
conformant, mobile-first by design, familiar to every user of federal sites. USWDS is plain
HTML + CSS + a little vanilla JS — **framework-agnostic**, so it works in Astro templates
directly (no wrapper library needed; `react-uswds` exists but pins USWDS versions and is
only needed if we choose React islands).

## Determination

**Adopt Astro 5 + TypeScript for the `/app` frontend, styled with USWDS, consuming
`/api/v1`.** Rationale in one line each:

- Astro preserves the reader's founding principle (text is HTML, JS is opt-in) while adding
  the TS component model and island hydration that future features need.
- USWDS supplies Section 508-grade components and mobile-first layout for a federal-subject
  site — accessibility by construction, not by audit.
- The FastAPI/Jinja reader stays running at `/app` until the Astro app reaches parity
  (Session 7 acceptance = the BUILDLOG 008 spec passes in Astro), then Jinja is retired to
  an internal debug view or deleted. The API is untouched throughout — which is the point
  of ADR-0010.

Costs, stated plainly: a Node build and runtime joins the stack (two services behind one
proxy); `make dev` grows a frontend target; the "no build step" principle is consciously
traded away in exchange for the component model — recorded in ADR-0011, not glossed.
