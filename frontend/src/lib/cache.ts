/**
 * What the reader may let a cache keep, mirroring `params.py` on the API side.
 *
 * The rule is the same one and it is worth restating, because getting it wrong
 * is silent: a page is immutable only when the caller **pinned a release point
 * and got the one they pinned**. `/app/us/usc/t16/s45f?release=119-99` can never
 * mean anything else. The same URL without `?release=`, or with `?date=`, is
 * answered from the newest ingested release point at or before the request — and
 * that answer changes the moment a newer release point is loaded. Caching those
 * forever would pin superseded law into caches with no way to invalidate it.
 *
 * The reader's pages carry no per-user state: the Watch button is a client-side
 * island that asks `/api/v1/auth/me` after paint, so the HTML is identical for
 * everyone and may be `public`. The pages that *are* per-user — "My Provisions",
 * login, signup — use `noStore` and say so.
 */

export const IMMUTABLE = "public, max-age=31536000, immutable";
export const REVALIDATE = "public, max-age=300";
export const NO_STORE = "private, no-store";

/** `immutable` only when a release point was asked for by name and honoured. */
export function cacheControl(
  requestedRelease: string | null | undefined,
  isExact: boolean,
): string {
  return requestedRelease && isExact ? IMMUTABLE : REVALIDATE;
}

/** Public page: cacheable, but by the rule above. */
export function setPublicCache(
  headers: Headers,
  requestedRelease: string | null | undefined,
  isExact: boolean,
): void {
  headers.set("Cache-Control", cacheControl(requestedRelease, isExact));
}

/** Per-user page: never stored, and keyed by cookie wherever it is considered. */
export function setNoStore(headers: Headers): void {
  headers.set("Cache-Control", NO_STORE);
  headers.set("Vary", "Cookie");
}
