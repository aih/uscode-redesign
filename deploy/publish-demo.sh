#!/usr/bin/env bash
# Publish the demo video to the mirror, so the site box can serve it (ADR-0038).
#
#   bash deploy/publish-demo.sh              # upload static/demo/* to S3
#   bash deploy/publish-demo.sh --fetch      # (on the box) pull them down to $DATA_ROOT/demo
#
# The video is recorded on a workstation, against a fully loaded corpus, by
# `make demo-video`. It cannot be built where the image is built: Actions has
# neither the corpus nor ffmpeg nor a running site, and the file is gitignored
# besides — a 3 MB binary regenerated on every demo does not belong in a history
# meant to be read.
#
# So it travels the way the corpus already travels (ADR-0013): workstation → S3
# → box. The box mounts $DATA_ROOT/demo at /app/static/demo (read-only,
# docker-compose.prod.yml), FastAPI serves it at /static/demo/, and the reader's
# /app/demo page plays it from the same origin — which is what keeps it inside
# `default-src 'self'` with no CSP change (ADR-0030), and what keeps a third
# party out of a site that vendored its own Swagger UI to avoid exactly that
# (ADR-0032).
#
# Credentials: none beyond what already exists. Uploading uses the mirror
# profile that pushes the corpus (`s3:PutObject` on `usc/*`); fetching uses the
# instance role, which already carries `s3:GetObject` and `s3:ListBucket` on the
# whole bucket for `mirror pull` (deploy/admin-grant.sh, Sid S3Mirror).

set -euo pipefail

cd "$(dirname "$0")/.."

MIRROR_BUCKET="${USC_MIRROR_BUCKET:-$(grep -E '^USC_MIRROR_BUCKET=' .env 2>/dev/null | cut -d= -f2- || true)}"
MIRROR_BUCKET="${MIRROR_BUCKET:-uscode-mirror-dreamproit}"
PREFIX="s3://${MIRROR_BUCKET}/usc/demo"

# The three files the page needs, named explicitly rather than synced as a
# directory: `aws s3 sync` on static/demo would also carry up whatever
# intermediates a half-finished run left there.
ASSETS=(uscode-demo.mp4 uscode-demo.vtt poster.png)

command -v aws >/dev/null || { echo "aws CLI not found."; exit 1; }

if [[ "${1:-}" == "--fetch" ]]; then
  DATA_ROOT="${DATA_ROOT:-/var/lib/uscode}"
  DEST="${DATA_ROOT}/demo"
  mkdir -p "$DEST"

  for asset in "${ASSETS[@]}"; do
    if aws s3 cp "${PREFIX}/${asset}" "${DEST}/${asset}" --only-show-errors; then
      echo "  fetched ${asset}"
    else
      # A missing video is a page that says "download it instead", not a failed
      # deploy. This script runs from deploy-on-box.sh, and nothing about the
      # site depends on the demo existing.
      echo "  ${asset} is not published yet — skipping"
    fi
  done

  # The mount is read-only to the container, so the container cannot be what
  # fixes ownership; do it here.
  chmod -R a+r "$DEST" 2>/dev/null || true
  echo "demo assets in ${DEST}:"
  ls -la "$DEST"
  exit 0
fi

# ------------------------------------------------------------------- upload

missing=()
for asset in "${ASSETS[@]}"; do
  [[ -f "static/demo/${asset}" ]] || missing+=("$asset")
done

if (( ${#missing[@]} > 0 )); then
  echo "Missing from static/demo/: ${missing[*]}"
  echo "Run \`make demo-video\` first (needs \`make dev-all\` running and ffmpeg)."
  exit 1
fi

echo "Uploading to ${PREFIX}/ …"
for asset in "${ASSETS[@]}"; do
  # `--content-type` explicitly: S3 guesses from the extension and gets .vtt
  # wrong often enough to matter — a caption track served as binary/octet-stream
  # is a track the browser ignores, silently, with the video playing fine.
  case "$asset" in
    *.mp4) type="video/mp4" ;;
    *.vtt) type="text/vtt" ;;
    *.png) type="image/png" ;;
    *) type="application/octet-stream" ;;
  esac

  aws s3 cp "static/demo/${asset}" "${PREFIX}/${asset}" \
    --content-type "$type" \
    --cache-control "public, max-age=86400" \
    --only-show-errors
  echo "  ${asset} ($(du -h "static/demo/${asset}" | cut -f1), ${type})"
done

cat <<'NEXT'

Uploaded. To put it on the site:

  aws ssm send-command \
    --document-name AWS-RunShellScript \
    --targets Key=tag:Name,Values=uscode-site \
    --parameters 'commands=["cd /opt/uscode && bash deploy/publish-demo.sh --fetch && docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate api"]'

The recreate is needed the first time only, to pick up the new volume mount;
after that a re-fetch is enough, because the mount is a directory and the
container reads through it.
NEXT
