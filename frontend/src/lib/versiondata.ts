/**
 * The version-change report, as `/app/data/version-changes` renders it
 * (ADR-0074, ADR-0076).
 *
 * `frontend/src/data/version-changes.json` is a copy of
 * `docs/verification/version-changes.json`, kept equal by `make
 * sync-verification` and `tests/versiondata.test.ts`. The reader image builds
 * from `./frontend`, so nothing under `docs/` exists at image-build time — the
 * same boundary ADR-0053 met when the colour-pair list moved.
 *
 * Three shapes in the artifact decide what this module has to do:
 *
 *   - `per_title[t].by_kind` is sparse. Title `18a` carries no `text` key and
 *     `50a` no `structure` key, so a cell reading one directly prints
 *     `undefined`.
 *   - A share is `null` where its denominator is zero: `by_kind.initial.share`
 *     corpus-wide, because an initial group has no departing group to have
 *     changed from, and `text_classified_share` for `18a`, which has no text
 *     changes. Neither is `0`.
 *   - A title number is a string (gotcha 16). The keys include `5a`, `18a` and
 *     `50a`, and sorted as text the table reads `1, 10, 11, 12, …, 18a, 19, 2`.
 */

import { compareTitles } from "./url";

export type ChangeKind = "initial" | "text" | "notes" | "structure";

/** Reading order for the columns: the arrival that has no predecessor, then
 *  the three transitions in the priority `change_kind` is decided by. */
export const CHANGE_KINDS: ChangeKind[] = ["initial", "text", "notes", "structure"];

export interface KindTotal {
  count: number;
  share: number | null;
}

export interface TitleReport {
  by_kind: Partial<Record<ChangeKind, number>>;
  text_classified: number;
  text_classified_share: number | null;
}

export interface VersionChangeReport {
  by_kind: Record<ChangeKind, KindTotal>;
  change_rows: number;
  concurrent: number;
  generated_at: string;
  law_rows: number;
  per_title: Record<string, TitleReport>;
  sections_covered: number;
  text_classified: number;
  text_classified_share: number | null;
  transitions: number;
  version_groups_hashed: number;
  version_groups_total: number;
}

export interface TitleRow {
  num: string;
  initial: number;
  text: number;
  notes: number;
  structure: number;
  /** All four kinds — the title's share of `change_rows`. */
  changeRows: number;
  textClassified: number;
  textClassifiedShare: number | null;
}

/** One row per title in the report, every kind present as a number, in the
 *  Code's own order. */
export function titleRows(report: VersionChangeReport): TitleRow[] {
  return Object.entries(report.per_title)
    .map(([num, entry]) => {
      const kinds = Object.fromEntries(
        CHANGE_KINDS.map((kind) => [kind, entry.by_kind[kind] ?? 0]),
      ) as Record<ChangeKind, number>;
      return {
        num,
        ...kinds,
        changeRows: CHANGE_KINDS.reduce((total, kind) => total + kinds[kind], 0),
        textClassified: entry.text_classified,
        textClassifiedShare: entry.text_classified_share,
      };
    })
    .sort((a, b) => compareTitles(a.num, b.num));
}

/** The keys the table can be ordered by. `title` is the Code's order; the
 *  three others are counts, and their first direction is largest first, which
 *  is what a reader opening a size column wants to see. `-desc` reverses
 *  whichever of those is in force, so the words under each option say what the
 *  direction means rather than which way the numbers run. */
export const SORT_KEYS = ["title", "rows", "text", "classified"] as const;
export type SortKey = (typeof SORT_KEYS)[number];

export const DEFAULT_SORT = "title";

/** The sort in force, from `?sort=`. Anything unrecognised is the default, so
 *  a hand-edited URL renders the table rather than nothing. */
export function parseSort(value: string | null | undefined): string {
  if (!value) return DEFAULT_SORT;
  const key = value.replace(/-desc$/u, "");
  if (!(SORT_KEYS as readonly string[]).includes(key)) return DEFAULT_SORT;
  return value;
}

/**
 * The rows in the order `sort` names.
 *
 * A reversed order is the forward list reversed rather than a second
 * comparator — ADR-0071's rule, and it matters here for the same reason: 10 of
 * the 56 titles tie some other title on at least one sortable column, and two
 * comparators disagree about where a tie sits.
 *
 * A `null` classified share sorts last in the forward direction: a title with
 * no text changes has no share, and putting it at the bottom keeps the column's
 * top end the answer to "which titles are best attributed".
 */
export function sortTitleRows(rows: TitleRow[], sort: string): TitleRow[] {
  const key = sort.replace(/-desc$/u, "") as SortKey;
  const forward = [...rows];

  if (key === "rows") forward.sort((a, b) => b.changeRows - a.changeRows);
  else if (key === "text") forward.sort((a, b) => b.text - a.text);
  else if (key === "classified") {
    forward.sort((a, b) => {
      if (a.textClassifiedShare === null) return b.textClassifiedShare === null ? 0 : 1;
      if (b.textClassifiedShare === null) return -1;
      return b.textClassifiedShare - a.textClassifiedShare;
    });
  }

  return sort.endsWith("-desc") ? forward.reverse() : forward;
}

/** A share as a percentage, or an em dash where there is none. The artifact
 *  rounds every share to four decimal places, so two places here is the whole
 *  of the recorded value rather than a truncation of it. */
export function formatShare(share: number | null): string {
  return share === null ? "—" : `${(share * 100).toFixed(2)}%`;
}

/** A count as a share of a total, for the figures the artifact does not
 *  precompute — `concurrent` against `transitions`. */
export function shareOf(count: number, total: number): number | null {
  return total === 0 ? null : count / total;
}

export function formatCount(count: number): string {
  return count.toLocaleString("en-US");
}
