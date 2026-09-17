/**
 * The site's currency in the chrome: the newest release point loaded and its
 * date, in the header of every page, and the same with the last check of
 * uscode.house.gov in the footer (ADR-0085).
 *
 * `/api/v1/status` is read at most once per `TTL_MS` per process, and again as
 * soon as any response has carried a newer corpus generation (ADR-0078). Both
 * halves are needed: the generation moves when a load commits, and the clock is
 * what moves `hours_since_check`, which changes every day with no load at all.
 * `fetchStatus` never throws, and a null answer is not kept, so a status route
 * that was briefly down costs the chrome one page's line rather than five
 * minutes of it.
 */

import { fetchStatus } from "./api";
import { currencyNote, usDate } from "./currency";
import { currentGeneration } from "./generation";
import type { Status } from "./types";

/** Five minutes: ADR-0018's `REVALIDATE`, and `/api/v1/status`'s own `max-age`. */
export const TTL_MS = 300_000;

interface Entry {
  pending: Promise<Status | null>;
  at: number;
  generation: number | null;
}

export class StatusMemo {
  private entry: Entry | null = null;

  constructor(
    private fetcher: () => Promise<Status | null> = fetchStatus,
    private now: () => number = Date.now,
    private ttlMs: number = TTL_MS,
    private generation: () => number | null = currentGeneration,
  ) {}

  private fresh(entry: Entry): boolean {
    if (this.now() - entry.at >= this.ttlMs) return false;
    const seen = this.generation();
    return entry.generation === null || seen === null || entry.generation === seen;
  }

  get(): Promise<Status | null> {
    if (this.entry && this.fresh(this.entry)) return this.entry.pending;
    const pending = this.fetcher();
    const entry: Entry = { pending, at: this.now(), generation: this.generation() };
    this.entry = entry;
    void pending.then((status) => {
      if (status === null && this.entry === entry) this.entry = null;
    });
    return pending;
  }

  clear(): void {
    this.entry = null;
  }
}

const memo = new StatusMemo();

/** `/api/v1/status`, memoised for the chrome. */
export function cachedStatus(): Promise<Status | null> {
  return memo.get();
}

/** The header's line: the newest release point loaded and its currency date. */
export interface Dateline {
  label: string;
  /** `MM/DD/YYYY`. */
  date: string;
}

export function dateline(status: Status | null): Dateline | null {
  const label = status?.corpus.latest_release;
  const date = usDate(status?.corpus.latest_currency_date ?? null);
  return label && date ? { label, date } : null;
}

/** The footer's facts. */
export interface FooterCurrency extends Dateline {
  /** The day uscode.house.gov was last checked, `MM/DD/YYYY` in Washington's
   *  calendar; null when there is no record of a check. */
  checkedOn: string | null;
  /** `currencyNote`'s headline when its tone is a warning. */
  warning: string | null;
}

const WASHINGTON = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** `2026-09-16T21:01:28Z` → `09/16/2026`; null for anything unparseable. */
export function checkedOnDate(timestamp: string | null): string | null {
  if (!timestamp) return null;
  const when = new Date(timestamp);
  return Number.isNaN(when.getTime()) ? null : WASHINGTON.format(when);
}

export function footerCurrency(status: Status | null): FooterCurrency | null {
  const line = dateline(status);
  if (!status || !line) return null;
  const note = currencyNote(status);
  return {
    ...line,
    checkedOn: status.source.ok ? checkedOnDate(status.source.last_checked_at) : null,
    warning: note?.tone === "warning" ? note.text : null,
  };
}
