import { describe, expect, it } from "vitest";

import { CITES_KEYWORD, parseCites } from "../src/lib/query";

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
