#!/usr/bin/env bash
#
# Load test of the top routes, against a running `make dev-all` (PLAN Day 6c).
#
# The numbers this produces are a reproducible command, not an assertion
# (PLAN §11.5) — re-run it and you get your own. They are *relative* numbers:
# a laptop with a Docker VM and 66 of 382 release points loaded is not the
# deployed box, and the interesting comparisons are between rows, not against
# any absolute target.
#
# Two rows carry the session's actual claims:
#   * "section, revalidated" vs "section, pinned"  — what the 304 path saves.
#   * "parent TOC (was fetched per section page)"  — the call PLAN Day 6b removed;
#     it is still a real route, so it can still be measured.
#
# Usage:  make loadtest            (needs `brew install hey` and the stack up)
#         BASE=... N=... C=... scripts/loadtest.sh

set -euo pipefail

BASE="${BASE:-http://localhost:8000}"
N="${N:-500}"       # requests per route
C="${C:-20}"        # concurrency
RELEASE="${RELEASE:-119-102not101}"
PRIOR="${PRIOR:-119-99}"
OUT="${OUT:-docs/verification/loadtest.json}"

command -v hey >/dev/null || { echo "hey not found: brew install hey" >&2; exit 1; }
curl -sf "$BASE/health" >/dev/null || { echo "nothing at $BASE — run 'make dev-all'" >&2; exit 1; }

SECTION="/us/usc/t16/s45f"
PROVISION="/us/usc/t16/s45f/c/5"
PARENT="/us/usc/t16/ch1/schVI"

# name|url|requests|extra header (optional)
#
# The diff row gets its own, much smaller request count: it is seconds per
# request (see the note this script's output feeds into), so at $N it would be
# most of the wall time and tell you nothing the small sample doesn't.
ROUTES=(
  "section JSON, pinned|$BASE/api/v1$SECTION?release=$RELEASE|$N|"
  "section JSON, unpinned|$BASE/api/v1$SECTION|$N|"
  "provision JSON (extracted at request time)|$BASE/api/v1$PROVISION?release=$RELEASE|$N|"
  "section XML, verbatim USLM|$BASE/api/v1$SECTION?release=$RELEASE&format=xml|$N|"
  "parent TOC (was fetched per section page)|$BASE/api/v1$PARENT?release=$RELEASE|$N|"
  "labels, batched|$BASE/api/v1/labels?release=$RELEASE&identifier=$SECTION&identifier=/us/usc/t16/s1|$N|"
  "neighbors|$BASE/api/v1/sections$SECTION/neighbors?release=$RELEASE|$N|"
  "versions timeline|$BASE/api/v1/sections/us/usc/t16/s2201/versions|$N|"
  "releases|$BASE/api/v1/releases?title=16|$N|"
  "reader section page (SSR)|$BASE/app/us/usc/t16/s45f?release=$RELEASE|$N|"
  "reader TOC page (SSR)|$BASE/app/us/usc/t16/ch1?release=$RELEASE|$N|"
)

# The conditional-request row needs the live ETag, so it is built after the fact.
# `curl -I` would send HEAD, and the API answers GET only — a HEAD is 405, so
# that spelling silently yielded an empty tag and measured a plain 200 instead
# of a revalidation. `-D - -o /dev/null` gets the headers off a real GET.
ETAG=$(curl -s -D - -o /dev/null "$BASE/api/v1$SECTION?release=$RELEASE" \
  | awk 'tolower($1)=="etag:"{print $2}' | tr -d '\r')
[[ -n "$ETAG" ]] || { echo "could not read an ETag to revalidate against" >&2; exit 1; }
ROUTES+=("section, revalidated (If-None-Match -> 304)|$BASE/api/v1$SECTION?release=$RELEASE|$N|If-None-Match: $ETAG")

# Diff goes last, always. It saturates the CPU for seconds at a time, and any
# row measured immediately after it reads as several times slower than it is —
# which is how the first run of this script "showed" /releases at 8.6 rps and a
# 304 revalidation slower than the 200 it replaces. Both were the diff's shadow.
ROUTES+=("diff between two release points|$BASE/api/v1/sections/us/usc/t16/s2201/diff?from=$PRIOR&to=$RELEASE|$((C * 2))|")

echo "load test: $N requests, $C concurrent, against $BASE"
printf '%-46s %7s %9s %9s %9s %10s %8s\n' ROUTE RPS "MEAN ms" "P50 ms" "P95 ms" BYTES REQS

