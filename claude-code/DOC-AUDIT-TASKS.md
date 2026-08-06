# Documentation audit — task list

Produced by the 2026-08-06 audit session (BUILDLOG 056). Every documentation surface was read and
checked against the code: the nine guide chapters, the demo captions, the search syntax page,
`/app/design`, the shortcuts references, the OpenAPI surface, README, GETTING-STARTED, PLAN, and the
internal docs (`ia-map`, `backlog`, `deploy-status`). This file is the work order for the fix
session.

Priorities: Tier 1 first (user-facing factual errors), then Tiers 2–4 (README, internal docs, API
docs), then Tier 5 (prose cleanup). Line numbers are as of commit `f37d633`; re-grep before editing,
since earlier fixes in a file shift later lines. The "Verified correct" list at the end names what
the audit confirmed — leave those alone.

---

## Tier 1 — factual errors on user-facing pages

1. **Guide 09 — "six interactive states" is nine.**
   `frontend/src/pages/guide/09-checking-this-site.md:55`. `docs/a11y/routes.json` defines 9
   states; the three missing from the prose are `density-compact` (ADR-0054), `shortcuts-open`
   (ADR-0055) and `release-switcher-open` (ADR-0056). List all nine.

2. **Guide 01 — "three-minute demo" is 4 m 33 s.**
   `frontend/src/pages/guide/01-what-this-site-is.md:56`. `docs/demo/scenes.json` `totalMs` is
   272,967. Reword to the real length or drop the duration.

3. **Guide 05 — "Repeating a prefix widens it" holds for three of six prefixes.**
   `frontend/src/pages/guide/05-search-and-citations.md:77`. True for `title:`/`chapter:`/`status:`
   (one `terms` clause per field — `storage/searchquery.py:376-380`). Repeating `heading:` narrows:
   each term is its own `must` clause (`:370-371`). Repeating `release:`/`date:` keeps only the
   last (`:145-148`). State the three cases.

4. **Search syntax page contradicts itself on `release:`/`date:` in the box.**
   `frontend/src/pages/search/syntax.astro:65-67` ("only through the URL for now") and `:204-208`
   ("The search box has no control for this yet"). Both prefixes work typed into the box
   (`searchquery.py:62,145-148`) and are listed in the operator table this same page renders
   (`frontend/src/lib/searchsyntax.ts:175-190`, rendered by `syntax.astro:164-179`). Guide 05:205-206
   states the working behaviour. Fix both passages.

5. **`?sort=` is documented nowhere a searcher would look.**
   Three values: `relevance`, `citation`, `recent` (`searchquery.py:303`; UI labels
   `frontend/src/pages/search.astro:42-46`). Add to `syntax.astro` (which already documents
   `&release=`/`&date=`) and to guide 08's search row. Guide 05 describes the orders in prose but
   never names the parameter.

6. **The print-hidden list in two docs is incomplete.**
   `frontend/src/pages/guide/02-reading.md:348-350` and `frontend/src/pages/design.astro:841-842`
   both omit `.contents` (the "In this section" panel) and `.neighbors` (the previous/next cards),
   which print also drops (`frontend/src/styles/site.scss:4745-4763`). Both are features guide 02
   itself introduces.

7. **Guide 06 overstates the hover preview's keyboard path.**
   `frontend/src/pages/guide/06-working-with-the-text.md:48-49,55`. The whole island, keyboard path
   included, runs only when `matchMedia("(hover: hover) and (pointer: fine)")` matches
   (`frontend/src/components/CitePreview.astro:44-46,95`). On a touch device, focusing a citation
   does nothing; the guide's `:53` covers tapping only.

8. **Guide 06 copy-control claims.** Three corrections in
   `frontend/src/pages/guide/06-working-with-the-text.md:11-44`:
   - `:13` "Beside every identified provision is a copy control" — the section itself has no gutter
     icon; it gets the "Whole section" button in the bar (`CopyColumn.astro:76-84,290`).
   - The copied **Link** carries the release point the page was pinned to (`CopyColumn.astro:63-73`),
     so a link copied from a pinned page is not the moving citation URL. Unstated.
   - With scripting off the entire copy column is absent (`CopyColumn.astro:41-47,89`). Unstated.

