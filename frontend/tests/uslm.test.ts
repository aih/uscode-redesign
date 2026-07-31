import { describe, expect, it } from "vitest";

import { highlightHtml, hrefs, parseFragment, render } from "../src/lib/uslm";
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
