import { describe, expect, it } from "vitest";

import { sourceRedline } from "../src/lib/xmlredline";

describe("sourceRedline", () => {
  const BEFORE = '<section identifier="/us/usc/t16/s45f" id="idAAA"><p>Five dollars.</p></section>';

  it("marks an insertion and a deletion", () => {
    const after = BEFORE.replace("Five", "Ten");
    const { html, inserted, deleted } = sourceRedline(BEFORE, after);

    expect(html).toContain("<ins>");
    expect(html).toContain("<del>");
    expect(inserted).toBeGreaterThan(0);
    expect(deleted).toBeGreaterThan(0);
  });

  it("reports nothing changed for identical fragments", () => {
    const { html, inserted, deleted } = sourceRedline(BEFORE, BEFORE);
    expect(inserted).toBe(0);
    expect(deleted).toBe(0);
    expect(html).not.toContain("<ins>");
    expect(html).not.toContain("<del>");
  });

  it("escapes the XML before colouring it, so no source tag becomes a real one", () => {
    // The whole fragment is markup, and none of it may reach the browser as
    // markup. Only this module's own spans and ins/del elements may.
    const { html } = sourceRedline(BEFORE, BEFORE);
    expect(html).not.toContain("<section");
    expect(html).not.toContain("<p>");
    expect(html).toContain("&lt;section");
  });

  it("cannot be made to emit a tag from the source text", () => {
    const evil = '<section id="idAAA"><p>&lt;img src=x onerror=alert(1)&gt;</p></section>';
    const { html } = sourceRedline(evil, evil);
    expect(html).not.toContain("<img");
    // The `&` of the source's own entity is escaped too, so what it denotes is
    // visible as text rather than being re-interpreted.
    expect(html).toContain("&amp;lt;img");
  });

  it("colours element names and attributes separately", () => {
    const { html } = sourceRedline(BEFORE, BEFORE);
    expect(html).toContain('<span class="xml-tag">');
    expect(html).toContain('<span class="xml-attr">identifier</span>');
    expect(html).toContain('<span class="xml-val">');
  });

  it("shows a guid-only change as a change in the attribute value", () => {
    // The case this view is most often used for: an untouched section whose
    // @id regenerated. It must be visible, and it must be visibly confined to
    // the quoted value.
    const after = BEFORE.replace("idAAA", "idZZZ");
    const { html, inserted, deleted } = sourceRedline(BEFORE, after);

    expect(inserted).toBeGreaterThan(0);
    expect(deleted).toBeGreaterThan(0);
    expect(html).toContain("<ins>");
    expect(html).not.toContain("Five dollars.</del>");
  });

  it("sees a whitespace-only change, which the reading redline cannot", () => {
    const after = BEFORE.replace("</section>", "\n</section>");
    const { inserted } = sourceRedline(BEFORE, after);
    expect(inserted).toBe(1);
  });
});
