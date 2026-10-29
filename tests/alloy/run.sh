#!/usr/bin/env bash
# Runs deploy/alloy/ against a real Caddy and real GeoIP databases, and checks
# what it would send to Grafana Cloud (ADR-0096). CI runs it; it needs Docker
# and network access to download.db-ip.com.
#
#   bash tests/alloy/run.sh
#
# A Caddy carrying the edge's compose labels logs six requests; Alloy finds it
# through the Docker socket, exactly as on the box, and sends the enriched lines
# to an OTLP receiver inside itself (loop.alloy), which prints them. The
# printing exporter is experimental in Alloy, so the test allows that level;
# the box runs at the default, generally-available.
set -euo pipefail
cd "$(dirname "$0")/../.."

ALLOY_IMAGE="$(sed -n 's/^ *image: \(grafana\/alloy:.*\)$/\1/p' docker-compose.prod.yml)"
WORK="$(mktemp -d)"
trap 'docker rm -f usc-test-edge usc-test-alloy >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT

bash deploy/geoip-update.sh "$WORK/geoip"
mkdir -p "$WORK/config"
cp deploy/alloy/*.alloy tests/alloy/loop.alloy "$WORK/config/"

docker run -d --name usc-test-edge -p 8080:8080 \
    --label com.docker.compose.project=edge \
    --label com.docker.compose.service=caddy \
    -v "$PWD/tests/alloy/Caddyfile:/etc/caddy/Caddyfile:ro" \
    caddy:2-alpine >/dev/null

docker run -d --name usc-test-alloy --user 0:0 \
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -v "$WORK/config:/etc/alloy:ro" \
    -v "$WORK/geoip:/geoip:ro" \
    -e OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
    -e "OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20dGVzdDp0ZXN0" \
    "$ALLOY_IMAGE" run /etc/alloy --storage.path=/tmp/alloy \
    --stability.level=experimental >/dev/null

sleep 15
if [ "$(docker inspect -f '{{.State.Running}}' usc-test-alloy)" != true ]; then
    docker logs usc-test-alloy
    echo "alloy exited" >&2
    exit 1
fi

BROWSER="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
GPTBOT="Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)"
ask() {  # address, User-Agent, path
    curl -s -o /dev/null -H "X-Forwarded-For: $1" -A "$2" "http://127.0.0.1:8080$3"
}
ask 8.8.8.8 "$BROWSER" "/app/us/usc/t16/s45f?release=119-99"
ask 8.8.8.8 "$GPTBOT" /app/
ask 73.162.0.1 "$BROWSER" /app/_astro/site.css
ask 73.162.0.1 "curl/8.5.0" /limited
ask 128.32.0.1 "python-requests/2.32" /api/v1/status
ask 140.147.0.1 "$BROWSER" /us/usc/t16/s1

sleep 15
docker logs usc-test-alloy > "$WORK/alloy.log" 2>&1
# The debug exporter's dump is a log message, so its quotes arrive escaped.
tr -d '\\' < "$WORK/alloy.log" > "$WORK/records.log"
grep -o 'Body: Str({[^}]*})' "$WORK/records.log" | sed 's/^Body: Str(//; s/)$//' > "$WORK/records.json" || true
echo "--- records sent"
cat "$WORK/records.json"

failed=0
expect() {  # description, extended regex
    if grep -Eq "$2" "$WORK/records.json"; then
        echo "ok   $1"
    else
        echo "FAIL $1" >&2
        failed=1
    fi
}
count="$(grep -c '"_entry"' "$WORK/records.json" || true)"
if [ "$count" = 6 ]; then echo "ok   six records, one per request"; else echo "FAIL $count records, expected 6" >&2; failed=1; fi
expect "location and network are filled in" '"asn_org":"[^"]+"[^}]*"country_code":"US"'
expect "8.8.8.8 is Google's network, in the US" '"asn_org":"Google LLC"[^}]*"client_ip":"8.8.8.8"[^}]*"country_code":"US"'
expect "a university's network is education" '"client_ip":"128.32.0.1"[^}]*"network":"education"'
expect "8.8.8.8 is cloud" '"client_ip":"8.8.8.8"[^}]*"network":"cloud"|"network":"cloud"[^}]*"client_ip":"8.8.8.8"'
expect "the gate's 403 is cookie-gate" '"outcome":"cookie-gate"'
expect "GPTBot is an ai-crawler, blocked" '"client":"ai-crawler"[^}]*"outcome":"blocked"'
expect "an asset is an asset" '"area":"asset"[^}]*"_entry":"/app/_astro/site.css"'
expect "curl is a script, rate-limited" '"client":"script"[^}]*"outcome":"rate-limited"'
expect "a pinned release is marked" '"pinned":"yes"[^}]*"_entry":"/app/us/usc/t16/s45f\?release=119-99"'
if grep -q 'loki.attribute.labels' "$WORK/records.log"; then echo "FAIL a label reached the record unpacked" >&2; failed=1; fi
grep -q 'service.name: Str(edge-proxy)' "$WORK/records.log" || { echo "FAIL resource service.name" >&2; failed=1; }
if [ "$failed" != 0 ]; then
    echo "--- alloy log"
    cat "$WORK/alloy.log"
    exit 1
fi
echo "the edge log pipeline works"
