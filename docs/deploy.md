# Deploying the site (AWS)

The decision and its reasoning are [ADR-0020](adr/0020-deploy-one-ec2-box-compose-caddy.md);
this is the runbook. Companion to [remote-ops.md](remote-ops.md), which covers the *downloader*
box — a different, disposable machine with a different job. This one serves the site.

Shape: **one EC2 instance running `docker-compose.prod.yml`**, Caddy terminating HTTPS, Postgres
in a container on a separate EBS volume, and the corpus pulled from the S3 mirror. No RDS, no
ECS — see the ADR for why.

Everything here assumes `AWS_PROFILE=uscode` and `AWS_REGION=us-east-1`, matching the mirror.

---

## 0. What it costs

| | | monthly |
|---|---|---|
| `m7g.large` (2 vCPU, 8 GB, arm64) — for the load pass | $0.0816/hr | ~$60 |
| `t4g.large` (2 vCPU, 8 GB) — steady serving, chosen state | $0.0672/hr | ~$49 |
| 20 GB gp3 root + 120 GB gp3 data | $0.08/GB-month | ~$11 |
| S3 mirror (~9.7 GB, already exists) | | ~$0.25 |
| Egress | first 100 GB free | ~$0 |

So roughly **$70 during the load and ~$60–65/month all-in after** (t4g.large plus volumes, ECR
storage, and the S3 mirror). `t4g.large` over the smaller `t4g.medium` is not a downgrade decision
deferred, it's the RAM math actually adding up: OpenSearch's 2g heap (ADR-0029, decision 6) plus
Postgres's `shared_buffers` (1 GB) plus the Node SSR process plus FastAPI plus Caddy don't fit in
4 GB alongside the OS. `m7g.large` stays the load-pass-only option — downsize to `t4g.large`, not
`t4g.medium`, in step 6. Sizing comes from measurement, not guesswork: 6,711 MB of Postgres for
792 of 3,153 title-releases, with `guid_map` (5,270 MB, 21.7 M rows) dominating and growing
linearly — call the full corpus **25–35 GB**. A 120 GB volume holds that plus the 9.7 GB of zips
with room to spare.

## 1. Prerequisites

- **A domain name** with an A record pointing at the instance's Elastic IP. Caddy needs a
  hostname to get a certificate; there is no way around this. (`sslip.io` works in a pinch —
  `1-2-3-4.sslip.io` resolves to `1.2.3.4` — but use a real name for anything public.)
- **An IAM identity that can create EC2 and IAM resources**, to run `deploy/admin-grant.sh` (§2)
  once. The `uscode` profile (`uscode-mirror-dreamproit-user`) is scoped to the mirror bucket and
  **cannot** do this; it cannot even `s3:ListAllMyBuckets`. Provisioning needs a wider identity.
- **The mirror complete.** It is: the ledger is 3,153 `ok` / 44 `unavailable` / 0 pending, 9.7 GB
  on disk, verified against the local corpus (`docs/verification/database.json`). Nothing to do
  here for a fresh deploy — noted because it wasn't always true, and a partial mirror would mean
  the box pulling an incomplete corpus. If it ever regresses, `push` uploads zips first and
  `ledger.json` last, so an interrupted run never leaves the mirror advertising files it does not
  have (ADR-0013); it is resumable — `aws s3 sync` skips what is already there. After ADR-0035,
  this push runs from the site box itself (§7), not a separate backfill machine — that box's job
  finished and it isn't kept around.

## 2. Provision

`deploy/admin-grant.sh` does everything below in one run — the security group, the instance role
and its policies, the OIDC provider and `uscode-github-deploy` role Actions assumes (§7) — and is
meant to be run once, by a human with an admin profile, not folded into the site's own deploy path.
The steps it performs, spelled out:

