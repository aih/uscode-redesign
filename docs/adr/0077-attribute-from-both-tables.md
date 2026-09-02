# ADR-0077: Attribute a change from the row of its own kind, and consult the Editorial Classification Change Table

**Date:** 2026-09-02 · **Status:** Accepted · **Amends:** ADR-0074 (decisions 5 and 6) · **Spec:** `docs/version-semantics-spec.md`

## Context

ADR-0074 attributes every version transition by intersecting two sets: the Public Laws that
arrived with the transition (incorporated at the arriving release point and not at the departing
one) and the laws OLRC's classification tables record against the section. It recorded three
things it did not do, and this session was asked to review the logic and take them up:

1. **A transition was `classified` only by a text row.** A note row in the window wrote a law row
   flagged `is_note_classification` and decided nothing, whatever the transition's kind. That is
   right for a `text` change, where a note classification is not evidence the statutory text
   changed, and wrong for a `notes` change, where a note row is exactly the evidence: the tables
   saying a law's provision is set out as a note under this section, and that law arriving with
   the change that added the note. Corpus-wide 7,186 `notes` transitions carried a law row and
   every one of them read `none`.

2. **The Editorial Classification Change Table was not consulted.** OLRC publishes it beside the
   classification tables (ADR-0067 loads it: 21 rows across two documents). Each row records a
   provision OLRC moved — from a note to a section, or between sections — while classifying a new
   law, with the former classification, the new one, the provision moved and the law that
   prompted the move. A section created or emptied that way changes text with no amendment to it,
   and the tables' rows for the moved provision point at its *former* home. Such a transition read
   `none`, and the reader said "No classifying statute recorded", which is true and misleading:
   OLRC did record why.

3. **The report could not say where the changes were.** It gave the four kinds' shares and nothing
   about which release points the transitions arrive at. The 75.1% `structure` figure is the
   corpus's single largest fact and the page could only describe it in the abstract; and ADR-0076
   found the page writing the corpus's coverage — 58 titles, 381 release points, `119-102not101`,
   12 July 2026 — by hand because the report did not carry it.

The rest of the review confirmed the logic. The digests, the ordering by earliest mapped release,
the incorporated-set window, the mid-corpus `initial` departure and both halves of `concurrent`
are as specified and as measured; nothing there is changed.

## Decisions

**1. `classified` means a row of the transition's own kind.** A `text` or `initial` transition is
`classified` by a text row in the window, as before. A `notes` transition is `classified` by a
note row. A `structure` transition matches nothing of either kind (measured at 0% in ADR-0074's
finding 5) and stays `none`. `_attribute` takes the kind; nothing else in the rule moves.

**2. The ECCT is read, and produces a third attribution value.** For every section in a batch the
ECCT's rows are matched on either side — former classification or new — through
`ecct_key(identifier)`, the inverse of `derive_usc_identifier` through the same
`normalize_section`, so the EN DASH the corpus writes meets the hyphen the table writes
(gotcha 17). A row whose *prompting* law is in the window writes a law row for that law, flagged
`in_ecct` and carrying `ecct_move` (`42:294t nt → 42:294u new`), with `ed chg` — OLRC's own
cross-reference token for the ECCT — as its action. A transition with such a row and no
classification row of its own kind is **`editorial`**. The vocabulary is therefore
`classified | editorial | none`, in that order of precedence.

The prompting law is the one attributed, not the provision moved: the affected provision's law
(Pub. L. 117-105 in the one row of the current session) was incorporated years before the move
and is in no window, while the prompting law (Pub. L. 119-75) is what arrived. The affected law is
in the move text.

