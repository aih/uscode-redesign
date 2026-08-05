# Session preamble — paste this above any task prompt

You are working in `aih/uscode-redesign`. Read `CLAUDE.md` first and treat it as binding. In
particular:

1. **Architecture rules are not negotiable.** API and reader talk only to the `Repository`
   interface; no raw SQL in handlers; no USLM element names outside a parser or
   `frontend/src/lib/uslm.ts`; every reader href goes through `frontend/src/lib/url.ts`.
   `tests/test_architecture.py` enforces this — if your change needs to break it, stop and write
   an ADR proposing the change instead.
2. **Three suites are required.** `make test` (Python), `make test-web` (Vitest),
   `make test-e2e` (Playwright). Nothing is done until all three are green. Do not add a fourth
   test runner.
3. **Documentation duties (PLAN §11).** A consequential decision gets a short ADR in `docs/adr/`,
   including the cost you are accepting. A user-visible change updates the matching chapter in
   `frontend/src/pages/guide/*.md` **in the same session**, with a ```scenario``` block where you
   are making a behavioural claim — the guide ratchet in `frontend/tests/guide.test.ts` will fail
   `make test-web` otherwise. End the session with a `BUILDLOG.md` entry: date, model, what was
   asked, what was decided, commits, what was verified and the command to re-check it.
4. **Scenario blocks must be answerable from the CI fixture corpus** (Title 16 at `119-99` and
   `119-102not101`) unless marked `data: corpus`.
5. **Small commits, imperative messages, preserve `Co-Authored-By` trailers.**
6. **Don't invent numbers.** Any count or measurement you state in docs must come from a command
   someone else can re-run, and the artifact goes in `docs/verification/`.
7. **Scope discipline.** Do exactly the numbered task. If you find an adjacent defect, write it
   down at the end of the BUILDLOG entry as a candidate task; do not fix it in the same commit.

Style for anything user-facing you write: plain, specific, no marketing voice. This audience
drafts statutes for a living.