```bash
export AWS_REGION=us-east-1

# Security group: 80 and 443 only. No SSH — access is SSM, as in remote-ops §1.
SG=$(aws ec2 create-security-group --group-name uscode-site \
      --description "uscode-redesign public site" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 443 --cidr 0.0.0.0/0

# Instance role: SSM for access, read-write on the mirror, ECR pull, and
# CloudWatch metrics. ADR-0035 moved ADR-0013's one-writer role onto this box
# once the backfill box's job finished — the weekly corpus update (§7) now
# writes the ledger and the zips from here, not just its own Postgres dumps,
# so PutObject widens from usc/db/* to the whole usc/ prefix.
aws iam create-role --role-name uscode-site \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
    "Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name uscode-site \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam attach-role-policy --role-name uscode-site \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
aws iam put-role-policy --role-name uscode-site --policy-name mirror-and-metrics \
  --policy-document '{"Version":"2012-10-17","Statement":[
    {"Effect":"Allow","Action":["s3:GetObject","s3:ListBucket","s3:PutObject"],
     "Resource":["arn:aws:s3:::uscode-mirror-dreamproit",
                 "arn:aws:s3:::uscode-mirror-dreamproit/usc/*"]},
    {"Effect":"Allow","Action":["cloudwatch:PutMetricData"],"Resource":"*"}]}'
aws iam create-instance-profile --instance-profile-name uscode-site
aws iam add-role-to-instance-profile --instance-profile-name uscode-site --role-name uscode-site

# m7g.large for the load pass — a multi-day load-all on a burstable t4g would
# exhaust its CPU credits and crawl. Downsize to t4g.large after (step 6) —
# the steady-state instance, not a smaller one; see §0 for the RAM math.
# HttpPutResponseHopLimit=2 because a containerized process (ECR login,
# mirror pull) is one network hop further from IMDS than a process on the
# host — 1 is the AMI default and would leave every container's metadata
# call failing silently.
aws ec2 run-instances \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
  --instance-type m7g.large \
  --iam-instance-profile Name=uscode-site \
  --security-group-ids "$SG" \
  --metadata-options "HttpTokens=required,HttpPutResponseHopLimit=2" \
  --block-device-mappings \
    'DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3,DeleteOnTermination=true}' \
    'DeviceName=/dev/xvdb,Ebs={VolumeSize=120,VolumeType=gp3,DeleteOnTermination=false}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=uscode-site}]'
```

The data volume has `DeleteOnTermination=false` on purpose: the instance is replaceable, the
25–35 GB of loaded corpus is not. The `Name=uscode-site` tag is not just labeling — `deploy.yml`
and `update-corpus.yml` (§7) target SSM commands at it.

Then allocate an Elastic IP, associate it, and point the domain's A record at it.

## 3. Set the box up

`aws ssm start-session --target <instance-id>`, then:

```bash
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user   # log out and back in

# The data volume, mounted where docker-compose.prod.yml expects it.
sudo mkfs.ext4 /dev/nvme1n1        # first boot only — this erases the volume
sudo mkdir -p /var/lib/uscode
echo "/dev/nvme1n1 /var/lib/uscode ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
sudo mount -a
sudo mkdir -p /var/lib/uscode/{pgdata,releases,manifests,caddy,opensearch,logs}
sudo chown -R ec2-user:ec2-user /var/lib/uscode

git clone https://github.com/<owner>/uscode-redesign.git && cd uscode-redesign
cat > .env <<EOF
SITE_ADDRESS=uscode.linkedlegislation.org
POSTGRES_PASSWORD=$(openssl rand -base64 32)
DATA_ROOT=/var/lib/uscode
USC_MIRROR_BUCKET=uscode-mirror-dreamproit
ECR_REGISTRY=739065237548.dkr.ecr.us-east-1.amazonaws.com
SEARCH_PASSWORD=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)!7q
EOF
chmod 600 .env
```

**`SEARCH_PASSWORD` is honoured only on the OpenSearch data volume's first boot** — changing it
later in `.env` does nothing until the volume is wiped, and it must not contain the substring
`admin` (the image rejects that at startup). Generate it once, here, and leave it alone.

## 4. Bring the site up, then fill it

First bring-up is a manual run of the same script continuous deploy uses (§7):

```bash
bash deploy/deploy-on-box.sh <sha>
```

Spelled out, that script does: `aws ecr get-login-password | docker login`, pin `<sha>` into
`.env`'s `IMAGE_TAG`, `docker compose -f docker-compose.prod.yml pull`,
`docker compose -f docker-compose.prod.yml run --rm --no-deps api uv run alembic upgrade head`,
then `docker compose -f docker-compose.prod.yml up -d --wait` — the healthchecks on `api`
(`/health`) and `frontend` (`/app/healthz`) are what `--wait` waits on, so the command doesn't
return until both are actually answering, not just started. If ECR isn't reachable yet or you want
to build locally instead: `docker compose -f docker-compose.prod.yml up -d --build --wait` falls
back to each service's `build:` block.

