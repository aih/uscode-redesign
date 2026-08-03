#!/usr/bin/env bash
# Runs ON the site box (ADR-0020) after a push to main builds and pushes new
# images. Invoked by .github/workflows/deploy.yml over SSM as ec2-user:
#
#   bash deploy/deploy-on-box.sh <image-tag>
#
# Pulls the tagged images, migrates the database with the NEW image before it
# serves anything, brings the stack up, and prunes. Everything logs to
# $DATA_ROOT/logs/deploy.log so a failed SSM command still leaves a trail on
# the box. flock keeps two overlapping deploys (a re-run while one is still
# migrating) from racing each other.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:?usage: deploy-on-box.sh <image-tag>}"

# .env lives beside docker-compose.prod.yml (not committed); defaults mirror
# its documented contract.
DATA_ROOT="$(grep -E '^DATA_ROOT=' .env 2>/dev/null | cut -d= -f2- || true)"
DATA_ROOT="${DATA_ROOT:-/var/lib/uscode}"
ECR_REGISTRY="$(grep -E '^ECR_REGISTRY=' .env 2>/dev/null | cut -d= -f2- || true)"
if [ -z "$ECR_REGISTRY" ]; then
    echo "ECR_REGISTRY not set in .env" >&2
    exit 1
fi

mkdir -p "$DATA_ROOT/logs"
exec > >(tee -a "$DATA_ROOT/logs/deploy.log") 2>&1

exec 9>"$DATA_ROOT/deploy.lock"
if ! flock -n 9; then
    echo "deploy already running"
    exit 1
fi

echo "=== $(date -u +%FT%TZ) deploying $TAG ==="

aws ecr get-login-password --region us-east-1 \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Pin the deployed tag in .env so a later manual `docker compose up -d` (a
# reboot, a manual restart) reuses this sha rather than silently reverting to
# whatever :latest happens to be at that moment.
if grep -qE '^IMAGE_TAG=' .env 2>/dev/null; then
    sed -i.bak "s/^IMAGE_TAG=.*/IMAGE_TAG=${TAG}/" .env && rm -f .env.bak
else
    echo "IMAGE_TAG=${TAG}" >> .env
fi

echo "=== pulling images ==="
docker compose -f docker-compose.prod.yml pull api frontend

# --no-deps below means the migration container starts nothing for itself, so
# the database has to already be up: true on every redeploy, false on a first
# bring-up. Starting db and opensearch first (and waiting on their
# healthchecks) makes this script the same command in both cases.
echo "=== starting stateful services ==="
docker compose -f docker-compose.prod.yml up -d --wait db opensearch

echo "=== migrating (new image, before it serves) ==="
docker compose -f docker-compose.prod.yml run --rm --no-deps api uv run alembic upgrade head

echo "=== bringing the stack up ==="
docker compose -f docker-compose.prod.yml up -d --wait

# deploy/Caddyfile is a bind mount, and compose recreates a container when the
# *service definition* changes — a mounted file's bytes are not that. Caddy
# reads its config once, at start. So without this step a Caddyfile change
# reaches the box (the workflow does `git checkout --force`), the deploy
# reports success, and the proxy goes on serving the config it booted with:
# a green deploy that changed nothing, which is the kind that gets diagnosed
# twice because nothing looks wrong.
#
# It has to be `--force-recreate` and not `caddy reload`, which is the obvious
# and wrong answer. A single-file bind mount binds an *inode*, not a path, and
# `git checkout --force` replaces the file rather than rewriting it in place —
# so the new bytes land on a new inode that nothing in the container is
# looking at. Measured, editing the file under a running container: `docker
# inspect` still lists the mount, while inside the container
# `/etc/caddy/Caddyfile` is gone entirely and `/etc/caddy` is empty. On Linux
# the same divergence shows up as the old contents persisting instead. Either
# way `caddy reload --config /etc/caddy/Caddyfile` reloads a file that is not
# the one in the repository, and exits 0 having done so — the failure above,
# now with a reassuring log line over it. Recreating the container remounts
# the path and is the only thing that reliably picks up the edit.
#
# The cost is real and small: recreating the proxy drops in-flight connections
# for about a second, on a deploy that has already restarted both backends.
# Certificates live on the /data volume, so nothing re-does ACME.
echo "=== recreating the proxy so it picks up deploy/Caddyfile ==="
docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate proxy

# Prove it rather than assume it: what the proxy is *serving* is the only
# evidence that the step above did anything, and this is a deploy script whose
# whole failure mode is looking successful.
#
# It has to ask for the real hostname, not localhost — the Caddyfile has one
# site block, matched on $SITE_ADDRESS, so a request with any other Host gets a
# 404 from Caddy and would fail this check while the site was perfectly
# healthy. `--resolve` keeps the request on the box rather than sending it out
# to DNS and back, so this measures this instance and not whatever the world
# currently points at. Asserting the directive rather than the status code is
# the point: a 200 would also be returned by the previous config's 404 handler
# had this route ever been dropped.
SITE_ADDRESS="$(grep -E '^SITE_ADDRESS=' .env 2>/dev/null | cut -d= -f2- || true)"
if [ -n "$SITE_ADDRESS" ]; then
    echo "=== checking the proxy serves the current Caddyfile ==="
    curl -sfL --retry 5 --retry-delay 2 --retry-all-errors \
        --resolve "${SITE_ADDRESS}:443:127.0.0.1" \
        "https://${SITE_ADDRESS}/robots.txt" | grep -qx 'Disallow: /'
    echo "robots.txt served as expected"
fi

echo "=== pruning old images ==="
docker image prune -f

echo "=== $(date -u +%FT%TZ) deploy of $TAG complete ==="
