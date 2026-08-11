/**
 * The titles the header's Titles menu offers before "All titles".
 *
 * An editorial shortlist, not a measurement. This site records no per-title
 * traffic and the header reaches no data — `SiteHeader` renders on `/app/design`
 * too, which is required to make no API call (ADR-0053) — so the list is a
 * constant here rather than a query. Nothing in the site claims these are the
 * most-read titles; they are seven a drafter is likely to want a shortcut to,
 * and the menu's last row goes to the full list either way.
 *
 * The names are OLRC's own, shortened where the official name is a sentence
 * (title 18 is "Crimes and Criminal Procedure", title 26 is "Internal Revenue
 * Code"). The numbers are strings because a title number is a string
 * (CLAUDE.md gotcha 16) — `5a` is a title and `5` is a different one — even
 * though none of these seven carries a suffix.
 */
export interface NavTitle {
  /** The title number as it appears in an identifier: `/us/usc/t{num}`. */
  num: string;
  /** What the menu row reads after the number. */
  name: string;
}

export const NAV_TITLES: readonly NavTitle[] = [
  { num: "5", name: "Government Organization and Employees" },
  { num: "11", name: "Bankruptcy" },
  { num: "15", name: "Commerce and Trade" },
  { num: "18", name: "Crimes and Criminal Procedure" },
  { num: "26", name: "Internal Revenue Code" },
  { num: "28", name: "Judiciary and Judicial Procedure" },
  { num: "42", name: "The Public Health and Welfare" },
];
