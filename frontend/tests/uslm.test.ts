import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  copyableIdentifiers,
  highlightHtml,
  hrefs,
  parseFragment,
  render,
} from "../src/lib/uslm";
import type { Labels } from "../src/lib/types";

const NS = 'xmlns="http://xml.house.gov/schemas/uslm/1.0"';

describe("heading depth (Day 7 debt, cleared here)", () => {
  it("is not flat: nested levels get increasing <hN>, not <h2> everywhere", () => {
    const xml = `<section ${NS} identifier="/us/usc/t16/s45f"><num>§ 45f.</num><heading>Top</heading><subsection identifier="/us/usc/t16/s45f/a"><num>(a)</num><heading>Mid</heading><paragraph identifier="/us/usc/t16/s45f/a/1"><num>(1)</num><heading>Leaf</heading><content>text</content></paragraph></subsection></section>`;
    const html = render(parseFragment(xml), { target: null, release: null, labels: {} });

    expect(html).toContain("<h2 class=\"uslm-heading\">Top</h2>");
    expect(html).toContain("<h3 class=\"uslm-heading\">Mid</h3>");
    expect(html).toContain("<h4 class=\"uslm-heading\">Leaf</h4>");
  });

  it("caps at <h6> for USLM's deepest nesting rather than emitting an invalid tag", () => {
    const deep = ["section", "subsection", "paragraph", "subparagraph", "clause", "subclause", "item", "subitem"];
    let xml = "";
    let close = "";
    for (const tag of deep) {
      xml += `<${tag} ${tag === "section" ? NS : ""}><heading>H</heading>`;
      close = `</${tag}>` + close;
    }
    xml += close;
    const html = render(parseFragment(xml), { target: null, release: null, labels: {} });

    expect(html).toContain("<h6 class=\"uslm-heading\">H</h6>");
    expect(html).not.toMatch(/<h[7-9]/u);
  });
});

describe("notes and sourceCredit render as no-JS collapsibles", () => {
  it("wraps sourceCredit in <details><summary>", () => {
    const xml = `<section ${NS}><sourceCredit>(Pub. L. 100–1)</sourceCredit></section>`;
    const html = render(parseFragment(xml), { target: null, release: null, labels: {} });

    expect(html).toContain('<details class="uslm-details uslm-sourceCredit">');
    expect(html).toContain("<summary>Source</summary>");
  });

  it("wraps notes in <details><summary>", () => {
    const xml = `<section ${NS}><notes><note>See also Tables.</note></notes></section>`;
    const html = render(parseFragment(xml), { target: null, release: null, labels: {} });

    expect(html).toContain('<details class="uslm-details uslm-notes">');
    expect(html).toContain("<summary>Notes</summary>");
  });
});

describe("references (ADR-0015 decision 3)", () => {
  const labels: Labels = {
    "/us/usc/t16/s1": { identifier: "/us/usc/t16/s1", level: "section", num: "1", heading: "Short title" },
  };

  it("resolves an internal ref to the reader with hover text", () => {
    const xml = `<section ${NS}><p><ref href="/us/usc/t16/s1">section 1</ref></p></section>`;
    const html = render(parseFragment(xml), { target: null, release: "119-99", labels });

    expect(html).toContain('href="/app/us/usc/t16/s1?release=119-99"');
    expect(html).toContain('title="§ 1. Short title"');
  });

  it("renders an unresolvable reference as plain text, never a broken link", () => {
    const xml = `<section ${NS}><p><ref href="/us/pl/103/1">Pub. L. 103-1</ref></p></section>`;
    const html = render(parseFragment(xml), { target: null, release: "119-99", labels: {} });

    expect(html).toContain('<span class="uslm-ref-plain">Pub. L. 103-1</span>');
    expect(html).not.toContain("<a ");
  });
});

