# ADR-0075 — The version history defaults to statutory changes

- **Status:** Accepted
- **Date:** 2026-08-31
- **Context:** `docs/version-semantics-spec.md` (Phase V3); ADR-0007 (dedupe on
  guid-stripped content), ADR-0018 (a cache policy per response), ADR-0021
  (several elements under one identifier), ADR-0053 (`/app/design` as the
  regression surface), ADR-0066 (`content_first_seen` does not mean what it is
  called; the compare default), ADR-0071 (the sort bar's vocabulary),
  ADR-0074 (the stored classification and attribution). Amends ADR-0066.
  Session 66.

## Context

`/app/versions` listed every group ADR-0007's content hash produced and its lede
called each one "a release point where the text changed". Corpus-wide, 75.1% of
those transitions changed no text and no notes and 17.1% changed only the notes;
7.8% changed the statutory text (`docs/verification/version-changes.json`). So
the page's central claim was false for nine entries in ten, and § 2201's history
— two amendments in thirteen years — read as seven equal rows.

ADR-0074 stores what each transition was and, for a text change, the Public Laws
the OLRC classification tables classify to that section inside the transition's
window. This ADR is what the reader does with that.

The same finding reaches ADR-0066's "Compare with…" default one level down. That
control offers "the last release point holding different text", read off the
group before the one on screen — and the group before is usually the same words
with different markup, which is the empty redline the control exists to avoid.

## Decision

1. **Two views, one document.** `/app/versions/…` renders **every** entry, each
   `<li>` carrying `data-change-kind`; the list root carries `data-view`, from
   `?view=all`, and the stylesheet hides the `notes` and `structure` entries in
   the default view. The alternative — asking the API for one view or the other,
   or filtering in the browser — was rejected on two counts. One document per
   URL is one cache entry per URL (ADR-0018) and one address to paste; and the
   deferred per-account default (`docs/version-semantics-spec.md`) flips
   `data-view` from the pre-paint bootstrap that already stamps the theme and
   the reading density, which needs no markup change because the CSS keys on the
   list root rather than on a class the server picked per entry. The page adds
   no script of its own: `/app/versions` measures 18,250 inline bytes against
   its 18,500 budget before and after this work (`docs/verification/js-bytes.json`),
   all of it the site chrome's.

2. **A run of release points extends through what the view hides.** An entry's
   "Unchanged through" line is the run its own group carried; in the default
   view the groups hidden after it are the same statutory text, so the line has
   to name their release points too. `frontend/src/lib/versions.ts` computes
   both runs and both diff links per entry, and CSS shows one of each per view.
   Rendering only the visible run would have made the default view claim a
   provision left the Code between two amendments.

3. **The switch is two links in the sort bar's vocabulary** (ADR-0071):
   **Amendments (N)** | **All recorded versions (M)**, the one in force a marked
   pill, the other a link. One line under the lede — the whole footprint the
   full history costs the default view.

4. **A law is a chip, and an unattributed text change says so.** A `text` entry
   attributed `classified` shows one chip per law, **Pub. L. 119–102** with the
   EN DASH the tables and the Code write, carrying the source's action word when
   it is not a plain amendment (`new`, `repealed`, `tr to`). An unattributed one
   reads "No classifying statute recorded" — never "editorial", which would be
   a claim ADR-0074's data does not support for the half of text transitions
   that name no statute.

   **The chip links to the lookup, not to a session table.** The spec asked for
   the session table filtered to that law, and the session a law falls in is not
   derivable from `(congress, number)`: the tables are per congress *and*
   session and the split is by date. Resolving it would be one
   `/api/v1/classifications/suggest` call per chip. So the chip is
   `classificationHref(null, null, { q: "Pub. L. 119-102" })` — the lookup, which
   answers that query with a link into the right table. The cost is one further
   click.

5. **The displayed start of an entry is `releases[0]`.** Not `first_seen`, which
   follows the stored fragment's `first_release_id` and names a later release
   point than the group's own earliest whenever an incremental load attached one
   (ADR-0066). The From/To picker under the timeline offers the same labels, and
   offers only the entries the view on screen shows.

6. **An unknown state degrades visibly.** When any entry answers
   `change_kind: null` — a corpus loaded but not back-filled, or back-filled
   before an incremental load — the page renders the all view, says change kinds
   are not computed for this corpus, and offers no switch. The section page's
   history link keeps the sentence it had rather than printing a count of
   amendments it cannot compute.

7. **`previousChangedRelease` walks back to the last transition that changed
   the words** (amending ADR-0066's default), and compares against the release
   point immediately before it. Without change rows it stops at the group
   before, which is the answer it gave before the annotations existed — so a
   corpus with no backfill keeps ADR-0066's behaviour rather than losing the
   control.

8. **The section page's history link carries the count**: "Version history —
   amended N times over M release points", from the timeline the page already
   fetches for the compare default (ADR-0066's third allowed-to-fail call). No
   new request.

9. **`/app/design` renders both views** over one fixture carrying all four
   change kinds, both attribution states and two law chips (ADR-0053). The CI
   fixture corpus's two release points produce nothing but `initial` and `text`,
   so this is the only place CI, `make shots` and the axe matrix see a
   notes-only or metadata-only entry rendered.

## Consequences

- The default view of § 2201 is three entries where it was seven, and each of
  the two amendments names the public law behind it.
- `?view=all` is a new address for an existing page rather than a new route, so
  the guide ratchet asks for prose and this ADR, and the axe matrix gains one
  route entry.
- A reader who wants the metadata churn has to ask for it. That is one click on
  every section, and it is what makes the default honest.

## Costs, named

- **A law chip is two clicks from the table row it names** (decision 4).
- **The default view can be empty of amendments.** A section whose text has
  never changed in the corpus shows one entry — the start — and the switch says
  how many recorded versions the metadata churn produced.
- **A whitespace-only statutory change classifies as `structure`** and is
  therefore hidden by default (ADR-0074's recorded cost, met here for the first
  time in the reader). The reading redline cannot see such a change either
  (ADR-0026), so the two surfaces agree.
- **`concurrent` entries are shown with a note and nothing more.** ADR-0074
  flags 39,645 transitions whose windows are unreliable — recurring content, not
  ADR-0021 duplicates — and the timeline says the order is the order they were
  stored in rather than trying to repair it.
- **The default view's counts and the API's are the same numbers read twice.**
  The page computes them from the entries in hand; nothing asserts that a
  filtered count from the API would agree, because there is no filtered call.
- **The deferred per-account default is designed and not built.** The CSS keys
  on `data-view` so a later `usc-versions-view` stamp can flip it, and nothing
  in this session writes that stamp or the settings row behind it.
