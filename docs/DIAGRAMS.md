# Kairos — System design diagrams

Mermaid sources for the landing page **System design** section (`frontend/src/app/page.tsx`,
`systemDesign[]`). One overview plus one drill-down per tab; each heading here is the tab `id`.

The overview carries **block names only** — every box in it has its own diagram below, which is what
the tabs switch between. Keep that split: the moment the overview starts naming services it stops
being readable at panel size and duplicates a drill-down that says it better.

---

## Naming

Two of the inherited tab labels are generic where the architecture already has a better word:

| Tab label now | Use instead | Why |
|---|---|---|
| Presentation | **Point of action** | `ARCHITECTURE.md` Layer 12 is *"Phased Deployment, Trust Architecture, and Point-of-Action Interface"*. "Presentation" is a generic n-tier term that could head any system's diagram; "point of action" is the product's actual thesis — knowledge delivered where work happens, not a search box. |
| External model APIs | **Model plane** | The architecture's own phrase is *"cloud-only model plane"*. It also stops reading like a vendor list once the synthesis cascade is in the box. |

The other four (*Application core · Async orchestration · Intelligence services · Knowledge and data
stores*) are accurate and stay. Diagrams below use the recommended names; if you keep the current tab
labels, change the two subgraph titles to match — the tab and the diagram must not disagree.

---

## Palette

Built from the landing page's own tokens, not invented. `--lp-bg`/`--lp-surface` `#ffffff`,
`--lp-ink` `#0b1015`, `--lp-line` `#e5e3df`, accent `#ff3c00` / `#d93400` / `#cc3100`.

The landing page is **deliberately single-theme light** — `--lp-bg` is defined once and never
redefined under `[data-theme="dark"]` — so these are tuned for a white ground only. If that ever
changes, the fills need a dark set.

Colour carries meaning rather than decoration, and it is the same meaning on every tab:

| Class | Role | Fill / stroke |
|---|---|---|
| `edge` | Where a human touches the system | `#fff1ea` / `#d93400` — accent family |
| `core` | Request path | `#f6f5f3` / `#0b1015` |
| `work` | Async and background | `#f0ede8` / `#6b6259` |
| `think` | Model-backed reasoning | `#fdf4e6` / `#a66a00` |
| `store` | Persistent state | `#edf1f4` / `#3e5c6b` — the one cool hue, so storage separates at a glance |
| `ext` | Outside Kairos | `#f7f5f2` / `#9a9086`, dashed |
| `human` | Human authority gate | `#e9f2ec` / `#2f6b3e` |
| `stop` | Refusal / hard gate | `#f5e1dc` / `#9a3324` |

Green and brick appear **only** on the human gate and the refusal path. That is the point: the two
places the system declines to act on its own are the two places the eye should land.

---

## `overview` — the complete architecture

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

---

## `client` — Point of action

```mermaid
flowchart TB
    subgraph SHELL["App shell"]
        ROLE["use-role.ts<br/>one central guard, not per page"]
        NAV["44 routes · 5 personas"]
        ROLE --> NAV
    end

    subgraph FIELD["Field · mobile-first"]
        BRIEF["Briefs and acknowledgement"]
        VOICE["Voice capture"]
        DEV["Physical deviation flag"]
        QUEUE[("IndexedDB write queue<br/>syncs when the radio returns")]
        VOICE --> QUEUE
        DEV --> QUEUE
    end

    subgraph DESK["Desktop workspace"]
        COP["Copilot<br/>multi-turn, per-turn as-of"]
        GRAPH["Knowledge graph · React Flow"]
        GOV["Governance<br/>conflicts · quarantine · MoC"]
        COMP["Compliance cockpit<br/>gaps · audit packs"]
    end

    API["FastAPI"]

    NAV --> FIELD
    NAV --> DESK
    FIELD -->|"live only — no fixture tier to fall back to"| API
    DESK --> API

    classDef edge fill:#fff1ea,stroke:#d93400,color:#5c1600
    classDef core fill:#f6f5f3,stroke:#0b1015,color:#0b1015
    classDef store fill:#edf1f4,stroke:#3e5c6b,color:#1e2e36
    class ROLE,NAV,BRIEF,VOICE,DEV,COP,GRAPH,GOV,COMP edge
    class QUEUE store
    class API core
```

