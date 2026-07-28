# ADR-0012: A resumable backfill driven by `titlesAffected`, verified by hash-dedupe

**Status:** Accepted — 2026-07-28 (Session 6)
**Context:** PLAN.md §9.10 (gotcha 10), §11.4–11.5; CLAUDE.md "External source etiquette";
docs/prior-art.md §1; ADR-0007 (content dedupe at ingest). Ports
[`loadusc-xcitedb/loadusc/downloadusc.py`](https://github.com/dreamproit/loadusc-xcitedb)
@ `d16f1ee` into `ingest/`.

## The problem the original solved, and the one it didn't

`downloadusc.py` already knew the two things that are genuinely hard about this: how to turn
an OLRC release-point label into a per-title zip URL, and that `titlesAffected` — not the
full title list — is what to download. Those are load-bearing and are kept.

What it has no answer for is duration. The corpus is ~3,200 files and tens of gigabytes over
a link deliberately held to ~1 req/sec; a full run takes hours and will be interrupted. The
original's only memory is `os.path.exists(dir_name)` at *directory* granularity
(`downloadusc.py:86`), so an interruption halfway through a release point leaves a directory
that looks complete, and a run that is genuinely half-finished either re-fetches everything
or silently skips what it never got.

## Decision

Three modules, splitting transport from orchestration:

- **`ingest/download.py`** — `fetch_zip` does one GET: streamed to a `.part` file, hashed on
  the way through, validated with `zipfile.is_zipfile`, bounded retries with exponential
  backoff. It **returns a result rather than raising**, because "this title does not exist at
  this release point" is an answer to record, not an error that should abort a 3,200-file run.
- **`ingest/backfill.py`** — the plan, the ledger, the runner, the verification.
- **`python -m ingest backfill` / `verify-downloads`** — the CLI, unattended-friendly.

### `titlesAffected` is the plan, plus a baseline

Measured against the seeded inventory: **3,197 downloads instead of 22,156** (382 release
points × 58 titles), an 85.6% reduction.

The 58 titles are derived from the data — the union of every `titlesAffected` in the
inventory — not hard-coded. It comes out as the 53 numbered titles that exist (there is no
Title 53) plus the five appendix titles `05a`, `11a`, `18a`, `28a`, `50a` that gotcha 7 calls
out as separate files. A title that never changed across the whole inventory would be
invisible to this; none exists today, and the verification report prints the baseline's title
count so a future gap shows up instead of passing silently.

**The oldest release point is fetched in full.** `titlesAffected` describes a delta, and a
delta needs something to apply to. This is also precisely what makes gotcha 10's *retrieval*
rule true: a request for a release point that was never ingested is answerable from the
newest ingested release point at or before it — which holds only if some earlier release
point has the title at all. The original intended this (`downloadusc.py:265-266`) but its
implementation reads `url` and `dir_name` from leftover loop variables that refer to
different release points, so the oldest RP's files land in the wrong directory
(docs/prior-art.md §1). Here it is an explicit `baseline=True` flag on the task, carried into
the ledger.

Tasks are ordered oldest-first, so an interruption leaves a *prefix* of history complete
rather than a scatter, and the baseline always lands before anything that depends on it.

### The ledger is a cache; the disk is the truth

Every outcome goes to `data/releases/ledger.json` — status, URL, sha256, bytes, HTTP status,
attempts, `baseline`, timestamp — written in full through `os.replace`, which is atomic on
POSIX, so it is never observed half-written.

The rule that makes this safe: **a missing ledger entry never means a missing file.** On
resume, a zip on disk with no entry is re-hashed and adopted. A ledger deleted, corrupted, or
lost to a `kill -9` therefore costs one hashing pass, not a re-download of tens of gigabytes.
Verified by test — and in the live trial, `119-99/16` from an earlier session was adopted
with zero requests.

### Three outcomes, not two

| status | meaning | on re-run |
|---|---|---|
| `ok` | valid zip on disk | skipped |
| `unavailable` | the server answered, and the answer is there is no such file | skipped unless `--retry-unavailable` |
| `failed` | transport or 5xx, retries exhausted | retried |

Keeping `unavailable` and `failed` apart is the point. Only `unavailable` is a statement about
what OLRC publishes; only `failed` says nothing and is worth re-asking. Collapsing them either
re-asks 3,000 settled questions every run — the impoliteness the etiquette rule exists to
prevent — or permanently gives up on a title because of one reset connection.

A 404 settles immediately with no retry. An HTTP 200 whose body is not a zip is
uscode.house.gov's HTML error page; it gets one confirming retry to cover a truncated
transfer, then becomes `unavailable`.

### Hash-dedupe is the verification step

Content dedupe proper happens at ingest, over guid-stripped section text (ADR-0007). These
zips would never collapse anyway — guids regenerate per release point and zip members carry
timestamps — so hashing them saves no storage. It is used here for what identical bytes across
two *different* `(release, title)` pairs actually prove:

- **Same title, different release points, identical bytes.** OLRC listed the title in
  `titlesAffected` and republished it unchanged. Reported, not failed — a finding about the
  source. It is also the signature of the `u1` hazard: `118-22` and `118-22u1` are *different*
  release points with different files, and if their zips ever hash alike, one label is being
  served the other's content.
- **Different titles, identical bytes.** Two distinct titles cannot share a zip. This means
  URL construction collapsed two addresses into one — the most plausible way this downloader
  breaks, since every URL is built by string substitution on a label. **Fails the report.**

`--deep` re-hashes every file on disk rather than trusting the ledger, which is what makes
`docs/verification/downloads.json` a reproducible artifact rather than a restatement of what
the downloader already believed (documentation duty 5).

## Reused from `loadusc-xcitedb`

- `titlesAffected` drives the per-release title list (`downloadusc.py:87`).
- Zip URL construction, and title-number normalization — lowercase, zero-pad to two digits
  ignoring a trailing `a`, so `5` → `05` and `18A` → `18a` (`:88-93`). Already in
  `ingest/inventory.py` from Session 3.5; the backfill builds every URL through it.
- `zipfile.is_zipfile` on the body as the validity check, because a 200 is not proof (`:95`).
- Cache on disk, never re-download (`:86`) — kept, at file rather than directory granularity.
- The intent that the oldest release point needs every title (`:265-266`).

## Changed, and why

- **Resumable at file granularity**, via a persisted ledger with adoption-from-disk. The
  original had no memory beyond a directory's existence.
- **Streaming and constant-memory.** The original held each zip in memory twice —
  `io.BytesIO(r.content)` to test it, again to extract (`:95`, `:111`). Title 42 is multiples
  of Title 16 (gotcha 6) and this has to survive it.
- **`unavailable` vs `failed` distinguished**; the original retried everything, including
  404s, up to 20 times with no backoff and no sleep (`:97-108`).
- **No silent `u1` fallback.** The original, failing to get `…u1.zip`, retries the URL with
  `u1` stripped (`:99-102`) and stores the result under the `u1` label — a *different* release
  point's content filed under this one. Both labels are separate rows in our inventory and get
  fetched on their own, so the fallback is not merely risky here, it is wrong. We record
  `unavailable`, and gotcha 10's retrieval rule degrades gracefully. Verification flags the
  collision if it ever appears anyway.
- **TLS verification stays on.** The original disables certificate verification for
  uscode.house.gov globally and suppresses the warning (`:42-64`). The certificate validates;
  if that changes we pin a CA rather than stop checking.
- **Throttling, User-Agent, backoff** are enforced in the transport layer where no caller can
  forget them, rather than being absent.
- **Every outcome is recorded with a hash**, feeding both the verification report and the
  provenance manifests (documentation duties 4 and 5). The original produced no provenance.
- **Nothing is downloaded to be thrown away**: zips are kept, and extraction stays a separate
  step, so the corpus is not doubled on disk.

## Consequences

- A full backfill is one unattended, interruptible command:
  `uv run python -m ingest backfill`, re-run to resume, `--limit` for a trial.
- Two `docs/verification/` artifacts now have a producer; `make verify` (Day 7) can call
  `verify-downloads --deep` as one of its checks.
- Storage is bounded by what actually changed, but **not** deduped at the zip level, by
  design — that is ingest's job over section content, and doing it twice would only mean
  keeping fewer of the published artifacts a sceptic re-downloads to check us.
- The ledger is per-corpus, not per-release, so it is one file to inspect and one file to
  lose harmlessly. It is gitignored with the rest of `data/`.
- `download_title_zip` keeps raising on failure — the interactive single-title path still
  wants to fail loudly. Only the bulk path records and continues.
