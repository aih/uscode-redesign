/**
 * The sentence the reader gets about how current this mirror is.
 *
 * What these pin is the ranking, not the wording: several of these states can
 * be true at once (behind *and* stale *and* the last check failed), and the one
 * that gets said is the one the reader can act on. The tone matters as much as
 * the text — an "ok" note is skimmed, a "warning" is an alert — so every case
 * asserts both.
 */
import { describe, expect, it } from "vitest";

import { classificationNote, currencyNote, humanizeAge, usDate } from "../src/lib/currency";
import type { ClassificationSource, Status } from "../src/lib/types";

function status(overrides: Partial<Status["source"]> = {}, corpus: Partial<Status["corpus"]> = {}): Status {
  return {
    source: {
      url: "https://uscode.house.gov/download/priorreleasepoints.htm",
      last_checked_at: "2026-08-02T09:00:00Z",
      hours_since_check: 3,
      ok: true,
      stale: false,
      release_points_seen: 382,
      new_release_points: [],
      latest_published_label: "119-102not101",
      latest_published_date: "2026-07-12",
      error: null,
      ...overrides,
    },
    corpus: {
      latest_release: "119-102not101",
      latest_currency_date: "2026-07-12",
      release_points_known: 382,
      behind_by: 0,
      ...corpus,
    },
  };
}

describe("humanizeAge", () => {
  it("is deliberately coarse — the schedule is daily, so minutes would be false precision", () => {
    expect(humanizeAge(0.2)).toBe("in the last hour");
    expect(humanizeAge(1.5)).toBe("an hour ago");
    expect(humanizeAge(5)).toBe("5 hours ago");
    expect(humanizeAge(26)).toBe("yesterday");
    expect(humanizeAge(24 * 6)).toBe("6 days ago");
    expect(humanizeAge(24 * 45)).toBe("a month ago");
  });

  it("says so rather than guessing when there is no age", () => {
    expect(humanizeAge(null)).toBe("at an unknown time");
  });
});

describe("usDate", () => {
  it("uses OLRC's own currency-note form", () => {
    expect(usDate("2026-07-12")).toBe("07/12/2026");
    expect(usDate(null)).toBeNull();
  });
});

describe("currencyNote", () => {
  it("renders nothing at all when the status endpoint could not be reached", () => {
    // A note *about* the law must never be able to take down the law.
    expect(currencyNote(null)).toBeNull();
  });

  it("is quiet when the check is recent and nothing newer exists", () => {
    const note = currencyNote(status())!;
    expect(note.tone).toBe("ok");
    expect(note.text).toContain("3 hours ago");
    expect(note.detail).toContain("119-102not101");
  });

  it("warns when nothing has ever checked — never checked is not the same as up to date", () => {
    const note = currencyNote(status({ last_checked_at: null, hours_since_check: null }))!;
    expect(note.tone).toBe("warning");
    expect(note.text).toContain("no record of checking");
  });

  it("warns, and quotes the error, when the last check failed", () => {
    const note = currencyNote(
      status({ ok: false, stale: true, error: "URLError: timed out" }),
    )!;
    expect(note.tone).toBe("warning");
    expect(note.text).toContain("failed");
    expect(note.detail).toContain("URLError: timed out");
  });

  it("reports being behind before reporting being stale — it is the actionable one", () => {
    const note = currencyNote(
      status({ stale: true, hours_since_check: 24 * 9 }, { behind_by: 4 }),
    )!;
    expect(note.tone).toBe("warning");
    expect(note.text).toContain("4 release points");
    expect(note.text).not.toContain("longer ago");
  });

  it("counts one missing release point in the singular", () => {
    const note = currencyNote(status({}, { behind_by: 1 }))!;
    expect(note.text).toContain("1 release point published");
    expect(note.text).toContain("is not loaded yet");
  });

  it("warns when the last successful check is older than the site's own bound", () => {
    const note = currencyNote(status({ stale: true, hours_since_check: 24 * 9 }))!;
    expect(note.tone).toBe("warning");
    expect(note.text).toContain("9 days ago");
    expect(note.detail).toContain("may not be the newest");
  });

  it("copes with a database holding no release points at all", () => {
    const note = currencyNote(
      status({}, { latest_release: null, latest_currency_date: null }),
    )!;
    expect(note.detail).toContain("No release point is loaded here yet.");
  });
});

describe("classificationNote", () => {
  function classification(
    overrides: Partial<ClassificationSource> = {},
  ): ClassificationSource {
    return {
      url: "https://uscode.house.gov/classification/tables.shtml",
      last_checked_at: "2026-08-14T09:00:00Z",
      hours_since_check: 3,
      ok: true,
      stale: false,
      files_seen: 32,
      changed_files: [],
      latest_covered_text: "Public Laws 118-35 to 118-274",
      error: null,
      ...overrides,
    };
  }

  it("renders nothing when the registry request failed", () => {
    expect(classificationNote(null)).toBeNull();
  });

  it("is quiet when the check is recent", () => {
    const note = classificationNote(classification())!;
    expect(note.tone).toBe("ok");
    expect(note.text).toContain("3 hours ago");
    expect(note.detail).toBeUndefined();
  });

  it("says how many tables changed at the last check", () => {
    const note = classificationNote(classification({ changed_files: ["usc118-2.html"] }))!;
    expect(note.detail).toBe("1 table changed at that check.");
  });

  // `ClassificationCheckOut` reports "no check has ever run" as ok: false, so a
  // page reading `ok` alone said a check had failed when none was ever made.
  it("does not call a check that never happened a failure", () => {
    const note = classificationNote(
      classification({ last_checked_at: null, hours_since_check: null, ok: false, stale: true }),
    )!;
    expect(note.tone).toBe("warning");
    expect(note.text).toContain("no record of checking");
    expect(note.text).not.toContain("failed");
  });

  it("warns, and quotes the error, when the last check failed", () => {
    const note = classificationNote(
      classification({ ok: false, stale: true, error: "HTTP 503" }),
    )!;
    expect(note.text).toContain("failed");
    expect(note.detail).toContain("HTTP 503");
  });

  it("warns when the last successful check is older than the site's own bound", () => {
    const note = classificationNote(classification({ stale: true, hours_since_check: 24 * 9 }))!;
    expect(note.tone).toBe("warning");
    expect(note.text).toContain("9 days ago");
    expect(note.detail).toContain("may have published a newer one");
  });
});