9. **`/app/design`'s lede contradicts its own contents.**
   `frontend/src/pages/design.astro:394-401` omits four of the page's thirteen sections: the
   reading measure, keyboard navigation, reading density, and print. The TOC at `:413-425` lists
   all thirteen.

10. **Guide 09's description of `/app/design` is short seven sections.**
    `frontend/src/pages/guide/09-checking-this-site.md:84-89` omits the section bar, the neighbour
    cards, the release switcher, the release context band, the section contents panel, the keyboard
    shortcut list, reading density, and print — all on the page (`design.astro:413-425`).

11. **382 vs 381 release points — name the noun.**
    Guide 03:12 and guide 07:35 say 382; guide 09:25 and `about.astro:109` say 381. Both are right:
    382 in the seeded inventory, 381 loaded (and gotcha 4's 385 counts superseded `u1` pairs among
    the published set). Add one distinguishing sentence — guide 03 is the natural home — and have
    each other mention name its noun ("published" / "loaded").

12. **ADR-0021's numbers appear in three unreconciled units.**
    Guide 05:217 "49 identifiers across 14 titles"; `syntax.astro:270-274` "160 documents… 9 of
    them in current text"; guide 09:48 "six count mismatches". All correct at different
    granularities. Add a bridging clause where two meet (guide 05 ↔ the syntax page).

13. **Guide 02 keyboard-section corrections.**
    - `:181` the "Moving inside a section" group drops the "on a section page" qualifier; both
      shortcut groups are `sectionOnly` (`frontend/src/lib/shortcuts.ts:41,65`) and the dialog
      prints the qualifier on both.
    - `:205-206` `[` and `]` step only the provision rows of the contents list, not the source
      credit and notes rows (`KeyboardNav.astro:120-127` selects `href^="#/"`).
    - `:202-203` the input guard covers any input, textarea, select, or contenteditable element
      (`KeyboardNav.astro:192-198`), not only "a search box or a date field".

14. **`Esc` does not close the release switcher, and no doc says so.**
    Deliberate (`frontend/src/components/ReleasePicker.astro:33-36` — no island). One clause in
    guide 02's `Esc` row or guide 03's switcher section.

15. **Facet caps are undocumented.**
    12 values shown per group; a group is suppressed when a single value covers every result
    (`frontend/src/components/SearchFacets.astro:38-70`). One sentence at guide 05:136-139.

16. **Verify the currency date on the syntax page's example.**
    `syntax.astro:50` gives `06/12/2026` for release 119-99. Not confirmed during the audit; check
    against `release_points` before or while editing that page.

## Tier 2 — README.md (stale since 2026-08-03)

17. **`:75` — test counts 474/185/74 → 545/299/449** (268 of the 449 the accessibility scan).

18. **`:71` and `:126-128` — the site is deployed and README doesn't know.**
    Live at `uscode.linkedlegislation.org` since 2026-08-01 (ADR-0020, ADR-0035); the URL appears
    nowhere in README. Of the `:126-128` "Next" list, only USLM 2.x parser parity remains: the
    accessibility pass is ADR-0039, and the "how it was built" page shipped as `/app/about` plus
    guide chapter 09.

19. **`:104-106` — the search-index caveat reads as a property of the site.**
    True only of a fresh local checkout; the deployed index is complete (489,578 documents). Scope
    the sentence to local checkouts.

20. **`:59-63` — the suite list omits `make test-a11y` and `make measure`**, both ratchets with
    committed artifacts.

21. **`:16-18` — overstates USLM 2.x support.** `Uslm2Parser` has no table/indent handling.

22. **Nothing from ADR-0043–0056 is mentioned.** No `/app/design`, `/app/demo`, `/app/docs`, the
    Spectral/Archivo brand layer, the keyboard map, the release switcher, or the accessibility
    ratchet. One short paragraph; not a rewrite.

23. **Prose tics** — see the README table in Tier 5.

## Tier 3 — internal docs and CLAUDE.md

24. **`docs/ia-map.md:109-113` — the release switcher moved.**
    The map says `ReleasePicker` sits at the top of the content "rather than in the sticky stack,
    for the measured reason in ADR-0044". ADR-0056 moved it back into `.contextbar` as a
    `<details>`. Also `:70`'s "Task B5" is defined in `claude-code/WORKSTREAM-B-STATE.md`, not
    `docs/backlog.md` — add the pointer.

