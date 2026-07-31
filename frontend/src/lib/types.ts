/**
 * The wire types this app reads — a hand-kept mirror of `api/schemas.py`.
 *
 * Not generated, because the two sides are meant to be independently editable
 * (ADR-0010): the frontend only ever reads JSON over HTTP, so a mismatch here
 * shows up as a runtime shape surprise, not a type error. Keep it narrow — only
 * the fields a page or component actually reads.
 */

export interface Release {
  label: string;
  currency_date: string;
  congress: number;
  law_num: number;
  excluded_laws: number[];
  update_num: number | null;
  seq: number;
  is_partial: boolean;
  caveat: string | null;
  titles_affected: string[];
  ingested_titles: string[];
}

export interface Provision {
  identifier: string;
  found: boolean;
  xml: string | null;
}

/** A further element the source published under the same `@identifier` at the
 *  same release point. Normally there are none; when there are, the reader shows
 *  every occurrence rather than picking one (ADR-0021). */
export interface DuplicateOccurrence {
  num: string | null;
  heading: string | null;
  status: string | null;
  xml: string;
  content_hash: string;
  guid: string | null;
  seq_in_title: number;
  source_credit: string | null;
}

export interface Section {
  identifier: string;
  title_num: string;
  num: string | null;
  heading: string | null;
  status: string | null;
  guid: string | null;
  source_credit: string | null;
  seq_in_title: number;
  parent_identifier: string | null;
  /** Title root down to the section's parent, inclusive — the breadcrumb trail. */
  ancestors: Entry[];
  xml: string;
  provision: Provision | null;
  duplicates: DuplicateOccurrence[];
  release: Release;
  served_from: Release;
  content_first_seen: Release;
  is_exact: boolean;
  note: string | null;
}

export interface Entry {
  identifier: string;
  level: string;
  num: string | null;
  heading: string | null;
  status?: string | null;
  is_section?: boolean;
}

export interface Toc {
  node: Entry;
  ancestors: Entry[];
  children: Entry[];
  sections: Entry[];
  release: Release;
  served_from: Release;
  note: string | null;
}

/** A `Section` has `xml`/`identifier`; a `Toc` has `node`/`sections` — either
 * answers `/api/v1/us/usc/{identifier}`, and the identifier alone decides which. */
export function isToc(body: Section | Toc): body is Toc {
  return "node" in body;
}

export interface Neighbors {
  identifier: string;
  previous: Entry | null;
  next: Entry | null;
  release: Release;
  served_from: Release;
}

export type Labels = Record<string, Entry>;

export interface VersionEntry {
  content_hash: string;
  first_seen: Release;
  releases: string[];
  num: string | null;
  heading: string | null;
  status: string | null;
}

export interface Versions {
  identifier: string;
  versions: VersionEntry[];
}

export interface DiffSection {
  release: Release;
  num: string | null;
  heading: string | null;
  status: string | null;
  content_hash: string;
}

export interface DiffOp {
  op: "equal" | "insert" | "delete";
  text: string;
}

export interface Diff {
  identifier: string;
  from: DiffSection;
  to: DiffSection;
  ops: DiffOp[];
}

export interface Title {
  num: string;
  name: string;
  is_positive_law: boolean;
  ingested_releases: string[];
}

/** Mirrors `CitationOut` — what `/api/v1/citation?q=` answers.
 *
 * `exists` is the field that matters: a citation can parse perfectly and name
 * nothing this database holds, and those are different failures to put in front
 * of a reader. `message` carries the explanation when there is a specific one. */
export interface Citation {
  query: string;
  identifier: string;
  section_identifier: string;
  title_num: string;
  section_num: string | null;
  subdivisions: string[];
  kind: "section" | "structure" | "title";
  note: boolean;
  et_seq: boolean;
  exists: boolean;
  heading: string | null;
  num: string | null;
  release: Release | null;
  message: string | null;
}

/** Mirrors `UserOut` (Day 5) — the whole shape `/api/v1/auth/me` returns. */
export interface User {
  id: string;
  email: string;
}

/** Mirrors `WatchlistItemOut` — a watched provision, enriched with what it
 * currently says. `num`/`heading`/`status` are null when enrichment failed
 * (an item pinned to a release the title was never ingested at), never when
 * the section simply has no heading. */
export interface WatchlistItem {
  id: number;
  identifier: string;
  title_num: string;
  note: string | null;
  pinned_release_label: string | null;
  created_at: string;
  num: string | null;
  heading: string | null;
  status: string | null;
}

/** Mirrors `WatchlistOut` — a named list plus its items, the shape both
 * `GET /api/v1/watchlist` (the reader's default list) and
 * `GET /api/v1/watchlists/{id}/items` return. */
export interface Watchlist {
  id: number;
  name: string;
  items: WatchlistItem[];
}

/** Mirrors `SearchSnippet` — one highlighted fragment from one field.
 *
 * `text` carries OpenSearch's `<em>` wrappers around the matched terms and
 * nothing else it escaped: the cluster does not escape field content, so this
 * is rendered through `highlightHtml` rather than `set:html` directly. */
export interface SearchSnippet {
  field: string;
  text: string;
}

/** Mirrors `SearchResultItem`. The index unit is the deduped section *version*
 * (ADR-0028), so `first_release` is where this exact text first appeared —
 * which is why an unchanged section can report a release far older than the one
 * searched. `type` distinguishes the two indices a query spans: a section, or a
 * structural node (a chapter or subchapter heading). */
export interface SearchResultItem {
  identifier: string;
  heading: string | null;
  num: string | null;
  level: string | null;
  type: "section" | "structure";
  snippets: SearchSnippet[];
  first_release: string | null;
  is_current: boolean;
}

/** Mirrors `SearchResponse`. `release` names the release point actually
 * searched — absent means the text in force, which is the default (ADR-0028). */
export interface SearchResponse {
  results: SearchResultItem[];
  total: number;
  release: string | null;
  note: string | null;
}

/* --------------------------------------------------------------- OpenAPI
 *
 * Only the parts `/app/docs` renders. This is deliberately not a complete
 * OpenAPI 3.1 typing: the schema is generated by FastAPI from the routes in
 * `api/`, so the shapes below describe what this project's schema actually
 * contains rather than everything the specification permits. Anything not
 * modelled here is simply not shown.
 */

/** A `$ref` to a component schema, or an inline one. Resolved by `derefSchema`
 * in `lib/openapi.ts` — FastAPI emits `$ref` for every Pydantic model. */
export interface JsonSchema {
  $ref?: string;
  type?: string;
  format?: string;
  title?: string;
  description?: string;
  enum?: unknown[];
  default?: unknown;
  items?: JsonSchema;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  /** Optional fields become `anyOf: [T, {type: "null"}]` in OpenAPI 3.1. */
  anyOf?: JsonSchema[];
}

export interface OpenApiParameter {
  name: string;
  in: "query" | "path" | "header" | "cookie";
  description?: string;
  required?: boolean;
  schema?: JsonSchema;
}

export interface OpenApiOperation {
  summary?: string;
  description?: string;
  tags?: string[];
  operationId?: string;
  parameters?: OpenApiParameter[];
  requestBody?: {
    required?: boolean;
    content?: Record<string, { schema?: JsonSchema }>;
  };
  responses?: Record<
    string,
    { description?: string; content?: Record<string, { schema?: JsonSchema }> }
  >;
}

export interface OpenApiSchema {
  openapi: string;
  info: { title: string; version: string; summary?: string; description?: string };
  paths: Record<string, Record<string, OpenApiOperation>>;
  components?: { schemas?: Record<string, JsonSchema> };
}
