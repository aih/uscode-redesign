import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { hrefs, parseFragment, render } from "../src/lib/uslm";
import { citedIdentifiers } from "../src/lib/refs";
import type { UslmElement } from "../src/lib/uslm";

/** The same 878 KB verbatim slice the Python suite renders against
 * (`tests/fixtures/usc16_slice.xml`, CLAUDE.md Fixtures) — one file, shared
 * across both suites, so a schema surprise shows up in either. */
const SLICE_PATH = fileURLToPath(new URL("../../tests/fixtures/usc16_slice.xml", import.meta.url));

function realSections(): UslmElement[] {
  const xml = readFileSync(SLICE_PATH, "utf-8");
  const doc = parseFragment(xml);
  const found: UslmElement[] = [];
  const walk = (el: UslmElement) => {
    const tag = el.localName ?? el.tagName;
    // ADR-0005: a <section> with no @identifier is quoted text inside
    // <quotedContent>, not a real code section — skip it, the same rule the
    // Python parser applies.
    if (tag === "section" && el.getAttribute("identifier")) found.push(el);
    for (let i = 0; i < el.childNodes.length; i++) {
      const child = el.childNodes[i];
      if (child.nodeType === 1) walk(child as UslmElement);
    }
  };
  walk(doc);
  return found;
}

describe("real sections from the shared fixture (BUILDLOG 014's parity bar)", () => {
  const sections = realSections();

  it("finds a non-trivial number of real sections", () => {
    expect(sections.length).toBeGreaterThan(50);
  });

  it("renders every one without throwing", () => {
    for (const section of sections) {
      expect(() => render(section, { target: null, release: "119-102not101", labels: {} })).not.toThrow();
    }
  });

  it("never ships a relative /us/pl/ or /us/stat/ href (the BUILDLOG 008 bug)", () => {
    for (const section of sections) {
      const html = render(section, { target: null, release: "119-102not101", labels: {} });
      expect(html).not.toMatch(/href="\/us\/(pl|stat)\//u);
    }
  });

  it("collects only /us/usc/ identifiers for the batched labels call", () => {
    for (const section of sections) {
      for (const identifier of citedIdentifiers(hrefs(section))) {
        expect(identifier.startsWith("/us/usc/")).toBe(true);
      }
    }
  });
});
