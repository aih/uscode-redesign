#!/usr/bin/env bash
# Retention for the database dumps on the mirror bucket (ADR-0013).
#
#   AWS_PROFILE=<admin> bash deploy/mirror-lifecycle.sh
#   AWS_PROFILE=<admin> DRY_RUN=1 bash deploy/mirror-lifecycle.sh   # show, change nothing
#
# Needs an ADMIN profile, not the deploy user and not the box. That is
# deliberate twice over:
#
#   * the instance role has s3:PutObject on usc/* and no s3:DeleteObject, so
#     the one writer of the corpus of record cannot delete it, and
#   * the deploy user cannot even read a lifecycle configuration
#     (s3:GetLifecycleConfiguration is not in its policy).
#
# Nothing here should ever be granted to either of them. The whole point of a
# lifecycle rule is that expiry is the bucket's job rather than a script's, so
# no credential that lives on the box needs the power to delete.
#
# WHY THIS IS A SCRIPT AND NOT A ONE-LINER, which is the part worth reading:
# PutBucketLifecycleConfiguration REPLACES the bucket's entire configuration.
# It does not merge. Running the obvious `aws s3api put-bucket-lifecycle-
# configuration` with one rule silently deletes every other rule on the bucket,
# and the failure is invisible until something you expected to expire does not,
# or something you expected to keep is gone. So this reads what is there first
# and refuses to clobber a configuration it did not write.
#
# WHAT IT MUST NEVER TOUCH: this bucket holds the corpus of record — the
# release-point zips under usc/releases/ and ledger.json, which ADR-0013 makes
# the authoritative copy of ~9.7 GB that would otherwise have to be re-fetched
# from uscode.house.gov at one request per second. Every rule below is scoped to
# the usc/db/ prefix. An unscoped expiry rule on this bucket would delete the
# corpus, and it would look exactly like a working retention policy right up
# until it did.
set -euo pipefail

BUCKET="${USC_MIRROR_BUCKET:-uscode-mirror-dreamproit}"
PREFIX="usc/db/"
RULE_ID="expire-db-dumps"

# How long a dump is worth keeping. The dumps are a fast-restore convenience,
# not the record: a `pg_restore` of the seed took 24 minutes where a `load-all`
# from the zips takes hours, but the zips are what make the corpus
# reproducible at all. So this can be generous without being unbounded — at the
# post-2026-08-03 rate of a few dozen dumps a year (deploy/update-corpus.sh
# takes one when load-all actually loads something), a year of retention is
# ~30 dumps, ~66 GB, on the order of $1.50/month.
EXPIRE_AFTER_DAYS="${EXPIRE_AFTER_DAYS:-365}"

# The bucket is versioned, and that matters more than it looks. In a versioned
# bucket, "expiring" a current object only writes a delete marker — the object
# itself becomes a noncurrent version and goes on being billed forever. A
# retention rule without these two clauses reduces what you can see with
# `aws s3 ls` and reduces the bill by nothing at all.
NONCURRENT_AFTER_DAYS="${NONCURRENT_AFTER_DAYS:-30}"

echo "==> bucket   s3://${BUCKET}"
echo "    prefix   ${PREFIX}"
echo "    expire   current versions after ${EXPIRE_AFTER_DAYS} days"
echo "             noncurrent versions after ${NONCURRENT_AFTER_DAYS} days"
echo

echo "==> existing lifecycle configuration"

# Read it in a way that can tell "there isn't one" from "I am not allowed to
# look", because those two must not lead to the same place. S3 returns
# NoSuchLifecycleConfiguration for the first and AccessDenied for the second,
# and a `|| true` collapses them into an empty string — which this script would
# then read as "nothing here to clobber" and go on to replace a configuration
# it could not see. That is the failure this whole script exists to prevent,
# and the first draft of it had exactly that bug: run with the deploy profile,
# which cannot read a lifecycle configuration, it reported "none — this will be
# the first".
ERR_FILE="$(mktemp)"
trap 'rm -f "$ERR_FILE"' EXIT

set +e
EXISTING="$(aws s3api get-bucket-lifecycle-configuration --bucket "$BUCKET" \
    --output json 2>"$ERR_FILE")"
READ_STATUS=$?
set -e

if [ "$READ_STATUS" -ne 0 ]; then
    if grep -q 'NoSuchLifecycleConfiguration' "$ERR_FILE"; then
        EXISTING=""
    else
        echo
        echo "REFUSING: could not read the bucket's current lifecycle configuration," >&2
        echo "so there is no way to know whether applying ours would delete rules." >&2
        echo "This needs an admin profile — the deploy user is denied this call." >&2
        echo >&2
        sed 's/^/    /' "$ERR_FILE" >&2
        exit 1
    fi
fi

if [ -z "$EXISTING" ]; then
    echo "    none — this will be the first"
else
    printf '%s\n' "$EXISTING" | sed 's/^/    /'
    # Re-running after this script wrote the rule is fine and expected; finding
    # a configuration this script did not write is not, because applying ours
    # would delete it.
    if printf '%s' "$EXISTING" | grep -q "\"$RULE_ID\""; then
        echo
        echo "    (contains $RULE_ID — this is a re-run, and replacing it is safe)"
    else
        echo
        echo "REFUSING: this bucket already has a lifecycle configuration that this" >&2
        echo "script did not write, and put-bucket-lifecycle-configuration REPLACES" >&2
        echo "rather than merges — applying ours would delete the rules above." >&2
        echo >&2
        echo "Merge by hand: add the rule this script would apply (run again with" >&2
        echo "DRY_RUN=1 to print it) to the existing document, then put the whole" >&2
        echo "thing." >&2
        exit 1
    fi
fi

# AbortIncompleteMultipartUpload is not padding. The dump is streamed with
# `pg_dump | aws s3 cp -`, which the CLI sends as a multipart upload, so a dump
# that dies half way leaves parts behind that are billed as storage and do not
# appear in `aws s3 ls` at all. Without this clause they accumulate invisibly,
# one per failed dump, forever — and a failed dump is precisely the case where
# nobody goes looking.
LIFECYCLE_JSON="$(cat <<JSON
{
  "Rules": [
    {
      "ID": "${RULE_ID}",
      "Status": "Enabled",
      "Filter": { "Prefix": "${PREFIX}" },
      "Expiration": { "Days": ${EXPIRE_AFTER_DAYS} },
      "NoncurrentVersionExpiration": { "NoncurrentDays": ${NONCURRENT_AFTER_DAYS} },
      "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 7 }
    },
    {
      "ID": "${RULE_ID}-delete-markers",
      "Status": "Enabled",
      "Filter": { "Prefix": "${PREFIX}" },
      "Expiration": { "ExpiredObjectDeleteMarker": true }
    }
  ]
}
JSON
)"

echo
echo "==> rule to apply"
printf '%s\n' "$LIFECYCLE_JSON" | sed 's/^/    /'

if [ -n "${DRY_RUN:-}" ]; then
    echo
    echo "DRY_RUN set — nothing applied."
    exit 0
fi

echo
echo "==> applying"
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" \
    --lifecycle-configuration "$LIFECYCLE_JSON"

echo "==> reading it back"
aws s3api get-bucket-lifecycle-configuration --bucket "$BUCKET" --output json \
    | sed 's/^/    /'

echo
echo "Done. S3 applies lifecycle rules asynchronously, once a day — nothing"
echo "disappears in the next few minutes, and objects already older than the"
echo "threshold are removed on the next run rather than immediately."
echo
echo "Check what is there now with:"
echo "  aws s3 ls s3://${BUCKET}/${PREFIX} --human-readable"