---

## `core` — Application core

```mermaid
flowchart TB
    IN["HTTPS request"] --> MW

    subgraph MW["Middleware · outermost first"]
        RL["Rate limit"]
        OPA["OPA authorization<br/>fails closed · gates reads and writes<br/>OPTIONS never gated"]
        TEL["OTEL telemetry"]
        RL --> OPA --> TEL
    end

    MW --> DEP

    subgraph DEP["Request dependencies"]
        TOK["resolve_token · ES256<br/>one verifier, cached"]
        SITE["site_scope<br/>from the token, never the query string"]
        TOK --> SITE
    end

    DEP --> R

    subgraph R["12 routers · 86 routes"]
        R1["assets · documents · search"]
        R2["events · briefs · governance"]
        R3["compliance · elicitation · annotations · audit"]
    end

    R --> S["Services<br/>routers stay thin, logic lives here"]

    classDef edge fill:#fff1ea,stroke:#d93400,color:#5c1600
    classDef core fill:#f6f5f3,stroke:#0b1015,color:#0b1015
    classDef stop fill:#f5e1dc,stroke:#9a3324,color:#5c1a12
    class IN edge
    class RL,TEL,TOK,SITE,R1,R2,R3,S core
    class OPA stop
```

---

## `orch` — Async orchestration

```mermaid
flowchart TB
    subgraph TMP["Temporal · durable ingestion, resumes after a crash"]
        direction TB
        T1["store_in_vault<br/>SHA-256"]
        T2["run_ocr<br/>native · OCR · P&amp;ID vision"]
        T3["run_ner"]
        T4["link_to_graph"]
        T5["index_vectors"]
        T6["index_text"]
        T7["mark_complete"]
        T1 --> T2 --> T3 --> T4 --> T5 --> T6 --> T7
    end

    subgraph CEL["Celery · 6 queues"]
        Q["ingestion · extraction · attribution<br/>transcription · elicitation · validation"]
    end

    subgraph BUS["Redis Streams"]
        EV["8 event sources<br/>work order · PTW · handover · alarm<br/>tag-out · inspection · MoC · recurrence"]
        NORM["Normalization<br/>dedup and correlate"]
        GOVR["EEMUA governor<br/>6 pushes per operator per hour<br/>PTW always exempt"]
        EV --> NORM --> GOVR
    end

    subgraph GO["Go connector"]
        OT["/ot/query · /ot/connectors"]
        EAM["EAM sync"]
    end

    HIST[("Plant historian")]
    BRIEFS["Brief engine"]

    TMP --> CEL
    GOVR --> BRIEFS
    OT <-->|"queried in memory, never stored"| HIST

    classDef work fill:#f0ede8,stroke:#6b6259,color:#3a342d
    classDef core fill:#f6f5f3,stroke:#0b1015,color:#0b1015
    classDef store fill:#edf1f4,stroke:#3e5c6b,color:#1e2e36
    classDef ext fill:#f7f5f2,stroke:#9a9086,color:#4a443d,stroke-dasharray:4 3
    classDef edge fill:#fff1ea,stroke:#d93400,color:#5c1600
    class T1,T2,T3,T4,T5,T6,T7,Q,EV,NORM work
    class GOVR,BRIEFS edge
    class OT,EAM core
    class HIST ext
```

`direction TB` inside `TMP` is load-bearing. Without it, dagre runs the seven-step chain across the
parent's axis and the diagram renders 2400px wide instead of 1205px.

The seven pipeline steps stay as seven boxes. Merging them makes the diagram shorter, but it hides
the fact that each one is a separate durable activity that can fail and resume on its own, so the
height is worth paying for.