**3. The two columns are additive and derivable.** Migration `c7e2a9f4b1d0` adds `in_ecct`
(`NOT NULL DEFAULT false`) and `ecct_move` (nullable) to `section_version_change_laws`; every
carrier — `VersionLawRef`, `VersionLawOut`, the reader's `VersionLaw` — gains them with defaults,
so an older API and a newer reader, or the reverse, keep working. `version-changes --reattribute`
recomputes the attribution and the law rows without touching the flags, which is the repair for a
corpus computed before this ADR. `update-corpus.sh` already runs it after a classification load
that changed a table, and the ECCT is one of those files.

**4. The reader says which table spoke.** An `editorial` entry's summary line names an editorial
reclassification; its chips are led by *Editorial reclassification prompted by* rather than
*Amended by*; each chip carries `ed chg`, and the move is written after it in the interface face.
A `notes` entry that is now `classified` keeps its sentence — *Notes updated* — and gains chips it
did not have.

**5. The report carries the analysis the page needs.** `build_report` adds:

- `attribution_by_kind` — every kind × every attribution value, zero-filled, so a reader of the
  artifact never has to know which values exist; `notes_classified` and its share; `editorial`;
  `ecct_law_rows`.
- `by_release` — arrivals per release point per kind, in `seq` order. A converter change is one
  release point receiving a `structure` arrival for nearly every section of every title it
  republished; an amendment cadence is `text` arrivals spread across the release points that
  incorporated them. The page shows the ten release points with the most arrivals of each and the
  share those ten hold.
- `coverage` — titles, release points known, release points loaded, and the newest loaded release
  point with its currency date. The four hand-written facts ADR-0076 named come off the page.

All of it is optional to the reader: an artifact written before this ADR lacks the keys, and the
page renders the tables it has. `frontend/src/data/version-changes.json` is still the committed
copy and still lacks them, because regenerating the artifact takes the full corpus
(`version-changes --recompute --report`, 7m50s on the development machine, 21m35s on the box);
that run and `make sync-verification` are the next session's first act.

**6. The explanation is rewritten around three questions.** The page and the guide now say: a
version is one distinct XML; a transition is asked, in order, whether the statutory text changed,
whether the notes did, and otherwise is `structure`, which is the stored name for *only the XML
differs*; the laws that arrived are a set difference on the release points' names; and each
transition is one of three things according to which table names one of those laws. `concurrent`
is explained by what produces it — XML that returns to an earlier form, kept as one version rather
than one per stretch of time — rather than by the arithmetic it breaks.

## Declined

**Renaming `structure`.** The stored value is in 489,738 rows, the API contract, `data-change-kind`
on every version-history entry and three test suites. The word is kept and defined in one sentence
wherever it appears.

**A row per era.** `concurrent` at 18.3% is the cost of one row per distinct XML when XML recurs.
Representing recurrence properly is one transition per change of mapped version along the release
sequence, which changes the count of transitions, every share on the page and the shape of
`section_version_changes`. It is the improvement ADR-0074 already named as its own ADR and is
still that; this ADR does not start it.

**Attributing `structure` transitions.** The ECCT could in principle name one — a move that left
the XML identical — but nothing a reader sees changed, and the measured match rate for
classification rows on that kind is 0%.

## Consequences

- `attribution` has three values. Anything that switched on two — `changeSummary`, `lawsLabel` —
  handles the third; anything that counted `classified` against `text` alone still does, and the
  new counts sit beside it.
- On the CI fixture corpus nothing is `editorial` and nothing is `notes`-classified: Title 16 at two
  release points has two text transitions and the one ECCT fixture row moves a Title 42 provision.
  The rule is tested purely, on synthetic rows, and end to end only by the recompute over the full
  corpus that is still owed.
- The ECCT covers the 119th Congress and records the moves made while classifying new laws; OLRC
  says the moves made while preparing a main edition or supplement are accounted for in Table III
  instead. The page's limitation says both.
- `_ecct_rows` reads the whole table once per batch of 200 sections and matches in Python. At 21
  rows that is nothing; at a table three orders of magnitude larger it would want an indexed
  query, and the indexes for it exist (`ix_ecct_entries_*`).
