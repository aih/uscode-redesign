#!/usr/bin/env bash
# The box's schedule, as a file in the repository rather than as three things
# somebody once typed into /etc/cron.d.
#
#   sudo bash deploy/install-crons.sh
#
# Idempotent: it writes /etc/cron.d/uscode whole, every time. Run it after any
# edit here, and on a rebuilt box — bootstrap-box.sh calls it, so a box brought
# up from scratch arrives with its schedule instead of arriving without one and
# looking fine for as long as nobody checks.
#
# Three jobs, and the daily one is the reason this file exists (ADR-0036):
#
#   * DAILY, the source check. Polls uscode.house.gov's release-points page,
#     records the attempt in `source_checks`, and runs the full download-and-load
#     chain only if something new was published. On an ordinary day that is one
#     HTTP request and one row. Daily is the *upper* bound on how often this
#     site asks — the source publishes release points a few dozen times a year,
#     and pulling a static page more often than that would be rude for no gain.
#   * NIGHTLY, the database dump to S3.
#   * WEEKLY, purge_login_failures — the login-throttle table's only reaper.
#
# The weekly full sweep is deliberately NOT here: it lives in
# .github/workflows/update-corpus.yml and dispatches over SSM, so the two
# schedules fail independently. A box whose crond dies still gets its weekly
# sweep; a GitHub schedule that is disabled (Actions turns off scheduled
# workflows on a repository with no activity for 60 days) still leaves the
# daily check running. Neither is a backup of the other, but between them the
# site does not go quietly unchecked.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/ec2-user/uscode-redesign}"
DATA_ROOT="${DATA_ROOT:-/var/lib/uscode}"
MIRROR_BUCKET="${USC_MIRROR_BUCKET:-uscode-mirror-dreamproit}"
CRON_FILE=/etc/cron.d/uscode

if [ "$(id -u)" -ne 0 ]; then
    echo "run this as root — it writes $CRON_FILE" >&2
    exit 1
fi

cat > "$CRON_FILE" <<EOF
# Managed by deploy/install-crons.sh — edit there, not here.
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

# Daily source check (ADR-0036). Runs the full update only when OLRC has
# published a release point this box has not seen. 06:41 UTC: after OLRC's
# usual publishing hours, and an odd minute so it does not land with everything
# else on the box.
41 6 * * * root cd ${REPO_DIR} && sudo -u ec2-user bash deploy/update-corpus.sh >> ${DATA_ROOT}/logs/check.log 2>&1

# Nightly database dump to the mirror bucket.
17 4 * * * root cd ${REPO_DIR} && docker compose -f docker-compose.prod.yml exec -T db pg_dump -U uscode -Fc uscode | aws s3 cp - s3://${MIRROR_BUCKET}/usc/db/uscode-\$(date +\%F).dump >> ${DATA_ROOT}/logs/backup.log 2>&1

# Weekly: expire the login-throttle rows. Nothing else calls this.
23 5 * * 0 root cd ${REPO_DIR} && docker compose -f docker-compose.prod.yml exec -T db psql -U uscode -d uscode -c "select purge_login_failures()" >> ${DATA_ROOT}/logs/purge.log 2>&1
EOF

chmod 0644 "$CRON_FILE"
mkdir -p "${DATA_ROOT}/logs"

echo "wrote $CRON_FILE:"
sed 's/^/    /' "$CRON_FILE"
echo
echo "crond picks up /etc/cron.d changes without a restart; confirm with:"
echo "  systemctl status crond"
