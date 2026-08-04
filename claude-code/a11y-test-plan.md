# Accessibility test plan — uscode.linkedlegislation.org

Standard: **WCAG 2.1 Level AA**. Section 508 conformance is claimed on top of it via the published
statement (task A10). Scope: the reader at `/app/*`, the user guide at `/app/guide`, the API docs
pages, and the error/limit pages (404, 429, appendix explanation, served-from notice).

Automated scanning catches roughly a third of AA failures. The manual protocol is not optional.

---

## 1. Automated gate (runs on every push)

| Layer | Tool | Where | Fails the build when |
| --- | --- | --- | --- |
| Rule scan | `@axe-core/playwright`, tags `wcag2a wcag2aa wcag21a wcag21aa` | `make test-e2e` | any `critical`/`serious`, or any new id/route pair not in `docs/a11y/known-violations.json` |
| Reflow / zoom | existing `make shots`, extended | 320px, 375px, 1280px, 1280px @200% | horizontal scroll at any width |
| Contrast | script over the token file | `docs/verification/contrast.json` | any pair below 4.5:1 / 3:1 as applicable, either theme |
| Payload | per-route JS byte budget | `make test-web` | budget regression (protects 2.2.x and everyone on a slow link) |
| Semantics | Vitest on rendered output | `make test-web` | missing landmark, skipped heading level, unlabelled control |

States to scan, not just initial loads: search with results, search with zero results, a preview
open, timeline expanded, redline rendered, copy control active, dark theme, `forced-colors: active`.

## 2. Route matrix

See `assets/a11y-routes.json`. Reconcile it against the guide ratchet's `covers.routes`, which is
the authoritative route inventory in this repo — if a route is not in both, one of them is wrong.

## 3. Manual protocol — run once per phase

### 3.1 Keyboard only (no mouse, no touch)
Complete each journey, recording every place focus is lost, trapped, invisible, or lands under the
sticky chrome:
1. Land on the home page → reach 16 U.S.C. § 45f → read subsection (c)(5).
2. From § 45f, compare it with the previous release point where its text changed.
3. Search a phrase → filter to one title → open the third result at a named release point.
4. Copy a provision, then copy a citation link.
5. Change theme, then reload — the choice persists and focus does not move.

Pass criteria: every journey completable; no more than 10 tab stops between two section headings
(A3); skip link is the first stop; `:focus-visible` always ≥3:1; Escape closes any transient layer
and returns focus to its trigger.

### 3.2 Screen readers
NVDA + Firefox and VoiceOver + Safari, on: a section page, a search results page, a redline, the
guide. Check specifically —
- the statute hierarchy is announced correctly from the heading tree;
- a date inside a note reads *inside* the sentence (A2);
- insertions and deletions announce as added/removed, not as unattributed text (A5);
- the release point and its currency date are reachable without hunting;
- result counts and zero-result explanations announce once, not on every keystroke.

### 3.3 Zoom, reflow, magnification
200% browser zoom at 1280px; 400% reflow at 320px equivalent; 400% screen magnifier on the section
page. The subsection indentation ladder must degrade rather than wrap into its numbers.

### 3.4 Voice control
One Dragon or Voice Control pass: every visible label matches its accessible name (2.5.3), and
"click Compare" works.

### 3.5 Motion and preference
`prefers-reduced-motion` removes sticky-chrome and timeline transitions; nothing animates for
longer than 5s without a control; no parallax.

## 4. Reporting

- `docs/verification/a11y.json` — machine output, per route, committed each run.
- `docs/a11y/known-violations.json` — every accepted exception, with owning task and reason.
- `docs/a11y/manual-YYYY-MM-DD.md` — manual run: tester, AT versions, journey outcomes, defects
  filed.
- `/app/accessibility` — the public statement, regenerated when the above change.

## 5. Sign-off sheet

A phase is accessible-done when all of: automated gate green with an empty known-violations file;
all five keyboard journeys complete unaided; both screen-reader passes with no blocking defect;
reflow clean at 320px and 200%; contrast table clean in both themes; and the conformance statement
matches the audit date.
