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

    def instant(self, uid, expr):
        return {"result": self.answers.get(expr, [])}


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
                row("uscode-api", 0),
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
    assert len(routes) == 2
    assert routes[0].endswith("/api/v1/us/usc/{identifier:path}")
    statutes = lines[lines.index("statutes-api") + 1 :]
    assert statutes[0] == "  Requests: no data"
    assert "Dashboard: https://example.grafana.net/d/uscode-sites" in lines


def test_a_get_is_retried_through_a_datasource_503(monkeypatch) -> None:
    import io
    import urllib.error

    apply = _load_apply()
    monkeypatch.setattr(apply.time, "sleep", lambda _: None)
    answers = [
        urllib.error.HTTPError(
            "u", 503, "x", {}, io.BytesIO(b'{"code": "DatasourceError"}')
        ),
        urllib.error.URLError("timed out"),
    ]

    class _Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def urlopen(request, timeout):
        if answers:
            raise answers.pop(0)
        return _Response(b'{"data": {"result": []}}')

    monkeypatch.setattr(apply.urllib.request, "urlopen", urlopen)
    grafana = apply.Grafana("https://example.grafana.net", "token")
    assert grafana.prom("prom", "query", {"query": "up"}) == {"result": []}
    assert answers == []


def test_a_get_gives_up_after_the_last_pause(monkeypatch) -> None:
    import io
    import urllib.error

    import pytest

    apply = _load_apply()
    monkeypatch.setattr(apply.time, "sleep", lambda _: None)
    tries = []

    def urlopen(request, timeout):
        tries.append(1)
        raise urllib.error.HTTPError("u", 503, "x", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(apply.urllib.request, "urlopen", urlopen)
    with pytest.raises(SystemExit):
        apply.Grafana("https://example.grafana.net", "t").call("GET", "/api/health")
    assert len(tries) == len(apply.RETRY_PAUSES) + 1


def test_instant_reads_the_frames_ds_query_returns(monkeypatch) -> None:
    apply = _load_apply()
    sent = []

    def call(method, path, body=None, ok=(), retry=None):
        sent.append((method, path, body, retry))
        frame = {
            "schema": {
                "fields": [
                    {"name": "Time", "type": "time"},
                    {"name": "Value", "type": "number", "labels": {"job": "uscode-api"}},
                ]
            },
            "data": {"values": [[1759680000000], [1200.5]]},
        }
        return 200, {"results": {"A": {"status": 200, "frames": [frame]}}}

    grafana = apply.Grafana("https://example.grafana.net", "t")
    monkeypatch.setattr(grafana, "call", call)
    assert grafana.instant("prom", "up") == {
        "result": [{"metric": {"job": "uscode-api"}, "value": [0, "1200.5"]}]
    }
    method, path, body, retry = sent[0]
    assert (method, path, retry) == ("POST", "/api/ds/query", True)
    assert body["queries"][0]["datasource"]["uid"] == "prom"
    assert body["queries"][0]["instant"] is True


def test_instant_stops_on_a_query_error(monkeypatch) -> None:
    import pytest

    apply = _load_apply()
    grafana = apply.Grafana("https://example.grafana.net", "t")
    monkeypatch.setattr(
        grafana,
        "call",
        lambda *a, **k: (200, {"results": {"A": {"error": "bad_data: parse error"}}}),
    )
    with pytest.raises(SystemExit, match="bad_data"):
        grafana.instant("prom", "up(")
