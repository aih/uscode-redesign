# ADR-0066 — Compare from the section header, and stop diffing the guids

**Status:** accepted (2026-08-11)

**Task:** workstream B, B5 — compare any provision across release points, in two clicks.

**Amends:** ADR-0016 (the API redline drops `@id` by default), ADR-0026 (the reader's redline gains a
focus), ADR-0044 (a second control that must not drop the provision).

## Context

The machinery for comparing two release points has existed since Day 4. What was missing was a way
in and a cost that could be paid.

**`/app/diff` was two hops from the text it compares.** Section → *Version history* → pick two
release points → redline. Three clicks to answer the question a versioned reader asks most often
about a provision already on screen, and the middle page exists to answer a different question.

**"The previous release point" is the wrong default.** The Code is republished in full at every
release point and few titles change at any of them (gotcha 10), so the release point before the one
on screen almost always holds character-for-character the same section. A "compare with the
previous release" control would, most of the time, produce an empty redline and teach the reader
that the feature does not work.

**The API's redline spent about half its time on identifiers.** `@id` guids regenerate at every
release point *by design* (ADR-0003, gotcha 1) — they are the one part of the XML guaranteed to
differ between any two release points whether or not a word of law changed. `docs/verification/loadtest.json`
measured the endpoint at ~0.45 rps, failing entirely past ~10 concurrent, and it is the tightest
budget ADR-0029 hands out.

## Decision

### 1. "Compare with…" on the section header, defaulting to the last release point that held different text

A `<details>` in the page body. Closed it is one chip; open it offers one link — the default — and a
`<select>` of every older release point as a plain GET form. Same shape as `ReleasePicker`
(ADR-0056), and for the same reasons: a native disclosure costs no script, and a GET form produces a
URL.

The default is computed by `lib/compare.ts` from the section's own version timeline: `/versions`
groups release points by content hash in order, so the group *before* the one holding the release on
screen ends at the last release point with different text. One click, and because it is a link
rather than a form it is also a URL to paste.

