# ADR-0091 — The relaunched source lists a window of release points

**Status:** accepted (2026-10-12)

**Amends:** ADR-0087 (the current release point's page), ADR-0036 (the daily poll).
**Related:** ADR-0012 (the backfill the inventory plans), ADR-0082 (a load that did not finish).

## Context

uscode.house.gov answered every page with a maintenance notice from about 2026-10-03, and the
poll recorded that as maintenance (exit 75) as designed. On 2026-10-12 the site came back "in a
temporary format" at new addresses. This site stayed at 119-111 (09/18/2026); the source was
current through 119-120 (10/07/2026).

What the relaunched site serves, read from a GitHub Actions runner on 2026-10-12:

| Address | Answer |
|---|---|
| `download/priorreleasepoints.htm`, `download/download.shtml`, `classification/tables.shtml`, `classification/priortables.shtml` | HTTP 200, a "Page Not Found" page (the maintenance notice until earlier that day) |
| `priorreleasepoints.html` | one release point, 119-118 (09/30/2026), laid out like the current page; no changed titles marked |
| `download.html` | the current release point, 119-120 (10/07/2026); titles 31 and 42 marked `usctitlechanged`; links rooted at the site (`download/releasepoints/…`) |
| `download/releasepoints/us/pl/119/{N}/xml_usc01@119-{N}.zip` | a zip for N = 118 and 120; a "Page Not Found" page for 111 to 117 and 119 |
| `classification/tables.html`, `priortables.html` | the classification tables, now linking `tbl119pl_2nd.html` and `ECCT.html` |

So the poll read pages that no longer exist, the prior page no longer carries the history, and
release points between 119-111 and 119-118, if OLRC published any, are not listed and cannot be
downloaded.

## Decision

1. The poll reads `priorreleasepoints.html` and `download.html`. `parse_inventory` reads the old
   `<li>` markup when it finds it and otherwise one section per
   `<h3 class="releasepointinformation">` heading (`parse_release_point_sections`). The zip-link
   pattern accepts the `download/` prefix. Zip URLs are unchanged.
2. `merge_inventory` appends what the pages list to the release points this site holds. Held
   release points keep their order, dates and changed titles. A poll refuses, as a failed check,
   a page that orders held release points differently, or lists a new release point before or
   earlier than a held one. This replaces the vanished-label guard, which refused any page that
   did not list the whole history; the guard stays in `poll_source` as a backstop.
3. The held release points come from `release_points`, with URLs and descriptions from the
   inventory file where it names the label.
4. A new release point is planned in full, every title the inventory has seen, when the source
   marks no changed titles for it, or when the release point before it on the source is not the
   newest one this site holds. Its changed titles would be a delta from text this site never saw.
5. Release points the source no longer lists are not recovered. 119-118 is loaded as the
   successor of 119-111.

## Consequences

- The next daily poll after deploy finds 119-118 and 119-120 and runs the full chain: 58 zips at
  119-118 and 2 at 119-120.
- `titles_affected` for 119-118 lists all 58 titles. `/app/releases` shows it as changing every
  title.
- Any release point between 119-111 and 119-118 is missing from the timeline. A request dated in
  that interval is answered from 119-111, as for any date between two release points.
- The classification poll still reads `classification/tables.shtml` and fails on the "Page Not
  Found" page (exit 1). The tables' new pages are `.html` and are not handled here.