Caddy gets its certificate within a few seconds of the DNS record resolving. The site is now up
and **empty**, which is fine — fill it while it serves. Two ways in, pick one:

**Fast path — restore a dump.** Minutes, not days, if a recent one exists in the mirror:

```bash
# Pull the newest dump and restore it. This is the corpus as of whenever the
# dump was taken, not necessarily the latest release point — check
# manifests/ or the release_points table once it's up.
aws s3 cp s3://uscode-mirror-dreamproit/usc/db/$(aws s3 ls s3://uscode-mirror-dreamproit/usc/db/ \
  | sort | tail -1 | awk '{print $4}') - \
  | docker compose -f docker-compose.prod.yml exec -T db pg_restore -U uscode -d uscode --clean --if-exists

# alembic upgrade head as a no-op check: the dump should already be on the
# schema the running image expects. If this actually migrates something,
# the dump predates a release and needs investigating before trusting it.
docker compose -f docker-compose.prod.yml exec api uv run alembic upgrade head

# A shallow check that what landed matches what the dump's manifest claims —
# not the full deep recount (that's `make verify-deep`, still worth running
# once, later, unhurried).
docker compose -f docker-compose.prod.yml exec api uv run python -m ingest verify
```

**From-source path — `load-all`.** The alternative when there's no dump yet, or when
reconstructibility itself is what's being verified (ADR-0020's argument for skipping RDS):

```bash
# The corpus, from the mirror. In-region, so this is minutes rather than the
# 40-50 hours the original polite download took. Re-hashed against the ledger
# on arrival: the transport is trusted, the bytes are not (ADR-0013).
docker compose -f docker-compose.prod.yml exec api \
  uv run python -m ingest mirror pull

# The load. Hours to days — 382 release points, and only 66 have ever been
# loaded anywhere. Resume state is the database (ADR-0014), so it survives
# restarts; run it detached and check back.
docker compose -f docker-compose.prod.yml exec -d api \
  sh -c 'uv run python -m ingest load-all >> /app/data/load-all.log 2>&1'
```

**Do not wait for the load to finish before opening the site.** A request for a release point
that was never ingested is answered from the newest ingested one at or before it, and says so via
`served_from` (gotcha 10) — so a partial corpus gives correct answers over a smaller range, not
wrong ones. Smoke-test as soon as a useful slice is in.

