/**
 * The corpus generation, as this process has seen it (ADR-0078).
 *
 * Every API response whose handler read the generation carries
 * `X-Corpus-Generation`: a counter Postgres triggers move inside every ingest
 * write's own transaction. `getJson` reports each one here, and the release
 * memo (`releasecache.ts`) keys its entries on the value — so "has anything
 * loaded since this was fetched?" is answered by a fact rather than a clock.
 *
 * The tracker is monotonic: a slow response from before a load cannot drag the
 * process's view backwards. It is process-wide on purpose, the same shape as
 * the release memo it serves — which response the number arrived on does not
 * matter, only that the corpus has moved.
 */

let seen = 0;

/** Report a response's `X-Corpus-Generation` header. Ignores null and anything
 *  non-numeric, so an older API (or a proxy that strips the header) degrades to
 *  the tracker never advancing — the memo then falls back to its TTL. */
export function noteGeneration(value: string | null): void {
  if (value === null) return;
  const parsed = Number(value);
  if (Number.isFinite(parsed) && parsed > seen) seen = parsed;
}

/** The newest generation any response has carried, or null before the first —
 *  a fresh process that has not heard from the API yet. */
export function currentGeneration(): number | null {
  return seen > 0 ? seen : null;
}

/** Tests only. */
export function resetGeneration(): void {
  seen = 0;
}
