# Deployment status — uscode.linkedlegislation.org

Live state of the demo deployment and what is still owed. Design lives in
[ADR-0020](adr/0020-deploy-one-ec2-box-compose-caddy.md) and
[ADR-0035](adr/0035-images-from-ecr-deploys-from-actions.md); the runbook is
[deploy.md](deploy.md). This file is the *current* picture — delete it once the site is
settled and the interesting parts have moved into deploy.md.

**Last updated:** 2026-08-02, second session — the alarm-email diagnosis and ADR-0036's daily check.

## The box

| | |
|---|---|
| Instance | `i-06b433caacd78fd96`, t4g.large, us-east-1 |
| Elastic IP | **52.1.30.78** |
| Security group | `sg-028b6e6362978d1c3` — 80 and 443 only, no SSH |
| Access | SSM only (`aws ssm start-session --target i-06b433caacd78fd96`) |
| Volumes | 20 GB root + 120 GB gp3 at `/var/lib/uscode` (`DeleteOnTermination=false`) |
| Repo on box | `/home/ec2-user/uscode-redesign`, `.env` beside it (mode 600, secrets generated on the box) |
| Logs | `/var/lib/uscode/logs/` — `deploy.log`, `backup.log`, `purge.log` |
| AWS profile | `uscode-admin` = IAM user `linkedlegislation-deploy` |

## The site is live

`https://uscode.linkedlegislation.org` — DNS in Route 53 (Namecheap delegates the zone to AWS),
certificate issued by Let's Encrypt on the first attempt after the record appeared. Smoke-tested
against the live host:

| check | result |
|---|---|
| TLS | verified, `CN=uscode.linkedlegislation.org`, issuer Let's Encrypt |
| `/health` | 200 in 0.61 s |
| citation URL, `Accept: text/html` | 200 → `/app/us/usc/t16/s45f/c/5?date=…` (the reader) |
| citation URL, `Accept: application/json` | 200 → `/api/v1/us/usc/t16/s45f/c/5` |
| reader content | `§ 45f Mineral King Valley addition authorized · 119-102not101` |
| search | real corpus — "conservation" returns `/us/usc/t16/s3831` "Conservation reserve" |
| cache, pinned (ADR-0018) | `public, max-age=31536000, immutable` |
| cache, unpinned | `public, max-age=300` |
| CSP / HSTS / nosniff / frame-deny (ADR-0030) | all present |
| diff rate limit (ADR-0029) | burst served, then `429` with `Retry-After: 4`, then recovery |

**`HEAD` returns 405 where `GET` returns 200** on `/api/v1`, live — CLAUDE.md's recorded debt,
confirmed rather than discovered. It matters the moment a CDN or uptime monitor is put in front,
because both probe with HEAD by default.

## What is left for you

**One thing, still: confirm the alarm email.** Checked on 2026-08-02 and the topic reads
`SubscriptionsConfirmed: 0, SubscriptionsPending: 1, SubscriptionsDeleted: 1` — **nobody has ever
received an alarm from this site.** The `Deleted: 1` is the first confirmation link expiring: AWS
drops an unconfirmed subscription after three days, so "I'll click it later" silently became "I need
a new one". A fresh confirmation was sent to `arihershowitz@gmail.com` on 2026-08-02 at 16:00 UTC.

It comes from `no-reply@sns.amazonaws.com`, subject **"AWS Notification - Subscription
Confirmation"**, and Gmail files it under Promotions or Spam as often as not. It expires in three
days.

Check that it took, and re-send it if it lapsed again:

```bash
AWS_PROFILE=uscode-admin bash deploy/alerts-status.sh
# and if it says nobody is receiving them:
ALERT_EMAIL=arihershowitz@gmail.com RESEND=1 AWS_PROFILE=uscode-admin bash deploy/alerts-status.sh
```

That script exists because of this failure: five alarms wired to a real topic look identical whether
or not anyone is subscribed, so the broken state was indistinguishable from the working one. It exits
non-zero when nothing is confirmed. Prove delivery once it is:

```bash
aws cloudwatch set-alarm-state --alarm-name uscode-status-check-failed \
  --state-value ALARM --state-reason 'testing delivery' --region us-east-1
```

**One IAM re-run needs an admin profile (not the deploy user).** `deploy/admin-grant.sh` now grants
`sns:ListSubscriptionsByTopic` and `sns:GetSubscriptionAttributes`, and moves `sns:ListTopics` to
`Resource: "*"` — that call is account-wide and does not support resource-level permissions, so
scoping it to `uscode-*` denied it outright, which is how the diagnosis above started with an
`AccessDenied` for a permission the policy appeared to grant. Re-run it (idempotent; it adds a new
policy version) to pick that up:

