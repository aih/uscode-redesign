# ADR-0038: The user guide is executable

**Status:** Accepted
**Date:** 2026-08-03
**Related:** [ADR-0010](0010-reader-and-api-separated-behind-a-redirecting-citation-url.md) (the reader
the guide documents), [ADR-0011](0011-astro-uswds-frontend-at-app.md) (Astro, which renders markdown
without help), [ADR-0023](0023-citations-parse-server-side-to-an-identifier.md) /
[ADR-0031](0031-search-is-strict-unless-asked.md) (the syntax page, whose tables the guide links
rather than copies), [ADR-0034](0034-features-built-and-switched-off-say-so.md) (a switched-off
feature explains itself — so must the guide), PLAN §11 (documentation duties)

## Context

The site has no user guide. What reader-directed prose exists is spread across `/app/about` (what
the site is), `/app/search/syntax` (citation forms and search operators) and a scattering of hint
lines beside individual controls. Nothing anywhere describes reading at a release point, the
version timeline, the redline, the copy modes, the guid permalink, or what the API is for — which
is most of what was built.

The reason to be careful about how a guide gets written here is that this project already knows
what happens to documentation that is only prose. `/app/search/syntax` carries a summary box
headed "Not the whole picture yet", saying the search index holds only current text and that a
point-in-time search therefore answers from the present. That was true when it was written. The
full index — 489,578 documents, current and superseded — was built on the box on 2026-08-02 and
recorded in `docs/deploy-status.md`. The site has been telling readers it cannot do something it
does. Nobody was careless; the sentence simply had nothing checking it.

That is the general case. A user guide is the largest surface of unverifiable claims a project can
own, it decays fastest, and it decays silently — a broken build is loud, a wrong sentence is not.
A guide describing 40-odd features across nine chapters, updated by hand as the site develops,
would be wrong within a fortnight and would stay wrong.

Two other things were wanted from the same material: a regression suite covering the reader at
journey level (the eight existing Playwright specs are deliberately deep and narrow — WCAG 1.4.13
clauses, sticky geometry, clipboard modes — and none of them assert that the documented path
through a feature works end to end), and a demo video. Writing those separately means writing the
same walkthroughs three times, in three notations, kept in sync by nobody.

## Decision

**The guide's chapters are markdown pages the reader serves, and every behavioural claim in them
carries a scenario block that is simultaneously a Playwright test and a scene of the demo video.**

Three parts.

**1. The chapters are `.md` files at `frontend/src/pages/guide/*.md`, served at `/app/guide`.**
Astro renders markdown pages natively against a layout named in frontmatter, so this adds no
rendering dependency, no build step and no second place where HTML is generated. The chapters keep
the site's chrome, its theme, its typography and its accessibility work by being pages of it, and
they stay plain readable markdown in the repository — which matters for a project whose
documentation is read on GitHub as often as it is browsed.

**2. Behaviour is documented in `scenario` fences, next to the prose that claims it.**

````
```scenario
id: release-pin
title: Read a section as it stood at an earlier release point
steps:
  - goto: /app/us/usc/t16/s45f?release=119-99
    caption: Any provision, at any release point.
  - expect: { selector: ".provenance", contains: "119-99" }
```
````

One block is one regression test and one candidate video scene. `frontend/scripts/scenarios.mjs`
extracts and validates them; `frontend/tests/e2e/guide.spec.ts` runs each as a Playwright test in
the existing e2e job; `frontend/scripts/demovideo.mjs` replays the ones flagged `demo: true` with
their captions on screen. The prose and the proof are the same edit, and the video is a view of
the test suite rather than a separate asset that ages.

**3. A ratchet in `make test-web` refuses new surface the guide does not cover.** Every route under
`frontend/src/pages/` must be claimed by some chapter's `covers.routes`, and every ADR must be
listed either in a chapter's `covers.adrs` or in the checker's explicit infrastructure exemption
list. A new reader page or a new user-facing decision turns the web suite red until the guide
accounts for it. This is what makes "the guide is kept up to date" a property of the build rather
than a resolution in a documentation duty, and it is why the scope of the guide can be trusted
without anyone auditing it.

