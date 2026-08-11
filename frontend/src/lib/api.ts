/**
 * The only place this app calls `/api/v1` (ADR-0011: frontend consumes the API
 * over HTTP and nothing else). Server-side `fetch` in Node needs an absolute
 * URL, so every call goes through `BASE` — `API_BASE_URL` in `docker compose`
 * (Caddy in front, ADR-0015), `localhost:8000` for `npm run dev`'s own proxy.
 */

import { API, ancestorIdentifiers } from "./url";
import type {
  Citation,
  ClassificationEntry,
  ClassificationPage,
  ClassificationSuggestion,
  ClassificationTables,
  Diff,
  EcctEntry,
  Entry,
  Labels,
  Neighbors,
  OpenApiSchema,
  Release,
  SearchResponse,
  Section,
  Status,
  Title,
  Toc,
  User,
  Versions,
  Watchlist,
} from "./types";
import { isToc } from "./types";

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000";

/** Mirrors `ErrorOut` — a status and a detail a page can put in front of a
 * reader, the way `ErrorPage.astro` does. */
export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

export interface ReleaseParams {
  release?: string | null;
  date?: string | null;
}

/** `?release=`/`?date=` off the page's own URL — read once, then carried on
 * every link the page renders (BUILDLOG 007: links stay pasteable). */
export function releaseParams(url: URL): ReleaseParams {
  return {
    release: url.searchParams.get("release"),
    date: url.searchParams.get("date"),
  };
}

type QueryValue = string | number | null | undefined | string[];

function qs(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value == null || value === "") continue;
    if (Array.isArray(value)) {
      for (const one of value) search.append(key, one);
    } else {
      search.append(key, String(value));
    }
  }
  const built = search.toString();
  return built ? `?${built}` : "";
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { accept: "application/json" },
  });
  if (!response.ok) {
    const body: { detail?: string } = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }
  return (await response.json()) as T;
}

/** Resolve a US Code identifier at a release point: a section (with its
 * provision anchored) or a table-of-contents node — the identifier decides. */
export async function fetchIdentifier(
  identifier: string,
  params: ReleaseParams = {},
): Promise<Section | Toc> {
  return getJson<Section | Toc>(`${API}${identifier}${qs({ ...params })}`);
}

export async function fetchToc(identifier: string, release?: string | null): Promise<Toc> {
  const body = await fetchIdentifier(identifier, { release });
  if (!isToc(body)) {
    throw new Error(`${identifier} is a section, not a table of contents`);
  }
  return body;
}

export async function fetchNeighbors(
  identifier: string,
  release?: string | null,
): Promise<Neighbors> {
  return getJson<Neighbors>(`/api/v1/sections${identifier}/neighbors${qs({ release })}`);
}

/** The API's own bound on one `/labels` call (`api/routes.py`, ADR-0029). The
 * list fans into one `IN (...)`, so an unbounded request is an unbounded
 * query; asking for 101 is a 422, not a truncated answer. */
export const LABELS_PER_REQUEST = 100;

/** How many citations one page will label at all — twelve requests' worth.
 *
 * Measured rather than guessed: across all 489,738 stored section versions the
 * densest carries 1,011 `<ref>`s into the Code, and exactly one exceeds 1,000.
 * This clears that, and still bounds a fan-out whose input is a *document* —
 * which is the thing ADR-0029 exists to stop. Past it the tail of a section's
 * citations goes unlabelled: they are still links, and still followable.
 */
export const LABELS_MAX = LABELS_PER_REQUEST * 12;

/** What a page's citations *say*, in as few requests as the bound allows.
 *
 * One request per hundred, not one per citation (`api/routes.py`'s `labels`
 * docstring: forty citations, one query, not forty) — but not one request for
 * all of them either, which is what this used to do. 3 U.S.C. § 301 carries
 * 242 distinct cross references, the API refused the list with a 422, and the
 * reader turned that into a 500 on a page whose text it already had. 4,221
 * stored versions are over the bound.
 */
export async function fetchLabels(
  identifiers: string[],
  release?: string | null,
): Promise<Labels> {
  if (identifiers.length === 0) return {};

  const wanted = identifiers.slice(0, LABELS_MAX);
  const batches: string[][] = [];
  for (let i = 0; i < wanted.length; i += LABELS_PER_REQUEST) {
    batches.push(wanted.slice(i, i + LABELS_PER_REQUEST));
  }

  const answers = await Promise.all(
    batches.map((batch) =>
      getJson<Record<string, Entry>>(`/api/v1/labels${qs({ identifier: batch, release })}`),
    ),
  );
  return Object.assign({}, ...answers) as Labels;
}

