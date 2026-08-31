/**
 * Which release point a section should be compared *with*.
 *
 * "The previous release point" is almost never the answer a reader wants. The
 * Code is republished in full at every release point and few titles change at
 * any of them (gotcha 10), so the release point before the one on screen
 * usually holds character-for-character the same section, and a redline against
 * it is empty. "What changed last time this provision changed" is a different
 * question and the one the reader means.
 *
 * The answer comes from the version timeline, which is already the site's own
 * record of every release point where this text changed: `/versions` groups the
 * release points by content hash, in order, so the group before the one holding
 * the release on screen ends at the last release point with different text.
 *
 * **Not `content_first_seen`,** which is on the section response and would have
 * cost no call. It does not mean what its name suggests on real data: § 45f's
 * newest group reports `first_seen: 119-99` while its own `releases` run from
 * `117-80`, because that field follows the stored fragment's `first_release_id`
 * and an incremental load can attach an earlier release point to a row without
 * lowering it (ADR-0007's dedupe, gotcha 15). `releases` comes from
 * `section_release_map` and is authoritative.
 *
 * The group before the one on screen is not always a group whose *text* is
 * different. ADR-0007's hash records a new group whenever the stored XML moved
 * at all, and corpus-wide 75.1% of transitions change no text and no notes
 * (`docs/verification/version-changes.json`), so the group immediately before
 * is usually the same words with different markup — the emptiness the whole
 * control exists to avoid, one level down. ADR-0074's annotations say which
 * transitions were statutory, so the walk skips the rest (ADR-0075).
 */
import type { VersionEntry } from "./types";
import { isStatutoryEntry } from "./versions";

/**
 * The last release point holding statutory text different from what is on
 * screen.
 *
 * Null when the release on screen is in the oldest group there is — that text
 * is as old as the corpus and has nothing before it — and null when `selected`
 * is in no group at all, which is a section the timeline does not cover.
 *
 * A corpus with no change rows answers `change_kind: null` throughout; there
 * the walk stops at the first group back, which is the behaviour this function
 * had before the annotations existed.
 */
export function previousChangedRelease(
  versions: VersionEntry[],
  selected: string,
): string | null {
  const index = versions.findIndex((version) => version.releases.includes(selected));
  if (index <= 0) return null;
  // Back to the transition that last changed the words. The group on screen is
  // the same text as every group behind it up to that point, so the release
  // point to compare with is the one immediately before it.
  //
  // An unannotated entry stops the walk: without a change row there is nothing
  // saying the transition was not statutory, and the group before is the answer
  // this function gave before the annotations existed.
  let changed = index;
  while (changed > 0 && isFoldedIntoPrevious(versions[changed])) changed -= 1;
  if (changed <= 0) return null;
  const releases = versions[changed - 1].releases;
  // The *last* release point of that group: the one immediately before the
  // change, so the redline spans one amendment rather than several.
  return releases[releases.length - 1] ?? null;
}

/** Whether this entry's arrival left the statutory text as it was — a `notes`
 *  or `structure` transition. False for an unannotated entry and for the
 *  oldest, neither of which the walk may pass. */
function isFoldedIntoPrevious(entry: VersionEntry): boolean {
  return entry.change_kind != null && !isStatutoryEntry(entry);
}

/**
 * Release points offered in the "Compare with…" list, newest first.
 *
 * Everything strictly older than what is on screen. Comparing a release point
 * with itself is an empty redline, and comparing forwards is the same redline
 * read backwards — the page presents `from` → `to`, so `to` stays the text the
 * reader is looking at and `from` is what they choose.
 */
export function comparableReleases<T extends { label: string; seq: number }>(
  selected: string,
  releases: T[],
): T[] {
  const current = releases.find((release) => release.label === selected);
  if (!current) return [];
  return releases.filter((release) => release.seq < current.seq).sort((a, b) => b.seq - a.seq);
}