```bash
AWS_PROFILE=<admin> bash deploy/admin-grant.sh
```

All five alarms exist and point at the topic. Four read `OK`; **`uscode-cpu-credits-low` reads
`ALARM`, and that is the alarm being right rather than a fault** — a t4g.large earns CPU credits
while idle and spends them under load, and this box spent a night restoring 22 GB and indexing half
a million documents. It should clear now that it only serves pages. If it is still in alarm after a
quiet day, that is the signal the instance is undersized for what is being asked of it.

Everything else that needed a human is done: the Route 53 A record exists, Caddy holds a
certificate, and #17 and #18 are merged — so the reindex streaming fix is baked into the running
image rather than copied into a container.

## What is already done

- **Provisioned**: security group, instance, Elastic IP, instance profile `uscode-site`,
  IMDSv2 with `HttpPutResponseHopLimit=2`.
- **IAM**: group `uscode-deploy` + policy, role `uscode-site`, GitHub OIDC provider, role
  `uscode-github-deploy`; repo variable `AWS_DEPLOY_ROLE_ARN` set.
- **ECR**: `uscode-api` and `uscode-frontend`, with lifecycle policies (untagged expire after 7
  days, keep the 10 most recent).
- **Images**: built for arm64 by Actions and pushed; the stack runs them.
- **Stack up**: api, db, opensearch, frontend, proxy — all healthy, migrations applied.
- **Alarms**: five on the `uscode-alerts` topic — CPU, CPU credit balance, status check, network
  out, disk. CloudWatch agent installed and publishing disk and memory.
- **Crons** (`/etc/cron.d/uscode`): nightly `pg_dump` to `s3://uscode-mirror-dreamproit/usc/db/`
  at 04:17 UTC, and the weekly `purge_login_failures` that nothing had ever scheduled. Both were
  typed in by hand and existed nowhere else; they are now written by **`deploy/install-crons.sh`**,
  which `bootstrap-box.sh` calls, so a rebuilt box arrives with its schedule instead of arriving
  without one and looking fine. The daily source check joins them there (ADR-0036) — **run that
  script once on the box to pick it up**, since `deploy-on-box.sh` does not touch `/etc/cron.d`.
- **Repo is public** — the box clones it with no credentials. Verified beforehand that no
  secrets are in the tree or in any of the 206 commits of history.

## Where the corpus stands

**Restored and verified.** The seed dump (2.33 GB compressed) was uploaded to
`s3://uscode-mirror-dreamproit/usc/db/uscode-2026-08-01.dump` and restored in 24 minutes with
`pg_restore -j 3`, no errors. Every count matches CLAUDE.md exactly:

| | on the box | expected |
|---|---|---|
| titles | 58 | 58 |
| release points | 382 | 382 |
| distinct sections | 65,938 | 65,938 |
| `section_versions` | 489,738 | 489,738 |
| `section_release_map` | 5,466,652 | 5,466,652 |
| `guid_map` | 96,185,732 | 96,185,732 |
| title-releases | 3,153 | 3,153 |
| `structure_nodes` | 9,916 | — |

`users` and `auth_sessions` are both **0**, so the account exclusion did what it was meant to.
Alembic reports `a2f0edc8f5e2 (head)` and migrated nothing, which is the check that the dump was
taken on the same schema the running image expects. On disk: 22 GB, smaller than the 27 GB the
development database occupies because a fresh restore carries no dead tuples.

**That dump deliberately excludes the accounts tables.** The local database held 1,301 users and
1,343 sessions left over from test runs, and ADR-0034 turned accounts off in the *reader* only —
`POST /api/v1/auth/signup` and the login routes still answer a direct caller — so restoring them
would have put test credentials on the public site. Schema comes across, rows do not. This does
**not** apply to the nightly backup cron, which dumps everything because restoring production
should restore real accounts.

Worth knowing for next time: `docker-compose.prod.yml` tunes `shared_buffers` and `work_mem` but
leaves `maintenance_work_mem` at Postgres's 64 MB default, and the restore spends most of its wall
clock building one index — `guid_map`'s primary key over 96,185,732 rows — inside that budget. On
an 8 GB box a few hundred MB would be safe and would cut it substantially. Not changed mid-restore,
because the setting is read per session and altering it would have meant interrupting the job to
gain time on a job already running.

## Search index

