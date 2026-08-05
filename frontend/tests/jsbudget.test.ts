/**
 * A per-route JavaScript byte budget (task B3, ADR-0046).
 *
 * The reader is server-rendered with a handful of small islands (ADR-0022), and
 * that is a claim nothing checked. This makes it checkable: every route gets a
 * ceiling in `docs/js-budgets.json`, and exceeding it fails `make test-web`.
 *
 * ## Why the bytes are counted from source rather than from a page
 *
 * There is no bundle to weigh. `astro build` emits **no client JavaScript at
 * all** for this site — `dist/client/_astro/` holds only CSS — because every
 * island is `<script is:inline>`, which Astro passes through into the HTML
 * untouched and never bundles. So the thing to measure is the inline script
 * bytes each route's component graph can ship, and those are in the `.astro`
 * files.
 *
 * Counting from source is also what lets this run in Vitest with no server and
 * no build, which is the requirement: a budget that needs a running stack is a
 * budget nobody runs. It is checked against a real page once — see
 * `docs/verification/js-bytes.json`'s `validated_against` note — so the static
 * number is known to match what a browser receives.
 *
 * ## What it deliberately does not count
 *
 * A component behind a false condition still contributes its script here. The
 * count is therefore what a route *can* ship, not always what it did — an
 * over-count, which is the safe direction for a ceiling.
 *
 * `CopyColumn`'s `<script type="application/json" data-copy-targets>` is
 * excluded. Its size is the section's provision list rather than any code, so it
 * varies per URL and a static ceiling over it would be a ceiling on the statute.
 * It is real bytes to a reader and it is measured nowhere; that is recorded as a
 * candidate task rather than pretended away.
 */

import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "../src");
const PAGES_DIR = join(SRC, "pages");
const BUDGETS = resolve(HERE, "../../docs/js-budgets.json");
const ARTIFACT = resolve(HERE, "../../docs/verification/js-bytes.json");

/** `<script is:inline>…</script>`, the only form that ships bytes verbatim. */
const INLINE_SCRIPT = /<script\b[^>]*\bis:inline\b[^>]*>([\s\S]*?)<\/script>/g;

/** A component or layout import — the edges of the graph walked below. */
const COMPONENT_IMPORT = /^\s*import\s+\w+\s+from\s+["'](\.[^"']+\.astro)["'];?\s*$/gm;

interface RouteBytes {
  route: string;
  page: string;
  bytes: number;
  scripts: number;
  components: string[];
}

/** Every route the reader serves, by the same walk the guide ratchet uses. */
function readerPages(): { route: string; file: string }[] {
  const found: { route: string; file: string }[] = [];

  function walk(dir: string, prefix: string): void {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(path, `${prefix}/${entry.name}`);
        continue;
      }
      // `.md` guide chapters and `.ts` endpoints carry no islands of their own;
      // a chapter's bytes are its layout's, and that layout is counted through
      // `guide/index.astro`.
      if (!entry.name.endsWith(".astro")) continue;

      const name = basename(entry.name, ".astro");
      const route =
        name.startsWith("[") ? prefix : name === "index" ? (prefix === "/app" ? "/app/" : prefix) : `${prefix}/${name}`;
      found.push({ route, file: path });
    }
  }

  walk(PAGES_DIR, "/app");
  return found.sort((a, b) => a.route.localeCompare(b.route));
}

/** Every `.astro` file a page pulls in, transitively, including itself. */
function graph(entry: string): string[] {
  const seen = new Set<string>();
  const queue = [entry];
  while (queue.length) {
    const file = queue.pop()!;
    if (seen.has(file)) continue;
    seen.add(file);
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(COMPONENT_IMPORT)) {
      queue.push(resolve(dirname(file), match[1]));
    }
  }
  return [...seen].sort();
}

function inlineBytes(source: string): { bytes: number; scripts: number } {
  let bytes = 0;
  let scripts = 0;
  for (const match of source.matchAll(INLINE_SCRIPT)) {
    bytes += Buffer.byteLength(match[1], "utf8");
    scripts += 1;
  }
  return { bytes, scripts };
}

function measure(): RouteBytes[] {
  // Two page files can serve one route — `us/usc/[...identifier].astro` and
  // `us/usc/index.astro` are both `/app/us/usc`, the second being the `?id=`
  // guid lookup. A request reaches one of them, never both, so the route's
  // budget is the heavier page rather than their sum.
  const byRoute = new Map<string, RouteBytes>();

  for (const { route, file } of readerPages()) {
    let bytes = 0;
    let scripts = 0;
    const components: string[] = [];
    for (const path of graph(file)) {
      const counted = inlineBytes(readFileSync(path, "utf8"));
      if (counted.scripts > 0) components.push(basename(path));
      bytes += counted.bytes;
      scripts += counted.scripts;
    }
    const row = { route, page: file.slice(SRC.length + 1), bytes, scripts, components };
    const existing = byRoute.get(route);
    if (!existing || row.bytes > existing.bytes) byRoute.set(route, row);
  }

  return [...byRoute.values()].sort((a, b) => a.route.localeCompare(b.route));
}

const measured = measure();
const budgets: Record<string, number> = JSON.parse(readFileSync(BUDGETS, "utf8")).budgets;

describe("per-route JavaScript byte budget", () => {
  it("every route has a budget, and every budget has a route", () => {
    const routes = measured.map((row) => row.route).sort();
    expect(Object.keys(budgets).sort()).toEqual(routes);
  });

  it.each(measured)("$route ships at most its budget", ({ route, bytes, components }) => {
    const budget = budgets[route];
    expect(
      bytes,
      `${route} ships ${bytes} inline script bytes against a budget of ${budget}.\n` +
        `Islands on this route: ${components.join(", ") || "none"}.\n` +
        `If the growth is intended, raise the ceiling in docs/js-budgets.json in the same commit ` +
        `and say why in the build log — that edit is the record that it was a decision.`,
    ).toBeLessThanOrEqual(budget);
  });

  it("writes the measured artifact", () => {
    const total = measured.reduce((sum, row) => sum + row.bytes, 0);
    writeFileSync(
      ARTIFACT,
      `${JSON.stringify(
        {
          generated_by: "frontend/tests/jsbudget.test.ts, via `make test-web`",
          counts:
            "Bytes inside <script is:inline> across each route's transitive .astro import graph. " +
            "A component behind a false condition is still counted, so this is what a route can " +
            "ship, not always what it did.",
          excluded:
            "CopyColumn's <script type=\"application/json\" data-copy-targets> — its size is the " +
            "section's provision list rather than code, so it varies per URL and is measured nowhere.",
          client_bundles:
            "None. `astro build` emits no client JavaScript for this site; dist/client/_astro holds " +
            "only CSS, because every island is is:inline and Astro never bundles those.",
          validated_against:
            "The rendered page — see docs/adr/0046 for the comparison against a live /app/us/usc/… response.",
          total_bytes: total,
          routes: measured,
        },
        null,
        2,
      )}\n`,
    );
    expect(total).toBeGreaterThan(0);
  });
});
