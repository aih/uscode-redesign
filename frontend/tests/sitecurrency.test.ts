import { describe, expect, it } from "vitest";

import { StatusMemo, checkedOnDate, dateline, footerCurrency } from "../src/lib/sitecurrency";
import type { Status } from "../src/lib/types";

function status(overrides: { source?: Partial<Status["source"]>; corpus?: Partial<Status["corpus"]> } = {}): Status {
  return {
    source: {
      url: "https://uscode.house.gov/download/priorreleasepoints.htm",
      last_checked_at: "2026-09-16T21:01:28Z",
      hours_since_check: 3,
      ok: true,
      stale: false,
      release_points_seen: 382,
      new_release_points: [],
      latest_published_label: "119-102",
      latest_published_date: "2026-07-12",
      error: null,
      ...overrides.source,
    },
    corpus: {
      latest_release: "119-102",
      latest_currency_date: "2026-07-12",
      release_points_known: 382,
      behind_by: 0,
      incomplete_loads: [],
      unloaded_titles: [],
      newest_complete_release: "119-102",
      ...overrides.corpus,
    },
  } as Status;
}

describe("dateline", () => {
  it("is the newest release point loaded and its date", () => {
    expect(dateline(status())).toEqual({ label: "119-102", date: "07/12/2026" });
  });

  it("is nothing without a status or a loaded release point", () => {
    expect(dateline(null)).toBeNull();
    expect(dateline(status({ corpus: { latest_release: null, latest_currency_date: null } }))).toBeNull();
  });
});

describe("footerCurrency", () => {
  it("adds the day of the last check, in Washington's calendar", () => {
    expect(footerCurrency(status())).toEqual({
      label: "119-102",
      date: "07/12/2026",
      checkedOn: "09/16/2026",
      warning: null,
    });
    // 02:30 UTC on the 17th is the evening of the 16th in Washington.
    expect(checkedOnDate("2026-09-17T02:30:00Z")).toBe("09/16/2026");
    expect(checkedOnDate("not a time")).toBeNull();
  });

  it("carries the currency note's headline when it is a warning", () => {
    const behind = footerCurrency(status({ corpus: { behind_by: 1 } }));
    expect(behind?.warning).toBe("1 release point published since the newest one loaded here is not loaded yet.");
  });

  it("does not name a failed check as the day the site checked", () => {
    const failed = footerCurrency(status({ source: { ok: false, error: "timeout" } }));
    expect(failed?.checkedOn).toBeNull();
    expect(failed?.warning).toContain("failed");
  });
});

describe("StatusMemo", () => {
  function harness() {
    let clock = 0;
    let generation: number | null = 7;
    let calls = 0;
    let answer: Status | null = status();
    const memo = new StatusMemo(
      async () => {
        calls += 1;
        return answer;
      },
      () => clock,
      1000,
      () => generation,
    );
    return {
      memo,
      calls: () => calls,
      tick: (ms: number) => (clock += ms),
      setGeneration: (g: number | null) => (generation = g),
      setAnswer: (s: Status | null) => (answer = s),
    };
  }

  it("asks once inside the interval and again after it", async () => {
    const h = harness();
    await h.memo.get();
    await h.memo.get();
    expect(h.calls()).toBe(1);
    h.tick(1000);
    await h.memo.get();
    expect(h.calls()).toBe(2);
  });

  it("asks again when the corpus generation has moved", async () => {
    const h = harness();
    await h.memo.get();
    h.setGeneration(8);
    await h.memo.get();
    expect(h.calls()).toBe(2);
  });

  it("does not keep a null answer", async () => {
    const h = harness();
    h.setAnswer(null);
    await h.memo.get();
    h.setAnswer(status());
    expect(await h.memo.get()).not.toBeNull();
    expect(h.calls()).toBe(2);
  });
});
