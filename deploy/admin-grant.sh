#!/usr/bin/env bash
# ONE-TIME setup, run by a human with an admin AWS profile:
#
#   AWS_PROFILE=<admin> bash deploy/admin-grant.sh
#
# "Admin" here means only the IAM actions this script calls, all of them scoped
# to uscode-* names — admin-grant-bootstrap-policy.json is exactly that set,
# for an account where nobody wants to hand out AdministratorAccess to run a
# setup script. Attach it, run this, detach it: nothing in the ongoing deploy
# path needs IAM write.
#
# That policy also carries iam:PassRole on uscode-site, which no line below
# calls by name: AddRoleToInstanceProfile requires it implicitly. Deriving the
# permission list by reading the `aws iam` calls here will miss it — and the
# failure arrives late, after the group, the role and the profile all exist.
#
# Creates the IAM surface deploy/update-corpus.yml, deploy-on-box.sh and
# update-corpus.sh need, and nothing more:
#
#   - group `uscode-deploy` + policy `uscode-deploy-policy`, with $DEPLOY_USER
#     added to it (day-to-day human/CI provisioning and operational access —
#     EC2, ECR, S3, SSM, CloudWatch/SNS, a scoped PassRole). Defaults to
#     `linkedlegislation-deploy`; set DEPLOY_USER to point it elsewhere.
#   - role + instance profile `uscode-site` (ADR-0020's box): SSM core, S3
#     read on the mirror plus write under usc/* (the site is now the mirror's
#     one writer per ADR-0013's handoff), ECR pull, CloudWatch agent metrics
#   - GitHub OIDC provider + role `uscode-github-deploy` (.github/workflows/
#     deploy.yml and update-corpus.yml assume this via `aws-actions/
#     configure-aws-credentials`): ECR push, tag-scoped SSM SendCommand,
#     nothing else
#
# Idempotent: every create is preceded by an existence check, so re-running
# this after a partial failure (or to pick up a policy edit made in this file)
# skips what's already there rather than erroring.
set -euo pipefail

ACCOUNT_ID="739065237548"
REGION="us-east-1"
GITHUB_REPO="aih/uscode-redesign"
DEPLOY_GROUP="uscode-deploy"
DEPLOY_POLICY_NAME="uscode-deploy-policy"
# The IAM user that does day-to-day provisioning and operations. Overridable
# because the account is shared and the right identity is a per-deployment
# choice, not a property of this script.
DEPLOY_USER="${DEPLOY_USER:-linkedlegislation-deploy}"
SITE_ROLE="uscode-site"
SITE_INSTANCE_PROFILE="uscode-site"
SITE_INLINE_POLICY="uscode-site-access"
GITHUB_ROLE="uscode-github-deploy"
MIRROR_BUCKET="uscode-mirror-dreamproit"
OIDC_PROVIDER_URL="token.actions.githubusercontent.com"
OIDC_PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/${OIDC_PROVIDER_URL}"
OIDC_THUMBPRINTS=("6938fd4d98bab03faadb97b34396831e3780aea1" "1c58a3a8518e8759bf075b76b750d4f2df264fcd")

echo "=== uscode-redesign one-time IAM setup (account ${ACCOUNT_ID}, region ${REGION}) ==="
echo "Using AWS_PROFILE=${AWS_PROFILE:-<default>}"
echo

# All the policy-document heredocs below are written to mktemp files; track
# them here and clean up on exit regardless of how the script ends.
TMP_FILES=()
cleanup() {
    [ "${#TMP_FILES[@]}" -eq 0 ] || rm -f "${TMP_FILES[@]}"
}
trap cleanup EXIT

mktemp_tracked() {
    local f
    f="$(mktemp)"
    TMP_FILES+=("$f")
    echo "$f"
}

# ---------------------------------------------------------------- helpers ---

iam_group_exists() {
    aws iam get-group --group-name "$1" >/dev/null 2>&1
}

iam_policy_arn() {
    aws iam list-policies --scope Local --query "Policies[?PolicyName=='$1'].Arn" --output text
}

iam_role_exists() {
    aws iam get-role --role-name "$1" >/dev/null 2>&1
}

iam_instance_profile_exists() {
    aws iam get-instance-profile --instance-profile-name "$1" >/dev/null 2>&1
}

# ------------------------------------------------------- a. uscode-deploy ---

echo "--- (a) IAM group ${DEPLOY_GROUP} + policy ${DEPLOY_POLICY_NAME} ---"

