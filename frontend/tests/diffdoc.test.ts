/**
 * The reading-text redline (ADR-0026).
 *
 * The bug this whole module exists to fix has a test of its own below: two
 * release points of an untouched section differ in every `@id` and in nothing
 * a reader can see, and the redline has to say so.
 */
import { describe, expect, it } from "vitest";

import { diffLinesHtml, documentDiff, sourceDelta } from "../src/lib/diffdoc";
import { parseFragment, readingBlocks } from "../src/lib/uslm";

const NS = 'xmlns="http://xml.house.gov/schemas/uslm/1.0"';

function blocks(xml: string) {
  return readingBlocks(parseFragment(xml));
}

function diffOf(a: string, b: string) {
  return documentDiff(blocks(a), blocks(b));
}

describe("readingBlocks: the document as lines a reader reads", () => {
  it("keeps a num and its text on one line", () => {
    const xml = `<section ${NS}><num>§ 45f.</num><heading>Mineral King</heading><subsection identifier="/us/usc/t16/s45f/a"><num>(a)</num><content>The Secretary shall act.</content></subsection></section>`;

    expect(blocks(xml).map((b) => b.text)).toEqual([
      "§ 45f. Mineral King",
      "(a) The Secretary shall act.",
    ]);
  });

  it("counts depth in levels, so a clause reads at the depth it lives at", () => {
    const xml = `<section ${NS}><num>§ 1.</num><subsection><num>(a)</num><paragraph><num>(1)</num><content>Deep.</content></paragraph></subsection></section>`;

    expect(blocks(xml).map((b) => b.depth)).toEqual([1, 2, 3]);
  });

  it("puts a continuation after the paragraphs it follows, not merged into the line above", () => {
    const xml = `<section ${NS}><subsection><num>(a)</num><chapeau>Whoever—</chapeau><paragraph><num>(1)</num><content>does a thing;</content></paragraph><continuation>shall be fined.</continuation></subsection></section>`;

    expect(blocks(xml).map((b) => b.text)).toEqual([
      "(a) Whoever—",
      "(1) does a thing;",
      "shall be fined.",
    ]);
  });

  it("marks notes and source credit as apparatus, not statutory text", () => {
    const xml = `<section ${NS}><content>Text.</content><sourceCredit>(Pub. L. 100–1)</sourceCredit><notes><note>Effective date.</note><note>Transfer.</note></notes></section>`;

    expect(blocks(xml).map((b) => [b.kind, b.text])).toEqual([
      ["text", "Text."],
      ["note", "(Pub. L. 100–1)"],
      ["note", "Effective date."],
      ["note", "Transfer."],
    ]);
  });

  it("breaks a note into its own paragraphs — one of them can be a whole Executive Order", () => {
    const xml = `<section ${NS}><notes><note><heading>Ex. Ord. No. 13648</heading><p>Provided:</p><p>By the authority vested in me…</p></note></notes></section>`;

    expect(blocks(xml).map((b) => b.text)).toEqual([
      "Ex. Ord. No. 13648",
      "Provided:",
      "By the authority vested in me…",
    ]);
  });

  it("normalizes the whitespace the source wraps its lines with", () => {
    const xml = `<section ${NS}><content>\n      The Secretary\n      shall act.\n    </content></section>`;

    expect(blocks(xml)[0].text).toBe("The Secretary shall act.");
  });

  it("drops nothing that carries text, and no markup gets in", () => {
    const xml = `<section ${NS}><content>See <ref href="/us/usc/t16/s1">section 1</ref> of this title.</content></section>`;
    const [line] = blocks(xml);

    expect(line.text).toBe("See section 1 of this title.");
    expect(line.text).not.toContain("<");
  });
});