/** Release points this title is actually *ingested* at, not all 382 —
 * `?ingested_title=` is what keeps the picker from offering empty answers. */
export async function fetchReleases(titleNum?: string | null): Promise<Release[]> {
  return getJson<Release[]>(`/api/v1/releases${qs({ ingested_title: titleNum })}`);
}

export async function fetchTitles(): Promise<Title[]> {
  return getJson<Title[]>("/api/v1/titles");
}

/** How current this mirror is, and when it last asked uscode.house.gov.
 *
 * Never let this fail a page: a currency note is context around the law, not
 * the law, and a status endpoint that is briefly down is not a reason to stop
 * serving the text it describes. Callers get `null` and render nothing. */
export async function fetchStatus(): Promise<Status | null> {
  try {
    return await getJson<Status>("/api/v1/status");
  } catch {
    return null;
  }
}

/** `11 usc 523(a)(1)` → the identifier it names, and whether it is there.
 *
 * Throws `ApiError(422)` when the text is not a citation at all; returns a body
 * with `exists: false` when it is a citation naming something absent. The two
 * are different answers and `/app/goto` shows them differently. */
export async function lookupCitation(
  query: string,
  params: ReleaseParams = {},
): Promise<Citation> {
  return getJson<Citation>(`${API}/citation${qs({ q: query, ...params })}`);
}

/**
 * Keyword search (ADR-0028).
 *
 * The default searches the text in force; `release`/`date` swap that for the
 * newest text at or before the release asked for, and the response names the
 * release it actually searched. Going through here rather than a bare `fetch`
 * is the point of this module: `search.astro` used to call the API directly
 * with its own `API_BASE_URL` default of `http://api:8001`, which is the
 * compose service name — so under `npm run dev` search alone silently failed
 * while every other page worked.
 */
export async function fetchSearch(
  query: string,
  opts: { offset?: number; limit?: number; sort?: string | null } & ReleaseParams = {},
): Promise<SearchResponse> {
  const { offset, limit, sort, ...release } = opts;
  return getJson<SearchResponse>(
    `${API}/search${qs({ q: query, offset, limit, sort, ...release })}`,
  );
}

/* ------------------------------------------------- classification tables
 *
 * ADR-0067's routes, under `/api/v1/classifications/…`. Everything here goes
 * through `getJson`, so a 404 from the API arrives as an `ApiError` a page can
 * hand to `ErrorPage` — which is the difference the spec asks these pages to
 * keep: "no table covers Public Law 119-72" is a 404, and "a table covers it
 * and it classified nothing" is a 200 with an empty `items`.
 */

/** The registry of source documents, and when this site last checked them. */
export async function fetchClassificationTables(): Promise<ClassificationTables> {
  return getJson<ClassificationTables>(`${API}/classifications/tables`);
}

/** How many rows one session page asks for. Well under the API's own bound of
 *  500: the largest session file is ~9,700 rows and the 104th's is 11,737, so
 *  an unbounded fetch here would be a page nobody can read and a query nobody
 *  budgeted for. */
export const CLASSIFICATION_PAGE_SIZE = 50;

export interface ClassificationEntryQuery {
  pl?: string | null;
  pl_section?: string | null;
  title?: string | null;
  section?: string | null;
  sort?: string | null;
  limit?: number;
  offset?: number;
}

/** One session's table, filtered, sorted and paged by the API. Nothing is
 *  sorted or sliced here: `?sort=code` orders by title through
 *  `title_sort_key`, which is server-side by gotcha 16. */
export async function fetchClassificationEntries(
  congress: number,
  session: number,
  query: ClassificationEntryQuery = {},
): Promise<ClassificationPage<ClassificationEntry>> {
  return getJson<ClassificationPage<ClassificationEntry>>(
    `${API}/classifications/tables/${congress}/${session}/entries${qs({ ...query })}`,
  );
}

/** The whole Editorial Classification Change Table — 21 rows across two files. */
export async function fetchEcct(): Promise<ClassificationPage<EcctEntry>> {
  return getJson<ClassificationPage<EcctEntry>>(`${API}/classifications/ecct`);
}

/**
 * What a lookup query means, decided server-side.
 *
 * The PL shorthand and the citation half both parse in Python — `citeparse.py`
 * is the single source of truth for what a citation is (ADR-0023), and a
 * TypeScript copy of it would be a second parser disagreeing with the first.
 * So this is the no-script path's handler as well as the island's endpoint: the
 * page calls it when a query arrives in `?q=`, and the island calls the same
 * URL from the browser.
 *
 * Never throws. A lookup that fails is a box that found nothing, not a page
 * that will not render.
 */