**Either path, build the search index next — nothing populates it automatically after a bulk
restore or a full load** (day-to-day loads sync incrementally via `ingest/load.py`; a from-scratch
corpus doesn't):

```bash
# Current text — 66k docs, what the default (unpinned) search reads. Do this
# first: it's what makes search go from empty to live.
docker compose -f docker-compose.prod.yml exec api \
  uv run python -m ingest.reindex_search --recreate

# Superseded text — 490k docs, what `?release=` search needs. Bigger, so run
# it detached and let it finish in the background.
docker compose -f docker-compose.prod.yml exec -d api \
  sh -c 'uv run python -m ingest.reindex_search --all-versions >> /app/data/reindex.log 2>&1'
```

When the corpus load finishes: `make verify`, then `make verify-deep` — the independent recount,
and the only one that does not just ask the loader to confirm its own bookkeeping. Commit
`docs/verification/database.json`.

## 5. Smoke test — from your machine, not the box

```bash
SITE=https://uscode.linkedlegislation.org

# The demo URL end to end, through the redirector into the reader (PLAN §10).
curl -sL -o /dev/null -w '%{http_code} %{url_effective}\n' \
  -H 'Accept: text/html' "$SITE/us/usc/t16/s45f/c/5?date=07/12/2026"

# The same citation, for a machine: 307 to /api/v1 instead.
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  -H 'Accept: application/json' "$SITE/us/usc/t16/s45f/c/5?date=07/12/2026"

# Caching: pinned is immutable, unpinned is not (ADR-0018).
curl -sD - -o /dev/null "$SITE/api/v1/us/usc/t16/s45f?release=119-102not101" | grep -i cache-control
curl -sD - -o /dev/null "$SITE/api/v1/us/usc/t16/s45f"                       | grep -i cache-control

# The one that must be checked and not assumed: the session cookie's Secure
# flag over real TLS (ADR-0019). Expect HttpOnly, SameSite=lax and Secure.
curl -s -D - -o /dev/null -X POST "$SITE/api/v1/auth/signup" \
  -H 'Content-Type: application/json' \
  -d '{"email":"smoke-'"$(date +%s)"'@example.com","password":"correct horse battery staple"}' \
  | grep -i set-cookie

# Per-user pages must never be cacheable.
curl -sD - -o /dev/null "$SITE/app/provisions" | grep -iE 'cache-control|vary'
```

Then, in a browser: open the demo URL, flip the release picker, follow a version timeline into a
diff, sign up, watch a section, and confirm it appears at `/app/provisions`.

## 6. After the load: downsize and back up

```bash
aws ec2 stop-instances --instance-ids <id>
aws ec2 modify-instance-attribute --instance-id <id> --instance-type t4g.large
aws ec2 start-instances --instance-ids <id>
```

Two minutes of downtime, same volumes, down to the ~$49/month steady state (§0) — `t4g.large`,
not a smaller size: OpenSearch's 2g heap alone rules out `t4g.medium`'s 4 GB once Postgres and the
Node/FastAPI/Caddy processes are also on the box.

Backups are a nightly `pg_dump` to the mirror — which also settles the question remote-ops §7
left open ("a `pg_dump` … would let any machine skip the load entirely"). Add to the box's crontab:

```
17 4 * * * cd ~/uscode-redesign && docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U uscode -Fc uscode | aws s3 cp - s3://uscode-mirror-dreamproit/usc/db/uscode-$(date +\%F).dump
```

A restore is `pg_restore` from that object, which turns a rebuild from days of loading into
minutes of downloading.

## 7. Continuous deploy and the weekly update

Design and named costs: [ADR-0035](adr/0035-images-from-ecr-deploys-from-actions.md). Neither
workflow uses SSH; both reach the box the same way, one `aws ssm send-command` targeting instances
tagged `Name=uscode-site` (§2).

**`.github/workflows/deploy.yml`** triggers on `workflow_run` of CI succeeding on `main` — not a
second test run, `workflow_run` just reads CI's result for that commit — plus manual
`workflow_dispatch`. It assumes the `uscode-github-deploy` OIDC role (repo variable
`AWS_DEPLOY_ROLE_ARN`; no long-lived AWS keys in this repository), builds and pushes both images
to ECR tagged `<git sha>` and `latest`, then SSM-runs
`git checkout --force <sha> && bash deploy/deploy-on-box.sh <sha>` on the box. `deploy-on-box.sh`
is flock-guarded against overlapping runs and logs to `${DATA_ROOT}/logs/deploy.log`.

**`.github/workflows/update-corpus.yml`** runs Mondays 07:23 UTC and on manual dispatch, and sends
one SSM command running `deploy/update-corpus.sh` inside the `api` container — `inventory` →
`backfill` (new title-releases only, ledger-resumable) → `mirror push` → `load-all` (incremental;
search sync is automatic inside `ingest/load.py`, no separate reindex needed for the weekly path)
→ `verify`. This is ADR-0013's one-writer role, moved here now that the backfill box's job is
done (ADR-0035). SSM's `executionTimeout` bounds one run at 12 hours; the GitHub job polls for up
to ~5.5 hours and then exits with a notice rather than blocking the workflow forever — SSM keeps
running regardless, and an incomplete run resumes on the next Monday.

Logs from both workflows land on the box at `${DATA_ROOT}/logs/` (`deploy.log`,
`update-corpus.log`) — check there first if a run's GitHub Actions summary isn't enough.

## What is deliberately not here

- **No CDN.** The `immutable` headers make CloudFront a drop-in when it is wanted; nothing about
  this shape has to change for it. Not needed for a demo.
- **No autoscaling, no multi-AZ, no managed failover.** One box. The whole database is
  reproducible from the mirror, which is what makes that acceptable — see ADR-0020.
- **No CI re-run inside the deploy path.** `deploy.yml` trusts `ci.yml`'s result for the commit
  rather than re-testing it (ADR-0035, decision 2) — a deliberate choice, not a gap.
