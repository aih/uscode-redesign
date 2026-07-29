# ADR-0020: Deploy as one EC2 instance running compose, not RDS or a PaaS

**Date:** 2026-07-29 · **Status:** Accepted · **Implements:** Day 6 deploy (PLAN.md) · **Runbook:** [docs/deploy.md](../deploy.md)

## Context

PLAN §8 offered two hosting shapes and made the choice conditional on a number nobody had:
*"Postgres with all RPs deduped is likely 10–40 GB — check managed-tier pricing"*, versus
*"cheaper for storage-heavy DB: a Hetzner/DO VPS running compose"*. The session prompt made the
same conditional explicit — pick "given the measured database size from Session 9" — and Session 9
never ran.

It has now been measured, on the partially loaded development database:

| table | size | rows |
|---|---|---|
| `guid_map` | 5,270 MB | 21,734,989 |
| `section_versions` | 1,169 MB | 212,094 |
| `section_release_map` | 247 MB | 1,275,317 |
| everything else | ~16 MB | |
| **total** | **6,711 MB** | for **792 of 3,153** title-releases |

`guid_map` is 79% of the database and grows linearly with title-releases — one row per guid per
release point, by ADR-0003's design. `section_versions` grows far more slowly because ADR-0007's
dedupe is working (1,275,262 section-release rows collapse to 212,094 stored versions, 83.4%).
Extrapolating the linear part: **the full corpus is 25–35 GB.**

The user chose AWS, which settles the provider and leaves the shape open.

## Decisions

**1. One EC2 instance running `docker-compose.prod.yml`.** Not RDS, not ECS/Fargate, not App
Runner.

RDS is the alternative worth taking seriously, and the case against it is mostly arithmetic: a
`db.t4g.medium` with 100 GB is roughly $60–70 a month *before* any compute, against ~$35 a month
for one instance running everything. For a demo site that is the difference between "obviously
worth it" and "needs justifying".

The reason the usual argument for a managed database is weak here is more interesting than the
price. What RDS sells is durability of state you cannot reconstruct. **This database is entirely
reconstructible**: it is a pure function of the zips on the S3 mirror and `ingest load-all`, both
of which are versioned, hashed, and verified (ADR-0012, ADR-0013, ADR-0014). Losing it costs the
hours of a reload, not the data. Paying a premium to protect state that is already reproducible is
paying twice.

**2. A separate EBS data volume, `DeleteOnTermination=false`.** 20 GB root plus 100 GB gp3 mounted
at `/var/lib/uscode`, holding `pgdata`, the corpus and Caddy's certificates. The instance is
disposable and the loaded corpus is not — a resize, an AMI change or a bad upgrade should not cost
a reload.

**3. `m7g.large` for the load, `t4g.medium` to serve.** The bulk load is CPU-bound lxml parsing for
hours or days; a burstable `t4g` would exhaust its CPU credits partway and crawl. Serving is not:
the load test's 130–300 rps came off a laptop through a single-worker dev stack. Stop, change
instance type, start — two minutes on the same volumes.

**4. Access is SSM only. No SSH, no inbound 22, and 5432 is not published at all.** This follows
`docs/remote-ops.md` §1 for the downloader box, and it is why `docker-compose.prod.yml` is a
standalone file rather than an overlay: Compose merges `ports` by *appending*, so an overlay
cannot remove the dev file's `5432:5432`, and a production stack assembled that way would put the
entire database on a public IP. A separate file cannot make that mistake.

**5. Caddy terminates TLS with a hostname from `$SITE_ADDRESS`.** One substitution turns the dev
`:8000` block into an HTTPS site with an automatically provisioned and renewed certificate. Caddy
also gains `trusted_proxies`, which is load-bearing for ADR-0019's cookie.

**6. The site is a *reader* of the mirror.** Its IAM role gets `s3:GetObject`/`s3:ListBucket` on
the corpus and write access only under `usc/db/`. ADR-0013's one-writer rule stands: the ledger's
writer is wherever the backfill runs, and that is not this box.

**7. Nightly `pg_dump` to `s3://…/usc/db/`.** This is the backup, and it also settles the question
`docs/remote-ops.md` §7 left open for "Session 8's call to record" — *"A `pg_dump` of the loaded
database pushed to S3 would let any machine skip the load entirely."* It would, and now it does.
It turns a rebuild from days of loading into minutes of downloading, which is what makes decision
1's "reconstructible" claim cheap in practice rather than only in principle.

**8. The site goes public before the load finishes.** A request for a release point that was never
ingested is answered from the newest ingested one at or before it, and reports that as
`served_from` (gotcha 10). A partial corpus therefore gives correct answers over a smaller range
rather than wrong ones, so there is no reason to keep the site dark for days.

## Consequences

- ~$70 during the load pass and ~$35 a month after, against $100+ for a managed-database shape.
- One box means one failure domain: a lost instance is downtime, and recovery is provision,
  restore the nightly dump, restart. There is no automatic failover and this is not a design that
  wants to grow one — the answer to needing that is a different ADR, not a bigger version of this.
- The instance holds no state worth backing up beyond the database dump, which is what makes it
  replaceable rather than precious.
- **The diff endpoint is unthrottled and CPU-bound**: measured at ~0.45 rps regardless of
  concurrency, failing entirely past about ten concurrent requests
  (`docs/verification/loadtest.json`). It is unauthenticated. ADR-0018's `immutable` caching helps
  repeat requests but not varied ones, so this needs a rate limit before the URL is advertised
  widely. Recorded as a known risk of going public, not as something this ADR solves.
- CloudFront is a drop-in whenever it is wanted, because ADR-0018 already emits exactly the
  headers it reads. Deliberately not part of v1.