export async function fetchClassificationSuggestions(
  query: string,
): Promise<ClassificationSuggestion[]> {
  if (!query.trim()) return [];
  try {
    const body = await getJson<
      ClassificationSuggestion[] | { suggestions: ClassificationSuggestion[] }
    >(`${API}/classifications/suggest${qs({ q: query })}`);
    return Array.isArray(body) ? body : (body.suggestions ?? []);
  } catch {
    return [];
  }
}

/** The OpenAPI schema FastAPI generates, for `/app/docs` to render.
 *
 * Not under `/api/v1` — `/openapi.json` is where FastAPI publishes it and
 * `main.py` does not move it, so this is the one path here that is not built
 * from `API`. Everything the docs page shows is derived from this: there is no
 * second, hand-written description of the API to drift out of date. */
export async function fetchOpenApi(): Promise<OpenApiSchema> {
  return getJson<OpenApiSchema>("/openapi.json");
}

/**
 * The nearest identifier above a failed one that does resolve, with the trail
 * to it — what a 404 offers instead of only "start from the top".
 *
 * Tries `ancestorIdentifiers()` nearest first and stops at the first hit, so a
 * mistyped subsection of a real section leads back to that section rather than
 * to the whole title. Every call is allowed to fail: this runs on a page that
 * is already an error, and a second error while explaining the first should
 * cost the reader nothing.
 *
 * Returns null when nothing above it resolves either — an identifier whose
 * title does not exist has no trail to offer, and inventing one would point at
 * another 404.
 */
export async function nearestAncestor(
  identifier: string,
  params: ReleaseParams = {},
  /** Try the identifier itself before its ancestors. For a status that does not
   *  mean "this does not exist" — a shed 429 refused the *work*, and the
   *  provision it was asked about is very likely still there. */
  includeSelf = false,
): Promise<{ entry: Entry; crumbs: Entry[] } | null> {
  const chain = includeSelf
    ? [identifier, ...ancestorIdentifiers(identifier)]
    : ancestorIdentifiers(identifier);
  for (const candidate of chain) {
    let body: Section | Toc;
    try {
      body = await fetchIdentifier(candidate, params);
    } catch {
      continue;
    }
    if (isToc(body)) {
      return { entry: body.node, crumbs: body.ancestors };
    }
    return {
      entry: { identifier: body.identifier, num: body.num, heading: body.heading, level: "section" },
      crumbs: body.ancestors ?? [],
    };
  }
  return null;
}

/** The section's change timeline — the version page's own data (Day 4). */
export async function fetchVersions(identifier: string): Promise<Versions> {
  return getJson<Versions>(`/api/v1/sections${identifier}/versions`);
}

/**
 * The API's source-level redline: two release points diffed as verbatim XML
 * (ADR-0016).
 *
 * The reader no longer renders this. `/app/diff` diffs the *reading text*
 * instead (ADR-0026) and links to this endpoint for anyone who wants the
 * bytes — so the client stays here, matching the API's surface, even though
 * the page it was written for stopped calling it.
 */
export async function fetchDiff(identifier: string, from: string, to: string): Promise<Diff> {
  return getJson<Diff>(`/api/v1/sections${identifier}/diff${qs({ from, to })}`);
}

/**
 * Auth-aware SSR reads (Day 5) — `/app/provisions` is rendered server-side like
 * every other page, so it has to forward the *browser's* session cookie to this
 * process's own server-side fetch by hand: a Node `fetch` to `API_BASE_URL` is a
 * separate request with no cookie jar of its own, unlike a same-origin fetch
 * from client-side JS (which is how `WatchButton.astro`'s island stays logged
 * in without any of this).
 */
async function getJsonWithCookie<T>(path: string, cookie: string | null): Promise<T | null> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { accept: "application/json", ...(cookie ? { cookie } : {}) },
  });
  if (response.status === 401) return null;
  if (!response.ok) {
    const body: { detail?: string } = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }
  return (await response.json()) as T;
}

/** `null` when the browser has no valid session — not an error, just "signed out". */
export async function fetchMe(cookie: string | null): Promise<User | null> {
  return getJsonWithCookie<User>("/api/v1/auth/me", cookie);
}

/** The reader's one watchlist ("My Provisions"), auto-created on first use.
 * `null` when signed out — callers check `fetchMe` first to tell that apart
 * from "signed in with nothing watched yet" (an empty `items`). */
export async function fetchDefaultWatchlist(cookie: string | null): Promise<Watchlist | null> {
  return getJsonWithCookie<Watchlist>("/api/v1/watchlist", cookie);
}
