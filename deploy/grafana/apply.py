"""Applies the dashboard and alert rules in this directory to Grafana Cloud.

    GRAFANA_URL=https://<stack>.grafana.net GRAFANA_TOKEN=... \
        ALERT_EMAIL=... python3 deploy/grafana/apply.py [--discover-only]

Run by .github/workflows/grafana.yml (ADR-0090). Stdlib only, so the runner
needs no install. Every step is idempotent: the folder and contact point are
created or updated by uid, the dashboard is saved with `overwrite`, and the
rule group is replaced whole.

It first prints what the stack holds — the data sources, the metric names
the two services report, and the labels on the request histogram — so the
log shows what the queries are written against.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOBS = 'job=~"uscode-api|statutes-api"'
HISTOGRAM = "http_server_request_duration_seconds_count"
# A GET that meets a 5xx or no answer at all is tried again after each of
# these pauses: Grafana Cloud's data source proxy answers 503 DatasourceError
# for minutes at a time (the weekly summary of 2026-10-05).
RETRY_PAUSES = (15, 60, 180, 600)


class Grafana:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

    def call(
        self,
        method: str,
        path: str,
        body: object | None = None,
        ok: tuple[int, ...] = (),
        retry: bool | None = None,
    ) -> tuple[int, object]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.url + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Disable-Provenance": "true",
            },
        )
        if retry is None:
            retry = method == "GET"
        pauses = list(RETRY_PAUSES) if retry else []
        while True:
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status, raw = response.status, response.read()
            except urllib.error.HTTPError as error:
                status, raw = error.code, error.read()
            except (urllib.error.URLError, TimeoutError) as error:
                if not pauses:
                    sys.exit(f"{method} {path}: {error}")
                status, raw = 0, str(error).encode()
            if (status == 0 or status >= 500) and pauses:
                pause = pauses.pop(0)
                print(f"{method} {path}: {status or raw.decode()}; again in {pause}s")
                time.sleep(pause)
                continue
            break
        try:
            payload: object = json.loads(raw) if raw else None
        except ValueError:
            payload = raw[:300].decode(errors="replace")
        if status >= 400 and status not in ok:
            sys.exit(f"{method} {path}: {status} {payload}")
        return status, payload

    def prom(self, uid: str, path: str, params: dict[str, str]) -> object:
        query = urllib.parse.urlencode(params)
        _, payload = self.call(
            "GET", f"/api/datasources/proxy/uid/{uid}/api/v1/{path}?{query}"
        )
        return payload.get("data") if isinstance(payload, dict) else payload

    def instant(self, uid: str, expr: str) -> dict[str, list[dict]]:
        """One instant PromQL query through `/api/ds/query`, in Prometheus's shape.

        `/api/ds/query` is the path Grafana's own dashboards and alert rules
        query through; the data source proxy `prom()` uses answered 503
        DatasourceError on every query from 2026-10-05 while it kept working.
        The frames are turned back into `{"result": [{"metric", "value"}]}`.
        """
        _, payload = self.call(
            "POST",
            "/api/ds/query",
            {
                "from": "now-5m",
                "to": "now",
                "queries": [
                    {
                        "refId": "A",
                        "datasource": {"type": "prometheus", "uid": uid},
                        "expr": expr,
                        "instant": True,
                        "range": False,
                    }
                ],
            },
            retry=True,
        )
        answer = (payload or {}).get("results", {}).get("A", {})
        if answer.get("error"):
            sys.exit(f"query failed: {answer['error']}\n  {expr}")
        result = []
        for frame in answer.get("frames", []):
            fields = frame.get("schema", {}).get("fields", [])
            values = frame.get("data", {}).get("values", [])
            for index, field in enumerate(fields):
                if field.get("type") != "number" or index >= len(values):
                    continue
                for value in values[index]:
                    if value is not None:
                        result.append(
                            {"metric": field.get("labels") or {}, "value": [0, str(value)]}
                        )
        return {"result": result}


def discover(grafana: Grafana) -> str:
    _, sources = grafana.call("GET", "/api/datasources")
    print("data sources:")
    for source in sources:
        print(f"  {source['type']:<12} {source['name']}  uid={source['uid']}")
    proms = [
        s for s in sources if s["type"] == "prometheus" and s["name"].endswith("-prom")
    ]
    if not proms:
        sys.exit("no Prometheus data source named *-prom")
    uid = proms[0]["uid"]

    names = grafana.prom(
        uid, "query", {"query": f"count by (__name__, job) ({{{JOBS}}})"}
    )
    print(f"metrics reported by {JOBS}:")
    for row in (names or {}).get("result", []):
        metric = row["metric"]
        print(
            f"  {metric.get('job')}  {metric.get('__name__')}  ({row['value'][1]} series)"
        )
    labels = grafana.prom(uid, "labels", {"match[]": f"{HISTOGRAM}{{{JOBS}}}"})
    print(f"labels on {HISTOGRAM}: {', '.join(labels or []) or '(none: no data yet)'}")
    return uid


def apply(grafana: Grafana, prom_uid: str, email: str) -> None:
    alerts = json.loads((HERE / "alerts.json").read_text())
    folder = alerts["folder"]
    status, _ = grafana.call("GET", f"/api/folders/{folder['uid']}", ok=(404,))
    if status == 404:
        grafana.call("POST", "/api/folders", folder)
    print(f"folder: {folder['title']}")

    dashboard = json.loads((HERE / "dashboard.json").read_text())
    _, saved = grafana.call(
        "POST",
        "/api/dashboards/db",
        {
            "dashboard": {**dashboard, "id": None},
            "folderUid": folder["uid"],
            "overwrite": True,
        },
    )
    print(f"dashboard: {grafana.url}{saved.get('url', '')}")

    receiver = "grafana-default-email"
    if email:
        receiver = "uscode-email"
        point = {
            "uid": receiver,
            "name": receiver,
            "type": "email",
            "settings": {"addresses": email},
        }
        status, _ = grafana.call(
            "PUT",
            f"/api/v1/provisioning/contact-points/{receiver}",
            point,
            ok=(400, 404, 500),
        )
        if status >= 400:
            grafana.call("POST", "/api/v1/provisioning/contact-points", point)
    print(f"contact point: {receiver}")

    rules = json.loads(
        json.dumps(alerts["rules"])
        .replace("${PROM}", prom_uid)
        .replace("${RECEIVER}", receiver)
    )
    for rule in rules:
        rule["folderUID"] = folder["uid"]
        rule["ruleGroup"] = alerts["group"]
    grafana.call(
        "PUT",
        f"/api/v1/provisioning/folder/{folder['uid']}/rule-groups/{alerts['group']}",
        {"title": alerts["group"], "interval": alerts["interval"], "rules": rules},
    )
    print(f"alert rules: {', '.join(rule['title'] for rule in rules)}")


def require_env() -> tuple[str, str]:
    url, token = os.environ.get("GRAFANA_URL", ""), os.environ.get("GRAFANA_TOKEN", "")
    if not url or not token:
        sys.exit("GRAFANA_URL and GRAFANA_TOKEN must be set")
    return url, token


def main() -> None:
    url, token = require_env()
    grafana = Grafana(url, token)
    prom_uid = discover(grafana)
    if "--discover-only" not in sys.argv:
        apply(grafana, prom_uid, os.environ.get("ALERT_EMAIL", ""))


if __name__ == "__main__":
    main()
