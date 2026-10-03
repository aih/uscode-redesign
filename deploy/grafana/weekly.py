"""Writes the weekly telemetry summary for both sites as plain text.

    GRAFANA_URL=... GRAFANA_TOKEN=... python3 deploy/grafana/weekly.py OUT.txt

Run by .github/workflows/weekly-summary.yml (ADR-0090), which mails OUT.txt
through the `uscode-alerts` SNS topic. Reads the stack's Prometheus data
source through Grafana's proxy with the same token as apply.py. The first
line of OUT.txt is the subject.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from apply import Grafana, require_env  # noqa: E402

PROM_UID = "grafanacloud-prom"
JOBS = 'job=~"uscode-api|statutes-api"'
COUNT = f"http_server_request_duration_seconds_count{{{JOBS}}}"
BUCKET = f"http_server_request_duration_seconds_bucket{{{JOBS}}}"
ERRORS = f'http_server_request_duration_seconds_count{{{JOBS}, http_response_status_code=~"5.."}}'
SITES = ("uscode-api", "statutes-api")

QUERIES = {
    "requests": f"sum by (job) (increase({COUNT}[7d]))",
    "previous": f"sum by (job) (increase({COUNT}[7d] offset 7d))",
    "errors": f"sum by (job) (increase({ERRORS}[7d]))",
    "p95": f"histogram_quantile(0.95, sum by (le, job) (increase({BUCKET}[7d])))",
    "peak": f"max by (job) (max_over_time(sum by (job) (rate({COUNT}[5m]))[7d:5m]))",
}
ROUTES = f"topk by (job) (5, sum by (job, http_route) (increase({COUNT}[7d])))"


def by_job(grafana: Grafana, query: str) -> dict[str, float]:
    data = grafana.prom(PROM_UID, "query", {"query": query})
    return {
        row["metric"].get("job", ""): float(row["value"][1])
        for row in (data or {}).get("result", [])
    }


def number(value: float | None) -> str:
    return "no data" if value is None else f"{value:,.0f}"


def change(now: float | None, before: float | None) -> str:
    if now is None or not before:
        return ""
    return f" ({(now - before) / before:+.0%} on the week before)"


def summary(grafana: Grafana, today: datetime.date) -> str:
    values = {name: by_job(grafana, query) for name, query in QUERIES.items()}
    routes = grafana.prom(PROM_UID, "query", {"query": ROUTES})
    lines = [
        f"US Code sites: the week to {today:%Y-%m-%d}",
        "",
        f"Telemetry for the seven days to {today:%A %d %B %Y}, from Grafana Cloud.",
    ]
    for site in SITES:
        requests = values["requests"].get(site)
        errors = values["errors"].get(site, 0.0 if requests is not None else None)
        p95 = values["p95"].get(site)
        peak = values["peak"].get(site)
        lines += [
            "",
            site,
            f"  Requests: {number(requests)}{change(requests, values['previous'].get(site))}",
            f"  Server errors (5xx): {number(errors)}",
            f"  Latency p95: {'no data' if p95 is None else f'{p95 * 1000:,.0f} ms'}",
            f"  Peak: {'no data' if peak is None else f'{peak:.2f} requests a second'}",
        ]
        top = sorted(
            (
                row
                for row in (routes or {}).get("result", [])
                if row["metric"].get("job") == site
                and row["metric"].get("http_route")
                and float(row["value"][1]) >= 0.5
            ),
            key=lambda row: -float(row["value"][1]),
        )
        if top:
            lines.append("  Busiest routes:")
            lines += [
                f"    {float(row['value'][1]):>10,.0f}  {row['metric'].get('http_route', '?')}"
                for row in top
            ]
    lines += ["", f"Dashboard: {grafana.url}/d/uscode-sites", ""]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: weekly.py OUT.txt")
    url, token = require_env()
    text = summary(
        Grafana(url, token), datetime.datetime.now(datetime.timezone.utc).date()
    )
    Path(sys.argv[1]).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
