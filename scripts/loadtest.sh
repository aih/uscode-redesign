#!/usr/bin/env bash
#
# Load test of the top routes (PLAN Day 6c, task B3).
#
# The numbers this produces are a reproducible command, not an assertion
# (PLAN §11.5) — re-run it and you get your own.
#
# Usage:  make loadtest                       (needs `brew install hey`)
#         BASE=https://uscode.linkedlegislation.org scripts/loadtest.sh
#         BASE=... N=... C=... OUT=... scripts/loadtest.sh
#
#
# ## Rate limits, and why every row names one
#
# ADR-0029 put token buckets in front of the expensive unauthenticated routes.
# Their deployed budgets are tight — the API diff refills at one request per
# five seconds — so a flat `-n 500 -c 20` across every route does not measure
# the site. It measures ADR-0029, and it does so badly: the first `capacity`
# requests are served and the rest are 429s produced in microseconds, which
# reads as a *throughput improvement* on the route that shed the most.
#
# So a limited route gets two rows, and the artifact says which is which:
#
#   * **within budget** — `hey -q` holds the arrival rate at or under the
#     bucket's refill rate, so nothing sheds and the row measures the route.
#   * **over budget** — the same route driven deliberately past the bucket, so
#     the row measures the shedding: what fraction is served, and that a 429
#     carries `Retry-After` rather than the connection collapsing.
#
# `hey -q` is per worker, so the arrival rate is C x q. An unlimited route gets
# one row at $N/$C and its `limiter` field is null.

set -euo pipefail

BASE="${BASE:-http://localhost:8000}"
N="${N:-200}"       # requests per unlimited route
C="${C:-8}"         # concurrency for unlimited routes
RELEASE="${RELEASE:-119-102not101}"
PRIOR="${PRIOR:-119-99}"
OUT="${OUT:-docs/verification/loadtest.json}"

command -v hey >/dev/null || { echo "hey not found: brew install hey" >&2; exit 1; }
curl -sf "$BASE/health" >/dev/null || { echo "nothing at $BASE — run 'make dev-all'" >&2; exit 1; }

SECTION="/us/usc/t16/s45f"
PROVISION="/us/usc/t16/s45f/c/5"
PARENT="/us/usc/t16/ch1/schVI"
VERSIONED="/us/usc/t16/s2201"

# name|url|requests|concurrency|qps per worker (0 = unthrottled)|header|limiter|budget
#
# `budget` is "none" for a route with no limiter, "within" for a row held under
# the refill rate, "over" for a row driven past it on purpose.
ROUTES=(
  "section JSON, pinned|$BASE/api/v1$SECTION?release=$RELEASE|$N|$C|0|||none"
  "section JSON, unpinned|$BASE/api/v1$SECTION|$N|$C|0|||none"
  "provision JSON (extracted at request time)|$BASE/api/v1$PROVISION?release=$RELEASE|$N|$C|0|||none"
  "section XML, verbatim USLM|$BASE/api/v1$SECTION?release=$RELEASE&format=xml|$N|$C|0|||none"
  "parent TOC (the ChapterRail's call, ADR-0043)|$BASE/api/v1$PARENT?release=$RELEASE|$N|$C|0|||none"
  "neighbors|$BASE/api/v1/sections$SECTION/neighbors?release=$RELEASE|$N|$C|0|||none"
  "versions timeline|$BASE/api/v1/sections$VERSIONED/versions|$N|$C|0|||none"
  "releases for one title (on every section page)|$BASE/api/v1/releases?title=16|$N|$C|0|||none"
  "titles (the front page)|$BASE/api/v1/titles|$N|$C|0|||none"
  "reader section page (SSR, 5 API calls)|$BASE/app/us/usc/t16/s45f?release=$RELEASE|$N|$C|0|||none"
  "reader TOC page (SSR, 2 API calls)|$BASE/app/us/usc/t16/ch1?release=$RELEASE|$N|$C|0|||none"
)

# ---- limited routes, held inside their budgets -----------------------------
#
# labels:   capacity 300, refill 30/s   (api/routes.py)
# search:   capacity 120, refill 10/s   (api/search.py)
# citation: capacity 120, refill 10/s   (api/routes.py)
# diff:     capacity   5, refill 0.2/s  (api/routes.py — the tightest here)
ROUTES+=(
  "labels, batched (within budget)|$BASE/api/v1/labels?release=$RELEASE&identifier=$SECTION&identifier=/us/usc/t16/s1|150|4|7||labels 300 @ 30/s|within"
  "search (within budget)|$BASE/api/v1/search?q=conservation|60|2|5||search 120 @ 10/s|within"
  "citation parse (within budget)|$BASE/api/v1/citation?q=16%20U.S.C.%2045f|60|2|5||citation 120 @ 10/s|within"
)

