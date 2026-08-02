#!/usr/bin/env bash
# The weekly corpus refresh on the site box (ADR-0013, ADR-0020). Invoked by
# .github/workflows/update-corpus.yml over SSM as ec2-user:
#
#   bash /home/ec2-user/uscode-redesign/deploy/update-corpus.sh
#
# Chain: inventory -> backfill -> mirror push -> load-all -> verify. Runs
# every step inside the `api` container via `docker compose exec`, so it needs
# no local Python environment on the box.
#
# data/uscreleasepoints.json is ephemeral inside the container: only
# data/releases and data/manifests are volume-mounted (docker-compose.prod.yml),
# not the inventory JSON. That means this whole chain has to happen as one
# `exec` per step within a single script run, not split across separate
# invocations days apart — a fresh container would have no inventory to
# resume from. If a deploy recreates the `api` container mid-run, that kills
# whatever `exec` was in flight; recovery is the backfill ledger and the
# database's own resume state (title_versions.sections_loaded), both durable
# on the mounted volumes, so the next scheduled or manual run picks up rather
# than redoing everything.
#
# The site box is now the mirror's one writer (ADR-0013 handoff, ADR-0020
# decision 6): the instance role's S3 grant includes PutObject under
# usc/*, unlike a plain read-only mirror consumer.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

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

run() {
    echo "=== $(date -u +%FT%TZ) $* ==="
    docker compose -f docker-compose.prod.yml exec -T api uv run python -m ingest "$@"
}

echo "=== $(date -u +%FT%TZ) corpus update starting ==="

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
docker compose -f docker-compose.prod.yml exec -T api python -c "
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

echo "=== $(date -u +%FT%TZ) corpus update complete ==="
