# Deployment status — uscode.linkedlegislation.org

Live state of the demo deployment and what is still owed. Design lives in
[ADR-0020](adr/0020-deploy-one-ec2-box-compose-caddy.md) and
[ADR-0035](adr/0035-images-from-ecr-deploys-from-actions.md); the runbook is
[deploy.md](deploy.md). This file is the *current* picture — delete it once the site is
settled and the interesting parts have moved into deploy.md.

**Last updated:** 2026-08-02, overnight session.

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

## What you need to do in the morning

At a glance: **DNS record → restart Caddy → confirm the alarm email → merge #17 and #18.** The
first is the only one blocking a working site; the rest can follow in any order. Both PRs are
green on all four suites.

**1. Add the DNS record.** This is the only thing blocking a working site:

```
uscode.linkedlegislation.org.   A   52.1.30.78
```

**2. Once it resolves, restart Caddy** so it retries immediately instead of waiting out its
backoff. Caddy has been failing ACME against a name that does not exist yet; it backs off
exponentially (capped at 30 days of retrying), so after DNS is live it could otherwise sit idle
for up to an hour before trying again:

```bash
export AWS_PROFILE=uscode-admin AWS_REGION=us-east-1
aws ssm send-command --instance-ids i-06b433caacd78fd96 \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["cd /home/ec2-user/uscode-redesign && docker compose -f docker-compose.prod.yml restart proxy"]'
```

Then, within a minute or two:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://uscode.linkedlegislation.org/health
```

The half of this that does not depend on you has already been checked: from off the box, with the
hostname forced to the Elastic IP, **port 80 answers and redirects correctly**
(`308 → https://uscode.linkedlegislation.org/health`), which is the path Let's Encrypt's HTTP-01
challenge uses. So the security group, Caddy's routing and the redirect are all confirmed working
from the public internet — the certificate is waiting on the DNS record and nothing else. HTTPS
currently fails the handshake outright, which is what "no certificate yet" looks like rather than a
misconfiguration:

```bash
# what was run, and what it said
curl -sk --resolve uscode.linkedlegislation.org:443:52.1.30.78 ... # status=000 (no cert yet)
curl -s  --resolve uscode.linkedlegislation.org:80:52.1.30.78  ... # status=308 → https://...
```

**3. Confirm the alarm email.** AWS sent a subscription confirmation to
`arihershowitz@gmail.com` for the `uscode-alerts` SNS topic. **Until you click it, every alarm
is silent** — an unconfirmed topic fails quietly, which looks exactly like nothing being wrong.

All five alarms exist and point at the topic. Four read `OK`; **`uscode-cpu-credits-low` reads
`ALARM`, and that is the alarm being right rather than a fault** — a t4g.large earns CPU credits
while idle and spends them under load, and this box has spent the night restoring 22 GB and
indexing half a million documents. It should clear once the box is only serving pages. If it is
still in alarm after a quiet day, that is the signal the instance is undersized for what is being
asked of it. Prove delivery afterwards:

```bash
aws cloudwatch set-alarm-state --alarm-name uscode-status-check-failed \
  --state-value ALARM --state-reason 'testing delivery' --region us-east-1
```

**4. Merge the two open PRs** (merging is blocked for the agent by a permission classifier):

- **#17** — deploy as `linkedlegislation-deploy`, least-privilege bootstrap policy, AMI lookup
  instead of the SSM alias.
- **#18** — the three fixes the first real deploy found (compose plugin, SSM polling, OIDC trust).

Both are already applied by hand to the live box and the live IAM role; merging makes a rebuild
reproduce them rather than repeat the debugging.

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
  at 04:17 UTC, and the weekly `purge_login_failures` that nothing had ever scheduled.
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

**Current state: search works.** `uscode_sections` holds 65,938 current-text documents and
`uscode_structure` 9,916; "conservation" returns 199 hits led by `/us/usc/t16/s2903`. Verified
after the rebuild described below.

The superseded pass got further with the fix — 230,500 documents, with **swap untouched**, where
before it had died around 3.4 GB — but was killed again at that point. This time there was no
kernel OOM logged at all and no traceback, and the only new thing in that run was a
`MemoryMax=2G` I had put on the systemd unit as a backstop. That was a mistake twice over: it
constrains the compose client rather than the Python inside the container, so it never protected
what I intended, and it is the most likely thing that sent the kill. It has been removed.

It was also a mistake to run that pass as `--recreate --all-versions`: `--recreate` drops the
index first, so a failure half way left **no working search** rather than a partial one. The
current-text index was rebuilt on its own to restore service, and the superseded pass is now
running **additively** (`--all-versions`, no `--recreate`). The two passes share document ids, so
the additive run tops the index up and a failure leaves working search behind. Check it with:

```bash
systemctl status uscode-reindex.service
tail -f /var/lib/uscode/logs/reindex-all.log
```

**If it failed again, nothing is broken and there is nothing urgent to do.** The default search
covers current text, and a point-in-time search answers from current text while naming the release
it searched, so the gap is visible rather than silent. Re-run it, or leave it — `?release=` search
reaching back through superseded text is the only thing it buys.

## Still owed

1. **`ingest verify` — done, and it passes.** 3,153 title-versions across 381 release points and
   58 titles; 91.0% dedupe; the six count mismatches it reports are exactly the ADR-0021 ones
   CLAUDE.md documents (`113-296not287/54`, `114-329/10`, `115-8/10`, `117-80/19`,
   `117-110not103/19`, `117-111not103/19`). Report at `docs/verification/database.json` **on the
   box** — not committed from there, since the repo copy is the development corpus's.
2. **Smoke tests** — deploy.md §5 is the full set; this is the copy-paste version for once TLS is
   up. Every line should be checked against what it *should* say, not just that it returned:

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
5. **A real end-to-end deploy** — push a trivial commit to main and watch CI → deploy.yml → the
   box, which is the first time the whole automated path runs unassisted.
6. **`workflow_dispatch` on update-corpus.yml** once, to prove the weekly job before it fires
   unattended on a Monday.

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
