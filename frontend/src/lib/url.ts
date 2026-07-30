/**
 * Every reader href goes through here — CLAUDE.md architecture rule 5: "`/app`
 * is spelled out once." `API` is the identifier-mirroring machine prefix
 * (`/api/v1/us/usc/…`, ADR-0009); `APP` is the reader's own prefix (ADR-0010).
 */

export const APP = "/app";
/** `identifier` already carries `/us/usc/…` (it *is* the USLM `@identifier`),
 * so the machine-surface prefix is just `/api/v1` — `apiHref("/us/usc/t16/s45f")`
 * becomes `/api/v1/us/usc/t16/s45f`, matching `api/routes.py`'s route exactly. */
export const API = "/api/v1";

export interface ApiParams {
  release?: string | null;
  date?: string | null;
  format?: string | null;
}

function query(params: ApiParams): string {
  const pairs = Object.entries(params).filter(
    (entry): entry is [string, string] => entry[1] != null && entry[1] !== "",
  );
  if (pairs.length === 0) return "";
  return `?${new URLSearchParams(pairs).toString()}`;
}

/** A page under `/app` — always HTML, no negotiation. */
export function appHref(identifier: string, release?: string | null): string {
  return `${APP}${identifier}${query({ release })}`;
}

/** `/api/v1/us/usc/…` — the machine surface. */
export function apiHref(identifier: string, params: ApiParams = {}): string {
  return `${API}${identifier}${query(params)}`;
}

/** The bare citation URL (ADR-0009/0010): what a citation *is*, unprefixed by
 * either surface, and the form worth pasting or printing. */
export function citationHref(identifier: string, release?: string | null): string {
  return `${identifier}${query({ release })}`;
}

/** `/app/versions/…` — the change timeline for a section (Day 4). */
export function versionsHref(identifier: string): string {
  return `${APP}/versions${identifier}`;
}

/** `/app/diff/…?from=&to=` — a redline between two release points (Day 4). */
export function diffHref(identifier: string, from: string, to: string): string {
  return `${APP}/diff${identifier}?${new URLSearchParams({ from, to }).toString()}`;
}

/** `/app/provisions` — the reader's one watchlist page (Day 5). */
export function provisionsHref(): string {
  return `${APP}/provisions`;
}

/** `/app/goto?q=…` — where the citation box posts. A plain GET target, so the
 * box needs no JavaScript and the result is a URL worth pasting. */
export function gotoHref(query?: string | null): string {
  return query ? `${APP}/goto?q=${encodeURIComponent(query)}` : `${APP}/goto`;
}

/** `/app/login`, carrying where to return to after signing in. */
export function loginHref(next?: string | null): string {
  return next ? `${APP}/login?next=${encodeURIComponent(next)}` : `${APP}/login`;
}

/** `/app/signup`, same `next` convention as `loginHref`. */
export function signupHref(next?: string | null): string {
  return next ? `${APP}/signup?next=${encodeURIComponent(next)}` : `${APP}/signup`;
}

/** `45f.` → `45f`: the page supplies its own punctuation (`doc-title__num`
 * already appends "."), so a source num that carries a trailing period would
 * otherwise double it. */
export function trimNum(num: string | null | undefined): string {
  if (!num) return "";
  return num.trim().replace(/\.$/u, "");
}

/** `/c/5` → `(c)(5)`. USLM's short-form vocabulary is empty below section
 * (`docs/prior-art.md` §1), so a provision path is bare designators with no
 * level name attached — "(c)(5)" is the honest reading, not "paragraph (c)(5)",
 * because a bare designator's level (subsection? subparagraph?) is not
 * recoverable from the string alone. */
export function provisionLabel(remainder: string): string {
  return remainder
    .split("/")
    .filter((segment) => segment.length > 0)
    .map((segment) => `(${segment})`)
    .join("");
}
