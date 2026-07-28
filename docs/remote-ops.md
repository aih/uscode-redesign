# Remote operations: the download box and the S3 mirror

How to run the corpus backfill on a disposable EC2 instance, mirror the result
to S3, and keep local development untouched. Design rationale in ADR-0013;
the moving parts are `python -m ingest mirror {push,pull}` (`ingest/mirror.py`),
`scripts/run-backfill-ec2.sh`, and `scripts/ec2-user-data.sh`.

**The shape of it:** EC2 is a *disposable downloader* — it pulls resume state
from S3, runs the backfill, pushes hourly, and powers itself off when done. S3
is the *corpus of record*. The laptop is for development, on samples and
slices. Exactly one machine runs the backfill at a time (the "one writer"
rule); everyone else pulls.

## 0. What it costs

Assumes `us-east-1`, on-demand, July 2026 public pricing — check the console,
but the shape won't move:

| Item | Rate | This project |
|---|---|---|
| EC2 `t4g.micro` (2 vCPU, 1 GB, arm64) | ~$0.0084/hr | ~40–50 h run ≈ **$0.40** |
| EBS gp3 20 GB | $0.08/GB-mo | ≈ $0.05 for the run's few days |
| S3 Standard, ~9 GB corpus | $0.023/GB-mo | ≈ **$0.21/mo** ongoing |
| S3 requests (~3.3k PUTs) | $0.005/1k | ≈ $0.02 |
| Egress S3 → laptop | first 100 GB/mo free | $0 at our size |

Total: **well under $1 for the run, ~$0.25/mo to keep the mirror.** The
backfill is bandwidth-shaped, not CPU-shaped — OLRC serves ~50 KB/s and our
throttle is 1 req/sec — so the smallest Graviton instance is not a compromise,
it's correctly sized. (Session 8's bulk *load* wants more RAM; see §7.)

## 1. One-time AWS setup

Pick a globally-unique bucket name and a region once, and export them in the
shell you're working from:

```bash
export AWS_REGION=us-east-1
export BUCKET=uscode-mirror-$(aws sts get-caller-identity --query Account --output text)
```

### 1a. The bucket — private, versioned

```bash
aws s3api create-bucket --bucket "$BUCKET" --region "$AWS_REGION"
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled
```

(Versioning is the cheap insurance: a bad push can never destroy the previous
ledger. Corpus zips never change in place, so versioning costs ~nothing.)

### 1b. The instance role — S3 on this bucket, SSM, nothing else

No SSH keys and no open inbound ports anywhere in this guide: shell access is
`aws ssm start-session`, which Amazon Linux 2023 supports out of the box.

```bash
aws iam create-role --role-name usc-downloader \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name usc-downloader \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

aws iam put-role-policy --role-name usc-downloader \
  --policy-name usc-mirror-rw \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [
      {\"Effect\": \"Allow\", \"Action\": [\"s3:ListBucket\"],
       \"Resource\": \"arn:aws:s3:::$BUCKET\"},
      {\"Effect\": \"Allow\",
       \"Action\": [\"s3:GetObject\", \"s3:PutObject\"],
       \"Resource\": \"arn:aws:s3:::$BUCKET/usc/*\"}]}"

aws iam create-instance-profile --instance-profile-name usc-downloader
aws iam add-role-to-instance-profile \
  --instance-profile-name usc-downloader --role-name usc-downloader
```

## 2. Hand off the laptop's partial state

The laptop has been downloading; its progress should not be re-downloaded from
OLRC. Stop the local run, push what it has, and from this moment the laptop is
a *reader* of the mirror (one-writer rule):

```bash
cd ~/Documents/workspace/aih/uscode-redesign
pkill -f "ingest backfill"        # ledger saves after every file; nothing is lost
export USC_MIRROR_BUCKET=$BUCKET
uv run python -m ingest mirror push
```

Push order is deliberate: zips first, `ledger.json` last, so the mirror never
advertises files it doesn't hold.

## 3. Launch the download box

```bash
sed "s/__BUCKET__/$BUCKET/" scripts/ec2-user-data.sh > /tmp/user-data.sh

aws ec2 run-instances \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
  --instance-type t4g.micro \
  --iam-instance-profile Name=usc-downloader \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3,DeleteOnTermination=true}' \
  --instance-initiated-shutdown-behavior stop \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=usc-downloader}]' \
  --user-data file:///tmp/user-data.sh \
  --count 1
```

