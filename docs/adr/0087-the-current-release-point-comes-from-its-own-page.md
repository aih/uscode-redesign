# ADR-0087 — The current release point comes from its own page

**Status:** accepted (2026-09-18)

**Amends:** ADR-0036 (the daily poll). **Related:** ADR-0012 (the backfill the poll drives).

## Context

The poll read one page, `download/priorreleasepoints.htm`. On 2026-09-18 uscode.house.gov was
current through 119-108 (09/11/2026) and this site through 119-103 (09/02/2026), with the last
check reporting OK and nothing new.

That page carries the current release point as a commented-out `<li>` at the top:

```html
<!--    <li class="releasepoint"><a class="releasepoint" href="releasepoints/us/pl/119/108/usc-rp@119-108.htm">Public Law 119-108 (09/11/2026), affecting titles 26, 31, 40.</a></li>  -->
```

OLRC uncomments it when the next release point supersedes it. `parse_inventory` strips comments,
so the poll saw a release point only after its successor was published, and the site ran one
release point behind at all times. The module docstring had recorded the commented-out `119-102`
entry as a release point "never published"; it was the current one on the day the fixture was cut.

The current release point is on `download/download.shtml`: a heading
(`<h3 class="releasepointinformation">Public Law 119-108 (09/11/2026)</h3>`), one row per title
whose download links carry the label (`xml_usc26@119-108.zip`), and the rows changed since the
previous release point marked `usctitlechanged` / `usctitleappendixchanged`.

## Decision

1. `ingest.inventory.fetch_entries` reads both pages. `parse_current_release_point` takes the label
   from the XML zip links (exactly one distinct label, or the parse fails), the date from the
   heading, and `titles_affected` from the changed rows. `with_current_release_point` appends it
   as the newest entry, `seq` one past the prior list's newest, unless the prior list already
   names it.
2. A current release point dated earlier than the newest prior one is a parse failure.
3. Either page failing to fetch or parse fails the check, recorded in `source_checks` as before.
   Once the current release point is seeded, the vanished-label guard in `poll_source` would refuse
   a poll that read the prior page alone.
4. The commented-out `<li>` is not parsed. The current page is the source OLRC publishes for it.
5. `python -m ingest inventory` and `check` take `--current-url`; the poll stays daily.

## Consequences

- The site is behind uscode.house.gov by at most one day plus the load time.
- The poll is two requests a day instead of one.
- When the prior list later names the release point, `seed_release_points` updates its row in
  place: the date and titles from the prior list replace the ones read from the current page.
