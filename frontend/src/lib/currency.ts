/**
 * Putting `/api/v1/status` into one sentence a reader can act on.
 *
 * The site mirrors a source that changes without warning, so "how current is
 * this" has two halves and only one of them is visible in the text. The date on
 * a release point says what the law was current through; it says nothing about
 * whether OLRC has published three more since. That second half is the one this
 * module exists to state out loud, because the failure it guards against is
 * silent by construction: a mirror that stopped updating renders exactly like a
 * mirror with nothing to update.
 *
 * So the tone is derived from the two ways of being wrong, and they are
 * different sentences:
 *
 *   - *behind* — we know what was published and have not loaded all of it. The
 *     reader can see which release points are missing.
 *   - *unconfirmed* — we have not successfully asked lately. Nothing here is
 *     known to be wrong; nothing here is known to be right either.
 *
 * Kept as a pure function of (status, now) so it is testable without a browser
 * and without a clock — `frontend/tests/currency.test.ts`.
 */

import type { ClassificationSource, Status } from "./types";

export type Tone = "ok" | "warning";

export interface CurrencyNote {
  tone: Tone;
  /** The headline sentence — always safe to show on its own. */
  text: string;
  /** A second sentence with the detail, when there is one worth adding. */
  detail?: string;
}

/** "3 hours ago", "yesterday", "6 days ago" — deliberately coarse.
 *
 * Nobody needs the minute a mirror was polled, and a precise-looking figure
 * invites a precision the schedule does not have (the check is daily, so any
 * answer is up to a day old the moment it is rendered). */
export function humanizeAge(hours: number | null): string {
  if (hours == null) return "at an unknown time";
  if (hours < 1) return "in the last hour";
  if (hours < 2) return "an hour ago";
  if (hours < 24) return `${Math.floor(hours)} hours ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 31) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "a month ago" : `${months} months ago`;
}

/** `2026-07-12` → `07/12/2026`, the form OLRC's own currency notes use. */
export function usDate(iso: string | null): string | null {
  if (!iso) return null;
  const [year, month, day] = iso.split("-");
  return year && month && day ? `${month}/${day}/${year}` : null;
}

export function currencyNote(status: Status | null): CurrencyNote | null {
  if (!status) return null;
  const { source, corpus } = status;

  const held = corpus.latest_release
    ? `The newest release point loaded here is ${corpus.latest_release}` +
      (corpus.latest_currency_date ? ` (${usDate(corpus.latest_currency_date)})` : "") +
      "."
    : "No release point is loaded here yet.";

  if (!source.last_checked_at) {
    return {
      tone: "warning",
      text: "This site has no record of checking uscode.house.gov for new release points.",
      detail: held,
    };
  }

  const ago = humanizeAge(source.hours_since_check);

  if (!source.ok) {
    return {
      tone: "warning",
      text: `The last attempt to check uscode.house.gov failed (${ago}).`,
      // The error is shown rather than summarised: whoever can act on it needs
      // to know whether the site was down or its markup changed.
      detail: `${held}${source.error ? ` The check reported: ${source.error}` : ""}`,
    };
  }

  // Behind is reported before stale. Both can be true, and "we know we are
  // missing four release points" is the more actionable of the two.
  const behind = corpus.behind_by ?? 0;
  if (behind > 0) {
    const n = behind;
    return {
      tone: "warning",
      text:
        `${n} release point${n === 1 ? "" : "s"} published since the newest one loaded here ` +
        `${n === 1 ? "is" : "are"} not loaded yet.`,
      detail: `${held} Checked ${ago}.`,
    };
  }

  if (source.stale) {
    return {
      tone: "warning",
      text: `uscode.house.gov was last checked ${ago} — longer ago than this site intends.`,
      detail: `${held} It may not be the newest published.`,
    };
  }

  const published = source.latest_published_label
    ? ` Nothing newer than ${source.latest_published_label}` +
      (source.latest_published_date ? ` (${usDate(source.latest_published_date)})` : "") +
      " has been published."
    : "";
  return {
    tone: "ok",
    text: `Checked uscode.house.gov for new release points ${ago}.`,
    detail: `${held}${published}`,
  };
}

/**
 * The same sentence for the classification tables' own poll.
 *
 * Four states: no check row yet (the API reports the first-load date, flagged
 * `baseline`, so the page can name a date instead of "no record"), the last
 * check failed, the last check succeeded but is older than the schedule
 * intends, and the quiet case. The `!last_checked_at` branch survives only as
 * a fallback against an API older than the `baseline` field.
 */
export function classificationNote(source: ClassificationSource | null): CurrencyNote | null {
  if (!source) return null;
  const held = "The tables below are the ones this site holds.";

  if (source.baseline && source.last_checked_at) {
    // No check row yet: the API reports the date the tables were first loaded
    // as the last-checked date, and the daily check owns it from its first run.
    const loaded = usDate(source.last_checked_at.slice(0, 10));
    return {
      tone: source.stale ? "warning" : "ok",
      text: `The classification tables were last checked on ${loaded}, when this site loaded them from uscode.house.gov.`,
      detail: source.stale ? `${held} OLRC may have published a newer one since.` : held,
    };
  }

  if (!source.last_checked_at) {
    return {
      tone: "warning",
      text: "This site has no record of checking uscode.house.gov for new classification tables.",
      detail: `${held} OLRC may have published a newer one.`,
    };
  }

  const ago = humanizeAge(source.hours_since_check);

  if (!source.ok) {
    return {
      tone: "warning",
      text: `The last attempt to check uscode.house.gov for new classification tables failed (${ago}).`,
      detail: `${held}${source.error ? ` The check reported: ${source.error}` : ""}`,
    };
  }

  if (source.stale) {
    return {
      tone: "warning",
      text: `uscode.house.gov was last checked for new classification tables ${ago} — longer ago than this site intends.`,
      detail: `${held} OLRC may have published a newer one since.`,
    };
  }

  const changed = source.changed_files.length;
  return {
    tone: "ok",
    text: `Checked uscode.house.gov for new classification tables ${ago}.`,
    detail: changed > 0 ? `${changed} table${changed === 1 ? "" : "s"} changed at that check.` : undefined,
  };
}