25. **`docs/backlog.md` — B1/B2 premises are stale.**
    `:15` "18rem… site.scss:106" → 19rem, now at `site.scss:442`; `:17-18` "296px" derives from the
    stale value (the rule is `calc(var(--sticky-h) + 0.5rem)` at `site.scss:775`); `:42` "~1,270
    lines" → 4,909; `:33-35` "re-measure before designing" is answered by ADR-0044, ADR-0054
    (0px of `--sticky-h` at three widths) and ADR-0056 (89px, asserted in `sticky.spec.ts`). The
    file's own rule (L4-5) says an item overtaken by an ADR gets a note naming it — B1 is partly
    overtaken by ADR-0056.

26. **`docs/deploy-status.md` — internal contradictions.**
    `:299` "475 tests" (a third distinct count in the repo); `:311-313` "not merged yet" vs
    `:170-172` "#17 and #18 are merged"; `:265-267` the `--all-versions` caveat vs `:315` and
    `:374` "Done… Nothing is outstanding here"; `:269-272` 65,938 current documents vs `:319-322`
    65,929, reconciled only at `:325` with no forward reference; `:9` last-updated 2026-08-03.
    The later statements are the true ones; reconcile top-down and re-date.

27. **PLAN.md — present-tense statements that are now false.**
    Recommendation: correct the status paragraph, add dated supersession notes to the rest rather
    than rewriting history.
    - `:11` "209 Python tests… 27 frontend"; "backfill… running concurrently"; the "Next:" list is
      all done.
    - `:46-56` §2 diagram shows `web/` as the reader with no supersession note (`web/` is empty;
      the reader is `frontend/`, ADR-0011).
    - `:143-153` §4 route table: missing `/api/v1/search`, `/citation`, `/labels`, `/status`,
      `/sections/{id}/diff`, `/settings`; rows omit the `/api/v1` prefix; `:151` names OAuth, which
      was never built (ADR-0017 is email+password only).
    - `:154` "HTML rendering reuses OLRC's CSS" — the API serves no HTML (ADR-0010); rendering is
      `frontend/src/lib/uslm.ts`.
    - `:173` and `:242` "~324 RPs" contradict `:30`'s corrected 382.
    - `:215` "~100 GB free" vs the measured 9.7 GB corpus.
    - `:217-220` Fly/Render/Hetzner hosting superseded by ADR-0020/0035 (and ADR-0047 rules out a
      shared cache in front of the spine).
    - `:226-237` §9's `1a` entry offsets the printed numbers from the ordinal citations elsewhere
      (`api/routes.py:161,311` and CLAUDE.md cite "gotcha 4" and "gotcha 9" by position). Renumber
      §9 or cite by name.

28. **GETTING-STARTED.md — stale since 2026-07-28.**
    Recommendation: supersession markers, not rewrites.
    - `:190` documents `defaultMode: "acceptEdits"`; `.claude/settings.json` has no such key.
    - `:157`, `:172-176`, `:178-182` Sessions 9, 12 and 13 are unmarked though done; the "skeptic's
      page" shipped as `/app/about` + guide 09, not `/about/how`.
    - `:78` "~324 zips, never commit" — the count is superseded (382), and one 5 MB zip is
      committed deliberately for `make ci-data`.
    - `:69-76` sample-tree setup instructions for trees that are committed.
    - `:23` Fly/Render/Hetzner; `:93` `web/` package (empty since Session 7); `:219` live
      scheduling advice for tracks completed weeks ago.

29. **CLAUDE.md — two self-errors.**
    `:231` "56 ADRs" → 55 files (numbered to 0056; there is no ADR-0048 — BUILDLOG:1460). `:38`
    "28 route entries" → 29 (`docs/a11y/routes.json`; the arithmetic to 268 scans confirms 29).

30. **`ingest/search_sync.py:137`** — the comment claims "The sort control says so" about the
    citation-order caveat; no UI text does (only guide 05:159-161). Fix the comment or add the UI
    text; if the UI text is added, guide 05 needs no change.

## Tier 4 — API and OpenAPI documentation

