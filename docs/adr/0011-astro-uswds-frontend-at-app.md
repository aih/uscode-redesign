# ADR-0011: Astro + TypeScript + USWDS frontend at /app

**Date:** 2026-07-28 · **Status:** Accepted (implemented in Session 7, BUILDLOG 014) · **Builds on:** ADR-0010 · **Refined by:** ADR-0015

## Decision

The `/app` reader becomes an **Astro 5 + TypeScript** application styled with the
**U.S. Web Design System (USWDS)**, consuming `/api/v1` as its only data source. The
FastAPI/Jinja reader remains until the Astro app passes the Session-7 acceptance spec
(BUILDLOG 008: mobile-first, navbar, one-line section title, top+bottom nav, ref hover
text, no broken `/us/pl/` links), then retires.

## Rationale

Full comparison in `docs/research/2026-07-ui-framework.md`. Deciding factors: Astro ships
zero JS by default, so statutory text stays server-rendered HTML — the reader's founding
principle survives the framework adoption; islands give per-component hydration for the
features that justify a framework at all (diff viewer, version timeline slider, watchlist,
citation search); TS is first-class; islands may be React or Svelte later without
re-platforming. USWDS is the federal government's own WCAG 2.1 AA / Section 508 design
system, framework-agnostic (plain HTML+CSS), and the obvious visual language for the
United States Code.

## What is consciously traded away

The "no build step, one stylesheet" principle (BUILDLOG 007) is retired for `/app`. A Node
build and SSR runtime join the stack. In exchange: a typed component model, a tested
accessible design system, and a frontend that can grow features without touching `api/`.
The API keeps zero frontend dependencies — the boundary ADR-0010 drew is what makes this
swap safe, and the architecture tests must keep proving it.

## Consequences

- Layout: `frontend/` (Astro app) beside `api/`, `web/` (Jinja, until parity). One reverse
  proxy serves `/app` → Astro SSR and everything else → FastAPI; compose gains a `frontend`
  service; `make dev` starts both.
- `web/uslm_html.py`'s USLM→HTML mapping is ported to a typed renderer in the Astro app
  (or exposed via the API as a rendered-HTML field — Session 7 decides and records which).
  **Decided: the typed renderer, in `frontend/src/lib/uslm.ts` — see ADR-0015.**
- Model assignment: frontend work stays Sonnet 5; the Astro scaffold + proxy wiring gets an
  Opus plan first (new service topology).
- PLAN §8: Node 20+ becomes a firm requirement, not a maybe.
