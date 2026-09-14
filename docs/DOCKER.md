# Kairos — Docker & Deployment Reference

> **Single source of truth for the container build system, local vs production
> run modes, and AWS deployment.** Read alongside [`INFRA.md`](./INFRA.md)
> (ports, Redis/Qdrant/ES layout, observability) and [`BACKEND.md`](./BACKEND.md).

---

## 1. Design in one picture

Kairos runs one container per service (frontend, API, workers, each datastore,
each observability component). Everything is **local containers except the
managed cloud services**:

| Runs as a container (local / on the AWS box) | Managed cloud service (NOT a container) |
|---|---|
| Frontend, API, Celery + Temporal workers, Go connector | **Supabase** — Postgres DB · Storage (vault, bucket `kairos-vault`) · Auth (JWT) · Vault (secrets) |
| Elasticsearch, Redis, Temporal (+ its own Postgres), Temporal UI, OPA | **Neo4j Aura** — knowledge graph |
| — | **Qdrant Cloud** — vector store · **Grafana Cloud** — observability (traces/metrics via OTLP) |

> **Neo4j + Qdrant moved to cloud.** Their local containers (`kairos-neo4j`, `kairos-qdrant`) are
> **profile-gated** — they do not start by default. Credentials live in `.env` only (never in this
> committed file). For offline dev / tests without touching cloud data:
> `docker compose --profile local-stores up` and point `NEO4J_URI` / `QDRANT_URL` at the local containers.
| | NVIDIA NIM · Jina · Groq (inference APIs) |

There is **no HashiCorp Vault container** and **no app Postgres container** —
those roles are cloud Supabase. The only Postgres in the stack is Temporal's
private internal DB.

---

## 2. Two-file Compose model

The stack is defined by **two files** that select the run mode:

| File | Role | Loaded when |
|------|------|-------------|
| `docker-compose.yml` | **Base — production / AWS-safe.** Non-root images, network isolation, resource limits, healthchecks, only ports **3000 + 8000** published, code baked into images. | Always |
| `docker-compose.override.yml` | **Dev.** Source bind-mounts + hot-reload (`uvicorn --reload`, `next dev`, `go run`), runs as root, publishes every datastore/UI port for debugging. | Auto-loaded by plain `docker compose up` |

```bash
# LOCAL DEV  (base + override, auto)          → hot-reload, all debug ports
docker compose up -d --build        #  ==  make dev

# PRODUCTION / AWS  (base only, override skipped)
docker compose -f docker-compose.yml up -d --build   #  ==  make prod
```

Passing `-f docker-compose.yml` explicitly disables the automatic override
merge — that single flag is the entire dev/prod switch.

---

## 3. Container stack

| Container | Image | Published (dev) | Published (prod) | Network |
|-----------|-------|-----------------|------------------|---------|
| `kairos-frontend` | `kairos-frontend:local` (multi-stage) | 3000 | **3000** | edge |
| `kairos-backend-api` | `kairos-backend:local` (multi-stage) | 8000 | **8000** | edge, internal |
| `kairos-celery-worker` | `kairos-backend:local` (shared) | — | — | internal |
| `kairos-temporal-activity-worker` | `kairos-backend:local` (shared) | — | — | internal |
| `kairos-elicitation-worker` | `kairos-backend:local` (shared) | — | — | internal |
| `kairos-backend-go` | `kairos-connector:local` (multi-stage) | 8090 | — | internal |
| `kairos-neo4j` | `neo4j:5.20-community` | 7474, 7687 | — | internal · **profile `local-stores` only** (cloud by default) |
| `kairos-qdrant` | `qdrant/qdrant:v1.9.4` | 6333, 6334 | — | internal · **profile `local-stores` only** (cloud by default) |
| `kairos-elasticsearch` | `elasticsearch:8.13.4` | 9200, 9300 | — | internal |
| `kairos-redis` | `redis:7.2-alpine` | 6379 | — | internal |
| `kairos-temporal` | `temporalio/auto-setup:1.24.2` | 7233 | — | internal |
| `kairos-temporal_postgres` | `postgres:14-alpine` | — | — | internal |
| `kairos-temporal_ui` | `temporalio/ui:2.26.2` | 8088 | — | internal |
| `kairos-opa` | `openpolicyagent/opa:0.65.0` | 8181 | — | internal |
| `kairos-caddy` | `caddy:2-alpine` | — | **80, 443** | edge · **`--profile prod` only** |

> Observability containers (`kairos-otel-collector`, `kairos-tempo`, `kairos-grafana`) were **removed** —
> the backend exports OTLP directly to **Grafana Cloud** (see INFRA.md §6).

**The four Python services share one image** (`kairos-backend:local`), built
once and reused — they differ only by `command:`. In prod, **only the frontend
and API are reachable from the host**; every datastore stays on the internal
network.

