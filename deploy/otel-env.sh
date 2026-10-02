#!/usr/bin/env bash
# Copies the Grafana Cloud OTLP endpoint and header (ADR-0089) from SSM
# Parameter Store into .env, so the api's compose environment picks them up.
#
#   bash deploy/otel-env.sh [path/to/.env]
#
# The values start as GitHub secrets in aih/uscode-redesign; deploy.yml writes
# them to /uscode/otel/endpoint and /uscode/otel/headers as SecureStrings, and
# the box reads them with its instance role. statutes-at-large's deploy reads
# the same two parameters, so they are set in one place.
#
# Never fatal: a missing parameter or a denied read leaves .env as it was,
# and an api without the two lines exports nothing.
set -uo pipefail

ENV_FILE="${1:-.env}"
REGION="${AWS_REGION:-us-east-1}"

read_param() {
    aws ssm get-parameter --region "$REGION" --name "$1" --with-decryption \
        --query Parameter.Value --output text 2>/dev/null
}

ENDPOINT="$(read_param /uscode/otel/endpoint)" || ENDPOINT=""
HEADERS="$(read_param /uscode/otel/headers)" || HEADERS=""

if [ -z "$ENDPOINT" ] || [ -z "$HEADERS" ]; then
    echo "otel: /uscode/otel/* not readable; .env left as it was"
    exit 0
fi

touch "$ENV_FILE"
TMP="$(mktemp "${ENV_FILE}.XXXXXX")"
grep -vE '^OTEL_EXPORTER_OTLP_(ENDPOINT|HEADERS)=' "$ENV_FILE" > "$TMP" || true
printf 'OTEL_EXPORTER_OTLP_ENDPOINT=%s\nOTEL_EXPORTER_OTLP_HEADERS=%s\n' \
    "$ENDPOINT" "$HEADERS" >> "$TMP"
chmod --reference="$ENV_FILE" "$TMP" 2>/dev/null || chmod 600 "$TMP"
mv "$TMP" "$ENV_FILE"
echo "otel: endpoint and header written to $ENV_FILE"
