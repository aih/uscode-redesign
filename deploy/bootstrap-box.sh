#!/usr/bin/env bash
# First-boot setup for the site box (docs/deploy.md §3), as a script rather
# than a paste buffer. Run once, over SSM, as root:
#
#   SITE_ADDRESS=uscode.linkedlegislation.org \
#   ECR_REGISTRY=739065237548.dkr.ecr.us-east-1.amazonaws.com \
#   USC_MIRROR_BUCKET=uscode-mirror-dreamproit \
#     bash bootstrap-box.sh
#
# Idempotent throughout: re-running it will not reformat the data volume, will
# not re-clone, and — this is the one that matters — will not regenerate the
# passwords in .env. OpenSearch only honours its admin password on the data
# volume's FIRST boot, so a second .env with a fresh password would leave every
# search 401ing behind a green healthcheck.
set -euo pipefail

SITE_ADDRESS="${SITE_ADDRESS:?set SITE_ADDRESS to the public hostname}"
ECR_REGISTRY="${ECR_REGISTRY:?set ECR_REGISTRY}"
USC_MIRROR_BUCKET="${USC_MIRROR_BUCKET:-uscode-mirror-dreamproit}"
DATA_ROOT="${DATA_ROOT:-/var/lib/uscode}"
REPO_URL="${REPO_URL:-https://github.com/aih/uscode-redesign.git}"
REPO_DIR="/home/ec2-user/uscode-redesign"

echo "==> packages"
dnf install -y docker git >/dev/null
systemctl enable --now docker
usermod -aG docker ec2-user

# AL2023's `docker` package is the engine and CLI only — it ships the buildx
# plugin but not compose, and AL2023's repositories carry no compose package at
# all. Without this, every `docker compose -f ...` on the box fails with
# "unknown shorthand flag: 'f' in -f", because `compose` was never a subcommand
# and docker read the -f as its own.
COMPOSE_PLUGIN=/usr/libexec/docker/cli-plugins/docker-compose
if [ -x "$COMPOSE_PLUGIN" ]; then
    echo "    compose plugin already installed ($("$COMPOSE_PLUGIN" version --short 2>/dev/null))"
else
    echo "    installing the docker compose plugin"
    COMPOSE_TAG="${COMPOSE_TAG:-$(curl -fsSLI -o /dev/null -w '%{url_effective}' \
        https://github.com/docker/compose/releases/latest | sed 's#.*/tag/##')}"
    COMPOSE_URL="https://github.com/docker/compose/releases/download/${COMPOSE_TAG}/docker-compose-linux-$(uname -m)"
    curl -fsSL "$COMPOSE_URL" -o /tmp/docker-compose
    # The release publishes a checksum beside the binary; a download that lands
    # corrupt should fail here rather than at the first deploy.
    if curl -fsSL "${COMPOSE_URL}.sha256" -o /tmp/docker-compose.sha256; then
        expected="$(awk '{print $1}' /tmp/docker-compose.sha256)"
        actual="$(sha256sum /tmp/docker-compose | awk '{print $1}')"
        if [ "$expected" != "$actual" ]; then
            echo "compose checksum mismatch: expected $expected, got $actual" >&2
            exit 1
        fi
        echo "    checksum verified"
    else
        echo "    no published checksum for ${COMPOSE_TAG}; installing unverified" >&2
    fi
    mkdir -p "$(dirname "$COMPOSE_PLUGIN")"
    install -m 0755 /tmp/docker-compose "$COMPOSE_PLUGIN"
    rm -f /tmp/docker-compose /tmp/docker-compose.sha256
    echo "    installed compose ${COMPOSE_TAG}"
fi

echo "==> data volume at $DATA_ROOT"
# The root volume is nvme0n1; the data volume is the other one. Finding it by
# elimination rather than by name because NVMe device order is not guaranteed.
DATA_DEV=""
for dev in /dev/nvme?n1; do
    [ "$dev" = "/dev/nvme0n1" ] && continue
    DATA_DEV="$dev"
    break
done
if [ -z "$DATA_DEV" ]; then
    echo "no second NVMe device found — was the data volume attached?" >&2
    lsblk >&2
    exit 1
fi

if ! blkid "$DATA_DEV" >/dev/null 2>&1; then
    echo "    formatting $DATA_DEV (first boot only)"
    mkfs.ext4 -q "$DATA_DEV"
else
    echo "    $DATA_DEV already has a filesystem — leaving it alone"
fi

mkdir -p "$DATA_ROOT"
if ! grep -q "$DATA_ROOT" /etc/fstab; then
    echo "$DATA_DEV $DATA_ROOT ext4 defaults,nofail 0 2" >> /etc/fstab
fi
mountpoint -q "$DATA_ROOT" || mount -a

mkdir -p "$DATA_ROOT"/{pgdata,releases,manifests,caddy,opensearch,logs}
chown -R ec2-user:ec2-user "$DATA_ROOT"

echo "==> repository at $REPO_DIR"
if [ ! -d "$REPO_DIR/.git" ]; then
    sudo -u ec2-user git clone --quiet "$REPO_URL" "$REPO_DIR"
else
    echo "    already cloned"
fi

echo "==> .env"
ENV_FILE="$REPO_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "    .env exists — keeping it (regenerating SEARCH_PASSWORD would"
    echo "    lock us out of the existing OpenSearch volume)"
else
    # No "admin" in the search password: the image rejects it at boot and says
    # so only in a log line.
    POSTGRES_PASSWORD="$(openssl rand -base64 32 | tr -d '\n')"
    SEARCH_PASSWORD="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)!7q"
    cat > "$ENV_FILE" <<ENVEOF
SITE_ADDRESS=${SITE_ADDRESS}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
SEARCH_PASSWORD=${SEARCH_PASSWORD}
DATA_ROOT=${DATA_ROOT}
USC_MIRROR_BUCKET=${USC_MIRROR_BUCKET}
ECR_REGISTRY=${ECR_REGISTRY}
ENVEOF
    chown ec2-user:ec2-user "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "    written (secrets generated on the box; they are not echoed here"
    echo "    because SSM keeps command output)"
fi

echo "==> schedule"
# The daily source check, the nightly dump and the weekly purge. Installed here
# so a rebuilt box arrives with its schedule: a box with no cron looks healthy
# in every way except that it has quietly stopped checking for new law.
DATA_ROOT="$DATA_ROOT" REPO_DIR="$REPO_DIR" USC_MIRROR_BUCKET="$USC_MIRROR_BUCKET" \
    bash "$REPO_DIR/deploy/install-crons.sh"

echo
echo "Bootstrap complete. Next: deploy/deploy-on-box.sh <sha> to bring the"
echo "stack up, then seed the database (docs/deploy.md §4)."
