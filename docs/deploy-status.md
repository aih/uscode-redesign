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

**3. Confirm the alarm email.** AWS sent a subscription confirmation to
`arihershowitz@gmail.com` for the `uscode-alerts` SNS topic. **Until you click it, every alarm
is silent** — an unconfirmed topic fails quietly, which looks exactly like nothing being wrong.
Prove delivery afterwards:

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

The seed dump (2.33 GB compressed, restoring to ~27 GB) was uploaded to
`s3://uscode-mirror-dreamproit/usc/db/uscode-2026-08-01.dump` and is being restored on the box.

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

## Still owed after the corpus lands

1. **Build the search index** — nothing populates it after a bulk restore (day-to-day loads sync
   incrementally inside `ingest/load.py`; a from-scratch corpus does not):

   ```bash
   # 66k current-text docs — this is what makes search go from empty to live.
   docker compose -f docker-compose.prod.yml exec api \
     uv run python -m ingest.reindex_search --recreate

   # 490k superseded docs, what `?release=` search needs. Much longer; detach it.
   docker compose -f docker-compose.prod.yml exec -d api \
     sh -c 'uv run python -m ingest.reindex_search --all-versions >> /app/data/reindex.log 2>&1'
   ```

2. **`ingest verify`** (shallow) to confirm the restore matches what the dump claimed.
3. **`mirror pull`** so the box has the zips locally for future incremental loads.
4. **Smoke tests** — deploy.md §5, against the real hostname once TLS is up.
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
