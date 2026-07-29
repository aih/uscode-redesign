import { describe, expect, it } from "vitest";

import { citedIdentifiers, resolveRef } from "../src/lib/refs";
import type { Labels } from "../src/lib/types";

describe("citedIdentifiers", () => {
  it("keeps only internal /us/usc/ hrefs, deduped and stripped of query/hash", () => {
    const found = citedIdentifiers([
      "/us/usc/t16/s1",
      "/us/usc/t16/s1?release=119-99",
      "/us/usc/t16/s1#c/5",
      "/us/stat/123/1764",
      "/us/pl/111/24",
    ]);
    expect(found).toEqual(["/us/usc/t16/s1"]);
  });

  it("is empty for a fragment with no internal citations", () => {
    expect(citedIdentifiers(["/us/stat/123/1764"])).toEqual([]);
  });
});

describe("resolveRef — the BUILDLOG 008 fix, verified against govinfo (ADR-0015)", () => {
  const labels: Labels = {
    "/us/usc/t16/s1": { identifier: "/us/usc/t16/s1", level: "section", num: "1", heading: "Short title" },
  };

  it("rewrites an internal reference to the reader, carrying the release point", () => {
    const resolved = resolveRef("/us/usc/t16/s1", "119-99", labels);
    expect(resolved.href).toBe("/app/us/usc/t16/s1?release=119-99");
  });

  it("labels an internal reference from the batched lookup", () => {
    const resolved = resolveRef("/us/usc/t16/s1", "119-99", labels);
    expect(resolved.title).toBe("§ 1. Short title");
  });

  it("does not error, and does not link falsely, for an internal reference missing from the batch", () => {
    const resolved = resolveRef("/us/usc/t16/s999999", "119-99", {});
    expect(resolved.href).toBe("/app/us/usc/t16/s999999?release=119-99");
    expect(resolved.title).toBeNull();
  });

  it("never emits a relative /us/stat/ href — govinfo's statute link service", () => {
    const resolved = resolveRef("/us/stat/123/1764", "119-99", {});
    expect(resolved.href).toBe("https://www.govinfo.gov/link/statute/123/1764");
  });

  it("never emits a relative /us/pl/ href for a public law at or after the 104th Congress", () => {
    const resolved = resolveRef("/us/pl/111/24/tV/s512", "119-99", {});
    expect(resolved.href).toBe("https://www.govinfo.gov/link/plaw/111/public/24");
  });

  it("degrades a pre-104th-Congress public law to plain text — govinfo answers 400", () => {
    const resolved = resolveRef("/us/pl/103/1", "119-99", {});
    expect(resolved.href).toBeNull();
  });

  it("degrades /us/act/ references to plain text — no local route serves them", () => {
    const resolved = resolveRef("/us/act/1946-08-08/ch960", "119-99", {});
    expect(resolved.href).toBeNull();
  });
});