---

## 4. Networks

| Network | Members | Purpose |
|---------|---------|---------|
| `edge` | frontend, **api** | Public-facing. Frontend (SSR) reaches the API here. |
| `internal` | **api** + everything else | Datastores, workers, observability. Never published in prod. |

The API is the only bridge (on both networks). The frontend cannot reach Neo4j,
Redis, Elasticsearch, etc. directly — defence-in-depth for the AWS deployment.

---

## 5. Persistent volumes

| Volume | Mounted at | Holds |
|--------|-----------|-------|
| `kairos-neo4j_data` | neo4j `/data` | **Knowledge graph** (was an anonymous volume before — now durable) |
| `kairos-neo4j_logs` | neo4j `/logs` | Neo4j logs |
| `kairos-qdrant_data` | qdrant `/qdrant/storage` | Vectors |
| `kairos-elasticsearch_data` | es `/usr/share/elasticsearch/data` | Full-text indices |
| `kairos-redis_data` | redis `/data` | AOF (streams, cache, Celery) |
| `kairos-temporal_postgres_data` | temporal-pg `/var/lib/postgresql/data` | Temporal history |

`make nuke` (`docker compose down -v`) destroys all of these. Config files
(`infra/**`) are mounted read-only from the repo, not volumes.

---

## 6. Dockerfiles

### `backend/Dockerfile` — multi-stage, non-root
`builder` installs all deps into `/opt/venv` (with the build toolchain); the
`runtime` stage copies only the venv + the runtime shared libs and runs as user
`kairos` (uid 1001). No `HEALTHCHECK` in the image (it serves both the HTTP API
and non-HTTP workers) — the API's health probe is defined in Compose. Default
`CMD` is the API; workers override `command:`.

### `frontend/Dockerfile` — 4 stages
`deps → dev → builder → runner`. **`dev`** runs `next dev` (used by the dev
override). **`runner`** serves the Next.js **standalone** build (`node server.js`)
as non-root user `nextjs`. Requires `output: "standalone"` in `next.config.ts`.

### `backend/connectors/Dockerfile` — multi-stage, non-root
`builder` (golang:1.25-alpine — bumped from 1.22 for `x/crypto` 0.52) compiles a static binary,
also used for `go run` in dev. `release`
is a tiny Alpine image with just the binary + `fixtures/`, running as non-root
`kairos`.

**`.dockerignore`** trims each build context: `backend/` keeps `tests/` +
`scripts/` (run inside the container), `frontend/` strips `node_modules`,
`.next`, tests. There is no root `Dockerfile`/`.dockerignore` (removed — no
service builds from the repo root).

---

## 7. Health & startup ordering

Every stateful service has a healthcheck, and dependents wait on
`condition: service_healthy`:

- **API** waits for Elasticsearch + Redis + OPA to be *healthy* (fixes the "API boots before ES and
  exits" race). It no longer depends on Neo4j/Qdrant — those are cloud (reached over the network at
  request time, not gated at boot).
- Workers wait for Redis; Temporal workers also wait for Temporal.
- The local Neo4j container (profile `local-stores`) has a `cypher-shell` healthcheck.

---

## 8. Resource limits

Base sets memory ceilings (`deploy.resources.limits.memory`), honored by
`docker compose up`. Approximate ceilings: ES 2g · API/celery/temporal-worker 1.5g each ·
elicitation 1g · Redis 768m · frontend 2g · Temporal/Temporal-PG 512m · OPA/Temporal-UI/Go 256m.

**Neo4j, Qdrant, and observability (Grafana/Tempo/OTEL) are all cloud now** — not in the default
footprint. That removed ~4.5 GB of ceilings and ~2 GB of real idle RAM off the box. **Default ceiling
≈ 12 GB** (limits are ceilings; real idle usage is ~2–3 GB). Adding `--profile local-stores` re-adds
Neo4j 2g + Qdrant 1g. Size the AWS host for the default (see §9).

---

## 9. AWS deployment

**Target:** a single EC2 instance running Docker + Compose v2 (simplest path;
ECS/EKS is a later migration). Recommended: **t3.xlarge / m6i.xlarge (4 vCPU,
16 GB)** with a **≥ 40 GB gp3** EBS volume (images ~5 GB + data).