Notes on flags that matter:
- The AMI resolves to current Amazon Linux 2023 **arm64** at launch — nothing
  hard-coded to go stale.
- No `--key-name` and no security-group with inbound rules: access is SSM only.
- `--instance-initiated-shutdown-behavior stop`: when the run script calls
  `systemctl poweroff` on completion, the instance stops (billing ends) but is
  not destroyed — the EBS volume survives for inspection or a Session 8 reuse.

What user-data does (all of it visible in `scripts/ec2-user-data.sh`): installs
git + awscli, installs uv, clones this repo, writes two systemd units —
`usc-backfill.service` (pull → backfill → verify → push → power off; restarts
itself on failure) and an hourly `usc-mirror-push.timer` so an instance lost
mid-run costs at most an hour of downloads — and starts them.

## 4. Watch it (optional — it needs nothing from you)

```bash
IID=$(aws ec2 describe-instances \
  --filters Name=tag:Name,Values=usc-downloader Name=instance-state-name,Values=running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)

aws ssm start-session --target "$IID"
# then, inside the session:
journalctl -u usc-backfill -f          # the run, live
systemctl list-timers usc-mirror-push* # next hourly push
```

Progress without logging in — the mirror itself is the status page:

```bash
aws s3 cp "s3://$BUCKET/usc/releases/ledger.json" - | \
  python3 -c "import json,sys; d=json.load(sys.stdin); \
  from collections import Counter; \
  print(d['count'], 'of 3197:', dict(Counter(e['status'] for e in d['entries'])))"
```

The run ends in one of two states:
- **Instance stopped itself** → the backfill exited 0, the deep verification
  ran, and the final push completed. Done.
- **Still running long after the ETA** → `journalctl -u usc-backfill` inside an
  SSM session; `failed` entries retry on the unit's own restart loop, so a
  stuck run means OLRC-side trouble, not lost state.

## 5. Bring the results home

```bash
export USC_MIRROR_BUCKET=$BUCKET

# Development slice — a title at full history, verified by hash on arrival:
uv run python -m ingest mirror pull --title 16

# Or specific release points:
uv run python -m ingest mirror pull --release 119-99 --release 119-102not101

# Or, when you actually want all ~9 GB locally (Session 8 on the laptop):
uv run python -m ingest mirror pull
```

Every pull re-hashes what landed against the ledger's sha256s — transport is
delegated to `aws s3 sync`; trust is not. Then commit the verification
artifact the box produced:

```bash
aws s3 cp "s3://$BUCKET/usc/verification/downloads.json" docs/verification/downloads.json
git add docs/verification/downloads.json && git commit
```

## 6. Teardown

```bash
aws ec2 terminate-instances --instance-ids "$IID"   # EBS deletes with it
```

Keep the bucket — $0.25/mo is the whole point. The role and instance profile
are free and reusable for Session 8.

**Re-running later** (new release points appear every few weeks): refresh the
inventory (`uv run python -m ingest inventory`), push it
(`mirror push`), and launch the same instance command from §3. The plan grows
by the new RPs; everything already mirrored is skipped by the ledger.

## 7. What this deliberately does NOT move off the laptop

Local development stays exactly as CLAUDE.md describes: `make test` on the
878 KB fixture, `make dev-data` for two release points of Title 16, samples in
`samples/`. Nothing in daily development requires the mirror or the corpus —
`mirror pull --title N` exists for when a task genuinely needs history.

**Session 8 (bulk load) sizing, when it comes:** parsing 3,197 files into
Postgres wants more than the 1 GB download box. Stop the instance, change type
to `t4g.medium` (4 GB, ~$0.0336/hr), start, and reuse the same volume and
mirror — or run the load locally against a full `mirror pull`. Decide then,
with the measured corpus in hand; the parser streams (gotcha 6), so RAM needs
stay modest either way. A `pg_dump` of the loaded database pushed to
`s3://$BUCKET/usc/db/` would let any machine skip the load entirely — that's
Session 8's call to record.