31. **Rate limits are absent from the OpenAPI document.**
    `main.py:42-62` (the app description) never mentions ADR-0029; `/docs`, `/redoc` and
    `/app/docs` (which renders that description — `frontend/src/pages/docs.astro:36`) tell a
    developer nothing about throttling. Guide 08:67-68 is the only description.

32. **429 is declared inconsistently.**
    `/citation`, `/labels` and `/diff` declare it (`api/routes.py:192,323,400`); `/api/v1/search`
    (`api/search.py:124`), `/auth/login` and `/auth/signup` (`api/auth.py:80,245,261-279`) return
    it undeclared.

33. **Fifteen routes have no summary or description.**
    All four in `api/auth.py`, eight of nine in `api/watchlists.py`, one of two in
    `api/settings.py`, and `/health` (`main.py:95`).

34. **The labels bound is enforced but unstated.**
    `api/routes.py:320-349` enforces `max_length=100`; the route description never states it, so a
    caller learns it from a 422.

35. **Guide 08's route table is incomplete.**
    `frontend/src/pages/guide/08-api.md:26-35` omits `/api/v1/labels` and `/api/v1/citation`, and
    the search row omits `?sort=`/`?limit=`/`?offset=`/`?release=`/`?date=`. For the auth,
    watchlist and settings routes: recommend one sentence noting they exist and serve the inactive
    accounts feature (ADR-0034; CLAUDE.md records that `POST /api/v1/auth/signup` works for a
    direct caller). If the decision goes the other way, record it.

36. **HEAD is 405 on every `/api/v1` route.**
    Known debt; one line in guide 08 or the API description.

## Tier 5 — prose cleanup

The style rules are Documentation duties 7 (guide and captions) and `~/.claude/CLAUDE.md` (all
prose for a human reader — README and the about page included; ADRs exempt, rationale is their
job). Each table row: line, verbatim quote (abbreviated where long), rule broken. Re-grep the quote
before editing.

### `frontend/src/pages/guide/index.astro`

| Line | Quote | Rule |
|---|---|---|
| 32-34 | "Those steps are not an illustration: they are run as automated tests on every change to the site, so a claim in this guide that stopped being true would fail the build rather than sit here misleading you." | Antithesis ×2, justifying clause, presumes the reader ("misleading you"), aphoristic closer. The sentence that prompted this audit. |

### `frontend/src/pages/guide/01-what-this-site-is.md`

| Line | Quote | Rule |
|---|---|---|
| 18 | Heading "## The idea" | Teaser heading; name the content |
| 20 | "Every provision… has an address, at every point in time it has existed." | Verbatim repeat of the summary (L5) and the caption (L41) |
| 52 | "…so this prevents automated crawling from consuming excessive resources." | Justifying clause; crawler rationale is ADR-0037's business |
| 73 | "A claim here that stopped being true would fail in testing." | Justifying/consequence clause |
| 75 | "This approach ensures that the documentation remains accurate as the application evolves." | Aphoristic closer; restates L70-73 |

### `frontend/src/pages/guide/02-reading.md`

| Line | Quote | Rule |
|---|---|---|
| 47 | "One URL is safe to paste into a brief, an email or a script." | Aphoristic closer |
| 100 | "Three more ways to move:" | Announcing a count |
| 117 (caption) | "Reading order is preserved, so you can move through a chapter section by section." | Justifying "so you can" |
| 133 | "**Repealed and omitted sections keep their place in reading order.** They are not skipped or hidden. A section that was repealed remains part of the structure…" | Antithesis; sentence 3 restates sentence 1; bold for drama |
| 154 (caption) | "The notes, without scrolling the length of the section to find them." | Presumes the reader's alternative; restates the caption before it |
| 158 | "The bar stays put at every width, so it is reachable from any scroll position." | Justifying clause |
| 202-203 | "A jump inside a page takes the keyboard with it, so Tab continues from where you landed." | Justifying clause |
| 205-206 | "…so a section with no subsections has nothing to step through." | Justifying clause (and see Tier 1 item 13 for the factual fix) |
| 259-261 | "The badge prints whatever the source says, rather than mapping it onto a fixed list — … would be editorialising." | Rationale in guide prose; antithesis; moralising |
| 277 (caption) | "Each date is part of the running text, not a line of its own." | Antithesis in a caption |
| 286-289 | "No keyboard has that key, so the search box accepts either…" | Justifying clause; absolute for emphasis |
| 291-295 | "are separate titles with their own structure, not appendices bolted onto…"; "…because the OLRC publishes no section at that flat address — the site explains this rather than showing a bare 404." | Antithesis; "because" + "rather than" |
| 305 | "No font is fetched from Google Fonts or any other host, so the page renders its type without a request to a third party." | Justifying clause; restates L304 |
| 315-319 | "…so the numbers at one depth line up with the text at the depth above"; "…where the screen has less to spend." | Justifying clause; rationale |
| 328 | Heading "### Five kinds of text in one column" | Announcing a count in a heading |
| 339-341 | "It keeps the reading face, because it is statutory text, and takes the panel and the label so that it is not read as the note's own prose." | "because" and "so that" in one sentence |
| 353-359 | "…so a page that has left your printer still says which provision it is…"; "…so following it later lands on the same text you printed." | Justifying clauses |
| 365-368 | "Colour carries three meanings and no others." / "…so none of it depends on being able to tell the colours apart." | Absolute + count; justifying clause; closes the chapter on an aphorism |

