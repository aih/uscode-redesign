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

/**
 * Percent-encode an identifier for use in a URL, leaving `/` as `/`.
 *
 * Not cosmetic. **OLRC writes section numbers with an EN DASH** —
 * `/us/usc/t16/s45a–1`, U+2013 — and 5,697 of the corpus's 65,938 sections
 * contain one. A raw en dash in a `Location:` header is a crash, not a wobble:
 * a header value is a ByteString, and Node throws
 * `Cannot convert argument to a ByteString because the character at index 20
 * has a value of 8211`. Both places this app redirects — the citation box and
 * the `?id=` guid lookup — 500 on those sections without this.
 *
 * `encodeURI` rather than `encodeURIComponent` because the identifier's slashes
 * are path structure, not data.
 */
function encodePath(identifier: string): string {
  return encodeURI(identifier);
}

/** A page under `/app` — always HTML, no negotiation. */
export function appHref(identifier: string, release?: string | null): string {
  return `${APP}${encodePath(identifier)}${query({ release })}`;
}

/** `/api/v1/us/usc/…` — the machine surface. */
export function apiHref(identifier: string, params: ApiParams = {}): string {
  return `${API}${encodePath(identifier)}${query(params)}`;
}

/** The bare citation URL (ADR-0009/0010): what a citation *is*, unprefixed by
 * either surface, and the form worth pasting or printing. */
export function citationHref(identifier: string, release?: string | null): string {
  return `${encodePath(identifier)}${query({ release })}`;
}

/** `/app/versions/…` — the change timeline for a section (Day 4). */
export function versionsHref(identifier: string): string {
  return `${APP}/versions${encodePath(identifier)}`;
}

/** `/app/diff/…?from=&to=` — a redline between two release points (Day 4). */
export function diffHref(identifier: string, from: string, to: string): string {
  return `${APP}/diff${encodePath(identifier)}?${new URLSearchParams({ from, to }).toString()}`;
}

/** `/api/v1/sections/…/diff?from=&to=` — the *source-level* redline: the same
 * two release points, diffed as verbatim XML (ADR-0016). The reader's own diff
 * page shows the reading text instead (ADR-0026) and links here for the bytes,
 * which is the one place the two views are named side by side. */
export function apiDiffHref(identifier: string, from: string, to: string): string {
  return `${API}/sections${encodePath(identifier)}/diff?${new URLSearchParams({ from, to }).toString()}`;
}

/** `/app/preview/…` — the hover preview of a cited provision (ADR-0024).
 *
 * An Astro *endpoint*, not a page: it returns the rendered fragment so no USLM
 * renderer reaches the browser. It goes through `encodePath` for the same
 * reason everything else here does, and that is not theoretical — `CitePreview`
 * used to build this string inline, so hovering a citation in any of the 5,697
 * sections whose number contains U+2013 requested a malformed URL. */
export function previewHref(identifier: string, release?: string | null): string {
  return `${APP}/preview${encodePath(identifier)}${query({ release })}`;
}

/** `/app/provisions` — the reader's one watchlist page (Day 5). */
export function provisionsHref(): string {
  return `${APP}/provisions`;
}

/**
 * Validate a `?next=` destination before navigating to it.
 *
 * `loginHref`/`signupHref` put a return destination in the query string and the
 * auth forms navigate to it after a successful `fetch`. Taken at face value —
 * which is what both pages used to do — that is two live holes at the exact
 * moment someone is typing a password:
 *
 *   - `?next=https://evil.example/` is an **open redirect** off the trusted
 *     origin, straight from the login form to a copy of it.
 *   - `?next=javascript:…` is script execution in this page's **own origin**,
 *     because `window.location.assign` honours that scheme.
 *
 * So the rule is an allowlist, not a denylist: the value must be a path on this
 * origin under `/app/`. Anything else — any scheme, any authority, any path
 * outside the reader — falls back to the watchlist page. A denylist here would
 * be a losing game (`java\nscript:`, `//evil`, `/\evil`, `%6a%61…`); "starts
 * with /app/ and contains no scheme or authority" is checkable.
 */
export function safeNext(value: string | null | undefined): string {
  const fallback = provisionsHref();
  if (!value) return fallback;

  // Strip the control characters browsers ignore when parsing a URL: without
  // this, `java\tscript:alert(1)` reads as a path here and as a scheme there.
  const candidate = value.replace(/[\x00-\x1f\x7f\s]/gu, "");
  if (!candidate) return fallback;

  // A leading `//` (or `/\`) is protocol-relative — an authority, not a path.
  if (/^[/\\]{2}/u.test(candidate)) return fallback;
  // Any scheme at all. A colon before the first `/` means the string is naming
  // something other than a path on this origin.
  const firstSlash = candidate.indexOf("/");
  const firstColon = candidate.indexOf(":");
  if (firstColon !== -1 && (firstSlash === -1 || firstColon < firstSlash)) {
    return fallback;
  }
  // And after all that it still has to be a page in this reader.
  if (!candidate.startsWith(`${APP}/`)) return fallback;
  return candidate;
}

/** `/app/goto?q=…` — where the site's one search box posts. A plain GET target,
 * so the box needs no JavaScript and the result is a URL worth pasting.
 *
 * It is named for what it does most of the time rather than for everything it
 * does: `/app/goto` is a router now, and a query it cannot read as a citation
 * ends up at `searchHref` instead. */
export function gotoHref(query?: string | null): string {
  return query ? `${APP}/goto?q=${encodeURIComponent(query)}` : `${APP}/goto`;
}

/** `/app/search?q=…` — keyword results.
 *
 * `cites` marks a query that arrived as `cites <citation>`: a request for the
 * provisions that *cite* one, which this site cannot answer yet and answers as
 * a keyword search over the subject, saying so on the page. The flag is what
 * lets it say so. See `docs/citation-index-plan.md`. */
export function searchHref(
  query: string,
  opts: { cites?: boolean; release?: string | null } = {},
): string {
  const params = new URLSearchParams({ q: query });
  if (opts.release) params.set("release", opts.release);
  if (opts.cites) params.set("cites", "1");
  return `${APP}/search?${params.toString()}`;
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

/** `05` → `5`, `05a` → `5a`. OLRC's `titlesAffected` carries the *file-naming*
 * form of a title number — zero-padded, because that is how the zips are named
 * — and no URL in this reader uses it: the identifier scheme is `/us/usc/t5a`
 * (CLAUDE.md gotcha 16). */
export function unpadTitle(num: string): string {
  return num.replace(/^0+(?=\d)/u, "");
}

/** Sort key for a title number, the TypeScript half of
 * `storage.postgres.title_sort_key`: `5a` sorts after `5` and before `6`, and
 * `10` after `9`. A title number is a string and must never be compared as one
 * — sorted as text, the Code reads `1, 10, 11, 11a, 12, … 2, 20`, which is what
 * the front page listed for eight sessions (ADR-0025). */
export function titleSortKey(num: string): [number, string] {
  const match = /^(\d+)(.*)$/u.exec(unpadTitle(num));
  return match ? [Number(match[1]), match[2]] : [Number.MAX_SAFE_INTEGER, num];
}

export function compareTitles(a: string, b: string): number {
  const [an, as] = titleSortKey(a);
  const [bn, bs] = titleSortKey(b);
  return an - bn || as.localeCompare(bs);
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
