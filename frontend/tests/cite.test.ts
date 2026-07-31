/**
 * `formatCitation` is the inverse of `citeparse.py`, and the copy widget's
 * whole value rests on it: a citation on someone's clipboard that this site
 * cannot resolve is worse than no copy button, because it looks right.
 *
 * So the interesting assertions here are the round trips — every example in
 * `citationforms.ts` names an identifier, and formatting that identifier has to
 * produce something the parser reads back to the same place. That check spans
 * two languages, so it is split: `tests/test_citation_forms.py` proves the
 * examples parse to those identifiers, and this file proves the identifiers
 * format to citations of the documented shape.
 */

import { describe, expect, it } from "vitest";

import { formatCitation } from "../src/lib/cite";
import { CITATION_FORMS } from "../src/lib/citationforms";

describe("formatCitation", () => {
  it("writes a section the way a citation writes it", () => {
    expect(formatCitation("/us/usc/t11/s523")).toBe("11 U.S.C. § 523");
  });

  it("writes subdivisions as parentheses, in order", () => {
    expect(formatCitation("/us/usc/t16/s45f/c/5")).toBe("16 U.S.C. § 45f(c)(5)");
    expect(formatCitation("/us/usc/t11/s523/a/1/B/ii")).toBe(
      "11 U.S.C. § 523(a)(1)(B)(ii)",
    );
  });

  it("keeps the case of a subdivision", () => {
    // `(B)` and `(b)` are different provisions and the identifiers distinguish
    // them, so lowercasing here would put a wrong citation on the clipboard
    // that still looks plausible.
    expect(formatCitation("/us/usc/t11/s523/a/1/B")).toContain("(B)");
    expect(formatCitation("/us/usc/t11/s523/b")).toBe("11 U.S.C. § 523(b)");
  });

  it("keeps a section number's letters and dashes", () => {
    expect(formatCitation("/us/usc/t42/s2000e-2")).toBe("42 U.S.C. § 2000e-2");
    // OLRC's en dash, U+2013 — 5,697 sections carry one (CLAUDE.md gotcha 17).
    expect(formatCitation("/us/usc/t16/s45a–1")).toBe("16 U.S.C. § 45a–1");
  });

  it("names an appendix title as an appendix", () => {
    expect(formatCitation("/us/usc/t5a/s3")).toBe("5 U.S.C. App. § 3");
  });

  it("writes a structural node with its level", () => {
    expect(formatCitation("/us/usc/t11/ch5")).toBe("11 U.S.C. ch. 5");
    expect(formatCitation("/us/usc/t16/schII")).toBe("16 U.S.C. subch. II");
  });

  it("writes a whole title as a title", () => {
    expect(formatCitation("/us/usc/t11")).toBe("Title 11, U.S. Code");
  });

  it("returns anything it does not recognise unchanged", () => {
    // A wrong citation is a silent wrong answer on someone's clipboard; the
    // raw identifier is at least true, and still resolves in the search box.
    expect(formatCitation("/us/cfr/t40/s1500")).toBe("/us/cfr/t40/s1500");
    expect(formatCitation("nonsense")).toBe("nonsense");
  });
});

describe("the documented citation forms round-trip", () => {
  // Rows whose identifier is not a plain section: `citeparse` accepts several
  // spellings and this formats one of them, so string equality with the row's
  // own `example` is the wrong test — the shape is what has to hold.
  it.each(CITATION_FORMS.map((form) => [form.example, form.identifier]))(
    "%s → %s formats to a citation naming the same title and section",
    (_example, identifier) => {
      const cite = formatCitation(identifier);
      expect(cite).not.toBe(identifier);

      const title = /^\/us\/usc\/t(\d+)([a-z]?)/u.exec(identifier);
      expect(title).not.toBeNull();
      expect(cite).toContain(title![1]);

      const section = /\/s([^/]+)/u.exec(identifier);
      if (section) {
        expect(cite).toContain("§ ");
        expect(cite).toContain(section[1]);
      }
    },
  );
});