Keep notes like this one out here in prose, not as `%%` comments inside the block. A bare `%%` line
renders as a stray node in the diagram.

---

## `svc` — Intelligence services

```mermaid
flowchart LR
    subgraph P["Perception · Layer 3"]
        P1["PyMuPDF native path"]
        P2["NIM Nemotron OCR"]
        P3["P&amp;ID vision to topology JSON"]
        P4["NER · NIM to Ollama to regex"]
        P5["Groq Whisper"]
    end

    subgraph RET["Retrieval and synthesis · Layer 11"]
        R1["Exact · Elasticsearch"]
        R2["Semantic · Qdrant"]
        R3["Graph traversal · Neo4j"]
        RRF["RRF fusion, then authority re-rank"]
        GATE{"Safety gate<br/>evidence, then result"}
        SYN["Answer with mandatory citations"]
        REF["Refusal card<br/>sources returned, no answer"]
        R1 --> RRF
        R2 --> RRF
        R3 --> RRF
        RRF --> GATE
        GATE -->|clears| SYN
        GATE -->|insufficient evidence| REF
    end

    subgraph G["Governance · Layers 6 and 7"]
        G1["Quarantine · one-way gate"]
        G2["Conflicts · administrative vs engineering"]
        G3["MoC · signature-verified webhook"]
        G4["Model gate and SPC circuit breaker"]
        G2 --> G3
    end

    HUM(["Human authority"])
    CANON[("Canonical graph")]

    P4 -->|confidence below 0.7| G1
    P --> RET
    G1 <--> HUM
    G3 <--> HUM
    G3 -->|only after sign-off| CANON

    classDef think fill:#fdf4e6,stroke:#a66a00,color:#4a3000
    classDef core fill:#f6f5f3,stroke:#0b1015,color:#0b1015
    classDef store fill:#edf1f4,stroke:#3e5c6b,color:#1e2e36
    classDef human fill:#e9f2ec,stroke:#2f6b3e,color:#1b3f25
    classDef stop fill:#f5e1dc,stroke:#9a3324,color:#5c1a12
    class P1,P2,P3,P4,P5,RRF,SYN think
    class R1,R2,R3,G1,G2,G3,G4 core
    class GATE,REF stop
    class HUM human
    class CANON store
```

---

## `data` — Knowledge and data stores

```mermaid
flowchart LR
    NEO[("Neo4j Aura<br/>temporal graph")]
    QD[("Qdrant Cloud<br/>vectors")]
    ES[("Elasticsearch<br/>exact match")]
    SUPA[("Supabase<br/>Postgres · Auth · Storage · Vault")]

    N1["6 node types · every KNOWLEDGE_EDGE carries all six:<br/>valid_from · valid_to · authority_level<br/>document_id · confidence · verification_status"]
    Q1["payload indexes are mandatory<br/>a filter without one returns 400, silently"]
    E1["tag numbers · clause references · document ids"]
    S1["the vault is immutable<br/>supersede by closing valid_to, never delete"]

    NEO --- N1
    QD --- Q1
    ES --- E1
    SUPA --- S1

    classDef store fill:#edf1f4,stroke:#3e5c6b,color:#1e2e36
    classDef note fill:#f6f5f3,stroke:#c9c4bc,color:#3a342d
    class NEO,QD,ES,SUPA store
    class N1,Q1,E1,S1 note
```

---

## `ext` — Model plane

