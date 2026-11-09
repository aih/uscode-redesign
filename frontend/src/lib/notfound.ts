/**
 * What the reader's 404 offers for an address it has no page for (ADR-0099).
 *
 * `pages/404.astro` renders for any `/app/…` path no route matches. A path that
 * differs from one of the pages below only in letter case or a trailing slash is
 * redirected there (`caseRedirect`); any other near miss is offered as a link
 * (`suggestions`), along with the path read as a citation and its words as a
 * query for the one search box (`lookupQuery`).
 *
 * `STATIC_PAGES` is every route under `src/pages` that takes no parameter;
 * `tests/notfound.test.ts` walks that directory and fails when the two differ.
 */
import { APP, gotoHref } from "./url";

/** Every reader page without a parameter, as its path under `/app`. */
export const STATIC_PAGES: readonly string[] = [
  "/app/",
  "/app/about",
  "/app/classification",
  "/app/classification/ecct",
  "/app/data/version-changes",
  "/app/demo",
  "/app/design",
  "/app/docs",
  "/app/goto",
  "/app/guide",
  "/app/guide/01-what-this-site-is",
  "/app/guide/02-reading",
  "/app/guide/03-reading-at-a-point-in-time",
  "/app/guide/04-version-history-and-redlines",
  "/app/guide/05-search-and-citations",
  "/app/guide/06-working-with-the-text",
  "/app/guide/07-accounts",
  "/app/guide/08-api",
  "/app/guide/09-checking-this-site",
  "/app/guide/10-classification-tables",
  "/app/login",
  "/app/offline",
  "/app/provisions",
  "/app/releases",
  "/app/search",
  "/app/search/syntax",
  "/app/settings",
  "/app/signup",
  "/app/us/usc",
];

/** Routes under `src/pages` that are not pages a reader is sent to. */
export const UNLISTED_ROUTES: readonly string[] = ["/app/404", "/app/429", "/app/healthz"];

/** The sections of the site, as the 404 lists them. */
export const SITE_SECTIONS: readonly { href: string; label: string }[] = [
  { href: `${APP}/`, label: "Home" },
  { href: `${APP}/us/usc`, label: "Titles of the U.S. Code" },
  { href: `${APP}/releases`, label: "Release points" },
  { href: `${APP}/classification`, label: "Classification tables" },
  { href: `${APP}/data/version-changes`, label: "Version-change data" },
  { href: `${APP}/search/syntax`, label: "Search syntax" },
  { href: `${APP}/provisions`, label: "My Provisions" },
  { href: `${APP}/guide`, label: "User guide" },
  { href: `${APP}/docs`, label: "API docs" },
  { href: `${APP}/about`, label: "About this site" },
];

/** How close a near miss has to be to be offered: difflib's default cutoff. */
export const CUTOFF = 0.8;

/** Lower case, no trailing slash, `/app/` itself kept. */
function norm(path: string): string {
  const low = path.toLowerCase().replace(/\/+$/u, "");
  return low === APP ? `${APP}/` : low;
}

function decode(path: string): string {
  try {
    return decodeURIComponent(path);
  } catch {
    return path;
  }
}

/** The page this path names apart from letter case or a trailing slash, when
 *  there is one and it is not the path itself. */
export function caseRedirect(path: string): string | null {
  const wanted = norm(path);
  const page = STATIC_PAGES.find((p) => norm(p) === wanted);
  return page && page !== path ? page : null;
}

/** Levenshtein distance between two strings. */
function distance(a: string, b: string): number {
  let previous = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    for (let j = 1; j <= b.length; j++) {
      current[j] = Math.min(
        previous[j] + 1,
        current[j - 1] + 1,
        previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    previous = current;
  }
  return previous[b.length];
}

/** 1 for equal strings, 0 for nothing in common; the share of the two lengths
 *  that is not an edit. */
export function similarity(a: string, b: string): number {
  const total = a.length + b.length;
  return total === 0 ? 1 : (total - distance(a, b)) / total;
}

/** The part of a path after `/app/`, lower case, without the trailing slash. */
function tail(path: string): string {
  return norm(decode(path)).replace(/^\/app\/?/u, "");
}

/**
 * The path read as a US Code identifier, when a segment of it is a title
 * (`t16`, `t5a`): `/app/usc/t16/s45f` and `/app/t16/s45f` → `/app/us/usc/t16/s45f`.
 */
export function citationPath(path: string): string | null {
  const segments = decode(path).replace(/^\/app\/?/u, "").split("/").filter(Boolean);
  const at = segments.findIndex((s) => /^t\d+a?$/iu.test(s));
  if (at < 0) return null;
  const rest = segments.slice(at);
  rest[0] = rest[0].toLowerCase();
  return `${APP}/us/usc/${rest.join("/")}`;
}

/** Up to three paths close to `path`: the path as a citation, then the pages
 *  whose spelling is nearest. Never `path` itself. */
export function suggestions(path: string, limit = 3): string[] {
  const wanted = tail(path);
  const near = STATIC_PAGES.map((page) => ({ page, score: similarity(wanted, tail(page)) }))
    .filter(({ score }) => wanted.length > 0 && score >= CUTOFF)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(({ page }) => page);
  const cited = citationPath(path);
  const out = cited ? [cited, ...near] : near;
  return out.filter((p, i) => out.indexOf(p) === i && p !== path).slice(0, limit);
}

/** The label `SITE_SECTIONS` gives a page, when it lists it. */
export function sectionLabel(href: string): string | null {
  return SITE_SECTIONS.find((s) => norm(s.href) === norm(href))?.label ?? null;
}

/**
 * The words of the path, as a query for the search box: `/app/16_usc/45f` →
 * `16 usc 45f`. Slashes, underscores and plus signs become spaces. Null when the path has no letters or digits, or is
 * longer than a query anyone typed.
 */
export function lookupQuery(path: string): string | null {
  const words = decode(path)
    .replace(/^\/app\/?/u, "")
    .replace(/[/_+]+/gu, " ")
    .replace(/\s+/gu, " ")
    .trim();
  if (!/[\p{L}\p{N}]/u.test(words) || words.length > 80) return null;
  return words;
}

/** Where the lookup link goes: the search box's own target, which reads a
 *  citation as a citation and anything else as words. */
export function lookupHref(path: string): string | null {
  const query = lookupQuery(path);
  return query ? gotoHref(query) : null;
}