describe("preview hooks (ADR-0024)", () => {
  const internal = `<section ${NS}><p><ref href="/us/usc/t16/s1">section 1</ref></p></section>`;

  it("marks an internal reference with the identifier the card should fetch", () => {
    const html = render(parseFragment(internal), {
      target: null,
      release: "119-99",
      labels: {},
    });

    // The identifier, not the href: the island never has to un-prefix `/app`.
    expect(html).toContain('data-cite="/us/usc/t16/s1"');
    expect(html).toContain('data-cite-release="119-99"');
  });

  it("keeps title= alongside it", () => {
    // `title` is the no-JavaScript fallback, what a screen reader announces
    // (the card is aria-hidden), and what a touch device shows — the card never
    // opens there by design. Removing it would be a regression on three fronts.
    const labels: Labels = {
      "/us/usc/t16/s1": {
        identifier: "/us/usc/t16/s1",
        level: "section",
        num: "1",
        heading: "Short title",
      },
    };
    const html = render(parseFragment(internal), {
      target: null,
      release: "119-99",
      labels,
    });

    expect(html).toContain('title="§ 1. Short title"');
    expect(html).toContain("data-cite=");
  });

  it("omits the release when the page is not pinned to one", () => {
    const html = render(parseFragment(internal), {
      target: null,
      release: null,
      labels: {},
    });

    expect(html).toContain('data-cite="/us/usc/t16/s1"');
    expect(html).not.toContain("data-cite-release");
  });

  it("never marks a govinfo link — there is nothing here to preview", () => {
    const xml = `<section ${NS}><p><ref href="/us/stat/100/1">100 Stat. 1</ref></p></section>`;
    const html = render(parseFragment(xml), { target: null, release: "119-99", labels: {} });

    expect(html).toContain("govinfo.gov");
    expect(html).not.toContain("data-cite");
  });

  it("never marks an unresolvable reference, which is not a link at all", () => {
    const xml = `<section ${NS}><p><ref href="/us/act/1917-05-18">the Act</ref></p></section>`;
    const html = render(parseFragment(xml), { target: null, release: "119-99", labels: {} });

    expect(html).not.toContain("data-cite");
  });
});

describe("structure", () => {
  it("highlights the requested provision with the .target class", () => {
    const xml = `<section ${NS} identifier="/us/usc/t16/s45f"><subsection identifier="/us/usc/t16/s45f/a"><content>text</content></subsection></section>`;
    const html = render(parseFragment(xml), {
      target: "/us/usc/t16/s45f/a",
      release: null,
      labels: {},
    });

    expect(html).toContain('id="/us/usc/t16/s45f/a"');
    expect(html).toMatch(/class="uslm-subsection target"/u);
  });

  it("copies the source @class through, so indentN styling survives (BUILDLOG 008 item 1)", () => {
    const xml = `<section ${NS}><subsection class="indent2 firstIndent-2"><content>text</content></subsection></section>`;
    const html = render(parseFragment(xml), { target: null, release: null, labels: {} });

    expect(html).toContain('class="uslm-subsection indent2 firstIndent-2"');
  });

  it("renders a table with real HTML table tags, not divs", () => {
    const xml = `<section ${NS}><table><tr><td>a</td></tr></table></section>`;
    const html = render(parseFragment(xml), { target: null, release: null, labels: {} });

    expect(html).toContain("<table");
    expect(html).toContain("<tr");
    expect(html).toContain("<td");
  });
});

describe("hrefs", () => {
  it("collects every ref href in document order", () => {
    const xml = `<section ${NS}><p><ref href="/us/usc/t16/s1">a</ref></p><sourceCredit><ref href="/us/stat/123/1764">b</ref></sourceCredit></section>`;
    expect(hrefs(parseFragment(xml))).toEqual(["/us/usc/t16/s1", "/us/stat/123/1764"]);
  });
});

describe("highlightHtml", () => {
  // OpenSearch does not escape field content — it returns the stored text with
  // `<em>` around the matched terms. So a highlight fragment is untrusted text
  // with two known tags in it, and this is the only thing that may reach
  // `set:html` on the search page.

  it("keeps the highlighter's own em wrappers", () => {
    expect(highlightHtml("the <em>navigable</em> waters")).toBe(
      "the <em>navigable</em> waters",
    );
  });

  it("escapes markup that came from the indexed text", () => {
    expect(highlightHtml('<script>alert(1)</script>')).toBe(
      "&lt;script&gt;alert(1)&lt;/script&gt;",
    );
    expect(highlightHtml('<img src=x onerror="alert(1)">')).not.toContain("<img");
  });

  it("escapes a tag that merely looks like the highlighter's", () => {
    // `<embed>` starts with the same three letters; only the exact tag survives.
    expect(highlightHtml("<embed src=evil>")).toBe("&lt;embed src=evil&gt;");
    expect(highlightHtml("<em class=x>hi</em>")).toContain("&lt;em class=x&gt;");
  });

  it("escapes ampersands without double-escaping the ones it just made", () => {
    expect(highlightHtml("Fish & Wildlife")).toBe("Fish &amp; Wildlife");
    expect(highlightHtml("&lt;")).toBe("&amp;lt;");
  });
});

