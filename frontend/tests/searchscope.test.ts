/**
 * The facet links edit the query string, so this is the format the URL of a
 * filtered search is written in — ADR-0049.
 *
 * The cross-language half of this is `tests/test_search_syntax.py`, which
 * checks that the scope *names* here and in `storage/searchquery.py` are the
 * same set. What that cannot check is the editing: whether adding a filter
 * twice adds it twice, whether removing one takes the words with it, whether a
 * quoted value survives a round trip. That is here.
 */
import { describe, expect, it } from "vitest";
import {
  hasScope,
  normaliseTitle,
  parseQuery,
  toggleScope,
  withScope,
  withoutScope,
} from "../src/lib/searchscope";

describe("parseQuery", () => {
  it("leaves a plain query alone", () => {
    expect(parseQuery("navigable waters")).toEqual({
      text: "navigable waters",
      scopes: [],
    });
  });

  it("lifts a scope out of the words", () => {
    expect(parseQuery("conservation title:16")).toEqual({
      text: "conservation",
      scopes: [{ name: "title", value: "16" }],
    });
  });

  it("keeps a quoted value in one piece", () => {
    // Without the quote arm in the tokenizer this splits at the space and
    // "horses" becomes free text — a different query, with no sign of it.
    expect(parseQuery('heading:"wild horses"')).toEqual({
      text: "",
      scopes: [{ name: "heading", value: "wild horses" }],
    });
  });

  it("leaves a prefix it does not implement in the text", () => {
    expect(parseQuery("see: also")).toEqual({ text: "see: also", scopes: [] });
  });

  it("leaves a scope with nothing after it in the text", () => {
    // `title:` filters on nothing. Searching for the characters returns
    // nothing findable, which is a truer answer than every section.
    expect(parseQuery("water title:")).toEqual({ text: "water title:", scopes: [] });
  });

  it("reads the time scopes without resolving them", () => {
    expect(parseQuery("conservation release:119-99").scopes).toEqual([
      { name: "release", value: "119-99" },
    ]);
  });
});

describe("normaliseTitle", () => {
  it("accepts both ways a drafter writes a title", () => {
    expect(normaliseTitle("t16")).toBe("16");
    expect(normaliseTitle("16")).toBe("16");
    expect(normaliseTitle("T5a")).toBe("5a");
  });

  it("does not eat a leading t off a word", () => {
    // `title:t` is not a title; only `t` followed by a digit is the prefix.
    expect(normaliseTitle("transferred")).toBe("transferred");
  });
});

describe("editing scopes", () => {
  it("adds a filter to the query", () => {
    expect(withScope("conservation", "title", "16")).toBe("conservation title:16");
  });

  it("does not add the same filter twice", () => {
    const once = withScope("conservation", "title", "16");
    expect(withScope(once, "title", "16")).toBe(once);
  });

  it("normalises as it adds, so t16 and 16 are one filter", () => {
    const once = withScope("conservation", "title", "16");
    expect(withScope(once, "title", "t16")).toBe(once);
  });

  it("removes a filter and keeps the words", () => {
    expect(withoutScope("conservation title:16", "title", "16")).toBe("conservation");
  });

  it("removes only the value asked for", () => {
    const both = withScope(withScope("water", "title", "16"), "title", "33");
    expect(withoutScope(both, "title", "16")).toBe("water title:33");
  });

  it("quotes a value that would otherwise split", () => {
    const q = withScope("", "heading", "wild horses");
    expect(q).toBe('heading:"wild horses"');
    expect(parseQuery(q).scopes).toEqual([{ name: "heading", value: "wild horses" }]);
  });

  it("keeps a release scope through a facet edit", () => {
    // The facet link rebuilds the whole query, so a scope it is not touching
    // has to survive the round trip or switching title silently drops the
    // release point the reader pinned.
    const q = toggleScope("conservation release:119-99", "title", "16");
    expect(parseQuery(q).scopes).toEqual([
      { name: "release", value: "119-99" },
      { name: "title", value: "16" },
    ]);
  });

  it("toggles off what is already on", () => {
    expect(toggleScope("conservation title:16", "title", "16")).toBe("conservation");
  });

  it("reports what is on", () => {
    expect(hasScope("conservation title:16", "title", "16")).toBe(true);
    expect(hasScope("conservation title:16", "title", "33")).toBe(false);
    expect(hasScope("conservation", "status", "repealed")).toBe(false);
  });
});
