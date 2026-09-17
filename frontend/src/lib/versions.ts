/**
 * What the version timeline shows, and what it folds away (ADR-0075).
 *
 * The timeline groups a section's history by ADR-0007's content hash, so it
 * records a new entry whenever the stored XML changed at all. Corpus-wide that
 * is 75.1% structure-only and 17.1% notes-only against 7.8% statutory text
 * (`docs/verification/version-changes.json`). ADR-0074 stores which of the
 * three each transition was; this module turns that into the two views the
 * page renders — the amendments, and everything recorded.
 *
 * Both views are one document: every entry is in the DOM, the list root carries
 * `data-view`, and CSS hides what the view does not show. So the arithmetic
 * here runs once per entry and produces both answers at once — the run of
 * release points an entry's own group carried, and the run it carries once the
 * groups the default view hides are folded into it.
 */
import type { Release, Section, VersionEntry, VersionLaw } from "./types";

export type VersionsView = "text" | "all";

/** `?view=all` on `/app/versions/…`. `text` is the default and is written into
 *  no URL, so the address of the default view is the address it always had. */
export const VERSIONS_VIEW_PARAM = "view";

export function readVersionsView(raw: string | null | undefined): VersionsView {
  return raw === "all" ? "all" : "text";
}

/**
 * Whether the default view shows this entry.
 *
 * The statutory changes, plus `initial` — the oldest entry is where the
 * history starts, and a view that dropped it would begin in the middle.
 */
export function isStatutoryEntry(entry: VersionEntry): boolean {
  return entry.change_kind === "initial" || entry.change_kind === "text";
}

/**
 * Whether every entry carries ADR-0074's annotations.
 *
 * A corpus loaded but not back-filled answers `change_kind: null` throughout,
 * and one back-filled before an incremental load can answer it on some entries
 * and not others. Either way there is no honest default view, so the page shows
 * everything and says so.
 */
export function isAnnotated(entries: VersionEntry[]): boolean {
  return entries.length > 0 && entries.every((entry) => entry.change_kind != null);
}

export interface TimelineRow {
  entry: VersionEntry;
  /** `initial` / `text` / `notes` / `structure`, or `unknown` with no change
   *  row. The value of the `data-change-kind` attribute the CSS filters on. */
  kind: string;
  /** Whether the default view shows this row. */
  statutory: boolean;
  /** The release point this text starts at — `releases[0]`, not `first_seen`,
   *  which follows the stored fragment's `first_release_id` and can name a
   *  later release point than the group's own earliest (ADR-0066). */
  start: string | null;
  /** The release points this entry's own group carried. */
  releases: string[];
  /** The same, extended through the groups the default view hides after it, so
   *  the "unchanged through" run of a visible entry is not cut short by an
   *  entry the reader cannot see. Equal to `releases` in the all view's terms
   *  and for a row the default view hides. Sorted by release-point order when
   *  `timelineRows` was given one — the folded groups interleave whenever the
   *  content recurs, so concatenating them is not a sorted list. */
  effectiveReleases: string[];
  /**
   * The release point to compare against: the last release of the entry before
   * this one, so the redline spans one transition. **Null when that release
   * point is not strictly older than `start`.**
   *
   * One value serves both views. The entries the default view hides sit between
   * a shown entry and the one above it, and they are folded into that one's
   * run, so the end of the previous *shown* entry's effective run is the last
   * release of the entry immediately before — the same label either way.
   *
   * The window a transition arrives across can run backwards: ADR-0074 records
   * one shape of it as `concurrent`, where the departing group is still mapped
   * at or after the arriving group's first release. `/app/diff` reads `?from=`
   * and `?to=` in the order it is given them, so a link built from such a window
   * renders every insertion as a deletion — measured at **39,645 of 423,800
   * transitions**, 58 of them a release point against itself. No comparison is
   * offered there; the From/To picker under the timeline still is.
   */
  from: string | null;
  /** There is an entry before this one and no comparison is offered against it,
   *  because the window runs backwards. The timeline says so rather than
   *  leaving a gap where every other entry has a link. */
  withheld: boolean;
}

/**
 * Where a release point sits in the global order, by label.
 *
 * Labels do not sort (gotcha 4), so ordering needs the inventory's `seq` and
 * cannot be recovered from the strings. A lookup that answers `undefined` for a
 * label — an incomplete release list, or a page with none at all — leaves the
 * order unknown, and both callers below degrade rather than guess.
 */
