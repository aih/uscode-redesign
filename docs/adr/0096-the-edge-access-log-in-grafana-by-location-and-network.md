# ADR-0096 — The edge's access log in Grafana, by location and network

**Status:** accepted (2026-10-29)

**Related:** ADR-0089 (OpenTelemetry to Grafana Cloud), ADR-0090 (the dashboard and alert rules
as code), ADR-0073 and ADR-0088 (the crawls), the statutes repository's ADR-0017 (one edge for two
sites).

## Context

The "Traffic spike" alert fires on the request rate in the two APIs' metrics. Those metrics and
the traces carry a route and a status code, and no client address or User-Agent. The one place a
request's address and User-Agent are written is the edge Caddy's access log, on the box, in the
container `edge-caddy-1`. Reading it took a shell on the box and `docker logs`.

## Decision

1. A Grafana Alloy container, `alloy` in `docker-compose.prod.yml`, reads the edge container's log
   through the Docker socket (`deploy/alloy/source.alloy`, found by its compose labels `edge` /
   `caddy`) and keeps its read position under `$DATA_ROOT/alloy`.
2. `deploy/alloy/process.alloy` keeps the access-log entries and writes one JSON line per request:
   `_entry` (the URI), `site`, `method`, `status`, `duration`, `client_ip`, `user_agent`,
   `referer`, and
   - `country`, `country_code`, `region`, `city`, `asn`, `asn_org` from DB-IP's free City Lite
     and ASN Lite databases (CC BY 4.0);
   - `network`: `cloud`, `education`, `government`, `isp` or `unknown`, from regular expressions
     over the ASN's organisation name;
   - `client`: `ai-crawler`, `search-engine`, `other-bot`, `script`, `browser`, `other` or `none`,
     from the User-Agent;
   - `outcome`: `served`, `cookie-gate` (a 403 carrying `Set-Cookie`), `blocked` (any other 403),
     `rate-limited`, `client-error` or `server-error`;
   - `area` (`reader`, `asset`, `api`, `citation`, `other`) and `pinned` (`yes` when the address
     carries `?release=`, `?date=` or `?id=`).
   None of them is a Loki label.
3. `deploy/alloy/export.alloy` sends the lines over the OTLP endpoint and header the api already
   has in `.env` (ADR-0089), as the stream `{service_name="edge-proxy"}`.
4. `deploy/geoip-update.sh` downloads the two databases into `$DATA_ROOT/geoip`, at most once
   every 28 days. A deploy runs it, and so does a monthly cron that then restarts Alloy.
5. `alloy` is in the compose profile `observability`, so the stack's `up -d --wait` neither starts
   it nor waits on it. `deploy-on-box.sh` starts it after the site has answered its checks, only
   when the OTLP endpoint and both databases are present, and goes on when it fails.
6. `deploy/grafana/traffic.json` is the dashboard "Traffic sources" (uid `uscode-traffic`),
   applied by `apply.py` beside the existing one: totals, request rate by network and by client,
   shares of network, client and outcome, the top countries, regions, cities, networks, addresses,
   User-Agents and areas, and the requests themselves. A `site` variable selects one site.
7. `tests/alloy/run.sh` (CI job `edge-logs`) runs `deploy/alloy/` unchanged against a Caddy with the
   edge's compose labels and log format and the real databases, with Grafana Cloud replaced by an
   OTLP receiver inside the same Alloy, and checks the records it receives.

## Consequences

- Grafana Cloud holds every request's client address and User-Agent for the stack's log retention.
- The Alloy container holds the Docker socket, which is root on the box.
- The network and client types are name matches. A provider whose name carries none of the listed
  words is `isp`; a User-Agent that copies a browser's is `browser`.
- About 250,000 lines a day at 2 to 3 requests a second, against Grafana Cloud's log quota.
