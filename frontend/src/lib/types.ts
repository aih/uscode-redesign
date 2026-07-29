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
  xml: string;
  provision: Provision | null;
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