export type ReleaseOrder = (label: string) => number | undefined;

/** `seq` by label, from the release list `/app/versions` fetches for the title. */
export function releaseOrder(releases: { label: string; seq: number }[]): ReleaseOrder {
  const seqs = new Map(releases.map((release) => [release.label, release.seq]));
  return (label) => seqs.get(label);
}

/**
 * One row per entry, carrying both views' answers.
 *
 * `entries` arrive oldest first, which is the order the page renders and the
 * order the repository guarantees (earliest mapped release, ADR-0066).
 *
 * `order` places a release-point label in the global sequence. Without it the
 * folded run stays in concatenation order and a comparison is offered only where
 * ADR-0074's `concurrent` flag is clear — the flag covers every backwards window
 * and 37,951 forward ones besides, so it is the conservative answer and not the
 * exact one.
 */
export function timelineRows(entries: VersionEntry[], order?: ReleaseOrder): TimelineRow[] {
  const annotated = isAnnotated(entries);
  const rows: TimelineRow[] = entries.map((entry, index) => {
    const releases = entry.releases ?? [];
    // An unannotated corpus has no default view to compute, so every row is
    // treated as shown: the page renders the all view and hides nothing.
    const statutory = annotated ? isStatutoryEntry(entry) : true;
    const previous = index > 0 ? entries[index - 1] : null;
    const previousReleases = previous?.releases ?? [];
    const start = releases[0] ?? null;
    const from = previous ? (previousReleases[previousReleases.length - 1] ?? null) : null;
    const forward = isForward(from, start, entry, order);
    return {
      entry,
      kind: entry.change_kind ?? "unknown",
      statutory,
      start,
      releases,
      effectiveReleases: [...releases],
      from: forward ? from : null,
      withheld: previous !== null && !forward,
    };
  });

  // Fold each hidden run into the shown row above it.
  let lastShown: TimelineRow | null = null;
  for (const row of rows) {
    if (row.statutory) lastShown = row;
    else if (lastShown) lastShown.effectiveReleases.push(...row.releases);
  }

  if (order) {
    for (const row of rows) sortReleases(row.effectiveReleases, order);
  }

  return rows;
}

/** Whether a redline from `from` to `start` runs forwards in time. */
function isForward(
  from: string | null,
  start: string | null,
  entry: VersionEntry,
  order?: ReleaseOrder,
): boolean {
  if (!from || !start) return false;
  const before = order?.(from);
  const after = order?.(start);
  if (before !== undefined && after !== undefined) return before < after;
  // No order to read. `concurrent` is the only signal left, and it is set on
  // every backwards window, so trusting it costs some comparisons and offers
  // none that run the wrong way.
  return entry.concurrent !== true;
}

/** In place, by release-point order; a label the order does not know keeps its
 *  position relative to the labels it cannot be compared with. */
function sortReleases(releases: string[], order: ReleaseOrder): void {
  releases.sort((a, b) => {
    const left = order(a);
    const right = order(b);
    if (left === undefined || right === undefined) return 0;
    return left - right;
  });
}

export interface VersionCounts {
  /** Entries the default view shows. */
  statutory: number;
  /** Every recorded entry. */
  all: number;
  /** Transitions that changed the statutory text: what the default view's name
   *  counts, and what the section page's history link prints. Below
   *  `statutory`, which also counts the oldest entry. */
  amendments: number;
  /** Release points this section is in the Code at, across every entry. */
  releases: number;
}

export function versionCounts(entries: VersionEntry[]): VersionCounts {
  const annotated = isAnnotated(entries);
  const statutory = annotated ? entries.filter(isStatutoryEntry).length : entries.length;
  return {
    statutory,
    all: entries.length,
    amendments: entries.filter((entry) => entry.change_kind === "text").length,
    releases: entries.reduce((total, entry) => total + (entry.releases?.length ?? 0), 0),
  };
}

/**
 * `Pub. L. 119–102`, with the EN DASH the Code and the classification tables
 * both write (gotcha 17 is about section numbers; the same dash is the
 * convention for a public law citation).
 */
export function lawLabel(law: VersionLaw): string {
  return `Pub. L. ${law.pl_congress}–${law.pl_num}`;
}

