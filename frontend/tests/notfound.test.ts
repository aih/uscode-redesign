/**
 * What the reader's 404 offers (ADR-0099): `lib/notfound.ts`.
 *
 * The first test is a ratchet: `STATIC_PAGES` is written out by hand, so a new
 * page without a parameter fails here until it is listed — otherwise its
 * misspellings would never be suggested and its letter-case variants never
 * redirected.
 */
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  STATIC_PAGES,
  SITE_SECTIONS,
  UNLISTED_ROUTES,
  caseRedirect,
  citationPath,
  lookupHref,
  lookupQuery,
  similarity,
  suggestions,
} from "../src/lib/notfound";

const PAGES_DIR = fileURLToPath(new URL("../src/pages", import.meta.url));

/** Every route under `src/pages` that takes no parameter. */
function parameterlessRoutes(): string[] {
  const routes: string[] = [];
  function walk(dir: string, prefix: string): void {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!entry.name.startsWith("[")) walk(join(dir, entry.name), `${prefix}/${entry.name}`);
        continue;
      }
      const match = /^(.*)\.(astro|md|ts)$/u.exec(entry.name);
      if (!match || match[1].startsWith("[")) continue;
      const name = match[1];
      routes.push(name === "index" ? (prefix === "/app" ? "/app/" : prefix) : `${prefix}/${name}`);
    }
  }
  walk(PAGES_DIR, "/app");
  return routes.sort();
}

describe("the pages the 404 knows", () => {
  it("are every parameterless route under src/pages", () => {
    const listed = [...STATIC_PAGES, ...UNLISTED_ROUTES].sort();
    expect(listed).toEqual(parameterlessRoutes());
  });

  it("list only real pages among the sections of the site", () => {
    for (const { href } of SITE_SECTIONS) expect(STATIC_PAGES).toContain(href);
  });
});

describe("caseRedirect", () => {
  it("sends a path that differs only in letter case to the page", () => {
    expect(caseRedirect("/app/About")).toBe("/app/about");
    expect(caseRedirect("/app/GUIDE/02-Reading")).toBe("/app/guide/02-reading");
  });

  it("drops a trailing slash", () => {
    expect(caseRedirect("/app/releases/")).toBe("/app/releases");
    expect(caseRedirect("/app/US/USC/")).toBe("/app/us/usc");
  });

  it("does not redirect a page to itself or a path that is not a page", () => {
    expect(caseRedirect("/app/about")).toBeNull();
    expect(caseRedirect("/app/")).toBeNull();
    expect(caseRedirect("/app/abuot")).toBeNull();
  });
});

describe("suggestions", () => {
  it("offers the page a misspelling is closest to", () => {
    expect(suggestions("/app/abuot")).toEqual(["/app/about"]);
    expect(suggestions("/app/release")).toContain("/app/releases");
    expect(suggestions("/app/classifications")).toContain("/app/classification");
  });

  it("offers nothing for a path like no page", () => {
    expect(suggestions("/app/wp-admin/setup-config.php")).toEqual([]);
    expect(suggestions("/app/")).toEqual([]);
  });

  it("reads a path with a title segment as a citation, first", () => {
    expect(citationPath("/app/t16/s45f")).toBe("/app/us/usc/t16/s45f");
    expect(citationPath("/app/usc/T5a/s3")).toBe("/app/us/usc/t5a/s3");
    expect(citationPath("/app/us/t16")).toBe("/app/us/usc/t16");
    expect(citationPath("/app/about")).toBeNull();
    expect(suggestions("/app/usc/t16/s45f/c/5")[0]).toBe("/app/us/usc/t16/s45f/c/5");
  });

  it("returns at most three", () => {
    expect(suggestions("/app/guide/0").length).toBeLessThanOrEqual(3);
  });
});

describe("similarity", () => {
  it("is 1 for equal strings and 0.8 for one transposition in five letters", () => {
    expect(similarity("about", "about")).toBe(1);
    expect(similarity("abuot", "about")).toBeCloseTo(0.8);
  });
});

describe("lookupQuery", () => {
  it("turns slashes, underscores and plus signs into spaces", () => {
    expect(lookupQuery("/app/16_usc/45f")).toBe("16 usc 45f");
    expect(lookupQuery("/app/freedom+of+information")).toBe("freedom of information");
  });

  it("decodes the path", () => {
    expect(lookupQuery("/app/45a%E2%80%931")).toBe("45a–1");
  });

  it("gives nothing for a path without letters or digits, or one too long to be typed", () => {
    expect(lookupQuery("/app/")).toBeNull();
    expect(lookupQuery("/app/---")).toBeNull();
    expect(lookupQuery(`/app/${"a".repeat(100)}`)).toBeNull();
  });

  it("links to the search box's own target", () => {
    expect(lookupHref("/app/16usc45f")).toBe("/app/goto?q=16usc45f");
  });
});