**Current text is built and live: 65,938 documents in `uscode_sections`, 9,916 in
`uscode_structure`.** A query for "conservation" returns 199 hits (`/us/usc/t16/s2903`
"Conservation plans", `/us/usc/t16/s3831` "Conservation reserve"). That retires CLAUDE.md's
"4,000-document smoke slice" debt for the deployed box — dev is unchanged.

**The `--all-versions` pass (490k superseded docs) does not fit in memory.** It was OOM-killed
twice, at 3.28 GB and 3.46 GB resident, while OpenSearch held 2.5 GB and Postgres 1.1 GB of the
box's 7.8 GB. The failure looks like it dies indexing structure nodes; it does not. The node
counter prints with `flush=True` and the later lines do not, so with output redirected to a file
everything after the last flush is lost when `SIGKILL` lands — the process was well into the
section pass.

What it is actually doing there is buffering the whole result set: `_all_version_query()` selects
`SectionVersion.xml` across 489,738 rows, which is the ~3.5 GB the code's own comment says `.all()`
would cost, and the observed RSS matches it. **So `yield_per` is not streaming from the server
here** — worth fixing in `ingest/reindex_search.py` (a real server-side cursor, or chunking by
`first_release_id`), because the same buffering will bite any future full reindex regardless of box
size.

**Fixed, not worked around.** `session.execute(stmt).yield_per(n)` calls `yield_per` on the
*Result* — by then the query has run and psycopg has buffered every row. Passing it as an execution
option on the statement is what opens a server-side cursor. Measured against the full local corpus:

| rows | before | after |
|---|---|---|
| 20,000 | 562 MB | 258 MB |
| 40,000 | 996 MB | 281 MB |
| 60,000 | 1,020 MB, still climbing | 283 MB, flat |

The whole patched `_index_sections` over 80,000 rows peaks at 448 MB. The fix is in **PR #18**
(`ingest/reindex_search.py`), with all 475 tests passing.

Two things were done to the box along the way and both should stay:

- **A 6 GB swapfile** at `/var/lib/uscode/swapfile` (in `/etc/fstab`, `vm.swappiness=10`). The box
  had none, so any job peaking above free RAM was a kill rather than a slowdown.
- **The instance was stopped and started.** With swap in play the runaway process thrashed instead
  of dying, which starved the SSM agent to `ConnectionLost` — the box was healthy to EC2 and
  unreachable to everything else. `ec2:RebootInstances` is **not** in the deploy policy (only
  Start/Stop), which is worth adding. Everything came back on its own: containers restarted, swap
  remounted from fstab, the Elastic IP stayed attached.

The patched file was copied into the running container (`docker cp`), since the fix is not merged
yet. **Merging #18 and letting deploy.yml rebuild the image is what makes it permanent** — the
copy is lost the next time the container is recreated.

**Done — the whole corpus is indexed, superseded text included.**

| | |
|---|---|
| `uscode_sections` total | **489,578** |
| — `is_current: true` | 65,929 |
| — `is_current: false` | 423,649 |
| `uscode_structure` | 9,916 |
| "conservation" | 2,227 hits (199 against current text alone) |

Two gaps, both expected and both the same cause. The pass reports `Finished SectionVersions
(489,738)` while the index holds 489,578, and the current-text subset is 65,929 against 65,938
sections in the database — **160 and 9 short respectively**. That is ADR-0021: where the source
publishes several elements under one `@identifier` at one release point, they collapse onto a
shared OpenSearch `_id` and the index keeps one of them. CLAUDE.md already records this as a known
cost of the search design, and the arithmetic here is consistent with it rather than with anything
having gone wrong in the run.

Peak swap use across the whole 490k pass: **9 MB**. Before the streaming fix the same work was
being killed at 3.4 GB resident.

**Everything that killed the superseded pass after the streaming fix was this project's own deploy
pipeline, not memory.** Each documentation push to `main` went green in CI, which fired
`deploy.yml` on `workflow_run`, which ran `deploy-on-box.sh`, which runs `docker compose up -d` —
recreating the `api` container and killing the `docker compose exec` running inside it. The
correlation is exact:

| deploy.yml run | reindex died |
|---|---|
| 12:24:20–12:25:40 | 12:25:00 |
| 12:29:15–12:30:55 | container churn at 12:30:09 |
| 12:36:48–12:38:07 | 12:37:26 |

The evidence that it was never memory: `systemd-oomd` inactive, nothing in `dmesg`, the api
container's cgroup reporting `oom_kill 0`, memory pressure at zero — and the container's
`StartedAt` matching the moment of death, with dockerd logging `hasBeenManuallyStopped=true`.

