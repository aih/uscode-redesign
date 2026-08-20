# ADR-0033: A copy control per provision, with four modes and a server-computed citation

**Status:** Accepted
**Date:** 2026-07-31
**Related:** [ADR-0022](0022-uswds-retained-no-client-framework.md) (why this is an island and not a component),
[ADR-0023](0023-citations-parse-server-side-to-an-identifier.md) (the parser this inverts)

## Context

Reading a provision and *using* it are different jobs, and until now the site only did the first.
Getting `16 U.S.C. § 45f(c)(5)` and its text out of this reader meant selecting across an indented
DOM, pasting, and then writing the citation by hand from the breadcrumb.

Congress.gov solves this with a column of copy icons beside the text. The idea is right. What it
does not do is let you choose *what* copy means without going somewhere else, and "copy this
provision" genuinely means four different things depending on what is being written:

| | wanted by |
|---|---|
| the words | someone quoting |
| the citation | someone footnoting |
| citation + text | someone drafting a brief |
| a link | someone sending it to a colleague |

## Decision

**A control beside every identified provision, a mode toggle above them, and modifier keys for
the exception.**

- Targets come from `uslm.copyableIdentifiers` — elements that are both a `LEVEL_TAGS` container
  *and* carry an `@identifier`. Not every identified element is a provision; `<num>` and
  `<content>` can carry identifiers, and a button on a paragraph's number an inch from the one on
  the paragraph is two controls doing nearly the same thing.
- The section itself gets a named **"Whole section"** button in the bar rather than a gutter icon,
  because in the gutter it lands on the same line as the first subsection's.
- The mode is a `<select>`, persisted in `localStorage` — **never a cookie**, for ADR-0027's
  reason: a cookie would put `Vary: Cookie` on the whole cached reader to remember a preference
  about the clipboard.
- **Shift / Alt / Ctrl-or-⌘ override the toggle for one click only.** The toggle is what the
  reader set; the modifier is the exception they are making now. Writing the modifier back to
  storage would silently redefine "set".
- **Link mode writes a `text/html` flavour as well as `text/plain`**, so pasting into anything
  rich yields a real hyperlink labelled with the citation instead of a bare URL. This is the one
  thing here Congress.gov's version does not do, and the one most often wanted.

**Every citation and URL is computed on the server**, by `lib/cite.ts` and `lib/url.ts`, and
shipped to the island as a JSON block. The island does DOM insertion and clipboard writes and
nothing else.

That split is the load-bearing part of this decision. An `is:inline` island cannot import a
module, so anything it computes is untestable by construction — and citation formatting is
exactly the part worth testing, because a citation that this site cannot resolve is worse than no
copy button: it looks right. `formatCitation` is the inverse of `citeparse.py`, and the round
trip is checked from both ends (`frontend/tests/cite.test.ts` and `tests/test_citation_forms.py`).

## Alternatives rejected

**A bundled `<script>` importing `lib/cite.ts` directly.** Would let the island import, at the
cost of being the first non-inline island on a site whose eight others are all inline (ADR-0022).
Shipping the finished strings gets the same testability without the precedent.

**Rendering the buttons server-side into `lib/uslm.ts`'s output.** Would put a feature into the
sole presentation layer, break every renderer snapshot, and ship controls that do nothing where
there is no JavaScript — there is no non-scripted way to write to the clipboard.

**A fixed left column, as Congress.gov has.** A provision is indented by its depth, so a fixed
column leaves a four-deep clause's button an inch and a half from the clause, with three other
buttons between. Hanging each control off its own provision puts it where the thing it acts on
starts, in indent whitespace that was already empty.

**Hover-to-reveal.** The usual treatment, and it hides the feature from anyone who does not
already know it is there. The controls sit at 45% opacity always.

## Consequences

- **A long section adds ~100 stops to the tab order.** Real, and the alternative —
  `tabindex="-1"` — makes the feature mouse-only, which is worse. Recorded rather than solved.
- Copied text **omits notes and the source credit**: they are the section's apparatus, not part of
  the provision, and a brief does not want a section's amendment history pasted under a
  subsection. They remain on the page and remain selectable.
- Text is reconstructed by walking the DOM, not from `innerText`, because `innerText` includes or
  excludes the notes depending on whether their `<details>` happens to be open — which would make
  what lands on the clipboard depend on the width of the screen.
- A designator and its sentence are joined onto one line, because `<content>` renders as a `<p>`
  and the Code prints `(1) assure the preservation…` as one line.
- `navigator.clipboard` needs a secure context, so this does nothing over plain HTTP on a
  non-localhost hostname. It fails with a message rather than silently.
- The island runs on `DOMContentLoaded`, not inline. It is rendered *above* the text it decorates,
  so at inline-execution time none of its targets are parsed — which it shipped with for one
  build, silently doing nothing with no error anywhere. `frontend/tests/e2e/copy.spec.ts` exists
  mostly to catch that class of failure.

## Addendum (2026-08-19): the bar and the gutter are opened by different conditions

The island revealed the bar only after injecting at least one gutter button (`if (injected === 0)
return`), so a section with no identified subdivision showed no copy control at all — not even the
"Whole section" button this ADR put in the bar precisely because the section has nowhere to sit in
the gutter. The button was built, wired and holding a correct citation; it was inside an element
that was never un-hidden.

That is not an edge: 2,791 of the 5,028 sections in `samples/uslm2/USLM2/usc16.xml` and 32 of the
39 in `usc01.xml` carry no identified `LEVEL_TAGS` descendant, so the majority of section pages
offered no way to copy anything.

Now `.copycol` is revealed whenever there is a target, and `has-copy` — the class that opens the
1.75rem gutter — is added only when a button was injected into it. A section with no subdivisions
gets the bar and keeps the full reading measure. `frontend/tests/e2e/copy.spec.ts` covers the
shape at `/app/us/usc/t16/s21`, where the assertions are the two conditions apart: the whole-section
button visible, `.copybtn` and `.section-body.has-copy` both absent.
