#!/usr/bin/env bash
# CloudWatch alarms for the site box, and the SNS topic that mails them.
#
#   ALERT_EMAIL=you@example.org bash deploy/alarms.sh <instance-id>
#
# Idempotent: put-metric-alarm and create-topic are both upserts, and a repeat
# subscribe to an address already subscribed is a no-op. Safe to re-run after
# changing a threshold.
#
# These are the "do I need to pay for more?" tripwires, not a monitoring
# system. ADR-0020 chose one box on purpose and there is no autoscaling to
# trigger — an alarm here is a mail to a human who then decides. The site's own
# rate limits (ADR-0029) are what actually protect it under load; these only
# say that it happened.
set -euo pipefail

INSTANCE_ID="${1:?usage: ALERT_EMAIL=you@example.org alarms.sh <instance-id>}"
ALERT_EMAIL="${ALERT_EMAIL:?set ALERT_EMAIL to the address that should receive alarms}"
REGION="${AWS_REGION:-us-east-1}"
TOPIC_NAME="uscode-alerts"

echo "==> SNS topic $TOPIC_NAME"
TOPIC_ARN="$(aws sns create-topic --name "$TOPIC_NAME" --region "$REGION" \
    --query TopicArn --output text)"
echo "    $TOPIC_ARN"

echo "==> subscribing $ALERT_EMAIL"
aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email \
    --notification-endpoint "$ALERT_EMAIL" --region "$REGION" >/dev/null
echo "    check that mailbox — AWS will not send anything until the"
echo "    subscription is confirmed, and an unconfirmed topic fails silently."

alarm() {
    local name="$1" description="$2" namespace="$3" metric="$4" stat="$5" \
        period="$6" evals="$7" threshold="$8" operator="$9" dimensions="${10}"
    echo "==> alarm $name"
    aws cloudwatch put-metric-alarm \
        --alarm-name "$name" \
        --alarm-description "$description" \
        --namespace "$namespace" \
        --metric-name "$metric" \
        --statistic "$stat" \
        --period "$period" \
        --evaluation-periods "$evals" \
        --threshold "$threshold" \
        --comparison-operator "$operator" \
        --dimensions "$dimensions" \
        --alarm-actions "$TOPIC_ARN" \
        --treat-missing-data notBreaching \
        --region "$REGION"
}

DIM="Name=InstanceId,Value=${INSTANCE_ID}"

# Sustained CPU. Three five-minute periods, not one, because a reindex or a
# corpus load is supposed to peg the CPU and is not news.
alarm uscode-cpu-high \
    "CPU over 70% for 15 minutes — check whether it is traffic or a load job" \
    AWS/EC2 CPUUtilization Average 300 3 70 GreaterThanThreshold "$DIM"

# The burstable-instance failure mode: credits exhausted means the box is
# throttled to baseline and every page gets slow, with CPU% looking fine.
alarm uscode-cpu-credits-low \
    "t4g CPU credit balance under 60 — the box is about to be throttled to baseline" \
    AWS/EC2 CPUCreditBalance Average 300 2 60 LessThanThreshold "$DIM"

# The instance or its host is unhealthy. One period: this is never noise.
alarm uscode-status-check-failed \
    "EC2 status check failed — instance or host impaired" \
    AWS/EC2 StatusCheckFailed Maximum 60 1 0 GreaterThanThreshold "$DIM"

# The traffic tripwire the demo actually wants: a few hundred visitors will
# never approach this, so crossing it means either real interest or a scraper.
alarm uscode-network-out-high \
    "Over ~5 GB out in an hour — more traffic than this demo was sized for" \
    AWS/EC2 NetworkOut Sum 3600 1 5000000000 GreaterThanThreshold "$DIM"

# Disk needs the CloudWatch agent (it publishes CWAgent/disk_used_percent);
# without the agent installed this alarm sits in INSUFFICIENT_DATA, which
# treat-missing-data notBreaching keeps quiet rather than noisy.
echo "==> alarm uscode-disk-high (needs the CloudWatch agent on the box)"
aws cloudwatch put-metric-alarm \
    --alarm-name uscode-disk-high \
    --alarm-description "Data volume over 80% full — the corpus grows every release point" \
    --namespace CWAgent \
    --metric-name disk_used_percent \
    --statistic Average \
    --period 300 \
    --evaluation-periods 2 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --dimensions "$DIM" "Name=path,Value=/var/lib/uscode" \
    --alarm-actions "$TOPIC_ARN" \
    --treat-missing-data notBreaching \
    --region "$REGION"

echo
echo "Done. Confirm the subscription in $ALERT_EMAIL, then test delivery with:"
echo "  aws cloudwatch set-alarm-state --alarm-name uscode-status-check-failed \\"
echo "    --state-value ALARM --state-reason 'testing delivery' --region $REGION"
