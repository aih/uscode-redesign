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
 */
import type { VersionEntry } from "./types";

/**
 * The last release point holding text different from what is on screen.
 *
 * Null when the release on screen is in the oldest group there is — that text
 * is as old as the corpus and has nothing before it — and null when `selected`
 * is in no group at all, which is a section the timeline does not cover.
 */
export function previousChangedRelease(
  versions: VersionEntry[],
  selected: string,
): string | null {
  const index = versions.findIndex((version) => version.releases.includes(selected));
  if (index <= 0) return null;
  const before = versions[index - 1].releases;
  // The *last* release point of the previous group: the one immediately before
  // the change, so the redline spans one amendment rather than several.
  return before[before.length - 1] ?? null;
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
