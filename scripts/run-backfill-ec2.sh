#!/usr/bin/env bash
# The unattended backfill cycle on the EC2 download box (docs/remote-ops.md).
#
#   pull (resume state) -> backfill -> verify -> push -> power off if complete
#
# Run by the usc-backfill systemd unit as ec2-user. Restart=on-failure gives
# retries at the process level; the backfill itself resumes from the ledger, so
# a crash costs at most one file. On clean completion the instance powers
# itself off, which stops the billing — an on-demand box that forgets to die is
# the main way a "budget-friendly" design stops being one.
#
# Requires: USC_MIRROR_BUCKET in the environment (the systemd unit sets it).
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

echo "=== $(date -u +%FT%TZ) pull resume state from s3://${USC_MIRROR_BUCKET} ==="
uv run python -m ingest mirror pull --no-verify || exit 1

if [ ! -f data/uscreleasepoints.json ]; then
    echo "=== no inventory on the mirror; fetching from uscode.house.gov ==="
    uv run python -m ingest inventory --no-seed || exit 1
fi

echo "=== $(date -u +%FT%TZ) backfill ==="
uv run python -m ingest backfill --quiet
backfill_rc=$?

echo "=== $(date -u +%FT%TZ) verify (deep) ==="
uv run python -m ingest verify-downloads --deep
verify_rc=$?

echo "=== $(date -u +%FT%TZ) push to mirror ==="
uv run python -m ingest mirror push || exit 1

if [ "$backfill_rc" -eq 0 ]; then
    echo "=== backfill complete (verify rc=$verify_rc); powering off ==="
    sudo systemctl poweroff
else
    echo "=== backfill incomplete (rc=$backfill_rc); systemd will retry ==="
fi
exit "$backfill_rc"
