# ADR-0089 — OpenTelemetry from FastAPI to Grafana Cloud

**Status:** accepted (2026-10-02)

**Related:** ADR-0020 (one box), ADR-0073 (the watchdog and the pool), ADR-0086 (the root disk),
ADR-0088 (the cookie gate and the global budget). statutes-at-large carries the same change under
its own ADR.

## Context

The deployment's monitoring is CloudWatch: EC2 metrics, the agent's memory and disk, the
watchdog's `USCode/SiteUp`, and alarms mailed through the `uscode-alerts` SNS topic. None of it
says which routes are called, how long they take, or which raise.

FastAPI 0.142.0 added built-in OpenTelemetry (`FastAPI(telemetry=...)`): a server span per request
with child spans for dependency resolution, the endpoint, serialization and background tasks; the
`http.server.request.duration` histogram and `http.server.active_requests`; and log records for
unhandled exceptions (with stack traces) and validation failures. It adds OTLP/HTTP exporters at
lifespan startup when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and does nothing when it is not. Spans
carry `url.path` and `url.query`; no attribute carries the client address or User-Agent. 0.141.1
has no `fastapi.telemetry` module; this repository locked 0.140.7.

## Decision

1. `fastapi[opentelemetry]>=0.142.2`. `main.py` passes `telemetry={"exclude": _untraced}`, which
   skips `/health` — Docker polls it every 10 s.
2. The api exports directly to a Grafana Cloud free stack over OTLP/HTTP. No collector runs on the
   box. `docker-compose.prod.yml` sets `OTEL_SERVICE_NAME=uscode-api`, the deployment environment
   and the image tag as resource attributes, `parentbased_traceidratio` at 0.25, and a 60 s metric
   interval; the endpoint and its `Authorization` header come from `.env`.
3. Traces are sampled at 25%. Metrics and logs are not sampled.
4. The dashboard, alert rules and weekly summary are separate changes (the plan's phases 2 and 3).

## Consequences

- The dev stack, CI and `make test` export nothing; `tests/test_telemetry.py` checks the route
  template on the server span and the `/health` exclusion against an in-memory exporter.
- Free-tier limits as reported at the time: 10,000 active series, 50 GB traces, 50 GB logs, 14-day
  retention, 3 users. The global budget (ADR-0088, 6 requests a second from outside callers) bounds
  sampled trace volume at roughly 0.6 GB a day.
- Requests that Caddy answers (the cookie gate, the crawler 403) never reach FastAPI and are not
  counted. Database, Redis and OpenSearch calls appear only as time inside the endpoint span.
- Exception records carry stack traces to a third party. Validation-failure records carry the
  route and an error count, not the request body.
