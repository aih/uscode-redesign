# ADR-0090 — The Grafana dashboard and alert rules live in the repository

**Status:** accepted (2026-10-03)

**Related:** ADR-0089 (OpenTelemetry to Grafana Cloud), ADR-0073 (the watchdog and `uscode-site-down`).

## Context

ADR-0089 sends both sites' traces, metrics and logs to a Grafana Cloud stack. Grafana keeps a
dashboard or an alert rule made in its UI only in that stack, with no history and no review.

## Decision

1. `deploy/grafana/dashboard.json` is the dashboard "US Code and Statutes sites" (uid
   `uscode-sites`). It has requests, latency, status codes, the busiest and slowest routes,
   requests in flight, slow traces and exception logs. A `job` variable selects `uscode-api`,
   `statutes-api` or both. The data sources are dashboard variables, so the file names no stack.
2. `deploy/grafana/alerts.json` holds one rule group, `uscode`, evaluated every minute:
   - **Traffic spike:** a site's request rate over 10 minutes is more than three times the same
     10 minutes a week earlier and above 2 requests a second, held for 10 minutes. A site with no
     data a week back is compared against zero.
   - **Server errors:** over 5% of responses are 5xx and the rate is above 0.1 a second, held for
     10 minutes.
3. `.github/workflows/grafana.yml` runs `deploy/grafana/apply.py` when those files change on
   `main`, and on demand. The script uses a service-account token (`GRAFANA_URL`,
   `GRAFANA_TOKEN`). It prints the stack's data sources, the metrics the two services report and
   the labels on the request histogram, then creates or updates the folder, the dashboard, an
   email contact point for `ALERT_EMAIL` and the rule group.
4. Rules are written with `X-Disable-Provenance`, so they stay editable in the UI. The next run of
   the workflow overwrites edits made there.

## Consequences

- The spike rule cannot fire on a site's first week of history unless its rate exceeds 2 requests
  a second, since an absent week counts as zero.
- The thresholds were chosen without measured traffic. ADR-0088's global budget is 6 requests a
  second for outside callers, which bounds what a spike from outside can reach.
- Grafana's alert email goes directly to `ALERT_EMAIL`, not through the `uscode-alerts` SNS topic.
  CloudWatch alarms still go through SNS.
- The service account needs the Admin role. With Editor, the first run was refused
  `GET /api/datasources` (403, `datasources:read`).
