# Kairos — Infrastructure Reference

> **For AI coding agents:** This document is the single source of truth for every Docker container, service port, data store configuration, network topology, observability pipeline, and dev command in Kairos. Read alongside `BACKEND.md` (app-level services) and `ARCHITECTURE.md` (layer design).

---

## Table of Contents

1. [Container Stack](#1-container-stack)
2. [Service URLs](#2-service-urls)
3. [Redis DB & Stream Allocation](#3-redis-db--stream-allocation)
4. [Qdrant Collections](#4-qdrant-collections)
5. [Elasticsearch Indices](#5-elasticsearch-indices)
6. [Observability Pipeline](#6-observability-pipeline)
7. [Grafana Dashboards](#7-grafana-dashboards)
8. [Infra Config Files](#8-infra-config-files)
9. [Dev Commands](#9-dev-commands)

---

## 1. Container Stack

All services run as Docker containers. Start with `make dev` (or `docker compose up -d`).

| Container | Image | Port(s) | Purpose |
|-----------|-------|---------|---------| 
| `kairos-frontend` | node:20-alpine (local build) | `3000` | Next.js web app (App Router, dev server) |
| `kairos-backend-api` | Python 3.12 (local build) | `8000` | FastAPI REST API |
| `kairos-celery-worker` | Python 3.12 (local build) | — | Celery workers (ingestion, extraction, attribution, elicitation, transcription, validation) |
| `kairos-temporal-activity-worker` | Python 3.12 (local build) | — | Temporal activity worker (document pipeline) |
| `kairos-elicitation-worker` | Python 3.12 (local build) | — | Temporal worker (elicitation workflows) |
| `kairos-backend-go` | Go 1.25 (local build) | `8090` | OT historian + EAM connector. Go was bumped 1.22 → 1.25 because `golang.org/x/crypto` 0.52 (4 CRITICAL advisories) requires it. |
| `kairos-neo4j` | neo4j:5.20-community | `7474`, `7687` | Temporal knowledge graph — **CLOUD (Neo4j Aura) by default**; local container is profile-gated (`--profile local-stores`) |
| `kairos-qdrant` | qdrant:v1.9.4 | `6333`, `6334` | Vector store — **CLOUD (Qdrant Cloud) by default**; local container is profile-gated |
| `kairos-elasticsearch` | elasticsearch:8.13.4 | `9200` | Full-text search (local container) |
| `kairos-redis` | redis:7.2-alpine | `6379` | Cache + event streams + Celery broker |
| `kairos-temporal` | temporalio/auto-setup:1.24.2 | `7233` | Durable workflow engine |
| `kairos-temporal_ui` | temporalio/ui:2.26.2 | `8088` | Temporal dashboard |
| `kairos-temporal_postgres` | postgres:14-alpine | — | Temporal internal DB |
| `kairos-opa` | openpolicyagent/opa:0.65.0 | `8181` | Policy enforcement — writes + sensitive reads. Reach it as `http://kairos-opa:8181`, **never `localhost`** (inside the API container that is the API itself). Policy is loaded at container start, so `docker compose restart kairos-opa` after editing `kairos.rego` |
| `kairos-caddy` | caddy:2-alpine | `80`, `443` | HTTPS reverse proxy — **`--profile prod` only**, does not start in dev |

> **Observability is CLOUD (Grafana Cloud).** The former local `kairos-otel-collector`, `kairos-tempo`,
> and `kairos-grafana` containers were **removed** — the backend exports traces/metrics directly to the
> Grafana Cloud OTLP gateway (`OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_EXPORTER_OTLP_HEADERS` in `.env`).
> Setup lives in `api/middleware/telemetry.py` (HTTP OTLP exporter, URL-decodes the auth header, appends
> `/v1/traces` · `/v1/metrics`). No-op if the endpoint is unset.

> **Cloud stores:** **Neo4j (Aura)**, **Qdrant Cloud**, and **Supabase** (Postgres + Storage + Auth +
> Vault) are cloud services, not containers — credentials live in `.env` only. The `kairos-neo4j` and
> `kairos-qdrant` containers above **do not start by default**; `docker compose --profile local-stores up`
> brings them back for offline dev / running the test suite without touching cloud data. Point
> `NEO4J_URI` / `QDRANT_URL` at them to use them.
>
> **`NEO4J_LOCAL_PASSWORD` — why the local container has its own credential.** Neo4j rejects any
> initial admin username other than literally `neo4j` (`Invalid admin username, it must be neo4j`),
> so compose hardcodes the user and takes only the password from `NEO4J_LOCAL_PASSWORD`
> (default `kairos_dev_password`). It previously interpolated `${NEO4J_USERNAME}`, which meant the
> local container **crash-looped whenever `.env` pointed at Aura** — precisely when you want local
> stores. To point the app at the local container, also set `NEO4J_USERNAME=neo4j` and
> `NEO4J_PASSWORD=$NEO4J_LOCAL_PASSWORD` in `.env`.
>
> **Run modes & networks:** the stack is split into a production-safe base
> (`docker-compose.yml`) + an auto-loaded dev override (`docker-compose.override.yml`).
> Full build/run/AWS details: [`DOCKER.md`](./DOCKER.md).

---

## 2. Service URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| FastAPI docs | http://localhost:8000/docs |
| FastAPI health | http://localhost:8000/health/detailed |
| Temporal UI | http://localhost:8088 |
| Neo4j Browser | Aura console (cloud) — or http://localhost:7474 with `--profile local-stores` |
| Qdrant Dashboard | Qdrant Cloud console — or http://localhost:6333/dashboard with `--profile local-stores` |
| Grafana / Tempo | Grafana Cloud (hosted — traces + dashboards) |
| OPA | http://localhost:8181/health |
| Go Connector | http://localhost:8090/health |

---

## 3. Redis DB & Stream Allocation

### DB Allocation

| DB | Use |
|----|-----|
| `0` | Application cache + event streams |
| `1` | Celery broker + result backend |
| `2` | Redis Streams (reserved) |

> **Docker note:** Inside containers, `localhost` is not the Redis host. `docker-compose.yml` explicitly sets `REDIS_URL=redis://kairos-redis:6379/0` and `CELERY_BROKER_URL=redis://kairos-redis:6379/1`.

### Redis Streams

| Stream Key | Content |
|------------|---------|
| `kairos:events:work_orders` | WorkOrderEvent payloads |
| `kairos:events:ptw` | PTWEvent payloads |
| `kairos:events:shift_handover` | ShiftHandoverEvent payloads |
| `kairos:events:alarms` | AlarmEvent + DeviationFlagEvent payloads |
| `kairos:events:tag_out` | TagOutEvent payloads |
| `kairos:events:inspections` | InspectionCompleteEvent payloads (non-failed) |
| `kairos:events:briefs` | Assembled brief delivery messages |

---

## 4. Qdrant Collections

| Collection | Dimensions | Purpose |
|------------|-----------|---------| 
| `kairos_documents` | 1024 | Document chunk embeddings (jina-embeddings-v3) |
| `kairos_knowledge` | 1024 | Knowledge graph concept embeddings |

Created on startup by `VectorStoreService.ensure_collections()`.

---

## 5. Elasticsearch Indices

| Index | Content |
|-------|---------|
| `kairos_assets` | Asset tag numbers, names, equipment class |
| `kairos_documents` | Document content + metadata (full-text) |
| `kairos_events` | Operational event log |

Created on startup by `SearchEngineService.ensure_indices()`.

> **Boot race:** `kairos-backend-api` calls `ensure_indices()` on startup and **exits** if Elasticsearch isn't ready yet. After `make dev`, if the API is down, `docker restart kairos-backend-api` once ES is healthy.

---

## 6. Observability Pipeline

```
FastAPI API
  → OTLP/HTTP (api/middleware/telemetry.py)
  → Grafana Cloud OTLP gateway  (OTEL_EXPORTER_OTLP_ENDPOINT + Authorization header, both in .env)
    → traces + metrics, viewed in the hosted Grafana Cloud UI
```

Endpoints are derived as `<endpoint>/v1/traces` and `<endpoint>/v1/metrics`; the auth header is
URL-decoded (`%20` → space) before use. The whole block no-ops if `OTEL_EXPORTER_OTLP_ENDPOINT` is unset.

**FastAPI auto-instrumentation:** `FastAPIInstrumentor`, `RedisInstrumentor`, `HTTPXClientInstrumentor`.

### Custom Metrics

Defined in `api/services/metrics.py` and exported over OTLP to Grafana Cloud — **there is no local
scrape endpoint**. The `:8889/metrics` address documented here previously belonged to the
`kairos-otel-collector` container, which was removed when observability moved to Cloud.

| OTEL instrument | Prometheus name | Instrument type | Labels |
|---|---|---|---|
| `kairos.briefs.delivered` | `kairos_briefs_delivered_total` | Counter | `priority`, `trigger_event_type` |
| `kairos.governor.suppressed` | `kairos_governor_suppressed_total` | Counter | `user_id` |
| `kairos.ingestion.duration` | `kairos_ingestion_duration_seconds` | Histogram | `document_type` |
| `kairos.conflicts.open` | `kairos_conflicts_open` | UpDownCounter (renders as a Prometheus gauge) | `track` |

---

## 7. Grafana Dashboards

**Hosted on Grafana Cloud.** Traces + metrics are exported via OTLP (see §6); view them in your
Grafana Cloud instance. (Pre-cloud, dashboards ran in a local `kairos-grafana` container at `:3001`.)

| Dashboard | UID | Panels |
|-----------|-----|--------|
| Kairos — Ingestion Pipeline | `kairos-ingestion` | 6 panels: docs/hr, p50/p95 duration, ingest rate, type breakdown, request rate, error rate |
| Kairos — Operational Intelligence | `kairos-operational` | 9 panels: briefs/hr, governor suppression, open conflicts, suppression rate, briefs over time, briefs by priority, conflicts by track, governor per-user, traces explorer |

**Both dashboards are imported and live** (2026-08-15) at `/d/kairos-ingestion` and
`/d/kairos-operational`, wired to `grafanacloud-prom` and `grafanacloud-traces`.

Import from **`infra/grafana/dashboards-import/`**, not the `provisioning/` copies. The
provisioning JSONs hardcode datasource uids (`grafana-prom-datasource`, `tempo`) that do not exist
in a Cloud stack, so importing them raw wires every panel to a missing datasource; the
`dashboards-import/` versions use `__inputs` placeholders, which is what makes Grafana show a
datasource picker on the import screen.

> **Custom metrics require telemetry in *every* process that records them.** `services/metrics.py`
> instruments are no-ops without a MeterProvider, and the Celery worker never called
> `setup_telemetry()` — so `kairos_briefs_delivered_total` and `kairos_governor_suppressed_total`,
> which are recorded inside Celery tasks (`brief_engine`, `event_bus`), could never reach Grafana
> no matter how much real traffic ran. Fixed 2026-08-15: `celery_app.py` calls `setup_telemetry()`
> on `worker_process_init` (per forked child — an exporter thread does not survive a fork), and
> `setup_telemetry(app=None)` skips the FastAPI-only instrumentation. Verified by delivering a real
> brief and watching `kairos_briefs_delivered_total` appear in Grafana Cloud.

---

## 8. Infra Config Files

| Path | Purpose | Status |
|------|---------|--------|
| `infra/policies/kairos.rego` | OPA RBAC rules | **Active** (mounted by `kairos-opa`) |
| `infra/temporal/dynamicconfig.yaml` | Temporal server dynamic config | **Active** (mounted by `kairos-temporal`) |
| `infra/caddy/Caddyfile` | HTTPS reverse proxy (prod) | **Active** under `--profile prod` |
| `infra/grafana/provisioning/dashboards/*.json` | Grafana dashboard definitions | **Legacy** — not mounted (obs is Grafana Cloud); **keep** — importable into Grafana Cloud |
| `infra/grafana/provisioning/datasources/`, `infra/otel/otel-config.yaml`, `infra/tempo/tempo.yaml` | Local Grafana/OTEL-collector/Tempo configs | **Dead** — their containers were removed; no runtime use |
| `docker-compose.yml` + `docker-compose.override.yml` | Base (prod-safe) + auto-loaded dev override | **Active** |
| `backend/.dockerignore` | Strips `__pycache__`, `.pyc`, `.pytest_cache`, `connectors/` from the backend build context. Keeps `tests/` + `scripts/` (run inside the container). | **Active** |
| `backend/connectors/.dockerignore` | Strips Go test artifacts and vendor dir from the Go build context. | **Active** |
| `frontend/.dockerignore` | Strips `node_modules`, `.next`, `*.md`, secrets from the frontend build context. | **Active** |

---

## 9. Dev Commands

```bash
make dev          # Build + start all services (docker compose up -d --build)
make stop         # docker compose down
make nuke         # docker compose down -v  ← destroys ALL data volumes
make init-all     # Apply Neo4j schema + create Qdrant collections
make logs         # Tail all service logs
make ps           # Container status
make seed         # seed_regulations.py + seed_users.py
make load-dataset # Load dataset/ through the real pipeline (ARGS=--fast to skip docs)
# Deletes ONLY the prefixes/ids named in purge_test_data.py — NOT `WO-*` or `DOC-*`.
# Those wildcards are the mental model that once DETACH DELETEd four real documents:
# real ids are `DOC-` + 12 random chars, so a bare `DOC-X` prefix matched ~1 in 36.
# Whole ids live in the _EXACT lists and are matched by equality.
make purge-test-data
make verify        # Per-layer smoke + latency (PASS/FAIL table); ARGS=--full adds LLM/VLM checks
make model-gate MODEL=<model-id>   # Layer-0 deployment gate; exits non-zero on regression

# ARCHITECTURE.md §7 — graph query-performance regression check. Asserts plan SHAPE (anchored
# queries resolve through an index seek), not timings, so it catches the constraint-gone-missing
# class of bug without going flaky as the corpus grows. Run after any graph schema change.
make graph-perf

# KG linkage completeness, document-centric, with the unlinked remainder classified.
docker compose run --rm --no-deps kairos-backend-api python benchmark/run_kg_completeness.py

# Cross-functional discovery counterfactual. Embeddings only — no LLM quota, safe to re-run.
docker compose run --rm --no-deps kairos-backend-api python benchmark/run_cross_functional.py

# OCR accuracy vs the dataset's clean/degraded pairings. Costs ~4 OCR calls — do NOT run it
# alongside run_benchmark.py, which reports INVALID if any question hits a 429.
docker compose run --rm --no-deps kairos-backend-api python benchmark/run_ocr_gate.py

# Document submission-pattern audit (ARCHITECTURE §8 anti-poisoning). No model calls.
docker compose run --rm --no-deps kairos-backend-api python scripts/audit_submission_patterns.py

# Layer-4 corpus backfill. DRY RUN by default — prints the gap and writes nothing.
# --events is free (no model calls); --entities costs ~1 NIM call per document.
docker compose run --rm --no-deps kairos-backend-api python scripts/backfill_graph_nodes.py
docker compose run --rm --no-deps kairos-backend-api python scripts/backfill_graph_nodes.py --events --apply

# Rebuild specific containers
docker compose up -d --no-deps --build kairos-frontend          # new npm deps only
docker compose up -d --no-deps --force-recreate kairos-backend-api  # NIM env changes

# Seed test users (required after make nuke)
docker exec kairos-backend-api python scripts/seed_users.py

# Seed compliance regulations into Neo4j
docker exec kairos-backend-api python scripts/seed_regulations.py

# NEVER run tests, pytest, npm or tsc on the host — host package resolution differs from the
# pinned images and produces false failures (auth.test.ts / api.test.ts fail on host, pass in
# the container). Everything below runs in Docker.

# Run tests — full suite (needs the stack up; use local stores, never cloud)
docker exec kairos-backend-api python -m pytest tests/ -q --timeout=120

# Run the service-free tests with NO stack running at all (146 tests, no secrets, no network).
# This is what CI's tier-1 `unit` job runs. Re-measured 2026-08-17.
docker compose run --rm --no-deps -e KAIROS_SKIP_TEST_CLEANUP=1 kairos-backend-api \
  pytest -q tests/test_{pii,query_category,search_fusion,ingestion_formats,http_pool,\
model_validation,pid,auth_cache,config_guardrail,briefs_countersign,topology_verify,\
ot_coverage,phase_gate,extraction_path,timestamp_alignment,model_gate_classes,ner_parse,\
superseded_filter,brief_signing}.py

# Lint the backend exactly as CI does (pinned ruff + backend/ruff.toml)
docker run --rm -v "$(pwd)/backend:/b" -w /b ghcr.io/astral-sh/ruff:0.16.0 check .

# Validate the compliance Cypher against a local Neo4j (EXPLAIN + semantics)
docker compose run --rm --no-deps -e NEO4J_URI=bolt://kairos-neo4j:7687 \
  -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD=kairos_dev_password -e NEO4J_DATABASE=neo4j \
  kairos-backend-api python scripts/verify_compliance_cypher.py

# AST parse check before waiting on Docker
python3 -c "import ast; ast.parse(open('backend/api/routers/events.py').read())"

# Check logs
docker logs kairos-backend-api 2>&1 | tail -30
docker logs kairos-celery-worker 2>&1 | tail -30
docker logs kairos-temporal-activity-worker 2>&1 | tail -20

# Trigger EAM sync (Go connector)
curl -X POST http://localhost:8090/eam/sync
```

### After `make nuke`

```bash
make dev → make init-all → make seed → make load-dataset
```
