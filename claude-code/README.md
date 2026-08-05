# uscode-redesign — improvement package

Prepared 2026-08-03 for `github.com/aih/uscode-redesign` (branch `main`), deployed at
`uscode.linkedlegislation.org`.

I could not open a PR — GitHub was not connected to my session and the deployed domain is not
reachable from it. Everything below is written to be run from Claude Code inside a clone of the
repo. The audit is grounded in `README.md` and `CLAUDE.md` as published on `main`; every task
starts by re-reading the files it touches, so anything I inferred wrongly gets corrected in the
first step rather than baked in.

## What's here

| File | Use |
| --- | --- |
| `00-CONVENTIONS.md` | Paste at the top of **every** session. Encodes the repo's own rules (ADR + guide + BUILDLOG duties, three test suites). |
| `prompts/A-accessibility.md` | WCAG 2.1 AA: harness, then fixes. A1 first. |
| `prompts/B-navigation-ia.md` | Navigation, release context, search relevance, cross-release compare. |
| `prompts/C-design-system.md` | Brand proposal + USWDS token layer + living style guide. |
| `prompts/D-personalization.md` | Unblocking accounts, watchlists, alerts. |
| `prompts/E-housekeeping.md` | Recorded debts that block professionalism or scale. |
| `a11y-test-plan.md` | The accessibility test plan on its own — automated gate, manual protocol, route matrix, sign-off sheet. |
| `assets/brand.md` | The proposed brand, in words and numbers. |
| `assets/_uswds-theme-overrides.scss` | Starting token file for C1. Verify names against your installed USWDS. |
| `assets/a11y-routes.json` | Route matrix the automated scan iterates. |
| `assets/links.md` | Normative references worth having open. |

## Running order

Phase 1 (measure, don't change): **A1**, **B3-measure**, **C1-audit**.
Phase 2 (fix what the measurement found): **A2–A8**, **C1–C2**, **B1–B2**.
Phase 3: **B4–B5**, **A9–A10**, **C3**.
Phase 4: **E1–E5**, then **D1–D3**.

One task per session, one worktree per task, per PLAN §7's rhythm.

## Branch and PR, by hand

```bash
git switch -c redesign/a11y-and-design-system
# … run a task …
make test && make test-web && make test-e2e
git push -u origin redesign/a11y-and-design-system
gh pr create --fill --base main
```

Keep one branch per workstream (`redesign/a11y`, `redesign/nav-ia`, `redesign/design-system`) so
review stays readable. The design-system branch will touch nearly every template; land it after
the accessibility fixes, not before, or you will re-audit everything.
