/**
 * The rows the command palette offers below its input (ADR-0062).
 *
 * Two kinds. `siteCommands()` are the same on every page and are built here
 * from `url.ts`, so `/app` stays spelled out once (architecture rule 5).
 * `sectionCommands()` are the ones that only mean something with a provision on
 * screen, and they need what only the server has — the section's identifier and
 * the release points its title has been published at — so the page computes
 * them and hands them to the island as JSON.
 *
 * It is a module rather than markup inside the component because the island is
 * `<script is:inline>` and can import nothing: the rows have to arrive already
 * built, and a row built in the script would be a destination no test could
 * call. The same arrangement `KeyboardNav` uses for its three neighbour hrefs.
 *
 * ## What is not here
 *
 * **No citation parsing.** `citeparse.py` is the only thing that decides what a
 * citation is (ADR-0023) and there is no TypeScript copy of it — `lib/cite.ts`
 * is the inverse function, an identifier written out as a citation. So the
 * palette's input is submitted to `/app/goto`, which is the router that already
 * answers this question, rather than to a second parser predicting what that
 * router will say.
 *
 * **No watchlist row.** Accounts are off in the reader (ADR-0034), so "add to
 * My Provisions" would be a command with nothing behind it.
 */

import type { Release } from "./types";
import { APP, classificationHref, diffHref, settingsHref, syntaxHref, versionsHref } from "./url";

export interface PaletteCommand {
  /** Stable name for the row. The e2e suite selects on it, and it is what the
   *  island filters against alongside the label. */
  id: string;
  /** What the row says. Sentence case, no trailing stop. */
  label: string;
  /** A second line under the label, or null for a row that needs none. */
  hint?: string | null;
  /** Where the row goes. Null for a row the island handles itself — the only
   *  one is the shortcut list, which is a dialog rather than a page. */
  href?: string | null;
}

/**
 * The rows every page carries.
 *
 * `/app/settings` is in the list because it is otherwise reachable from no
 * rendered page: `AuthNav` is its only linker and the header does not render
 * `AuthNav` while accounts are off (`docs/ia-map.md`).
 */
export function siteCommands(): PaletteCommand[] {
  return [
    {
      id: "titles",
      label: "All titles",
      hint: "The Code's table of contents",
      href: `${APP}/`,
    },
    {
      id: "releases",
      label: "Release points",
      hint: "Every published release point, and how current this site is",
      href: `${APP}/releases`,
    },
    {
      id: "classification",
      label: "Classification tables",
      hint: "Which provision of which public law was classified to which section",
      href: classificationHref(),
    },
    {
      id: "guide",
      label: "User guide",
      hint: "What this site does, chapter by chapter",
      href: `${APP}/guide`,
    },
    {
      id: "syntax",
      label: "Search and citation guide",
      hint: "Every citation form and search operator the box accepts",
      href: syntaxHref(),
    },
    {
      id: "settings",
      label: "Reading settings",
      hint: "Theme, reading density and where links open",
      href: settingsHref(),
    },
    {
      id: "shortcuts",
      label: "Keyboard shortcuts",
      hint: "The whole key map",
      href: null,
    },
  ];
}

/**
 * The rows a section page adds.
 *
 * "Compare with the previous release point" is the entry point task B5 owes the
 * section header: `/app/diff` is otherwise three hops from the text it compares
 * (section → version history → pick two → diff).
 *
 * `releases` is the title's own release list, newest first, which the section
 * page already holds for the release switcher — so this costs no further API
 * call. It is the list of release points at which the *title* was published,
 * not the ones at which this section changed, so the redline it opens can
 * legitimately report no changes. That is what `/app/diff` says when two
 * versions match, and the row names the release point it will compare against
 * so the destination is not a surprise.
 */
export function sectionCommands(
  identifier: string,
  releases: Release[],
  selected: string,
): PaletteCommand[] {
  const commands: PaletteCommand[] = [];

  const index = releases.findIndex((release) => release.label === selected);
  // The list is newest first, so the *next* entry is the one before this in
  // time. -1 is a served release point that is not in the title's list at all,
  // which leaves the row off rather than comparing against an arbitrary one.
  const previous = index === -1 ? undefined : releases[index + 1];
  if (previous) {
    commands.push({
      id: "compare-previous",
      label: `Compare with the previous release point (${previous.label})`,
      hint: `Redline this section between ${previous.label} and ${selected}`,
      href: diffHref(identifier, previous.label, selected),
    });
  }

  commands.push({
    id: "versions",
    label: "Version history",
    hint: "Every release point at which this section's text changed",
    href: versionsHref(identifier),
  });

  return commands;
}

/**
 * What the island matches a typed query against, stamped on the row as
 * `data-label` at render time.
 *
 * The label and the id, lowercased; not the hint, which is a sentence, and
 * matching sentences makes every row match almost any word. Computed here so
 * the island's own filter is `key.includes(needle)` and nothing else — it can
 * import nothing, and a normalisation rule written twice is a rule that
 * disagrees with itself.
 */
export function matchKey(command: PaletteCommand): string {
  return `${command.label} ${command.id}`.toLowerCase();
}