describe("link target (ADR-0031)", () => {
  const NS_ = `xmlns="http://xml.house.gov/schemas/uslm/1.0"`;
  const opts = { target: null, release: "119-99", labels: {} };

  it("opens an internal cross reference in a new tab", () => {
    const xml = `<section ${NS_}><p><ref href="/us/usc/t16/s1">section 1</ref></p></section>`;
    const html = render(parseFragment(xml), opts);
    expect(html).toContain('target="_blank"');
    // The preference undoes it by this attribute and nothing else, so a link
    // that opts in must always be findable.
    expect(html).toContain("data-newtab");
  });

  it("never emits target without rel=noopener", () => {
    // `target="_blank"` alone hands the opened page a live `window.opener`
    // handle on this one. The two must not come apart.
    for (const href of ["/us/usc/t16/s1", "/us/stat/100/1"]) {
      const xml = `<section ${NS_}><p><ref href="${href}">x</ref></p></section>`;
      const html = render(parseFragment(xml), opts);
      if (!html.includes('target="_blank"')) continue;
      expect(html).toContain('rel="noopener"');
    }
  });

  it("emits exactly one rel attribute on an external reference", () => {
    // The external branch already carried `rel="noopener"`; adding a second
    // `rel` would be invalid HTML and the browser would discard one of them —
    // silently dropping the protection from the links that leave this site.
    const xml = `<section ${NS_}><p><ref href="/us/stat/100/1">100 Stat. 1</ref></p></section>`;
    const html = render(parseFragment(xml), opts);
    const anchor = html.slice(html.indexOf("<a "), html.indexOf(">", html.indexOf("<a ")) + 1);
    expect(anchor.match(/\srel=/gu)?.length ?? 0).toBe(1);
  });

  it("leaves an unresolvable reference alone — it is not a link", () => {
    const xml = `<section ${NS_}><p><ref href="/us/act/1917-05-18">the Act</ref></p></section>`;
    const html = render(parseFragment(xml), opts);
    expect(html).not.toContain("target=");
    expect(html).not.toContain("data-newtab");
  });
});

describe("copyableIdentifiers — what the copy column offers a control for", () => {
  it("returns the section itself first, then its provisions in reading order", () => {
    const xml = `<section ${NS} identifier="/us/usc/t16/s45f"><num>§ 45f.</num><subsection identifier="/us/usc/t16/s45f/a"><num>(a)</num><content>one</content></subsection><subsection identifier="/us/usc/t16/s45f/c"><num>(c)</num><paragraph identifier="/us/usc/t16/s45f/c/5"><content>five</content></paragraph></subsection></section>`;

    expect(copyableIdentifiers(parseFragment(xml))).toEqual([
      "/us/usc/t16/s45f",
      "/us/usc/t16/s45f/a",
      "/us/usc/t16/s45f/c",
      "/us/usc/t16/s45f/c/5",
    ]);
  });

  it("skips elements that carry an identifier but are not provisions", () => {
    // `<num>` and `<content>` can carry identifiers of their own. A copy button
    // on a paragraph's number, an inch from the one on the paragraph, is two
    // controls doing nearly the same thing.
    const xml = `<section ${NS} identifier="/us/usc/t16/s45f"><num identifier="/us/usc/t16/s45f/num">§ 45f.</num><subsection identifier="/us/usc/t16/s45f/a"><content identifier="/us/usc/t16/s45f/a/content">text</content></subsection></section>`;

    expect(copyableIdentifiers(parseFragment(xml))).toEqual([
      "/us/usc/t16/s45f",
      "/us/usc/t16/s45f/a",
    ]);
  });

  it("skips a provision with no identifier, since there is nothing to cite", () => {
    const xml = `<section ${NS} identifier="/us/usc/t16/s45f"><subsection><content>unidentified</content></subsection></section>`;

    expect(copyableIdentifiers(parseFragment(xml))).toEqual(["/us/usc/t16/s45f"]);
  });

  it("offers one control when the source repeats an identifier (ADR-0021)", () => {
    // The page renders every occurrence, but `getElementById` finds only the
    // first — so a second button would silently copy the wrong body.
    const xml = `<section ${NS} identifier="/us/usc/t16/s45f"><subsection identifier="/us/usc/t16/s45f/a"><content>one</content></subsection><subsection identifier="/us/usc/t16/s45f/a"><content>again</content></subsection></section>`;

    expect(copyableIdentifiers(parseFragment(xml))).toEqual([
      "/us/usc/t16/s45f",
      "/us/usc/t16/s45f/a",
    ]);
  });
});

