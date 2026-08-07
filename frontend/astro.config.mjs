// @ts-check
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";

import node from "@astrojs/node";
import { defineConfig } from "astro/config";

import { remarkScenario } from "./scripts/remark-scenario.mjs";

const commitHash = (() => {
  try {
    return execSync("git rev-parse HEAD").toString().trim();
  } catch {
    return "unknown";
  }
})();

/**
 * The reader, at /app (ADR-0010, ADR-0011).
 *
 * `base: "/app"` is not cosmetic: it is the contract with the proxy in front of
 * this process. Caddy sends /app/* here and everything else to FastAPI, so every
 * route this app declares lives under that prefix and every asset it emits is
 * addressed from it.
 *
 * `output: "server"` because a reader of versioned law cannot be prerendered:
 * the page for one identifier differs at every release point, and there are 382
 * of them.
 *
 * The dev proxy exists so `npm run dev` is a complete site rather than half of
 * one — the reader on :4321 and the API it reads from on :8000, same origin as
 * far as the browser is concerned, exactly as Caddy will arrange it in compose.
 */
const API = process.env.API_BASE_URL ?? "http://localhost:8000";

export default defineConfig({
  base: "/app",
  trailingSlash: "ignore",
  output: "server",
  adapter: node({ mode: "standalone" }),
  server: { port: 4321, host: true },
  devToolbar: { enabled: false },
  /* The user guide's chapters are markdown pages (ADR-0038). The only thing
   * Astro's own markdown handling does not already do for them is render a
   * `scenario` fence as something a reader wants to look at, which is this
   * plugin's whole job. */
  markdown: {
    remarkPlugins: [remarkScenario],
  },
  vite: {
    define: {
      __COMMIT_HASH__: JSON.stringify(commitHash),
    },
    css: {
      preprocessorOptions: {
        scss: {
          loadPaths: [
            fileURLToPath(
              new URL("./node_modules/@uswds/uswds/packages", import.meta.url),
            ),
          ],
          quietDeps: true,
          silenceDeprecations: ["import", "global-builtin", "mixed-decls"],
        },
      },
    },
    server: {
      // Deliberately NOT proxying `/us/usc` here, which looks like an omission
      // and is not: the dev server strips `base` before the proxy sees a URL, so
      // `/app/us/usc/t16/s45f` arrives as `/us/usc/t16/s45f` and every reader
      // page would be proxied to the API — serving JSON where a page belongs.
      // The bare citation URL is FastAPI's route anyway; in dev it answers on
      // :8000, and under Caddy (`make dev-all`) both share one origin.
      proxy: Object.fromEntries(
        // `/favicon.svg` and `/static` are the API's too (ADR-0032): the docs
        // bundles and the tab mark live there, and `Base.astro` links the
        // favicon root-absolute so one file serves the whole site. Without
        // them here, `npm run dev` alone shows a blank tab.
        ["/api/v1", "/health", "/docs", "/redoc", "/openapi.json", "/static", "/favicon"].map((path) => [
          `^${path}`,
          { 
            target: API, 
            changeOrigin: true,
            bypass(req) {
              // The dev server strips `base` (`/app`) before the proxy sees a URL.
              // A request to `/app/docs` arrives as `/docs` and would be proxied
              // to the API's Swagger UI instead of rendering `pages/docs.astro`.
              // Bypassing any request that originally started with `/app/` ensures
              // Astro handles all reader pages.
              if (req.originalUrl && req.originalUrl.startsWith("/app/")) {
                return req.url;
              }
            }
          },
        ]),
      ),
    },
  },
});