/** The lookup query a law chip links by: a hyphen, because that is what a
 *  reader types and what the classification tables' own `pl` values carry. */
export function lawQuery(law: VersionLaw): string {
  return `Pub. L. ${law.pl_congress}-${law.pl_num}`;
}

/**
 * The source's action words for a law, minus the empty string.
 *
 * The empty string is a plain amendment and needs no word beside a citation the
 * page has already called an amendment; `new`, `repealed` and `tr to` say
 * something the citation does not.
 */
export function lawActions(law: VersionLaw): string[] {
  return [...new Set(law.classification_actions ?? [])].filter((action) => action !== "");
}

/**
 * What the chips under an entry are a list of.
 *
 * ADR-0074 attributes every transition, not only the text ones: 7,186 `notes`
 * transitions and 81 `structure` transitions carry a law corpus-wide. A chip
 * beside "Notes updated" reads as an amendment unless the row says what it is,
 * so the lead-in is the sentence that makes the list true for its own kind.
 */
export function lawsLabel(entry: VersionEntry): string {
  return entry.change_kind === "text"
    ? "Amended by"
    : "Public laws recorded for this change:";
}

/**
 * The sentence under an entry saying what kind of change arrived with it.
 *
 * The oldest entry gets one too: the default view lists it beside the
 * amendments without it being one, and the count beside that view's name is the
 * amendments alone, so the row has to say what it is.
 *
 * Null for an entry of a corpus with no change rows.
 */
export function changeSummary(entry: VersionEntry): string | null {
  switch (entry.change_kind) {
    case "initial":
      return "The oldest text this site holds for this section.";
    case "text":
      return entry.attribution === "classified"
        ? "Statutory text changed."
        : "Statutory text changed. No classifying statute recorded.";
    case "notes":
      return "Notes updated. The statutory text is unchanged.";
    case "structure":
      return "XML/metadata only. Neither the statutory text nor the notes changed.";
    default:
      return null;
  }
}

// ------------------------------------------------------- a window of dates

/** `?from=` / `?to=` on `/app/versions/…` (ADR-0084). */
export const VERSIONS_FROM_PARAM = "from";
export const VERSIONS_TO_PARAM = "to";

/** What the reader asked for, as typed: the API validates the form. */
export interface WindowRequest {
  from: string;
  to: string | null;
}

/** Read the two date fields off the page's URL. `from` alone is a window to
 *  today; `to` alone is not a window and is reported as such by the page. */
export function readWindowRequest(params: URLSearchParams): WindowRequest | null {
  const from = (params.get(VERSIONS_FROM_PARAM) ?? "").trim();
  const to = (params.get(VERSIONS_TO_PARAM) ?? "").trim();
  return from ? { from, to: to || null } : null;
}

/**
 * The section's history between two release points, cut from the timeline
 * by release-point order — the reader's copy of `versions_in_window` in
 * `storage/repository.py`, over the same map.
 *
 * `versions` is the entry in force at `start` (which may have begun before
 * it) followed by each entry that arrived inside `(start, end]`, oldest first.
 * `kinds` are the kinds of those arrivals, each once. `order` places a label
 * in the global sequence; an entry whose every label the order does not know
 * cannot be placed and is left out, which the page reports rather than hides.
 */
export interface VersionWindowCut {
  versions: VersionEntry[];
  kinds: string[];
  /** Whether every entry could be placed. */
  complete: boolean;
}

export function versionsInWindow(
  entries: VersionEntry[],
  start: { seq: number },
  end: { seq: number },
  order: ReleaseOrder,
): VersionWindowCut {
  const bySeq = new Map<number, VersionEntry>();
  let complete = true;
  for (const entry of entries) {
    let placed = false;
    for (const label of entry.releases ?? []) {
      const seq = order(label);
      if (seq === undefined) continue;
      bySeq.set(seq, entry);
      placed = true;
    }
    if (!placed) complete = false;
  }

  let baseline: VersionEntry | null = null;
  let baselineSeq = -1;
  for (const [seq, entry] of bySeq) {
    if (baselineSeq < seq && seq <= start.seq) {
      baseline = entry;
      baselineSeq = seq;
    }
  }

  const sequence: VersionEntry[] = baseline ? [baseline] : [];
  for (const seq of [...bySeq.keys()].sort((a, b) => a - b)) {
    if (seq > start.seq && seq <= end.seq) {
      const entry = bySeq.get(seq)!;
      if (sequence[sequence.length - 1] !== entry) sequence.push(entry);
    }
  }

  const kinds: string[] = [];
  for (const entry of baseline ? sequence.slice(1) : sequence) {
    if (entry.change_kind && !kinds.includes(entry.change_kind)) kinds.push(entry.change_kind);
  }
  if (!baseline && sequence.length > 0 && !kinds.includes("initial")) kinds.unshift("initial");

  return { versions: sequence, kinds, complete };
}