**This is exactly the cost ADR-0035 records** — "a deploy that recreates the `api` container
mid-update kills whatever `update-corpus.sh` was running inside it" — met in the wild, with a
reindex standing in for the corpus update. The operational rule it implies: **do not push to
`main` while a long job is running on the box**, or run that job somewhere a deploy does not
recreate. The weekly update inherits the same exposure and the same recovery, which is that
its work is resumable.

Two of my own missteps along the way, recorded because the reasoning was wrong and not just the
outcome. I put a `MemoryMax=2G` on the systemd unit as a backstop and then blamed it for a kill:
it constrains the compose client rather than the Python inside the container, so it never
protected what I intended *and* was not the culprit. And running the pass as
`--recreate --all-versions` meant a failure half way left **no working search** rather than a
partial one — `--recreate` drops the index first. The current-text index was rebuilt on its own to
restore service, and the pass now runs **additively** (`--all-versions`, no `--recreate`); the two
passes share document ids, so it tops the index up and a failure leaves working search behind.
That worked: the run killed at 94,500 left 156,440 documents serving. Check it with:

```bash
systemctl status uscode-reindex.service
tail -f /var/lib/uscode/logs/reindex-all.log
```

**Nothing is outstanding here.** `?release=` search now reaches back through superseded text. If a
future full reindex is ever needed, run it when nothing is deploying, and additively unless a
mapping change forces `--recreate`.

## How the corpus keeps up (ADR-0036)

**Daily poll on the box, weekly full sweep from Actions.** The box's cron runs
`deploy/update-corpus.sh` with no arguments at 06:41 UTC: one request to
uscode.house.gov's release-points page, one `source_checks` row, and — on the ~360 days a year when
OLRC has published nothing — nothing else. When the poll finds a release point this box has not seen
(`python -m ingest check` exits 10) it runs the whole download-and-load chain there and then, so new
law is picked up within a day rather than within a week.

The weekly Actions job now dispatches `--force`, which makes it the backstop rather than the primary
schedule: it runs the full chain whether or not anything was published, so a load that half-finished
or a zip that never reached the mirror is repaired within the week. The two schedules fail
independently — a disabled GitHub schedule leaves the box's cron running, a dead `crond` leaves the
weekly sweep — which matters because GitHub disables scheduled workflows on a repository with no
pushes for 60 days.

**Every check is recorded, including the failures.** That is the point rather than a detail: a corpus
that has stopped being updated looks exactly like a corpus with nothing to update, from the outside
and from the inside. `GET /api/v1/status` reports when the site last looked and what it found, and
`/app/releases` says it in a sentence. Past seven days without a successful check the site stops
claiming to be current and shows a warning instead, and `USCode/SourceCheckStale` alarms — with
`treat-missing-data breaching`, uniquely among these alarms, because a checker that has stopped
publishes nothing at all.

## The weekly sweep is proven

Dispatched by hand before it can fire unattended on a Monday, and it now runs green end to end:

```
mirror pull   1m18s
inventory     refreshed from uscode.house.gov
backfill      planned 3197: 0 downloaded, 3197 skipped, 44 unavailable
mirror push   nothing new to send
load-all      planned 3153: 0 loaded, 3153 skipped
verify        6 count mismatches (ADR-0021, expected), 0 source, 0 incomplete
```

**`0 downloaded, 3197 skipped` is the whole point of the `mirror pull` fix.** Without it this box —
seeded from a dump rather than by `load-all` — had no ledger and no zips, so backfill would have
planned the entire corpus: 3,197 files at one request per second against uscode.house.gov, 40-50
hours, for files the mirror already held.

**The first run failed, and the failure was mine.** `ingest verify` exits non-zero whenever
`report.sound` is false, and sound is false if there are *any* count mismatches — of which this
corpus always has exactly six (ADR-0021, recorded in CLAUDE.md, deliberately reported rather than
smoothed away). Gating the weekly job on that exit code would have failed it every week forever
while nothing was wrong, which is worse than not checking at all: an alert that always fires is an
alert nobody reads. The gate is now `source_mismatches` and `incomplete_loads` — the two fields
that mean something is actually wrong — with `count_mismatches` printed rather than gated on.

## Still owed