```bash
# 1. Provision EC2 (Amazon Linux 2023 / Ubuntu 22.04), install Docker + compose plugin.
# 2. Clone the repo onto the instance.
git clone <repo> kairos && cd kairos

# 3. Create the production .env (real secrets — do NOT commit).
cp .env.example .env && $EDITOR .env
#    Set at minimum: SUPABASE_*, NVIDIA_NIM_API_KEY, JINA_API_KEY, GROQ_API_KEY,
#    NEO4J_PASSWORD, INTERNAL_API_KEY, GRAFANA_ADMIN_PASSWORD, APP_SECRET_KEY,
#    APP_DEBUG=False, APP_ENV=production,
#    NEXT_PUBLIC_API_URL=https://<your-domain-or-ALB>  (browser-reachable API URL; build-time value)

# 4. Start production stack (base only — override skipped).
make prod          # == docker compose -f docker-compose.yml up -d --build

# 5. One-time init (runs inside the API container).
make init-all && make seed && make load-dataset
```

### AWS security checklist
- **Security Group:** inbound **80/443 only** (to a reverse proxy) — or 3000 +
  8000 if going direct. **Never** open 6379/7687/9200/7474/etc.; in prod they
  are not published at all, but keep the SG tight regardless.
- **TLS / reverse proxy:** put an ALB or nginx in front of 3000 (frontend) and
  8000 (API). Point `NEXT_PUBLIC_API_URL` at the public API URL; the frontend's
  server-side `API_INTERNAL_URL` stays `http://kairos-backend-api:8000`. Public
  Next.js variables are embedded during `next build`, so change the value before
  `make prod`/the frontend image build and rebuild the image to deploy it.
- **Secrets:** load `.env` from AWS SSM Parameter Store / Secrets Manager at
  deploy time; do not bake secrets into images. `APP_DEBUG=False` disables the
  dev auth bypass — verify it is off.
- **ES has `xpack.security.enabled=false`** — safe only because it is unpublished
  and internal-network-only. Do not expose port 9200 on AWS.
- **Persistence:** the named volumes live on the instance's EBS volume. Snapshot
  EBS for backups, or migrate stores to managed services later.

### Rebuild / redeploy
```bash
git pull
docker compose -f docker-compose.yml up -d --build      # rebuild changed images
docker compose -f docker-compose.yml up -d --no-deps --build kairos-frontend   # one service
```

---

## 10. Common operations

```bash
make dev            # local dev stack (hot-reload, all debug ports)
make prod           # production stack (base only)
make stop           # docker compose down
make nuke           # down -v  ← destroys ALL volumes
make ps / make logs # status / tail logs

# Rebuild one service (new deps)
docker compose up -d --no-deps --build kairos-frontend
docker compose up -d --no-deps --build kairos-backend-api

# Validate compose before running
docker compose config >/dev/null                        # dev merge
docker compose -f docker-compose.yml config >/dev/null  # prod
```

### Image sizes (measured)
| Image | Dev target | Prod target |
|-------|-----------|-------------|
| `kairos-backend:local` | ~1.0 GB | ~1.0 GB |
| `kairos-frontend:local` | ~1.2 GB (`dev`, full node_modules) | ~250 MB (`runner`, standalone) |
| `kairos-connector:local` | ~878 MB (`builder`, Go toolchain) | ~36 MB (`release`) |

Dev-target sizes re-measured 2026-08-17 (`docker images`); the prod `runner`/`release` figures are
from the last prod build and are not re-measured on every change.

The backend was ~2.88 GB originally; multi-stage stripped the build toolchain,
and choosing **Path B** (cloud vision model) for the Layer 3 P&ID parser let the
local ML stack (`torch`/`torchvision`/`ultralytics`/`layoutparser`/`opencv`/
`scipy`/`scikit-learn`/`pandas`) be removed entirely — down to **~986 MB**.

> **Layer 3 note.** P&ID topology extraction uses a cloud VLM (`api/services/pid.py`,
> NIM `llama-3.2-11b-vision-instruct`) — no local model packages, consistent with the cloud-only
> model plane. If **Path A** (custom YOLOv9 + LayoutLMv3) is ever built, it belongs
> in its **own GPU-backed service** with a separate `requirements-cv.txt` — not the
> shared API/worker image.

---

## 11. What changed from the original single-file setup

| Area | Before | After |
|------|--------|-------|
| Compose | one dev-shaped file | base (prod/AWS) + dev override |
| Root `Dockerfile` / `.dockerignore` | empty + orphaned | removed |
| HashiCorp Vault container | ran, unused | removed (cloud Supabase Vault) |
| Neo4j data | anonymous volume (loss risk) | named volume `kairos-neo4j_data` |
| Backend image | single-stage, root, build tools in runtime | multi-stage, non-root, slim runtime |
| Frontend image | dev server only | multi-stage; standalone non-root prod |
| Go connector (prod) | 880 MB builder stage | ~36 MB non-root release stage |
| 4 Python services | 4 separate image builds | one shared image, built once |
| Ports | all datastore ports published | only 3000 + 8000 in prod |
| Networks | one flat network | edge / internal split |
| Healthchecks | missing on Neo4j; API boot race | full coverage + `service_healthy` gates |
| Resource limits | none | memory ceilings on every service |
