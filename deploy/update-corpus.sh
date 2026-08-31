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
#     re-plans the backfill, re-runs the version-change pass and recounts, so a
#     load that half-finished, a change-row backfill that did, or a zip that
#     never made it to S3 is repaired within the week rather than waiting for
#     the next release point to expose it.
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
# mirror push -> load-all -> version-changes -> verify. Every step runs inside
# the `api` container via `docker compose exec`, so the box needs no Python of
# its own.
#
# The classification tables (ADR-0067) are a second source with its own poll and
# its own check table, run first and independently of all of that.
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
MIRROR_BUCKET="$(grep -E '^USC_MIRROR_BUCKET=' .env 2>/dev/null | cut -d= -f2- || true)"
MIRROR_BUCKET="${MIRROR_BUCKET:-uscode-mirror-dreamproit}"

# Set by run_load below: how many title-releases load-all actually wrote. It is
# what decides whether there is anything worth dumping.
LOADED=0

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

# load-all, with its summary line captured so the rest of this script can know
# whether the corpus actually changed. It prints
# `planned N: X loaded, Y skipped, Z failed`, and X is the only honest answer to
# "is a new backup worth 2.2 GB" — the mode this script was called in is not.
# A weekly --force sweep reaches this line having loaded nothing at all on most
# weeks, and a daily poll that found new law reaches it having loaded a handful.
#
# Capturing costs no live output: `--quiet` passes on_event=None, so load-all
# prints its summary at the end and nothing during the run.
run_load() {
    echo "=== $(date -u +%FT%TZ) load-all --quiet ==="
    local out status
    out="$($COMPOSE exec -T api uv run python -m ingest load-all --quiet 2>&1)"
    status=$?
    echo "$out"
    LOADED="$(printf '%s\n' "$out" \
        | sed -n 's/.*planned [0-9]*: \([0-9][0-9]*\) loaded.*/\1/p' | tail -1)"
    # An unparseable summary must not read as "nothing changed" — that is the
    # direction that silently skips a backup. Assume it loaded.
    if ! [[ "$LOADED" =~ ^[0-9]+$ ]]; then
        echo "could not read the loaded count from load-all — assuming it loaded"
        LOADED=1
    fi
    return $status
}

# The classification load, with its summary line captured for the same reason
# run_load captures its own: the version timeline's law attributions (ADR-0074)
# are derived from classification_entries, and redoing them corpus-wide is
# minutes of delete-and-reinsert over 30,250 rows.
#
# `loaded` is not the question. `--force` ignores the content-hash gate, so on
# the weekly sweep every fetched document reads as loaded whether or not OLRC
# edited it — which would reattribute the whole corpus 51 weeks a year and turn
# a transient failure there into a red run on a week when nothing happened.
# `with new content` is the count of documents whose <PRE> text actually
# differs from the loaded copy, which is what a stale attribution needs.
run_classification() {
    echo "=== $(date -u +%FT%TZ) classification $* ==="
    local out status changed
    out="$($COMPOSE exec -T api uv run python -m ingest classification "$@" 2>&1)"
    status=$?
    echo "$out"
    changed="$(printf '%s\n' "$out" \
        | sed -n 's/.*, \([0-9][0-9]*\) with new content.*/\1/p' | tail -1)"
    # An unreadable summary must not read as "nothing changed" — that is the
    # direction that silently leaves the law rows stale. Assume it changed.
    if ! [[ "$changed" =~ ^[0-9]+$ ]]; then
        echo "could not read the changed count from classification — assuming a table moved"
        changed=1
    fi
    if [ "$changed" -gt 0 ]; then
        CLASSIFICATION_CHANGED=1
    fi
    return $status
}

# The database dump, on the mirror (ADR-0013), taken when the corpus changes
# rather than on a clock.
#
# It used to be a nightly cron, which meant ~360 copies a year of a corpus that
# OLRC republishes a few dozen times a year: 2.2 GB a night, about 66 GB a
# month, growing forever. The US Code does not change nightly, so neither
# should the backup. Hanging it off `load-all` ties it to the event that
# actually invalidates the last one.
#
# It dumps everything, accounts included, deliberately — unlike the seed dump
# that built this box, which excluded them so 1,301 test users would not land on
# a public site. Restoring production should restore production.
#
# The box cannot prune what it writes: the instance role has s3:PutObject on
# usc/* and no s3:DeleteObject, so the one writer of the corpus of record cannot
# delete it. That is worth keeping. Retention therefore belongs in an S3
# lifecycle rule set by an admin, and at a few dozen dumps a year it is no
# longer urgent.
#
# `set -o pipefail` at the top of this script is load-bearing here, and it is
# the one thing the nightly cron did not have. `pg_dump | aws s3 cp -` with a
# pg_dump that dies half way is an `aws` that uploads what it got and exits 0:
# a truncated dump, stored under a name that says it is a backup, reported as a
# success. Without pipefail the shell reports the exit status of `aws` alone, so
# the cron line this replaces could have been doing that for as long as it ran.
dump_to_mirror() {
    local key="s3://${MIRROR_BUCKET}/usc/db/uscode-$(date -u +%F).dump"
    echo "=== $(date -u +%FT%TZ) dumping the database to ${key} ==="
    if $COMPOSE exec -T db pg_dump -U uscode -Fc uscode | aws s3 cp - "$key"; then
        echo "dump complete"
        return 0
    fi
    echo "DUMP FAILED — the corpus is still reproducible from the mirror's zips"
    echo "(ADR-0013), but a restore would have to reload rather than pg_restore."
    return 1
}

