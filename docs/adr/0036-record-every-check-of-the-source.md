# ADR-0036: Poll daily, record every check, and say so on the page

**Status:** Accepted
**Date:** 2026-08-02
**Related:** [ADR-0013](0013-s3-mirror-of-record-disposable-downloader.md) (the mirror this keeps
current), [ADR-0018](0018-cache-immutably-only-when-the-release-point-is-pinned.md) (why the status
answer is not cached immutably), [ADR-0020](0020-deploy-one-ec2-box-compose-caddy.md) (the box the
schedule runs on), [ADR-0035](0035-images-from-ecr-deploys-from-actions.md) (the weekly Actions job
this demotes to a backstop)

## Context

The site mirrors a source that changes without warning. OLRC publishes a release point when it
publishes one — a few dozen times a year, on no schedule anyone can subscribe to — and everything
this site says about currency is downstream of having noticed.

Until now the noticing was one weekly GitHub Actions cron dispatching the full
`inventory → backfill → mirror push → load-all → verify` chain over SSM. Two problems, and they are
different in kind.

The first is latency: up to seven days between a release point being published and this site holding
it, for a job whose expensive part is skipped on the ~50 weeks a year when nothing changed. The check
itself is one HTTP GET of a static page.

The second is worse, and is the reason this ADR exists. **Nothing recorded that the check had
happened.** A corpus that has stopped being updated is indistinguishable, from the outside and from
the inside, from a corpus with nothing to update: every page renders, every release point carries a
real date, every answer is internally consistent. The failure mode is silence. GitHub disables
scheduled workflows on a repository with no pushes for 60 days; a `workflow_run` chain can be
disabled in a settings page; a box can lose its cron. Any of those turns this into a site confidently
serving 2026 law in 2027, with no symptom at all.

That is the specific thing a reader cannot check for themselves. They can read a release point's
date; they cannot know whether anyone has looked lately to see if there is a newer one.

## Decisions

**1. Every poll writes a `source_checks` row — including the ones that fail.** The table records
`checked_at`, the URL, whether it succeeded, how many release points the page listed, which labels
were new, the newest published, and the error if there was one. Recording the *attempt* rather than
only its result is the whole point: a failed check still proves the checker is alive, and
distinguishes "OLRC published nothing" from "we stopped asking three weeks ago". Append-only and
never pruned — at one row a day it is a few KB a year, and the history answers *when* it stopped,
which the current state cannot.

**2. Daily, not weekly, and daily is the ceiling as well as the floor.** The cadence is bounded on
both sides deliberately. Not more often than daily: the source publishes a few dozen times a year and
polling a static page harder than that is rude for no gain (CLAUDE.md's source etiquette — sequential,
~1 req/sec, descriptive UA). Not less often than weekly: that is the bound `SOURCE_CHECK_STALE_AFTER`
encodes, and past it the site stops claiming to be current and says so instead.

**3. The daily job does the cheap thing and escalates.** `python -m ingest check` fetches the page,
records the check, seeds any new release points, and signals through its exit code — `0` nothing new,
`10` new release points, `1` the check itself failed. `deploy/update-corpus.sh` runs the full
download-and-load chain only on `10`. On an ordinary day the daily cron costs one HTTP request and one
database row.

The exit code is the interface rather than JSON on stdout because the consumer is a shell script on a
box with no `jq` guarantee, and because a shell that mis-parses JSON fails open — it reads "no new
release points" out of a broken answer, which is exactly the silent-success failure this ADR is about.

**4. The weekly Actions job stays, as a `--force` backstop.** It now runs the whole chain whether or
not anything was published, so a load that half-finished or a zip that never reached the mirror is
repaired within the week rather than waiting for the next release point to expose it. Keeping both
schedules is not redundancy for its own sake: they fail independently. A disabled GitHub schedule
leaves the box's cron running; a dead `crond` leaves the weekly sweep. Neither is a backup of the
other, but between them the site does not go quietly unchecked.

**5. The daily poll writes its inventory JSON somewhere disposable.** `mirror pull` overwrites
`data/uscreleasepoints.json` with S3's copy, so a poll that wrote the canonical file would have it
clobbered by the first step of the full chain — and `backfill` would then plan from the stale list,
missing the release point the poll had just found. The poll writes a scratch file and the full chain
re-fetches for itself, in the order that has always worked.

**6. `GET /api/v1/status` reports two facts side by side, and does not collapse them.** What is
loaded here (`corpus.latest_release`, `corpus.behind_by`) and when this deployment last confirmed
that is everything published (`source.last_checked_at`, `source.stale`). A mirror can be current and
unverified, or verified and behind; those call for different responses, and a single "up to date"
boolean would have to lie about one of them. `behind_by` is `null` rather than `0` when the last check
failed — "we don't know" is not "nothing".

**7. The reader says it in a sentence, and shouts only when it should.** `/app/releases` — the page
that already answers "what exists" — carries the other half: *"Checked uscode.house.gov for new
release points 3 hours ago."* Quiet line when the answer is reassuring, USWDS warning alert when it is
not, because a status line is skimmed and an alert is a claim on attention. Being *behind* is reported
ahead of being *stale* when both are true: it is the more actionable of the two. The fetch swallows its
own errors and renders nothing on failure — a note *about* the law must never be able to take down the
law.

**8. A stopped checker is an alarm, not a thing someone notices.** The daily job publishes
`USCode/SourceCheckStale` (0 or 1) to CloudWatch, and `uscode-source-check-stale` is the one alarm in
this project with `--treat-missing-data breaching`. Everywhere else missing data means "no traffic",
which is fine. Here it means the daily job did not run at all — precisely the failure being watched
for. An alarm that went quiet when its metric disappeared would be silent for exactly the reason it
exists.

**9. The box's schedule is a file in the repository.** `deploy/install-crons.sh` writes
`/etc/cron.d/uscode` whole and is called from `bootstrap-box.sh`. The three jobs that were there
before this ADR had been typed in by hand and existed nowhere else; a rebuilt box would have come up
looking healthy in every respect except that it had quietly stopped checking for new law.

## Consequences

**Good.** New law is picked up within a day instead of within a week. "How current is this mirror"
is an answerable question — over HTTP, on the page, and to a monitor. The expensive chain still runs
only when there is something to load. A checker that stops running now produces an email rather than
nothing.

**Costs, named.**

- **Two source checks are recorded on days when something new is published** — the poll's, and the
  full chain's own `inventory` step. Both are real requests and both belong in the record; the
  alternative was threading the poll's result through `mirror pull`'s overwrite, which is the bug this
  ADR's decision 5 avoids.
- **`SourceCheckStale` is published by the same job whose failure it reports.** If the daily cron
  dies, the metric stops rather than going to 1 — which is why the alarm treats missing data as
  breaching. It does mean the signal is "no evidence of health" rather than "evidence of illness", and
  those are worth two days of grace before mailing, not none.
- **The staleness bound is a constant, not a policy someone can set.** Seven days is
  `storage.SOURCE_CHECK_STALE_AFTER`, chosen to match the weekly backstop. Changing the cadence
  without changing the constant would make the reader's warning fire routinely, which is the
  always-firing-alert failure this project already met once (`update-corpus.sh`'s verify gate).
- **`behind_by` counts release points, not law.** Most release points change a handful of titles and
  many change none that a given reader cares about. It answers "is this mirror complete", not "is the
  section I am reading out of date" — the second question is what the version timeline is for.
- **Nothing here makes the corpus load faster.** A release point that touches Title 42 still costs
  what it costs; the daily check only means the clock starts within a day.