/**
 * The inline/block partition, driven by a measurement rather than a memory.
 *
 * `docs/verification/inline-elements.json` is produced by
 * `scripts/inline_elements.py`, which counts how often each USLM element sits
 * beside a non-whitespace text node across the committed samples. Anything it
 * finds in running prose has to render inline; the table below is read from
 * that file, so re-running the script is what adds a case here.
 *
 * `<date>` was in neither the inline set nor anyone's memory of it, and it
 * occurs in running prose 20,513 times and isolated zero times — every date in
 * every editorial note rendered as a block in the middle of its sentence.
 */
describe("elements that occur in running prose render inline", () => {
  const measured = JSON.parse(
    readFileSync(new URL("../../docs/verification/inline-elements.json", import.meta.url), "utf8"),
  );

  /** Elements measured in prose that are still deliberately blocks, with the
   * ratio that justifies each. Adding to this list is the escape hatch, and it
   * is meant to be a diff someone has to argue for. */
  const DELIBERATE_BLOCKS: Record<string, string> = {
    p: "50 of 58,865 — the source being odd",
    table: "26 of 822",
    list: "8 of 36",
    heading: "3 of 87,190 — a span here would cost the outline",
    proviso: "2 of 5",
    num: "1,933 of 128,991, and already a <span> via its own branch",
    br: "5 of 776, and already <br/>",
  };

  const wrap = (inner: string): string =>
    `<content ${NS}>The Act of ${inner} reserving lands.</content>`;

  const html = (inner: string): string =>
    render(parseFragment(wrap(inner)), { target: null, release: null, labels: {} });

  for (const element of measured.elements as { name: string; inline: number }[]) {
    const { name } = element;
    if (name in DELIBERATE_BLOCKS) continue;

    it(`<${name}> does not become a block inside a sentence (${element.inline} occurrences)`, () => {
      const out = html(`<${name}>X</${name}>`);
      // The failure this catches is a `<div>` — the fallback at the bottom of
      // renderElement — landing between two halves of a sentence.
      expect(out, `<${name}> rendered as a block`).not.toMatch(
        new RegExp(`<div[^>]*class="[^"]*uslm-${name}\\b`, "u"),
      );
      expect(out).toContain("The Act of");
      expect(out).toContain("reserving lands.");
    });
  }

  it("keeps <date> in the sentence rather than breaking the line", () => {
    const out = html("<date date=\"1970-10-21\">October 21, 1970</date>");
    expect(out).toContain('<span class="uslm-date"');
    expect(out).not.toContain('<div class="uslm-date"');
  });

  it("renders a <note> as a block when it is one, and inline when it is not", () => {
    const block = render(
      parseFragment(`<notes ${NS}><note><p>An editorial note.</p></note></notes>`),
      { target: null, release: null, labels: {} },
    );
    expect(block, "an isolated note is apparatus and keeps its box").toMatch(
      /<div[^>]*class="uslm-note"/u,
    );

    const inline = html("<note>1 See References in Text note below.</note>");
    expect(inline, "a note inside a sentence is part of it").toMatch(
      /<span[^>]*class="uslm-note uslm-inlined"/u,
    );
  });

  it("covers every element the measurement found, as inline or as a listed block", () => {
    const named = new Set([...Object.keys(DELIBERATE_BLOCKS)]);
    const unaccounted = (measured.elements as { name: string }[])
      .map((e) => e.name)
      .filter((name) => !named.has(name))
      .filter((name) => {
        const out = html(`<${name}>X</${name}>`);
        return new RegExp(`<div[^>]*class="[^"]*uslm-${name}\\b`, "u").test(out);
      });

    expect(
      unaccounted,
      "these elements occur in running prose and still render as a block — add them to " +
        "INLINE_TAGS or CONTEXTUAL_TAGS in src/lib/uslm.ts, or to DELIBERATE_BLOCKS here " +
        "with the ratio that justifies it",
    ).toEqual([]);
  });
});
