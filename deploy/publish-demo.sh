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

  # Docker gets here first, and it creates mount points as root.
  #
  # `deploy-on-box.sh` runs `compose run api` for the migration before it calls
  # this, and that instantiates the api service — including its volumes — so
  # ${DATA_ROOT}/demo already exists, owned by root, by the time this runs on a
  # box that has never fetched. `mkdir -p` then succeeds (it is already there),
  # and every write fails with EACCES. That is exactly what happened on the
  # first deploy of this feature.
  #
  # Fixing the ownership here rather than reordering the deploy: the order is
  # not the guarantee. Any compose command that touches the api service creates
  # this directory, and a future one placed earlier would silently reintroduce
  # the same failure.
  if [[ ! -d "$DEST" ]]; then
    mkdir -p "$DEST" 2>/dev/null || sudo mkdir -p "$DEST"
  fi
  if [[ ! -w "$DEST" ]]; then
    echo "  ${DEST} is not writable by $(id -un); taking ownership"
    sudo chown "$(id -un):$(id -gn)" "$DEST"
  fi

  failed=0
  for asset in "${ASSETS[@]}"; do
    # Existence and writability are different failures and must not share a
    # message. The first version of this printed "not published yet" for both,
    # so a permission error read as "nobody has recorded a demo" — the deploy
    # log said the reassuring thing while the page 404'd.
    if ! aws s3api head-object --bucket "$MIRROR_BUCKET" --key "usc/demo/${asset}" >/dev/null 2>&1; then
      echo "  ${asset} is not published yet — skipping"
      continue
    fi

    if aws s3 cp "${PREFIX}/${asset}" "${DEST}/${asset}" --only-show-errors; then
      echo "  fetched ${asset}"
    else
      echo "  ERROR: ${asset} is in S3 but could not be written to ${DEST}" >&2
      failed=1
    fi
  done

  # The mount is read-only to the container, so the container cannot be what
  # fixes the mode; do it here.
  chmod -R a+r "$DEST" 2>/dev/null || true
  echo "demo assets in ${DEST}:"
  ls -la "$DEST"

  # Non-zero on a real failure. `deploy-on-box.sh` swallows it deliberately —
  # no demo video should ever fail a deploy — but it will have printed the
  # ERROR line above, which is the difference between a deploy that says
  # nothing and one that says the wrong thing.
  exit "$failed"
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

Uploaded. Now get it onto the box.

USUALLY: nothing. `deploy/deploy-on-box.sh` fetches these assets on every
deploy, so merging to main is enough — CI passes, .github/workflows/deploy.yml
runs, and the box pulls the current video as part of it. That is the path to
use the first time, because the box needs this script and the /app/static/demo
volume mount before either can do anything, and both arrive with the code.

TO PUBLISH A RE-RECORDED VIDEO WITHOUT A CODE DEPLOY, once the above has
happened at least once:

  AWS_PROFILE=uscode-admin aws ssm send-command \
    --instance-ids "$(AWS_PROFILE=uscode-admin aws ec2 describe-instances \
        --filters Name=tag:Name,Values=uscode-site Name=instance-state-name,Values=running \
        --query 'Reservations[].Instances[].InstanceId' --output text)" \
    --document-name AWS-RunShellScript \
    --comment "publish demo video" \
    --parameters 'commands=["sudo -iu ec2-user bash -c '"'"'cd ~/uscode-redesign && bash deploy/publish-demo.sh --fetch'"'"'"]'

Three things that command gets right and the obvious version does not:

  * the profile. SSM is the *deploy* identity (`uscode-admin`, which is the IAM
    user `linkedlegislation-deploy` — see docs/deploy-status.md), not the mirror
    identity that owns the upload above, and not whatever `default` is.
  * --instance-ids, resolved from the tag rather than --targets. A tag-targeted
    command reports an empty invocation list, so it looks like it did nothing;
    .github/workflows/deploy.yml resolves the id first for exactly this reason.
  * the checkout is ~ec2-user/uscode-redesign, reached with `sudo -iu ec2-user`.
    SSM runs commands as root, whose home is not where the repository is.

No container restart is needed for a re-fetch: the mount is a directory, so the
running container reads whatever is in it.
NEXT
