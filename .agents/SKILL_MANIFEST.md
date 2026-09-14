# Kairos Agent Skills Manifest

All skills installed in `.agents/skills/`, grouped by domain for fast lookup.

## Table of Contents

- [Neo4j](#neo4j)
- [Qdrant](#qdrant)
- [Redis](#redis)
- [Elasticsearch](#elasticsearch)
- [Grafana & Observability](#grafana-observability)
- [FastAPI & Python Backend](#fastapi-python)
- [Go](#golang)
- [React & Next.js (Frontend)](#react-nextjs)
- [UI Design & Motion](#ui-design-motion)
- [Tailwind CSS](#tailwind)
- [Accessibility](#accessibility)
- [Performance & PWA](#performance-pwa)
- [Infrastructure & DevOps](#infrastructure-devops)
- [Supabase](#supabase)
- [AI / HuggingFace](#ai-huggingface)
- [Ponytail (Complexity Control)](#ponytail)
- [Utilities](#utilities)

---

## Neo4j {#neo4j}

### `neo4j-cypher-skill`
Generates, optimizes, and validates Cypher 25 queries for Neo4j 2025.x and 2026.x. Use when writing new Cypher queries, optimizing slow queries, graph pattern matching, vector or fulltext search, subqueries, or batch writes. Covers MATCH, MERGE, CREATE, WITH, RETURN, CALL, UNWIND, FOREACH, LOAD CSV, SEARCH, expressions, functions, indexes, and subqueries. Does NOT handle driver migration or API changes — use neo4j-migration-skill. Does NOT cover DB administration or server ops — use neo4j-cli-tools-skill.

**Path**: `.agents/skills/neo4j-cypher-skill/SKILL.md`

### `neo4j-driver-python-skill`
Neo4j Python Driver v6 — driver lifecycle, execute_query, managed and explicit transactions, async (AsyncGraphDatabase), result handling, data type mapping, error handling, UNWIND batching, connection pool tuning, and causal consistency. Use when writing Python code that connects to Neo4j via GraphDatabase.driver, execute_query, execute_read, execute_write, AsyncGraphDatabase, neo4j.Result, or RoutingControl. Package name is `neo4j` (not neo4j-driver) since v6. Python >=3.10 required. Does NOT handle Cypher query authoring — use neo4j-cypher-skill. Does NOT cover driver upgrades or breaking changes — use neo4j-migration-skill. Does NOT cover GraphRAG pipelines (neo4j-graphrag package) — use neo4j-graphrag-skill.

**Path**: `.agents/skills/neo4j-driver-python-skill/SKILL.md`

### `neo4j-driver-go-skill`
Covers the Neo4j Go Driver v6 — driver lifecycle, ExecuteQuery, managed and explicit transactions, session config, error handling, data type mapping, and connection tuning. Use when writing Go code that connects to Neo4j, setting up NewDriver or ExecuteQuery, debugging sessions/transactions/result handling, or working with neo4j-go-driver v5→v6 migration. Triggers on NewDriver, ExecuteQuery, SessionConfig, ManagedTransaction, neo4j-go-driver. Does NOT handle Cypher query authoring — use neo4j-cypher-skill. Does NOT cover driver version migration steps — use neo4j-migration-skill.

**Path**: `.agents/skills/neo4j-driver-go-skill/SKILL.md`

### `neo4j-graphrag-skill`
Build GraphRAG retrieval pipelines on Neo4j using the neo4j-graphrag Python package (v1.16.0+). Covers retriever selection (VectorRetriever, HybridRetriever, VectorCypherRetriever, HybridCypherRetriever, Text2CypherRetriever, ToolsRetriever), external vector DB retrievers (Weaviate, Pinecone, Qdrant), retrieval_query Cypher fragments, query_params, filters, GraphRAG pipeline wiring (GraphRAG + LLM + prompt), all LLM providers (OpenAI, Anthropic, VertexAI, Bedrock, Cohere, Mistral, Ollama), embedder setup, index creation, token usage tracking, Cypher 25 SEARCH clause, and LangChain/LlamaIndex integration. Does NOT handle KG construction — use neo4j-document-import-skill. Does NOT handle plain vector search — use neo4j-vector-index-skill. Does NOT handle GDS analytics — use neo4j-gds-skill. Does NOT handle agent memory — use neo4j-agent-memory-skill.

**Path**: `.agents/skills/neo4j-graphrag-skill/SKILL.md`

### `neo4j-document-import-skill`
Ingests unstructured and semi-structured documents into Neo4j as a knowledge graph. Use when chunking PDFs, HTML, plain text, or Markdown; extracting entities and relationships from text with an LLM (SimpleKGPipeline, neo4j-graphrag); loading JSON via apoc.load.json; building Document→Chunk→Entity graph structures; or connecting LangChain/LlamaIndex document loaders to Neo4j. Covers neo4j-graphrag SimpleKGPipeline, LLM Graph Builder web UI, entity resolution, chunking strategies, and graph schema design for RAG pipelines. Does NOT handle structured CSV/relational import — use neo4j-import-skill. Does NOT handle GraphRAG retrieval after ingestion — use neo4j-graphrag-skill. Does NOT handle vector index creation — use neo4j-vector-search-skill.

**Path**: `.agents/skills/neo4j-document-import-skill/SKILL.md`

### `neo4j-import-skill`
Import structured data into Neo4j — LOAD CSV, CALL IN TRANSACTIONS, neo4j-admin database import full (offline bulk), apoc.load.csv/json, apoc.periodic.iterate, driver batch writes. Covers method selection, header file format, type coercion, null handling, ON ERROR modes, CONCURRENT TRANSACTIONS, pre-import constraint setup, and post-import validation. Use when importing CSV/JSON/Parquet files, migrating relational data to graph, or bulk-loading large datasets. Does NOT handle unstructured document/PDF/vector chunking pipelines — use neo4j-document-import-skill. Does NOT handle live app write patterns (MERGE/CREATE) — use neo4j-cypher-skill. Does NOT handle neo4j-admin backup/restore/config — use neo4j-cli-tools-skill.

**Path**: `.agents/skills/neo4j-import-skill/SKILL.md`

### `neo4j-vector-index-skill`
Create and manage Neo4j vector indexes, run vector similarity search (ANN/kNN), store embeddings on nodes or relationships, use SEARCH clause (Neo4j 2026.01+, preferred) or db.index.vector.queryNodes() procedure (deprecated 2026.04, still works on 2025.x), configure HNSW and quantization options, pick similarity function and embedding provider dimensions, and batch-update embeddings. Use when tasks involve CREATE VECTOR INDEX, vector.dimensions, cosine/euclidean search, embedding ingestion pipelines, semantic or structural nearest-neighbor lookup, or hybrid search (vector + fulltext, multiple vector sources, or graph-derived scores). Does NOT handle GraphRAG retrieval_query graph traversal — use neo4j-graphrag-skill. Does NOT handle fulltext-only/keyword-only search — use neo4j-cypher-skill. Does NOT compute GDS graph embeddings (FastRP, Node2Vec) — use neo4j-gds-skill.

**Path**: `.agents/skills/neo4j-vector-index-skill/SKILL.md`

### `neo4j-genai-plugin-skill`
Use Neo4j GenAI Plugin ai.text.* functions and procedures for in-Cypher embedding generation, text completion, structured output, chat, tokenization, and batch ingestion. Covers ai.text.embed(), ai.text.embedBatch(), ai.text.completion(), ai.text.structuredCompletion(), ai.text.aggregateCompletion(), ai.text.chat(), ai.text.tokenCount(), ai.text.chunkByTokenLimit(), and provider configuration for OpenAI, Azure OpenAI, VertexAI, and Amazon Bedrock. Requires CYPHER 25. Replaces deprecated genai.vector.encode(). Use when writing pure-Cypher GraphRAG, embedding nodes in-graph, generating structured maps from prompts, or calling LLMs inside Cypher queries. Does NOT handle neo4j-graphrag Python library pipelines — use neo4j-graphrag-skill. Does NOT handle vector index creation/search — use neo4j-vector-index-skill.

**Path**: `.agents/skills/neo4j-genai-plugin-skill/SKILL.md`

### `neo4j-modeling-skill`
Design, review, and refactor Neo4j graph data models. Use when choosing node labels vs relationship types vs properties, migrating relational/document schemas to graph, detecting anti-patterns (generic labels, supernodes, missing constraints), designing intermediate nodes for n-ary relationships, enforcing schema with constraints and indexes, or assessing an existing model against graph modeling best practices. Does NOT handle Cypher query authoring — use neo4j-cypher-skill. Does NOT handle Spring Data Neo4j entity mapping — use neo4j-spring-data-skill. Does NOT handle GraphQL type definitions — use neo4j-graphql-skill. Does NOT handle data import — use neo4j-import-skill.

**Path**: `.agents/skills/neo4j-modeling-skill/SKILL.md`

### `neo4j-security-skill`
Programmatic security management in Neo4j — RBAC/ABAC, user lifecycle (CREATE/ALTER/DROP USER), role lifecycle (CREATE/GRANT ROLE/DROP ROLE), privilege grants and denies (GRANT/DENY/REVOKE on graph, database, DBMS), property-level access control, sub-graph access control, SHOW PRIVILEGES inspection, and auth provider config reference (LDAP, OIDC/SSO). Use when an agent needs to manage users, roles, or privileges programmatically via Cypher on the system database. Does NOT handle Cypher query writing — use neo4j-cypher-skill. Does NOT handle cluster ops or backups — use neo4j-cli-tools-skill. Property-level security and ABAC require Enterprise Edition.

**Path**: `.agents/skills/neo4j-security-skill/SKILL.md`

---

## Qdrant {#qdrant}

### `qdrant-clients-sdk`
Qdrant provides client SDKs for various programming languages, allowing easy integration with Qdrant deployments.

**Path**: `.agents/skills/qdrant-clients-sdk/SKILL.md`

### `qdrant-search-quality`
Diagnoses and improves Qdrant search relevance. Use when someone reports 'search results are bad', 'wrong results', 'low precision', 'low recall', 'irrelevant matches', 'missing expected results', or asks 'how to improve search quality?', 'which embedding model?', 'should I use hybrid search?', 'should I use reranking?', 'how to measure retrieval quality?', 'build a golden set', 'ground truth dataset', or 'how to score recall@k?'. Also use when search quality degrades after quantization, model change, or data growth.

**Path**: `.agents/skills/qdrant-search-quality/SKILL.md`

### `qdrant-performance-optimization`
Different techniques to optimize the performance of Qdrant, including indexing strategies, query optimization, and hardware considerations. Use when you want to improve the speed and efficiency of your Qdrant deployment.

**Path**: `.agents/skills/qdrant-performance-optimization/SKILL.md`

### `qdrant-scaling`
Guides Qdrant scaling decisions. Use when someone asks 'how many nodes do I need', 'data doesn't fit on one node', 'need more throughput', 'cluster is slow', 'too many tenants', 'vertical or horizontal', 'how to shard', or 'need to add capacity'.

**Path**: `.agents/skills/qdrant-scaling/SKILL.md`

### `qdrant-monitoring`
Guides Qdrant monitoring and observability setup. Use when someone asks 'how to monitor Qdrant', 'what metrics to track', 'is Qdrant healthy', 'optimizer stuck', 'why is memory growing', 'requests are slow', or needs to set up Prometheus, Grafana, or health checks. Also use when debugging production issues that require metric analysis.

**Path**: `.agents/skills/qdrant-monitoring/SKILL.md`

### `qdrant-model-migration`
Guides embedding model migration in Qdrant without downtime. Use when someone asks 'how to switch embedding models', 'how to migrate vectors', 'how to update to a new model', 'zero-downtime model change', 'how to re-embed my data', or 'can I use two models at once'. Also use when upgrading model dimensions, switching providers, or A/B testing models.

**Path**: `.agents/skills/qdrant-model-migration/SKILL.md`

### `qdrant-version-upgrade`
Guidance on how to upgrade your Qdrant version without interrupting the availability of your application and ensuring data integrity.

**Path**: `.agents/skills/qdrant-version-upgrade/SKILL.md`

---

## Redis {#redis}

### `redis-core`
Core Redis modeling guidance — choose the right data structure (String, Hash, List, Set, Sorted Set, JSON, Stream, Vector Set) and use consistent colon-separated key names. Use when designing a Redis data model, caching objects, deciding between Hash and JSON, building counters, leaderboards, membership sets, or session stores, or when reviewing/cleaning up Redis key naming.

**Path**: `.agents/skills/redis-core/SKILL.md`

### `redis-connections`
Redis client and connection guidance covering connection pooling, multiplexing, pipelining, client-side caching with RESP3, avoiding slow commands (KEYS, SMEMBERS, HGETALL), and tuning socket timeouts. Use when configuring a Redis client (redis-py, Jedis, Lettuce, NRedisStack), batching commands for throughput, eliminating per-request connection creation, iterating large keyspaces with SCAN, enabling client-side caching for read-heavy workloads, or setting connect and read timeouts.

**Path**: `.agents/skills/redis-connections/SKILL.md`

### `redis-security`
Redis security guidance covering authentication (requirepass and ACL users), TLS, ACL-based least-privilege access control, restricting network exposure via bind and protected-mode, firewall rules, and disabling dangerous commands. Use when deploying Redis to production, defining ACL users for an application, configuring TLS connections, locking down a Redis instance behind a firewall, or auditing a Redis deployment for security hardening.

**Path**: `.agents/skills/redis-security/SKILL.md`

### `redis-observability`
Redis observability guidance — which metrics to monitor (memory, connections, hit ratio, ops/sec, rejected connections), which built-in commands to reach for during incident triage (SLOWLOG, INFO, MEMORY DOCTOR, CLIENT LIST, FT.PROFILE), and when to use the Redis Insight GUI. Use when setting up monitoring or alerts for a Redis instance, diagnosing a performance regression, profiling a slow FT.SEARCH query, or wiring Redis metrics into Prometheus, Datadog, or similar.

**Path**: `.agents/skills/redis-observability/SKILL.md`

---

## Elasticsearch {#elasticsearch}

### `elasticsearch-onboarding`
Help developers new to Elasticsearch get from zero to a working search experience. Guide them through understanding their intent, mapping their data, and building a search experience with best practices baked in. Use this when the user shows intent to build search-related functionality, asks about Elasticsearch-related concepts for their use case, or expresses the need for help getting started with Elasticsearch.

**Path**: `.agents/skills/elasticsearch-onboarding/SKILL.md`

### `elasticsearch-esql`
Execute ES|QL (Elasticsearch Query Language) queries, use when the user wants to query Elasticsearch data, analyze logs, aggregate metrics, explore data, or create charts and dashboards from ES|QL results.

**Path**: `.agents/skills/elasticsearch-esql/SKILL.md`

### `elasticsearch-authz`
Manage Elasticsearch RBAC: native users, roles, role mappings, document- and field-level security. Use when creating users or roles, assigning privileges, or mapping external realms like LDAP/SAML.

**Path**: `.agents/skills/elasticsearch-authz/SKILL.md`

---

## Grafana & Observability {#grafana-observability}

### `grafana-oss`
Configure Grafana OSS — provisions dashboards from YAML, sets up data sources (Prometheus / Loki / Tempo / Pyroscope), writes dashboard JSON with template variables, builds panel queries, assigns built-in roles (Viewer / Editor / Admin / GrafanaAdmin), mints service-account tokens, edits grafana.ini server config, creates annotations, installs plugins via provisioning, and validates each step with a health-check curl. Use when building dashboards, configuring data sources, setting up provisioning YAML, picking a panel type, writing template variables, managing users and roles, configuring SMTP/OAuth in grafana.ini, creating annotations via API, troubleshooting why a provisioned dashboard isn't showing up, or running Grafana OSS locally — even when the user says "set up a Prometheus data source", "provision dashboards from git", "make a service account", or "configure SSO in OSS" without saying "Grafana OSS".

**Path**: `.agents/skills/grafana-oss/SKILL.md`

### `dashboarding`
Create, modify, and organise Grafana dashboards including panels, variables, transformations, and alerting. Use when the user asks to create a Grafana dashboard, add a panel, configure a time series or stat panel, add template variables, set up dashboard linking, use transformations, configure thresholds, build a dashboard for a service, or export dashboard JSON. Triggers on phrases like "create dashboard", "add panel", "time series panel", "Grafana dashboard JSON", "template variables", "dashboard variable", "panel transformation", "threshold", "stat panel", "table panel", "Grafana annotations", or "dashboard folder".

**Path**: `.agents/skills/dashboarding/SKILL.md`

### `alerting-irm`
Configure Grafana Alerting, Incident Response Management (IRM), and SLOs end-to-end — provisions Grafana-managed and data-source-managed alert rules, contact points (Slack/PagerDuty/email/webhook), notification policies with hierarchical matchers, silences, mute timings, on-call schedules and escalation chains, incident-management integrations, and SLOs with multi-window burn-rate alerts. Use when configuring alerts, debugging notification routing, setting up on-call rotations, declaring or managing incidents, defining SLOs, provisioning alerting via YAML or API, picking matchers for a notification policy, building a PagerDuty/Slack webhook receiver, or troubleshooting why an alert isn't firing — even when the user says "page me on errors", "alert me when X happens", "route this to the platform team", or "set up an SLO" without naming Alerting or IRM.

**Path**: `.agents/skills/alerting-irm/SKILL.md`

### `prometheus`
Prometheus and Grafana Cloud Metrics overview including PromQL query language, Metrics Drilldown, alerting, recording rules, and integration patterns. Use when working with Prometheus, writing PromQL queries, configuring alerting, or discussing metrics architecture and best practices.

**Path**: `.agents/skills/prometheus/SKILL.md`

### `promql`
Write, validate, and optimise PromQL queries for Prometheus and Grafana Cloud Metrics. Use when the user asks to query metrics, write a PromQL expression, calculate rates, aggregate across labels, build histogram quantiles, create recording rules, debug query performance, or understand metric cardinality. Triggers on phrases like "PromQL", "Prometheus query", "write a metric query", "calculate rate", "histogram_quantile", "recording rule", "metric cardinality", "sum by", "rate vs irate", "absent()", or "query is slow".

**Path**: `.agents/skills/promql/SKILL.md`

### `loki`
Grafana Loki log aggregation and LogQL query language. Covers LogQL syntax (log queries, metric queries, label matchers, line filters, parsers: json/logfmt/pattern/regexp/unpack, label filters, line_format), Loki architecture, log ingestion via Alloy/Promtail/Fluent Bit, structured metadata, and Logs Drilldown. Use when writing LogQL queries, configuring Loki, troubleshooting log pipelines, or analyzing logs.

**Path**: `.agents/skills/loki/SKILL.md`

### `tempo`
Grafana Tempo distributed tracing backend. Covers TraceQL query language (span selectors, attribute scopes, pipeline operators, structural operators, metrics functions), trace ingestion via OTLP/Jaeger/Zipkin, Tempo architecture (distributor/ingester/compactor/querier/metrics-generator), full configuration reference with YAML, metrics-from-traces (span metrics, service graphs, TraceQL metrics), deployment modes (monolithic/microservices/Helm/Kubernetes), multi-tenancy, performance tuning, caching, and HTTP API. Use when working with distributed traces, writing TraceQL queries, deploying Tempo, configuring trace pipelines, or setting up Grafana-Tempo integrations (traces-to-logs, traces-to-metrics, traces-to-profiles).

**Path**: `.agents/skills/tempo/SKILL.md`

### `opentelemetry`
OpenTelemetry with Grafana stack. Covers OTel SDK instrumentation for Go/Java/Python/Node.js/.NET, OTLP protocol and endpoint configuration, sending telemetry to Grafana Cloud via OTLP endpoint, Grafana Alloy as OTel collector, sampling strategies, Kubernetes OTel Operator, and migration from other observability tools. Use when instrumenting apps with OTel, configuring OTLP endpoints, setting up collectors, or migrating to OpenTelemetry.

**Path**: `.agents/skills/opentelemetry/SKILL.md`

### `observability-edot-python-instrument`
Instrument a Python application with the Elastic Distribution of OpenTelemetry (EDOT) Python agent for automatic tracing, metrics, and logs. Use when adding observability to a Python service that has no existing APM agent.

**Path**: `.agents/skills/observability-edot-python-instrument/SKILL.md`

### `observability-llm-obs`
Monitor LLMs and agentic apps: performance, token/cost, response quality, and workflow orchestration. Use when the user asks about LLM monitoring, GenAI observability, or AI cost/quality.

**Path**: `.agents/skills/observability-llm-obs/SKILL.md`

### `observability-logs-search`
Search and filter Observability logs using ES|QL. Use when investigating log spikes, errors, or anomalies; getting volume and trends; or drilling into services or containers during incidents.

**Path**: `.agents/skills/observability-logs-search/SKILL.md`

---

## FastAPI & Python Backend {#fastapi-python}

### `fastapi`
FastAPI best practices and conventions. Use when working with FastAPI APIs, Pydantic models, dependencies, streaming responses including Server-Sent Events (SSE), and serving frontend apps. Keeps FastAPI code clean and up to date with the latest features and patterns.

**Path**: `.agents/skills/fastapi/SKILL.md`

### `fastapi-templates`
Create production-ready FastAPI projects with async patterns, dependency injection, and comprehensive error handling. Use when building new FastAPI applications or setting up backend API projects.

**Path**: `.agents/skills/fastapi-templates/SKILL.md`

### `python-code-style`
Python code style, linting, formatting, naming conventions, and documentation standards. Use when writing new code, reviewing style, configuring linters, writing docstrings, or establishing project standards.

**Path**: `.agents/skills/python-code-style/SKILL.md`

### `python-design-patterns`
Python design patterns including KISS, Separation of Concerns, Single Responsibility, and composition over inheritance. Use this skill when designing a new service or component from scratch and choosing how to layer responsibilities, when refactoring a God class or monolithic function that has grown too large, when deciding whether to add a new abstraction or live with duplication, when evaluating a pull request for structural issues like tight coupling or leaking internal types, when choosing between inheritance and composition for a new class hierarchy, or when a codebase is becoming hard to test because of entangled I/O and business logic.

**Path**: `.agents/skills/python-design-patterns/SKILL.md`

### `python-performance-optimization`
Profile and optimize Python code using cProfile, memory profilers, and performance best practices. Use when debugging slow Python code, optimizing bottlenecks, or improving application performance.

**Path**: `.agents/skills/python-performance-optimization/SKILL.md`

### `python-testing-patterns`
Implement comprehensive testing strategies with pytest, fixtures, mocking, and test-driven development. Use when writing Python tests, setting up test suites, or implementing testing best practices.

**Path**: `.agents/skills/python-testing-patterns/SKILL.md`

---

## Go {#golang}

### `golang-code-style`
Golang code style conventions — line length and breaking, variable declarations, control flow clarity, when comments help vs hurt. Use when writing or reviewing Go code, asking about style or clarity, or establishing project coding standards. Not for naming conventions (→ See `samber/cc-skills-golang@golang-naming` skill), linter configuration (→ See `samber/cc-skills-golang@golang-lint` skill), or doc comments (→ See `samber/cc-skills-golang@golang-documentation` skill).

**Path**: `.agents/skills/golang-code-style/SKILL.md`

### `golang-error-handling`
Idiomatic Golang error handling — creation, wrapping with %w, errors.Is/As, errors.Join, custom error types, sentinel errors, panic/recover, the single handling rule, structured logging with slog, HTTP request logging middleware, and samber/oops for production errors. Built to make logs usable at scale with log aggregation 3rd-party tools. Apply when creating, wrapping, inspecting, or logging errors in Go code. For samber/oops specifics → See `samber/cc-skills-golang@golang-samber-oops` skill; for slog handler ecosystem → See `samber/cc-skills-golang@golang-samber-slog` skill.

**Path**: `.agents/skills/golang-error-handling/SKILL.md`

### `golang-performance`
Golang performance optimization patterns and methodology - if X bottleneck, then apply Y. Covers allocation reduction, CPU efficiency, memory layout, GC tuning, pooling, caching, and hot-path optimization. Use when profiling or benchmarks have identified a bottleneck and you need the right optimization pattern to fix it. Also use when performing performance code review to suggest improvements or benchmarks that could help identify quick performance gains. Not for measurement methodology (→ See `samber/cc-skills-golang@golang-benchmark` skill) or debugging workflow (→ See `samber/cc-skills-golang@golang-troubleshooting` skill).

**Path**: `.agents/skills/golang-performance/SKILL.md`

### `golang-testing`
Production-ready Golang tests — table-driven tests, testify suites and mocks, parallel tests, fuzzing, fixtures, goroutine leak detection with goleak, snapshot testing, code coverage, integration tests, idiomatic test naming. Use when writing or reviewing Go tests, choosing a testing approach, setting up Go test CI, or debugging flaky/slow tests. For testify-specific APIs see `samber/cc-skills-golang@golang-stretchr-testify`; for measurement methodology see `samber/cc-skills-golang@golang-benchmark`.

**Path**: `.agents/skills/golang-testing/SKILL.md`

---

## React & Next.js (Frontend) {#react-nextjs}

### `vercel-react-best-practices`
React and Next.js performance optimization guidelines from Vercel Engineering. This skill should be used when writing, reviewing, or refactoring React/Next.js code to ensure optimal performance patterns. Triggers on tasks involving React components, Next.js pages, data fetching, bundle optimization, or performance improvements.

**Path**: `.agents/skills/vercel-react-best-practices/SKILL.md`

### `vercel-composition-patterns`
React composition patterns that scale. Use when refactoring components with boolean prop proliferation, building flexible component libraries, or designing reusable APIs. Triggers on tasks involving compound components, render props, context providers, or component architecture. Includes React 19 API changes.

**Path**: `.agents/skills/vercel-composition-patterns/SKILL.md`

### `vercel-react-view-transitions`
Guide for implementing smooth, native-feeling animations using React's View Transition API (`<ViewTransition>` component, `addTransitionType`, and CSS view transition pseudo-elements). Use this skill whenever the user wants to add page transitions, animate route changes, create shared element animations, animate enter/exit of components, animate list reorder, implement directional (forward/back) navigation animations, or integrate view transitions in Next.js. Also use when the user mentions view transitions, `startViewTransition`, `ViewTransition`, transition types, or asks about animating between UI states in React without third-party animation libraries.

**Path**: `.agents/skills/vercel-react-view-transitions/SKILL.md`

### `typescript-react-reviewer`
Expert code reviewer for TypeScript + React 19 applications. Use when reviewing React code, identifying anti-patterns, evaluating state management, or assessing code maintainability. Triggers: code review requests, PR reviews, React architecture evaluation, identifying code smells, TypeScript type safety checks, useEffect abuse detection, state management review.

**Path**: `.agents/skills/typescript-react-reviewer/SKILL.md`

### `typescript-advanced-types`
Master TypeScript's advanced type system including generics, conditional types, mapped types, template literals, and utility types for building type-safe applications. Use when implementing complex type logic, creating reusable type utilities, or ensuring compile-time type safety in TypeScript projects.

**Path**: `.agents/skills/typescript-advanced-types/SKILL.md`

### `react-flow-code-review`
Reviews React Flow code for anti-patterns, performance issues, and best practices. Use when reviewing code that uses @xyflow/react, checking for common mistakes, or optimizing node-based UI implementations.

**Path**: `.agents/skills/react-flow-code-review/SKILL.md`

---

## UI Design & Motion {#ui-design-motion}

### `web-design-guidelines`
Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".

**Path**: `.agents/skills/web-design-guidelines/SKILL.md`

### `baseline-ui`
Quickly deslop UI code by fixing spacing, hierarchy, typography, and small layout issues. Use when the interface needs a fast cleanup or polish pass.

**Path**: `.agents/skills/baseline-ui/SKILL.md`

### `emil-design-eng`
This skill encodes Emil Kowalski's philosophy on UI polish, component design, animation decisions, and the invisible details that make software feel great.

**Path**: `.agents/skills/emil-design-eng/SKILL.md`

### `animation-vocabulary`
Reverse-lookup glossary that turns a vague description of a web animation or motion effect into its exact term ("the bouncy thing when a popover opens" → Pop in; "the iOS rubber-band scroll" → Rubber-banding). Use when the user asks "what's it called when…", or describes a motion effect without knowing its name and wants the right word to prompt an AI or designer with. For naming an effect, not designing or building one.

**Path**: `.agents/skills/animation-vocabulary/SKILL.md`

### `fixing-motion-performance`
Audit and fix animation performance issues including layout thrashing, compositor properties, scroll-linked motion, and blur effects. Use when animations stutter, transitions jank, or reviewing CSS/JS animation performance.

**Path**: `.agents/skills/fixing-motion-performance/SKILL.md`

### `review-animations`
Reviews animation and motion code against a high craft bar derived from Emil Kowalski's design engineering philosophy. Default to flagging; approval is earned.

**Path**: `.agents/skills/review-animations/SKILL.md`

---

## Tailwind CSS {#tailwind}

### `tailwind-4-docs`
Comprehensive Tailwind CSS v4 documentation snapshot and workflow guidance. Use when answering Tailwind v4 questions, selecting utilities/variants, configuring Tailwind v4, or migrating projects from v3 to v4 with official docs and gotcha checks.

**Path**: `.agents/skills/tailwind-4-docs/SKILL.md`

### `tailwind-design-system`
Build scalable design systems with Tailwind CSS v4, design tokens, component libraries, and responsive patterns. Use when creating component libraries, implementing design systems, or standardizing UI patterns.

**Path**: `.agents/skills/tailwind-design-system/SKILL.md`

---

## Accessibility {#accessibility}

### `accessibility`
Audit and improve web accessibility following WCAG 2.2 guidelines. Use when asked to "improve accessibility", "a11y audit", "WCAG compliance", "screen reader support", "keyboard navigation", or "make accessible".

**Path**: `.agents/skills/accessibility/SKILL.md`

### `accessibility-compliance`
Implement WCAG 2.2 compliant interfaces with mobile accessibility, inclusive design patterns, and assistive technology support. Use when auditing accessibility, implementing ARIA patterns, building for screen readers, or ensuring inclusive user experiences.

**Path**: `.agents/skills/accessibility-compliance/SKILL.md`

### `fixing-accessibility`
Audit and fix HTML accessibility issues including ARIA labels, keyboard navigation, focus management, color contrast, and form errors. Use when adding interactive controls, forms, dialogs, or reviewing WCAG compliance.

**Path**: `.agents/skills/fixing-accessibility/SKILL.md`

---

## Performance & PWA {#performance-pwa}

### `performance`
Optimize web performance for faster loading and better user experience. Use when asked to "speed up my site", "optimize performance", "reduce load time", "fix slow loading", "improve page speed", or "performance audit".

**Path**: `.agents/skills/performance/SKILL.md`

### `core-web-vitals`
Optimize Core Web Vitals (LCP, INP, CLS) for better page experience and search ranking. Use when asked to "improve Core Web Vitals", "fix LCP", "reduce CLS", "optimize INP", "page experience optimization", or "fix layout shifts".

**Path**: `.agents/skills/core-web-vitals/SKILL.md`

### `pwa-development`
Progressive Web Apps - service workers, caching strategies, offline, Workbox

**Path**: `.agents/skills/pwa-development/SKILL.md`

---

## Infrastructure & DevOps {#infrastructure-devops}

### `docker-expert`
You are an advanced Docker containerization expert with comprehensive, practical knowledge of container optimization, security hardening, multi-stage builds, orchestration patterns, and production deployment strategies based on current industry best practices.

**Path**: `.agents/skills/docker-expert/SKILL.md`

### `multi-stage-dockerfile`
Create optimized multi-stage Dockerfiles for any language or framework

**Path**: `.agents/skills/multi-stage-dockerfile/SKILL.md`

### `github-actions-templates`
Production-ready GitHub Actions workflow patterns for testing, building, and deploying applications.

**Path**: `.agents/skills/github-actions-templates/SKILL.md`

### `celery-expert`
Expert Celery distributed task queue engineer specializing in async task processing, workflow orchestration, broker configuration (Redis/RabbitMQ), Celery Beat scheduling, and production monitoring. Deep expertise in task patterns (chains, groups, chords), retries, rate limiting, Flower monitoring, and security best practices. Use when designing distributed task systems, implementing background job processing, building workflow orchestration, or optimizing task queue performance.

**Path**: `.agents/skills/celery-expert/SKILL.md`

### `temporal-developer`
Develop, debug, and manage Temporal applications across Python, TypeScript, Go, Java, .NET, Ruby, and Rust. Use when the user is building workflows, activities, or workers with a Temporal SDK, debugging issues like non-determinism errors, stuck workflows, or activity retries, using Temporal CLI, Temporal Server, or Temporal Cloud, or working with durable execution concepts like signals, queries, heartbeats, versioning, continue-as-new, child workflows, or saga patterns. Also use when the user mentions "run a Temporal workflow from the CLI", "start a dev server", "run temporal server start-dev", "temporal workflow start", "temporal workflow execute", "temporal workflow signal", "temporal workflow query", "temporal workflow update".

**Path**: `.agents/skills/temporal-developer/SKILL.md`

---

## Supabase {#supabase}

### `supabase`
Use when doing ANY task involving Supabase. Triggers: Supabase products (Database, Auth, Edge Functions, Realtime, Storage, Vectors, Cron, Queues); client libraries and SSR integrations (supabase-js, @supabase/ssr) in Next.js, React, SvelteKit, Astro, Remix; auth issues (login, logout, sessions, JWT, cookies, getSession, getUser, getClaims, RLS); Supabase CLI or MCP server; schema changes, migrations, security audits, Postgres extensions (pg_graphql, pg_cron, pg_vector).

**Path**: `.agents/skills/supabase/SKILL.md`

### `supabase-postgres-best-practices`
Postgres performance optimization and best practices from Supabase. Use this skill when writing, reviewing, or optimizing Postgres queries, schema designs, or database configurations.

**Path**: `.agents/skills/supabase-postgres-best-practices/SKILL.md`

---

## AI / HuggingFace {#ai-huggingface}

### `huggingface-best`
Use when the user asks about finding the best, top, or recommended model for a task, wants to know what AI model to use, or wants to compare models by benchmark scores. Triggers on: "best model for X", "what model should I use for", "top models for [task]", "which model runs on my laptop/machine/device", "recommend a model for", "what LLM should I use for", "compare models for", "what's state of the art for", or any question about choosing an AI model for a specific use case. Always use this skill when the user wants model recommendations or comparisons, even if they don't explicitly mention HuggingFace or benchmarks.

**Path**: `.agents/skills/huggingface-best/SKILL.md`

### `huggingface-local-models`
Use to select models to run locally with llama.cpp and GGUF on CPU, Mac Metal, CUDA, or ROCm. Covers finding GGUFs, quant selection, running servers, exact GGUF file lookup, conversion, and OpenAI-compatible local serving.

**Path**: `.agents/skills/huggingface-local-models/SKILL.md`

---

## Ponytail (Complexity Control) {#ponytail}

### `ponytail`
Forces the laziest solution that actually works, simplest, shortest, most minimal. Channels a senior dev who has seen everything: question whether the task needs to exist at all (YAGNI), reach for the standard library before custom code, native platform features before dependencies, one line before fifty. Supports intensity levels: lite, full (default), ultra. Use whenever the user says "ponytail", "be lazy", "lazy mode", "simplest solution", "minimal solution", "yagni", "do less", or "shortest path", and whenever they complain about over-engineering, bloat, boilerplate, or unnecessary dependencies.

**Path**: `.agents/skills/ponytail/SKILL.md`

### `ponytail-audit`
Whole-repo audit for over-engineering. Like ponytail-review, but scans the entire codebase instead of a diff: a ranked list of what to delete, simplify, or replace with stdlib/native equivalents. Use when the user says "audit this codebase", "audit for over-engineering", "what can I delete from this repo", "find bloat", "ponytail-audit", or "/ponytail-audit". One-shot report, does not apply fixes.

**Path**: `.agents/skills/ponytail-audit/SKILL.md`

### `ponytail-debt`
Harvest every `ponytail:` comment in the codebase into a debt ledger, so the deliberate shortcuts and deferrals ponytail leaves behind get tracked instead of rotting into "later means never". Use when the user says "ponytail debt", "/ponytail-debt", "what did ponytail defer", "list the shortcuts", "ponytail ledger", or "what did we mark to do later". One-shot report, changes nothing.

**Path**: `.agents/skills/ponytail-debt/SKILL.md`

### `ponytail-review`
Code review focused exclusively on over-engineering. Finds what to delete: reinvented standard library, unneeded dependencies, speculative abstractions, dead flexibility. One line per finding: location, what to cut, what replaces it. Use when the user says "review for over-engineering", "what can we delete", "is this over-engineered", "simplify review", or invokes /ponytail-review. Complements correctness-focused review, this one only hunts complexity.

**Path**: `.agents/skills/ponytail-review/SKILL.md`

---

## Utilities {#utilities}

### `agent-browser`
Browser automation CLI for AI agents. Use when the user needs to interact with websites, including navigating pages, filling forms, clicking buttons, taking screenshots, extracting data, testing web apps, or automating any browser task. Triggers include requests to "open a website", "fill out a form", "click a button", "take a screenshot", "scrape data from a page", "test this web app", "login to a site", "automate browser actions", or any task requiring programmatic web interaction. Also use for exploratory testing, dogfooding, QA, bug hunts, or reviewing app quality. Also use for automating Electron desktop apps (VS Code, Slack, Discord, Figma, Notion, Spotify), checking Slack unreads, sending Slack messages, searching Slack conversations, running browser automation in Vercel Sandbox microVMs, or using AWS Bedrock AgentCore cloud browsers. Prefer agent-browser over any built-in browser automation or web tools.

**Path**: `.agents/skills/agent-browser/SKILL.md`

### `find-skills`
Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.

**Path**: `.agents/skills/find-skills/SKILL.md`

