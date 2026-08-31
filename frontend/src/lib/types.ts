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

/** `GET /api/v1/status` — how current this mirror is, and how it knows.
 *
 * Two facts, kept apart on purpose: what is loaded here, and when this
 * deployment last confirmed with OLRC that it is still everything published.
 * A reader can check the first for themselves by reading a date; only the
 * site can answer the second. */
export interface SourceCheck {
  url: string;
  last_checked_at: string | null;
  hours_since_check: number | null;
  ok: boolean;
  stale: boolean;
  release_points_seen: number | null;
  new_release_points: string[];
  latest_published_label: string | null;
  latest_published_date: string | null;
  error: string | null;
}

export interface CorpusStatus {
  latest_release: string | null;
  latest_currency_date: string | null;
  release_points_known: number;
  behind_by: number | null;
}

export interface Status {
  source: SourceCheck;
  corpus: CorpusStatus;
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

/** A Public Law the classification tables attribute to a version transition
 *  (ADR-0074). `classification_actions` holds the source's own action words —
 *  the empty string is a plain amendment. */
export interface VersionLaw {
  pl_congress: number;
  pl_num: number;
  in_classification: boolean;
  is_note_classification: boolean;
  in_source_credit: boolean;
  classification_actions: string[];
}

export interface VersionEntry {
  content_hash: string;
  first_seen: Release;
  releases: string[];
  num: string | null;
  heading: string | null;
  status: string | null;
  /** `initial` | `text` | `notes` | `structure` — how this entry differs from
   *  the one before it (ADR-0074). Null on every entry of a corpus whose change
   *  rows have not been computed, which the timeline says out loud. */
  change_kind?: string | null;
  text_changed?: boolean | null;
  notes_changed?: boolean | null;
  status_changed?: boolean | null;
  concurrent?: boolean | null;
  /** `classified` | `none`. */
  attribution?: string | null;
  laws?: VersionLaw[];
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
  title_num: string | null;
  status: string | null;
  /** Superseded versions of this section that also match (ADR-0049). The
   * default search reads the text in force, so this is the difference between
   * a section that does not mention the words and one that stopped. */
  earlier_matches: number;
  /** The source published more than one provision under this identifier at this
   * release point and the index holds one of them (ADR-0021). */
  id_collision: boolean;
}

/** One facet value and how many results carry it. */
export interface FacetValue {
  value: string;
  count: number;
}

/** Mirrors `SearchFacets` — counts over the whole result set, not the page. */
export interface SearchFacets {
  titles: FacetValue[];
  statuses: FacetValue[];
}

/** Mirrors `SearchResponse`. `release` names the release point actually
 * searched — absent means the text in force, which is the default (ADR-0028). */
export interface SearchResponse {
  results: SearchResultItem[];
  total: number;
  release: string | null;
  note: string | null;
  sort: string;
  facets: SearchFacets;
}

/* ------------------------------------------------- classification tables
 *
 * Mirrors the `…Out` models in `api/schemas.py` for the routes in
 * `docs/classification-spec.md` §4 (ADR-0067). Every field the source cannot
 * supply is nullable here because it is nullable there: 1,533 of the corpus's
 * 144,837 rows have no `usc_identifier`, 2 have no public law at all, and 6,053
 * cite a Statutes at Large page with no integer form.
 */

/** One source document — a Public Law order table, or the ECCT. */
export interface ClassificationFile {
  kind: string;
  congress: number;
  /** `1`, `2`, or `0` for the 104th's single whole-congress file. */
  session: number;
  /** The same value spelled the way a URL spells it: `1`, `2` or `all`. */
  session_label: string;
  source_url: string;
  source_filename: string;
  /** Verbatim: "Public Law 119-70 and Public Laws 119-74 through 119-102". */
  covered_laws_text: string | null;
  /** Gap-aware segments of the above — `["70-70", "74-102"]`. */
  covered_ranges: string[];
  first_law: number | null;
  last_law: number | null;
  prepared_date: string | null;
  /** Null for the 104th, which spans two Statutes at Large volumes. */
  stat_volume: number | null;
  fetched_at: string;
  row_count: number;
  skipped_lines: number;
}

/** The last poll of OLRC's classification index page.
 *
 * Its own check, and deliberately not the one `/api/v1/status` reports: that
 * polls the release-point inventory, and the two sources are published on
 * different schedules (ADR-0036, ADR-0067 decision 4). */
export interface ClassificationSource {
  url: string;
  /** Before any recorded check this is the date the tables were first loaded,
   * flagged `baseline`. */
  last_checked_at: string | null;
  hours_since_check: number | null;
  ok: boolean;
  /** The last check failed or is over a week old. */
  stale: boolean;
  /** No check has been recorded; `last_checked_at` is the first-load date. */
  baseline?: boolean;
  files_seen: number | null;
  changed_files: string[];
  latest_covered_text: string | null;
  error: string | null;
}

/** Route 1: the registry, its freshness, and the two totals the index page
 *  would otherwise compute for itself. */
export interface ClassificationTables {
  source: ClassificationSource;
  files: ClassificationFile[];
  /** The newest Public Law order table — the session being classified now. */
  current: ClassificationFile | null;
  /** Rows across every Public Law order table held. */
  entry_total: number;
}

/** One row of a Public Law order table. */
export interface ClassificationEntry {
  /** The congress of the *document* this row came from, which is not always the
   *  congress of the law: a table can carry a row about an earlier one. */
  congress: number;
  session: number;
  session_label: string;
  row_seq: number;
  /** The tag-stripped source line, kept verbatim — the only thing 129 rows the
   *  parser could not fully split still have (ADR-0067's addendum). */
  raw_line: string;
  title_raw: string;
  /** A string: `5a` is a title and `5` is a different one (gotcha 16). Ordering
   *  by it is the API's job, through `title_sort_key`. */
  title_num: string;
  is_appendix: boolean;
  section_raw: string;
  /** Lowercased, with a plain hyphen — what typed input is matched against. */
  section_norm: string;
  /** `""` means the law amended the section; the vocabulary is open. */
  description_raw: string;
  is_note: boolean;
  action: string | null;
  transfer_counterpart: string | null;
  act_name: string | null;
  /** Spelled with an EN DASH, as the corpus spells it — so every href built
   *  from it goes through `appHref`, which percent-encodes. Null for the 1,531
   *  appendix rows that derive none by rule, and for 2 others. */
  usc_identifier: string | null;
  pl_congress: number | null;
  pl_num: number | null;
  /** `118-35`, derived rather than stored; null for the 2 rows whose Pub. L.
   *  cell could not be read. Those rows are kept. */
  pl_label: string | null;
  /** `""` means the row is about the whole law. */
  pl_section_raw: string;
  new_section_quote: string | null;
  stat_volume: number | null;
  /** Empty for a page with no integer form. */
  stat_pages: number[];
  /** The page as printed — `3009-587`, `1501A-594`, `1544, 1545`. */
  stat_page_labels: string[];
}

/** One row of the Editorial Classification Change Table. */
export interface EcctEntry {
  congress: number;
  session: number;
  session_label: string;
  row_seq: number;
  former_raw: string;
  former_title_num: string | null;
  former_section_norm: string | null;
  former_is_note: boolean;
  new_raw: string;
  new_title_num: string | null;
  new_section_norm: string | null;
  new_is_note: boolean;
  provision_affected: string;
  provision_prompting: string;
  affected_pl_congress: number | null;
  affected_pl_num: number | null;
  prompting_pl_congress: number | null;
  prompting_pl_num: number | null;
}

/** One page of classification rows, and the size of the set it came from —
 *  routes 2 to 5. */
export interface ClassificationEntryPage {
  items: ClassificationEntry[];
  /** Rows the filters matched, not rows returned: what a pager needs. */
  total: number;
  limit: number;
  offset: number;
  sort: string | null;
  /** The document these rows came from, where they all came from one. Null on
   *  the by-section and by-identifier routes, which read across every table. */
  file: ClassificationFile | null;
}

/** The ECCT is 21 rows, so it is returned whole. */
export interface EcctPage {
  items: EcctEntry[];
  total: number;
}

/**
 * One thing the lookup box can offer for what was typed.
 *
 * `kind` is an open set — `pl`, `section-notes`, `section-classifications`,
 * `section-in-table`, `title-classifications`, `title-in-table` so far. The API
 * decides what a query means; this reader renders the answer.
 *
 * `href` is a path relative to the reader's base, percent-encoded and ready to
 * use. The structured fields beside it carry the same answer in pieces, and
 * they are what `classificationSuggestionHref` builds from — a reader URL is
 * `lib/url.ts`'s to write (architecture rule 5).
 */
export interface ClassificationSuggestion {
  kind: string;
  label: string;
  /** A second line for the row: what the suggestion leads to. */
  detail: string | null;
  href: string;
  congress: number | null;
  session: number | null;
  session_label: string | null;
  pl: string | null;
  pl_section: string | null;
  title_num: string | null;
  /** The `section_norm` spelling — a plain hyphen. */
  section: string | null;
  /** The USLM `@identifier`, as the corpus spells it (EN DASH). */
  identifier: string | null;
  fragment: string | null;
  /** How many rows are behind this suggestion, when known. */
  count: number | null;
}

export interface ClassificationSuggestions {
  query: string;
  suggestions: ClassificationSuggestion[];
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
