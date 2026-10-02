"""FastAPI's built-in OpenTelemetry, as main.py configures it (ADR-0089).

The app under test is a small one built with main's own `TELEMETRY` and an
in-memory exporter, so nothing here touches the global providers that the
real app would export through on the box.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from main import TELEMETRY


def _traced_app() -> tuple[TestClient, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    app = FastAPI(
        telemetry={
            **TELEMETRY,
            "tracer_provider": provider,
            "metrics": False,
            "logs": False,
            "auto_configure": False,
        }
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/us/usc/{identifier:path}")
    def section(identifier: str) -> dict[str, str]:
        return {"identifier": identifier}

    return TestClient(app), exporter


def test_a_route_is_traced_under_its_template() -> None:
    client, exporter = _traced_app()
    assert client.get("/api/v1/us/usc/t16/s45f").status_code == 200
    server = [s for s in exporter.get_finished_spans() if s.parent is None]
    assert len(server) == 1
    assert server[0].attributes["http.route"] == "/api/v1/us/usc/{identifier}"


def test_health_is_not_traced() -> None:
    client, exporter = _traced_app()
    assert client.get("/health").status_code == 200
    assert exporter.get_finished_spans() == ()


def test_the_real_app_carries_the_config() -> None:
    from main import _untraced

    assert TELEMETRY["exclude"] is _untraced
    assert _untraced({"type": "http", "path": "/health"})
    assert not _untraced({"type": "http", "path": "/api/v1/status"})
