.PHONY: dev dev-web dev-all dev-data ci-data ci-classification-data \
        test test-web test-slow test-all fixtures \
        verify verify-deep load-all shots loadtest navprofile spine-explain \
        test-e2e test-a11y demo-video measure footnav mobilebar diffcost

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
# COMMIT_SHA is what the footer names. The frontend image builds from
# ./frontend, which contains no .git, so the checkout's HEAD has to be handed
# to the build rather than read inside it.
dev-all:
	COMMIT_SHA=$$(git rev-parse HEAD 2>/dev/null || echo unknown) docker compose up --build

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
ci-data: ci-classification-data
	uv run alembic upgrade head
	uv run python -m ingest inventory --from-file tests/fixtures/releasepoints.json
	rm -rf .ci-data && mkdir -p .ci-data
	unzip -o -q samples/uslm1/xml_usc16@119-99.zip -d .ci-data
	uv run python -m ingest load .ci-data/usc16.xml --release 119-99 \
		--source-zip samples/uslm1/xml_usc16@119-99.zip
	uv run python -m ingest load samples/uslm1/usc16.xml --release 119-102not101
	rm -rf .ci-data

# The classification tables (ADR-0067), offline for the same reason: the
# committed slices copied to the filenames the index pages link, then loaded
# through `--from-file`, which reads a directory instead of the network. The
# artifacts go under .ci-data — a slice is ~80 rows and the committed
# docs/verification/classification-*.json describe the real files.
CLS_DIR = .ci-data/classification

ci-classification-data:
	uv run alembic upgrade head
	rm -rf $(CLS_DIR) && mkdir -p $(CLS_DIR)
	cp tests/fixtures/tables_slice.shtml $(CLS_DIR)/tables.shtml
	cp tests/fixtures/priortables_slice.shtml $(CLS_DIR)/priortables.shtml
	cp tests/fixtures/tbl118pl_2nd_slice.htm $(CLS_DIR)/tbl118pl_2nd.htm
	cp tests/fixtures/tbl110pl_1st_slice.htm $(CLS_DIR)/tbl110pl_1st.htm
	cp tests/fixtures/tbl104pl_slice.htm $(CLS_DIR)/tbl104pl.htm
	cp tests/fixtures/ecct.html $(CLS_DIR)/ecct.html
	uv run python -m ingest classification --force --from-file $(CLS_DIR) \
		--out $(CLS_DIR)/verification --manifest $(CLS_DIR)/manifest.json
	rm -rf $(CLS_DIR)

test:
	uv run pytest

# The reader's own tests: the USLM renderer and the reference rules that keep
# `/us/pl/` links off the page (BUILDLOG 008). Since the Jinja reader retired,
# this is where reader coverage lives — CI must run both.
test-web:
	cd frontend && npm install && npm test

# What only a browser can answer (Session 10): hover timers and the three WCAG
# 1.4.13 clauses of the citation preview, `position: sticky` geometry, the
# `scroll-margin-top` that keeps a deep-linked provision out from behind the
# sticky bar, and the citation box end to end. Needs the site running
# (`make dev-all`) — it tests the deployed shape, two processes behind Caddy,
# rather than a second and lying copy of it.
test-e2e:
	cd frontend && npm install && npx playwright test

# The accessibility scan alone (ADR-0039) — the same spec `test-e2e` already
# runs, on its own, because it is the one that regenerates a committed
# artifact. Every route in docs/a11y/routes.json against axe-core's WCAG 2.1 AA
# tag set, at three viewports, in both themes, once under forced-colors, plus
# the interactive states; results to docs/verification/a11y.json.
#
# It fails on any violation whose (route, rule) pair is not in
# docs/a11y/known-violations.json, and on any serious or critical violation
# whose entry does not name that severity. Needs the site running
# (`make dev-all`).
test-a11y:
	cd frontend && npm install && npx playwright test a11y.spec.ts

test-slow:
	uv run pytest -m slow

test-all:
	uv run pytest -m ""
	$(MAKE) test-web

# Headless screenshots of the demo URL, a TOC and home at 375px and 1280px,
# written to docs/screenshots/. Needs the site running (`make dev-all`).
shots:
	cd frontend && npm run shots

# Characters per line of statutory text, at three widths, counted from where the
# browser broke the lines (ADR-0052) -> docs/verification/measure.json. Also the
# scroll length of three sections, which is what the measure costs. Needs the
# site running (`make dev-all`).
#
# The band check here is a second copy of the one `make test-e2e` runs on every
# push (tests/e2e/typography.spec.ts, over scripts/measure-lines.mjs). What only
# this target produces is documentHeights, which gates nothing and therefore
# names the commit it was measured at.
measure:
	cd frontend && node scripts/measure.mjs

# What the API's redline costs with and without the @id guid churn, per section
# (ADR-0066) -> docs/verification/diffcost.json. Times the diff in process, so
# the endpoint's own rate limiter is not in the way. Needs the site running
# (`make dev-all`).
diffcost:
	uv run python scripts/diffcost.py

# How tall the footer's own links are once opened, at six widths, and how many
# columns they are in (ADR-0062) -> docs/verification/footnav.json. Needs the
# site running (`make dev-all`).
footnav:
	cd frontend && node scripts/footnav.mjs

# What the header costs below the desktop breakpoint — the bar, the search row
# under it, the smallest hit target on either, and the sticky stack they feed
# (ADR-0064) -> docs/verification/mobilebar.json. Needs the site running
# (`make dev-all`).
mobilebar:
	cd frontend && node scripts/mobilebar.mjs

# The demo video (ADR-0038): replays every scenario in the user guide flagged
# `demo: true`, in `demoOrder`, with that scenario's own captions burned on
# screen, and stitches the scenes into docs/demo/uscode-demo.mp4. The captions
# come from the guide, so the video cannot claim something the guide does not.
#
# Needs the site running (`make dev-all`) and ffmpeg (`brew install ffmpeg`).
# GUIDE_CORPUS=1 because two scenes — a redline with real amendments, a guid
# permalink — need more than the two release points CI loads.
#
# The mp4 is gitignored; docs/demo/scenes.json and uscode-demo.vtt are
# committed, so what the video says is reviewable in a diff.
demo-video:
	cd frontend && GUIDE_CORPUS=1 node scripts/demovideo.mjs

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

# Load test of the top routes: how many requests per second each holds. Every
# row names the ADR-0029 limiter that governs it and whether it was held inside
# that budget or driven past it on purpose. Needs `brew install hey` and a
# running stack — `make dev-all`, or BASE= the deployed host.
# Writes docs/verification/loadtest.json.
loadtest:
	scripts/loadtest.sh

# The other half of the same question: how long *one* reader waits, per journey,
# and which surface spent it. Times the same paths from the internet, from the
# box's loopback through Caddy, and against the Astro and FastAPI containers
# directly, so the layer split is measured rather than inferred. Needs AWS
# credentials for the box (SSM). Writes docs/verification/navprofile.json.
navprofile:
	uv run python scripts/navprofile.py

# EXPLAIN (ANALYZE, BUFFERS) for every query the spine actually runs, against
# the deployed corpus — the only place the 96 M-row guid_map exists. Needs the
# same SSM access. Writes docs/verification/spine-explain.json.
spine-explain:
	scripts/spine_explain.sh
