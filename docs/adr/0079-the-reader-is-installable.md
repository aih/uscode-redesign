# ADR-0079 — The reader is installable

- **Status:** Accepted
- **Date:** 2026-09-02
- **Context:** `docs/pwa-spec.md` Phase P1 (the spec's research findings are
  cited by number below); ADR-0015 (one Caddy routes `/app/*` to the
  frontend), ADR-0027 (the runtime theme), ADR-0030 (the CSP), ADR-0042 /
  ADR-0052 (the token block as the one source of colour), ADR-0046 (the JS
  byte budget), ADR-0065 (every dead end carries a trail). Session 96.

## Context

The reader had no install identity: no manifest, no icon under `/app`, no
`theme-color`, no `apple-touch-icon` (spec finding 4). Chromium requires only
HTTPS plus a valid manifest to offer installation — a service worker stopped
being an install criterion at Chrome 108/112 (finding 14) — so identity alone
makes the site installable on desktop and Android, and names it correctly on
an iOS Home Screen. Two behaviours are wrong in a standalone window before
anything is added: every cross reference and search result ships
`target="_blank"` and so opens a browser tab *outside* the installed app
(finding 9), and `/app/search` and `/app/goto` carry no trail at all, on the
one surface with no browser back button (finding 10).

## Decision

1. **The manifest lives under `/app`.** `frontend/public/` surfaces at
   `/app/<path>` (finding 1) and everything outside `/app` reaches FastAPI
   (finding 2), so `frontend/public/manifest.webmanifest` is served at
   `/app/manifest.webmanifest` with no Caddy, FastAPI or CSP change —
   `manifest-src` falls back to `default-src 'self'` (finding 3). `id` and
   `scope` are `"/app/"` with the trailing slash (`"/app"` also matches
   `/apple…`), `start_url` is in scope, `display` is `standalone` because
   `minimal-ui` falls back to `browser` on iOS (finding 15), and
   `launch_handler` is `navigate-existing`.

2. **Icons are generated, not drawn twice.** `scripts/icons.py`
   (`uv run --with cairosvg`, the `scripts/fonts.py` pattern — cairosvg is
   not a project dependency) renders `static/favicon.svg` into
   `frontend/public/icons/`: 192/512 `purpose: any`, 192/512
   `purpose: maskable` with the mark in the inner 80% on a full-bleed
   background, and an opaque 180px `apple-touch-icon` (iOS composites no
   alpha). `any` and `maskable` are separate entries — a combined
   `"any maskable"` icon has its `any` rendering cropped (finding 16's
   sources). `docs/verification/icons.json` pins the outputs to the source
   SVG's sha256. Two renderer facts the script absorbs: cairosvg ignores
   `textLength`, so the script measures the word's natural width and applies
   the squeeze `spacingAndGlyphs` would; and the glyphs come from whatever
   font the machine resolves for the favicon's stack, so a rebuild elsewhere
   can differ in outline at the same geometry — the same dependence the
   favicon itself has on the browser rendering it.

3. **The title bar follows the theme through one meta.** The manifest's
   `theme_color` is static and there is no manifest dark-mode member
   (finding 17), so `Base.astro` carries one `<meta name="theme-color">`
   defaulting to the light `--page`, corrected pre-paint by the theme
   bootstrap and moved by `ThemeToggle` on every toggle. The manifest's
   `theme_color` and `background_color` stay the light `--page`
   (`background_color` is the splash only). All five occurrences are the
   token block's values and `tests/pwa.test.ts` fails when any drifts.

4. **Standalone behaves as `usc-linktarget === "same"`.** The link-target
   script treats `matchMedia("(display-mode: standalone)").matches ||
   navigator.standalone` as the same-tab preference, so cross references and
   search results navigate in place inside the installed app. A browser tab
   is unchanged, and the markup's `target="_blank"` default stands with
   scripting off — the safety property the script already had.

5. **`viewport-fit=cover` and the safe-area padding land together.**
   `env(safe-area-inset-*)` padding on `.topbar`, on `.sectionbar` in the
   band where `.topbar` is `display: contents` and renders no box, and on
   `.usa-footer`. `env()` is 0 outside a notched standalone window, so
   nothing moves in a browser — `sticky.spec.ts`'s geometry assertions are
   the referee.

6. **`/app/search` and `/app/goto` carry a trail** — Home › Search — closing
   ADR-0065's one remaining no-trail gap. The `current` entry keeps an empty
   identifier so `PrintHeader`, which renders only for a page with a citation
   to name, stays silent.

## Declined

- **`window-controls-overlay` / `display_override`** — `standalone` is the
  intended mode everywhere; an overlay title bar is chrome this reader does
  not want to own.
- **Manifest `screenshots`** (the richer install UI) — addable later from
  `make shots` output if wanted.
- **`@vite-pwa/astro` / Workbox** — their value is precache-manifest
  generation, which an SSR reader with no client bundle barely uses
  (finding 18); Phase P2's worker is hand-rolled.

## Consequences

- **Every route's JS budget rises once** for the theme-color correction and
  the standalone check (~600 bytes with their comments, in `Base.astro`'s
  graph, which every route imports) plus `ThemeToggle`'s meta write. Ceilings
  re-measured per `docs/js-budgets.json`'s headroom rule.
- **The manifest's colours are static**: an installed dark reader gets a
  light splash; the title bar is correct from first paint.
- **iOS is unverifiable in CI** — Add to Home Screen has no emulation; the
  deploy check is a manual device pass, owed in `docs/deploy-status.md` when
  the phases deploy.
- **Five committed PNGs**, regenerable from the committed SVG and pinned by
  `docs/verification/icons.json`.
- Installation without Phase P2's worker means no offline behaviour yet: an
  installed app with no network shows the browser's own error page.
