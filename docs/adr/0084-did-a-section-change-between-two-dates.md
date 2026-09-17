# ADR-0084 — A section's history between two dates, from the API, the page and the search box

**Status:** accepted (2026-09-16)

**Task:** A legislative researcher wants to check whether a Code section changed between two
dates. The API should answer it; the version history page should ask it; the search box should
lead there.

**Builds on:** ADR-0003 (a date resolves to the newest release point on or before it), ADR-0007
(the content hash), ADR-0016 and ADR-0066 (the diff and its memo), ADR-0023 (the box parses no
citation of its own), ADR-0026 (the reader's redline is over the reading text), ADR-0029 (the
diff's budget), ADR-0074 (every transition has a kind), ADR-0075 (the history page).

## Context

The version history answered "when did this section change?" but not "did it change between
these two dates?", which is the question a researcher tracking a provision across a session of
Congress actually asks. Answering it by hand meant reading the timeline's release-point labels,
looking each up on `/app/releases` for its date, picking the pair that bracket the dates, and
opening a redline. The timeline entries carried labels alone; a release point is named for a
public law, not a date.

The pieces existed: `?date=` resolves a date to a release point everywhere; `SectionResult`
carries a guid-stripped `content_hash` that is stable across release points for one text;
`versions()` maps every entry to the release points publishing it; the diff route and the
reader's redline compare any two release points. Nothing composed them.

## Decision

### 1. The versions route takes a date window

`GET /api/v1/sections/{identifier}/versions?from=&to=`. Each date resolves as `?date=` does; `to`
defaults to today and needs a `from`; a reversed window is a 422. The response gains `window`:
each end's date, the release point it resolved to, whether the section exists there, the release
point the text was served from with the section route's own `note`, `changed`, `change_kinds` and
the guid-stripped `diff`. `versions` is cut to the entries in force at some release point in the
window — the one in force at `from`, then each arrival. A window at both of whose ends the
section is absent is a 404 naming where it is first published.

Every entry, windowed or not, now carries `first_release` and `last_release` — the earliest and
newest release points publishing that text, each with its currency date. `releases` stays a list
of labels; `first_seen` stays for compatibility.

`changed` is the two ends' content hashes compared, never the count of arrivals: recurring
content (ADR-0021) can arrive and leave inside a window and read the same at both ends.

### 2. The cut is one pure function, in storage

`versions_in_window(versions, start, end)` in `storage/repository.py` walks the release points
each entry is mapped to, by `seq`, and returns the baseline and the arrivals. It is pure so every
`Repository` implementation shares it, and it lives in storage because which text was in force
when is version resolution. `SectionVersionInfo` gains `published`, the mapped release points as
refs.

### 3. The windowed route shares the diff's budget

A dependency applies `_limit_diff` only when `from` or `to` is present. The plain timeline stays
unlimited and Redis-cached. Both routes memoise the redline on the release points the texts were
*served from* rather than the labels asked for: the text is a function of the served-from release
point, so two requests resolving to one pair share one redline, and a date-resolved pair — which
no request pinned — is as cacheable as a pinned one.

### 4. The history page asks the question and answers it itself

`/app/versions/…` carries a "Between two dates" form: two text fields, a plain GET back to the
page, the view in force as a hidden field, an empty To running to today. The answer renders above
the history: the verdict, the kinds, the two ends with the section route's note or the release
point's caveat, the versions in force as the timeline, and the reading-text redline with a link to
`/app/diff`.

The page does not call decision 1. It reads the plain timeline, fetches the section at each date
as any `?date=` request does, cuts the timeline with `versionsInWindow` in `lib/versions.ts` —
the same walk as `versions_in_window` — and diffs the two reading texts. The reason is the one
`/app/diff` already gave for building its own redline: the API's windowed form shares a
per-caller budget sized for a person, and the reader renders from one address for everyone. The
middleware puts the windowed page in the diff's bucket, and an empty `?from=`/`?to=` is stripped
by the same 307 that strips an empty `?release=`.

### 5. `history` is a prefix on the one box

`history <citation>` lands on the section's version history; `history <citation> from <date> to
<date>` lands on the answer. `between … and …` and `since <date>` read the same way. The prefix is
lifted in `lib/query.ts` beside `cites` and the citation still goes to `/api/v1/citation`
(ADR-0023). A subsection opens its section's history; a title or chapter renders a message with a
link to it; a `history` with no citation after it is told what it needs rather than searched.

## Consequences

**The cut exists twice.** Python and TypeScript walk the same map with the same rule, tested on
the same shapes (`tests/test_versions_window.py`, `frontend/tests/versions.test.ts`). The
alternative was the reader calling a route it would exhaust for everyone.

**`change_kinds` describes arrivals, not returns.** Recurring content that comes back inside a
window contributes its own recorded kind — `initial` for the oldest text — which describes its
first arrival, not its return. `changed` is unaffected; it reads the ends.

**A window's `to` end is usually not exact.** A date resolves to the newest release point on or
before it, which for a title unchanged since is not ingested, so the end carries the section
route's served-from note. That is the same sentence the section page shows and is printed rather
than suppressed.

**Cost.** The windowed API route is two release resolutions, two section reads, one `versions()`
and a memoised diff. The page is one more section fetch than `/app/diff` and one `documentDiff`,
under the diff's middleware bucket. `/app/versions` ships no script; its JS budget is unchanged.
The a11y matrix gains one route entry (seven scans); `make shots` gains one page.

**Measured on the fixture corpus:** § 2201 between 06/12/2026 and 07/12/2026 answers `changed:
true`, `change_kinds: ["text"]`, 11 non-equal ops; § 45f answers `changed: false` with one entry
in the window. The guide's scenarios (`versions-between-dates`, `history-prefix-dates`,
`api-versions-window`) hold both.
