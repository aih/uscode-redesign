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
import type { VersionEntry, VersionLaw } from "./types";

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
   *  and for a row the default view hides. */
  effectiveReleases: string[];
  /**
   * The release point to compare against: the last release of the entry before
   * this one, so the redline spans one transition.
   *
   * One value serves both views. The entries the default view hides sit between
   * a shown entry and the one above it, and they are folded into that one's
   * run, so the end of the previous *shown* entry's effective run is the last
   * release of the entry immediately before — the same label either way.
   */
  from: string | null;
}

/**
 * One row per entry, carrying both views' answers.
 *
 * `entries` arrive oldest first, which is the order the page renders and the
 * order the repository guarantees (earliest mapped release, ADR-0066).
 */
export function timelineRows(entries: VersionEntry[]): TimelineRow[] {
  const annotated = isAnnotated(entries);
  const rows: TimelineRow[] = entries.map((entry, index) => {
    const releases = entry.releases ?? [];
    // An unannotated corpus has no default view to compute, so every row is
    // treated as shown: the page renders the all view and hides nothing.
    const statutory = annotated ? isStatutoryEntry(entry) : true;
    const previous = index > 0 ? entries[index - 1] : null;
    const previousReleases = previous?.releases ?? [];
    return {
      entry,
      kind: entry.change_kind ?? "unknown",
      statutory,
      start: releases[0] ?? null,
      releases,
      effectiveReleases: [...releases],
      from: previous ? (previousReleases[previousReleases.length - 1] ?? null) : null,
    };
  });

  // Fold each hidden run into the shown row above it.
  let lastShown: TimelineRow | null = null;
  for (const row of rows) {
    if (row.statutory) lastShown = row;
    else if (lastShown) lastShown.effectiveReleases.push(...row.releases);
  }

  return rows;
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
