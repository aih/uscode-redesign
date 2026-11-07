"""Make an API token for `/api/v1` (ADR-0096) and print its settings entry.

    uv run python scripts/api_token.py reintroductions --scale 20

Prints the token once, for the caller, and the `USC_API_TOKENS` entry, which
holds only its SHA-256 digest, for the box's `.env`.
"""

import argparse
import hashlib
import json
import secrets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="who holds the token, e.g. reintroductions")
    ap.add_argument("--scale", type=float, default=10, help="multiplier on every per-caller budget")
    args = ap.parse_args()
    token = "usc_" + secrets.token_urlsafe(32)
    entry = {args.name: {"sha256": hashlib.sha256(token.encode()).hexdigest(), "scale": args.scale}}
    print(f"token (give to the caller, store nowhere else): {token}")
    print(f"USC_API_TOKENS entry: {json.dumps(entry)}")


if __name__ == "__main__":
    main()
