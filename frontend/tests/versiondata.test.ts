/**
 * The version-change report the reader renders, and the copy it renders from
 * (ADR-0076).
 *
 * `/app/data/version-changes` reads `src/data/version-changes.json`, which is a
 * copy of `docs/verification/version-changes.json`. It has to be a copy: the
 * reader image builds from `./frontend`, so nothing under `docs/` exists at
 * image-build time (ADR-0053's boundary). A copy drifts, so the drift is what
 * this file fails on — regenerate the report, run `make sync-verification`, and
 * forgetting the second step is a red build rather than a page quoting numbers
 * the corpus no longer holds.
 *
 * The second half is arithmetic on the artifact itself. The 56 per-title rows
 * sum to the corpus totals; a page that renders both is wrong if they ever
 * stop doing so, and neither the report nor the page can tell on its own.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  CHANGE_KINDS,
  formatCount,
  formatShare,
  parseSort,
  shareOf,
  sortTitleRows,
  titleRows,
  type VersionChangeReport,
} from "../src/lib/versiondata";

const HERE = dirname(fileURLToPath(import.meta.url));
const ARTIFACT = resolve(HERE, "../../docs/verification/version-changes.json");
const COPY = resolve(HERE, "../src/data/version-changes.json");

const artifact = JSON.parse(readFileSync(ARTIFACT, "utf8")) as VersionChangeReport;
const report = JSON.parse(readFileSync(COPY, "utf8")) as VersionChangeReport;

describe("the reader's copy of the version-change report", () => {
  it("is the committed artifact, leaf for leaf", () => {
    expect(
      report,
      "frontend/src/data/version-changes.json has drifted from " +
        "docs/verification/version-changes.json — run `make sync-verification`",
    ).toEqual(artifact);
  });

  it("carries the generation timestamp the page shows", () => {
    expect(report.generated_at).toMatch(/^\d{4}-\d{2}-\d{2}T/u);
  });
});

describe("the per-title rows reconcile to the corpus totals", () => {
  const rows = titleRows(report);

  it("covers 56 of the corpus's 58 titles", () => {
    // 11a and 28a hold no sections at any release point — every one of their
    // 20 and 19 title-releases loads 0 (docs/verification/database.json) — so
    // they have no version groups and no change rows to report.
    expect(rows).toHaveLength(56);
    expect(rows.map((row) => row.num)).not.toContain("11a");
    expect(rows.map((row) => row.num)).not.toContain("28a");
  });

  it("sums each kind to the corpus count for that kind", () => {
    for (const kind of CHANGE_KINDS) {
      const total = rows.reduce((sum, row) => sum + row[kind], 0);
      expect(total, `per-title ${kind} does not sum to by_kind.${kind}.count`).toBe(
        report.by_kind[kind].count,
      );
    }
  });

  it("sums to change_rows, and to transitions once the initial groups are taken out", () => {
    const changeRows = rows.reduce((sum, row) => sum + row.changeRows, 0);

    expect(changeRows).toBe(report.change_rows);
    expect(report.change_rows - report.by_kind.initial.count).toBe(report.transitions);
  });

  it("sums the attributed text changes to text_classified", () => {
    const classified = rows.reduce((sum, row) => sum + row.textClassified, 0);

    expect(classified).toBe(report.text_classified);
  });

  it("never reports more attributed text changes than text changes", () => {
    for (const row of rows) {
      expect(row.textClassified, `title ${row.num}`).toBeLessThanOrEqual(row.text);
    }
  });

  it("counts one initial group per section covered", () => {
    expect(report.by_kind.initial.count).toBe(report.sections_covered);
  });
});

describe("the sparse and null shapes in the artifact", () => {
  const rows = titleRows(report);
  const byNum = new Map(rows.map((row) => [row.num, row]));

  it("defaults a kind the artifact omits to 0 rather than undefined", () => {
    // Trap 1: `18a` carries no `text` key and `50a` no `structure` key.
    expect(artifact.per_title["18a"].by_kind.text).toBeUndefined();
    expect(artifact.per_title["50a"].by_kind.structure).toBeUndefined();
    expect(byNum.get("18a")?.text).toBe(0);
    expect(byNum.get("50a")?.structure).toBe(0);
  });

  it("renders a share with no denominator as a dash", () => {
    // Trap 2: an initial group has no departing group, and `18a` has no text
    // change to have been classified.
    expect(report.by_kind.initial.share).toBeNull();
    expect(byNum.get("18a")?.textClassifiedShare).toBeNull();
    expect(formatShare(null)).toBe("—");
    expect(formatShare(0)).toBe("0.00%");
  });

  it("reports the four decimal places the artifact stores", () => {
    expect(formatShare(report.text_classified_share)).toBe("49.25%");
    expect(formatShare(report.by_kind.structure.share)).toBe("75.14%");
    expect(formatShare(report.by_kind.notes.share)).toBe("17.10%");
    expect(formatShare(report.by_kind.text.share)).toBe("7.76%");
  });

  it("computes the shares the artifact does not store", () => {
    expect(formatShare(shareOf(report.concurrent, report.transitions))).toBe("18.31%");
    expect(shareOf(1, 0)).toBeNull();
  });

  it("groups the thousands the way the page prints them", () => {
    expect(formatCount(report.change_rows)).toBe("489,738");
  });
});

describe("the table's order", () => {
  const rows = titleRows(report);

  it("is the Code's order by default, not the string order", () => {
    // Gotcha 16: sorted as text this reads `1, 10, 11, 11a, 12, … 2, 20`.
    const nums = rows.map((row) => row.num);

    expect(nums.slice(0, 6)).toEqual(["1", "2", "3", "4", "5", "5a"]);
    expect(nums.indexOf("18a")).toBe(nums.indexOf("18") + 1);
    expect(nums.indexOf("50a")).toBe(nums.indexOf("50") + 1);
    expect(nums[nums.length - 1]).toBe("54");
  });

  it("orders a count column largest first", () => {
    const byRows = sortTitleRows(rows, "rows");

    expect(byRows[0].num).toBe("42");
    expect(byRows[0].changeRows).toBeGreaterThan(byRows[1].changeRows);
  });

  it("reverses that order rather than sorting a second time", () => {
    const forward = sortTitleRows(rows, "text").map((row) => row.num);
    const reversed = sortTitleRows(rows, "text-desc").map((row) => row.num);

    expect(reversed).toEqual([...forward].reverse());
  });

  it("puts a title with no share at the bottom of the share order", () => {
    const byShare = sortTitleRows(rows, "classified");

    expect(byShare[byShare.length - 1].num).toBe("18a");
    expect(byShare[0].textClassifiedShare).not.toBeNull();
  });

  it("keeps every row in every order", () => {
    for (const sort of ["title", "title-desc", "rows", "text-desc", "classified"]) {
      expect(sortTitleRows(rows, sort)).toHaveLength(rows.length);
    }
  });

  it("falls back to the Code's order on a sort it does not serve", () => {
    expect(parseSort(null)).toBe("title");
    expect(parseSort("")).toBe("title");
    expect(parseSort("nonsense")).toBe("title");
    expect(parseSort("rows-desc")).toBe("rows-desc");
    expect(parseSort("classified")).toBe("classified");
  });
});