echo "=== $(date -u +%FT%TZ) corpus update starting (mode: ${MODE}) ==="

# The classification tables (ADR-0067), first and on their own.
#
# They are a second source on the same host, polled by the same three exit
# codes, and nothing below depends on them: the tables record which provision
# of which public law was classified where, and the release-point chain loads
# the Code's text. So this runs before the poll rather than after the load —
# a release-point check that fails exits this script, and burying the
# classification poll behind that would stop recording it for as long as the
# other source was down.
#
# --force sweeps the tables whether or not the covered-law sentence moved,
# which is the weekly repair for a table OLRC edited without extending its
# range. It is the same weekly Actions run that forces the corpus sweep.
CLASSIFICATION_STATUS=0
# Set by run_classification when a load found a document whose <PRE> text
# really differs: the law attributions on the version timeline (ADR-0074) are
# derived from classification_entries, so a changed table invalidates them.
# `--reattribute` recomputes only the attribution and law rows — minutes, no
# XML parsing.
CLASSIFICATION_CHANGED=0
# Set when a version-changes step fails. The rows are re-derivable
# (`--recompute` / `--reattribute`), so a failure warns and the chain goes on;
# it still exits non-zero at the bottom so the run shows up red.
VERSION_CHANGES_STATUS=0
run classification-check
case "$?" in
    0)  echo "no classification table has changed" ;;
    10)
        echo "a classification table has changed"
        if [ "$MODE" = "check-only" ]; then
            echo "check-only: not loading"
        elif ! run_classification --quiet; then
            echo "the classification load failed — see above"
            CLASSIFICATION_STATUS=1
        fi
        ;;
    *)
        echo "the classification check failed — see above"
        CLASSIFICATION_STATUS=1
        ;;
esac

# A forced sweep re-fetches and re-loads every table, ignoring both the
# covered-text gate and the content hash. The check above has already run and
# recorded; this is the repair pass behind it.
if [ "$MODE" = "force" ]; then
    if ! run_classification --force --quiet; then
        echo "the forced classification sweep failed — see above"
        CLASSIFICATION_STATUS=1
    fi
fi

# A changed classification table invalidates the stored law attributions
# (ADR-0074). Attribution-only recompute: touches the law rows and the
# `attribution` column, never the content flags, and parses no XML.
if [ "$CLASSIFICATION_CHANGED" -eq 1 ]; then
    run version-changes --reattribute --quiet || {
        echo "reattribution failed — the law rows are stale until the next run"
        VERSION_CHANGES_STATUS=1
    }
fi

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

# Every early exit carries the classification status, so a poll or a load that
# failed up there is a red run rather than a line in a log nobody reads — the
# same reason a failed dump exits non-zero at the bottom of this script.
if [ "$MODE" = "check-only" ]; then
    echo "=== $(date -u +%FT%TZ) check complete (check-only) ==="
    exit "$((CLASSIFICATION_STATUS || VERSION_CHANGES_STATUS))"
fi
if [ "$MODE" != "force" ] && [ "$CHECK_STATUS" -eq 0 ]; then
    echo "=== $(date -u +%FT%TZ) nothing to do ==="
    exit "$((CLASSIFICATION_STATUS || VERSION_CHANGES_STATUS))"
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
run_load || { echo "load-all failed"; exit 1; }
# The change rows and law attributions for what the load just wrote
# (ADR-0074). load-all's own hook keeps them current and warns without failing
# the load, so this is the repair pass behind it: sections whose rows are
# already complete are skipped, making it a fast complete-check when the hook
# succeeded. Runs before the dump so the dump carries the rows.
#
# A forced sweep runs it whether or not anything loaded, which is the whole
# point of the weekly --force this script's header describes: a backfill that
# half finished — the box's owed one-time run, killed by a deploy recreating
# the api container (docs/deploy-status.md) — leaves sections with no change
# rows at all, and nothing surfaces that. `versions()` degrades a missing
# annotation to None, so the reader silently falls back to listing every
# recorded version. On the ~51 weeks a year that load nothing and have nothing
# to repair, this is the skip scan and no writes.
if [ "$LOADED" -gt 0 ] || [ "$MODE" = "force" ]; then
    run version-changes --quiet || {
        echo "version-changes failed — the rows are re-derivable; rerun by hand"
        echo "or let the next load repair them"
        VERSION_CHANGES_STATUS=1
    }
fi
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

# Back up only what changed, and only after `verify` has said the load is sound
# — a dump taken before that gate could preserve exactly the corruption the gate
# exists to catch, and it would be the copy someone restores from.
DUMP_STATUS=0
if [ "$LOADED" -gt 0 ]; then
    dump_to_mirror || DUMP_STATUS=1
else
    echo "=== nothing loaded — no dump; the last one is still current ==="
fi

echo "=== $(date -u +%FT%TZ) corpus update complete ==="

# A failed backup exits non-zero even though the corpus loaded fine, so it shows
# up as a red weekly run rather than as a line in a log nobody reads. A failed
# classification poll or load, or a failed version-changes pass, reads the same
# way.
if [ "$DUMP_STATUS" -ne 0 ]; then
    exit "$DUMP_STATUS"
fi
exit "$((CLASSIFICATION_STATUS || VERSION_CHANGES_STATUS))"
