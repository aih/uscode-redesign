/**
 * The reader serves its own type, and only its own type (ADR-0052).
 *
 * Two claims are checked here because both fail silently. A `@font-face` whose
 * file is not in `public/` degrades to the fallback stack, which looks like a
 * design choice rather than a 404; and a stylesheet that reaches a font CDN
 * still renders, so nothing goes red — it just means the first paint of
 * statutory text now waits on somebody else's server, and `font-src 'self'` in
 * the CSP (ADR-0030) stops being true.
 *
 * The manifest is the third leg: `docs/verification/fonts.json` is what the ADR
 * quotes byte sizes from, so a file rebuilt without regenerating it would leave
 * the documented weight of the critical path wrong.
 */
import { readFileSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const STYLES = resolve(HERE, "../src/styles/site.scss");
const BASE = resolve(HERE, "../src/layouts/Base.astro");
const PUBLIC = resolve(HERE, "../public");
const MANIFEST = resolve(HERE, "../../docs/verification/fonts.json");

const scss = readFileSync(STYLES, "utf8");
const base = readFileSync(BASE, "utf8");
const manifest = JSON.parse(readFileSync(MANIFEST, "utf8")) as {
  faces: { file: string; bytes: number; sha256: string }[];
  summary: { files: number; bytes: number; preloadedBytes: number };
};

/** Every `src: url(...)` in a `@font-face` block. */
function declaredSources(): string[] {
  return [...scss.matchAll(/@font-face\s*\{[^}]*?url\("([^"]+)"\)/g)].map((m) => m[1]);
}

describe("self-hosted webfonts", () => {
  it("declares one @font-face per file the build produced", () => {
    const sources = declaredSources();
    expect(sources).toHaveLength(manifest.faces.length);
    expect(new Set(sources.map((s) => s.split("/").pop()))).toEqual(
      new Set(manifest.faces.map((f) => f.file)),
    );
  });

  it("serves every declared font from this origin", () => {
    for (const source of declaredSources()) {
      expect(source, `${source} is not a path under /app`).toMatch(/^\/app\/fonts\//);
    }
  });

  it("reaches no other host for type, from CSS or from markup", () => {
    // `@import` of a foreign stylesheet is the usual way a font CDN gets in —
    // it is one line, and the fonts it pulls are invisible in this file.
    for (const text of [scss, base]) {
      expect(text).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com|use\.typekit|cdn\.jsdelivr/);
      expect(text).not.toMatch(/@import\s+url\(["']?https?:/);
    }
  });

  it("ships each declared file at the size the manifest recorded", () => {
    for (const face of manifest.faces) {
      const path = resolve(PUBLIC, "fonts", face.file);
      expect(statSync(path).size, `${face.file} differs from docs/verification/fonts.json`).toBe(
        face.bytes,
      );
    }
  });

  it("asks for both roman faces before the stylesheet names them", () => {
    // A webfont is discovered only once the CSS that declares it has parsed.
    // Without these the first paint of every page is the fallback face.
    for (const file of ["archivo-latin-var.woff2", "spectral-latin-400.woff2"]) {
      expect(base).toContain(`rel="preload"\n      href="/app/fonts/${file}"`);
    }
    // Cross-origin mode is not optional for a font, even same-origin: a preload
    // without it is a second, separate fetch rather than a warmed cache entry.
    expect(base.match(/rel="preload"/g)).toHaveLength(2);
    expect(base.match(/as="font"[\s\S]{0,80}crossorigin/g)).toHaveLength(2);
  });

  it("declares `swap` on every face", () => {
    const blocks = [...scss.matchAll(/@font-face\s*\{([^}]*)\}/g)].map((m) => m[1]);
    expect(blocks).toHaveLength(manifest.faces.length);
    for (const block of blocks) expect(block).toContain("font-display: swap");
  });
});