The step vocabulary is deliberately small — `goto`, `click`, `fill`, `press`, `hover`, `focus`,
`scroll`, `expect`, `pause` — and the scenarios are journey-level. The hand-written specs keep the
assertions a DSL should not try to carry.

**The video is served from this origin, and travels there the way the corpus does.** It plays at
`/app/demo` from `/static/demo/uscode-demo.mp4`, which is the only arrangement that needs no change
to the CSP: ADR-0030 declares no `media-src`, so media falls back to `default-src 'self'` and a
same-origin file plays while a YouTube or CloudFront embed would be blocked outright. Relaxing that
for a demo would be a poor trade, and this project has already answered the same question once —
ADR-0032 vendored 2.4 MB of Swagger UI rather than load it from a CDN, for the same reason.

The assets cannot be in the image: they are recorded on a workstation against the full corpus,
Actions has neither the corpus nor ffmpeg nor a running site, and a 3 MB binary regenerated per demo
does not belong in the history. So they go workstation → S3 → box (`deploy/publish-demo.sh`), which
is the path the corpus itself already takes under ADR-0013, and the box mounts them read-only at
`/app/static/demo`. **This needs no new credentials:** the upload uses the mirror identity that
already has `s3:PutObject` on `usc/*`, and the fetch uses the instance role, which already carries
`s3:GetObject`/`s3:ListBucket` on the whole bucket for `mirror pull`.

## Consequences

**Good.** A claim in the guide is executed on every push, so the guide cannot drift from the site
in the way `/app/search/syntax` did — and that stale box is fixed in the same commit as the chapter
that links to it. The reader gets documentation inside the site, at the same URL scheme, in the
same theme. The demo video regenerates from the guide with one command, so a feature that changes
its walkthrough changes the video too. And the journey-level coverage the e2e suite lacked arrives
as a side effect of writing prose, which is the cheapest way it was ever going to arrive.

**Costs, named.**

- **The step vocabulary is shallow, and deliberately cannot express the assertions that matter
  most.** No scenario checks that a hover card is dismissible without moving the pointer, or that
  a deep-linked provision clears the sticky bar. Those live in `preview.spec.ts` and
  `sticky.spec.ts` and always will. The guide suite proves the documented path works; it does not
  prove the feature is correct, and reading it as though it did would be a mistake.
- **CI runs the scenarios against the fixture corpus — Title 16 at two release points.** That is
  what `make ci-data` loads (ADR-0013: CI never fetches from OLRC). Any scenario needing more is
  marked `data: corpus` and skips in CI, so it is verified only when someone runs the suite locally
  against the full corpus. A `data: corpus` scenario is therefore a weaker claim than a default
  one, and the guide does not distinguish the two for the reader.
- **The video is a local artifact, not a CI-reproduced one.** `make demo-video` needs ffmpeg and a
  running site, and everything it writes to `static/demo/` is gitignored — video binaries do not
  belong in a git history that is meant to be read. `docs/demo/scenes.json` is committed, so what
  the video says is reviewable in a diff, but whether the deployed mp4 matches the current guide is
  not enforced by anything. Regenerating and re-publishing it is a step in the release checklist,
  not a gate — and because it is a manual step, the video is the one part of this design that can
  still go stale. That is the residual of the problem this ADR set out to solve, and it is named
  here rather than papered over.
- **Serving it costs the box bandwidth.** 3 MB per view from a single small instance, which is
  nothing at demo traffic and would not be at scale. `preload="none"` on the player means a visitor
  who does not press play pays for a 42 KB poster instead. If it ever matters, the answer is a CDN
  in front of the same origin, not a third-party embed.
- **The ratchet will annoy someone.** Adding a reader page now means editing a guide chapter in the
  same commit, and adding an ADR means classifying it. That is the intended cost — it is the only
  mechanism here that survives the author's attention — but it is a real tax on small changes, and
  the exemption list is what keeps it to one line for work that has no reader-visible surface.
- **Two more copies of the site's own vocabulary.** The guide describes citation forms and search
  operators that `citationforms.ts` and `searchsyntax.ts` hold canonically and `/app/search/syntax`
  renders from them. The guide links to that page and must never restate the tables; nothing
  enforces that but review.
