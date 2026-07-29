import { describe, expect, it } from "vitest";

import { apiHref, appHref, citationHref, diffHref, provisionLabel, trimNum, versionsHref } from "../src/lib/url";

describe("trimNum", () => {
  it("strips a single trailing period so the page's own punctuation doesn't double up", () => {
    expect(trimNum("45f.")).toBe("45f");
  });

  it("passes through a num with no trailing period", () => {
    expect(trimNum("45f")).toBe("45f");
  });

  it("is empty for null or undefined", () => {
    expect(trimNum(null)).toBe("");
    expect(trimNum(undefined)).toBe("");
  });
});

describe("provisionLabel", () => {
  it("wraps each bare designator in its own parens, without naming a level", () => {
    expect(provisionLabel("/c/5")).toBe("(c)(5)");
  });

  it("is empty for the section itself", () => {
    expect(provisionLabel("")).toBe("");
  });
});

describe("appHref", () => {
  it("carries the release point when given one", () => {
    expect(appHref("/us/usc/t16/s45f", "119-99")).toBe("/app/us/usc/t16/s45f?release=119-99");
  });

  it("omits the query string with no release", () => {
    expect(appHref("/us/usc/t16")).toBe("/app/us/usc/t16");
  });
});

describe("apiHref", () => {
  it("builds the machine-surface URL with both release and format", () => {
    expect(apiHref("/us/usc/t16/s45f", { release: "119-99", format: "xml" })).toBe(
      "/api/v1/us/usc/t16/s45f?release=119-99&format=xml",
    );
  });
});

describe("citationHref", () => {
  it("is the bare, pasteable citation — no /app or /api prefix", () => {
    expect(citationHref("/us/usc/t16/s45f/c/5", "119-102not101")).toBe(
      "/us/usc/t16/s45f/c/5?release=119-102not101",
    );
  });
});

describe("versionsHref and diffHref", () => {
  it("addresses the timeline page", () => {
    expect(versionsHref("/us/usc/t16/s45f")).toBe("/app/versions/us/usc/t16/s45f");
  });

  it("addresses the diff page with both release points", () => {
    expect(diffHref("/us/usc/t16/s45f", "119-99", "119-102not101")).toBe(
      "/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101",
    );
  });
});
