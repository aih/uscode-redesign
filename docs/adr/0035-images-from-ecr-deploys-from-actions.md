# ADR-0035: Images built by Actions, pushed to ECR, deployed by SSM — no build-on-box, no SSH

**Status:** Accepted
**Date:** 2026-08-01
**Related:** [ADR-0013](0013-s3-mirror-of-record-disposable-downloader.md) (one-writer rule, now
transferred), [ADR-0018](0018-cache-immutably-only-when-the-release-point-is-pinned.md) (cache
policy this doesn't change), [ADR-0020](0020-deploy-one-ec2-box-compose-caddy.md) (the box this
deploys onto), [ADR-0029](0029-request-identity-and-rate-limits.md) (rate limiter state, whose
per-process assumption this ADR keeps)

## Context

ADR-0020 put the site on one EC2 box and left "how does a change reach it" unanswered — `docs/deploy.md`
§4 was `docker compose up -d --build`, run by a human over an SSM session. That was fine for a first
bring-up. It stops being fine the moment there's a second deploy: building on the box means every push
competes with Postgres and OpenSearch for the same 8 GB and the same t4g burst credits, and "SSH in and
run compose" is a deploy path nobody reviewed, with no record of what shipped when.

Separately, ADR-0013's backfill box finished its job — the ledger is complete and the mirror holds the
whole corpus — and the weekly job that keeps it current still needs a home. The site box is already
running, already has network access to OLRC, and is no longer just a reader.

## Decisions

**1. Actions builds arm64 images natively (`ubuntu-24.04-arm`), pushes to ECR, SSM runs a
repo-versioned script.** Not build-on-box: the t4g.large's burst CPU budget is sized for OpenSearch's
heap and Postgres's buffer cache, not for a second lxml-and-esbuild toolchain competing for it during
serving hours. Not SSH: an OIDC role scoped to `ecr:PutImage` and `ssm:SendCommand`, with the
box-side logic committed and reviewed as `deploy/deploy-on-box.sh`, is an auditable deploy path — the
alternative is a key that can run anything, on a box with the database on it. `ubuntu-24.04-arm` avoids
cross-compilation and QEMU entirely; GitHub's arm64 runners build native images in native time.

**2. `workflow_run` on CI's success, not a second test run.** `deploy.yml` triggers when `ci.yml`
finishes green on `main`, plus manual `workflow_dispatch`. Re-running the suite inside the deploy
workflow would mean two independent pass/fail signals for the same commit that can disagree, and it
would double the CI minutes for every merge. The commit that deploys is the commit CI already vetted;
`workflow_run` reads that result rather than re-deriving it.

**3. `pg_restore` from a nightly dump sits beside `load-all`, not instead of it.** ADR-0020's
reconstructibility argument — the database is a pure function of the mirror plus the loader — is what
makes losing the box cheap, and that argument still has to be true after this ADR. So `load-all` from
the mirror stays the documented rebuild path. The dump in `s3://…/usc/db/` is a *fast path* for
standing up a box in minutes instead of days; it is not the thing verification trusts.

**4. The one-writer role moves from the backfill box to the site box.** ADR-0013 decided "one writer"
as a rule, not as a binding to a specific machine — but the machine it named, the disposable backfill
box, no longer runs anything: the backfill is complete. The weekly update (`update-corpus.yml`) needs
somewhere to run `inventory → backfill → mirror push → load-all`, and the site box is already up, has
the mirror credentials, and needs the fresh corpus locally anyway. Widening its instance-role
`s3:PutObject` from `usc/db/*` to `usc/*` is that transfer made concrete: it can now write the ledger
and the zips, not just its own Postgres dumps. **This is still one writer** — the backfill box is
retired, not duplicated alongside a second one.

**5. The corpus update runs weekly, on a schedule, unattended.** New release points appear on OLRC's
own cadence, not on a deploy's. A cron-triggered workflow that pushes one SSM command is the same shape
as the deploy path — no SSH, one script, one log — so this ADR does not introduce a second way of
reaching the box, only a second trigger for the same mechanism.

## Alternatives set aside

- **Build on the box** — rejected in decision 1; also means the deploy artifact (an image) and the
  build environment (whatever happens to be installed on the box that week) are the same thing, which
  is exactly the drift a registry exists to prevent.
- **A second full test run in `deploy.yml`** — rejected in decision 2; if the concern is "what if `main`
  moved between CI finishing and the deploy running", `workflow_run` pins to the commit CI actually
  tested, not to whatever `main` points at when the deploy fires.
- **ECS/Fargate to get "real" CD** — reopens ADR-0020's RDS argument in a new shape: paying for
  orchestration to manage a single box's failure domain, when the box's whole state is already
  reconstructible from the mirror.
- **A long-lived deploy key in GitHub secrets** — OIDC's short-lived, per-run credentials mean a leaked
  Actions log can't be replayed later; a static key can.

## Consequences (named costs)

- **A deploy that recreates the `api` container mid-update kills whatever `update-corpus.sh` was
  running inside it.** The recovery is the same resumability the backfill was already built on — the
  ledger and the database resume state pick up where they stopped — but a weekly job and a deploy
  landing in the same window is a real collision this ADR does not schedule around.
- **`latest` is a mutable tag by design, not an oversight.** It exists for a human doing `docker compose
  pull` by hand while debugging; what actually deploys is the git sha pinned into `.env`'s
  `IMAGE_TAG`, and `deploy-on-box.sh` never reads `latest` itself.
- **The IMDSv2 hop-limit is invisible until something inside a container needs instance-role
  credentials and hangs.** `HttpPutResponseHopLimit=2` exists because a containerized process is one
  network hop further from the metadata service than a process on the host; get the number wrong and
  the failure mode is a silent timeout on the first S3 call, not an error that names the cause.
- **SSM's `executionTimeout` caps one update run at 12 hours.** A corpus update that legitimately needs
  longer stops there, not when the work is done; the next scheduled run continues it because the ledger
  and the load are both resumable, but a human watching the GitHub job sees a job that gave up after
  ~5.5 hours of polling, not a job that finished.
- **Rate limiter state stays per-process, and this ADR does not change that.** ADR-0029 already named
  the cost of a second instance needing shared state; nothing here adds a second instance, so the
  assumption holds, but it holds by not being tested rather than by being re-verified.
