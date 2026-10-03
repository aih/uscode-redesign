"""Reports the shape of the Grafana Cloud OTLP settings, never their value.

    OTLP_ENDPOINT=... OTLP_HEADERS=... python3 deploy/otel-check.py

Run by deploy.yml before it stores the two secrets (ADR-0089). Prints the
length and form of the header, the decoded instance id and the token's
prefix and length, then sends one empty metrics request and prints Grafana's
status and reply. Emits a GitHub `::warning::` for each problem it finds and
always exits 0.
"""

from __future__ import annotations

import base64
import binascii
import os
import re
import urllib.error
import urllib.parse
import urllib.request

PREFIX = "Authorization=Basic%20"


def warn(message: str) -> None:
    print(f"::warning::otel-check: {message}")


def check_header(raw: str) -> str | None:
    spaces = bool(re.search(r"\s", raw))
    quotes = '"' in raw or "'" in raw
    print(
        f"header: length {len(raw)}, starts with {PREFIX!r}: {raw.startswith(PREFIX)}, "
        f"whitespace: {spaces}, quotes: {quotes}, 'Basic' occurs {raw.count('Basic')} time(s)"
    )
    if not raw.startswith(PREFIX):
        warn(f"the header must start with {PREFIX}")
        return None
    if spaces or quotes:
        warn("the header contains whitespace or quotes; paste it again without them")
    encoded = urllib.parse.unquote(raw[len(PREFIX) :]).strip()
    try:
        decoded = base64.b64decode(encoded, validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        warn(f"the {len(encoded)} characters after {PREFIX} are not valid base64")
        return None
    instance, sep, token = decoded.partition(":")
    print(
        f"decoded: instance id {instance if instance.isdigit() else '(not a number)'}, "
        f"separator present: {bool(sep)}, token starts with 'glc_': {token.startswith('glc_')}, "
        f"token length {len(token)}"
    )
    if not (instance.isdigit() and sep and token.startswith("glc_")):
        warn("the decoded value should be <instance id>:glc_<token>")
    return "Basic " + encoded


def check_endpoint(endpoint: str, auth: str | None) -> None:
    print(f"endpoint: {endpoint}")
    if not re.fullmatch(
        r"https://otlp-gateway-[a-z0-9-]+\.grafana\.net/otlp/?", endpoint
    ):
        warn(
            "the endpoint should look like https://otlp-gateway-<region>.grafana.net/otlp"
        )
    if auth is None:
        return
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/metrics",
        data=b"",
        method="POST",
        headers={"Content-Type": "application/x-protobuf", "Authorization": auth},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    except OSError as error:
        print(f"grafana: no answer ({type(error).__name__})")
        return
    print(f"grafana: {status} {body[:200].decode(errors='replace')!r}")
    if status >= 400:
        warn(f"Grafana answered {status} to an empty metrics request")


def main() -> None:
    endpoint = os.environ.get("OTLP_ENDPOINT", "")
    raw = os.environ.get("OTLP_HEADERS", "")
    if not endpoint or not raw:
        print("telemetry secrets not set")
        return
    check_endpoint(endpoint, check_header(raw))


if __name__ == "__main__":
    main()
