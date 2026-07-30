# ADR-0022 — USWDS retained; the UI refresh adds no client framework

- **Status:** Accepted
- **Date:** 2026-07-29
- **Context:** Session 10 (UI refresh before deploy), BUILDLOG 024

## Context

Four reader problems were queued before the ADR-0020 deploy: titles listed in
string order, no way to jump to a citation, cross references showing only a
heading, and nothing pinned while scrolling. The question asked first was
whether to adopt **Appica**, a React component library, to build them — the
owner was leaning toward it — evaluated against alternatives that had to be
mobile-first, accessible by default, and rich in components for text display.

## What Appica actually is

Measured on 2026-07-29, not inferred:

| Signal | Value |
|---|---|
| npm `@appica/ui-react` | **v1.0.0 — the only version ever published**, 2026-07-09 |
| GitHub `appica-dev/appica-ui` | created 2026-07-09, **last push 2026-07-09**, 61 minutes later |
| Stars / forks / open issues | 130 / 9 / 1 |
| Weekly downloads | **1,124** |
| Peer dependencies | React ≥19, React DOM ≥19, Tailwind ≥4 |
| Dependencies | `@base-ui/react`, `motion`, `embla-carousel@9.0.0-rc02` |
| License | MIT |

For scale, in the same week: `@base-ui/react` 7,650,000 downloads, `@ark-ui/react`
993,000, `@uswds/uswds` 68,000.

Its component inventory is genuinely apt — **Preview Card** is precisely the
hover-preview requirement, and it also ships Scroll Area, Table of Contents,
Breadcrumb, Combobox and Popover. This is not a bad library. It is a
three-week-old library with no commits since the hour it was published,
distributing a 1.0.0 that pins pre-release dependencies.

## Decision

**Keep USWDS. Add no client framework. Build the four features on platform
primitives.**

Three reasons, in order of weight:

**1. The renderer cannot accept React components.** `frontend/src/lib/uslm.ts`
turns USLM XML into an **HTML string**, consumed with `set:html`. It is the one
module outside the parsers permitted to know USLM element names (architecture
rule 5), it runs on the server on `@xmldom/xmldom`, and a React hover card cannot
wrap a `<ref>` inside a string. Adopting Appica for the preview means rewriting
that module to emit React elements — the single most load-bearing piece of
presentation in the project — to gain a component we can build in ~3 KB.

**2. USWDS is the point on a US Code site.** It is the federal government's
design system; ADR-0011 chose it with Section 508 as the stated bar. Replacing it
with a Tailwind-based library weeks before the site goes public trades an
institutional visual language for a novel one, on a site whose entire claim is
fidelity to what OLRC publishes.

**3. The platform now has the primitives.** `popover` supplies the top layer,
Escape and light dismiss. CSS anchor positioning is Baseline 2026 (~91% of
traffic; Safari 18.2–18.3 has `anchor()` without `@position-try`, which the
fallback handles). Dark mode already exists in `site.scss` as eight custom
properties under `prefers-color-scheme` — the feature named on the Appica docs
page that prompted this evaluation was already shipped.

The measured cost of the decision: the whole refresh added **one** island of
about 3 KB. The React path would have added React, React DOM, Tailwind, an Astro
React integration and ~15 transitive packages to a site that currently ships zero
framework JavaScript.

## Consequences

- Appica's *ideas* are adopted and its code is not. The hover card is its
  Preview Card, built on `popover`; the scroll area is `overflow-y: auto` plus
  `overscroll-behavior: contain`; the sticky TOC is `position: sticky`.
- Two things had to be built by hand that a library would have supplied, and
  both are recorded where they were got wrong: `--sticky-h` is a measured
  constant that drifts with the chrome (held honest by an e2e assertion), and
  WCAG 1.4.13's three clauses are three explicit mechanisms rather than a
  vendor's implementation (ADR-0024).
- The evaluation is retained rather than summarised so that a later reader can
  disagree with the *reasoning* rather than the conclusion. If Appica is
  maintained for a year, points 1 and 2 still stand and point 3 grows stronger.

## Alternatives considered

- **Appica wholesale.** Rejected above.
- **React 19 + Base UI for the islands only**, keeping USWDS for chrome.
  Middle cost, mature dependencies (Base UI is what Appica wraps), but it leaves
  two styling systems to maintain permanently and still does not solve point 1 —
  `uslm.ts` would keep emitting strings and the card would keep being built by
  hand inside a React root that bought nothing.
- **Ark UI / Zag.js**, which is framework-agnostic and would work in Astro
  without React. The closest real contender. Rejected because the four features
  needed exactly one popover, and a state-machine component library is a large
  answer to that question.
