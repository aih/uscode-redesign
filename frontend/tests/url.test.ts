import { describe, expect, it } from "vitest";

import {
  ancestorIdentifiers,
  apiDiffHref,
  apiHref,
  appHref,
  classificationEcctHref,
  classificationHref,
  classificationSuggestHref,
  compareTitles,
  citationHref,
  diffHref,
  govinfoPlawHref,
  normalizeSectionKey,
  sessionNumber,
  sessionSegment,
  statViewerHref,
  gotoHref,
  loginHref,
  provisionLabel,
  provisionsHref,
  safeNext,
  searchHref,
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

describe("safeNext", () => {
  // The auth forms carry `?next=` into `window.location.assign`. Untrusted, that
  // is an open redirect and a `javascript:` sink on the two pages in the app
  // where a password is being typed — so this is an allowlist, and these are the
  // cases the allowlist exists for.

  it("allows a path inside the reader, query string and all", () => {
    expect(safeNext("/app/us/usc/t16/s45f")).toBe("/app/us/usc/t16/s45f");
    expect(safeNext("/app/us/usc/t16/s45f?release=119-99")).toBe(
      "/app/us/usc/t16/s45f?release=119-99",
    );
  });

  it("falls back when there is nothing to go back to", () => {
    expect(safeNext(null)).toBe(provisionsHref());
    expect(safeNext(undefined)).toBe(provisionsHref());
    expect(safeNext("")).toBe(provisionsHref());
  });

  it("rejects an absolute URL on another origin", () => {
    expect(safeNext("https://evil.example/")).toBe(provisionsHref());
    expect(safeNext("http://evil.example/app/provisions")).toBe(provisionsHref());
  });

  it("rejects a protocol-relative URL, which is an authority and not a path", () => {
    expect(safeNext("//evil.example/")).toBe(provisionsHref());
    expect(safeNext("/\\evil.example/")).toBe(provisionsHref());
    expect(safeNext("\\\\evil.example/")).toBe(provisionsHref());
  });

  it("rejects javascript:, including the whitespace-obfuscated form", () => {
    expect(safeNext("javascript:alert(1)")).toBe(provisionsHref());
    // Browsers ignore control characters when parsing a URL, so a denylist that
    // matched the literal string would miss this one and `assign` would not.
    expect(safeNext("java\tscript:alert(1)")).toBe(provisionsHref());
    expect(safeNext("java\nscript:alert(1)")).toBe(provisionsHref());
    expect(safeNext(" javascript:alert(1)")).toBe(provisionsHref());
    expect(safeNext("data:text/html,<script>alert(1)</script>")).toBe(provisionsHref());
  });

  it("rejects a path outside the reader, including one that merely starts like it", () => {
    expect(safeNext("/api/v1/us/usc/t16/s45f")).toBe(provisionsHref());
    expect(safeNext("/appearances")).toBe(provisionsHref());
    expect(safeNext("/app")).toBe(provisionsHref());
  });
});

describe("searchHref", () => {
  it("builds a plain keyword search", () => {
    expect(searchHref("navigable waters")).toBe("/app/search?q=navigable+waters");
  });

  it("marks a cites query, so the results page can say what it actually did", () => {
    expect(searchHref("26 usc 501", { cites: true })).toBe(
      "/app/search?q=26+usc+501&cites=1",
    );
  });

  it("carries a release point when the search was pinned to one", () => {
    expect(searchHref("waters", { release: "119-99" })).toBe(
      "/app/search?q=waters&release=119-99",
    );
  });

  it("carries a date, which is the other way to name a moment in time", () => {
    // Missing until the syntax guide documented `&date=`, which is how the
    // pager came to drop it: `search.astro` rebuilds its own href from this
    // helper, so page two of a dated search reverted to the text in force.
    expect(searchHref("waters", { date: "06/12/2026" })).toBe(
      "/app/search?q=waters&date=06%2F12%2F2026",
    );
  });

  it("carries both halves of the query the pager has to reproduce", () => {
    expect(searchHref("26 usc 501", { cites: true, release: "119-99" })).toBe(
      "/app/search?q=26+usc+501&release=119-99&cites=1",
    );
  });

  it("encodes the characters that would otherwise change the query", () => {
    expect(searchHref("11 U.S.C. § 523")).toContain("%C2%A7");
    expect(searchHref("a&b")).toContain("a%26b");
  });
});

describe("ancestorIdentifiers", () => {
  it("walks up from nearest to furthest and stops at the title", () => {
    expect(ancestorIdentifiers("/us/usc/t16/s45f/c/5")).toEqual([
      "/us/usc/t16/s45f/c",
      "/us/usc/t16/s45f",
      "/us/usc/t16",
    ]);
  });

  it("offers the title for a section that does not exist", () => {
    expect(ancestorIdentifiers("/us/usc/t16/s99999")).toEqual(["/us/usc/t16"]);
  });

  it("stops above the title rather than offering /us/usc, which is not an identifier", () => {
    expect(ancestorIdentifiers("/us/usc/t16")).toEqual([]);
    expect(ancestorIdentifiers("/us/usc")).toEqual([]);
    expect(ancestorIdentifiers("/us")).toEqual([]);
  });

  it("refuses a path that is not a US Code identifier", () => {
    expect(ancestorIdentifiers("/uk/legislation/t16/s1")).toEqual([]);
    expect(ancestorIdentifiers("")).toEqual([]);
  });

  it("ignores a trailing slash rather than producing an empty last segment", () => {
    expect(ancestorIdentifiers("/us/usc/t16/s45f/")).toEqual(["/us/usc/t16"]);
  });

  it("keeps the en dash OLRC actually publishes (gotcha 17)", () => {
    expect(ancestorIdentifiers("/us/usc/t16/s45a\u20131/b")).toEqual([
      "/us/usc/t16/s45a\u20131",
      "/us/usc/t16",
    ]);
  });
});

describe("classification hrefs", () => {
  it("names the index when it has no congress and session", () => {
    expect(classificationHref()).toBe("/app/classification");
    expect(classificationHref(118)).toBe("/app/classification");
    expect(classificationHref(null, "2")).toBe("/app/classification");
  });

  it("names one table", () => {
    expect(classificationHref(118, "2")).toBe("/app/classification/118/2");
    expect(classificationHref(104, "all")).toBe("/app/classification/104/all");
  });

  it("omits the defaults, so one view has one URL", () => {
    expect(classificationHref(118, "2", { sort: "pl", offset: 0 })).toBe(
      "/app/classification/118/2",
    );
    expect(classificationHref(118, "2", { sort: "code" })).toBe(
      "/app/classification/118/2?sort=code",
    );
    expect(classificationHref(118, "2", { offset: 50 })).toBe(
      "/app/classification/118/2?offset=50",
    );
  });

  it("carries the filters under the API's own parameter names", () => {
    expect(classificationHref(118, "2", { pl: "118-42", plSection: "793", title: "7" })).toBe(
      "/app/classification/118/2?pl=118-42&pl_section=793&title=7",
    );
  });

  it("normalizes a typed section to the plain hyphen section_norm carries", () => {
    // The corpus spells `254c-15` with an EN DASH and `section_norm` with a
    // hyphen (gotcha 17, spec \u00a7 What Wave 1 measured 3). Typed input is matched
    // against the latter.
    expect(classificationHref(118, "2", { section: "254C\u201315" })).toBe(
      "/app/classification/118/2?section=254c-15",
    );
  });

  it("has one address for the ECCT", () => {
    expect(classificationEcctHref()).toBe("/app/classification/ecct");
  });

  it("encodes the suggest query rather than pasting it into a URL", () => {
    expect(classificationSuggestHref("118-33 101")).toBe(
      "/api/v1/classifications/suggest?q=118-33%20101",
    );
    // The island appends its own encoded query to this.
    expect(classificationSuggestHref("")).toBe("/api/v1/classifications/suggest?q=");
  });
});

describe("classification sessions", () => {
  it("writes the 104th's whole-congress file as `all`", () => {
    expect(sessionSegment(0)).toBe("all");
    expect(sessionSegment(1)).toBe("1");
    expect(sessionSegment(2)).toBe("2");
  });

  it("reads it back", () => {
    expect(sessionNumber("all")).toBe(0);
    expect(sessionNumber("1")).toBe(1);
    expect(sessionNumber("2")).toBe(2);
  });

  it("refuses anything that is not a session, so the page can 404", () => {
    expect(sessionNumber("0")).toBeNull();
    expect(sessionNumber("3")).toBeNull();
    expect(sessionNumber("")).toBeNull();
    expect(sessionNumber("../etc")).toBeNull();
  });
});

describe("normalizeSectionKey", () => {
  it("lowercases and folds every dash the source uses onto the plain hyphen", () => {
    expect(normalizeSectionKey(" 254C\u201315 ")).toBe("254c-15");
    expect(normalizeSectionKey("45A\u20111")).toBe("45a-1");
    expect(normalizeSectionKey("45a-1")).toBe("45a-1");
  });
});

describe("the two source links a classification row carries", () => {
  it("builds govinfo's public law page from (congress, number)", () => {
    expect(govinfoPlawHref(118, 42)).toBe("https://www.govinfo.gov/app/details/PLAW-118publ42");
  });

  it("builds OLRC's statviewer from (volume, page)", () => {
    expect(statViewerHref(138, 290)).toBe(
      "https://uscode.house.gov/statviewer.htm?volume=138&page=290",
    );
  });
});
