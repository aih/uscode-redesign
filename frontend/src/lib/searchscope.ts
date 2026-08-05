/**
 * The `field:value` scopes a search query can carry, read and written.
 *
 * The query string is the only place a search is written down. A facet link
 * therefore edits the query rather than adding a parameter beside it: one
 * representation, so `/app/search?q=water+title:16` is the whole search and a
 * filtered search is citable by its URL alone.
 *
 * This mirrors `parse_query` / `with_filter` / `without_filter` in
 * `storage/searchquery.py`, and the two must agree about which names are
 * scopes — a facet link writing `chapter:1` against a parser that does not know
 * the word would silently search for the literal text. The vocabulary is
 * ratcheted: `SEARCH_SCOPES` here is compared against Python's `SCOPE_FIELDS` by
 * `tests/test_search_syntax.py`, the same way the operator flags already are.
 */

export const SEARCH_SCOPES = ["heading", "title", "chapter", "status"] as const;
export type SearchScope = (typeof SEARCH_SCOPES)[number];

/** The two that name a moment rather than a subset. Parsed here so a query
 * carrying one round-trips through a facet edit unchanged. */
export const TIME_SCOPES = ["release", "date"] as const;

const ALL_SCOPES: readonly string[] = [...SEARCH_SCOPES, ...TIME_SCOPES];

/** Whitespace-separated tokens, except that a double-quoted run is one token —
 * including one carrying a scope prefix.
 *
 * The first alternative is not redundant. `"[^"]*"|\S+` only recognises a
 * quoted run when the quote opens the token, so `heading:"wild horses"` matched
 * `heading:"wild` and then `horses"` — the scope took a value of `"wild` and
 * the second word fell through to the free text. Mirrors `_TOKENS` in
 * `storage/searchquery.py`, which had the same bug. */
const TOKENS = /[a-zA-Z]+:"[^"]*"|"[^"]*"|\S+/gu;
const SCOPE_TOKEN = /^([a-z]+):(.*)$/iu;

export interface ScopeTerm {
  name: string;
  value: string;
}

export interface ParsedQuery {
  /** What is left once the scopes are lifted out. */
  text: string;
  scopes: ScopeTerm[];
}

function unquote(value: string): string {
  return value.length >= 2 && value.startsWith('"') && value.endsWith('"')
    ? value.slice(1, -1)
    : value;
}

/** `t16` → `16`. A drafter writing `title:t16` means title 16, and the index
 * holds the bare form because that is what `Title.num` holds. */
export function normaliseTitle(value: string): string {
  const lower = value.trim().toLowerCase();
  return /^t\d/u.test(lower) ? lower.slice(1) : lower;
}

function normalise(name: string, value: string): string {
  return name === "title" ? normaliseTitle(value) : value.trim().toLowerCase();
}

export function parseQuery(q: string): ParsedQuery {
  const text: string[] = [];
  const scopes: ScopeTerm[] = [];
  for (const token of q.match(TOKENS) ?? []) {
    const match = SCOPE_TOKEN.exec(token);
    const name = match?.[1]?.toLowerCase();
    const value = match ? unquote(match[2]).trim() : "";
    if (!match || !name || !ALL_SCOPES.includes(name) || !value) {
      // A prefix this site does not implement, or one with nothing after it,
      // stays in the text — the same forgiveness the Python parser gives it.
      text.push(token);
    } else {
      scopes.push({ name, value: normalise(name, value) });
    }
  }
  return { text: text.join(" "), scopes };
}

function quoteIfSpaced(value: string): string {
  return value.includes(" ") ? `"${value}"` : value;
}

function unparse(parsed: ParsedQuery): string {
  const parts = parsed.text ? [parsed.text] : [];
  for (const { name, value } of parsed.scopes) {
    parts.push(`${name}:${quoteIfSpaced(value)}`);
  }
  return parts.join(" ");
}

export function hasScope(q: string, name: string, value: string): boolean {
  const wanted = normalise(name, value);
  return parseQuery(q).scopes.some((s) => s.name === name && s.value === wanted);
}

/** The same query with one more scope. Idempotent. */
export function withScope(q: string, name: string, value: string): string {
  if (hasScope(q, name, value)) return q;
  const parsed = parseQuery(q);
  parsed.scopes.push({ name, value: normalise(name, value) });
  return unparse(parsed);
}

/** The same query with one scope removed. */
export function withoutScope(q: string, name: string, value: string): string {
  const wanted = normalise(name, value);
  const parsed = parseQuery(q);
  parsed.scopes = parsed.scopes.filter((s) => !(s.name === name && s.value === wanted));
  return unparse(parsed);
}

/** Add the scope, or take it away if it is already on. What a facet link does. */
export function toggleScope(q: string, name: string, value: string): string {
  return hasScope(q, name, value) ? withoutScope(q, name, value) : withScope(q, name, value);
}
