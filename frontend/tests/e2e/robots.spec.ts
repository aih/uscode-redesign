/**
 * robots.txt, through the real proxy.
 *
 * This lives in the browser suite for the same reason the suite exists at all:
 * the answer is a property of the deployed *shape* rather than of either
 * surface. `/robots.txt` is not a reader route and not an API route — it is
 * served by the Caddy that owns the host (deploy/Caddyfile), and neither a
 * Vitest unit nor a FastAPI TestClient can see it. Running against `make
 * dev-all` is what makes this the same path production takes.
 *
 * It is here because the file's absence was expensive. For its first days the
 * site answered 404 to every request for it, and the crawlers drew their own
 * conclusions: one hour of proxy log on 2026-08-03 held 43,068 requests, 99.9%
 * of them ClaudeBot and GPTBot, 85% carrying `?release=` — the version
 * dimension, some 25 million reader pages of it. A 404 here is not a missing
 * file, it is an open invitation, and nothing else in the suite would notice
 * if the route were dropped.
 */
import { expect, test } from "@playwright/test";

test("robots.txt is served, as text, and disallows everything to every other agent", async ({ request }) => {
  const response = await request.get("/robots.txt");

  expect(response.status()).toBe(200);
  // Served as a file rather than as a page: a crawler that gets text/html here
  // is entitled to ignore the whole thing.
  expect(response.headers()["content-type"]).toContain("text/plain");

  // The directives must be on their own lines. A heredoc that lost its
  // newlines would parse as one meaningless line, so assert the shape rather
  // than the substrings. Since ADR-0098 the first group lets Googlebot and
  // Bingbot fetch the landing pages; the group for `*` is unchanged.
  const groups = (await response.text())
    .split(/\n\s*\n/)
    .map((group) =>
      group
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
    )
    .filter((group) => group.length);
  expect(groups[0].slice(0, 2)).toEqual(["User-agent: Googlebot", "User-agent: Bingbot"]);
  expect(groups[0].at(-1)).toBe("Disallow: /");
  expect(groups[1]).toEqual(["User-agent: *", "Disallow: /"]);
  expect(groups[2]).toEqual([expect.stringMatching(/^Sitemap: https:\/\/.+\/sitemap\.xml$/)]);
});

test("the sitemap is served as XML and lists the front page", async ({ request }) => {
  const response = await request.get("/sitemap.xml");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("application/xml");
  const body = await response.text();
  expect(body.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true);
  expect(body).toMatch(/<loc>https:\/\/[^<]+\/app\/<\/loc>/);
});

test("the reader still answers while robots.txt is disallowing it", async ({ request }) => {
  // `Disallow` is advisory and addressed to crawlers; it must not be mistaken
  // for a routing rule. If a future edit to that Caddy block swallows the
  // catch-all handler, this is what says so.
  const response = await request.get("/app/us/usc/t16/s45f");
  expect(response.status()).toBe(200);
});
