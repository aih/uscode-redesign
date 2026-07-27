.PHONY: dev test verify

dev:
	docker compose up -d db
	uv run alembic upgrade head
	uv run python -m uvicorn api.main:app --reload

test:
	uv run pytest

verify:
	@echo "make verify: not yet implemented (PLAN.md §11.5, Day 7)."
	@echo "Will regenerate docs/verification/ by comparing ingested counts against source XML."
	@exit 1
