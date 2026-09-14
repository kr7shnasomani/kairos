# Kairos — Developer Makefile (100% Dockerized)
# Usage: make <target>

# Every target here is a command, not a file. `benchmark` in particular MUST stay
# listed: the repo has a `benchmark/` directory, so without this Make considers the
# target satisfied by the directory and prints "'benchmark' is up to date" while
# silently running nothing — exit 0, no benchmark, a green CI step that did no work.
.PHONY: help dev prod stop nuke logs ps \
        api workers connectors \
        init-neo4j init-qdrant init-all \
        seed load-dataset purge-test-data wipe-local reset-local \
        test test-api test-connectors \
        verify benchmark model-gate \
        lint format

# Default target
help:
	@echo ""
	@echo "  Kairos — Industrial Operational Intelligence Platform"
	@echo "  ======================================================="
	@echo ""
	@echo "  Infrastructure & Apps"
	@echo "    make dev          Start ALL services (Databases + API + Workers + Connectors)"
	@echo "    make stop         Stop all Docker services"
	@echo "    make nuke         Stop and delete all volumes (DESTROYS DATA)"
	@echo "    make logs         Tail logs for all services"
	@echo "    make ps           Show running service status"
	@echo ""
	@echo "  Initialisation"
	@echo "    make init-neo4j   Apply Neo4j schema (Cypher)"
	@echo "    make init-qdrant  Create Qdrant collections"
	@echo "    make init-all     Run all init scripts"
	@echo ""
	@echo "  Quality (Runs inside containers)"
	@echo "    make test         Run all tests"
	@echo "    make lint         Run linters (ruff + golangci-lint)"
	@echo "    make format       Auto-format code (ruff + gofmt)"
	@echo ""

# =============================================================================
# Infrastructure & Application
# =============================================================================

dev:
	docker compose up -d --build
	@echo ""
	@echo "  Services:"
	@echo "    API (FastAPI):   http://localhost:8000/docs"
	@echo "    Neo4j Browser:   http://localhost:7474"
	@echo "    Qdrant UI:       http://localhost:6333/dashboard"
	@echo "    Temporal UI:     http://localhost:8088"
	@echo "    Grafana:         http://localhost:3001  (admin / kairos_dev_password)"
	@echo ""

# Production / AWS: base only (no override) — no bind-mounts, no debug ports,
# non-root images, network isolation, resource limits. See docs/DOCKER.md.
prod:
	docker compose -f docker-compose.yml up -d --build
	@echo ""
	@echo "  Kairos (production mode) — only ports 3000 (frontend) + 8000 (API) published."
	@echo ""

stop:
	docker compose down

nuke:
	@echo "WARNING: This will destroy all local data volumes. Press Ctrl+C to cancel."
	@sleep 3
	docker compose down -v

logs:
	docker compose logs -f

ps:
	docker compose ps

# =============================================================================
# Initialisation (Executes inside the API container)
# =============================================================================

init-neo4j:
	docker compose exec kairos-backend-api python scripts/init_neo4j.py

init-qdrant:
	docker compose exec kairos-backend-api python scripts/init_qdrant.py

# Local Elasticsearch is per-machine and never synced from the cloud stores, so a fresh clone
# always starts with an empty search index. db/snapshots/kairos-es-data.tar.gz is a checked-in
# snapshot of that index for the golden dataset — restoring it here means every laptop that
# clones this repo gets identical local search data with zero manual steps and zero OCR/NIM cost.
import-search-index:
	@if [ -f db/snapshots/kairos-es-data.tar.gz ]; then \
		docker compose stop kairos-elasticsearch; \
		docker run --rm -v kairos_kairos-elasticsearch_data:/data -v "$(PWD)/db/snapshots":/backup alpine \
			sh -c "rm -rf /data/* && tar xzf /backup/kairos-es-data.tar.gz -C /data"; \
		docker compose up -d kairos-elasticsearch; \
		echo "Local search index restored from db/snapshots/kairos-es-data.tar.gz"; \
	else \
		echo "No snapshot at db/snapshots/kairos-es-data.tar.gz — run 'make export-search-index' on a machine with real data first."; \
	fi

