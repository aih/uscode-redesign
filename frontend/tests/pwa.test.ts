/**
 * The installable reader's identity holds together (ADR-0079).
 *
 * Everything here fails silently in a browser. A manifest that does not parse,
 * a scope missing its trailing slash (`"/app"` also matches `/apple…`), a
 * `start_url` outside the scope, or an icon whose declared size is not the
 * file's — each just means the install prompt never appears, or the installed
 * app opens wrong, with nothing red anywhere. Same shape as `fonts.test.ts`
 * asserting the `@font-face` contract.
 *
 * The theme-color values are asserted against the token block in `site.scss`
 * because they are written out three times — the meta's default, the
 * bootstrap's dark correction, `ThemeToggle`'s toggle — and a token change
 * that missed one would leave an installed window's title bar a colour the
 * page no longer is.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const PUBLIC = resolve(HERE, "../public");
const MANIFEST = resolve(PUBLIC, "manifest.webmanifest");
const STYLES = resolve(HERE, "../src/styles/site.scss");
const BASE = resolve(HERE, "../src/layouts/Base.astro");
const TOGGLE = resolve(HERE, "../src/components/ThemeToggle.astro");

interface Icon {
  src: string;
  sizes: string;
  type: string;
  purpose: string;
}

const manifest = JSON.parse(readFileSync(MANIFEST, "utf8")) as {
  id: string;
  name: string;
  short_name: string;
  start_url: string;
  scope: string;
  display: string;
  theme_color: string;
  background_color: string;
  icons: Icon[];
  shortcuts: { name: string; url: string }[];
};
const scss = readFileSync(STYLES, "utf8");
const base = readFileSync(BASE, "utf8");
const toggle = readFileSync(TOGGLE, "utf8");

/** The `--page` token in each theme, read from the token block rather than
 * retyped: the light value is the sole declaration before the dark block, the
 * dark value the first one inside it. (A third declaration exists in the print
 * block, which no installed window's title bar ever shows.) */
function pageTokens(): { light: string; dark: string } {
  const darkAt = scss.indexOf(':root[data-theme="dark"]');
  expect(darkAt).toBeGreaterThan(0);
  const declarations = [...scss.matchAll(/--page:\s*(#[0-9a-fA-F]{3,8})\s*;/g)];
  const light = declarations.filter((m) => m.index! < darkAt);
  const dark = declarations.filter((m) => m.index! >= darkAt);
  expect(light).toHaveLength(1);
  expect(dark.length).toBeGreaterThanOrEqual(1);
  return { light: light[0][1], dark: dark[0][1] };
}

/** Pixel dimensions out of the PNG header: width and height are the two
 * big-endian words at offsets 16 and 20, after the signature and the IHDR
 * chunk's length and type. */
function pngSize(path: string): { width: number; height: number } {
  const bytes = readFileSync(path);
  expect(bytes.subarray(0, 8)).toEqual(
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  );
  expect(bytes.subarray(12, 16).toString("latin1")).toBe("IHDR");
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

describe("web app manifest", () => {
  it("declares the identity that keeps installs addressable", () => {
    // `id` is what lets the entry page move without orphaning installs.
    expect(manifest.id).toBe("/app/");
    // `"/app"` would also match `/apple…`; the trailing slash is the scope.
    expect(manifest.scope).toBe("/app/");
    expect(manifest.scope.endsWith("/")).toBe(true);
    expect(manifest.start_url.startsWith(manifest.scope)).toBe(true);
    // `minimal-ui` falls back to `browser` on iOS; `standalone` is the mode.
    expect(manifest.display).toBe("standalone");
    expect(manifest.name).toBe("United States Code");
    expect(manifest.short_name.length).toBeLessThanOrEqual(12);
  });

  it("keeps every shortcut inside the scope", () => {
    expect(manifest.shortcuts.length).toBeGreaterThan(0);
    for (const shortcut of manifest.shortcuts) {
      expect(shortcut.url.startsWith(manifest.scope)).toBe(true);
    }
  });

  it("separates any from maskable, and covers 192 and 512 in both", () => {
    // One icon marked "any maskable" gets its `any` rendering cropped; the
    // two purposes are separate files by design.
    for (const icon of manifest.icons) {
      expect(["any", "maskable"]).toContain(icon.purpose);
    }
    for (const purpose of ["any", "maskable"]) {
      const sizes = manifest.icons.filter((i) => i.purpose === purpose).map((i) => i.sizes);
      expect(sizes).toContain("192x192");
      expect(sizes).toContain("512x512");
    }
  });

  it("ships every declared icon at its declared pixel size", () => {
    for (const icon of manifest.icons) {
      expect(icon.src.startsWith("/app/icons/")).toBe(true);
      expect(icon.type).toBe("image/png");
      const declared = Number(icon.sizes.split("x")[0]);
      const actual = pngSize(resolve(PUBLIC, icon.src.replace("/app/", "")));
      expect(actual, `${icon.src} is not the ${icon.sizes} it declares`).toEqual({
        width: declared,
        height: declared,
      });
    }
  });

  it("ships the apple-touch icon Base.astro links, at 180px", () => {
    expect(base).toContain('rel="apple-touch-icon" href="/app/icons/apple-touch-icon-180.png"');
    expect(pngSize(resolve(PUBLIC, "icons/apple-touch-icon-180.png"))).toEqual({
      width: 180,
      height: 180,
    });
  });

  it("links the manifest from every page's head", () => {
    expect(base).toContain('rel="manifest" href="/app/manifest.webmanifest"');
  });
});

describe("theme-color", () => {
  const tokens = pageTokens();

  it("colours the manifest with the light --page token", () => {
    // The manifest cannot follow a runtime theme; both members stay light.
    expect(manifest.theme_color).toBe(tokens.light);
    expect(manifest.background_color).toBe(tokens.light);
  });

  it("defaults the meta to light and corrects to dark pre-paint", () => {
    expect(base).toContain(`<meta name="theme-color" content="${tokens.light}" />`);
    expect(base).toContain(`themeMeta.setAttribute("content", "${tokens.dark}")`);
  });

  it("moves the meta with the toggle, using the same two values", () => {
    expect(toggle).toContain(`dark ? "${tokens.dark}" : "${tokens.light}"`);
  });

  it("pairs viewport-fit=cover with safe-area padding", () => {
    // The two land together: `cover` without the padding puts the topbar
    // under a notch in landscape standalone.
    expect(base).toContain("viewport-fit=cover");
    for (const selector of ["safe-area-inset-top", "safe-area-inset-bottom"]) {
      expect(scss).toContain(`env(${selector})`);
    }
  });
});
