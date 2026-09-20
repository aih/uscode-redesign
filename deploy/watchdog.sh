#!/usr/bin/env bash
# Is the site answering, and if it has stopped, make it answer again.
#
#   bash deploy/watchdog.sh          # one probe; cron runs it every minute
#   PROBE_ONLY=1 bash deploy/watchdog.sh   # report, never restart
#
# Installed by deploy/install-crons.sh. It exists because of 2026-08-19
# (ADR-0073): the site served nothing for about ten hours while every alarm on
# it read OK. The api container's own healthcheck had noticed — a failing
# streak of 2,710 by the time anyone looked — and noticing was all it did,
# because a Docker healthcheck's only effect is the word `unhealthy` in
# `docker ps`. Nothing acts on it. This is the thing that acts on it.
#
# Two jobs, deliberately in one script so they cannot disagree about whether
# the site is up:
#
#   1. Publish USCode/SiteUp to CloudWatch, so the alarm that pages a human is
#      driven by an end-to-end request rather than by CPU. The alarm treats
#      missing data as breaching, because a box too wedged to run this cron is
#      the case the alarm most needs to catch, and it publishes nothing at all.
#   2. Restart the stack's HTTP services after $FAIL_THRESHOLD consecutive
#      failures.
#
# The probe goes through the edge over the real hostname with --resolve, not
# to a container port: the shared Caddy on 127.0.0.1:443 forwards to this
# project's proxy by hostname (docs/deploy.md §9), that proxy's Caddyfile has
# one site block matched on the hostname in $SITE_ADDRESS, so any other Host
# gets a 404 that would look like an outage, and going through both proxies
# is what makes this measure what a reader gets.
#
# What it restarts is this project's HTTP services and never the edge. The
# edge belongs to the statutes repository's compose project and serves the
# other site too; when nothing listens on 127.0.0.1:443 the log says so and
# no restart is attempted, since none of this project's services can bring
# the edge back.
set -uo pipefail
cd "$(dirname "$0")/.."

DATA_ROOT="$(grep -E '^DATA_ROOT=' .env 2>/dev/null | cut -d= -f2- || true)"
DATA_ROOT="${DATA_ROOT:-/var/lib/uscode}"
SITE_ADDRESS="$(grep -E '^SITE_ADDRESS=' .env 2>/dev/null | cut -d= -f2- || true)"
# The hostname alone: `http://uscode.linkedlegislation.org:8000` behind the
# edge and the bare `uscode.linkedlegislation.org` before it both give
# `uscode.linkedlegislation.org`.
SITE_HOST="${SITE_ADDRESS#*://}"
SITE_HOST="${SITE_HOST%%/*}"
SITE_HOST="${SITE_HOST%%:*}"
REGION="${AWS_REGION:-us-east-1}"

# The reader's cookie gate (ADR-0088) answers 403 to a request for /app that
# carries no cookie, which is what this probe is. Without these two lines the
# watchdog would read the gate as the site being down and recreate the
# containers every ten minutes, for ever. The values are the proxy's own, from
# the same .env the proxy reads them from.
GATE_COOKIE="$(grep -E '^USC_GATE_COOKIE=' .env 2>/dev/null | cut -d= -f2- || true)"
GATE_COOKIE="${GATE_COOKIE:-usc_h}"
GATE_TOKEN="$(grep -E '^USC_GATE_TOKEN=' .env 2>/dev/null | cut -d= -f2- || true)"
GATE_TOKEN="${GATE_TOKEN:-1}"

STATE_DIR="${DATA_ROOT}/watchdog"
STATE_FILE="${STATE_DIR}/consecutive-failures"
LAST_RESTART_FILE="${STATE_DIR}/last-restart"
LOG="${DATA_ROOT}/logs/watchdog.log"

# Three minutes of failure before acting. One is noise — a deploy recreating
# the proxy drops connections for about a second, and a single slow response
# under load is not an outage. Ten hours is what the absence of this cost.
FAIL_THRESHOLD="${FAIL_THRESHOLD:-3}"
# Don't restart more than once every ten minutes. A restart that did not fix it
# will not fix it on the second try either, and a loop of them turns a degraded
# site into one that is never up long enough to diagnose.
RESTART_COOLDOWN="${RESTART_COOLDOWN:-600}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-10}"

mkdir -p "$STATE_DIR" "${DATA_ROOT}/logs"

log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

if [ -z "$SITE_HOST" ]; then
    log "no hostname in SITE_ADDRESS (${SITE_ADDRESS:-unset}) in .env — cannot probe"
    exit 1
fi

# Both surfaces, because they fail independently and either one being down is
# the site being down to somebody: /health is FastAPI, the reader path is Astro
# calling FastAPI, which is the shape that actually broke.
#
# Prints the status code, or `refused` when nothing accepted the connection on
# 127.0.0.1:443 (curl exit 7): the edge is down, or, in the shape before the
# edge, this project's proxy is not running.
probe() {
    local path="$1" code
    code="$(curl -sS -o /dev/null --max-time "$PROBE_TIMEOUT" \
        --resolve "${SITE_HOST}:443:127.0.0.1" \
        -b "${GATE_COOKIE}=${GATE_TOKEN}" \
        -w '%{http_code}' "https://${SITE_HOST}${path}" 2>/dev/null)"
    if [ "$?" -eq 7 ]; then
        echo refused
    else
        echo "$code"
    fi
}

