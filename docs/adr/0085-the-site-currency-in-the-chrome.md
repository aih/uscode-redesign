# ADR-0085 — The site's currency in the header, the footer and the front page

**Status:** accepted (2026-09-17)

**Task:** Show how current the site is on the front page, in the footer, and in the header: the
newest release point loaded and its date, visible at every width without taking space from the
reading chrome.

**Builds on:** ADR-0018 (cache policy), ADR-0036 (the poll and `/api/v1/status`), ADR-0053
(`/app/design` reaches no data), ADR-0061 and ADR-0064 (the header at each width), ADR-0078 (the
corpus generation), ADR-0082 (unfinished loads in the status).

## Context

The newest release point loaded was stated on `/app/releases` and, per title, in each section's
release band. No page stated it for the site as a whole, and the front page listed titles without
a date.

The header's height is a budget. Between 40em and 64em it is part of the sticky stack that
`--sticky-h` pays for, and `sticky.spec.ts` requires 60px of headroom; below 64em the bar is 52px
and every target on it is 44px (`chrome.spec.ts`); above 64em the header is 73.5px.

## Decision

### 1. One memoised status read, in `Base`

`lib/sitecurrency.ts` memoises `/api/v1/status` per process. An entry is fresh while it is under
five minutes old and the corpus generation has not moved; a null answer is not kept. `Base` reads it
once per page and hands the header a `Dateline` (label, date) and the footer a `FooterCurrency`
(label, date, day of the last check, warning headline). A page passes `currency={false}` to skip
both; `/app/design` does, and renders the three components as specimens instead.

### 2. The header: a dateline under the wordmark

`Dateline.astro` renders *Current through 07/12/2026 · 119-102* under both copies of the wordmark,
read aloud as *Current through 07/12/2026 · release point 119-102*. It is text outside the home
link, so the link's accessible name is unchanged.

- **Below 64em** it is absolutely positioned inside the home link's 44px box, the wordmark moved to
  the top of that box, with `pointer-events: none` so a tap on it follows the link. The bar stays
  52px and the header 104px.
- **Below 30em** *Current* is visually hidden as well: *Through 07/12/2026 · 119-102*, at 0.72rem,
  fits the 161px a 320px bar gives the brand.
- **The two parts are flex items on a one-line box that clips.** Where a long label does not fit,
  the release point wraps out of sight and the date stays; a screen reader reads both.
- **From 64em** the logo's margins are reduced by the dateline's line (2rem/1rem → 1.42rem/0.64rem),
  so the header measures 73.47px against 73.52px before. The line fits under the wordmark, so the
  logo keeps its width. A first version showed *release point* on desktop and did not wrap there;
  the logo widened from 237px to 272px, and at 1280px and 200% zoom — where the desktop header is
  laid out in 640 CSS px — the search button ended 10px past the edge (`make shots`).

### 3. The footer: facts with dates, not ages

`FooterCurrency.astro` opens the footer's secondary section: the newest release point loaded, its
date, the day uscode.house.gov was last checked (in `America/New_York`), and a link to
`/app/releases`. When `currencyNote` is a warning its headline leads, in `--ink`. The check is a
date rather than "3 hours ago" because a page with a pinned release point is cached for a year.

### 4. The front page: a panel above the example citation

`SiteCurrencyPanel.astro` uses `ReleaseContext`'s line — *Newest release point loaded 119-102
current through 07/12/2026* — adds the release point's caveat (from the memoised release list)
and `currencyNote`'s sentence as a plain line, or `SourceCurrency`'s warning alert.

## Consequences

- Every page that renders `Base` depends on `/api/v1/status` at most once per five minutes per
  process. When it does not answer, the header and footer render without the line.
- A page cached as `immutable` (a pinned `?release=`) carries the dateline as it was when served.
  `ReleaseContext`'s "newest" badge on those pages has the same property.
- `SourceCurrency`'s headline and detail had no space between them; both branches now carry an
  explicit `{" "}`.
