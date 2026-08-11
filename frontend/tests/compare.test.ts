import { describe, expect, it } from "vitest";

import { comparableReleases, previousChangedRelease } from "../src/lib/compare";
import type { VersionEntry } from "../src/lib/types";

/** Only the two fields `previousChangedRelease` reads. */
function version(releases: string[]): VersionEntry {
  return {
    content_hash: releases.join("-"),
    first_seen: null as never,
    releases,
    num: null,
    heading: null,
    status: null,
  };
}

/**
 * § 45f's real timeline, abridged to its last three groups. The last group's
 * `releases` start at `117-80` while its `first_seen` says `119-99`, which is
 * why this reads `releases` and not that field.
 */
const TIMELINE = [
  version(["116-193", "117-2", "117-49"]),
  version(["117-80", "118-1", "119-99", "119-102not101"]),
];

describe("previousChangedRelease", () => {
  it("is the last release point of the group before the one on screen", () => {
    expect(previousChangedRelease(TIMELINE, "119-102not101")).toBe("117-49");
  });

  it("gives the same answer from anywhere inside the current group", () => {
    // The reader may be on any release point holding this text; the previous
    // *different* text is the same one either way.
    for (const label of ["117-80", "118-1", "119-99", "119-102not101"]) {
      expect(previousChangedRelease(TIMELINE, label)).toBe("117-49");
    }
  });

  it("is null in the oldest group — that text is as old as the corpus", () => {
    expect(previousChangedRelease(TIMELINE, "116-193")).toBeNull();
    expect(previousChangedRelease(TIMELINE, "117-49")).toBeNull();
  });

  it("is null for a release point the timeline does not cover", () => {
    expect(previousChangedRelease(TIMELINE, "113-21")).toBeNull();
  });

  it("is null when there is no timeline at all", () => {
    expect(previousChangedRelease([], "119-99")).toBeNull();
  });

  it("takes the last release point of the previous group, not its first", () => {
    // The redline should span one amendment. Taking `releases[0]` would span
    // every release point of that group as well, which is the same text.
    expect(previousChangedRelease(TIMELINE, "117-80")).toBe("117-49");
    expect(previousChangedRelease(TIMELINE, "117-80")).not.toBe("116-193");
  });
});

describe("comparableReleases", () => {
  const releases = [
    { label: "119-102not101", seq: 381 },
    { label: "119-99", seq: 379 },
    { label: "117-49", seq: 300 },
    { label: "116-193", seq: 217 },
  ];

  it("offers everything strictly older than what is on screen, newest first", () => {
    expect(comparableReleases("119-99", releases).map((r) => r.label)).toEqual([
      "117-49",
      "116-193",
    ]);
  });

  it("never offers the release point on screen — that redline is empty", () => {
    expect(comparableReleases("119-102not101", releases).map((r) => r.label)).not.toContain(
      "119-102not101",
    );
  });

  it("offers nothing at the oldest release point", () => {
    expect(comparableReleases("116-193", releases)).toEqual([]);
  });

  it("offers nothing when the release on screen is not in the list", () => {
    // `seq` is the only ordering (gotcha 4: labels do not sort), so without a
    // row for `selected` there is no comparison to make.
    expect(comparableReleases("118-22u1", releases)).toEqual([]);
  });

  it("orders by seq rather than by label", () => {
    const scrambled = [
      { label: "116-193", seq: 217 },
      { label: "119-99", seq: 379 },
      { label: "117-49", seq: 300 },
    ];
    expect(comparableReleases("119-99", scrambled).map((r) => r.label)).toEqual([
      "117-49",
      "116-193",
    ]);
  });
});
