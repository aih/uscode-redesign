/**
 * A token bucket per caller — the reader's half of ADR-0029.
 *
 * The algorithm is deliberately the same as `params.RateLimiter` on the Python
 * side, so the two surfaces do not behave differently under load. It lives in
 * `lib/` rather than beside `middleware.ts` because that is where this project
 * puts logic it intends to test: the middleware is wiring and a policy choice,
 * this is the part with arithmetic in it.
 *
 * No lock, unlike the Python one: Node runs one request at a time between
 * awaits and `check` is synchronous throughout, so the read-modify-write cannot
 * interleave. FastAPI's sync handlers run in a threadpool and genuinely can.
 */

interface Bucket {
  tokens: number;
  updated: number;
}

/** Injectable clock. Real time by default; tests supply their own rather than
 *  sleeping, which is the only way to assert a refill rate honestly. */
export type Clock = () => number;

export class RateLimiter {
  /** How often to forget refilled buckets. The table is keyed by client address,
   *  so it needs a bound; sweeping on write costs one pass per interval and no
   *  timer. */
  static readonly SWEEP_INTERVAL_MS = 600_000;

  private readonly buckets = new Map<string, Bucket>();
  private swept: number;

  /**
   * @param name      For diagnostics, and so a limiter is identifiable in a test.
   * @param capacity  The burst a caller may spend at once.
   * @param refillPerSecond  The sustained rate, in requests per second.
   */
  constructor(
    readonly name: string,
    private readonly capacity: number,
    private readonly refillPerSecond: number,
    private readonly now: Clock = Date.now,
  ) {
    this.swept = now();
  }

  /** `null` if the request may proceed, else the seconds until it may. */
  check(key: string): number | null {
    const now = this.now();
    if (now - this.swept > RateLimiter.SWEEP_INTERVAL_MS) this.sweep(now);

    let bucket = this.buckets.get(key);
    if (!bucket) {
      bucket = { tokens: this.capacity, updated: now };
      this.buckets.set(key, bucket);
    }
    bucket.tokens = Math.min(
      this.capacity,
      bucket.tokens + ((now - bucket.updated) / 1000) * this.refillPerSecond,
    );
    bucket.updated = now;

    if (bucket.tokens < 1) {
      // Round up to a whole token, so a caller that obeys `Retry-After` comes
      // back able to spend rather than to a second 429.
      return Math.max(1, (1 - bucket.tokens) / this.refillPerSecond);
    }
    bucket.tokens -= 1;
    return null;
  }

  /** A full bucket is indistinguishable from one that never existed, so
   *  forgetting it changes no answer. That is what makes the sweep safe. */
  private sweep(now: number): void {
    const fullAfterMs = (this.capacity / this.refillPerSecond) * 1000;
    for (const [key, bucket] of this.buckets) {
      if (now - bucket.updated >= fullAfterMs) this.buckets.delete(key);
    }
    this.swept = now;
  }

  /** For tests and diagnostics. Nothing in the running app calls this. */
  get size(): number {
    return this.buckets.size;
  }
}
