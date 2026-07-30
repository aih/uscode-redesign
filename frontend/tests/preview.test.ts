import { describe, expect, it } from "vitest";

import { PREVIEW_CHARS, truncateFragment } from "../src/lib/preview";

describe("truncateFragment", () => {
  it("leaves short fragments alone", () => {
    const html = "<p>Short enough.</p>";
    expect(truncateFragment(html)).toEqual({ html, truncated: false });
  });

  it("never cuts inside a tag", () => {
    // The failure this exists to prevent: a naive slice lands in the middle of
    // `<a href="/app/us/usc/…` and the browser swallows the rest of the card as
    // an attribute value.
    const html =
      `<p>${"a".repeat(60)}</p>` +
      `<p>Then <a href="/app/us/usc/t16/s45f" data-cite="/us/usc/t16/s45f">§ 45f</a>.</p>`;
    const cut = truncateFragment(html, 70);

    expect(cut.truncated).toBe(true);
    expect(cut.html).toBe(`<p>${"a".repeat(60)}</p>`);
    // Every `<` that opened a tag also closed one.
    expect(cut.html.match(/</gu)?.length).toBe(cut.html.match(/>/gu)?.length);
  });

  it("keeps whole top-level elements, overshooting rather than splitting", () => {
    const html = `<p>${"x".repeat(500)}</p><p>second</p>`;
    const cut = truncateFragment(html, 100);

    // One enormous opening paragraph is kept entire: correct markup beats an
    // exact byte count, and the card scrolls.
    expect(cut.html).toBe(`<p>${"x".repeat(500)}</p>`);
    expect(cut.truncated).toBe(true);
  });

  it("treats a nested element as one chunk", () => {
    const html = `<div class="uslm-subsection"><p>${"y".repeat(40)}</p></div><p>after</p>`;
    const cut = truncateFragment(html, 50);

    expect(cut.html).toBe(`<div class="uslm-subsection"><p>${"y".repeat(40)}</p></div>`);
    expect(cut.html).toContain("</div>");
  });

  it("reports truncated=false when everything fit", () => {
    const html = "<p>one</p><p>two</p>";
    expect(truncateFragment(html, 1000).truncated).toBe(false);
  });

  it("returns markup it cannot chunk unchanged rather than half of it", () => {
    // Safety valve: returning the input whole is safe, returning half is not.
    const html = "<".repeat(3000);
    const cut = truncateFragment(html, 100);

    expect(cut.html).toBe(html);
    expect(cut.truncated).toBe(false);
  });

  it("defaults to the shared budget", () => {
    const html = `<p>${"z".repeat(PREVIEW_CHARS * 2)}</p><p>tail</p>`;
    expect(truncateFragment(html).truncated).toBe(true);
    expect(truncateFragment(html).html).not.toContain("tail");
  });
});