API_CODE="$(probe /health)"
APP_CODE="$(probe /app/us/usc/t16/s45f)"

if [ "$API_CODE" = "200" ] && [ "$APP_CODE" = "200" ]; then
    UP=1
else
    UP=0
fi

# IMDSv2, the same way deploy/update-corpus.sh gets it, cached because this
# runs every minute and the id does not change while the box is up.
instance_id() {
    if [ -s "${STATE_DIR}/instance-id" ]; then
        cat "${STATE_DIR}/instance-id"
        return 0
    fi
    local id
    id="$(curl -sX PUT --max-time 2 http://169.254.169.254/latest/api/token \
        -H "X-aws-ec2-metadata-token-ttl-seconds: 60" \
        | xargs -I{} curl -s --max-time 2 -H "X-aws-ec2-metadata-token: {}" \
            http://169.254.169.254/latest/meta-data/instance-id)"
    [ -n "$id" ] && echo "$id" > "${STATE_DIR}/instance-id"
    echo "$id"
}

# Publish first and unconditionally. If the restart below hangs or the box is
# short of resources, the metric has already left — which is the difference
# between an alarm that fires and a silent outage.
INSTANCE_ID="$(instance_id)"
if [ -z "$INSTANCE_ID" ]; then
    log "no instance id from IMDS — cannot publish SiteUp=$UP"
elif ! aws cloudwatch put-metric-data --region "$REGION" \
        --namespace USCode --metric-name SiteUp --value "$UP" --unit None \
        --dimensions "InstanceId=${INSTANCE_ID}" 2>>"$LOG"; then
    log "could not publish SiteUp=$UP"
fi

FAILURES=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
case "$FAILURES" in ''|*[!0-9]*) FAILURES=0 ;; esac

if [ "$UP" = "1" ]; then
    if [ "$FAILURES" -gt 0 ]; then
        log "recovered after $FAILURES failed probes (api=$API_CODE app=$APP_CODE)"
    fi
    echo 0 > "$STATE_FILE"
    exit 0
fi

FAILURES=$((FAILURES + 1))
echo "$FAILURES" > "$STATE_FILE"
log "probe failed ($FAILURES/$FAIL_THRESHOLD): api=$API_CODE app=$APP_CODE"

[ -n "${PROBE_ONLY:-}" ] && exit 1
[ "$FAILURES" -lt "$FAIL_THRESHOLD" ] && exit 1

# Nothing on 127.0.0.1:443 is the edge, not this site's backends. Restarting
# them would not bring it back and would interrupt whatever update-corpus.sh
# is running inside api (ADR-0035).
if [ "$API_CODE" = "refused" ] && [ "$APP_CODE" = "refused" ]; then
    log "nothing listens on 127.0.0.1:443 (the edge; before the edge, this project's proxy) — not restarting"
    exit 1
fi

# Never restart underneath a deploy. deploy-on-box.sh holds this lock for its
# whole run, and a deploy legitimately makes the site unavailable for a few
# seconds while it recreates containers — restarting into that is how a healthy
# deploy becomes a broken one.
exec 9>"${DATA_ROOT}/deploy.lock"
if ! flock -n 9; then
    log "a deploy holds the lock — not restarting"
    exit 1
fi

NOW=$(date +%s)
LAST=$(cat "$LAST_RESTART_FILE" 2>/dev/null || echo 0)
case "$LAST" in ''|*[!0-9]*) LAST=0 ;; esac
if [ $((NOW - LAST)) -lt "$RESTART_COOLDOWN" ]; then
    log "restarted $((NOW - LAST))s ago — inside the ${RESTART_COOLDOWN}s cooldown, leaving it alone"
    exit 1
fi

# api and frontend, and this project's own proxy. Behind the edge a wedged
# inner Caddy answers the probe as a 502 from the edge, and this script is the
# only thing that acts on that; the restart is cheap now that the proxy holds
# no TLS listener and issues no certificate. `restart` keeps the container, so
# its `edge` network attachment and the `uscode-proxy` alias survive. The
# edge itself is never restarted from here.
echo "$NOW" > "$LAST_RESTART_FILE"
log "restarting api, frontend and proxy after $FAILURES failed probes"
docker compose -f docker-compose.prod.yml restart api frontend proxy >>"$LOG" 2>&1
log "restart returned $?"

sleep 20
API_CODE="$(probe /health)"
APP_CODE="$(probe /app/us/usc/t16/s45f)"
if [ "$API_CODE" = "200" ] && [ "$APP_CODE" = "200" ]; then
    log "site answering again after restart"
    echo 0 > "$STATE_FILE"
    exit 0
fi

log "still failing after restart: api=$API_CODE app=$APP_CODE"
exit 1