### `frontend/src/pages/guide/03-reading-at-a-point-in-time.md`

| Line | Quote | Rule |
|---|---|---|
| 5 | summary "…the three ways to ask for one, and the four facts every page tells you…" | Announcing counts (rendered on `/app/guide`) |
| 15 | Heading "## Three ways to ask" | Announcing a count; name the content |
| 53 | "The bar stays on screen as you read, so both are reachable from any scroll position." | Justifying clause |
| 54 | "…returns `(c)(5)` at the release point you chose, not the top of § 45f." | Antithesis tail |
| 56-58 | "…is rebuilt at most every five minutes, so a release point loaded within the last few minutes may not be listed yet." | Consequence clause (the fact is fine; trim the "so") |
| 81 | "Four facts, in one band above the section:" | Announcing a count |
| 109-110 | "Most release points republish a title without changing it, so this site does not store multiple copies…" | Design rationale in guide prose |
| 111 | "…and **the page tells you that it did**." | Bold for drama |
| 114-116 | "…so neither is reading one." | Justifying clause |
| 120-121 | "…are greyed with a dagger, rather than omitted." | Antithesis |
| 133 | "This makes the site's update status visible to readers." | Restates the point just made; rationale |
| 139-141 | "…can be cached forever, because that text will never change: a release point is a fixed thing." / "…because tomorrow it may resolve somewhere else." / "This is why a pinned URL is the one to put in a citation." | "because" chain; aphorism; rationale closer ending the chapter |

### `frontend/src/pages/guide/04-version-history-and-redlines.md`

| Line | Quote | Rule |
|---|---|---|
| 17 | "This timeline shows when changes actually occurred. Because the Code republishes every title…, this list shows only changed entries." | "Because" clause; sentence 2 restates sentence 1 |
| 26 (caption) | "…one entry per distinct text, not one per release point." | Antithesis in a caption |
| 31 | Heading "## What changed?" | Rhetorical-question heading |
| 36 | "The redline is of the **reading text**, not of the source XML." | Antithesis + bold (keep the fact; reshape) |
| 48 (caption) | "…— the amendment, not the markup." | Antithesis in a caption |
| 66-67 | "…rather than open by default — computing it is the expensive part, and most readers want the words." | Rationale; presumes the reader's wants |
| 73-75 | "The comparison is over text, so a citation that is a link… is plain text here."; "**A change in whitespace alone is not shown…**, since it compares displayed text." | Justifying clauses; bold |

### `frontend/src/pages/guide/05-search-and-citations.md`

