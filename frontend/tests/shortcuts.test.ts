/**
 * The keyboard shortcut list, checked as data.
 *
 * `KeyboardNav`'s island is `is:inline` and imports nothing, so what it binds is
 * whatever `keyMap()` serialised into the page. These tests hold the two ends
 * together: that the map is derivable at all (a key claimed twice throws), and
 * that every action the printed list advertises is one the island has an arm
 * for. The second is the failure this file exists for — a row added to the
 * dialog and forgotten in the switch is a shortcut the guide documents and the
 * page does not have.
 */
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { SHORTCUT_GROUPS, keyMap } from "../src/lib/shortcuts";

const ISLAND = readFileSync(new URL("../src/components/KeyboardNav.astro", import.meta.url), "utf8");

/** Actions the island answers without a `case` of its own: `previous-section`,
 *  `next-section` and `up-level` are hrefs looked up in `targets`, and `close`
 *  belongs to the `<dialog>` and the hover card. */
const HANDLED_ELSEWHERE = new Set([
  "previous-section",
  "next-section",
  "up-level",
  "close",
]);

describe("the shortcut list", () => {
  it("binds every key to exactly one action", () => {
    expect(() => keyMap()).not.toThrow();
  });

  it("maps the display key to the KeyboardEvent.key the island switches on", () => {
    const map = keyMap();
    expect(map.ArrowLeft).toBe("previous-section");
    expect(map["?"]).toBe("help");
    expect(map.Escape).toBe("close");
  });

  it("gives every printed action something in the island that runs it", () => {
    for (const group of SHORTCUT_GROUPS) {
      for (const item of group.items) {
        if (HANDLED_ELSEWHERE.has(item.action)) continue;
        expect(ISLAND, `no case for "${item.action}"`).toContain(`case "${item.action}":`);
      }
    }
  });

  it("prints a key for every action and a sentence for every key", () => {
    for (const group of SHORTCUT_GROUPS) {
      for (const item of group.items) {
        expect(item.keys.length).toBeGreaterThan(0);
        expect(item.what.trim()).not.toBe("");
        // A `mod` shortcut is one binding printed twice — `⌘K` and `Ctrl K`
        // are the same key held with whichever modifier this reader's
        // keyboard has, and the page cannot know which, being one cached
        // document served to everyone (ADR-0018). Every other row prints one
        // spelling per code.
        if (item.mod) expect(item.codes.length).toBe(1);
        else expect(item.codes.length).toBe(item.keys.length);
      }
    }
  });

  it("puts a held modifier in the binding, so ⌘K is not the plain k next to it", () => {
    const map = keyMap();
    expect(map["Mod+k"]).toBe("palette");
    expect(map.k).toBe("next-section");
  });

  it("claims no key the island refuses to act on", () => {
    // Anything needing Shift other than `?` is dropped before the lookup, and
    // a single letter typed into a form control never reaches it. `?` is the
    // one exception the handler names, so it must stay the only shifted key.
    const shifted = Object.keys(keyMap()).filter((key) => /^[A-Z?~!@#$%^&*()_+{}|:"<>]$/u.test(key));
    expect(shifted).toEqual(["?"]);
  });
});