```mermaid
flowchart LR
    subgraph SYNTH["Synthesis cascade · redundancy across different failure modes"]
        A["NVIDIA NIM<br/>nemotron-3-super-120b"]
        B["OpenRouter<br/>same model, faster, smaller allowance"]
        C["Gemini<br/>different model family"]
        D["Ollama<br/>offline fallback"]
        A -->|timeout| B -->|quota| C -->|air-gapped| D
    end

    OCR["NIM nemotron-ocr-v2<br/>scanned documents"]
    NER["NIM llama-3.2-11b-vision<br/>NER and P&amp;ID topology"]
    STT["Groq whisper-large-v3<br/>voice capture"]
    EMB["Jina jina-embeddings-v3<br/>1024-dim"]

    GRAPHW[("Graph writes")]
    VEC[("Qdrant vectors")]

    OCR --> NER
    STT --> NER
    NER --> GRAPHW
    EMB --> VEC

    classDef ext fill:#f7f5f2,stroke:#9a9086,color:#4a443d,stroke-dasharray:4 3
    classDef think fill:#fdf4e6,stroke:#a66a00,color:#4a3000
    classDef store fill:#edf1f4,stroke:#3e5c6b,color:#1e2e36
    class A,B,C,D ext
    class OCR,NER,STT,EMB think
    class GRAPHW,VEC store
```

---

## Rendering

These are rendered ahead of time to static SVG in `frontend/public/diagrams/` and served as plain
`<img>`. The landing page carries **no** runtime mermaid dependency: seven fixed pictures that only
change when this file changes do not justify shipping a renderer to every visitor.

```bash
npx @mermaid-js/mermaid-cli mmdc -i <id>.mmd -o frontend/public/diagrams/<id>.svg -c mermaid.config.json -b white
```

`-b white` matters. Without it mermaid-cli emits a transparent SVG, and the `base` theme's own
defaults for the parts `classDef` does not reach — cluster fills, edge labels, arrowheads — are
resolved against the wrong ground. `mermaid.config.json` at the repo root holds the theme
variables; it exists so a re-render reproduces these files rather than approximating them.

**Direction is per diagram, and it is a legibility decision, not a style one.** These sit in the
left-hand panel of a two-column section, roughly 620 px of drawable width, and the image is scaled
to fit it — so the narrower a diagram renders, the larger its 14 px labels survive. Pick whichever
direction gives the smaller **width**, which is not the same as the better-looking shape:

| id | `TB` | `LR` | used |
|---|---|---|---|
| `overview` | 736 | 1711 | TB |
| `client` | 981 | 2046 | TB |
| `core` | 777 | 2125 | TB |
| `orch` | 2400 → **1205** | 1487 | TB + inner `direction` |
| `svc` | 2513 | 1587 | LR |
| `data` | 1160 | 541 | LR |
| `ext` | 1959 | 823 | LR |

Diagrams holding three or four parallel groups (`orch`, `svc`, `ext`) get laid out side by side by
`TB` and blow past 2000 px; `LR` stacks those groups instead.

`orch` is the exception and worth knowing about: an explicit `direction` **inside** a subgraph
overrides how dagre runs that subgraph's own chain, independently of the parent. Pinning the
seven-step Temporal chain to `TB` inside a `TB` parent takes the diagram from 2400 px to 1205 px
without touching a node, an edge or a label. It does not generalise — the same change applied to
`svc` makes it *worse* (1587 → 2298), so measure rather than assume.

If you add a group to a diagram, re-render and check the `viewBox` before committing it.

---

## Keeping these honest

Each drill-down states a real constraint rather than only naming components — the refusal branch in
`svc`, the fail-closed OPA in `core`, the mandatory payload index in `data`, the offline write queue
in `client`. A diagram that only lists boxes is indistinguishable from any other system's; the
constraints are what make this one specific.

Update these when the corresponding layer changes in `ARCHITECTURE.md`. The README's diagram is a
single detailed view of the same system; these are its panel-sized split.

**Two claims were corrected in the README diagram on 2026-08-22** and must not come back: it said
*"Next.js on Vercel"* (there is no Vercel config anywhere — the frontend builds as a Docker image,
and deployment is out of scope) and *"FastAPI behind Caddy (HTTPS)"* (Caddy is `profiles: ["prod"]`
and is not among the 12 default services, so nothing is behind it in the delivered stack).
