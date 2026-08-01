#!/usr/bin/env bash
# Provision the site box (docs/deploy.md §2). Run after deploy/admin-grant.sh
# has created the uscode-site instance profile:
#
#   bash deploy/provision.sh
#
# Idempotent: an existing security group, Elastic IP, or running instance
# tagged Name=uscode-site is reused rather than duplicated. Prints the instance
# id and public IP at the end — the IP is what the DNS A record points at.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
NAME="uscode-site"
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.large}"
DATA_VOLUME_GB="${DATA_VOLUME_GB:-120}"
ROOT_VOLUME_GB="${ROOT_VOLUME_GB:-20}"
# AL2023 arm64, resolved through SSM so the AMI id is never stale in this file.
AMI_ALIAS="resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"

echo "==> security group $NAME"
SG="$(aws ec2 describe-security-groups --region "$REGION" \
    --filters "Name=group-name,Values=$NAME" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo None)"
if [ "$SG" = "None" ] || [ -z "$SG" ]; then
    SG="$(aws ec2 create-security-group --region "$REGION" --group-name "$NAME" \
        --description "uscode demo site: HTTP and HTTPS only, no SSH (SSM for access)" \
        --query GroupId --output text)"
    # 80 as well as 443: Caddy needs it for the ACME HTTP challenge and to
    # redirect anyone who types the bare hostname.
    aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG" \
        --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null
    aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG" \
        --protocol tcp --port 443 --cidr 0.0.0.0/0 >/dev/null
    echo "    created $SG (80, 443; port 22 deliberately absent)"
else
    echo "    reusing $SG"
fi

echo "==> instance tagged Name=$NAME"
INSTANCE_ID="$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Name,Values=$NAME" \
              "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null || echo None)"

if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
    echo "    launching $INSTANCE_TYPE"
    # HttpPutResponseHopLimit=2: a process inside a container is one hop
    # further from IMDS than one on the host, and the default of 1 makes every
    # instance-role credential call inside the api container time out silently.
    # DeleteOnTermination=false on the data volume: the instance is
    # replaceable, the loaded corpus is not.
    INSTANCE_ID="$(aws ec2 run-instances --region "$REGION" \
        --image-id "$AMI_ALIAS" \
        --instance-type "$INSTANCE_TYPE" \
        --iam-instance-profile "Name=$NAME" \
        --security-group-ids "$SG" \
        --metadata-options "HttpTokens=required,HttpPutResponseHopLimit=2" \
        --block-device-mappings \
          "DeviceName=/dev/xvda,Ebs={VolumeSize=${ROOT_VOLUME_GB},VolumeType=gp3,DeleteOnTermination=true}" \
          "DeviceName=/dev/xvdb,Ebs={VolumeSize=${DATA_VOLUME_GB},VolumeType=gp3,DeleteOnTermination=false}" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
        --query 'Instances[0].InstanceId' --output text)"
    echo "    $INSTANCE_ID — waiting for it to run"
    aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
else
    echo "    reusing $INSTANCE_ID"
fi

echo "==> Elastic IP"
ALLOC_ID="$(aws ec2 describe-addresses --region "$REGION" \
    --filters "Name=tag:Name,Values=$NAME" \
    --query 'Addresses[0].AllocationId' --output text 2>/dev/null || echo None)"
if [ "$ALLOC_ID" = "None" ] || [ -z "$ALLOC_ID" ]; then
    ALLOC_ID="$(aws ec2 allocate-address --region "$REGION" --domain vpc \
        --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME}]" \
        --query AllocationId --output text)"
    echo "    allocated $ALLOC_ID"
else
    echo "    reusing $ALLOC_ID"
fi
aws ec2 associate-address --region "$REGION" \
    --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" >/dev/null

PUBLIC_IP="$(aws ec2 describe-addresses --region "$REGION" \
    --allocation-ids "$ALLOC_ID" --query 'Addresses[0].PublicIp' --output text)"

echo
echo "instance: $INSTANCE_ID"
echo "public IP: $PUBLIC_IP"
echo
echo "Next:"
echo "  1. Point the DNS A record at $PUBLIC_IP. Caddy cannot get a"
echo "     certificate until the name resolves, so do this first — it is the"
echo "     step with someone else's propagation delay in it."
echo "  2. Wait for SSM to register the instance:"
echo "     aws ssm describe-instance-information --region $REGION \\"
echo "       --filters Key=InstanceIds,Values=$INSTANCE_ID"
echo "  3. Bootstrap it (deploy/bootstrap-box.sh), then deploy/deploy-on-box.sh."
echo "  4. ALERT_EMAIL=... bash deploy/alarms.sh $INSTANCE_ID"
