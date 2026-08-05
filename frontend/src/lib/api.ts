/**
 * The only place this app calls `/api/v1` (ADR-0011: frontend consumes the API
 * over HTTP and nothing else). Server-side `fetch` in Node needs an absolute
 * URL, so every call goes through `BASE` — `API_BASE_URL` in `docker compose`
 * (Caddy in front, ADR-0015), `localhost:8000` for `npm run dev`'s own proxy.
 */

import { API } from "./url";
import type {
  Citation,
  Diff,
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

/** The OpenAPI schema FastAPI generates, for `/app/docs` to render.
 *
 * Not under `/api/v1` — `/openapi.json` is where FastAPI publishes it and
 * `main.py` does not move it, so this is the one path here that is not built
 * from `API`. Everything the docs page shows is derived from this: there is no
 * second, hand-written description of the API to drift out of date. */
export async function fetchOpenApi(): Promise<OpenApiSchema> {
  return getJson<OpenApiSchema>("/openapi.json");
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