Everything this list used to hold is done. `ingest verify` passes on the box (3,153 title-versions
across 381 release points and 58 titles; 91.0% dedupe; the six count mismatches are exactly the
ADR-0021 ones CLAUDE.md documents — `113-296not287/54`, `114-329/10`, `115-8/10`, `117-80/19`,
`117-110not103/19`, `117-111not103/19`; report at `docs/verification/database.json` **on the box**,
not committed from there since the repo copy is the development corpus's). The smoke tests ran
against the live host — the table at the top of this file *is* their result. `deploy.yml` has run
green on `workflow_run` a dozen times, which is the automated path proving itself. `update-corpus.yml`
ran green on `workflow_dispatch`.

What is genuinely outstanding is above: **the alarm subscription**, and the admin re-run of
`admin-grant.sh`.

Two things need doing **on the box** the first time this session's changes deploy, and neither is
automatic:

```bash
# 1. The daily source check's cron (ADR-0036). deploy-on-box.sh does not touch
#    /etc/cron.d, so the schedule lands only when this is run once:
sudo bash /home/ec2-user/uscode-redesign/deploy/install-crons.sh

# 2. The staleness alarm, which is new in deploy/alarms.sh:
ALERT_EMAIL=arihershowitz@gmail.com bash deploy/alarms.sh i-06b433caacd78fd96
```

Prove the check itself before trusting the schedule — it is one HTTP request and it should say
`nothing new since the last check`:

```bash
cd /home/ec2-user/uscode-redesign && bash deploy/update-corpus.sh --check-only
curl -s https://uscode.linkedlegislation.org/api/v1/status
```

The smoke block, kept because it is the copy-paste version and every line should be checked against
what it *should* say, not just that it returned:

   ```bash
   SITE=https://uscode.linkedlegislation.org

   # The demo URL end to end: the citation redirector into the reader (PLAN §10).
   curl -sL -o /dev/null -w '%{http_code} %{url_effective}\n' \
     -H 'Accept: text/html' "$SITE/us/usc/t16/s45f/c/5?date=07/12/2026"

   # Same URL, JSON — should land on /api/v1 rather than the reader.
   curl -sL -o /dev/null -w '%{http_code} %{url_effective}\n' \
     -H 'Accept: application/json' "$SITE/us/usc/t16/s45f/c/5"

   # ADR-0018: pinned is immutable, unpinned is five minutes.
   curl -sI "$SITE/api/v1/us/usc/t16/s45f?release=119-102not101" | grep -i cache-control
   curl -sI "$SITE/api/v1/us/usc/t16/s45f"                        | grep -i cache-control

   # Search over the real corpus, not a smoke slice.
   curl -s "$SITE/api/v1/search?q=conservation" | head -c 300

   # ADR-0029: the diff budget is the tightest in the project, so this should
   # start returning 429 with a Retry-After rather than collapsing.
   for i in $(seq 1 8); do
     curl -s -o /dev/null -w '%{http_code} ' \
       "$SITE/api/v1/diff/us/usc/t16/s45f?from=119-99&to=119-102not101"
   done; echo
   ```

   Known-good anchor from CLAUDE.md: `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` ↔
   `/us/usc/t16/s45f/c/5`.

## Known debts this deployment did not create

- **USWDS mono fonts 404 on every page.** Six `@font-face` rules point at `/app/uswds/fonts/`,
  which has never shipped; the family is referenced by `.usa-input`, `.usa-select` and the
  checkbox/radio labels, so the search box triggers it everywhere. Fix by shipping the woff2
  files or by changing `$theme-font-type-mono` deliberately and *looking* at the result — an
  earlier attempt to do the latter was reverted because it silently changed how form controls
  render (commit `7eed41d`).
- **`make test-slow` has never passed in CI.** Both nightly runs report exactly 551 MB peak RSS
  for a 32 MB parse against a 150 MB bound. It is not a streaming regression: on aarch64 Linux
  the same parse is flat against file size (0.3 MB → 19 MB, 23 MB → 31 MB, 33 MB → 33 MB) and
  `MALLOC_ARENA_MAX` changes nothing; macOS gives 48 MB. The bound was calibrated on a Mac and
  something about GitHub's x86_64 runners inflates it ~16×. **The box is arm64, where streaming
  is intact**, so `load-all` and the weekly update are memory-safe on 8 GB. Fix by recalibrating
  per platform or by asserting the scaling property instead of an absolute number.
- Everything in CLAUDE.md's "Open debts" paragraph still stands.

## Cost

~$49/mo instance + ~$11/mo for 140 GB of gp3 + ECR storage ≈ **$60–65/month**. The Elastic IP is
free while attached to a running instance. Downsize path if that matters: stop, resize to
`t4g.medium`, set `OPENSEARCH_HEAP=1g`, start — but the 2 GB OpenSearch heap plus Postgres's 1 GB
`shared_buffers` is why `t4g.large` was chosen, so expect it to be tight.
