/**
 * The command palette's rows (ADR-0062).
 *
 * The arithmetic worth testing is which release point "the previous one" is:
 * the list is newest first, so it is the entry *after* the one being served,
 * and getting that backwards produces a redline against the future that still
 * renders.
 */

import { describe, expect, it } from "vitest";

import { matchKey, sectionCommands, siteCommands } from "../src/lib/palette";
import type { Release } from "../src/lib/types";

function release(label: string, seq: number): Release {
  return {
    label,
    currency_date: "2026-07-12",
    congress: 119,
    law_num: seq,
    excluded_laws: [],
    update_num: null,
    seq,
    is_partial: false,
    caveat: null,
    titles_affected: [],
    ingested_titles: [],
  };
}

/** Newest first, which is the order `fetchReleases` answers in. */
const RELEASES = [release("119-102not101", 3), release("119-99", 2), release("118-22", 1)];

describe("sectionCommands", () => {
  it("compares against the release point before the one being served", () => {
    const commands = sectionCommands("/us/usc/t16/s45f", RELEASES, "119-102not101");
    const compare = commands.find((command) => command.id === "compare-previous");

    expect(compare?.href).toBe("/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101");
    expect(compare?.label).toContain("119-99");
  });

  it("takes the previous release point from where the served one sits, not from the head", () => {
    const commands = sectionCommands("/us/usc/t16/s45f", RELEASES, "119-99");
    const compare = commands.find((command) => command.id === "compare-previous");

    expect(compare?.href).toBe("/app/diff/us/usc/t16/s45f?from=118-22&to=119-99");
  });

  it("offers no comparison at the oldest release point", () => {
    const commands = sectionCommands("/us/usc/t16/s45f", RELEASES, "118-22");

    expect(commands.map((command) => command.id)).toEqual(["versions"]);
  });

  it("offers no comparison when the served release point is not in the list", () => {
    const commands = sectionCommands("/us/usc/t16/s45f", RELEASES, "117-1");

    expect(commands.map((command) => command.id)).toEqual(["versions"]);
  });

  it("offers version history with no release list at all", () => {
    const commands = sectionCommands("/us/usc/t16/s45f", [], "119-99");

    expect(commands).toEqual([
      {
        id: "versions",
        label: "Version history",
        hint: "Every release point at which this section's text changed",
        href: "/app/versions/us/usc/t16/s45f",
      },
    ]);
  });

  // Gotcha 17: 5,697 of the corpus's sections carry U+2013 in their number, and
  // every href this site builds goes through `encodePath` because of it.
  it("percent-encodes an en dash in a section number", () => {
    const commands = sectionCommands("/us/usc/t16/s45a–1", RELEASES, "119-102not101");

    for (const command of commands) {
      expect(command.href).toContain("s45a%E2%80%931");
      expect(command.href).not.toContain("–");
    }
  });
});

describe("siteCommands", () => {
  it("names every href through url.ts, so /app is spelled once", () => {
    for (const command of siteCommands()) {
      if (command.href === null) continue;
      expect(command.href, command.id).toMatch(/^\/app(\/|$)/u);
    }
  });

  it("leaves the shortcut list without an href, because it is a dialog", () => {
    const shortcuts = siteCommands().find((command) => command.id === "shortcuts");

    expect(shortcuts?.href).toBeNull();
  });

  // `/app/settings` is linked from no rendered page while accounts are off:
  // `AuthNav` is its only linker and `SiteHeader` does not render it (ADR-0034).
  it("reaches the settings page", () => {
    expect(siteCommands().map((command) => command.href)).toContain("/app/settings");
  });

  it("gives every row a distinct id", () => {
    const ids = siteCommands().map((command) => command.id);

    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("matchKey", () => {
  it("matches the label and the id, lowercased", () => {
    const key = matchKey({ id: "compare-previous", label: "Compare with the previous release point (119-99)" });

    expect(key).toContain("compare with the previous");
    expect(key).toContain("compare-previous");
  });

  it("leaves the hint out, so a sentence does not make every row match", () => {
    const key = matchKey({ id: "guide", label: "User guide", hint: "Chapter by chapter" });

    expect(key).not.toContain("chapter");
  });
});
