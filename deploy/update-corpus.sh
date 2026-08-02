#!/usr/bin/env bash
# The corpus refresh on the site box (ADR-0013, ADR-0020, ADR-0036).
#
#   bash deploy/update-corpus.sh              # poll; update only if there is something new
#   bash deploy/update-corpus.sh --check-only # poll and record, never download or load
#   bash deploy/update-corpus.sh --force      # run the whole chain regardless
#
# Two schedules call it, on purpose (ADR-0036):
#
#   * daily, from /etc/cron.d/uscode (deploy/install-crons.sh) with no
#     arguments. That is one HTTP request to uscode.house.gov's release-points
#     page, a `source_checks` row, and — on the ~360 days a year when OLRC has
#     published nothing new — nothing else at all.
#   * weekly, from .github/workflows/update-corpus.yml with --force. A full
#     sweep whether or not the daily poll saw anything: it re-pulls the mirror,
#     re-plans the backfill and recounts, so a load that half-finished or a zip
#     that never made it to S3 is repaired within the week rather than waiting
#     for the next release point to expose it.
#
# The daily poll is why `--out` points somewhere disposable. `mirror pull`
# overwrites data/uscreleasepoints.json with S3's copy, so a poll that wrote
# the canonical inventory would have it clobbered by the very next step of the
# full chain — and backfill would then plan from the stale list, missing the
# release point the poll had just found. The poll writes a scratch file; the
# full chain fetches the inventory again for itself, in the order that has
# always worked.
#
# Chain when there IS something new: mirror pull -> inventory -> backfill ->
# mirror push -> load-all -> verify. Every step runs inside the `api` container
# via `docker compose exec`, so the box needs no Python of its own.
#
# data/uscreleasepoints.json is ephemeral inside the container: only
# data/releases and data/manifests are volume-mounted (docker-compose.prod.yml),
# not the inventory JSON. That means the chain has to happen as one script run,
# not split across invocations days apart — a fresh container would have no
# inventory to resume from. If a deploy recreates the `api` container mid-run,
# that kills whatever `exec` was in flight; recovery is the backfill ledger and
# the database's own resume state (title_versions.sections_loaded), both durable
# on the mounted volumes, so the next scheduled or manual run picks up rather
# than redoing everything.
#
# The site box is now the mirror's one writer (ADR-0013 handoff, ADR-0020
# decision 6): the instance role's S3 grant includes PutObject under
# usc/*, unlike a plain read-only mirror consumer.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

MODE="auto"
case "${1:-}" in
    --check-only) MODE="check-only" ;;
    --force)      MODE="force" ;;
    "")           ;;
    *) echo "usage: $0 [--check-only|--force]" >&2; exit 2 ;;
esac

DATA_ROOT="$(grep -E '^DATA_ROOT=' .env 2>/dev/null | cut -d= -f2- || true)"
DATA_ROOT="${DATA_ROOT:-/var/lib/uscode}"

mkdir -p "$DATA_ROOT/logs"
LOG_FILE="$DATA_ROOT/logs/update-$(date +%F).log"
exec > >(tee -a "$LOG_FILE") 2>&1

exec 9>"$DATA_ROOT/update.lock"
if ! flock -n 9; then
    echo "update already running; overlapping scheduled run is a no-op"
    exit 0
fi

COMPOSE="docker compose -f docker-compose.prod.yml"

run() {
    echo "=== $(date -u +%FT%TZ) $* ==="
    $COMPOSE exec -T api uv run python -m ingest "$@"
}

# Whether the last recorded check is one this site would still call current —
# the same rule `/api/v1/status` and the reader's currency note apply
# (storage.SOURCE_CHECK_STALE_AFTER), asked of the repository rather than
# reimplemented in shell. Published to CloudWatch so a checker that has
# silently stopped is an alarm rather than a thing nobody notices; the alarm
# treats missing data as breaching, so a box that never publishes at all is
# just as loud as one publishing 1 (deploy/alarms.sh).
publish_staleness() {
    local stale
    stale="$($COMPOSE exec -T api python -c "
from db.base import SessionLocal
from storage.postgres import PostgresRepository
with SessionLocal() as session:
    check = PostgresRepository(session).last_source_check()
print(1 if check is None or check.is_stale() else 0)
" 2>/dev/null | tr -d '[:space:]')"

    if ! [[ "$stale" =~ ^[01]$ ]]; then
        echo "could not determine staleness (got '${stale}') — publishing 1"
        stale=1
    fi

    local instance_id
    instance_id="$(curl -s --max-time 2 -X PUT "http://169.254.169.254/latest/api/token" \
        -H "X-aws-ec2-metadata-token-ttl-seconds: 60" \
        | xargs -I{} curl -s --max-time 2 -H "X-aws-ec2-metadata-token: {}" \
            http://169.254.169.254/latest/meta-data/instance-id)"
    if [ -z "$instance_id" ]; then
        echo "no instance id from IMDS — skipping the CloudWatch metric"
        return 0
    fi

    aws cloudwatch put-metric-data --namespace USCode \
        --metric-name SourceCheckStale --value "$stale" --unit None \
        --dimensions "InstanceId=${instance_id}" --region "${AWS_REGION:-us-east-1}" \
        && echo "published USCode/SourceCheckStale=${stale}"
}

