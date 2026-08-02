#!/usr/bin/env bash
# Is anyone actually receiving the alarms?
#
#   bash deploy/alerts-status.sh            # report and exit non-zero if not
#   RESEND=1 bash deploy/alerts-status.sh   # re-send the confirmation mail too
#
# This exists because of the failure it checks for. deploy/alarms.sh creates
# five alarms and an SNS topic, and subscribing an email address to a topic
# does not subscribe it — AWS mails a confirmation link, and until someone
# clicks it the subscription sits in `PendingConfirmation` and every alarm
# publishes into nothing. The console shows five healthy alarms wired to a
# real topic the whole time, so the broken state looks exactly like the
# working one. Confirmation links also expire after three days, so "I'll click
# it later" silently becomes "I need a new one".
#
# The counts come from GetTopicAttributes rather than ListSubscriptionsByTopic
# because that is the call the deploy policy has always granted; the endpoint
# addresses need the wider grant, and are only listed if it happens to be
# there.
set -uo pipefail

REGION="${AWS_REGION:-us-east-1}"
TOPIC_NAME="${TOPIC_NAME:-uscode-alerts}"
ACCOUNT_ID="${ACCOUNT_ID:-739065237548}"
TOPIC_ARN="arn:aws:sns:${REGION}:${ACCOUNT_ID}:${TOPIC_NAME}"

ATTRS="$(aws sns get-topic-attributes --topic-arn "$TOPIC_ARN" --region "$REGION" \
    --query 'Attributes.[SubscriptionsConfirmed,SubscriptionsPending,SubscriptionsDeleted]' \
    --output text)" || {
    echo "could not read $TOPIC_ARN — wrong profile, wrong region, or no topic" >&2
    exit 2
}
read -r CONFIRMED PENDING DELETED <<<"$ATTRS"

echo "topic:     $TOPIC_ARN"
echo "confirmed: $CONFIRMED"
echo "pending:   $PENDING"
echo "deleted:   $DELETED"

# Best-effort: shows which addresses, when the profile is allowed to ask.
aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --region "$REGION" \
    --query 'Subscriptions[].[Protocol,Endpoint,SubscriptionArn]' --output text 2>/dev/null \
    | sed 's/^/           /'

echo
echo "alarms wired to this topic:"
aws cloudwatch describe-alarms --region "$REGION" \
    --query "MetricAlarms[?contains(AlarmActions, '${TOPIC_ARN}')].[AlarmName,StateValue]" \
    --output text | sed 's/^/           /'

if [ "${CONFIRMED:-0}" -gt 0 ]; then
    echo
    echo "OK — $CONFIRMED confirmed subscriber(s). Prove delivery end to end with:"
    echo "  aws cloudwatch set-alarm-state --alarm-name uscode-status-check-failed \\"
    echo "    --state-value ALARM --state-reason 'testing delivery' --region $REGION"
    exit 0
fi

echo
echo "NOBODY IS RECEIVING THESE ALARMS — $CONFIRMED confirmed, $PENDING pending." >&2

if [ "${RESEND:-}" = "1" ]; then
    ALERT_EMAIL="${ALERT_EMAIL:?set ALERT_EMAIL to the address to re-send to}"
    aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email \
        --notification-endpoint "$ALERT_EMAIL" --region "$REGION" >/dev/null
    echo "re-sent the confirmation to $ALERT_EMAIL — subject line" >&2
    echo "  \"AWS Notification - Subscription Confirmation\", from no-reply@sns.amazonaws.com." >&2
    echo "It expires in three days, and Gmail files it under Promotions or Spam." >&2
else
    echo "Re-send the confirmation with:" >&2
    echo "  ALERT_EMAIL=you@example.org RESEND=1 bash deploy/alerts-status.sh" >&2
fi
exit 1
