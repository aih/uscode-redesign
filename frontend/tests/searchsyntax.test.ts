import { describe, expect, it } from "vitest";

import { SEARCH_OPERATORS, fuzzify } from "../src/lib/searchsyntax";

describe("fuzzify", () => {
  it("loosens every word, not just the last one", () => {
    // The bug this exists to prevent: appending `~1` to the *query* rather than
    // to each term produces `water polution~1`, which tolerates a misspelling
    // in the word the reader spelled correctly and not in the one they did not.
    expect(fuzzify("water polution")).toBe("water~1 polution~1");
  });

  it("leaves a phrase alone", () => {
    // `"navigable waters"~1` is a proximity search, not a fuzzy one — a
    // different query than the reader is being offered.
    expect(fuzzify('"navigable waters"')).toBe('"navigable waters"');
  });

  it("leaves terms that already carry syntax alone", () => {
    expect(fuzzify("navigab* water")).toBe("navigab* water~1");
    expect(fuzzify("water -pollution")).toBe("water~1 -pollution");
    expect(fuzzify("conservation~2")).toBe("conservation~2");
    expect(fuzzify("(forest | grassland)")).toBe("(forest | grassland)");
  });

  it("collapses stray whitespace rather than emitting empty terms", () => {
    expect(fuzzify("  water   land  ")).toBe("water~1 land~1");
  });

  it("is a no-op on an empty query", () => {
    expect(fuzzify("")).toBe("");
  });
});

describe("the documented operator list", () => {
  it("gives every operator a flag, an example and an explanation", () => {
    // The guide's table renders all four; a blank cell would be a promise the
    // page makes and does not keep.
    for (const operator of SEARCH_OPERATORS) {
      expect(operator.flag).toBeTruthy();
      expect(operator.syntax).toBeTruthy();
      expect(operator.example).toBeTruthy();
      expect(operator.explanation.length).toBeGreaterThan(20);
    }
  });

  it("documents each flag exactly once", () => {
    const flags = SEARCH_OPERATORS.map((operator) => operator.flag);
    expect(new Set(flags).size).toBe(flags.length);
  });
});
