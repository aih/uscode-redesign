# CLAUDE.md — uscode-redesign

Versioned US Code retrieval site: any provision, at any release point (RP), via a URL scheme
mirroring the USLM `@identifier`. FastAPI + Postgres v1, XCiteDB later behind a repository
interface. Full context in [PLAN.md](PLAN.md); decisions in `docs/adr/`.

**Status:** The reader/API separation is live (`frontend/` exists, Jinja is gone). The release-point
inventory is seeded (382 RPs with real `currency_date` and a true global `seq`) and **the whole corpus
is loaded — 3,153 title-releases across 58 titles and 381 release points, 65,938 distinct sections,
5,466,652 (section, release) pairs stored as 489,738 `section_versions`, 91.0% deduped, 96,185,732
`guid_map` rows, 27 GB on disk** (ADR-0007's dedupe working at full scale); `structure_nodes` holds the
hierarchy from a streaming TOC pass (ADR-0006). The backfill is **COMPLETE** — the ledger is 3,153 `ok`
/ 44 `unavailable` / 0 pending, 9.7 GB on disk — and the S3 mirror (ADR-0013) holds all of it, verified
against the local corpus.

`storage/` has the `Repository` protocol + Postgres implementation, plus a second, narrower
`AccountsRepository`/`PostgresAccounts` pair for users/sessions/watchlists (ADR-0017 — not bolted onto
`Repository`, which stays version-resolution-only), and `storage/search.py` over OpenSearch (ADR-0028).
`api/` serves PLAN §4's routes — identifier lookup with `?release`/`?date`/`?format`, `?id=` guid lookup,
TOC, neighbors, versions, releases, a diff between two release points (ADR-0016), the batched
`/api/v1/labels` (100 identifiers max, the bound the route enforces), `/api/v1/search`,
`/api/v1/citation`, `/api/v1/status` (how current the mirror is and when it last checked, ADR-0036),
and auth + watchlist CRUD (ADR-0017). `frontend/` is the reader — **Astro 5 +
TypeScript + USWDS** at `/app/us/usc/…` (ADR-0011, ADR-0015), server-rendered with a handful of small
islands: sticky reading chrome, a version timeline, a reading-text redline (ADR-0026), keyword search,
hover previews (ADR-0024), one search-and-citation box (ADR-0023), a theme toggle (ADR-0027), and a copy
control (ADR-0033). Every response carries a cache policy (ADR-0018); every expensive unauthenticated
route is rate-limited (ADR-0029); CSP and frame headers are ADR-0030; accounts and bulk downloads are
built-and-off in the UI, a UI switch and not a security control (ADR-0034).

There is a **user guide at `/app/guide`** (ADR-0038) — ten markdown chapters in
`frontend/src/pages/guide/`, rendered by Astro against `GuideLayout`. It is *executable*: each
behavioural claim carries a ` ```scenario ` block that is at once the documented walkthrough, a
Playwright test, and (when flagged `demo: true`) a captioned scene of `make demo-video`. A Vitest
ratchet refuses a reader route or an ADR that no chapter accounts for. See Documentation duties 6.

**Accessibility is a ratchet in the browser suite** (ADR-0039). `frontend/tests/e2e/a11y.spec.ts`
runs axe-core over the route matrix in `docs/a11y/routes.json` — 35 route entries (one expanding to
every guide chapter on disk), three viewports, both themes, one `forced-colors: active` pass and
fourteen interactive states — among them the compact reading density (ADR-0054), the open shortcut dialog
(ADR-0055), the open release switcher (ADR-0056) and both site menus open at a phone width
(ADR-0058), both navbar dropdowns (ADR-0061), the command palette (ADR-0062) and the open
classification lookup (ADR-0067) — **322 scans**,
against `wcag2a`/`wcag2aa`/`wcag21a`/`wcag21aa`. A
violation whose (route, rule) pair is not in `docs/a11y/known-violations.json` fails the build, and a
serious or critical one fails **even when listed** unless its entry names that exact impact in
`waiveSeverity`. A route may declare **`readyWhen`**, a selector the scan waits for before running
axe: the two vendored bundles draw themselves, `load` fires on a shell, and a scan that lost that
race reported **one** node (`html-has-lang`, off the server's own `<html>`) where a rendered one
reports 174 — which is the whole of why this artifact's node count used to differ between runs of
identical code. Every entry carries the task that owns the fix; the measured baseline is
`docs/verification/a11y.json`. `make shots` carries the same ratchet for horizontal overflow at 320
CSS px and at 1280 zoomed to 200% (WCAG 1.4.10 and 1.4.4). Playwright's `globalSetup`/`globalTeardown`
for this live in `frontend/scripts/`, not `tests/e2e/` — **a global hook inside `testDir` is loaded as
part of the config, and every spec under it then collects as zero tests.**

**The inline/block partition in `uslm.ts` is measured, not remembered** (ADR-0040).
`scripts/inline_elements.py` counts how often each USLM element sits beside a non-whitespace text
node across the committed samples → `docs/verification/inline-elements.json`, and
`tests/uslm.test.ts` walks that artifact asserting nothing it found in prose renders as a `<div>`.
Elements the source uses **both** ways — `note` (30,981 block / 883 inline), `quotedContent` (875 /
2,701) — are in `CONTEXTUAL_TAGS` and decided per occurrence by `inRunningProse(el)`, marked
`.uslm-inlined`. `term` and `quote` do not exist in either schema's samples. The same test runs in
`collectBlocks`, so the redline does not split a sentence at a footnote marker.

**Contrast is computed from the tokens, in both themes** (ADR-0042). `uv run python
scripts/contrast.py` reads the token block out of `site.scss` and writes
`docs/verification/contrast.json` — 18 pairs, 36 checks — exiting non-zero on a failure. It and the
axe scan miss opposite things: the scan cannot see a pair no scanned route renders (**no route carried
a status badge**, so none was ever measured, and dark's was 2.25:1), and a token audit cannot see a
colour that is not a token (**USWDS's `.usa-nav__link` was 2.5:1 on every reader page** below 64em).
`--rule` is split: **`--edge`** bounds controls and is held to 3:1; `--rule` stays decorative and is
reported without a requirement. The list of pairs now lives in
`frontend/src/data/color-pairs.json`, which `/app/design` reads as well (ADR-0053). Two traps, both
hit here: **`.usa-alert`'s background is on
`__body`** (same shape as ADR-0027's footer note), and **a token used for a role it was not defined
for** — `.endpoint__method` took its *text* colour from `--panel`, which inverts, over a fixed
background.

**One navigation chrome, and the release point is a fact rather than an inference** (ADR-0043,
ADR-0044). `docs/ia-map.md` is the map — every reader route, derived from the guide ratchet's own
`readerRoutes()`, with each inbound link recorded as file:line — and it found that **only
`us/usc/[...identifier].astro` passed `crumbs`/`release`/`bar` to `Base`**, so `/app/versions` and
`/app/diff` carried no trail at all. Now: the breadcrumb ends at the provision on screen
(`aria-current="page"`), `SectionBar`'s steps name the neighbour from 40em up, and `ChapterRail`
lists the parent subdivision's sections in reading order with status badges **in place**, so a
repealed neighbour is visible before it is clicked (gotcha 9) — at the cost of the fourth API call
Day 6b dropped, and of showing `structure_nodes`' unversioned view, which the rail says out loud.
`ReleaseContext` replaces `Provenance` and adds what it never stated — **whether this is the newest
release point**; `ReleasePicker` is two GET forms (newest / a date / a named release point, two
because `?release=` beats `?date=` in `resolve_release`) posting to the **requested** identifier,
since building the action from `section.identifier` **dropped the provision anchor** on every switch.
The switcher **left the sticky stack** on a measurement: 19px of headroom under `--sticky-h` at
700px against a date field costing ~80, in the band `docs/backlog.md` already flags for 19rem of
chrome — 89px after the move, asserted in `sticky.spec.ts`. **ADR-0056 puts it back** as a
`<details>`, which answers that measurement rather than overruling it. Two traps: **`Astro.slots.has(name)` is
true for a slot whose content sits behind a false condition**, and **the first non-link text in the
breadcrumb bar inherits USWDS's own ink** (`$theme-breadcrumb-background-color`, light-page
assumption) and failed contrast in dark on every reader page — ADR-0042's `.usa-nav__link` again.

**The hover preview is keyboard-reachable and fails out loud** (ADR-0041, amending ADR-0024's
decision 4). The card no longer carries `aria-hidden="true"` next to `tabindex="0"` — focusable and
hidden from assistive technology at once, which is what ADR-0039's open-state scan found. It is a
`role="dialog"` with a per-reference `aria-label`; **Tab from the trigger moves into it, Escape closes
it and returns focus to the reference without scrolling**, and a dismissal *latches* — otherwise the
focus restore fires `focusin` on the trigger and the card the reader just closed reopens 300 ms later.
A fetch failure renders "Preview unavailable" plus the citation instead of nothing, and a 429 says so
by name; an `AbortError` stays silent, because that is the island superseding its own request.

**The brand is token overrides on USWDS and nothing else** (ADR-0052). Statutory text is **Spectral**,
the interface **Archivo**, monospace the system stack; both faces are Latin-subset WOFF2 in
`frontend/public/fonts`, built by `scripts/fonts.py` from pinned `google/fonts` commits into
`docs/verification/fonts.json` — **six files, 125,720 bytes, 45,872 of it preloaded**, and the build is
byte-reproducible only because the instancer is told to stop stamping the clock into `head.modified`.
The `@font-face` rules are hand-written: USWDS emits one per static weight, which **cannot express a
variable face**, and hard-codes `font-display: fallback`. Cap heights (**343 Archivo, 330 Spectral**)
are read out of the binaries, since USWDS normalises its type scale against them — the unit is cap
height in px at 500px, recovered from the two faces USWDS ships whose declared values match their
files. The palette is indigo `#31509d`, `#90302e` for repeal and error, `--version` `#036639` for
version semantics **and nothing else**, amber for the provision you asked for; `contrast.json` is now
**20 pairs, 40 checks, 0 failures**. Two traps: **USWDS's colour functions take a token name, not a
hex** — `get-color-token-from-bg` hands its result to `color()`, which fails the compile — so the
neutrals are `gray-warm` tokens and only the hues are the proposal's; and **`opacity` on text is a
contrast ratio no token can state** (`.soon__tag` at 0.85 over `--muted` was 4.4:1, invisible to
`contrast.py` and caught by axe). `--measure` replaces the `46rem` written out in five rules: **42rem,
a median 68 characters**, measured by `frontend/scripts/measure.mjs` (`make measure`) rather than
estimated. The face swap alone left line length identical and made pages
slightly **shorter** (§45f at 1280px: Georgia 8,829px → Spectral 8,798px); the narrower column is
what costs the scroll, **8,798 → 9,117, +3.6%**. The focus ring is still USWDS blue: the brand
assigns it the indigo, and `$theme-focus-color` is one compile-time value while the theme is chosen at
runtime.

**The design system has a page, and the page is the regression surface** (ADR-0053). `/app/design`
renders every part the reader is built from — the two faces and their roles, the reading measure,
the palette, the focus ring, the status badges, the breadcrumb and rail, the timeline, the redline,
the copy control, a search result row, and the four messages the site shows when it cannot answer.
Every specimen is the **component**, given specimen data, or the output of the library function that
builds that markup elsewhere; four blocks that were inline in a page became components to make that
true (`Timeline`, `SearchResult`, `NoResults`, `CitationNotFound`). It **reaches no data** — no API
call, no release point — so it renders the same on an empty machine as on the deployed box, which is
what lets `make shots` and the axe matrix treat it as a fixed target; the specimen provision is
under **title 0**, which OLRC does not publish, so its citations resolve to nothing. The contrast
table **computes itself in the browser** from the tokens the page resolved, so it is right in either
theme and reports the colour *in force* rather than the colour declared; the pair list moved to
`frontend/src/data/color-pairs.json` because `frontend/Dockerfile`'s build context is `./frontend`
and nothing under `docs/` exists at image-build time, and `tests/e2e/design.spec.ts` compares every
pair against `contrast.json`. Two defects it rendered into view, both components that were right in
exactly one place: an **unrecognised `@status` fell through to USWDS's `.usa-tag`** — a filled badge
in a colour the palette does not name and `contrast.json` never measured — and
**`.usa-breadcrumb`'s transparent background was scoped to `.contextbar`**, so outside the sticky
chrome the dark trail came back as a white slab; and **`Neighbors` dropped the space between a
section's number and its heading** — `§ 45eViolations of park regulations` on every section page,
because alone inside an element the text node between two expressions does not survive the Astro
compiler. **`WatchButton` is the one component the page does not cover**: accounts are off so it
renders nowhere, and its island calls `/auth/me` on mount, which the page's no-data property and
the test enforcing it will not have.

**The statute is set to a spec, and the spec is measured** (ADR-0054). **The subsection ladder did
not exist**: `--indent-step` reached only the *source's* `indentN` classes, so `(a)`, `(1)` and
`(A)` sat flush at one left edge on every section page. `uslm.ts` now marks every level below the
section root `prov` from its own `LEVEL_TAGS` — the stylesheet names no USLM element — and `.prov`
spends one step of `padding-left` per rung with the `<num>` hanging back into it. **One scale means
the structural one wins on a level**: `.prov` zeroes the source's `margin-left`/`text-indent`, which
were composing with it (§ 45f's subsections started 78px in, and two siblings at one depth sat 25px
apart because the source wrote `indent1` on one and `indent0` on the other). The step is **`1.5em`,
`1em` below 40em** — `em` and not `ch`, because **`.uslm-num` is bold and 3ch of Spectral Bold is
3px wider than 3ch of Spectral**, so every designator hung 3px into the column above. `scripts/ladder.py`
measures what it has to hold into `docs/verification/ladder.json`: **depth 7 at `/us/usc/t16/s1391`,
11 of 11,512 sections, 91.8% within depth 3, median designator 3 characters and 8 at worst**. Inside
the column, **the law is Spectral and everything written about the law is Archivo** — notes, source
credit and tables move to the interface face, and quoted amending text is a `<blockquote>` on a
labelled panel that keeps the reading face, because it is statutory text sitting inside a note that
is not. Tables arrive in a keyboard-reachable region named from their `<caption>`, **766 of which
USLM 2.x writes and which fell through to the `<div>` fallback** — invalid inside a `<table>`, so
the browser hoisted each one out. **`--measure` is `calc(38 * var(--reading-size))`** so the
character count rather than the width is held constant: **median 67, p10–p90 62–71, in both
densities** (`make measure`, which now exits non-zero outside 62–70). The **reading-density control**
(comfortable / compact) is `<html data-density>` stamped by the theme's own pre-paint bootstrap;
**0px of `--sticky-h` at 700/1024/1280** and 56px of header on a phone, where the header is not
sticky. **Print** drops the chrome, keeps the release facts, forces the notes open, and repeats a
running header carrying the citation and the release point; every `<ref>` prints `data-print-url` —
the citation URL, not the reader's `/app` path.

**Inside a section there is now somewhere to go, and one keyboard map for the site** (ADR-0055).
The ladder had reached the reading column and not the hover card, where ADR-0054's global
`.firstIndent-N` still pulled a first line two steps left with no padding to spend — so `(a)`,
`(b)` and `(c)` rendered **outside the card's padding box on `/us/usc/t16/s1391` and its
`overflow-y: auto` clipped them**, invisible, every line under them short its first character. The
ladder selectors are shared with `.cite-preview__body` and the card sets its **own
`--indent-step: 1em`**; halving the variable halves `firstIndent-N` too, which the
`[class*="indent"]` override it replaces could not do. Above the text, `SectionContents` renders
**`uslm.outline()`** — top-level provisions with their headings, then the source credit and the
notes. Provisions need no new anchor (`@identifier` is already their `id`); the apparatus does, so
**`RenderOptions.anchors` is opt-in and used once per document** — the section, a further
occurrence under one identifier (ADR-0021) and the hover card all render this markup into one page
and only the first may claim `#section-source`/`#section-notes`. The **section bar's number links
to `#main`**, because nothing new may be pinned: `--sticky-h` is what `scroll-margin-top` spends.
`KeyboardNav` moved into `Base` and binds `t b c [ ] s n / ?` on top of `←/j →/k u`, all of it from
**`lib/shortcuts.ts`**, which the dialog renders, `/app/design` renders as a panel, and the island
receives as JSON — an `is:inline` script imports nothing, so a binding written in the script would
be a second copy of the printed one. The help is a modal `<dialog>`. Two costs: **every route pays
3,678 more bytes of inline script** (`/app/` 9,000 → 13,000, `/app/us/usc` 34,500 → 37,500), which
is why that island's rationale is in its frontmatter docstring — written beside the code it was
6,500 a route; and **`j` is previous and `k` is next**, the reverse of the convention, now printed
on every page rather than in one sentence, left as ADR-0038's guide and `guide.spec.ts` already
have it.

**The release switcher is back in the sticky bar, as a disclosure** (ADR-0056, amending ADR-0044).
ADR-0044 had put the controls in the page body on a measurement — 19px of headroom under
`--sticky-h` at 700px against a date field costing ~80 — and the cost was the release point written
twice on every section page and ~180px of controls above the statute whether or not the reader
meant to move in time. `ReleasePicker` is now a `<details>` in `.contextbar` whose **closed summary
is the line the bar already carried**, so the stack is the height it was, and whose panel is
`position: absolute`, so opening it moves nothing — asserted at 700px and 1280px in
`sticky.spec.ts`, which measures `.contextbar`'s box open against closed. Native `<details>`, so it
costs no script and the two GET forms are unchanged. Two traps: **USWDS gives `.usa-button`
`width: 100%` below 480px**, which at 320px took the whole row and squeezed the release menu beside
it to nothing; and below 30em `.topbar` is `display: contents`, so a panel positioned against
anything but `.rpswitch` itself has no containing block short of the viewport and `top: 100%` puts
it a screen height down the document. `b` joins the keyboard map — the `<footer>` with
`block: "end"`, the counterpart to `t`'s `#main` — and the scenario vocabulary gains
`expect: { inViewport: true }`, since `visible` is true of an element a screen below the fold.
**The guide's chapter list is pinned and scrolls on its own**, the ADR-0050 arrangement, at an
offset of its own: `--sticky-h` is a scroll-margin budget rounded up over the tallest chrome a
*section* page carries, and a guide page's sticky chrome **measures 124px** at 1024/1280/1440
(`.topbar` alone), so honouring 19rem as a `top` offset started the list 180px below the bar — the
reason the rule there had read "not sticky, deliberately".

**The site menus collapse into a hamburger below 64em** (ADR-0058, amending ADR-0011). `SiteHeader`
argued the other way — "a menu you must tap to see is worse than four links you can already read" —
when there were four links; there are seven, and nine in the footer, and measured on
`/us/usc/t16/s45f` that was **416px of header and 326px of footer nav at 375px** on an 812px screen.
Both are now a native `<details>`, the disclosure ADR-0056 chose for the release switcher, so it
still costs no script and `<summary>` carries its own expanded state. The header's panel is
`position: absolute` — the header is sticky between 40em and 64em, so a panel in flow would be
`--sticky-h` growing while it is open — and the footer's is in flow, since nothing down there is
pinned; the disclaimer stays outside the disclosure. From 64em up the summary is hidden and
**`::details-content` is forced visible**, which is the only way to reach a closed `<details>`'s
content, with an `@supports not selector(::details-content)` fallback that leaves the hamburger
rather than leaving the nav unreachable. **`--sticky-h` drops 25rem → 23rem** in the 40em band
(sticky stack 393 → 241px at 640, 337 → 241 at 700; header 416 → 232 at 375, 216 → 120 at 700).
Three traps: **USWDS's `*, ::before, ::after { box-sizing: inherit }` matches no pseudo-element**, so
`::details-content` broke the chain, every link inherited `content-box`, and USWDS's `height: 100%`
on `.usa-nav__link` made that **28px of extra desktop header** — at widths that never see the
hamburger; **USWDS's small-width `.usa-nav` is a centred flex *column***, so overriding it with
`display: flex` alone stacked the chrome and read `.navtools`' 16rem `flex-basis` as a height; and
**a flex line breaks on the sum of its items' hypothetical sizes, before any of them shrinks**, so
the search box's 14rem of basis wrapped the chrome's row from 640 to 690 and left 1px of slack at
700 — passing here and failing in CI, where the scrollbar is 15px of the viewport. `flex-basis:
0` in the band removes the search box from the wrap calculation entirely — only the `flex: none`
controls count — and `flex-grow` still hands the box everything left over (ADR-0058's addendum).
**The row still did not fit, and what wrapped was inside the search box rather than the row**
(ADR-0059): at 640 the box got 166px against the 164px its own label needs, so in CI "Search or go
to a citation" ran to a second line and the header grew 11.5px — the density control costing
`--sticky-h` after all. The two toggles now **keep their icons and drop their words below 64em**,
which returns ~130px (box 166 → 302 at 640, header 232 → 176 at 375), and their accessible names
were already written by their own islands. Two traps: **`.density-toggle__label`'s base
`display: inline-block` is later in `site.scss` than the 40–64em rules**, and a media query adds no
specificity, so the override has to sit beside it; and **a layout with 2px of slack passes on macOS
and fails on Linux** — `.authnav` is 149px here and 154 there. The
same session: a search result leads with its citation (`resultCitation` in `lib/cite.ts` — `16
U.S.C. § 3831`, or `Title 16, CHAPTER 1—` for a structural node), and the redline's top line is the
result alone — `No changes`, or `2 lines added` — with the `sourceDelta` prose replaced by one line
under it linking the source redline, and shown only when the stored XML actually differs.

**The Source and Notes disclosures toggle, and look like they do** (ADR-0060). They could not: the
rule forcing `.uslm-details::details-content` visible from 40em up wins over the element's own state,
so on every desktop reader the summary flipped `open` and **changed nothing on screen** — and there
was no caret either, since a `<summary>` draws its marker on a `display: list-item` box and this one
is `display: flex` for the touch target. The summary is now a chip on `.rpswitch__summary`'s terms —
box, `▾`/`▴`, hover fill, focus ring — and `ApparatusDisclosure.astro` sets `open` at 40em and up,
stamps `data-apparatus="live"` and thereby retires the override, which is now
`html:not([data-apparatus="live"])`: CSS cannot default a `<details>` open by viewport, because the
open state is an attribute and one cached document is served to every width. Both paints show the
same thing, so nothing flashes, and scripting-off keeps the old behaviour. `c`, `n` and a fragment
jump open what they land on. **A card's fragment arrives after that script has run**, so
`CitePreview` opens the disclosures it injects — without it a preview of a repealed section (often
nothing but apparatus) was a shut box whose first focusable sat inside `content-visibility: hidden`,
where `.focus()` silently does nothing and ADR-0041's Tab-into-the-card stopped dead.

**Below 64em the header is a bar and a search row** (ADR-0064). `.navbar` is 52px — Menu, the site's
name, the light/dark switch — and `display: contents` from 64em up, where its three children are
items of the row ADR-0061 built, so the desktop header is untouched. The one search box has a
full-width row under the bar and is on screen without opening anything, which **retires ADR-0058's
`flex-basis` addendum and the two band-scoped bases it left**: those were about a row the box
*shared*. **More is not a disclosure there** — its summary is `display: none` and its
`::details-content` forced visible, `.navmenu`'s desktop arrangement run the other way round — so the
sheet reads Titles, My Provisions, REFERENCE, HELP, DISPLAY, Accounts, the group labels serving as
the dividers. **The wordmark is written twice**, one copy displayed per band: it must precede the
menu at desktop and follow it on the bar, so no single DOM gives both bands a tab order matching the
reading order, and `order` on a flex item is what ADR-0061 decision 4 refused. `display: contents` on
the `<nav>` would have reached the same layout and was rejected because **whether a boxless landmark
survives in the platform accessibility tree is not checkable here** — `page.accessibility` is gone
from Playwright and axe computes landmarks from the DOM. `ThemeToggle` renders twice and **ships its
script once, from the later instance**, binding every `[data-theme-toggle]`; the theme is therefore
reachable twice below 64em, which is what the spec asks and what ADR-0064 records as its cost.
Header **148 → 104px at 320**, unchanged at 375–1023, bar 52px, sticky stack back to ADR-0061's
**225px** (`make mobilebar` → `docs/verification/mobilebar.json`) after the first draft's half-rem
paddings measured 233 and `sticky.spec.ts`'s 60px of headroom refused it. Two traps: **`.navdrop__summary`'s
`width: 100%` plus 2rem of side padding was 32px wider than the sheet holding it** — ADR-0061's
`content-box` `<summary>` in a horizontal form — which drew the Titles caret past the right edge of a
panel that clips, invisible on every narrow window; and `:root[data-theme="dark"] a` at 0-2-1 took
the bar's wordmark blue, the third component to need the three-class count.

**A dead end says where else to go** (ADR-0065). A 404 offered the front page and nothing else; it
now offers the nearest identifier above the failed one that resolves, with the trail to it —
`ancestorIdentifiers()` walks up and stops at the title, and nothing is offered when nothing above
resolves either. An identifier absent at a release point without being repealed (gotcha 3) reads
like a typo, so when `/versions` knows it the page says at how many release points it *is* in the
Code and from which to which. The appendix explanation moved from one surface to both: `5 U.S.C.
App. 3` parses to `/us/usc/t5a/s3` and OLRC publishes nothing there, and `_appendix_hint()` is now
named from the identifier so `/api/v1/citation` and the identifier lookup give one answer, naming
**both** real forms. And a shed `/app/diff/` was `text/plain` with no chrome — a navigation is now
rewritten to `/app/429` **at the URL it asked for**, while a fetch still gets the text body
`CitePreview` reads by status. **No search box on the error page**: there is one on this site and it
is in the chrome at every width, and a second would duplicate the `site-q` id `/` reaches by. The
**redirects table gotcha 3 suggests is declined** — OLRC publishes no machine-readable map from a
vanished identifier to where its subject matter went, and one populated by guessing would send a
reader silently to the wrong provision.

**Comparing is one click, and the API stopped diffing the guids** (ADR-0066). `CompareWith` is a
`<details>` on every section header: one named comparison plus a `<select>` of every older release
point, as a link and a GET form. The default is **not** the previous release point — the Code
republishes every title at every one, so that redline is usually empty — but the last release point
that held *different* text, read off the section's version timeline. **Not `content_first_seen`**,
which does not mean what it is called: § 45f's newest group reports `first_seen: 119-99` while its
own `releases` run from `117-80`, because the field follows the stored fragment's `first_release_id`
and an incremental load can attach an earlier release without lowering it. `?at=/c/5` rides through
both routes, `ReadingBlock` carries the `@identifier` of the nearest enclosing element, and the
redline **marks that run inside the whole section** with a line above saying how much of the change
is in it — including when the answer is none. The API diff drops `@id` by default (`?guids=keep`
restores ADR-0016's verbatim contract, tested by reassembling both sides byte for byte) and memoises
on the resolved pair when both are pinned: `make diffcost` → **§ 1536 4,063.9 ms → 1.8 ms, § 668dd
3,216.1 → 7.2, 399 ops → 3**, not a constant factor because diff-match-patch short-circuits on a
common prefix. Two consequences of making comparisons ordinary: the reader's diff limiter goes
**8/0.5s → 20/1s**, and the tests that empty that bucket moved to a Playwright project of their own
that runs last, because the bucket is global and every worker shares one address.

`make test` = **795** Python tests; `make test-web` = **404** frontend tests; `make test-e2e` = **627**
Playwright tests, 322 of which are the accessibility scan (**all three are required** — reader
coverage lives in Vitest since Jinja retired), and
**CI runs all three on every push** (`.github/workflows/ci.yml`, Postgres service container, offline
fixtures via `make ci-data`, `USC_REQUIRE_INTEGRATION=1` so a misconfigured job can't go green having run
nothing).

**Session history lives in [BUILDLOG.md](BUILDLOG.md)** — one entry per session, and in `docs/adr/`
(72 ADRs, numbered to 0073 — there is no ADR-0048). Read the entry you need rather than assuming; this file deliberately no longer restates them.

**Deployed** to one EC2 box at `uscode.linkedlegislation.org` (ADR-0020 + ADR-0035): images built by
Actions on arm64 and pushed to ECR, deploys by SSM, corpus seeded by `pg_restore` from the mirror.
**The source is polled daily and every poll is recorded** (ADR-0036): `python -m ingest check` writes a
`source_checks` row whether it succeeds or fails, runs the full load chain only when OLRC has published
something new, and `GET /api/v1/status` and `/app/releases` say when the site last looked — a mirror
that has stopped updating is otherwise indistinguishable from one with nothing to update. A weekly
`--force` sweep from Actions is the backstop. **The whole site is `Disallow: /` to crawlers**
(ADR-0037) — served from the Caddyfile, because `robots.txt` belongs to the host and one Caddy owns
it; blunt on purpose while the site is a demo, after two AI crawlers walking the `?release=` axis
(25M reader pages behind it) pinned the box at 43,068 requests/hour against ~48 human ones. A
Caddyfile change only reaches the running proxy because `deploy-on-box.sh` **force-recreates** it:
the file is a single-file bind mount, which binds an inode, so `caddy reload` would reload the
pre-`git checkout` file and exit 0. **The site went down for ten hours under six green alarms, and now something asks whether it
answers** (ADR-0073). Meta's `meta-externalagent` walked the `?release=` axis — 7,155 of 7,172
requests in an hour over ~60 addresses in `57.141.0.0/24`, having fetched `/robots.txt` 21 times in
24 hours and read `Disallow: /` — and the pages it asked for were never slow (0.3–1.0s). What made
it an outage is that **all fifteen pooled connections ended up `idle in transaction` on
`ClientRead`**: FastAPI closes a dependency's session after the response is sent, so a response that
is never sent is a session that is never closed, and Postgres holds that state forever — so it did
**not** recover when the load eased. Every alarm was a resource tripwire and the outage used no
resource (load average 0.73, 2.1% api CPU, 0.0% Postgres); the api container's own healthcheck had a
failing streak of **2,710** and a Docker healthcheck's only effect is a word in `docker ps`. Now:
declared crawlers get **403 at the proxy** (enforcement of ADR-0037's policy, not a new one — and
ADR-0029's per-caller limits would never have fired at two requests a minute per address);
`storage/session.py` sets `statement_timeout` 20s and `idle_in_transaction_session_timeout` 30s
**per transaction**, via an `after_begin` listener on a sessionmaker of storage's own, because
**ingest shares `db/base.py` in its own process and must stay unbounded** and because **applying the
bounds at session construction makes every early-rejected request need a database**
(`tests/test_rate_limit.py` caught that); the pool is 10+20 with `pool_pre_ping` and
`pool_timeout` **30s → 2s**, so it sheds rather than queues; uvicorn carries `--limit-concurrency 64`
and Caddy `dial_timeout`/`response_header_timeout` on both upstreams. **`deploy/watchdog.sh`** runs
every minute, probes both surfaces through the proxy, publishes `USCode/SiteUp` and restarts the HTTP
services after three failures — deploy lock first, ten-minute cooldown — and `uscode-site-down`
treats **missing data as breaching**, since a box too wedged to run cron publishes nothing.

**Live state and what is still owed are in
[docs/deploy-status.md](docs/deploy-status.md)** — read that before touching the deployment.

**The search ranking is measured rather than asserted** (ADR-0049). `docs/verification/search-judgements.json`
is 37 drafter queries and 529 graded documents, pooled from every candidate profile before grading;
`uv run python scripts/search_eval.py score` writes `docs/verification/search-relevance.json`.
nDCG@10 went **0.6894 → 0.7159** and recall@10 **0.7672 → 0.8016**. The old heading weight was
**4, not the 2 its own query said** — a deprecated index-time `boost: 2.0` in the mapping multiplies
with the query-time weight rather than replacing it. The query gains six scopes — `heading:`,
`title:`, `chapter:`, `status:`, `release:`, `date:` — **lifted out before the cluster sees them**,
since `query_string` (the parser that understands them natively) throws on malformed input and
ADR-0031 refused that. Facets **edit the query** rather than sitting beside it, so a filtered search
is citable by its URL alone; `?sort=` offers relevance, citation order and most-recently-amended.
The `all-versions` profile **scored highest and was declined** — it changes what a result is — so
the default still reads the text in force and reports the rest as "also matched in N earlier
versions". Two counting defects fixed: `hits.total` was capped at OpenSearch's default 10,000, and
under collapse it counted versions while the page listed sections. **The mapping is not additive, so
the deploy rebuilds the index itself** (ADR-0051): `SECTIONS_INDEX`/`STRUCTURE_INDEX` are now
**aliases** over a physical index named for its mapping's fingerprint, `reindex_search --if-changed`
rebuilds only what drifted and **builds beside the live index rather than over it**, and
`deploy-on-box.sh` runs it. The failure this prevents is silent: a field the new code queries and
the old index lacks is *absent, not broken*, so `title:16` returns an empty page that looks exactly
like a title with nothing in it.
**The chapter rail is pinned and scrolls on its own** (ADR-0050, reversing ADR-0043's standing
decision): bounding the height is the half the first attempt was missing.

**The menu refinement is three quarters done** (`docs/menu-refinement-spec.md`). The header is four
items with two `<details>` dropdowns and the first script the chrome has carried (ADR-0061); the one
search box is also a ⌘K command palette (ADR-0062); the footer's nine links are four labelled groups
(ADR-0063). `--sticky-h` drops with the header — 23rem → 18rem in the 40–64em band, 19rem → 15rem
above it, each measured against a stack of 225px and 168px. **B9 — the mobile chrome — landed as
ADR-0064**, described above, which completes the spec.

**Workstream B is complete.** B5, B6 and B11 landed together (ADR-0065, ADR-0066); state and
standing decisions are in `claude-code/WORKSTREAM-B-STATE.md`.

**The classification tables are built** (`docs/classification-spec.md`, ADR-0067).
OLRC's tables record which provision of which Public Law was classified to which Code section.
Waves 1, 2 and 3 are **merged** (PRs #44, #45, #46) — the parser, the four tables
(`classification_files`, `classification_entries`, `ecct_entries`,
`classification_source_checks`, migrations `3c8d9ab6d527` and `0044883c483c`), the fetch, the
loader, the poll, the `classification` / `classification-check` subcommands, the storage protocol,
eight API routes under `/api/v1/classifications` and three reader routes under
`/app/classification`. **Wave 4 is PR #47** on `c5-classification-chrome`: the chrome links, guide
chapter 10, the `/app/design` specimens, `docs/ia-map.md`'s three rows and the `update-corpus.sh`
poll wiring.
**The whole corpus is loaded from the live source in both places** — the development box and the
deployed one: **144,837 rows across 31 Public Law order tables plus 21 ECCT rows, 33 documents, 0
failed, ~110 seconds from cold** (`docs/verification/classification-*.json`, one artifact per
document). The deployed box holds those rows and answers 404 for every route that would show them
until the next deploy carries Wave 3's reader (`docs/deploy-status.md`). **The first full-corpus parse found four
defects in the 28 vintages Wave 1 never measured** — a Sec. column one character left of its own
header in two files, a Stat. page numbered with a letter (`113 Stat. 1501A-594`), a row OLRC has
corrected carrying an asterisk that shifts every later column, and a page butted straight against
its Sec. designator — all fixed, and the reason a boundary is now checked against the file's own
rows rather than trusted from the header alone (ADR-0067's addendum). **The lookup is
table-scopable (ADR-0068)**: `suggest` takes `congress`+`session`, under which a bare law number
means a law of that congress and a citation's first answer counts that section's rows in the scoped
table; each session page carries the box scoped to itself (finding a row there was otherwise up to
118 page turns), and the index's box offers the scope as a `<select>` (`?scope=118-2`).
**Every table of rows sorts both ways and pages by number (ADR-0071)**: one vocabulary —
`pl`, `pl-desc`, `code`, `code-desc` — on every classification listing route and reported in every
response, with two defaults (a session page is the document as published, a by-code view is a
history) each omitted from its own URL, so every URL that worked before still names the same view. A
descending order is the ascending list **reversed** rather than a second comparator, because these
rows have ties. The sort bar's option in force is a link that reverses it and the headings of the
**U.S. Code** and **Pub. L.** columns are the same control (`aria-sort`); the other three hold the
source's own notation and order nothing. `Pager.astro` is one control for every paged list —
search results and both classification views — with page N of M, the two ends always reachable, a
window of two either side and a **Go to page** form where the numbers cannot reach every page, which
is why **`?page=` exists beside `?offset=`** (`?offset=` stays canonical and wins). The arithmetic is
`lib/pager.ts` and is tested in Vitest at the corpus's own sizes, because **the CI fixture corpus's
largest classification table is 84 rows** — two pages — and no browser test can reach a window, a gap
or a jump box; `/app/design` renders a 235-page specimen so the axe matrix and `make shots` can. Two
traps, both ADR-0042's shape: **`:root[data-theme="dark"] a` is 0-2-1** and beat
`.sortbar__option--on`'s single class the moment that option became a link, painting the pill's text
in the dark link blue on a light blue fill; and **USWDS paints `th[aria-sort]` a fixed `#97d4ea`**,
applying it to `aria-sort="none"` as well, in the light theme only. A third is left open:
**`a { color: var(--link) }` is declared inside the dark block alone**, so an ordinary link in the
light theme is the browser's `#0000EE` outside the statutory text.

**A title is a query and a section's public laws are always an offer (ADR-0070)**: `15 usc` and
`title 15` — `citeparse`'s `kind="title"`, which the endpoint used to drop — lead to every row
classified to that title (`/app/classification?title=15`, over the new
`GET /api/v1/classifications/code/{title_num}` and `entries_for_title`), led by the rows in the
scoped table where there is a scope; and a citation offers the section's notes *and* the rows the
tables hold against it whenever either the section or a row exists, since the empty answer is the
one a provision last amended before 1996 has. Both by-code views say the tables begin at the 104th
Congress, and the section view links the notes at `#section-notes` — resolved through
`/api/v1/citation`, because an identifier assembled from the table's hyphen 404s for the 3,398 the
corpus spells with an EN DASH. **Choosing a table loads it, and the box on a table filters it (ADR-0072,
amending ADR-0068)**: the index's `<select>` is a chooser rather than a suggest scope — `?scope=`
is a 302 to that table carrying whatever is typed — and a `?q=` submitted on a session page that
names rows in a table is applied as a filter rather than listed above it
(`classificationTableFilterHref`; the three kinds that do not name rows in a table are still
listed). The U.S. Code column previews on hover, which is why both routes' JS budget went
24,000 → 36,000. Two traps: **a GET form posts its own fields and nothing else**, so `?sort=code`
was dropped on every submission until the order became a hidden field; and **Firefox fires
`change` on every arrow key in a `<select>`**, so the chooser submits for a pointer only and the
keyboard commits with `Enter`. Sizes: **title 10 carries 23,093 of the 144,837 rows, title 42
19,476, title 15 4,495**, against a longest section history of 412. What remains unbuilt by choice:
a section page shows no classification rows, so the link runs one way; and the poll cannot see a
change to the ECCT alone. (The title view's `sort=code` is built — ADR-0071.)

**Next: (1) Day 7 hardening — part of it landed as ADR-0073 under an outage, and what it did not
cover is the load test below; (2) `docs/verification/loadtest.json` has never been regenerated
against the deployed box and is now stale for `/app/diff` three times over — ADR-0026 moved the
reader off the endpoint, ADR-0066 made the endpoint 150-2,000x cheaper, and the reader's own limiter
changed — and it now also predates ADR-0073's pool, concurrency cap and proxy timeouts, which are
exactly what a load test would measure; (3) the remaining accessibility tasks A4, A9 and A10.**

Open debts: **the source's `indentUp0/1/2/3`, `indentDown1/2`, `indentTo54pts`,
`indentTo65ptsHang`, `indent0And43pts` and `rightIndent1` classes are styled by nothing** — 8,733
occurrences across the committed samples, all inside notes and tables. `[class*="indent"]` used to
give each of them exactly one step, which was wrong for all of them; naming the levels leaves them
unstyled rather than wrongly styled (ADR-0054's recorded cost), and reading them properly is its own
task. **A headed level still breaks after its heading** — `(a) In general` then the text below,
where the printed Code runs the two together: USLM 1.x writes no separator and 2.x writes
`<inline class="noSmallCaps">.—</inline>` inside the heading, so running them in needs the renderer
to tell those cases apart. **`j` is previous and `k` is next**, which is the reverse of the
convention every reader who knows those keys has; it is what the guide documents and
`guide.spec.ts` asserts, and ADR-0055 left it rather than flipping a documented binding unasked.
**`/app/settings` is reachable from no rendered page** — `AuthNav` is its only linker and
`SiteHeader` does not render `AuthNav` while accounts are off (ADR-0034), so guide chapter 06's prose
link is the only way in (`docs/ia-map.md`); **the reader's own measured WCAG 2.1 AA failures are cleared** (ADR-0039, ADR-0042) —
`docs/verification/a11y.json` is **8 route/rule pairs over 2,903 nodes**, down from 41 pairs, and
every one that remains is `docs/a11y/known-violations.json`'s: the vendored Swagger UI / ReDoc bundles
(ADR-0032, owned as published exceptions), two scrollable regions with no keyboard route in, and
`html-has-lang` on `/docs` and `/redoc`, which is ours — the shells come from `main.py` — all owned by
A4 or A10. **The gate is weaker than specified**: A1 asked that serious/critical fail regardless of the
known list, which would have landed the harness red, so `waiveSeverity` lets a dated, owner-signed line
through — recorded as ADR-0039's cost. **`docs/a11y/manual-protocol.md` does not exist** (task A9), so
the half of WCAG 2.1 AA axe cannot see is unmeasured, and **no conformance statement is published**
(task A10). **the rate limiters are per-process state**, honest for ADR-0020's single box and wrong for a second instance (ADR-0029's recorded cost); **the CSP carries `script-src 'unsafe-inline'`** until the islands get nonces through the new Astro middleware (ADR-0030's recorded cost); **no email verification and no password reset — accounts are throwaway until email exists, decided and recorded in ADR-0019** rather than left as a gap; `docs/verification/loadtest.json` has never been regenerated against the deployed site, and it now also predates ADR-0037's `Disallow: /`, so any future run measures a site nothing is crawling (`docs/deploy-status.md`); **nothing in this deployment can verify its own S3 retention rules** — the `usc/db/` lifecycle rules exist (created in the console 2026-08-03; the dump itself is no longer nightly, it runs from `update-corpus.sh` gated on `load-all` having actually loaded something), but `s3:GetLifecycleConfiguration` is denied to every credential here, so that is the one claim in `docs/deploy-status.md` resting on a console screenshot rather than a re-runnable command. `deploy/mirror-lifecycle.sh` is the reproducible version and needs a temporary grant (`deploy/mirror-lifecycle-bootstrap-policy.json`) to run; the box deliberately cannot do any of it, since the instance role has `s3:PutObject` on `usc/*` and no `s3:DeleteObject`; **appendix titles are unreachable by citation** — `5 U.S.C. App. 3` parses to `/us/usc/t5a/s3` and OLRC publishes nothing there (0 of 461 appendix sections use the flat form; they are `/us/usc/t5a/pl/92/463/s1` or `/us/usc/t50a/act/1917-05-18/ch15/s212`), so the API explains rather than 404s; the preview endpoint is unauthenticated and fans out per hovered citation — **now rate-limited in `frontend/src/middleware.ts` (ADR-0029)**, still unauthenticated, though a 429 now degrades to a visible "Preview unavailable" card with the citation rather than nothing (ADR-0041); **the reader's redline drops `<ref>` links and cannot see a whitespace-only change** (ADR-0026's named costs); **the deployed search index is complete — 489,578 documents, 65,929 current and 423,649 superseded (`docs/deploy-status.md`, built 2026-08-02), so `?release=` search does reach back through superseded text**; a *local* index is whatever you last built (`python -m ingest.reindex_search --recreate` for the 66k current-text index the default query reads, `--all-versions` additively for the 490k superseded ones), and the response names the release it searched, so which one you got is visible. `/app/search/syntax` claimed the current-text-only limit for a fortnight after it stopped being true, which is what ADR-0038 exists to prevent; the search endpoint is unauthenticated — **now throttled and input-bounded (ADR-0029)**; **a section the source publishes twice under one identifier at one release (ADR-0021) shares an OpenSearch `_id`**, so the index keeps one of the two — measured at **160 (identifier, release) pairs across 49 identifiers in 14 titles**, and now flagged on the document and said on the result row (ADR-0049); **a rebuild concurrent with a corpus load is unguarded** — an incremental load during an ADR-0051 rebuild writes through the alias to the outgoing index and those writes are lost at promotion; the poll is daily and a deploy is minutes, and the fix is a lock nobody has written; **`?sort=citation` puts every chapter and subchapter heading of a title ahead of every section of it** rather than each before the sections it contains, because structure nodes have no `seq_in_title` (ADR-0049's named cost, said in the guide); **the ranking cannot favour a provision whose heading does not carry the words** — FOIA is `Public information; agency rules, opinions, orders, records, and proceedings`, and every one of the six worst-scoring judgement queries is that shape; the diff endpoint is CPU-bound — ~0.45 rps at any concurrency, failing entirely past ~10 concurrent — and is **now rate-limited (ADR-0029, the tightest budget in the project)**, so it sheds with 429 + `Retry-After` rather than collapsing; `docs/verification/loadtest.json` predates that and has not been regenerated; **~half the API diff's cost is `@id` churn rather than legal change** — diffing the guid-stripped text is 2,220 ms → 1,172 ms and 51 → 20 ops; the *reader* no longer pays it (ADR-0026 moved the reader to a text redline), the endpoint still does, and `docs/verification/loadtest.json` is stale for `/app/diff` as a result; **accounts and bulk downloads are switched off in the reader but their API routes are untouched** — ADR-0034 is a UI decision, so `POST /api/v1/auth/signup` still works for a direct caller; **the copy column adds ~100 tab stops to a long section** and its copied text drops notes and `sourceCredit` (ADR-0033's named costs); **link mode has no plain-text fallback** — if the `ClipboardItem` write throws (older Firefox, plain HTTP on a non-localhost host) the reader is told "Could not copy" and gets nothing, where the bare URL would still be useful (BUILDLOG 034, raised and left unchanged); **the labels batching has no end-to-end test** because CI's fixture corpus tops out at 75 cross references (16 U.S.C. § 1801) against a bound of 100, so an e2e assertion would pass with or without the fix — real cover needs a denser fixture title in `make ci-data` (BUILDLOG 034); **2.4 MB of vendored Swagger UI / ReDoc is committed**, so a security fix in either arrives only when someone bumps `static/apidocs/MANIFEST.json` (ADR-0032's named cost); **HEAD is 405 on every `/api/v1` route** (FastAPI registers GET alone), which matters once a CDN or uptime monitor is in front; `purge_login_failures` is now on a weekly cron on the deployed box but nothing calls it in dev; **the general `/api/v1/watchlists` multi-list CRUD has no frontend UI** (only the default-list convenience endpoints the reader uses are wired to a page); a deduped fragment carries the guids of the release its text first appeared at (ADR-0007's recorded cost); `structure_nodes` is unversioned — one row per node, holding **the newest loaded release's view**; `first_release_id`/`last_release_id` bound its life, and both those and the descriptive fields are gated on `seq`, so load order doesn't decide the answer (an older load silently relabelled a `reserved` subchapter `repealed` before that gate existed). Per-release structural history is still owed; **the source sometimes publishes several elements under one `@identifier` at one release point — the reader shows every occurrence with a note rather than picking one (ADR-0021), and `sections_loaded` therefore exceeds `section_release_map` on six title-releases**; `Uslm2Parser` has no table/indent handling (Day 7); `make verify` is real (ADR-0014) and `--deep` has now been run over the whole corpus — **3,153 of 3,153 title-versions independently recounted from source, 0 source mismatches, 0 incomplete loads** (`docs/verification/database.json`); the six count mismatches it reports are the source publishing several elements under one `@identifier` (ADR-0021), left reported rather than smoothed away. **Test speed rule:** default `make test` never parses the 32 MB usc16.xml — unit tests use `tests/fixtures/usc16_slice.xml` (regenerate with `make fixtures`); full-sample tests are `@pytest.mark.slow`, run by `make test-slow`. API integration tests need a loaded database (`make dev-data`) and skip without one.

## Architecture rules (PLAN §2)

1. **API and UI talk only to the `Repository` interface** (`storage/repository.py`) —
   `resolve_release(...)`, `get_section(identifier, release)`, `get_toc(...)`, `resolve_id(...)`,
   `neighbors(...)`, `versions(...)`, `list_releases(...)`. Postgres is implementation v1
   (`storage/postgres.py`, the only SQL in the project); XCiteDB becomes a second implementation
   with no API/UI changes. **No raw SQL in API handlers**, and nothing version-resolution-related
   outside the Repository. `api/` holds no database session either — `storage.get_repository` is
   the FastAPI dependency. `tests/test_architecture.py` enforces all of this; ingest is
   deliberately on the other side of the boundary and writes `db/` models directly.
2. **The ingest layer is schema-plural.** A `UslmParser` protocol with `Uslm1Parser` and
   `Uslm2Parser`, selected by `detect_uslm_version(file)` — **the root namespace URI decides**
   (`xml.house.gov/schemas/uslm/1.0` → 1.x, `schemas.gpo.gov/xml/uslm` → 2.x); `xsi:schemaLocation`
   only labels the point version (ADR-0004). Both emit the same normalized `SectionRecord`
   (identifier, guid, temporalId, num, heading, status, seq, raw XML fragment, source credit,
   notes, guid_refs, ancestors). **Never hard-code USLM element paths outside a parser
   implementation** — `StreamingSectionParser` shares the traversal but knows no element names of
   its own; each parser supplies an `ElementNames` vocabulary. Downstream layers are
   schema-agnostic; `schema_version` rides along so original XML is always returnable verbatim.
3. **Sections are the storage atom** (ADR-0001). Sub-section provisions (`/c/5`) are extracted from
   the section XML at request time via lxml XPath on `@identifier`, returning the whole section with
   the target anchored/highlighted — the reader always keeps context.
4. **Layout:** `ingest/` (fetch RPs, parse USLM, split into sections) → `storage/` (Postgres +
   repository interface) ← `api/` (FastAPI resolver, auth, watchlist) ← `frontend/` (the Astro
   reader, over HTTP only). Top-level `main.py` composes the app, `params.py` holds what the
   surfaces share, `citation.py` is the redirector.
5. **Reader and API separated; the citation URL redirects (ADR-0010, amends ADR-0009 — done,
   BUILDLOG 014).** Reader at `/app/us/usc/…` (always HTML, no negotiation), API at
   `/api/v1/us/usc/…` (JSON default, `?format=xml` verbatim; no Jinja imports under `api/`), and
   the bare citation URL `/us/usc/…` a thin redirector — 307 to `/app` for HTML-winning `Accept:`,
   307 to `/api/v1` otherwise, `?format=` wins, `Vary: Accept`, query string copied through
   verbatim. The app is assembled in top-level **`main.py`** (`uvicorn main:app`), the only module
   that imports both surfaces; the HTTP helpers they share — `?release`/`?date`/`?format`, release
   resolution, `Accept:` parsing — live in top-level **`params.py`**, and the redirector in
   **`citation.py`**. `tests/test_architecture.py` enforces it: **no Python module imports a
   template engine**, which is the strongest form of the rule and true since the Jinja reader
   retired. The reader is Astro 5 + TypeScript + USWDS in `frontend/` (ADR-0011, accepted),
   consuming `/api/v1` over HTTP and nothing else; one Caddy (`deploy/Caddyfile`) owns :8000 and
   routes `/app/*` to it, everything else to FastAPI on :8001 (ADR-0015). Every reader href goes
   through `frontend/src/lib/url.ts` — `/app` is spelled out once. Presentation — the sole place
   outside the parsers allowed to know USLM element names — is `frontend/src/lib/uslm.ts`.

## Identifier semantics (PLAN §1, ADR-0003) — the thing most likely to be gotten wrong

| Attribute | Meaning | Use for |
|---|---|---|
| `@identifier` | Logical path `/us/usc/t16/s45f/c/5`. **Cross-release identity.** Stable across RPs *unless renumbered*. | Primary key for the URL scheme; joining a provision to itself over time |
| `@id` (guid) | `id0b32dff7-810c-11f1-…`. **Pins (provision, release point)** — regenerated at every RP *by design*, and that pair is globally unique. | Global `guid_map` index; `?id=` lookup needs no release param; stable "this exact text at this exact time" citation |
| `@temporalId` | `s1201_a_1_A`. **Not guaranteed unique.** | Display only — never a key |
| `@status` | `repealed` / `omitted` / `transferred` / `reserved` | Must stay retrievable and badged in UI |

A guid is never a cross-release identity — that is `@identifier`'s job, and only its job.

## Gotchas (PLAN §9) — encoded here because each one has already bitten someone

1. **Guids regenerate per RP by design.** Version pin, never cross-release identity. **This
   defeats naive content dedupe** — an untouched section's raw XML differs at every RP, so
   hashing it collapses nothing (measured: 0 of 5,095 Title 16 sections identical between
   119-99 and 119-102not101; 5,093 identical once `@id` was stripped). Hash
   `SectionRecord.content_key`, never `.xml` (ADR-0007).
2. **Dual schemas** — no USLM 1.x paths outside `Uslm1Parser` (see architecture rule 2).
3. **Renumbering/transfers break `@identifier` continuity.** Track `status="transferred"`; consider a
   redirects table. An identifier can vanish at an RP *without* being repealed.
4. **RP labels do not sort lexically.** Parse into (congress, law_num, excluded_laws[], update_num)
   plus a global `seq` taken from the inventory page's order. Skip labels compound
   (`277not255not268`), and 17 of the 385 published RPs carry a `u1` update suffix (`118-22u1`) —
   `118-22` is a *different* release point with different files.
5. **"not" laws vs `?date`.** At RP `119-102not101` the text is *not* fully current through
   07/12/2026. The UI must surface the exception, not just the date.
6. **Title 42 is huge** (multiples of Title 16). Parsers must stream — `iterparse` + element
   clearing, never whole trees. Batch DB writes.
7. **Appendix titles** (`05a`, `11a`, `18a`, `28a`, `50a`) are separate files with looser structure —
   treat as distinct titles.
8. **Early RPs (2013–2015)** came from an older USLM 1.0 converter; expect attribute drift. Validate
   ingest counts per title per RP.
9. **Repealed/omitted sections keep their place in reading order** — present in prev/next, badged.
10. **Every RP republishes all titles** but few changed — dedupe by content hash or storage explodes
    (~300 RPs × ~1 GB). `titlesAffected` from the RP inventory drives ingest; hashing verifies.
    The flip side is a *retrieval* rule: a request for an RP that was never ingested is answerable
    from the newest ingested RP at or before it, because the title didn't change in between. The
    Repository does that and reports it as `served_from` — answer, but never silently.
11. **XCiteDB is the near future,** not "someday" — respect rule 1 strictly.
12. **`<section>` inside `<quotedContent>` is not a section** — it is statutory text quoted by an
    amending act, carries no `@identifier`/`@id`, and must never be stored or counted (ADR-0005).
    Counting `<section>` elements naively inflates Title 16 by 298. Related: skipping such an
    element must not *remove* it — it is part of the enclosing section's verbatim XML.
13. **`@status` is not section-only and not a closed set.** Title 16's one `reserved` is on a
    `<subchapter>`; USLM 2.x Title 49 uses `renumbered`. Never model status as an enum.
14. **USLM 1.0.15 emits no `@temporalId` at all** — zero in a 32 MB title. Display-only field;
    do not build anything that assumes it is present. It also emits no `<dc:title>`, so a title's
    real name (`CONSERVATION`) comes from the root structural element, not `<meta>`.
15. **Facts that can change while the text does not** — reading order, parent chapter — belong on
    `section_release_map`, never on the content-deduped `section_versions` row (ADR-0008).
16. **A title number is a string; never `ORDER BY` one.** `5a` is a title and `5` is a different
    one, so `Title.num` cannot be an integer — and sorting it as text gives
    `1, 10, 11, 11a, 12, … 2, 20`, which is what the front page listed for eight sessions. Sort
    through `storage.postgres.title_sort_key` (`'5a'` → `(5, 'a')`), which is also the documented
    contract on `Repository.list_titles` (ADR-0025). Do **not** reach for `_padded()` instead: that
    is OLRC's file-naming form (`05`, `18a`) for matching `titles_affected`, and it is still a
    string comparison — one that merely happens to work below title 100.

17. **OLRC writes section numbers with an EN DASH, not a hyphen.** `/us/usc/t16/s45a–1` is
    U+2013, and **5,697 of the corpus's 65,938 sections contain one while not a single section
    contains `-`**. No keyboard has that key, so anything matching user input against an
    identifier must try both (`citeparse.ParsedCitation.section_variants`). Worse, a raw en dash
    in an HTTP header **throws** — a header value is a ByteString — so every URL built for a
    redirect must be percent-encoded (`frontend/src/lib/url.ts`). Both failures were live.

## Fixtures

- `samples/uslm1/usc16.xml` — USLM 1.0.15, 32 MB. Primary parser fixture.
- `samples/uslm2/USLM2/` — USLM 2.x: `usc16.xml` (cross-schema parity), `usc49.xml` (heaviest
  table/layout markup), `usc01.xml` (253 K, fast iteration). Trimmed from OLRC's full 57-title,
  594 MB [sample zip](https://uscode.house.gov/currency/uscinuslmv2samples.zip) — re-download it if
  another title is needed.
- `tests/fixtures/usc16_slice.xml` — 878 KB verbatim slice of usc16.xml (ch.1 subchapters I–VI
  through §45f, plus schXIII for quoted sections and schXCVII for `reserved`). Every unit test runs
  against this. Regenerate with `make fixtures` (`scripts/extract_fixture.py`).
- Known-good assertion: `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` ↔ `/us/usc/t16/s45f/c/5`.
- Title 16 @ 119-102not101 — **two counts, don't conflate them (ADR-0005):**
  - raw `<section>` elements: **5,393**; 523 repealed / 102 omitted / 19 transferred.
  - real code sections the parser emits: **5,095**; 522 repealed / 102 omitted / 19 transferred.
  - The 298-element gap is `<section>` inside `<quotedContent>` — statutory text quoted by amending
    acts, with no `@identifier` and no `@id`. One of them is marked repealed, hence 523 vs 522.
  - The file's **single `reserved` is on a `<subchapter>`** (`/us/usc/t16/ch1/schXCVII`), not a
    section. Section status counts total 643, never 644.
- **Never commit `data/`** — the RP zips (measured ~9 GB via `titlesAffected`; 40–80 GB only if
  every title were fetched at every RP) are gitignored; the corpus of record is the S3 mirror
  (ADR-0013).

## Commands

```
make dev        # the API alone: /api/v1, the citation redirector at /us/usc, /docs
make dev-web    # the reader alone on :4321 (Astro), against API_BASE_URL
make dev-all    # the whole site on :8000 — Caddy in front of both, as deployed
make dev-data   # seed release_points from the RP inventory, then load Title 16 at 119-99
                # (downloaded, ~5 MB) and 119-102not101 (from samples/) — what the API
                # integration tests need; they skip without it
make ci-data    # the same two release points with NO network: inventory from
                # tests/fixtures/releasepoints.json, 119-99 from a committed zip. What CI
                # uses — never fetch from uscode.house.gov on every push (ADR-0013).
                # Runs `make ci-classification-data` first, which copies the committed
                # classification slices to the filenames OLRC publishes them at and loads
                # them through `python -m ingest classification --from-file` (ADR-0067).
make loadtest   # hey against the top routes → docs/verification/loadtest.json; needs
                # `make dev-all` running and `brew install hey`
make test       # uv run pytest (-m 'not slow') — the specification; nothing merges without it green
make test-web   # vitest: the USLM renderer + reading-text extraction, the reference rules,
                # the document redline, url/cache/preview helpers — and the guide ratchet
                # (ADR-0038), which fails when a route or an ADR is in no guide chapter
make test-a11y  # the accessibility scan alone (ADR-0039): axe-core over docs/a11y/routes.json at
                # three viewports, both themes, forced-colors and ten interactive states →
                # docs/verification/a11y.json. Fails on any violation not in
                # docs/a11y/known-violations.json. Needs `make dev-all` running.
make test-e2e   # playwright: what only a browser can answer — the theme toggle (light default,
                # persistence, no sticky-height cost), the hover preview's three WCAG
                # 1.4.13 clauses, sticky geometry, scroll-margin-top, the citation box end to
                # end — plus every scenario block in the user guide, run as a test
                # (ADR-0038). Needs `make dev-all` running.
make shots      # headless screenshots at 375, 1280, 320 and 1280-at-200%-zoom → docs/screenshots/
                # (48 PNGs). Fails if a page scrolls sideways at any of them — WCAG 1.4.10 and
                # 1.4.4 — with the same known-violations ratchet as make test-a11y (ADR-0039)
make demo-video # replay the guide's `demo: true` scenarios with their captions on screen
                # → docs/demo/uscode-demo.mp4 (gitignored) + .vtt/scenes.json (committed);
                # needs `make dev-all` running and `brew install ffmpeg` (ADR-0038)
make test-slow  # full-sample parser integration tests (~4 s): counts vs samples/, memory bound
make test-all   # both
make fixtures   # regenerate tests/fixtures/usc16_slice.xml from samples/uslm1/usc16.xml
uv run python scripts/inline_elements.py
                # recount which USLM elements occur in running prose across the committed
                # samples → docs/verification/inline-elements.json, which tests/uslm.test.ts
                # reads element by element (ADR-0040). No database, no network.
uv run python scripts/ladder.py
                # how deep the (a)/(1)/(A)/(i) ladder goes and how wide its numbers get,
                # across the committed samples → docs/verification/ladder.json (ADR-0054).
                # frontend/tests/e2e/typography.spec.ts reads the depth it reports. No
                # database, no network.
uv run python scripts/contrast.py
                # compute every declared colour pair from site.scss's token block, both
                # themes → docs/verification/contrast.json (ADR-0042). Exits non-zero on a
                # failure, so it is a check as well as a generator.
uv run --with "fonttools[woff]" python scripts/fonts.py
                # rebuild the two self-hosted faces from pinned google/fonts commits →
                # frontend/public/fonts/ + docs/verification/fonts.json (ADR-0052). Byte
                # reproducible; fontTools is deliberately not a project dependency.
make diffcost   # what the API's redline costs with and without the @id guid churn, per
                # section -> docs/verification/diffcost.json (ADR-0066). Times the diff in
                # process, so the endpoint's own rate limiter is not in the way. Needs
                # `make dev-all` running.
make measure    # characters per rendered line of statutory text at 375/768/1280 in both
                # reading densities, and the scroll length of three sections in each
                # → docs/verification/measure.json (ADR-0052, ADR-0054). Exits non-zero
                # when a median leaves 62–70 — the same check `make test-e2e` now runs on
                # every push, over scripts/measure-lines.mjs; what only this target
                # produces is the scroll lengths, which gate nothing and so carry the
                # commit they were measured at. Needs `make dev-all` running.
uv run python scripts/search_eval.py score
                # score every scoring profile in storage/searchquery.py against
                # docs/verification/search-judgements.json → search-relevance.json
                # (ADR-0049). `pool` instead of `score` prints the candidates to grade,
                # from every profile, so no profile is judged against another's set.
                # Needs a cluster with the corpus indexed.
make verify     # (TBD — stub, exits 1) full-corpus counts vs source XML → docs/verification/, PLAN §11.5, Day 7
docker compose up --build   # full containerized stack (db + api) instead of `make dev`'s local API
```

The `python -m ingest …` CLI reference (inventory, fetch, backfill, mirror, load-all, load,
reindex_search, verify, verify-downloads) and `scripts/vendor_apidocs.py` are in the **`ingest-cli`
skill** (`.claude/skills/ingest-cli/SKILL.md`) — loaded on demand rather than every session.

Stack: see `pyproject.toml`, `package.json` and `docker-compose.yml`. What they don't say: the `api`
service builds from `Dockerfile` with UV_PROJECT_ENVIRONMENT=/opt/venv so the dev bind mount doesn't
shadow the container venv; `db/config.py` reads `DATABASE_URL` (see `.env.example`) and Alembic's
`env.py` pulls the same setting and `target_metadata` from `db.models.Base`, so there is no separate URL
to keep in sync. Node 20+ is required — the Astro frontend (ADR-0011) landed in Session 7 and
`make test-web` runs under it.

## Documentation duties (PLAN §11) — non-negotiable, this project is built in the open

1. **Every session ends by updating `BUILDLOG.md`** — one entry per session, in the format at the top
   of that file: date, tool/model, what was asked, what was decided (link ADRs), commits produced,
   what was verified and how to re-check it. Write it while context is hot, before the session ends.
2. **`docs/adr/`** — one short ADR per consequential decision. Skeptics audit reasoning, not results.
3. **Commit discipline** — small commits, imperative messages, preserve `Co-Authored-By` trailers.
   The git history is the walkthrough.
4. **Provenance manifests** — every ingest writes `data/manifests/{release}.json`: source URL,
   download timestamp, zip sha256, per-title section/element counts. Anyone can re-download and
   confirm.
5. **Verification artifacts committed** to `docs/verification/`, regenerated by `make verify` —
   reliability claims must be reproducible commands, not assertions.
6. **A user-visible change updates the user guide in the same session** (ADR-0038). The chapters are
   `frontend/src/pages/guide/*.md`; a behavioural claim carries a ` ```scenario ` block, which is
   simultaneously the Playwright test (`tests/e2e/guide.spec.ts`) and a scene of `make demo-video`.
   This is not on trust: `frontend/tests/guide.test.ts` fails when a reader route is in no chapter's
   `covers.routes`, or an ADR is in neither a chapter's `covers.adrs` nor its infrastructure
   exemption list — so a new page or a new decision turns `make test-web` red until the guide
   accounts for it. Scenarios must be answerable from the CI fixture corpus (Title 16 at `119-99`
   and `119-102not101`) unless marked `data: corpus`, which skips in CI.
7. **Guide prose describes behaviour, not rationale.** The chapters say what a feature is and what
   it does; *why it was built that way* goes in the ADR. Concretely, and each of these was edited
   out of the guide once already: no justifying clause after a factual statement; no aphoristic
   closing line; no "not X — it is Y" as a default sentence shape; no teaser or rhetorical-question
   headings (name the content — "Limitations", "Rate limits", not "What this does not promise"); no
   announcing a count before a list; no presuming the reader's knowledge or that something "will
   catch you out"; no incident narratives as evidence (the crawler traffic, the stale search-syntax
   page — those are ADR-0037 and ADR-0038's business); no moralising or absolutes. Full rules in
   `~/.claude/CLAUDE.md`. The same applies to `docs/demo/scenes.json` captions, which are the
   guide's own sentences.

## Model assignment

The per-workstream agent/model table is **PLAN §7** — read it there. Rhythm per module: plan (Opus) →
approve → implement in a worktree → tests pass → fresh-context reviewer reads the diff → merge. Merge
order: schema → ingest → API → web → auth.

## External source etiquette

uscode.house.gov needs no credentials, but be polite: sequential downloads, ~1 req/sec, cache
everything, descriptive User-Agent. Reuse [dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb)
for the RP inventory/downloader and [dreamproit/versions](https://github.com/dreamproit/versions)
for the temporal diff approach — don't rediscover solved problems.