mkdir -p "$(dirname "$OUT")"
rows=""
for entry in "${ROUTES[@]}"; do
  IFS='|' read -r name url reqs header <<<"$entry"

  hey_args=(-n "$reqs" -c "$C")
  curl_args=(-s -o /dev/null -w '%{size_download}')
  if [[ -n "${header:-}" ]]; then
    hey_args+=(-H "$header")
    curl_args+=(-H "$header")
  fi

  # Response size comes from curl: this hey build reports no Size/request.
  size=$(curl "${curl_args[@]}" "$url" 2>/dev/null || echo 0)

  sleep 1  # let the previous row's load drain, so rows measure themselves
  raw=$(hey "${hey_args[@]}" "$url" 2>/dev/null)

  # hey prints percentiles as "  50%% in 0.0364 secs" — the value is $3, and the
  # doubled % is why a "%" pattern has to be matched loosely.
  rps=$(awk '/Requests\/sec:/{printf "%.1f", $2}' <<<"$raw")
  mean=$(awk '/Average:/{printf "%.1f", $2*1000}' <<<"$raw")
  p50=$(awk '$1 ~ /^50%/ {printf "%.1f", $3*1000; exit}' <<<"$raw")
  p95=$(awk '$1 ~ /^95%/ {printf "%.1f", $3*1000; exit}' <<<"$raw")

  # hey reports NaN and prints no distribution when a run is short and slow —
  # which is exactly the diff row. Little's law recovers the mean from what it
  # does report: at steady state, latency = concurrency / throughput.
  if [[ -z "$mean" || "$mean" == "nan" || "$mean" == "-nan" ]]; then
    mean=$(awk -v c="$C" -v r="$rps" 'BEGIN{ if (r > 0) printf "%.1f", c / r * 1000; else print 0 }')
    p50=${p50:-$mean}
    p95=${p95:-$mean}
  fi
  # Only the status-code section: the response-time histogram also prints
  # bracketed counts ("0.060 [129] |■■■"), which otherwise land here as codes.
  codes=$(awk '/Status code distribution:/{s=1;next} s && $1 ~ /^\[[0-9]+\]$/{gsub(/[][]/,"",$1);printf "%s:%s ", $1, $2}' <<<"$raw" | sed 's/ *$//')

  printf '%-46s %7s %9s %9s %9s %10s %8s\n' "$name" "$rps" "$mean" "$p50" "$p95" "$size" "$reqs"
  rows+=$(printf '{"route":"%s","url":"%s","requests":%s,"rps":%s,"mean_ms":%s,"p50_ms":%s,"p95_ms":%s,"bytes_per_request":%s,"status_codes":"%s"},' \
    "$name" "${url#"$BASE"}" "$reqs" "${rps:-0}" "${mean:-0}" "${p50:-0}" "${p95:-0}" "${size:-0}" "$codes")
done

cat > "$OUT" <<JSON
{
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "base": "$BASE",
  "requests_per_route": $N,
  "concurrency": $C,
  "release": "$RELEASE",
  "note": "Laptop numbers against a partial corpus, through the dev stack (single uvicorn worker, --reload). Relative comparisons between rows are the point, not absolutes.",
  "findings": [
    "The diff endpoint is CPU-bound and does not scale with concurrency: it holds ~0.45 rps at every concurrency from 1 to 10, while latency grows linearly (2.2 s, 4.5 s, 11.9 s, 22.0 s). Past about 10 concurrent it exceeds a 20 s client timeout and every request fails. It is unauthenticated, so one client can saturate it. Diff_Timeout=0 is ADR-0016's deliberate choice (a timed-out diff-match-patch silently returns a worse diff), so this is a known cost, not a regression - but it must be throttled or precomputed before public exposure.",
    "Roughly half the diff cost is guid churn rather than legal change: @id attributes regenerate at every release point by design (ADR-0003), so the two texts differ in every element. Diffing the guid-stripped text - what ADR-0007 already does for dedupe - took the same section from 2,220 ms and 51 ops to 1,172 ms and 20 ops. The extra 31 ops are regenerated guids presented to the reader as changes to the law.",
    "Revalidation works and is worth having, but it is not a latency win on loopback: 304s ran 183.7 rps against 159.1 for the full 200. What it actually saves is the body - 28,348 bytes per request - which matters over a real network and not at all here.",
    "HEAD is 405 on every /api/v1 route: FastAPI's APIRouter registers GET alone, where Starlette's own Route would add HEAD. Caches, CDNs and uptime monitors use HEAD, so this is worth fixing before a CDN goes in front."
  ],
  "routes": [${rows%,}]
}
JSON
echo
echo "wrote $OUT"
