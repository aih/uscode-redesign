import { describe, expect, it } from "vitest";

import {
  CITES_KEYWORD,
  HISTORY_KEYWORD,
  HISTORY_SHORT_KEYWORD,
  parseCites,
  parseHistory,
} from "../src/lib/query";

describe("parseCites", () => {
  // The one routing decision the header's single box can make without asking
  // the API. Everything else — "is this a citation?" — is `citeparse`'s call.

  it("takes the citation out of a cites query", () => {
    expect(parseCites("cites 26 usc 501")).toEqual({ subject: "26 usc 501" });
  });

  it("does not care about case or surrounding space", () => {
    expect(parseCites("  CITES 26 usc 501  ")).toEqual({ subject: "26 usc 501" });
    expect(parseCites("Cites 11 U.S.C. § 523(a)(1)")).toEqual({
      subject: "11 U.S.C. § 523(a)(1)",
    });
  });

  it("needs a whole word, so an ordinary search starting with those letters is not one", () => {
    // Someone searching the text for this word is not asking for a reverse
    // lookup, and silently giving them one would be worse than useless.
    expect(parseCites("citespersons")).toBeNull();
    expect(parseCites("citesomething 26 usc 501")).toBeNull();
  });

  it("is not a cites query with no subject to look up", () => {
    expect(parseCites("cites")).toBeNull();
    expect(parseCites("  cites   ")).toBeNull();
  });

  it("leaves an ordinary keyword search alone", () => {
    expect(parseCites("navigable waters")).toBeNull();
    expect(parseCites("26 usc 501")).toBeNull();
    expect(parseCites("")).toBeNull();
  });

  it("keeps a subject that itself contains the word", () => {
    expect(parseCites("cites cites")).toEqual({ subject: "cites" });
  });

  it("exports the keyword the UI shows, so the hint and the parser cannot drift", () => {
    expect(CITES_KEYWORD).toBe("cites");
    expect(parseCites(`${CITES_KEYWORD} 26 usc 501`)).not.toBeNull();
  });
});

describe("parseHistory", () => {
  // The second prefix the box reads without the API (ADR-0084). The citation
  // after it is still `citeparse`'s to read; only the keyword and a trailing
  // date range are lifted here.

  it("takes the citation out of a history query", () => {
    expect(parseHistory("history 16 usc 45f")).toEqual({
      keyword: "history",
      subject: "16 usc 45f",
      from: null,
      to: null,
    });
  });

  it("does not care about case or surrounding space", () => {
    expect(parseHistory("  HISTORY 11 U.S.C. § 523(a)(1)  ")).toEqual({
      keyword: "history",
      subject: "11 U.S.C. § 523(a)(1)",
      from: null,
      to: null,
    });
  });

  it("reads a date range off the end, in either date form", () => {
    expect(parseHistory("history 16 usc 2201 from 6/12/2026 to 7/12/2026")).toEqual({
      keyword: "history",
      subject: "16 usc 2201",
      from: "6/12/2026",
      to: "7/12/2026",
    });
    expect(parseHistory("history 16 usc 2201 between 2026-06-12 and 2026-07-12")).toEqual({
      keyword: "history",
      subject: "16 usc 2201",
      from: "2026-06-12",
      to: "2026-07-12",
    });
  });

  it("reads a start alone, which runs to today", () => {
    expect(parseHistory("history 16 usc 2201 since 2024-01-01")).toEqual({
      keyword: "history",
      subject: "16 usc 2201",
      from: "2024-01-01",
      to: null,
    });
  });

  it("leaves a range it cannot read in the subject", () => {
    // `citeparse` will refuse it and the page says why; guessing at a date
    // here would send the reader somewhere with the wrong dates in the URL.
    expect(parseHistory("history 16 usc 2201 from yesterday")).toEqual({
      keyword: "history",
      subject: "16 usc 2201 from yesterday",
      from: null,
      to: null,
    });
  });

  it("needs a whole word and a subject", () => {
    expect(parseHistory("historyof 16 usc 45f")).toBeNull();
    expect(parseHistory("history")).toBeNull();
    expect(parseHistory("legislative history")).toBeNull();
  });

  it("reads v as the short form, with or without a space before a digit", () => {
    for (const typed of ["v 16 usc 2201", "V 16 usc 2201"]) {
      expect(parseHistory(typed)).toEqual({ keyword: "v", subject: "16 usc 2201", from: null, to: null });
    }
    for (const typed of ["v16/2201", "v 16/2201"]) {
      expect(parseHistory(typed)).toEqual({ keyword: "v", subject: "16/2201", from: null, to: null });
    }
    expect(parseHistory("v16/2201 from 6/12/2026 to 7/12/2026")).toEqual({
      keyword: "v",
      subject: "16/2201",
      from: "6/12/2026",
      to: "7/12/2026",
    });
  });

  it("does not read a word starting with v as the short form", () => {
    expect(parseHistory("vessels")).toBeNull();
    expect(parseHistory("veterans 38 usc 101")).toBeNull();
    expect(parseHistory("v")).toBeNull();
    expect(parseHistory("history16/2201")).toBeNull();
  });

  it("exports the keyword the UI shows, so the hint and the parser cannot drift", () => {
    expect(HISTORY_KEYWORD).toBe("history");
    expect(parseHistory(`${HISTORY_KEYWORD} 16 usc 45f`)).not.toBeNull();
    expect(HISTORY_SHORT_KEYWORD).toBe("v");
    expect(parseHistory(`${HISTORY_SHORT_KEYWORD} 16 usc 45f`)).not.toBeNull();
  });
});
