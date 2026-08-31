import { describe, expect, it } from "vitest";

import type { VersionEntry, VersionLaw } from "../src/lib/types";
import {
  changeSummary,
  isAnnotated,
  isStatutoryEntry,
  lawActions,
  lawLabel,
  lawQuery,
  readVersionsView,
  timelineRows,
  versionCounts,
} from "../src/lib/versions";

function entry(
  kind: string | null,
  releases: string[],
  extra: Partial<VersionEntry> = {},
): VersionEntry {
  return {
    content_hash: releases.join("-"),
    first_seen: null as never,
    releases,
    num: "§ 2201.",
    heading: "Specimen",
    status: null,
    change_kind: kind,
    text_changed: kind === "text",
    notes_changed: kind === "notes",
    status_changed: false,
    concurrent: false,
    attribution: "none",
    laws: [],
    ...extra,
  };
}

/**
 * § 2201's real history in the full local corpus, abridged to its release runs:
 * seven groups of which two changed the statutory text.
 */
const TIMELINE: VersionEntry[] = [
  entry("initial", ["113-21", "113-30"]),
  entry("structure", ["113-44"]),
  entry("structure", ["114-139"]),
  entry("text", ["115-442", "116-3"], { attribution: "classified" }),
  entry("structure", ["116-29"]),
  entry("notes", ["117-80", "119-99"]),
  entry("text", ["119-102not101"], { attribution: "classified" }),
];

/** The same section as a corpus with no change rows: the shape the API answers
 *  before the backfill has run. */
const UNANNOTATED: VersionEntry[] = [
  entry(null, ["113-21"]),
  entry(null, ["115-442"]),
  entry(null, ["119-102not101"]),
];

describe("readVersionsView", () => {
  it("is the default view unless the URL says all", () => {
    expect(readVersionsView("all")).toBe("all");
    expect(readVersionsView("text")).toBe("text");
    expect(readVersionsView(null)).toBe("text");
    expect(readVersionsView(undefined)).toBe("text");
    expect(readVersionsView("ALL")).toBe("text");
    expect(readVersionsView("everything")).toBe("text");
  });
});

describe("isStatutoryEntry", () => {
  it("is the text transitions and the entry the history starts at", () => {
    expect(isStatutoryEntry(entry("text", []))).toBe(true);
    expect(isStatutoryEntry(entry("initial", []))).toBe(true);
    expect(isStatutoryEntry(entry("notes", []))).toBe(false);
    expect(isStatutoryEntry(entry("structure", []))).toBe(false);
    expect(isStatutoryEntry(entry(null, []))).toBe(false);
  });
});

describe("isAnnotated", () => {
  it("wants a change kind on every entry", () => {
    expect(isAnnotated(TIMELINE)).toBe(true);
    expect(isAnnotated(UNANNOTATED)).toBe(false);
    // One entry short of a full set is still no default view: an incremental
    // load after a backfill can leave exactly this.
    expect(isAnnotated([...TIMELINE, entry(null, ["119-110"])])).toBe(false);
  });

  it("is false for an empty timeline", () => {
    expect(isAnnotated([])).toBe(false);
  });
});

