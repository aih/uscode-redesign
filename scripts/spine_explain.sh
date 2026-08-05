#!/usr/bin/env bash
#
# Run scripts/spine_explain.py against the deployed corpus and commit the plans.
#
# The plans have to come from the real database: on a laptop with two release
# points of one title, every one of these queries is an index scan over a few
# thousand rows and the planner would tell you nothing about the 96,185,732-row
# `guid_map`. The box is SSM-only (docs/deploy-status.md), so this ships the
# script there, runs it inside the api container — the only place with both the
# application code and the corpus — and brings the JSON back.
#
# gzip + base64 on the way back because `ssm get-command-invocation` truncates
# at 24,000 characters, and a truncated plan reads as a short one.
#
# Usage:  scripts/spine_explain.sh
#         INSTANCE=i-… AWS_PROFILE=… OUT=… scripts/spine_explain.sh

set -euo pipefail

INSTANCE="${INSTANCE:-i-06b433caacd78fd96}"
AWS_PROFILE="${AWS_PROFILE:-uscode-admin}"
CONTAINER="${CONTAINER:-uscode-redesign-api-1}"
OUT="${OUT:-docs/verification/spine-explain.json}"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
payload=$(base64 < "$here/spine_explain.py" | tr -d '\n')

remote=$(cat <<REMOTE
set -euo pipefail
echo $payload | base64 -d > /tmp/spine_explain.py
docker cp /tmp/spine_explain.py $CONTAINER:/tmp/spine_explain.py
# PYTHONPATH, not just -w: Python puts the *script's* directory on sys.path, and
# the script is in /tmp, so \`import db\` finds nothing without this.
docker exec -w /app -e PYTHONPATH=/app $CONTAINER /opt/venv/bin/python /tmp/spine_explain.py | gzip | base64 -w0
REMOTE
)
encoded=$(base64 <<<"$remote" | tr -d '\n')

echo "running spine_explain.py in $CONTAINER on $INSTANCE"
command_id=$(aws --profile "$AWS_PROFILE" ssm send-command \
  --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript \
  --parameters "commands=[\"echo $encoded | base64 -d > /tmp/spine.sh\",\"bash /tmp/spine.sh\"]" \
  --query 'Command.CommandId' --output text)

while :; do
  sleep 8
  status=$(aws --profile "$AWS_PROFILE" ssm get-command-invocation \
    --command-id "$command_id" --instance-id "$INSTANCE" \
    --query 'Status' --output text 2>/dev/null || echo Pending)
  case "$status" in
    Pending|InProgress|Delayed) echo "  $status" ;;
    Success) break ;;
    *)
      aws --profile "$AWS_PROFILE" ssm get-command-invocation \
        --command-id "$command_id" --instance-id "$INSTANCE" \
        --query 'StandardErrorContent' --output text >&2
      echo "spine_explain failed: $status" >&2
      exit 1 ;;
  esac
done

mkdir -p "$(dirname "$OUT")"
aws --profile "$AWS_PROFILE" ssm get-command-invocation \
  --command-id "$command_id" --instance-id "$INSTANCE" \
  --query 'StandardOutputContent' --output text \
  | tr -d '\n' | base64 -d | gunzip \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d, indent=2))' \
  > "$OUT"

echo "wrote $OUT"
