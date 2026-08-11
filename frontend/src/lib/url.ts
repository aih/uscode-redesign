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

/**
 * `/app/diff/…?from=&to=` — a redline between two release points (Day 4).
 *
 * `provision` names a sub-section path — `/c/5` — of the section being
 * compared. It rides as a query parameter rather than a fragment because the
 * server has to act on it: the redline is built page-side, and a fragment never
 * leaves the browser. The page anchors and marks that provision inside the
 * whole section's redline, which is ADR-0001's rule about never losing context
 * applied to a comparison.
 */
export function diffHref(
  identifier: string,
  from: string,
  to: string,
  provision?: string | null,
): string {
  const params = new URLSearchParams({ from, to });
  if (provision) params.set("at", provision);
  return `${diffAction(identifier)}?${params.toString()}`;
}

/** The path half of `diffHref`, for a GET form whose own fields supply the
 *  query string. Rule 5 is about every reader href being built here, and a
 *  form action is one. */
export function diffAction(identifier: string): string {
  return `${APP}/diff${encodePath(identifier)}`;
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
 * lets it say so. See `docs/citation-index-plan.md`.
 *
 * `release` and `date` are the two ways to ask for a moment in time, and they
 * are the same two a citation URL takes. `date` was missing here, which is why
 * paging a dated search silently fell back to the text in force at page two —
 * the pager rebuilds its own href, and could only rebuild what this accepts. */
export function searchHref(
  query: string,
  opts: {
    cites?: boolean;
    release?: string | null;
    date?: string | null;
    sort?: string | null;
    offset?: number | null;
  } = {},
): string {
  const params = new URLSearchParams({ q: query });
  if (opts.release) params.set("release", opts.release);
  if (opts.date) params.set("date", opts.date);
  if (opts.cites) params.set("cites", "1");
  // `relevance` is the default, so leaving it out keeps the plain search URL
  // plain — and keeps two URLs from naming the same search.
  if (opts.sort && opts.sort !== "relevance") params.set("sort", opts.sort);
  if (opts.offset) params.set("offset", String(opts.offset));
  return `${APP}/search?${params.toString()}`;
}

/** `/app/login`, carrying where to return to after signing in. */
/** `/app/search/syntax` — the operators the search box accepts (ADR-0031). */
export function syntaxHref(): string {
  return `${APP}/search/syntax`;
}

/** `/app/settings` — the signed-in reader's preferences. */
export function settingsHref(): string {
  return `${APP}/settings`;
}

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

/**
 * The identifiers to try, nearest first, when one resolves to nothing.
 *
 * `/us/usc/t16/s45f/c/5` → `/us/usc/t16/s45f`, `/us/usc/t16`. Stops at the
 * title: `/us/usc` is the front page and is not an identifier the API answers,
 * and anything above it belongs to a different code.
 *
 * Every segment is a candidate rather than only the title, because the trail a
 * reader wants back is the nearest thing that exists — a mistyped subsection of
 * a real section should offer the section, not the whole title. The list is
 * short by construction (a section identifier has at most a handful of
 * segments), which is what makes trying them one at a time affordable on a page
 * nobody reaches on purpose.
 */
export function ancestorIdentifiers(identifier: string): string[] {
  const parts = identifier.replace(/\/+$/u, "").split("/").filter(Boolean);
  // ["us", "usc", "t16", …] — anything shorter has no title in it.
  if (parts.length < 4 || parts[0] !== "us" || parts[1] !== "usc") return [];
  const out: string[] = [];
  for (let end = parts.length - 1; end >= 3; end -= 1) {
    out.push(`/${parts.slice(0, end).join("/")}`);
  }
  return out;
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

/* ------------------------------------------------- classification tables
 *
 * OLRC's classification tables (ADR-0067) under `/app/classification`. The
 * source publishes one file per congress per session; the reader's URL says
 * which one, and the filters, sort and page ride in the query string.
 */

/** The session segment of a classification URL.
 *
 * The database stores `0` for the 104th congress, whose tables are one
 * whole-congress file rather than one per session. `0` is not a session anyone
 * would type, so the URL writes `all` and the two are mapped in both
 * directions here. */
export type ClassificationSession = "1" | "2" | "all";

/** `0` → `all`. */
export function sessionSegment(session: number): ClassificationSession {
  return session === 1 ? "1" : session === 2 ? "2" : "all";
}

/** `all` → `0`; anything that is not a session at all → `null`, which is what
 *  makes a mistyped URL a 404 rather than a query for session `NaN`. */
export function sessionNumber(segment: string): number | null {
  if (segment === "all") return 0;
  if (segment === "1") return 1;
  if (segment === "2") return 2;
  return null;
}

/**
 * A section number as the tables spell it, from whatever a person typed.
 *
 * `classification_entries.section_norm` is lowercased with a plain hyphen
 * (spec §2), while the corpus's `usc_identifier` carries an EN DASH — the same
 * two spellings gotcha 17 is about. Typed input is matched against the former,
 * so it is normalized to the hyphen here and never to U+2013.
 */
export function normalizeSectionKey(value: string): string {
  return value.trim().toLowerCase().replace(/[‑–—]/gu, "-");
}

/**
 * `?offset=` as the API will accept it, from whatever a URL carried.
 *
 * The counterpart of the `offset` `classificationHref` writes. The route
 * declares it `int` and `ge=0`, so a float is a 422 and an error page where the
 * table should be — `Number("1.5")` is `1.5`, which reaches the API intact and
 * fails there rather than here. Anything unreadable, negative or fractional
 * becomes the first page, which is the same rule `?sort=` follows: a mistyped
 * URL still shows the table.
 */
export function readOffset(raw: string | null | undefined): number {
  const parsed = Number(raw ?? "");
  if (!Number.isFinite(parsed) || parsed <= 0) return 0;
  return Math.floor(parsed);
}

export interface ClassificationFilters {
  /** `118-33` — one public law. */
  pl?: string | null;
  /** `101` — a prefix of the law's own section designator. */
  plSection?: string | null;
  title?: string | null;
  section?: string | null;
  sort?: string | null;
  offset?: number | null;
}

/** The order a session table is read in. `pl` is the source's own order and is
 *  the default, so it is left out of the URL. */
export const CLASSIFICATION_SORTS = ["pl", "code"] as const;

/**
 * `/app/classification`, `/app/classification/118/2`, and either with filters.
 *
 * Defaults are omitted rather than written out, so one view has one URL: the
 * source's order and the first page spell themselves by their absence. A
 * congress without a session (or the other way round) names no file, so both
 * are required together or the base page is returned.
 */
export function classificationHref(
  congress?: number | string | null,
  session?: string | null,
  opts: ClassificationFilters = {},
): string {
  const base =
    congress != null && congress !== "" && session
      ? `${APP}/classification/${congress}/${session}`
      : `${APP}/classification`;
  const params = new URLSearchParams();
  if (opts.pl) params.set("pl", opts.pl);
  if (opts.plSection) params.set("pl_section", opts.plSection);
  if (opts.title) params.set("title", opts.title);
  if (opts.section) params.set("section", normalizeSectionKey(opts.section));
  if (opts.sort && opts.sort !== "pl") params.set("sort", opts.sort);
  if (opts.offset) params.set("offset", String(opts.offset));
  const query = params.toString();
  return query ? `${base}?${query}` : base;
}

/** `/app/classification/ecct` — the Editorial Classification Change Table. */
export function classificationEcctHref(): string {
  return `${APP}/classification/ecct`;
}

/** `/api/v1/classifications/suggest?q=…` — what the lookup's listbox fetches.
 *
 * Built here rather than in the island for architecture rule 5's reason and one
 * more: an `is:inline` script imports nothing, so a URL written inside it is a
 * second copy of this one. The page renders `classificationSuggestHref("")` into
 * a data attribute and the island appends the encoded query to it. */
export function classificationSuggestHref(query: string): string {
  return `${API}/classifications/suggest?q=${encodeURIComponent(query)}`;
}

/**
 * Where one lookup suggestion leads.
 *
 * The API returns a ready-made `href` and the same answer in structured pieces.
 * This builds from the pieces, because a reader URL is this module's to write
 * (architecture rule 5) — and because the identifier in a `section-notes`
 * suggestion is the corpus's EN DASH, which `appHref` percent-encodes and a
 * pasted string would not.
 *
 * The three kinds the API defines today, and an unknown one falls back to the
 * path it was given: a suggestion this reader does not recognise should still
 * go somewhere rather than nowhere.
 */
export function classificationSuggestionHref(suggestion: {
  kind: string;
  href: string;
  congress?: number | null;
  session_label?: string | null;
  pl?: string | null;
  pl_section?: string | null;
  title_num?: string | null;
  section?: string | null;
  identifier?: string | null;
  fragment?: string | null;
}): string {
  if (suggestion.kind === "pl" && suggestion.congress != null && suggestion.session_label) {
    return classificationHref(suggestion.congress, suggestion.session_label, {
      pl: suggestion.pl,
      plSection: suggestion.pl_section,
    });
  }
  if (suggestion.kind === "section-notes" && suggestion.identifier) {
    return `${appHref(suggestion.identifier)}${suggestion.fragment ?? ""}`;
  }
  if (suggestion.kind === "section-classifications" && suggestion.title_num) {
    return classificationHref(null, null, {
      title: suggestion.title_num,
      section: suggestion.section,
    });
  }
  return `${APP}${suggestion.href}`;
}

/** govinfo's page for a public law. Predictable from (congress, number), which
 *  congress.gov's is not — its URLs are keyed by the bill, and the tables do
 *  not carry one. */
export function govinfoPlawHref(congress: number | string, num: number | string): string {
  return `https://www.govinfo.gov/app/details/PLAW-${congress}publ${num}`;
}

/** OLRC's statviewer, the target the source tables link their own Stat. pages
 *  to. Only ever built from an integer page: `110 Stat. 3009-587` is a single
 *  page whose label this endpoint cannot take. */
export function statViewerHref(volume: number | string, page: number | string): string {
  return `https://uscode.house.gov/statviewer.htm?volume=${volume}&page=${page}`;
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