# The conditional-request row needs the live ETag, so it is built after the fact.
# `curl -I` would send HEAD, and the API answers GET alone — a HEAD is 405, so
# that spelling silently yielded an empty tag and measured a plain 200 instead
# of a revalidation. `-D - -o /dev/null` gets the headers off a real GET.
ETAG=$(curl -s -D - -o /dev/null "$BASE/api/v1$SECTION?release=$RELEASE" \
  | awk 'tolower($1)=="etag:"{print $2}' | tr -d '\r')
[[ -n "$ETAG" ]] || { echo "could not read an ETag to revalidate against" >&2; exit 1; }
ROUTES+=("section, revalidated (If-None-Match -> 304)|$BASE/api/v1$SECTION?release=$RELEASE|$N|$C|0|If-None-Match: $ETAG||none")

# ---- the shedding rows, deliberately over budget ---------------------------
#
# Last, and in this order. The diff saturates the CPU for seconds at a time, and
# any row measured immediately after it reads as several times slower than it
# is — which is how the first run of this script "showed" /releases at 8.6 rps
# and a 304 revalidation slower than the 200 it replaces. Both were the diff's
# shadow.
ROUTES+=(
  "search (over budget, measures the limiter)|$BASE/api/v1/search?q=conservation|200|10|0||search 120 @ 10/s|over"
  "labels (over budget, measures the limiter)|$BASE/api/v1/labels?release=$RELEASE&identifier=$SECTION|500|20|0||labels 300 @ 30/s|over"
  "diff between two release points (within budget: the burst)|$BASE/api/v1/sections$VERSIONED/diff?from=$PRIOR&to=$RELEASE|5|1|0||diff 5 @ 0.2/s|within"
  "diff (over budget, measures the limiter)|$BASE/api/v1/sections$VERSIONED/diff?from=$PRIOR&to=$RELEASE|40|10|0||diff 5 @ 0.2/s|over"
)

echo "load test against $BASE — $N requests at $C concurrent on unlimited routes"
printf '%-58s %7s %9s %9s %9s %10s %6s\n' ROUTE RPS "MEAN ms" "P50 ms" "P95 ms" BYTES REQS

mkdir -p "$(dirname "$OUT")"
rows=""
for entry in "${ROUTES[@]}"; do
  IFS='|' read -r name url reqs conc qps header limiter budget <<<"$entry"

  # Every request asks for compression, because every browser does and Caddy
  # only compresses what asks (`encode gzip zstd`). Left off, this measures a
  # response no reader receives — 76,021 bytes for a section page against the
  # 21,246 that cross the wire — and it also measures the box without the gzip
  # CPU it really spends. `%{size_download}` under `--compressed` reports the
  # wire bytes.
  hey_args=(-n "$reqs" -c "$conc" -H "Accept-Encoding: gzip")
  [[ "${qps:-0}" != "0" ]] && hey_args+=(-q "$qps") || true
  curl_args=(-s --compressed -o /dev/null -w '%{size_download}')
  if [[ -n "${header:-}" ]]; then
    hey_args+=(-H "$header")
    curl_args+=(-H "$header")
  fi

  # Response size comes from curl: this hey build reports no Size/request.
  size=$(curl "${curl_args[@]}" "$url" 2>/dev/null || echo 0)

  # Long enough for the tightest bucket to refill between rows, so a row that is
  # meant to be inside its budget does not start against an empty one left by
  # the row before it. The diff bucket needs 25 s to refill from empty; that is
  # paid once, before the diff rows, rather than between every pair.
  case "$budget" in
    within|over) sleep 6 ;;
    *) sleep 2 ;;
  esac
  # `|| true` because a false `[[ ]] && …` returns 1, and `set -e` would end the
  # run on the first row that is not a diff.
  [[ "$url" == *"/diff?"* ]] && sleep 25 || true

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
    mean=$(awk -v c="$conc" -v r="$rps" 'BEGIN{ if (r > 0) printf "%.1f", c / r * 1000; else print 0 }')
    p50=${p50:-$mean}
    p95=${p95:-$mean}
  fi
  # Only the status-code section: the response-time histogram also prints
  # bracketed counts ("0.060 [129] |■■■"), which otherwise land here as codes.
  codes=$(awk '/Status code distribution:/{s=1;next} s && $1 ~ /^\[[0-9]+\]$/{gsub(/[][]/,"",$1);printf "%s:%s ", $1, $2}' <<<"$raw" | sed 's/ *$//')

  printf '%-58s %7s %9s %9s %9s %10s %6s\n' "$name" "$rps" "$mean" "$p50" "$p95" "$size" "$reqs"
  rows+=$(printf '{"route":"%s","url":"%s","requests":%s,"concurrency":%s,"qps_per_worker":%s,"limiter":%s,"budget":"%s","rps":%s,"mean_ms":%s,"p50_ms":%s,"p95_ms":%s,"bytes_per_request":%s,"status_codes":"%s"},' \
    "$name" "${url#"$BASE"}" "$reqs" "$conc" "${qps:-0}" \
    "$([[ -n "$limiter" ]] && printf '"%s"' "$limiter" || printf 'null')" \
    "$budget" "${rps:-0}" "${mean:-0}" "${p50:-0}" "${p95:-0}" "${size:-0}" "$codes")
