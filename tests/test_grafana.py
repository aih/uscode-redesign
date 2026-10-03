"""The Grafana dashboard and alert rules in deploy/grafana (ADR-0090)."""

import importlib.util
import json
from pathlib import Path

GRAFANA = Path(__file__).resolve().parent.parent / "deploy" / "grafana"


def _load_apply():
    spec = importlib.util.spec_from_file_location("grafana_apply", GRAFANA / "apply.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Recorder:
    url = "https://example.grafana.net"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def call(self, method, path, body=None, ok=()):
        self.calls.append((method, path, body))
        if method == "GET" and path.startswith("/api/folders/"):
            return 404, None
        if path == "/api/dashboards/db":
            return 200, {"url": "/d/uscode-sites"}
        return 200, {}


def test_dashboard_panels_have_unique_ids_and_queries() -> None:
    dashboard = json.loads((GRAFANA / "dashboard.json").read_text())
    ids = [panel["id"] for panel in dashboard["panels"]]
    assert len(ids) == len(set(ids))
    assert all(panel["targets"] for panel in dashboard["panels"])
    assert dashboard["uid"] == "uscode-sites"


def test_apply_fills_the_rules_and_replaces_the_group() -> None:
    apply = _load_apply()
    grafana = _Recorder()
    apply.apply(grafana, "prom-uid", "someone@example.org")

    paths = [(method, path) for method, path, _ in grafana.calls]
    assert ("POST", "/api/folders") in paths
    assert ("POST", "/api/dashboards/db") in paths
    assert ("PUT", "/api/v1/provisioning/contact-points/uscode-email") in paths

    method, path, group = grafana.calls[-1]
    assert (method, path) == (
        "PUT",
        "/api/v1/provisioning/folder/uscode/rule-groups/uscode",
    )
    text = json.dumps(group)
    assert "${" not in text
    assert {rule["uid"] for rule in group["rules"]} == {
        "uscode-traffic-spike",
        "uscode-server-errors",
    }
    for rule in group["rules"]:
        assert rule["data"][0]["datasourceUid"] == "prom-uid"
        assert rule["notification_settings"] == {"receiver": "uscode-email"}
        assert rule["folderUID"] == "uscode"


def test_without_an_email_the_default_contact_point_is_used() -> None:
    apply = _load_apply()
    grafana = _Recorder()
    apply.apply(grafana, "prom-uid", "")
    _, _, group = grafana.calls[-1]
    assert all(
        rule["notification_settings"]["receiver"] == "grafana-default-email"
        for rule in group["rules"]
    )
    assert not any("contact-points" in path for _, path, _ in grafana.calls)


def _load_weekly():
    spec = importlib.util.spec_from_file_location(
        "grafana_weekly", GRAFANA / "weekly.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Prometheus:
    url = "https://example.grafana.net"

    def __init__(self, answers: dict[str, list[dict]]) -> None:
        self.answers = answers

    def prom(self, uid, path, params):
        return {"result": self.answers.get(params["query"], [])}


def test_weekly_summary_reports_each_site() -> None:
    import datetime

    weekly = _load_weekly()

    def row(job, value, **labels):
        return {"metric": {"job": job, **labels}, "value": [0, str(value)]}

    grafana = _Prometheus(
        {
            weekly.QUERIES["requests"]: [row("uscode-api", 1200)],
            weekly.QUERIES["previous"]: [row("uscode-api", 1000)],
            weekly.QUERIES["p95"]: [row("uscode-api", 0.25)],
            weekly.QUERIES["peak"]: [row("uscode-api", 1.5)],
            weekly.ROUTES: [
                row("uscode-api", 40, http_route="/api/v1/status"),
                row("uscode-api", 900, http_route="/api/v1/us/usc/{identifier:path}"),
            ],
        }
    )
    text = weekly.summary(grafana, datetime.date(2026, 10, 5))
    lines = text.splitlines()
    assert lines[0] == "US Code sites: the week to 2026-10-05"
    assert "  Requests: 1,200 (+20% on the week before)" in lines
    assert "  Server errors (5xx): 0" in lines
    assert "  Latency p95: 250 ms" in lines
    assert "  Peak: 1.50 requests a second" in lines
    routes = [line for line in lines if line.startswith("    ")]
    assert routes[0].endswith("/api/v1/us/usc/{identifier:path}")
    statutes = lines[lines.index("statutes-api") + 1 :]
    assert statutes[0] == "  Requests: no data"
    assert "Dashboard: https://example.grafana.net/d/uscode-sites" in lines
