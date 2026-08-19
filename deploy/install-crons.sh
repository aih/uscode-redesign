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
# Three jobs. The daily one is the reason this file was written (ADR-0036);
# the every-minute one is the reason it was edited (ADR-0073):
#
#   * DAILY, the source check. Polls uscode.house.gov's release-points page,
#     records the attempt in `source_checks`, and runs the full download-and-load
#     chain only if something new was published. On an ordinary day that is one
#     HTTP request and one row. Daily is the *upper* bound on how often this
#     site asks — the source publishes release points a few dozen times a year,
#     and pulling a static page more often than that would be rude for no gain.
#   * WEEKLY, purge_login_failures — the login-throttle table's only reaper.
#   * EVERY MINUTE, the watchdog. It probes the site through the proxy,
#     publishes USCode/SiteUp, and restarts the HTTP services after three
#     consecutive failures. On 2026-08-19 the site served nothing for about ten
#     hours: the api container's healthcheck had a failing streak of 2,710 and
#     every CloudWatch alarm read OK, because the alarms watch the box — CPU,
#     disk, network — and the box was fine. Nothing was watching whether the
#     site answered.
#
#     Every minute is not aggressive for a probe that costs two local HTTP
#     requests, and the threshold rather than the period is what keeps it from
#     acting on noise.
#
# The database dump used to be a third job, nightly. It is not here any more and
# that is not an omission: the US Code changes a few dozen times a year, so a
# nightly dump was ~360 near-identical 2.2 GB copies a year — about 66 GB a
# month, growing forever — of a corpus that had not moved. It now runs at the
# end of deploy/update-corpus.sh, gated on load-all having actually written
# something, which is the event that invalidates the previous dump. Backups
# follow the data rather than the clock.
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

# The nightly database dump used to be here. It now runs from
# deploy/update-corpus.sh when load-all has actually loaded something — see the
# note at the top of this file.

# Weekly: expire the login-throttle rows. Nothing else calls this.
23 5 * * 0 root cd ${REPO_DIR} && docker compose -f docker-compose.prod.yml exec -T db psql -U uscode -d uscode -c "select purge_login_failures()" >> ${DATA_ROOT}/logs/purge.log 2>&1

# Every minute: is the site answering, and if not, make it answer (ADR-0073).
# It writes its own log and takes the deploy lock before restarting anything,
# so this line stays quiet — a probe that succeeds prints nothing.
* * * * * root cd ${REPO_DIR} && sudo -u ec2-user bash deploy/watchdog.sh >/dev/null 2>&1
EOF

chmod 0644 "$CRON_FILE"
mkdir -p "${DATA_ROOT}/logs"

echo "wrote $CRON_FILE:"
sed 's/^/    /' "$CRON_FILE"
echo
echo "crond picks up /etc/cron.d changes without a restart; confirm with:"
echo "  systemctl status crond"
