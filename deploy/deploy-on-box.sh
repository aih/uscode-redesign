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

echo "=== migrating (new image, before it serves) ==="
docker compose -f docker-compose.prod.yml run --rm --no-deps api uv run alembic upgrade head

echo "=== bringing the stack up ==="
docker compose -f docker-compose.prod.yml up -d --wait

echo "=== pruning old images ==="
docker image prune -f

echo "=== $(date -u +%FT%TZ) deploy of $TAG complete ==="