| Line | Quote | Rule |
|---|---|---|
| 12-13 | "You do not have to tell it which you meant." | Presumes the reader |
| 36-37 | "That list is generated from the parser's own table, so it cannot describe a form the site does not accept." | Justifying clause; absolute |
| 39 | "Two things to look out for:" | Announcing a count; presumes the reader's reaction |
| 40-42 | "…is searched rather than resolved, because it is not a citation; and… resolves to nothing, because the OLRC publishes nothing at that flat address." | Two "because" clauses |
| 63-64 | "Six prefixes narrow a search without changing the words in it." | Announcing a count |
| 138-139 | "…so the address bar always holds the whole search… A search you paste into a brief or a ticket arrives as the search you ran." | Justifying clause; aphoristic closer |
| 157 | "Results come back by relevance. Two other orders are available:" | Announcing a count |
| 178 | "The ordering is measured rather than asserted." | Antithesis; aphoristic |
| 183-184 | "Ranking by words has a limit worth knowing:…" | Presumes the reader ("worth knowing") |
| 200-201 | "…offers you the loosened version of your own query rather than a blank page" | Antithesis |
| 205-208 | "…so you can tell from the answer which question was asked." | The exact forbidden "so that…you" shape |
| 221 | "Note that this is a keyword search rather than a structured reverse-citation index." | "Note that"; antithesis |
| 224 | scenario title "The \"cites\" prefix says what it actually is" | Moralising framing (titles render in the verification box) |

### `frontend/src/pages/guide/06-working-with-the-text.md`

| Line | Quote | Rule |
|---|---|---|
| 5 | summary "…and the three reading settings the browser keeps." | Announcing a count |
| 44 | "**Copying does not include notes or credits:** The copy function does not include notes or source credits." | The sentence restates its own bolded lead verbatim |
| 50 | "You find out whether you need to go there without going there." | Aphoristic closer |
| 53 | "…tapping a citation simply follows the link rather than opening the hover card." | Antithesis; "simply" as reassurance |
| 75-76 | "Previews are rate-limited, so moving quickly down a section… can reach the limit" | Consequence clause (keep the fact, reshape) |
| 102-103 | "For \"this provision over time\", the citation URL is the right address; for \"the words I am quoting\", use the guid." | Restates L94-100; aphoristic summary |
| 116 | "…applied before the page paints, preventing flashes between pages." | Justifying clause |
| 140-143 | "…the lines do not get longer, there are just more of them on the screen."; "…because a narrower column gives a table more rows to wrap into." | Restatement; "because" clause |
| 159-160 | "…open in a new tab by default, so you can stay in the section you were reading." | The forbidden "so you can" shape |

### `frontend/src/pages/guide/07-accounts.md`

| Line | Quote | Rule |
|---|---|---|
| 5 | summary "What an account will be for, why it is switched off, and everything that works without one." | Rationale advertised; "everything" absolute |
| 11 | "Their controls are still visible on the page to explain their intended functionality." | Purpose clause |
| 21 | Heading "## Why they are inactive" | Rationale as a heading; rename (e.g. "Status") |
| 27-29 | "…so you can come back to *this section as it stood then* in one click…" | "so you can"; italics for drama |
| 33 | "The core features that do not require accounts:" | Restates the heading immediately above it |

### `frontend/src/pages/guide/08-api.md`

| Line | Quote | Rule |
|---|---|---|
| 11-12 | "…and the reader has no privileged access to anything." | Absolute for reassurance |
| 37-39 | "…which is the thing to use if you want to parse rather than read." | Presumes intent; antithesis |
| 65 | "Pin the release point in anything you store." | Imperative closer |
| 68 | "The limits are set well above normal reading patterns and well below automated crawling." | Justifying clause; crawler reference; vague absolute in place of a number |

### `frontend/src/pages/guide/09-checking-this-site.md`

| Line | Quote | Rule |
|---|---|---|
| 11 | "This is not an official publication. This chapter explains how to verify…" | Restates the summary (L5) and chapter 01's disclaimer |
| 16-18 | "…returns the source USLM **verbatim** — not a re-serialisation, but the stored fragment as published — so you can compare… byte for byte." | Antithesis; "so you can"; emphasis flourish |
| 28 | "That last pair of numbers is the one worth understanding." | Presumes the reader; teaser with no content |
| 28-31 | "…is what makes the corpus 27 GB instead of hundreds." | Justifying clause; rhetorical contrast; paragraph-closer |
| 33-36 | "…because guids regenerate at every release point by design — hashing the raw XML dedupes nothing at all, which was measured rather than assumed: … **zero** were byte-identical…" | "because"; antithesis; war story as evidence; bold for drama |
| 38 | "One consequence you can see:" | Presumes the reader; announcing a count |
| 49 | "…which is [shown rather than smoothed away](/app/guide/02-reading)." | Antithesis; moralising |
| 65 | "Colour is checked separately, because a scan only sees the pages it is pointed at." | "because" clause |
| 91-97 | "Each specimen is the component itself…, rather than a picture of it."; "…so its citations resolve to nothing…"; "…so it is correct in whichever theme you are reading." | Antithesis; justifying clauses |
| 116-118 | "The set of statuses is not fixed — the source may publish one this site has never seen —…" | Antithesis ahead of the behaviour |

