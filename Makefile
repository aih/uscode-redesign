.PHONY: dev test test-slow test-all fixtures verify

dev:
	docker compose up -d db
	uv run alembic upgrade head
	uv run python -m uvicorn api.main:app --reload

test:
	uv run pytest

test-slow:
	uv run pytest -m slow

test-all:
	uv run pytest -m ""

fixtures:
	uv run python scripts/extract_fixture.py

verify:
	@echo "make verify: not yet implemented (PLAN.md §11.5, Day 7)."
	@echo "Will regenerate docs/verification/ by comparing ingested counts against source XML."
	@exit 1
