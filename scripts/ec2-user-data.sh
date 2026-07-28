#!/bin/bash
# EC2 user-data for the disposable download box (docs/remote-ops.md, ADR-0013).
# Amazon Linux 2023, arm64. Substitute __BUCKET__ before launching:
#
#   sed "s/__BUCKET__/$BUCKET/" scripts/ec2-user-data.sh > /tmp/user-data.sh
#
# Everything of substance lives in the repo (scripts/run-backfill-ec2.sh); this
# file only bootstraps: packages, uv, clone, two systemd units, go.
set -euxo pipefail

dnf install -y git awscli-2

sudo -u ec2-user bash -c '
  curl -LsSf https://astral.sh/uv/install.sh | sh
  cd ~ && git clone https://github.com/aih/uscode-redesign.git
  cd uscode-redesign && ~/.local/bin/uv sync
'

# The run itself: retries on failure, resumes from the ledger, powers off when done.
cat > /etc/systemd/system/usc-backfill.service <<'UNIT'
[Unit]
Description=USC release-point backfill (resumable; powers off when complete)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/uscode-redesign
Environment=USC_MIRROR_BUCKET=__BUCKET__
ExecStart=/home/ec2-user/uscode-redesign/scripts/run-backfill-ec2.sh
Restart=on-failure
RestartSec=300

[Install]
WantedBy=multi-user.target
UNIT

# Hourly push while the run is going: an instance lost mid-run costs <=1h of downloads.
cat > /etc/systemd/system/usc-mirror-push.service <<'UNIT'
[Unit]
Description=Push backfill progress to the S3 mirror

[Service]
Type=oneshot
User=ec2-user
WorkingDirectory=/home/ec2-user/uscode-redesign
Environment=USC_MIRROR_BUCKET=__BUCKET__
Environment=PATH=/home/ec2-user/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/ec2-user/.local/bin/uv run python -m ingest mirror push
UNIT

cat > /etc/systemd/system/usc-mirror-push.timer <<'UNIT'
[Unit]
Description=Hourly mirror push during the backfill

[Timer]
OnBootSec=1h
OnUnitActiveSec=1h

[Install]
WantedBy=timers.target
UNIT

# ec2-user may power the box off (and nothing else) without a password.
echo 'ec2-user ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff' \
  > /etc/sudoers.d/usc-poweroff
chmod 440 /etc/sudoers.d/usc-poweroff

systemctl daemon-reload
systemctl enable --now usc-mirror-push.timer
systemctl enable --now usc-backfill.service