### Demo captions (edit in the chapters, then regenerate)

Captions live in the guide chapters' scenario `caption:` fields; `docs/demo/scenes.json` and the
`.vtt` are generated by `make demo-video`. The `scenes.json` lines below locate the offending
caption; fix it in the owning chapter.

| scenes.json line | Caption | Rule |
|---|---|---|
| 39 | "— and it is highlighted inside the whole section, never stranded out of context." | Dramatic absolute |
| 59 | "Reading order is preserved, so you can move through a chapter section by section." | "so you can" |
| 72-73 | "One click to the notes, past however many subsections are in between." / "The notes, without scrolling the length of the section to find them." | Presumes the reader's effort; the second restates the first |
| 96 | "The page names the release point it answered from — every page does." | Restates itself for emphasis |
| 117 | "The address keeps the provision — you move in time, not in the text." | Antithesis; aphorism |
| 127 | "…one entry per distinct text, not one per release point." | Antithesis |
| 138 | "…— the amendment, not the markup." | Antithesis |
| 147 | "One box takes a citation or a phrase — you do not have to say which." | Presumes the reader |
| 150 | "16 U.S.C. § 45f — no need to know the URL scheme at all." | Presumes the reader; "at all" |
| 181 | "The filter is written into the query, so the URL is the whole search." | Justifying clause |
| 203 | "— heading, status and opening words, without losing your place." | Restates the scene title |
| 225 | "Compact is in force, and the control now offers the way back." | Restates the action just shown |

### `frontend/src/pages/about.astro`

| Line | Quote | Rule |
|---|---|---|
| 38 | "Nothing here amends, replaces or interprets what they publish." | Absolute triple (borderline — it is a legal disclaimer; keep if wanted) |
| 61-62 | "The citation is human-readable and it still works later." | Aphoristic assertion |
| 103 | "If something here is wrong, that is where it will show." | Aphoristic closer |
| 112-113 | "…stored once, avoiding duplication. About 91%… because the Code republishes every title…" | "because" clause; sentence 2 restates sentence 1 |

### `frontend/src/pages/search/syntax.astro`

