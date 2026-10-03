<img width="2048" height="918" alt="image" src="https://github.com/user-attachments/assets/92f54712-99e9-4e93-aadc-b3105b897372" /><div align="center">
</div>

<div align="center">

[Live Demo](https://kairos-deterium.vercel.app) · [Solution](./docs/ARCHITECTURE.md) · [Demo Video](https://drive.google.com/file/d/18ZO95MckNtESg-Z2ruRBNnKq6JyB57rP/view) · [Documentation](./docs/)

A 13-layer platform organised into five planes: **perception, knowledge, governance, retrieval, and delivery**. A FastAPI core orchestrates five datastores, durable Temporal workflows, Celery workers, and Go OT connectors, with a Next.js interface on top.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-Graph_DB-018BFF?style=flat-square&logo=neo4j&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-FF0000?style=flat-square&logo=qdrant&logoColor=white)
![Elasticsearch](https://img.shields.io/badge/Elasticsearch-Exact_Search-005571?style=flat-square&logo=elasticsearch&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-Auth_%26_Storage-3ECF8E?style=flat-square&logo=supabase&logoColor=white)
![Temporal](https://img.shields.io/badge/Temporal-Workflows-111111?style=flat-square)
![Redis](https://img.shields.io/badge/Redis-Streams_%26_Cache-DC382D?style=flat-square&logo=redis&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-Frontend-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Local_Infra-2496ED?style=flat-square&logo=docker&logoColor=white)
![Go](https://img.shields.io/badge/Go-OT_Connectors-00ADD8?style=flat-square&logo=go&logoColor=white)
![NVIDIA_NIM](https://img.shields.io/badge/NVIDIA_NIM-LLM_Synthesis-76B900?style=flat-square&logo=nvidia&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-Observability-F46800?style=flat-square&logo=grafana&logoColor=white)

</div>

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Key Capabilities](#key-capabilities)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Repository Layout](#repository-layout)
- [License](#license)

---

## Overview

Asset-intensive facilities, such as refineries, plants, pipelines, and power stations, run on knowledge scattered across disconnected systems. P&IDs live in one archive, maintenance history in another, standard operating procedures in a third, inspection records and regulatory filings elsewhere again. A technician standing in front of a failing pump cannot see that the same seal failed twice before, that the OEM revised the spec eighteen months ago, or that an isolation valve is overdue for inspection. The most dangerous gaps are the ones nobody knows to query, and the people who hold that context in their heads are retiring faster than they are being replaced.

**Kairos** turns that fragmented, tribal knowledge into a single **governed, temporal knowledge graph** and delivers the right information to the right person at the exact moment it is needed, doing so *proactively* with a source citation behind every claim. It ingests heterogeneous documents, extracts and links their entities, records how every fact changes over time, and surfaces answers, briefs, root-cause analyses, and compliance evidence on any device.

Three principles run through the entire platform:

> **Never assert without provenance. Never auto-promote unverified input. Refuse rather than hedge on a safety-critical question.**

These principles are enforced in the data model (every fact is an edge that carries its own authority and verification status), in the ingestion pipeline (low-confidence extractions are quarantined for a human, never silently trusted), and in the copilot (safety-critical queries return an explicit refusal card instead of a plausible guess).

## How It Works

At its core Kairos is a pipeline: raw industrial artifacts go in one end, and governed, cited, point-of-action intelligence comes out the other. Between them sits a knowledge graph that remembers not just *what* is true but *when* it was true and *how sure* we are.

```mermaid
flowchart TB
    CLIENT["Point of action<br/>Next.js · field and desktop"]
    CORE["Application core<br/>FastAPI · OPA · Auth"]
    ORCH["Async orchestration<br/>Temporal · Celery · Go · Redis Streams"]
    SVC["Intelligence services<br/>Perception · Synthesis · Governance"]
    DATA[("Knowledge and data stores<br/>Neo4j · Qdrant · Elasticsearch · Supabase")]
    EXT["Model plane<br/>NVIDIA NIM · Groq · Jina"]
    HUM(["Human authority<br/>review · promote · sign off"])
    OBS["Observability<br/>OTEL to Grafana Cloud"]

    CLIENT -->|HTTPS| CORE
    CORE -->|ingest and events| ORCH
    CORE -->|query| SVC
    ORCH --> SVC
    SVC <-->|read and write| DATA
    SVC -->|inference| EXT
    SVC <-->|nothing becomes canonical without this| HUM
    CORE -.-> OBS
    ORCH -.-> OBS

    classDef edge fill:#fff1ea,stroke:#d93400,color:#5c1600
    classDef core fill:#f6f5f3,stroke:#0b1015,color:#0b1015
    classDef work fill:#f0ede8,stroke:#6b6259,color:#3a342d
    classDef think fill:#fdf4e6,stroke:#a66a00,color:#4a3000
    classDef store fill:#edf1f4,stroke:#3e5c6b,color:#1e2e36
    classDef ext fill:#f7f5f2,stroke:#9a9086,color:#4a443d,stroke-dasharray:4 3
    classDef human fill:#e9f2ec,stroke:#2f6b3e,color:#1b3f25
    class CLIENT edge
    class CORE core
    class ORCH work
    class SVC think
    class DATA store
    class EXT ext
    class HUM human
    class OBS ext
```

1. **Ingest & perceive.** Documents, events, and voice notes enter through one gate. OCR and NER lift entities (including equipment tags, process parameters, regulatory clauses, people, and dates) out of unstructured text; P&ID drawings are parsed into a connected topology. Files are stored byte-for-byte in an immutable, SHA-256-deduplicated vault.
2. **Link into the graph.** Extracted facts become **edges** in a temporal knowledge graph. Each edge carries six governance properties (validity window, authority level, source document, confidence, verification status) so the graph can answer *what was known on any past date* and show how a fact was later superseded.
3. **Govern.** Nothing unverified reaches an operator by accident. Contradictions surface as conflicts (administrative ones resolve in-app; engineering ones route through Management of Change); low-confidence extractions sit in a one-way quarantine that only a human can promote; an SPC circuit breaker halts ingestion for an asset class whose override rate spikes; a model gate blocks extraction models that fail a precision/recall bar.
4. **Retrieve & deliver.** The copilot answers questions with hybrid retrieval (graph + vector + exact) and mandatory citations, refusing outright on safety-critical parameters. Operational events assemble **proactive briefs** — governed by an EEMUA-191 push ceiling so operators are never flooded — and everything reaches the field on a mobile-first, offline-capable interface built from the same component set as the desktop workspace.

For the full design, including the 13-layer breakdown, knowledge-graph mechanics, OT virtualization, and the dual-track governance model, see **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)**.

## Key Capabilities

- **Universal document ingestion:** PDFs, engineering drawings, scanned/handwritten forms, and multi-script (Hindi / Hinglish) text flow through an OCR → NER → graph-linking → indexing pipeline into an immutable, deduplicated vault.
- **Temporal knowledge graph:** every fact is a time-bounded edge with authority, provenance, confidence, and verification status; query the past, watch knowledge get superseded, never lose history.
- **Expert copilot:** hybrid retrieval with citations, confidence scores, phase-gated synthesis, and explicit refusal on safety-critical queries, on mobile for technicians, not just desktops for engineers.
- **Proactive briefs:** events (work orders, PTWs, tag-outs, inspections, alarms) assemble contextual briefs, rate-limited by an EEMUA-191 governor and suppressed by plant state. Permit-to-Work briefs require **two distinct authenticated signatures** — the issuing engineer acknowledges, a second authority countersigns.
- **Maintenance & RCA intelligence:** fuses work-order history, failure records, OEM manuals, and inspection findings into root-cause timelines and hypotheses, with a blast-radius view of everything a change affects.
- **Governed accuracy:** dual-track conflict resolution, human-only quarantine promotion, Management-of-Change, SLA escalation, an SPC circuit breaker, and a per-asset-class model gate. Extracted P&ID topology stays *candidate* until an engineer confirms it element by element.
- **Compliance cockpit:** regulatory clauses (OISD, ISO 45001, Factory Act, PESO) mapped against current procedures, automatic gap detection, and human-signed audit-evidence packs.
- **Knowledge capture at the cliff:** micro-interviews and voice capture pull undocumented expertise out of departing experts before it walks out the door.

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (Python 3.12), Temporal (durable workflows), Celery (task queues), Go (Gin) OT connectors |
| **Datastores** | Neo4j Aura (graph, cloud), Qdrant Cloud (vector), Elasticsearch (exact), Redis (streams/cache), Supabase (Postgres · Auth · Storage · Vault) |
| **AI models** | NVIDIA NIM (LLM · NER · OCR), Groq Whisper (STT), Jina (embeddings). Cloud-only, no local weights. Synthesis runs on NIM Nemotron 3 Ultra 550B and falls back to OpenRouter (Llama 3.1 70B), then Gemini |
| **Frontend** | Next.js 16, React 19, Tailwind CSS v4, TypeScript (strict) |
| **Platform** | Docker Compose, OPA (authz), Supabase Vault (secrets), OpenTelemetry → Grafana Cloud (traces + metrics) |

## Quick Start

The entire stack runs inside Docker — no local Python, Node, or Go required.

**Prerequisites:** Docker Desktop · Make

```bash
# 1. Clone and configure
git clone https://github.com/kr7shnasomani/kairos.git
cd kairos
cp .env.example .env          # add cloud keys (NIM, Groq, Supabase) when ready

# 2. Boot the full platform
make dev

# 3. Initialize datastores and seed reference data (first run, or after `make nuke`)
make init-all
make seed                     # regulatory framework + demo users

# 4. Load the golden demo dataset (optional but recommended)
make load-dataset             # ingest the sample corpus through the real pipeline
# make load-dataset ARGS=--fast   # structured backbone + events only (fast)
```

Then open the frontend at **[http://localhost:3000](http://localhost:3000)**.

To reset to a clean, deterministic state at any time: `make nuke && make dev && make init-all && make seed && make load-dataset`.

> Supabase, Neo4j, Qdrant, and Grafana are **cloud** services (credentials in `.env`). The local Neo4j/Qdrant containers only run with `docker compose --profile local-stores up` (`:7474` / `:6333`). Secrets use Supabase Vault.

**Demo users** (seeded by `make seed`, sign in at `/login`):

| Email | Role | Sees |
|---|---|---|
| `admin@kairos.local` | admin | everything, incl. model gate / plant state / MDM |
| `engineer@kairos.local` | engineer | full desktop workspace |
| `reliability@kairos.local` | reliability | staff workspace **+ the one-way quarantine gate** — the only non-admin role that may promote unverified knowledge |
| `compliance@kairos.local` | compliance | read-only: compliance cockpit + audit trail |
| `field_worker@kairos.local` | field_worker | mobile-first field app (hamburger navigation) |

Passwords are not in the repository. Set one per role in your gitignored `.env`
(names in `.env.example`) before `make seed`, which refuses to run without them:
`KAIROS_SEED_PASSWORD_ADMIN`, `KAIROS_SEED_PASSWORD_ENGINEER`, `KAIROS_SEED_PASSWORD_FIELD_WORKER`,
`KAIROS_SEED_PASSWORD_RELIABILITY`, `KAIROS_SEED_PASSWORD_COMPLIANCE`. The personas are worth walking separately —
role-based governance is the point of the product, and it only *shows* when you log in as someone
who cannot do everything: an engineer resolves conflicts but is **refused** quarantine promotion,
while reliability is allowed.

## Repository Layout

Kairos is a monorepo: a Python backend, a Next.js frontend, a shared demo dataset, and the infrastructure to run it all locally.

```text
kairos/
├── backend/            # Python platform (FastAPI API, Temporal workflows, Celery + Go OT workers)
│   └── scripts/        # In-container Python: init · seed · backfill · verification (`python scripts/X.py`)
├── frontend/           # Next.js point-of-action web app (field mobile + desktop)
├── benchmark/          # Retrieval/answer-quality harness + deterministic grader (results in RESULTS.md)
├── dataset/            # Golden demo + benchmark corpus (docs · events · telemetry)
├── db/                 # Neo4j Cypher schema · consolidated Supabase schema · pending migrations · maintenance SQL
├── docs/               # Product & technical documentation (this folder)
├── fixtures/           # Backend mock-by-design data (P&ID topology fallback, test audio)
├── infra/              # Caddy (HTTPS) · OPA policies · Temporal config · Grafana Cloud
├── tests/              # Integration test suite (self-cleaning)
├── tools/              # Host-side dev tooling: authz-policy check · diagram + screenshot renderers
├── docker-compose.yml  # Full local infrastructure
├── Makefile            # Project lifecycle commands
├── AGENTS.md           # Contributor & AI-agent guardrails, conventions, pitfalls
└── README.md
```

Each major area has its own deep-dive in the docs folder.

## License

Proprietary — all rights reserved. Copyright (c) 2026 Krishna Somani. See [`LICENSE`](LICENSE); no use,
copying or redistribution is permitted without written permission from the copyright owner.