**Not `content_first_seen`,** which is already on the section response and would have cost no call at
all. It does not mean what the name suggests on real data: § 45f's newest group reports
`first_seen: 119-99` while its own `releases` run from `117-80`, because that field follows the
stored fragment's `first_release_id` and an incremental load can attach an earlier release point to
a row without lowering it (ADR-0007's dedupe, gotcha 15). `releases` comes from
`section_release_map` and is authoritative. This was found by shipping the wrong version first and
watching the default produce "No changes".

### 2. The comparison is a URL, and it keeps the provision

`diffHref(identifier, from, to, provision)` carries a sub-section path as `?at=/c/5` — a query
parameter and not a fragment, because the server has to act on it and a fragment never leaves the
browser. Both the default link and the form carry it. ADR-0044 found the release switcher dropping
the provision on every switch; this is the same failure available to a second control, and it is
tested rather than remembered.

### 3. A provision-level comparison marks the provision inside the whole section's redline

`ReadingBlock` gains `owner`: the `@identifier` of the nearest enclosing element that carries one,
inherited down, so a `<content>` under `(c)(5)` belongs to `(c)(5)`. `DiffLine` carries it through,
and `diffLinesHtml(lines, focus)` marks the matching run and anchors its first line `#diff-focus`.

The whole section is still rendered. That is ADR-0001's rule — a request for `/c/5` is answered with
the section, so the reader never loses context — applied to a comparison. Above the redline, a line
says which provision is marked and how much of the change is inside it, including when the answer is
**none**: a reader who asked about one subsection should be told plainly that this amendment did not
touch it, rather than left to scan a redline for a highlight that is not there.

Matching is the identifier itself or a `/`-delimited descendant, so `/c/5` does not claim `/c/50`.

### 4. The API diff drops `@id` by default, and caches

`?guids=strip` is the default and `?guids=keep` restores the verbatim behaviour ADR-0016 wrote. The
response reports which it gave, so a caller never has to guess.

Stripping is an lxml parse and re-serialise, not a regex: `id="…"` can occur inside quoted statutory
text, and a textual substitution could edit one side of a comparison and not the other — a redline
reporting a change nobody made. A fragment that does not parse is returned unchanged, because an
optimisation that can fail a request is worse than the cost it saves.

Results are memoised on `(identifier, resolved from, resolved to, mode)`, bounded at 256 entries, and
**only when both release points resolved exactly**. An unpinned label names a different release point
the moment a newer one is loaded, so caching under it would serve a redline for a pair the URL no
longer means — the same distinction ADR-0018 draws for `Cache-Control`.

`make diffcost` measures it (`docs/verification/diffcost.json`), timing the diff in process because
the endpoint's own limiter is five in a burst and the limiter is not what is being measured:

| section | fragment | `keep` | `strip` | |
|---|---|---|---|---|
| `/us/usc/t16/s45f` | 25,742 B | 492.1 ms, 124 ops | 3.3 ms, 5 ops | 149× |
| `/us/usc/t16/s1801` | 97,921 B | 500.9 ms, 195 ops | 3.5 ms, 3 ops | 142× |
| `/us/usc/t16/s1536` | 91,999 B | 4,063.9 ms, 362 ops | 1.8 ms, 5 ops | 2,242× |
| `/us/usc/t16/s668dd` | 161,729 B | 3,216.1 ms, 399 ops | 7.2 ms, 3 ops | 447× |

It is not a constant factor, and that is the interesting part: diff-match-patch short-circuits on a
common prefix and suffix, so removing the guids is the difference between two nearly-identical
strings and two strings that differ every few hundred bytes.

## Consequences

### What this costs

**A section page makes a sixth API call.** `/versions` joins the existing `Promise.all`, so it is
concurrent with the five already there and adds nothing to wall clock — the finding ADR-0043's
fourth call was measured on. Warm, it answers in ~8 ms, the same order as the section fetch itself.
It is allowed to fail: without it the "Compare with…" default is missing and the reader still has the
statute.

**`ops` no longer reassemble the stored XML by default.** That was ADR-0016's contract and
`guids=keep` still honours it, under a test that reassembles both sides byte for byte. A caller who
was relying on the default and does not read the `guids` field will get a different answer than
before. This is a demo API with no versioning story; the alternative was leaving the default slow
and the redline dominated by content that cannot mean anything.

**The diff cache is per-process**, honest for ADR-0020's single box and wrong for a second instance
— exactly as ADR-0029's rate limiters already are. It is now the second thing here that would want
a shared cache, and the first that would be merely less effective rather than incorrect.

**`docs/verification/loadtest.json` is stale for `/app/diff` and `/api/v1/sections/…/diff`** and was
already. It has never been regenerated since ADR-0026 moved the reader off the endpoint, and it now
also predates this. Regenerating it needs the deployed box (`make loadtest BASE=…`).

**Nothing pages the select.** A title with 381 release points puts 380 `<option>`s in the markup of
every section page, which is the same debt `docs/ia-map.md` already records against the release
switcher, now carried twice.

### What it buys

A comparison is one click from the provision, it lands on a redline that shows something, and the
subsection the reader was reading is marked inside it. The API's own redline went from seconds to
milliseconds and from hundreds of ops to a handful, and the ops that disappeared were all
regenerated identifiers.

### Traps hit here

**A field named `content_first_seen` is not when the content was first seen.** See decision 1. The
version timeline's `releases` is the authoritative record and the only one that survived contact
with the corpus.

**The reader's default link and the redline it reaches must be checked together.** The first version
of this shipped a control whose default produced "No changes" on § 45f, which looks exactly like a
broken feature and is exactly what a "compare with the previous release point" control does. The
test asserts the redline is not empty, not merely that the link exists.

**USWDS gives `.usa-button` `width: 100%` below 480px** — ADR-0056's trap, met again on a second
two-control row, where it would have taken the whole row and squeezed the select to nothing.