| Line | Quote | Rule |
|---|---|---|
| 60 | "You do not have to tell it which you meant — it reads what you wrote." | Presumes the reader; aphoristic tail |
| 66 | "…though only through the URL for now, and with a limit worth reading first." | Presumes the reader; teaser — and factually wrong (Tier 1 item 4) |
| 102 | Heading "Two things that will catch you out" | Teaser heading; count; the exact phrase the rules forbid |
| 127-131 | Both `lede` paragraphs open with framing rather than content; "…when you are not sure how a word is written." | Teaser construction; presumes the reader |
| 138-142 | "This site used to return all three, because it ran every search with a two-character-edit tolerance nobody asked for. In a body of law a different word is a different rule, so that tolerance is now something you request." | War story (ADR-0031's business); "because"; aphorism; editorialising |
| 198-201 | "This is the one place on the site where the answer is not yet complete, so both halves are set out below…" | Justifying clause; announces structure; absolute |
| 234-236 | "Usually easier than looking up a label." | Presumes the reader's preference |
| 269 | "One known gap, and it is small." | Presumes the reader's reaction; no factual content |
| 274 | "Those provisions are complete in the reader; it is the search index that holds one of the pair." | Cleft antithesis |
| 290-292 | "…not a real cross-reference index, and the results page says so rather than letting the answer pass for the finished thing." | Antithesis ×2; moralising |

### `README.md`

| Line | Quote | Rule |
|---|---|---|
| 3 | "…which is to say it is the citation you already know."; "built around one idea: **every provision… has an address…**" | Presumes the reader; epigram |
| 14 | "One citation, one address, two surfaces that cache and deploy independently." | Epigram |
| 22-23 | "…preview on hover rather than costing you your place." | Antithesis |
| 30-32 | "A claim that stops being true fails the build instead of sitting on a page misleading people — which is exactly what the search guide did for a fortnight, and the reason the design exists." | Antithesis; war story; justifying clause |
| 48-49 | "…the repo is arranged so that **every claim is checkable**" | Justifying clause; bold |
| 53-54 | "…is a matter of record rather than of memory." | Antithesis |
| 57-58, 95-96 | "re-parses the source XML for an independent recount instead of / rather than trusting the loader's own bookkeeping" | Antithesis — and the two lines are near-verbatim duplicates 38 lines apart; keep one |
| 60 | "**Behavior** — the test suite is the specification." | Epigram |
| 98-100 | "…explained rather than averaged away… shows every occurrence with a note instead of silently picking one." | Antithesis ×2 in one sentence |
| 104 | "One caveat worth knowing before you judge the results —" | Presumes the reader |
| 120-124 | "because a citation has one URL and `Accept:` decides…"; "`curl` needs `-L` because it now follows a redirect" | "because" clauses (the second is arguably load-bearing; judgement call) |
| 126-127 | "…waiting on an AWS identity and a domain name rather than on code" | Antithesis — and factually stale (Tier 2 item 18) |

---

## Verified correct — do not churn

- Corpus numbers agree everywhere they appear: 3,153 title-releases / 58 titles / 381 loaded
  release points / 65,938 sections / 5,466,652 pairs / 489,738 section_versions / 91.0% / 96,185,732
  guid_map rows / 27 GB — across README:88-93, CLAUDE.md, deploy-status:204-211, guide 03/07/09,
  about.astro. The index arithmetic on `syntax.astro:263-274` (489,578 = 489,738 − 160; 65,929 =
  65,938 − 9; 423,649 superseded) is internally consistent.
- Guide 02's shortcut table matches `shortcuts.ts` exactly — all 13 bindings, `j`=previous /
  `k`=next included; the footer's `#keyboard-shortcuts` anchor resolves; the dialog and
  `/app/design` render the same data and cannot drift.
- Guide 03's release-switcher section already matches ADR-0056: the `<details>` summary, "Newest —
  follows new releases", provision preserved across a switch, the five-minute release-list cache.
- Guide 04's redline claims are all correct: links dropped, whitespace-only changes invisible in
  the reading view and visible in the source view, `?source=1`, one history entry per distinct
  text.
- Guide 06's density section is correct, including constant characters-per-line across densities.
- README's corpus table, backfill figures (3,153 ok / 44 unavailable / 9.7 GB) and all 17 relative
  links are correct; every command README names exists in the Makefile.
- `params.py`'s `ReleaseParam`/`DateParam`/`FormatParam` descriptions match behaviour; guide 08's
  claims about `/app/docs`, `/docs` and `/redoc` are accurate.
- The guide ratchet accounts for every route and every ADR through 0056; `docs/ia-map.md` is
  current apart from item 24.
- `46rem` appears only as the labelled superseded value; the `--measure` chain
  (`calc(38 * var(--reading-size))`) is reconciled through ADR-0054 everywhere it is discussed.

## Constraints for the fix session

- Guide edits must not change ` ```scenario ` block semantics: `tests/e2e/guide.spec.ts` executes
  them and `frontend/tests/guide.test.ts` checks captions and the ≤360 s narration total. Caption
  fixes go in the chapters' `caption:` fields; `make demo-video` regenerates the committed
  `scenes.json` and `.vtt` (the mp4 is gitignored).
- Guide prose follows Documentation duties 7: behaviour, not rationale. Several Tier 1 items
  (7, 8, 14) must land as flat statements of behaviour, and the Tier 5 rewrites must not introduce
  new justifying clauses while removing old ones.
- After guide or syntax-page edits: `make test-web` (ratchet) and the guide spec under
  `make test-e2e` (needs `make dev-all` running). After Tier 4 code edits: `make test`, then eyeball
  `/docs` and `/app/docs`. README/PLAN/GETTING-STARTED edits need no suite.
- Duty 6 still applies during the fixes: a Tier 4 change that alters user-visible API behaviour or
  its description updates guide 08 in the same commit.
- The fix session ends with its own BUILDLOG entry; a consequential decision (for example whether
  guide 08 names the auth routes) gets an ADR.
