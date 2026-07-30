import { describe, expect, it } from "vitest";

import { RateLimiter } from "../src/lib/ratelimit";

/** A clock the test drives, so a refill rate can be asserted without sleeping. */
function fakeClock() {
  let now = 1_000_000;
  return {
    now: () => now,
    advance(seconds: number) {
      now += seconds * 1000;
    },
  };
}

describe("RateLimiter", () => {
  it("allows exactly the burst, then sheds", () => {
    const clock = fakeClock();
    const limiter = new RateLimiter("test", 3, 1, clock.now);

    expect(limiter.check("a")).toBeNull();
    expect(limiter.check("a")).toBeNull();
    expect(limiter.check("a")).toBeNull();
    expect(limiter.check("a")).not.toBeNull();
  });

  it("counts each caller separately", () => {
    const clock = fakeClock();
    const limiter = new RateLimiter("test", 1, 1, clock.now);

    expect(limiter.check("a")).toBeNull();
    expect(limiter.check("a")).not.toBeNull();
    // b's budget is its own — the point of keying on the address at all.
    expect(limiter.check("b")).toBeNull();
  });

  it("refills at the sustained rate", () => {
    const clock = fakeClock();
    const limiter = new RateLimiter("test", 2, 0.5, clock.now);

    expect(limiter.check("a")).toBeNull();
    expect(limiter.check("a")).toBeNull();
    expect(limiter.check("a")).not.toBeNull();

    // Half a token at 0.5/s after one second: still not enough.
    clock.advance(1);
    expect(limiter.check("a")).not.toBeNull();

    // A whole one after two.
    clock.advance(2);
    expect(limiter.check("a")).toBeNull();
  });

  it("never refills past the burst capacity", () => {
    const clock = fakeClock();
    const limiter = new RateLimiter("test", 2, 1, clock.now);

    // An hour idle must not bank an hour's worth of requests.
    clock.advance(3600);
    expect(limiter.check("a")).toBeNull();
    expect(limiter.check("a")).toBeNull();
    expect(limiter.check("a")).not.toBeNull();
  });

  it("reports a Retry-After a caller can actually obey", () => {
    const clock = fakeClock();
    const limiter = new RateLimiter("test", 1, 0.5, clock.now);

    expect(limiter.check("a")).toBeNull();
    const wait = limiter.check("a");
    expect(wait).not.toBeNull();

    // Waiting exactly as long as told must be enough — a Retry-After that
    // returns a second 429 is worse than none, because it teaches clients to
    // ignore the header.
    clock.advance(wait!);
    expect(limiter.check("a")).toBeNull();
  });

  it("forgets refilled buckets, so the table cannot grow without bound", () => {
    const clock = fakeClock();
    const limiter = new RateLimiter("test", 1, 1, clock.now);

    for (let i = 0; i < 50; i++) limiter.check(`caller-${i}`);
    expect(limiter.size).toBe(50);

    // The sweep runs on write, past the interval, and drops every bucket that
    // has refilled — they hold no information a fresh one would not.
    clock.advance(RateLimiter.SWEEP_INTERVAL_MS / 1000 + 1);
    limiter.check("someone-new");
    expect(limiter.size).toBe(1);
  });

  it("keeps a bucket that is still spent when the sweep runs", () => {
    const clock = fakeClock();
    // Capacity 10 at 0.001/s takes 10,000s to refill — far longer than the
    // sweep interval, so this bucket must survive it.
    const limiter = new RateLimiter("test", 10, 0.001, clock.now);
    for (let i = 0; i < 10; i++) expect(limiter.check("heavy")).toBeNull();
    expect(limiter.check("heavy")).not.toBeNull();

    clock.advance(RateLimiter.SWEEP_INTERVAL_MS / 1000 + 1);
    limiter.check("someone-new");

    // Still limited: forgetting it here would hand out a fresh burst every ten
    // minutes, which is the bug a naive sweep introduces.
    expect(limiter.check("heavy")).not.toBeNull();
  });
});
