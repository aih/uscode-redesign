.PHONY: dev dev-web dev-all dev-data ci-data test test-web test-slow test-all fixtures \
        verify verify-deep load-all shots loadtest

# The API alone: /api/v1, the citation redirector at /us/usc, and /docs. The
# reader is a separate process (ADR-0011), so /app answers only under `dev-all`
# or alongside `dev-web`.
dev:
	docker compose up -d db
	uv run alembic upgrade head
	uv run python -m uvicorn main:app --reload

# The reader, on :4321, against whatever API_BASE_URL points at (default :8000).
# Fast iteration on the frontend; the citation URL still belongs to the API.
dev-web:
	cd frontend && npm install && npm run dev

# The whole site on :8000 — Caddy in front of both surfaces, exactly as deployed.
# This is the only target where a pasted citation URL redirects into the reader.
dev-all:
	docker compose up --build

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

# The same two release points as `dev-data`, but with **no network access at
# all**: the inventory comes from a committed JSON instead of OLRC's HTML, and
# Title 16 @ 119-99 from a committed zip instead of a download. CI must not hit
# uscode.house.gov on every push — that violates the source-etiquette rule, and
# ADR-0013 says every consumer pulls from the mirror rather than the origin.
# Committing a 5 MB zip is the cheaper honest answer than wiring CI to S3.
ci-data:
	uv run alembic upgrade head
	uv run python -m ingest inventory --from-file tests/fixtures/releasepoints.json
	rm -rf .ci-data && mkdir -p .ci-data
	unzip -o -q samples/uslm1/xml_usc16@119-99.zip -d .ci-data
	uv run python -m ingest load .ci-data/usc16.xml --release 119-99 \
		--source-zip samples/uslm1/xml_usc16@119-99.zip
	uv run python -m ingest load samples/uslm1/usc16.xml --release 119-102not101
	rm -rf .ci-data

test:
	uv run pytest

# The reader's own tests: the USLM renderer and the reference rules that keep
# `/us/pl/` links off the page (BUILDLOG 008). Since the Jinja reader retired,
# this is where reader coverage lives — CI must run both.
test-web:
	cd frontend && npm install && npm test

test-slow:
	uv run pytest -m slow

test-all:
	uv run pytest -m ""
	$(MAKE) test-web

# Headless screenshots of the demo URL, a TOC and home at 375px and 1280px,
# written to docs/screenshots/. Needs the site running (`make dev-all`).
shots:
	cd frontend && npm run shots

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

# Load test of the top routes against a running `make dev-all` (PLAN Day 6c).
# Needs `brew install hey`. Writes docs/verification/loadtest.json.
loadtest:
	scripts/loadtest.sh