# Run this after `load-dataset`, whenever the golden dataset changes, then commit the updated
# tarball — it's how the snapshot above stays current.
export-search-index:
	docker compose stop kairos-elasticsearch
	@mkdir -p db/snapshots
	docker run --rm -v kairos_kairos-elasticsearch_data:/data -v "$(PWD)/db/snapshots":/backup alpine \
		tar czf /backup/kairos-es-data.tar.gz -C /data .
	docker compose up -d kairos-elasticsearch
	@echo "Wrote db/snapshots/kairos-es-data.tar.gz — commit it so every clone stays in sync."

# Schema only. It deliberately does not run import-search-index: every documented setup follows
# init-all with load-dataset, which indexes the corpus itself, and restoring the snapshot first
# left Elasticsearch holding a second copy under document IDs the other stores do not have.
# Run import-search-index on its own only when pointing a fresh clone at already-loaded cloud stores.
init-all: init-neo4j init-qdrant
	@echo "All datastores initialized."

# =============================================================================
# Seeding & golden dataset (Executes inside the API container)
# =============================================================================

seed:
	docker compose exec kairos-backend-api python scripts/seed_regulations.py
	docker compose exec kairos-backend-api python scripts/seed_users.py

# Load the canonical demo corpus (dataset/) through the real ingestion pipeline.
# Append ARGS=--fast to skip the document pipeline (structured backbone + events only).
load-dataset:
	docker compose exec kairos-backend-api python scripts/load_demo_dataset.py $(ARGS)

# Delete integration-test residue (ASSET-TEST/DEDUP/EV/ACK-*, WO-*, DOC-*) from every store.
purge-test-data:
	docker compose exec kairos-backend-api python scripts/purge_test_data.py

# Empty the local stores (Neo4j + ES + Qdrant). Supabase is reset via db/maintenance/reset_all_data.sql.
wipe-local:
	docker compose exec kairos-backend-api python scripts/wipe_local_stores.py

# One-shot pristine reset of local stores + reload the golden dataset.
# (Truncate cloud Supabase first with db/maintenance/reset_all_data.sql — done separately.)
reset-local: wipe-local seed load-dataset
	@echo "Local stores wiped, reseeded, and reloaded from the golden dataset."

# =============================================================================
# Tests (Executes inside containers)
# =============================================================================

test: test-api test-connectors

test-api:
	docker compose exec kairos-backend-api pytest tests/ -v --tb=short

test-connectors:
	docker compose exec kairos-backend-go go test ./...

# Per-layer smoke + latency table (append ARGS=--full for the slow LLM/VLM checks)
verify:
	docker compose exec kairos-backend-api python benchmark/verify_layers.py $(ARGS)

# Domain-expert benchmark scorecard (append ARGS=--synthesize for answer quality; hits NIM)
benchmark:
	docker compose exec kairos-backend-api python benchmark/run_benchmark.py $(ARGS)

# Layer-0 deployment gate. Exits non-zero when the candidate model regresses against the
# incumbent baseline, so it can gate a release:  make model-gate MODEL=meta/llama-3.2-11b-vision-instruct
# Reports only — halting extraction per asset class additionally requires MODEL_GATE_ENFORCE=true.
model-gate:
	docker compose exec kairos-backend-api python scripts/run_model_validation.py --model-name $(MODEL) $(ARGS)

# ARCHITECTURE.md §7 — query-performance regression check for graph schema changes.
# Asserts plan SHAPE (anchored queries resolve through an index seek), not timings: the
# regression this catches is `asset_id_unique` going missing and the Layer 4 hot path
# silently degrading to a NodeByLabelScan, which returns correct rows and fails nothing.
# Run it after any change to db/neo4j/init_schema.cypher or a hot-path query.
.PHONY: graph-perf
graph-perf:
	docker compose run --rm --no-deps kairos-backend-api python scripts/verify_graph_perf.py

# =============================================================================
# Quality (Executes inside containers)
# =============================================================================

lint:
	docker compose exec kairos-backend-api ruff check .
	docker compose exec kairos-backend-go golangci-lint run

format:
	docker compose exec kairos-backend-api ruff format .
	docker compose exec kairos-backend-go gofmt -w .
