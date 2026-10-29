#!/usr/bin/env bash
# Downloads DB-IP's free IP to City Lite and IP to ASN Lite databases
# (CC BY 4.0, https://db-ip.com) for the edge log shipper (ADR-0096).
#
#   bash deploy/geoip-update.sh [DIR]     # default /var/lib/uscode/geoip
#
# Writes DIR/dbip-city-lite.mmdb and DIR/dbip-asn-lite.mmdb. DB-IP publishes
# one file a month, named for the month; this month's is tried, then last
# month's. A database younger than 28 days is left as it is. Each download is
# written beside its final name and moved into place, so a failed one leaves
# the previous file. Exits non-zero when either database is still missing.
set -uo pipefail

DIR="${1:-/var/lib/uscode/geoip}"
mkdir -p "$DIR"

fetch() {
    local kind="$1" dest="$DIR/dbip-$1-lite.mmdb" tmp month
    if [ -s "$dest" ] && [ -z "$(find "$dest" -mtime +27)" ]; then
        echo "geoip: $kind is current"
        return 0
    fi
    tmp="$(mktemp "$dest.XXXXXX")"
    for month in "$(date -u +%Y-%m)" "$(date -u -d "$(date -u +%Y-%m-15) -1 month" +%Y-%m)"; do
        if curl -sSfL --max-time 600 -A "uscode-redesign geoip-update" \
                "https://download.db-ip.com/free/dbip-${kind}-lite-${month}.mmdb.gz" \
                | gunzip > "$tmp" && [ -s "$tmp" ]; then
            chmod 0644 "$tmp"
            mv "$tmp" "$dest"
            echo "geoip: $kind $month"
            return 0
        fi
    done
    rm -f "$tmp"
    echo "geoip: could not download the $kind database" >&2
    [ -s "$dest" ]
}

status=0
fetch city || status=1
fetch asn || status=1
exit "$status"