echo "=== $(date -u +%FT%TZ) corpus update starting (mode: ${MODE}) ==="

# The poll. One request to uscode.house.gov, one source_checks row whatever
# happens, and an exit code that says whether there is work: 0 nothing new,
# 10 new release points, 1 the check itself failed.
run check --out data/check-inventory.json
CHECK_STATUS=$?
publish_staleness

case "$CHECK_STATUS" in
    0)  echo "no new release points" ;;
    10) echo "new release points published" ;;
    *)
        echo "the check failed — see above"
        # A failed poll is not a reason to skip a forced sweep: the sweep
        # repairs the corpus we already have, and needs no fresh inventory to
        # do it. It IS a reason to stop the automatic path, which has nothing
        # to act on.
        [ "$MODE" = "force" ] || exit 1
        ;;
esac

if [ "$MODE" = "check-only" ]; then
    echo "=== $(date -u +%FT%TZ) check complete (check-only) ==="
    exit 0
fi
if [ "$MODE" != "force" ] && [ "$CHECK_STATUS" -eq 0 ]; then
    echo "=== $(date -u +%FT%TZ) nothing to do ==="
    exit 0
fi

# Pull BEFORE anything else, exactly as scripts/run-backfill-ec2.sh does, and
# for two reasons that both bite on a box seeded from a pg_dump rather than by
# load-all:
#
#   - backfill skips what the ledger settles and adopts what is on disk. This
#     box has neither, so without a pull it would plan the whole corpus —
#     ~3,197 downloads at one request per second, which is 40-50 hours of
#     hammering uscode.house.gov for files the mirror already holds.
#   - `mirror push` writes ledger.json with `cp`, unconditionally. A ledger
#     built from a partial local corpus would overwrite the complete one in
#     S3. The zips survive that (push syncs without --delete) and the bucket
#     is versioned, but the ledger is the corpus index of record (ADR-0013)
#     and should not need recovering.
run mirror pull || { echo "mirror pull failed"; exit 1; }
# Re-fetched rather than reusing the poll's scratch copy: `mirror pull` has
# just overwritten data/uscreleasepoints.json with S3's, and this is the step
# that puts the current one back — both on disk and in `release_points`. It
# records a second source_check, which is correct; it is a second real request.
run inventory || { echo "inventory failed"; exit 1; }
run backfill --quiet || { echo "backfill failed"; exit 1; }
run mirror push || { echo "mirror push failed"; exit 1; }
# Incremental: resume state is the database (title_versions.sections_loaded),
# not a second ledger. Search stays in step automatically inside
# ingest/load.py (sync_sections + retire_versions) — no separate reindex step.
run load-all --quiet || { echo "load-all failed"; exit 1; }
# Shallow recount; the summary lands in this log rather than a committed
# report (--deep re-parses every source file and is what `make verify-deep`
# is for, not a weekly job).
#
# `ingest verify` exits non-zero whenever `report.sound` is false, and sound is
# false if there are ANY count mismatches — which on this corpus there always
# are: six, where the source publishes several elements under one @identifier
# (ADR-0021), documented in CLAUDE.md and deliberately reported rather than
# smoothed away. Gating the weekly job on that exit code would fail it every
# week forever, which is worse than not checking at all: an alert that always
# fires is an alert nobody reads.
#
# So take the exit code as advisory and gate on the two things in the report
# that mean something is actually wrong — source mismatches (the recount
# disagrees with the source XML) and incomplete loads.
run verify || true
echo "=== $(date -u +%FT%TZ) verify gate ==="
$COMPOSE exec -T api python -c "
import json, sys
d = json.load(open('docs/verification/database.json'))
counts = len(d['count_mismatches'])
source = len(d['source_mismatches'])
incomplete = len(d['incomplete_loads'])
print(f'  count mismatches: {counts} (ADR-0021, expected)')
print(f'  source mismatches: {source}')
print(f'  incomplete loads: {incomplete}')
if source or incomplete:
    print('  FAILING: the recount disagrees with the source, or a load did not finish')
    sys.exit(1)
print('  ok — nothing here that ADR-0021 does not already account for')
" || { echo "verify gate failed — read the mismatches above"; exit 1; }

# Re-published after a successful chain: the load may have taken hours, and the
# value from before it started is the wrong one to leave behind.
publish_staleness

echo "=== $(date -u +%FT%TZ) corpus update complete ==="