describe("timelineRows", () => {
  const rows = timelineRows(TIMELINE);

  it("keeps every entry, in order, and marks which the default view shows", () => {
    expect(rows.map((row) => row.kind)).toEqual([
      "initial",
      "structure",
      "structure",
      "text",
      "structure",
      "notes",
      "text",
    ]);
    expect(rows.map((row) => row.statutory)).toEqual([
      true,
      false,
      false,
      true,
      false,
      false,
      true,
    ]);
  });

  it("starts each entry at releases[0], never at first_seen", () => {
    // `first_seen` is `null as never` in these fixtures: reading it would throw.
    expect(rows.map((row) => row.start)).toEqual([
      "113-21",
      "113-44",
      "114-139",
      "115-442",
      "116-29",
      "117-80",
      "119-102not101",
    ]);
  });

  it("extends a shown entry's run through the entries the default view hides", () => {
    // The oldest entry stands through two structure-only groups after it.
    expect(rows[0].releases).toEqual(["113-21", "113-30"]);
    expect(rows[0].effectiveReleases).toEqual(["113-21", "113-30", "113-44", "114-139"]);
    // The 115-442 amendment stands until the next one, across a structure-only
    // and a notes-only group.
    expect(rows[3].effectiveReleases).toEqual([
      "115-442",
      "116-3",
      "116-29",
      "117-80",
      "119-99",
    ]);
  });

  it("leaves a hidden entry's own run alone", () => {
    for (const row of rows.filter((candidate) => !candidate.statutory)) {
      expect(row.effectiveReleases).toEqual(row.releases);
    }
  });

  it("gives the newest entry no run to absorb", () => {
    expect(rows[6].effectiveReleases).toEqual(["119-102not101"]);
  });

  it("compares each entry with the last release of the entry before it", () => {
    expect(rows.map((row) => row.from)).toEqual([
      null,
      "113-30",
      "113-44",
      "114-139",
      "116-3",
      "116-29",
      "119-99",
    ]);
  });

  it("compares a shown entry with the end of the previous shown entry's run", () => {
    expect(rows[0].fromStatutory).toBeNull();
    expect(rows[3].fromStatutory).toBe("114-139");
    expect(rows[6].fromStatutory).toBe("119-99");
  });

  it("leaves a hidden entry no default-view comparison", () => {
    for (const row of rows.filter((candidate) => !candidate.statutory)) {
      expect(row.fromStatutory).toBeNull();
    }
  });

  it("shows everything, and folds nothing, without change rows", () => {
    const plain = timelineRows(UNANNOTATED);
    expect(plain.map((row) => row.kind)).toEqual(["unknown", "unknown", "unknown"]);
    expect(plain.every((row) => row.statutory)).toBe(true);
    for (const row of plain) expect(row.effectiveReleases).toEqual(row.releases);
  });

  it("has nothing to say about an empty timeline", () => {
    expect(timelineRows([])).toEqual([]);
  });
});

describe("versionCounts", () => {
  it("counts both views and the amendments between them", () => {
    expect(versionCounts(TIMELINE)).toEqual({
      statutory: 3,
      all: 7,
      amendments: 2,
      releases: 10,
    });
  });

  it("counts every entry as shown when there are no change rows", () => {
    const counts = versionCounts(UNANNOTATED);
    expect(counts.statutory).toBe(3);
    expect(counts.all).toBe(3);
    // Nothing is recorded as an amendment, which is why the section page keeps
    // its old sentence rather than printing "amended 0 times".
    expect(counts.amendments).toBe(0);
  });
});

describe("law chips", () => {
  const law: VersionLaw = {
    pl_congress: 119,
    pl_num: 102,
    in_classification: true,
    is_note_classification: false,
    in_source_credit: true,
    classification_actions: ["", "new"],
  };

  it("writes the citation with an EN DASH", () => {
    expect(lawLabel(law)).toBe("Pub. L. 119–102");
    expect(lawLabel(law)).toContain("–");
    expect(lawLabel(law)).not.toContain("-");
  });

  it("looks the law up by the hyphen the tables and a keyboard carry", () => {
    expect(lawQuery(law)).toBe("Pub. L. 119-102");
  });

  it("drops the empty action, which is a plain amendment", () => {
    expect(lawActions(law)).toEqual(["new"]);
    expect(lawActions({ ...law, classification_actions: [""] })).toEqual([]);
    expect(lawActions({ ...law, classification_actions: [] })).toEqual([]);
  });

  it("says each action once", () => {
    expect(lawActions({ ...law, classification_actions: ["new", "new", ""] })).toEqual(["new"]);
  });
});

describe("changeSummary", () => {
  it("says whether a text change names a statute", () => {
    expect(changeSummary(entry("text", [], { attribution: "classified" }))).toBe(
      "Statutory text changed.",
    );
    expect(changeSummary(entry("text", [], { attribution: "none" }))).toContain(
      "No classifying statute recorded",
    );
  });

  it("names the other two kinds", () => {
    expect(changeSummary(entry("notes", []))).toContain("Notes updated");
    expect(changeSummary(entry("structure", []))).toContain("XML/metadata only");
  });

  it("says nothing about the oldest entry or an unannotated one", () => {
    expect(changeSummary(entry("initial", []))).toBeNull();
    expect(changeSummary(entry(null, []))).toBeNull();
  });
});