if iam_group_exists "$DEPLOY_GROUP"; then
    echo "group ${DEPLOY_GROUP} already exists, skipping create"
else
    aws iam create-group --group-name "$DEPLOY_GROUP"
    echo "created group ${DEPLOY_GROUP}"
fi

DEPLOY_POLICY_DOC="$(mktemp_tracked)"
cat > "$DEPLOY_POLICY_DOC" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Ec2Provisioning",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:CreateTags",
        "ec2:Describe*",
        "ec2:CreateSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:AllocateAddress",
        "ec2:AssociateAddress",
        "ec2:CreateVolume",
        "ec2:AttachVolume",
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:ModifyInstanceAttribute"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Ec2TerminateOnlyUscodeSite",
      "Effect": "Allow",
      "Action": "ec2:TerminateInstances",
      "Resource": "*",
      "Condition": {
        "StringEquals": { "ec2:ResourceTag/Name": "uscode-site" }
      }
    },
    {
      "Sid": "EcrRepoManagement",
      "Effect": "Allow",
      "Action": [
        "ecr:CreateRepository",
        "ecr:DescribeRepositories",
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EcrPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/uscode-*"
    },
    {
      "Sid": "S3Mirror",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::${MIRROR_BUCKET}",
        "arn:aws:s3:::${MIRROR_BUCKET}/*"
      ]
    },
    {
      "Sid": "SsmSendCommandUscodeSite",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ec2:${REGION}:${ACCOUNT_ID}:instance/*",
      "Condition": {
        "StringEquals": { "ssm:resourceTag/Name": "uscode-site" }
      }
    },
    {
      "Sid": "SsmSendCommandDocument",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ssm:${REGION}::document/AWS-RunShellScript"
    },
    {
      "Sid": "SsmOperate",
      "Effect": "Allow",
      "Action": [
        "ssm:GetCommandInvocation",
        "ssm:ListCommands",
        "ssm:DescribeInstanceInformation"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SsmStartSessionUscodeSite",
      "Effect": "Allow",
      "Action": "ssm:StartSession",
      "Resource": "arn:aws:ec2:${REGION}:${ACCOUNT_ID}:instance/*",
      "Condition": {
        "StringEquals": { "ssm:resourceTag/Name": "uscode-site" }
      }
    },
    {
      "Sid": "CloudWatchAlarms",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricAlarm",
        "cloudwatch:DescribeAlarms",
        "cloudwatch:SetAlarmState"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SnsAlerts",
      "Effect": "Allow",
      "Action": [
        "sns:CreateTopic",
        "sns:Subscribe",
        "sns:GetTopicAttributes",
        "sns:ListTopics",
        "sns:Publish"
      ],
      "Resource": "arn:aws:sns:${REGION}:${ACCOUNT_ID}:uscode-*"
    },
    {
      "Sid": "PassSiteRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::${ACCOUNT_ID}:role/${SITE_ROLE}"
    },
    {
      "Sid": "IamVerify",
      "Effect": "Allow",
      "Action": [
        "iam:GetRole",
        "iam:GetInstanceProfile"
      ],
      "Resource": [
        "arn:aws:iam::${ACCOUNT_ID}:role/uscode-*",
        "arn:aws:iam::${ACCOUNT_ID}:instance-profile/uscode-*"
      ]
    }
  ]
}
EOF

EXISTING_DEPLOY_POLICY_ARN="$(iam_policy_arn "$DEPLOY_POLICY_NAME")"
if [ -n "$EXISTING_DEPLOY_POLICY_ARN" ] && [ "$EXISTING_DEPLOY_POLICY_ARN" != "None" ]; then
    echo "policy ${DEPLOY_POLICY_NAME} already exists (${EXISTING_DEPLOY_POLICY_ARN}), adding a new version"
    # A managed policy can hold at most 5 versions; drop the oldest non-default
    # one if we're about to hit that so a re-run of this script never fails.
    OLD_VERSION="$(aws iam list-policy-versions --policy-arn "$EXISTING_DEPLOY_POLICY_ARN" \
        --query 'Versions[?IsDefaultVersion==`false`] | [-1].VersionId' --output text)"
    VERSION_COUNT="$(aws iam list-policy-versions --policy-arn "$EXISTING_DEPLOY_POLICY_ARN" \
        --query 'length(Versions)' --output text)"
    if [ "$VERSION_COUNT" -ge 5 ] && [ -n "$OLD_VERSION" ] && [ "$OLD_VERSION" != "None" ]; then
        aws iam delete-policy-version --policy-arn "$EXISTING_DEPLOY_POLICY_ARN" --version-id "$OLD_VERSION"
    fi
    aws iam create-policy-version --policy-arn "$EXISTING_DEPLOY_POLICY_ARN" \
        --policy-document "file://${DEPLOY_POLICY_DOC}" --set-as-default
    DEPLOY_POLICY_ARN="$EXISTING_DEPLOY_POLICY_ARN"
else
    DEPLOY_POLICY_ARN="$(aws iam create-policy --policy-name "$DEPLOY_POLICY_NAME" \
        --policy-document "file://${DEPLOY_POLICY_DOC}" --query 'Policy.Arn' --output text)"
    echo "created policy ${DEPLOY_POLICY_NAME} (${DEPLOY_POLICY_ARN})"
fi

if aws iam list-attached-group-policies --group-name "$DEPLOY_GROUP" \
        --query "AttachedPolicies[?PolicyArn=='${DEPLOY_POLICY_ARN}']" --output text | grep -q .; then
    echo "policy already attached to ${DEPLOY_GROUP}, skipping"
else
    aws iam attach-group-policy --group-name "$DEPLOY_GROUP" --policy-arn "$DEPLOY_POLICY_ARN"
    echo "attached ${DEPLOY_POLICY_NAME} to ${DEPLOY_GROUP}"
fi

if aws iam get-group --group-name "$DEPLOY_GROUP" --query "Users[?UserName=='${DEPLOY_USER}']" \
        --output text | grep -q .; then
    echo "user ${DEPLOY_USER} already in ${DEPLOY_GROUP}, skipping"
else
    aws iam add-user-to-group --group-name "$DEPLOY_GROUP" --user-name "$DEPLOY_USER"
    echo "added ${DEPLOY_USER} to ${DEPLOY_GROUP}"
fi

echo

# --------------------------------------------------------- b. uscode-site ---

echo "--- (b) role/instance profile ${SITE_ROLE} ---"

SITE_TRUST_DOC="$(mktemp_tracked)"
cat > "$SITE_TRUST_DOC" <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

if iam_role_exists "$SITE_ROLE"; then
    echo "role ${SITE_ROLE} already exists, skipping create"
else
    aws iam create-role --role-name "$SITE_ROLE" \
        --assume-role-policy-document "file://${SITE_TRUST_DOC}"
    echo "created role ${SITE_ROLE}"
fi

if aws iam list-attached-role-policies --role-name "$SITE_ROLE" \
        --query "AttachedPolicies[?PolicyName=='AmazonSSMManagedInstanceCore']" \
        --output text | grep -q .; then
    echo "AmazonSSMManagedInstanceCore already attached to ${SITE_ROLE}, skipping"
else
    aws iam attach-role-policy --role-name "$SITE_ROLE" \
        --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
    echo "attached AmazonSSMManagedInstanceCore to ${SITE_ROLE}"
fi

SITE_INLINE_DOC="$(mktemp_tracked)"
cat > "$SITE_INLINE_DOC" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MirrorRead",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::${MIRROR_BUCKET}",
        "arn:aws:s3:::${MIRROR_BUCKET}/*"
      ]
    },
    {
      "Sid": "MirrorWriteUnderUsc",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${MIRROR_BUCKET}/usc/*"
    },
    {
      "Sid": "EcrPull",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchCheckLayerAvailability"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchAgent",
      "Effect": "Allow",
      "Action": "cloudwatch:PutMetricData",
      "Resource": "*"
    }
  ]
}
EOF

# put-role-policy is an upsert; run it unconditionally so an edit to this
# script's inline policy is picked up on re-run, same as the managed policy
# version bump above.
aws iam put-role-policy --role-name "$SITE_ROLE" \
    --policy-name "$SITE_INLINE_POLICY" --policy-document "file://${SITE_INLINE_DOC}"
echo "put inline policy ${SITE_INLINE_POLICY} on ${SITE_ROLE}"

if iam_instance_profile_exists "$SITE_INSTANCE_PROFILE"; then
    echo "instance profile ${SITE_INSTANCE_PROFILE} already exists, skipping create"
else
    aws iam create-instance-profile --instance-profile-name "$SITE_INSTANCE_PROFILE"
    echo "created instance profile ${SITE_INSTANCE_PROFILE}"
fi

if aws iam get-instance-profile --instance-profile-name "$SITE_INSTANCE_PROFILE" \
        --query "InstanceProfile.Roles[?RoleName=='${SITE_ROLE}']" --output text | grep -q .; then
    echo "role ${SITE_ROLE} already in instance profile ${SITE_INSTANCE_PROFILE}, skipping"
else
    aws iam add-role-to-instance-profile --instance-profile-name "$SITE_INSTANCE_PROFILE" \
        --role-name "$SITE_ROLE"
    echo "added role ${SITE_ROLE} to instance profile ${SITE_INSTANCE_PROFILE}"
fi

echo

# --------------------------------------------------- c. GitHub OIDC + role ---

echo "--- (c) GitHub OIDC provider + role ${GITHUB_ROLE} ---"

if aws iam list-open-id-connect-providers \
        --query "OpenIDConnectProviderList[?contains(Arn, '${OIDC_PROVIDER_URL}')]" \
        --output text | grep -q .; then
    echo "OIDC provider for ${OIDC_PROVIDER_URL} already exists, skipping create"
else
    aws iam create-open-id-connect-provider \
        --url "https://${OIDC_PROVIDER_URL}" \
        --client-id-list sts.amazonaws.com \
        --thumbprint-list "${OIDC_THUMBPRINTS[@]}"
    echo "created OIDC provider for ${OIDC_PROVIDER_URL}"
fi

GITHUB_TRUST_DOC="$(mktemp_tracked)"
cat > "$GITHUB_TRUST_DOC" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Federated": "${OIDC_PROVIDER_ARN}" },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_REPO}:ref:refs/heads/main"
        }
      }
    }
  ]
}
EOF

if iam_role_exists "$GITHUB_ROLE"; then
    echo "role ${GITHUB_ROLE} already exists, updating trust policy"
    aws iam update-assume-role-policy --role-name "$GITHUB_ROLE" \
        --policy-document "file://${GITHUB_TRUST_DOC}"
else
    aws iam create-role --role-name "$GITHUB_ROLE" \
        --assume-role-policy-document "file://${GITHUB_TRUST_DOC}"
    echo "created role ${GITHUB_ROLE}"
fi

GITHUB_PERMISSIONS_DOC="$(mktemp_tracked)"
cat > "$GITHUB_PERMISSIONS_DOC" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "EcrPush",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/uscode-*"
    },
    {
      "Sid": "SsmSendCommandUscodeSite",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ec2:${REGION}:${ACCOUNT_ID}:instance/*",
      "Condition": {
        "StringEquals": { "ssm:resourceTag/Name": "uscode-site" }
      }
    },
    {
      "Sid": "SsmSendCommandDocument",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ssm:${REGION}::document/AWS-RunShellScript"
    },
    {
      "Sid": "SsmPollCommand",
      "Effect": "Allow",
      "Action": [
        "ssm:GetCommandInvocation",
        "ssm:ListCommands"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Ec2Describe",
      "Effect": "Allow",
      "Action": "ec2:DescribeInstances",
      "Resource": "*"
    }
  ]
}
EOF

# put-role-policy upserts, same rationale as the site role's inline policy.
aws iam put-role-policy --role-name "$GITHUB_ROLE" \
    --policy-name "${GITHUB_ROLE}-policy" --policy-document "file://${GITHUB_PERMISSIONS_DOC}"
echo "put permissions policy on ${GITHUB_ROLE}"

echo
GITHUB_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${GITHUB_ROLE}"

echo "=============================================================="
echo "Summary"
echo "=============================================================="
echo "GitHub repo variable AWS_DEPLOY_ROLE_ARN:"
echo "  ${GITHUB_ROLE_ARN}"
echo
echo "Instance profile for the EC2 launch (docs/deploy.md):"
echo "  ${SITE_INSTANCE_PROFILE}"
echo
echo "Next steps:"
echo "  1. Set the GitHub Actions repo variable AWS_DEPLOY_ROLE_ARN to the"
echo "     role ARN above:"
echo "       gh variable set AWS_DEPLOY_ROLE_ARN --repo ${GITHUB_REPO} --body '${GITHUB_ROLE_ARN}'"
echo "  2. Launch the EC2 instance (ADR-0020) with:"
echo "       --iam-instance-profile Name=${SITE_INSTANCE_PROFILE}"
echo "       --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=uscode-site}]'"
echo "  3. Create the ECR repositories uscode-api / uscode-frontend if the"
echo "     first deploy.yml run doesn't create them automatically."
echo "  4. Confirm ${DEPLOY_USER} (in ${DEPLOY_GROUP}) can do day-to-day"
echo "     provisioning — it needs an access key configured locally as an AWS"
echo "     profile; ${GITHUB_ROLE} is CI-only and assumed by Actions."
