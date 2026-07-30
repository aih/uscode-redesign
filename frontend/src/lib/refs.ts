/**
 * What a `<ref href="…">` becomes — ADR-0015 decision 3, verified against
 * govinfo before being written down: link to something that exists, or do not
 * link. This is also the fix for the BUILDLOG 008 live bug (relative
 * `/us/pl/…` and `/us/stat/…` hrefs, paths this site never served).
 */

import type { Entry, Labels } from "./types";
import { appHref, trimNum } from "./url";

/** The internal identifiers a fragment's citations name — exactly what the
 * batched `/api/v1/labels` call needs, deduped and stripped of any query or
 * anchor. External refs (`/us/stat/…`, `/us/pl/…`) never need a label: they
 * link straight to govinfo, or not at all. */
export function citedIdentifiers(hrefs: string[]): string[] {
  const seen = new Set<string>();
  for (const href of hrefs) {
    if (!href.startsWith("/us/usc/")) continue;
    seen.add(href.split(/[?#]/u)[0]);
  }
  return [...seen];
}

export interface ResolvedRef {
  /** Where to send the reader, or `null` for plain text — never a broken link. */
  href: string | null;
  /** Hover text from the batched label lookup; `null` when there is none. */
  title: string | null;
  /** The US Code identifier this reference names, for internal refs only.
   * `null` for govinfo links and for anything that did not resolve — the
   * preview island keys off this, and there is nothing here to preview of a
   * provision published somewhere else. */
  identifier: string | null;
}

const STATUTE = /^\/us\/stat\/(\d+)\/(\d+)/u;
const PUBLIC_LAW = /^\/us\/pl\/(\d+)\/(\d+)/u;

/** govinfo's public-law link service starts at the 104th Congress
 * (ADR-0015: `104/1` → 302, `103/1` → 400). Older laws degrade to text. */
const GOVINFO_PLAW_STARTS_AT = 104;

export function resolveRef(href: string, release: string | null, labels: Labels): ResolvedRef {
  if (href.startsWith("/us/usc/")) {
    const identifier = href.split(/[?#]/u)[0];
    const entry: Entry | undefined = labels[identifier];
    return {
      href: appHref(identifier, release),
      title: entry ? labelText(entry) : null,
      identifier,
    };
  }

  const statute = STATUTE.exec(href);
  if (statute) {
    const [, volume, page] = statute;
    return {
      href: `https://www.govinfo.gov/link/statute/${volume}/${page}`,
      title: null,
      identifier: null,
    };
  }

  const publicLaw = PUBLIC_LAW.exec(href);
  if (publicLaw) {
    const [, congress, num] = publicLaw;
    if (Number(congress) >= GOVINFO_PLAW_STARTS_AT) {
      return {
        href: `https://www.govinfo.gov/link/plaw/${congress}/public/${num}`,
        title: null,
        identifier: null,
      };
    }
  }

  // Pre-104th-Congress public laws, `/us/act/…`, and anything else this site
  // does not serve: a link this site cannot resolve is text, not a 404.
  return { href: null, title: null, identifier: null };
}

function labelText(entry: Entry): string {
  // `num` arrives from the source as `§ 688.`, section symbol included — so
  // adding one produced `§ § 688.` on every citation's hover text. Add the
  // symbol only when the source did not.
  const num = trimNum(entry.num);
  const labelled = num && !num.startsWith("§") ? `§ ${num}` : num;
  return [labelled ? `${labelled}.` : null, entry.heading]
    .filter((part): part is string => Boolean(part))
    .join(" ");
}
