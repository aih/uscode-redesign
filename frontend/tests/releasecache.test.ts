import { describe, expect, it, vi } from "vitest";

import { currentGeneration, noteGeneration, resetGeneration } from "../src/lib/generation";
import { ReleaseCache, TTL_MS } from "../src/lib/releasecache";
import type { Release } from "../src/lib/types";

/** A clock the test drives, so a TTL can be asserted without sleeping. */
function fakeClock() {
  let now = 1_000_000;
  return {
    now: () => now,
    advance(ms: number) {
      now += ms;
    },
  };
}

function release(label: string): Release {
  return {
    label,
    currency_date: "2026-07-12",
    congress: 119,
    law_num: 102,
    excluded_laws: [],
    update_num: null,
    seq: 382,
    is_partial: false,
    caveat: null,
    titles_affected: ["16"],
    ingested_titles: ["16"],
  };
}

describe("ReleaseCache", () => {
  it("fetches once per title and serves the rest from memory", async () => {
    const clock = fakeClock();
    const fetcher = vi.fn(async () => [release("119-102not101")]);
    const cache = new ReleaseCache(fetcher, clock.now);

    await cache.get("16");
    await cache.get("16");
    await cache.get("16");

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("keys on the title, so two titles are two answers", async () => {
    const clock = fakeClock();
    const fetcher = vi.fn(async (titleNum?: string | null) => [release(`t${titleNum}`)]);
    const cache = new ReleaseCache(fetcher, clock.now);

    expect((await cache.get("16"))[0].label).toBe("t16");
    expect((await cache.get("42"))[0].label).toBe("t42");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("gives a title with no number its own entry rather than colliding", async () => {
    const clock = fakeClock();
    const fetcher = vi.fn(async () => [release("119-102not101")]);
    const cache = new ReleaseCache(fetcher, clock.now);

    await cache.get(null);
    await cache.get(undefined);
    await cache.get("16");

    // null and undefined are the same question; "16" is a different one.
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("re-fetches once the entry is older than the TTL, when no generation is known", async () => {
    const clock = fakeClock();
    const fetcher = vi.fn(async () => [release("119-102not101")]);
    const cache = new ReleaseCache(fetcher, clock.now);

    await cache.get("16");
    clock.advance(TTL_MS - 1);
    await cache.get("16");
    expect(fetcher).toHaveBeenCalledTimes(1);

    clock.advance(2);
    await cache.get("16");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("serves an entry while the corpus generation stands, with no clock at all", async () => {
    const clock = fakeClock();
    const fetcher = vi.fn(async () => [release("119-102not101")]);
    const cache = new ReleaseCache(fetcher, clock.now, TTL_MS, () => 41);

    await cache.get("16");
    // Days pass; nothing loads. The entry is still the corpus's own answer.
    clock.advance(TTL_MS * 1000);
    await cache.get("16");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("re-fetches the moment a newer generation has been seen — no window", async () => {
    const clock = fakeClock();
    let generation = 41;
    const fetcher = vi.fn(async () => [release("119-102not101")]);
    const cache = new ReleaseCache(fetcher, clock.now, TTL_MS, () => generation);

    await cache.get("16");
    generation = 42; // an ingest commit, reported by any response's header
    await cache.get("16");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("falls back to the TTL for an entry created before any generation arrived", async () => {
    const clock = fakeClock();
    let generation: number | null = null;
    const fetcher = vi.fn(async () => [release("119-102not101")]);
    const cache = new ReleaseCache(fetcher, clock.now, TTL_MS, () => generation);

    await cache.get("16");
    generation = 41; // the header starts arriving, but this entry predates it
    clock.advance(TTL_MS - 1);
    await cache.get("16");
    expect(fetcher).toHaveBeenCalledTimes(1);
    clock.advance(2);
    await cache.get("16");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("collapses concurrent misses into one request", async () => {
    const clock = fakeClock();
    let resolve: (value: Release[]) => void = () => {};
    const fetcher = vi.fn(
      () =>
        new Promise<Release[]>((r) => {
          resolve = r;
        }),
    );
    const cache = new ReleaseCache(fetcher, clock.now);

    // Eight readers of one title arriving together — the shape the load test
    // measured the box collapsing under.
    const waiting = Array.from({ length: 8 }, () => cache.get("16"));
    expect(fetcher).toHaveBeenCalledTimes(1);

    resolve([release("119-102not101")]);
    const answers = await Promise.all(waiting);
    expect(answers.every((a) => a[0].label === "119-102not101")).toBe(true);
  });

  it("does not cache a failure — the next view tries again", async () => {
    const clock = fakeClock();
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error("API 503"))
      .mockResolvedValueOnce([release("119-102not101")]);
    const cache = new ReleaseCache(fetcher, clock.now);

    await expect(cache.get("16")).rejects.toThrow("API 503");
    // Same instant, so a cached rejection would still be live.
    expect((await cache.get("16"))[0].label).toBe("119-102not101");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("a failure evicts only its own entry", async () => {
    const clock = fakeClock();
    let failLater: (error: Error) => void = () => {};
    const fetcher = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Release[]>((_, reject) => {
            failLater = reject;
          }),
      )
      .mockResolvedValue([release("119-102not101")]);
    const cache = new ReleaseCache(fetcher, clock.now);

    const doomed = cache.get("16");
    doomed.catch(() => {});
    // The slow failure is superseded before it settles.
    clock.advance(TTL_MS + 1);
    await cache.get("16");
    expect(cache.size()).toBe(1);

    failLater(new Error("too late"));
    await new Promise((r) => setTimeout(r, 0));
    // The replacement survives: eviction is guarded on still being current.
    expect(cache.size()).toBe(1);
  });
});

describe("the generation tracker", () => {
  it("starts unknown, follows the header, and never goes backwards", () => {
    resetGeneration();
    expect(currentGeneration()).toBe(null);

    noteGeneration("41");
    expect(currentGeneration()).toBe(41);

    noteGeneration("40"); // a slow response from before a load
    expect(currentGeneration()).toBe(41);

    noteGeneration("42");
    expect(currentGeneration()).toBe(42);
    resetGeneration();
  });

  it("ignores an absent or malformed header", () => {
    resetGeneration();
    noteGeneration(null);
    noteGeneration("not a number");
    noteGeneration("");
    expect(currentGeneration()).toBe(null);
    resetGeneration();
  });
});
