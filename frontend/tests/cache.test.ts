/**
 * The reader's half of ADR-0018. The rule these pin is the one that is silent
 * when it breaks: a page may only be cached forever if the URL named a release
 * point *and got it*. Everything else is answered from "newest ingested at or
 * before", which moves.
 */
import { describe, expect, it } from "vitest";

import {
  IMMUTABLE,
  NO_STORE,
  REVALIDATE,
  cacheControl,
  setNoStore,
  setPublicCache,
} from "../src/lib/cache";

describe("cacheControl", () => {
  it("pins a release point that was asked for by name and honoured", () => {
    expect(cacheControl("119-102not101", true)).toBe(IMMUTABLE);
  });

  it("never pins a request that named no release point", () => {
    expect(cacheControl(null, true)).toBe(REVALIDATE);
    expect(cacheControl(undefined, true)).toBe(REVALIDATE);
    expect(cacheControl("", true)).toBe(REVALIDATE);
  });

  it("never pins a label that resolved to a different release point", () => {
    // `119-102` was never published; it resolves to `119-102not101`. The URL
    // asked for something that does not exist, so its answer can still change.
    expect(cacheControl("119-102", false)).toBe(REVALIDATE);
  });
});

describe("response headers", () => {
  it("marks a per-user page unstorable and keyed by cookie", () => {
    const headers = new Headers();

    setNoStore(headers);

    expect(headers.get("Cache-Control")).toBe(NO_STORE);
    expect(headers.get("Vary")).toBe("Cookie");
  });

  it("does not add Vary: Cookie to a public page", () => {
    // The reader's section pages are identical for every visitor — the Watch
    // button is a client-side island — so varying on cookie would fragment the
    // cache for no benefit.
    const headers = new Headers();

    setPublicCache(headers, "119-99", true);

    expect(headers.get("Cache-Control")).toBe(IMMUTABLE);
    expect(headers.get("Vary")).toBeNull();
  });
});
