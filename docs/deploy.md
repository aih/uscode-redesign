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
| `t4g.medium` (2 vCPU, 4 GB) — steady serving after | $0.0336/hr | ~$25 |
| 20 GB gp3 root + 100 GB gp3 data | $0.08/GB-month | ~$10 |
| S3 mirror (~9.7 GB, already exists) | | ~$0.25 |
| Egress | first 100 GB free | ~$0 |

So roughly **$70 during the load and $35/month after**. Sizing comes from measurement, not
guesswork: 6,711 MB of Postgres for 792 of 3,153 title-releases, with `guid_map` (5,270 MB,
21.7 M rows) dominating and growing linearly — call the full corpus **25–35 GB**. A 100 GB volume
holds that plus the 9.7 GB of zips with room to spare.

## 1. Prerequisites

- **A domain name** with an A record pointing at the instance's Elastic IP. Caddy needs a
  hostname to get a certificate; there is no way around this. (`sslip.io` works in a pinch —
  `1-2-3-4.sslip.io` resolves to `1.2.3.4` — but use a real name for anything public.)
- **An IAM identity that can create EC2 and IAM resources.** The `uscode` profile
  (`uscode-mirror-dreamproit-user`) is scoped to the mirror bucket and **cannot** do this; it
  cannot even `s3:ListAllMyBuckets`. Provisioning needs a wider identity.
- **The mirror complete.** `s3://uscode-mirror-dreamproit/usc/` currently holds 1,122 of 3,153
  zips — an interrupted push. Finish it from the machine that ran the backfill *before*
  provisioning, or the box will pull a partial corpus:

  ```bash
  AWS_PROFILE=uscode USC_MIRROR_BUCKET=uscode-mirror-dreamproit \
    uv run python -m ingest mirror push
  ```

  `push` uploads zips first and `ledger.json` last, so an interrupted run never leaves the mirror
  advertising files it does not have (ADR-0013). It is resumable — `aws s3 sync` skips what is
  already there.

## 2. Provision

```bash
export AWS_REGION=us-east-1

# Security group: 80 and 443 only. No SSH — access is SSM, as in remote-ops §1.
SG=$(aws ec2 create-security-group --group-name uscode-site \
      --description "uscode-redesign public site" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 443 --cidr 0.0.0.0/0

# Instance role: SSM for access, read-only on the mirror. The site is a *reader*
# of the corpus — ADR-0013's one-writer rule stands, and the writer is the
# backfill box.
aws iam create-role --role-name uscode-site \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
    "Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name uscode-site \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam put-role-policy --role-name uscode-site --policy-name mirror-read \
  --policy-document '{"Version":"2012-10-17","Statement":[
    {"Effect":"Allow","Action":["s3:GetObject","s3:ListBucket"],
     "Resource":["arn:aws:s3:::uscode-mirror-dreamproit",
                 "arn:aws:s3:::uscode-mirror-dreamproit/usc/*"]},
    {"Effect":"Allow","Action":["s3:PutObject"],
     "Resource":"arn:aws:s3:::uscode-mirror-dreamproit/usc/db/*"}]}'
aws iam create-instance-profile --instance-profile-name uscode-site
aws iam add-role-to-instance-profile --instance-profile-name uscode-site --role-name uscode-site

# m7g.large for the load pass — a multi-day load-all on a burstable t4g would
# exhaust its CPU credits and crawl. Downsize after (step 6).
aws ec2 run-instances \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
  --instance-type m7g.large \
  --iam-instance-profile Name=uscode-site \
  --security-group-ids "$SG" \
  --block-device-mappings \
    'DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3,DeleteOnTermination=true}' \
    'DeviceName=/dev/xvdb,Ebs={VolumeSize=100,VolumeType=gp3,DeleteOnTermination=false}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=uscode-site}]'
```

The data volume has `DeleteOnTermination=false` on purpose: the instance is replaceable, the
25–35 GB of loaded corpus is not.

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
sudo mkdir -p /var/lib/uscode/{pgdata,releases,manifests,caddy}
sudo chown -R ec2-user:ec2-user /var/lib/uscode

git clone https://github.com/<owner>/uscode-redesign.git && cd uscode-redesign
cat > .env <<EOF
SITE_ADDRESS=uscode.example.org
POSTGRES_PASSWORD=$(openssl rand -base64 32)
DATA_ROOT=/var/lib/uscode
USC_MIRROR_BUCKET=uscode-mirror-dreamproit
EOF
chmod 600 .env
```

## 4. Bring the site up, then fill it

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api uv run alembic upgrade head
```

Caddy gets its certificate within a few seconds of the DNS record resolving. The site is now up
and **empty**, which is fine — fill it while it serves:

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

When it finishes: `make verify`, then `make verify-deep` — the independent recount, and the only
one that does not just ask the loader to confirm its own bookkeeping. Commit
`docs/verification/database.json`.

## 5. Smoke test — from your machine, not the box

```bash
SITE=https://uscode.example.org

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
aws ec2 modify-instance-attribute --instance-id <id> --instance-type t4g.medium
aws ec2 start-instances --instance-ids <id>
```

Two minutes of downtime, same volumes, ~$35/month less.

Backups are a nightly `pg_dump` to the mirror — which also settles the question remote-ops §7
left open ("a `pg_dump` … would let any machine skip the load entirely"). Add to the box's crontab:

```
17 4 * * * cd ~/uscode-redesign && docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U uscode -Fc uscode | aws s3 cp - s3://uscode-mirror-dreamproit/usc/db/uscode-$(date +\%F).dump
```

A restore is `pg_restore` from that object, which turns a rebuild from days of loading into
minutes of downloading.

## What is deliberately not here

- **No CDN.** The `immutable` headers make CloudFront a drop-in when it is wanted; nothing about
  this shape has to change for it. Not needed for a demo.
- **No autoscaling, no multi-AZ, no managed failover.** One box. The whole database is
  reproducible from the mirror, which is what makes that acceptable — see ADR-0020.
- **The diff endpoint is not throttled.** The load test measured it at ~0.45 rps regardless of
  concurrency, failing entirely past ~10 concurrent requests
  (`docs/verification/loadtest.json`). It is unauthenticated. **Put a rate limit in front of it
  before advertising the URL widely.**
