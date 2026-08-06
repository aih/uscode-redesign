/**
 * Every keyboard shortcut the reader has, in one list.
 *
 * The list is data because three things need it and they must not disagree: the
 * help dialog renders it, `/app/design` renders the same dialog as a specimen,
 * and `KeyboardNav`'s island receives the key → action map out of it as JSON.
 * An `is:inline` script can import nothing (the constraint `CitePreview` and
 * `CopyColumn` already work around the same way), so the alternative was a
 * second copy of the bindings written in the script — which is how a documented
 * shortcut stops being the shortcut that fires.
 *
 * `keys` is what the reader sees and `codes` is what `KeyboardEvent.key`
 * reports, because for four of these they are not the same string: `←` is
 * `ArrowLeft`, `Esc` is `Escape`.
 */

export interface Shortcut {
  /** What the island does. One `switch` arm each, in `KeyboardNav.astro`. */
  action: string;
  /** As printed in the help dialog. */
  keys: string[];
  /** As `KeyboardEvent.key` reports them. */
  codes: string[];
  /** The sentence in the help dialog. Imperative, no trailing stop. */
  what: string;
}

export interface ShortcutGroup {
  name: string;
  /** True when every shortcut in the group needs a section on screen. The
   *  dialog says so, rather than listing keys that do nothing on the page the
   *  reader is looking at. */
  sectionOnly?: boolean;
  items: Shortcut[];
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    name: "Moving between sections",
    sectionOnly: true,
    items: [
      {
        action: "previous-section",
        keys: ["←", "j"],
        codes: ["ArrowLeft", "j"],
        what: "Previous section in reading order",
      },
      {
        action: "next-section",
        keys: ["→", "k"],
        codes: ["ArrowRight", "k"],
        what: "Next section in reading order",
      },
      {
        action: "up-level",
        keys: ["u"],
        codes: ["u"],
        what: "Up to the chapter or subchapter that contains it",
      },
    ],
  },
  {
    name: "Moving inside a section",
    sectionOnly: true,
    items: [
      {
        action: "contents",
        keys: ["c"],
        codes: ["c"],
        what: "The contents list",
      },
      {
        action: "previous-provision",
        keys: ["["],
        codes: ["["],
        what: "Previous subsection",
      },
      {
        action: "next-provision",
        keys: ["]"],
        codes: ["]"],
        what: "Next subsection",
      },
      {
        action: "source",
        keys: ["s"],
        codes: ["s"],
        what: "Source credit",
      },
      {
        action: "notes",
        keys: ["n"],
        codes: ["n"],
        what: "Notes",
      },
    ],
  },
  {
    name: "Anywhere on the site",
    items: [
      {
        action: "top",
        keys: ["t"],
        codes: ["t"],
        // `#main`, which is where the skip link goes too — the top of the
        // page's content rather than of the browser window, so the sticky
        // chrome is not scrolled back into view to be scrolled past again.
        what: "Top of the page",
      },
      {
        action: "bottom",
        keys: ["b"],
        codes: ["b"],
        // The footer, which is the last thing on every page. `t` reaches
        // `#main` rather than the window's top, and this is its counterpart at
        // the other end: the end of the content, with the site's own links
        // under the keyboard when it lands.
        what: "Bottom of the page",
      },
      {
        action: "search",
        keys: ["/"],
        codes: ["/"],
        what: "Search or go to a citation",
      },
      {
        action: "help",
        keys: ["?"],
        codes: ["?"],
        what: "This list",
      },
      {
        action: "close",
        keys: ["Esc"],
        codes: ["Escape"],
        what: "Close this list, or a citation preview",
      },
    ],
  },
];

/** `{ "ArrowLeft": "previous-section", … }` — what the island switches on.
 *
 * Built here so the bindings are derived from the printed list rather than
 * written twice. A key claimed by two actions is a bug the dialog cannot show,
 * so it throws rather than letting the later one win silently. */
export function keyMap(): Record<string, string> {
  const map: Record<string, string> = {};
  for (const group of SHORTCUT_GROUPS) {
    for (const item of group.items) {
      for (const code of item.codes) {
        if (map[code]) {
          throw new Error(`Two actions bound to ${code}: ${map[code]} and ${item.action}`);
        }
        map[code] = item.action;
      }
    }
  }
  return map;
}