done

# ---- checks the script makes rather than claims ----------------------------
#
# Standing claims in this artifact that are cheap to re-verify, so they are
# re-verified on every run instead of being copied forward as prose.
#
# Every one ends in `|| true`. A run reaches this point having spent half an
# hour of real requests against a real host, and a probe that fails must not be
# able to throw all of that away — which is exactly what happened once: `-X
# HEAD` only changes the method, so curl still waited for a body the 405 never
# sent, exited 18 (CURLE_PARTIAL_FILE), and `set -e` ended the script with every
# row measured and nothing written. `-I` is curl's own HEAD and expects no body.
header_of() {
  curl -s -D - -o /dev/null "$1" \
    | awk -v want="$2:" 'tolower($1)==want{$1="";print}' | tr -d '\r' | sed 's/^ *//' || true
}

head_status=$(curl -s -o /dev/null -w '%{http_code}' -I "$BASE/api/v1$SECTION?release=$RELEASE" || echo 0)
get_status=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/v1$SECTION?release=$RELEASE" || echo 0)
sleep 25
# This probe comes back empty, and the empty value is the finding rather than a
# failed check: it asks *sequentially*, and the diff bucket refills one token
# every five seconds while the endpoint itself takes about five seconds to
# answer (see the "within budget: the burst" row). A caller making one diff
# request at a time therefore always finds a token waiting and is never shed.
# The 429 and its Retry-After are observed in the "diff (over budget)" row,
# where concurrency is what exceeds the bucket.
retry_after=$(
  for _ in $(seq 1 8); do
    header_of "$BASE/api/v1/sections$VERSIONED/diff?from=$PRIOR&to=$RELEASE" "retry-after"
  done | grep -m1 . || echo ""
)
cache_pinned=$(header_of "$BASE/api/v1$SECTION?release=$RELEASE" "cache-control")
cache_unpinned=$(header_of "$BASE/api/v1$SECTION" "cache-control")
cache_toc=$(header_of "$BASE/api/v1$PARENT?release=$RELEASE" "cache-control")

cat > "$OUT" <<JSON
{
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "base": "$BASE",
  "command": "BASE=$BASE scripts/loadtest.sh",
  "unlimited_route_requests": $N,
  "unlimited_route_concurrency": $C,
  "release": "$RELEASE",
  "note": "Every row names the limiter that governs it (ADR-0029) and whether it was held inside that budget or driven past it on purpose. A row marked \"over\" measures the limiter, not the route: read its status codes, not its rps. Rows marked \"none\" have no limiter and are the only ones whose throughput describes the route. bytes_per_request is the compressed wire size, the same thing a browser downloads.",
  "checks": {
    "head_status": $head_status,
    "get_status": $get_status,
    "diff_retry_after_header": "$retry_after",
    "cache_control_pinned": "$cache_pinned",
    "cache_control_unpinned": "$cache_unpinned",
    "cache_control_toc": "$cache_toc"
  },
  "routes": [${rows%,}]
}
JSON
echo
echo "wrote $OUT"