describe("documentDiff", () => {
  it("reports no change when only the guids moved — the reason this exists", () => {
    // Every `@id` regenerates at every release point by design (gotcha 1). The
    // source-level redline of these two is hundreds of ops; the reading text is
    // identical, and that is what the page now says.
    const before = `<section ${NS} id="ida1" identifier="/us/usc/t16/s45f"><num id="ida2">§ 45f.</num><content id="ida3">The Secretary shall act.</content></section>`;
    const after = `<section ${NS} id="idb9" identifier="/us/usc/t16/s45f"><num id="idb8">§ 45f.</num><content id="idb7">The Secretary shall act.</content></section>`;

    const diff = diffOf(before, after);

    expect(diff).toMatchObject({ changed: 0, inserted: 0, deleted: 0 });
    expect(diff.lines.every((line) => line.mark === "equal")).toBe(true);
  });

  it("shows an edited line once, with the words that changed marked inside it", () => {
    const before = `<section ${NS}><content>The Secretary shall pay $5,000,000 to the State.</content></section>`;
    const after = `<section ${NS}><content>The Secretary shall pay $7,500,000 to the State.</content></section>`;

    const diff = diffOf(before, after);

    expect(diff.changed).toBe(1);
    expect(diff.lines).toHaveLength(1);
    const [line] = diff.lines;
    expect(line.mark).toBe("changed");
    expect(line.spans.filter((s) => s.mark === "delete").map((s) => s.text).join("")).toContain("5,000,000");
    expect(line.spans.filter((s) => s.mark === "insert").map((s) => s.text).join("")).toContain("7,500,000");
  });

  it("does not pretend an unrelated replacement is an edit of the same line", () => {
    const before = `<section ${NS}><content>Appropriations are authorized for fiscal year 2019.</content></section>`;
    const after = `<section ${NS}><content>Nothing in this chapter affects tribal water rights.</content></section>`;

    const diff = diffOf(before, after);

    expect(diff.changed).toBe(0);
    expect(diff.deleted).toBe(1);
    expect(diff.inserted).toBe(1);
    expect(diff.lines.map((l) => l.mark)).toEqual(["delete", "insert"]);
  });

  it("aligns around an inserted paragraph rather than re-marking everything after it", () => {
    const before = `<section ${NS}><subsection><num>(a)</num><content>First.</content></subsection><subsection><num>(c)</num><content>Third.</content></subsection></section>`;
    const after = `<section ${NS}><subsection><num>(a)</num><content>First.</content></subsection><subsection><num>(b)</num><content>Second.</content></subsection><subsection><num>(c)</num><content>Third.</content></subsection></section>`;

    const diff = diffOf(before, after);

    expect(diff.inserted).toBe(1);
    expect(diff.changed + diff.deleted).toBe(0);
    expect(diff.lines.map((l) => l.mark)).toEqual(["equal", "insert", "equal"]);
  });

  it("treats the same sentence at a new depth as a change", () => {
    const before = `<section ${NS}><subsection><content>Same words.</content></subsection></section>`;
    const after = `<section ${NS}><subsection><paragraph><content>Same words.</content></paragraph></subsection></section>`;

    const diff = diffOf(before, after);

    expect(diff.inserted + diff.deleted + diff.changed).toBeGreaterThan(0);
  });
});

describe("diffLinesHtml", () => {
  it("escapes the text and marks the runs", () => {
    const before = `<section ${NS}><content>a &lt;b&gt; c</content></section>`;
    const after = `<section ${NS}><content>a &lt;b&gt; d</content></section>`;

    const html = diffLinesHtml(diffOf(before, after).lines);

    expect(html).toContain("&lt;b&gt;");
    expect(html).not.toContain("<b>");
    expect(html).toMatch(/<ins>d<\/ins>/u);
    expect(html).toMatch(/<del>c<\/del>/u);
  });

  it("carries the outline depth as a custom property, and the kind as a class", () => {
    const xml = `<section ${NS}><subsection><content>Text.</content></subsection><notes><note>A note.</note></notes></section>`;
    const html = diffLinesHtml(documentDiff([], readingBlocks(parseFragment(xml))).lines);

    expect(html).toContain('style="--depth: 1"');
    expect(html).toContain("diff-line--note");
  });
});

describe("sourceDelta", () => {
  // An empty redline means "nothing you can read changed", which is a weaker
  // claim than "nothing changed". These are the three things it can mean.

  it("calls two byte-identical fragments identical", () => {
    const xml = '<section identifier="/us/usc/t16/s45f" id="idAAA"><p>Text.</p></section>';
    expect(sourceDelta(xml, xml)).toBe("identical");
  });

  it("recognises regenerated guids as the only difference", () => {
    // Guids regenerate at every release point by design (gotcha 1) — this is
    // the churn ADR-0026 moved the reader off, and it is not a legal change.
    const before = '<section identifier="/us/usc/t16/s45f" id="idAAA"><p id="idBBB">Text.</p></section>';
    const after = '<section identifier="/us/usc/t16/s45f" id="idCCC"><p id="idDDD">Text.</p></section>';
    expect(sourceDelta(before, after)).toBe("guids-only");
  });

  it("does not mistake temporalId or xml:id for the guid attribute", () => {
    // `\s` before `id=` is what keeps those two out; if it stopped working,
    // a real @temporalId change would be reported as guid churn.
    const before = '<section temporalId="s45f_a" id="idAAA">Text.</section>';
    const after = '<section temporalId="s45f_b" id="idCCC">Text.</section>';
    expect(sourceDelta(before, after)).toBe("beyond-guids");
  });

  it("reports a whitespace-only change, which the reading redline cannot see", () => {
    // ADR-0026's named cost, stated as a test so the page can name it too.
    const before = '<section id="idAAA"><p>Text.</p></section>';
    const after = '<section id="idAAA"><p>Text.</p>\n</section>';
    expect(sourceDelta(before, after)).toBe("beyond-guids");
  });

  it("reports a changed attribute that carries no words", () => {
    const before = '<section id="idAAA" status="operational">Text.</section>';
    const after = '<section id="idAAA" status="repealed">Text.</section>';
    expect(sourceDelta(before, after)).toBe("beyond-guids");
  });

  it("handles single-quoted attributes", () => {
    expect(sourceDelta("<section id='idAAA'>T.</section>", "<section id='idCCC'>T.</section>")).toBe(
      "guids-only",
    );
  });
});
