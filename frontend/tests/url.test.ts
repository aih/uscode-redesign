import { describe, expect, it } from "vitest";

import {
  apiDiffHref,
  apiHref,
  appHref,
  compareTitles,
  citationHref,
  diffHref,
  gotoHref,
  loginHref,
  provisionLabel,
  provisionsHref,
  signupHref,
  trimNum,
  unpadTitle,
  versionsHref,
} from "../src/lib/url";

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

describe("provisionsHref", () => {
  it("addresses My Provisions", () => {
    expect(provisionsHref()).toBe("/app/provisions");
  });
});

describe("loginHref and signupHref", () => {
  it("carry a next path, URL-encoded", () => {
    expect(loginHref("/app/us/usc/t16/s45f?release=119-99")).toBe(
      "/app/login?next=%2Fapp%2Fus%2Fusc%2Ft16%2Fs45f%3Frelease%3D119-99",
    );
    expect(signupHref("/app/provisions")).toBe("/app/signup?next=%2Fapp%2Fprovisions");
  });

  it("omit the query string with no next", () => {
    expect(loginHref()).toBe("/app/login");
    expect(signupHref(null)).toBe("/app/signup");
  });
});

describe("gotoHref", () => {
  it("is a bare form target with no query", () => {
    expect(gotoHref()).toBe("/app/goto");
    expect(gotoHref(null)).toBe("/app/goto");
  });

  it("encodes a citation, including the characters that mean something in a URL", () => {
    expect(gotoHref("11 usc 523(a)(1)")).toBe("/app/goto?q=11%20usc%20523(a)(1)");
    // `§` and `/` are the two that would otherwise change what was asked.
    expect(gotoHref("11 U.S.C. § 523")).toBe("/app/goto?q=11%20U.S.C.%20%C2%A7%20523");
    expect(gotoHref("/us/usc/t11/s523")).toBe("/app/goto?q=%2Fus%2Fusc%2Ft11%2Fs523");
  });
});

describe("en-dash identifiers (the ones OLRC actually publishes)", () => {
  // `/us/usc/t16/s45a–1` uses U+2013, as do 5,697 of the corpus's 65,938
  // sections. A raw one in a `Location:` header throws in Node — a header value
  // is a ByteString — so both redirects in this app 500'd on those sections.
  const EN_DASH = "/us/usc/t16/s45a–1";

  it("percent-encodes the dash in every href builder", () => {
    expect(appHref(EN_DASH)).toBe("/app/us/usc/t16/s45a%E2%80%931");
    expect(apiHref(EN_DASH)).toBe("/api/v1/us/usc/t16/s45a%E2%80%931");
    expect(citationHref(EN_DASH)).toBe("/us/usc/t16/s45a%E2%80%931");
    expect(versionsHref(EN_DASH)).toBe("/app/versions/us/usc/t16/s45a%E2%80%931");
  });

  it("leaves the path separators alone", () => {
    // encodeURI, not encodeURIComponent: the slashes are structure, not data.
    expect(appHref(EN_DASH)).toContain("/us/usc/t16/");
    expect(appHref(EN_DASH)).not.toContain("%2F");
  });

  it("still appends the release query after encoding", () => {
    expect(appHref(EN_DASH, "119-99")).toBe(
      "/app/us/usc/t16/s45a%E2%80%931?release=119-99",
    );
  });

  it("leaves an ordinary identifier byte-for-byte unchanged", () => {
    expect(appHref("/us/usc/t16/s45f/c/5")).toBe("/app/us/usc/t16/s45f/c/5");
  });
});

describe("title numbers (gotcha 16: a title number is a string, never an integer)", () => {
  it("unpads OLRC's file-naming form, which is not the identifier form", () => {
    expect(unpadTitle("05")).toBe("5");
    expect(unpadTitle("05a")).toBe("5a");
    expect(unpadTitle("16")).toBe("16");
    expect(unpadTitle("5")).toBe("5");
  });

  it("sorts the way the Code is bound, not the way strings compare", () => {
    const titles = ["11", "2", "05a", "10", "5", "50a", "1", "50", "54"];

    expect([...titles].sort(compareTitles)).toEqual([
      "1",
      "2",
      "5",
      "05a",
      "10",
      "11",
      "50",
      "50a",
      "54",
    ]);
    // The bug this exists to prevent: plain text sort puts 10 before 2.
    expect([...titles].sort()).not.toEqual([...titles].sort(compareTitles));
  });
});

describe("apiDiffHref", () => {
  it("points at the API's source-level redline, not the reader's", () => {
    expect(apiDiffHref("/us/usc/t16/s45f", "119-99", "119-102not101")).toBe(
      "/api/v1/sections/us/usc/t16/s45f/diff?from=119-99&to=119-102not101",
    );
  });

  it("percent-encodes an en-dash section number, like every other builder", () => {
    expect(apiDiffHref("/us/usc/t16/s45a\u20131", "119-99", "119-100")).toContain(
      "/sections/us/usc/t16/s45a%E2%80%931/diff",
    );
  });
});
