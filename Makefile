.PHONY: dev dev-data test test-slow test-all fixtures verify verify-deep load-all

dev:
	docker compose up -d db
	uv run alembic upgrade head
	uv run python -m uvicorn main:app --reload

# Everything the API integration tests need: the release-point inventory, then
# Title 16 at the two release points the tests assert against. Title 16 @ 119-99
# is downloaded from uscode.house.gov (~5 MB); 119-102not101 is in samples/.
dev-data:
	uv run alembic upgrade head
	uv run python -m ingest inventory
	uv run python -m ingest fetch --release 119-99 --title 16
	uv run python -m ingest load data/releases/119-99/usc16.xml --release 119-99 \
		--source-zip data/releases/119-99/xml_usc16@119-99.zip
	uv run python -m ingest load samples/uslm1/usc16.xml --release 119-102not101

test:
	uv run pytest

test-slow:
	uv run pytest -m slow

test-all:
	uv run pytest -m ""

fixtures:
	uv run python scripts/extract_fixture.py

# Counts recorded at load vs. what section_release_map actually holds. Seconds.
verify:
	uv run python -m ingest verify

# Adds an independent recount by re-parsing every source file. Hours on a full
# corpus — this is the one that doesn't just ask the loader to confirm itself.
verify-deep:
	uv run python -m ingest verify --deep

# Load every downloaded title, ledger-driven, resumable (ADR-0014).
load-all:
	uv run python -m ingest load-all