/**
 * One end of the window as the page resolved it, in the fields the result
 * panel prints — built from the section fetched with `?date=`, or from the
 * release list alone when the section was not in the Code by then.
 */
export interface WindowEnd {
  /** As typed. */
  date: string;
  /** The release point the date resolved to: `section.release` when the
   *  section exists, otherwise the release list's answer, or null when the
   *  date precedes the first release point. */
  release: Release | null;
  /** The release point the text was read from (gotcha 10, ADR-0083). */
  servedFrom: Release | null;
  absentFrom: Release | null;
  exists: boolean;
  num: string | null;
  heading: string | null;
  status: string | null;
  contentHash: string | null;
  /** The section route's own sentence when the answer is not literally the
   *  release point the date names. */
  note: string | null;
}

export function windowEnd(date: string, section: Section | null, fallback: Release | null): WindowEnd {
  return {
    date,
    release: section?.release ?? fallback,
    servedFrom: section?.served_from ?? null,
    absentFrom: section?.absent_from ?? null,
    exists: section !== null,
    num: section?.num ?? null,
    heading: section?.heading ?? null,
    status: section?.status ?? null,
    contentHash: section?.content_hash ?? null,
    note: section?.note ?? null,
  };
}

/** The newest release point on or before a date, from the release list: the
 *  same rule `resolve_release` applies, for the end of a window where the
 *  section does not exist and no section fetch can name one. */
export function releaseOnOrBefore(releases: Release[], date: string): Release | null {
  const iso = isoDate(date);
  if (!iso) return null;
  let best: Release | null = null;
  for (const release of releases) {
    if (release.currency_date <= iso && (best === null || release.seq > best.seq)) best = release;
  }
  return best;
}

/** `07/12/2026`, `7/12/2026` or `2026-07-12` → `2026-07-12`; null for anything
 *  else. Both forms `parse_date_param` accepts, so the page and the API read
 *  one date the same way. */
export function isoDate(typed: string): string | null {
  const trimmed = typed.trim();
  if (/^\d{4}-\d{2}-\d{2}$/u.test(trimmed)) return trimmed;
  const us = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/u.exec(trimmed);
  if (!us) return null;
  return `${us[3]}-${us[1].padStart(2, "0")}-${us[2].padStart(2, "0")}`;
}

/** What changed, named for the window's verdict. `initial` is a sentence of
 *  its own; `structure` alone is "only". */
const KIND_NOUNS: Record<string, string> = {
  text: "statute text",
  notes: "notes",
  structure: "XML/metadata",
};

/** The order the kinds are named in: the text first. */
const KIND_ORDER = ["text", "notes", "structure"];

/** "The statute text, notes and XML/metadata changed." — the kinds as a
 *  sentence, or null when nothing arrived. */
export function kindsSentence(kinds: string[]): string | null {
  if (kinds.length === 0) return null;
  const sentences: string[] = [];
  if (kinds.includes("initial")) sentences.push("The section entered the Code.");

  const rank = (kind: string) => {
    const at = KIND_ORDER.indexOf(kind);
    return at === -1 ? KIND_ORDER.length : at;
  };
  const changed = [...new Set(kinds)].filter((kind) => kind !== "initial").sort((a, b) => rank(a) - rank(b));
  if (changed.length === 1 && changed[0] === "structure") {
    sentences.push("Only the stored XML or metadata changed.");
  } else if (changed.length > 0) {
    const nouns = changed.map((kind) => KIND_NOUNS[kind] ?? kind);
    const joined =
      nouns.length === 1 ? nouns[0] : `${nouns.slice(0, -1).join(", ")} and ${nouns[nouns.length - 1]}`;
    sentences.push(`The ${joined} changed.`);
  }
  return sentences.join(" ");
}

