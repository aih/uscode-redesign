import { describe, expect, it } from "vitest";

import type { VersionEntry, VersionLaw } from "../src/lib/types";
import {
  changeSummary,
  isAnnotated,
  isStatutoryEntry,
  lawActions,
  lawLabel,
  lawQuery,
  lawsLabel,
  readVersionsView,
  releaseOrder,
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

/** Release-point order for every label these fixtures use. Labels do not sort
 *  (gotcha 4), so the numbers below are the inventory's `seq` and the gaps
 *  between them are the release points these sections were never mapped at. */
const ORDER = releaseOrder([
  { label: "113-21", seq: 10 },
  { label: "113-30", seq: 11 },
  { label: "113-44", seq: 12 },
  { label: "114-139", seq: 20 },
  { label: "115-442", seq: 30 },
  { label: "116-3", seq: 40 },
  { label: "116-29", seq: 41 },
  { label: "117-80", seq: 50 },
  { label: "119-99", seq: 60 },
  { label: "119-102not101", seq: 61 },
]);

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
  const rows = timelineRows(TIMELINE, ORDER);

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

  it("gives a shown entry the same comparison in both views", () => {
    // The hidden entries between two shown ones are folded into the run of the
    // one above, so the end of the previous shown entry's effective run is the
    // last release of the entry immediately before — the same label either way,
    // which is why there is one `from` and not two.
    const shown = rows.filter((row) => row.statutory);
    for (const [index, row] of shown.entries()) {
      if (index === 0) continue;
      const previousShown = shown[index - 1];
      const run = previousShown.effectiveReleases;
      expect(row.from).toBe(run[run.length - 1]);
    }
  });

  it("shows everything, and folds nothing, without change rows", () => {
    const plain = timelineRows(UNANNOTATED, ORDER);
    expect(plain.map((row) => row.kind)).toEqual(["unknown", "unknown", "unknown"]);
    expect(plain.every((row) => row.statutory)).toBe(true);
    for (const row of plain) expect(row.effectiveReleases).toEqual(row.releases);
  });

  it("has nothing to say about an empty timeline", () => {
    expect(timelineRows([])).toEqual([]);
  });
});

describe("timelineRows and a window that runs backwards", () => {
  /**
   * Recurring content, the shape ADR-0074 flags `concurrent`: the third group
   * is mapped at 116-29, *inside* the second group's own run, so the release
   * point before it (`116-3`) is newer than the release point it starts at.
   * `/app/diff` reads `?from=`/`?to=` in the order it is handed them, so a link
   * built from that window renders every insertion as a deletion.
   */
  const RECURRING: VersionEntry[] = [
    entry("initial", ["113-21"]),
    entry("text", ["114-139", "116-3", "119-99"], { attribution: "classified" }),
    entry("text", ["116-29"], { concurrent: true, attribution: "classified" }),
  ];

  it("offers no comparison where the window runs backwards", () => {
    const rows = timelineRows(RECURRING, ORDER);
    expect(rows[1].from).toBe("113-21");
    expect(rows[1].withheld).toBe(false);
    // 116-3 is seq 40 and 116-29 is seq 41 — but the *last* release of the
    // group before is 119-99 at seq 60, which is newer than what this entry
    // starts at.
    expect(rows[2].from).toBeNull();
    expect(rows[2].withheld).toBe(true);
  });

  it("never says a comparison was withheld on the oldest entry", () => {
    const rows = timelineRows(RECURRING, ORDER);
    expect(rows[0].from).toBeNull();
    expect(rows[0].withheld).toBe(false);
  });

  it("falls back to the concurrent flag with no release order", () => {
    // Conservative rather than exact: the flag is set on every backwards window
    // and on forward ones besides, so this suppresses more than it must and
    // never offers one that runs the wrong way.
    const rows = timelineRows(RECURRING);
    expect(rows[1].from).toBe("113-21");
    expect(rows[2].from).toBeNull();
    expect(rows[2].withheld).toBe(true);
  });

  it("sorts a folded run by release order rather than by concatenation", () => {
    // The hidden group at 116-29 sits inside the shown group's own run, so
    // pushing its releases on the end leaves the list out of order.
    const interleaved: VersionEntry[] = [
      entry("initial", ["113-21"]),
      entry("text", ["114-139", "119-99"], { attribution: "classified" }),
      entry("structure", ["116-29"]),
    ];
    expect(timelineRows(interleaved, ORDER)[1].effectiveReleases).toEqual([
      "114-139",
      "116-29",
      "119-99",
    ]);
    // Without an order the labels stay as concatenated — they cannot be sorted,
    // since release-point labels do not sort lexically (gotcha 4).
    expect(timelineRows(interleaved)[1].effectiveReleases).toEqual([
      "114-139",
      "119-99",
      "116-29",
    ]);
  });

  it("leaves a label the order does not know where it is", () => {
    const rows = timelineRows(
      [entry("initial", ["113-21"]), entry("structure", ["118-22u1"])],
      ORDER,
    );
    expect(rows[0].effectiveReleases).toEqual(["113-21", "118-22u1"]);
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

  it("says what the chips under an entry are a list of", () => {
    // ADR-0074 attributes notes-only and metadata-only transitions too — 7,186
    // and 81 of them carry a law corpus-wide — so "Amended by" is true of a
    // text entry and of nothing else.
    expect(lawsLabel(entry("text", []))).toBe("Amended by");
    for (const kind of ["notes", "structure", "initial"]) {
      expect(lawsLabel(entry(kind, []))).not.toContain("Amended");
      expect(lawsLabel(entry(kind, []))).toContain("recorded for this change");
    }
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

  it("names the oldest entry, which the default view lists beside the amendments", () => {
    expect(changeSummary(entry("initial", []))).toContain("oldest text this site holds");
  });

  it("says nothing about an unannotated entry", () => {
    expect(changeSummary(entry(null, []))).toBeNull();
  });
});
