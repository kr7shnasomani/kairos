# Kairos: Industrial Operational Intelligence Platform
### The Definitive Solution to Industrial Knowledge Fragmentation

---

## 1. Solution Name and Core Innovation

**Kairos** — the first industrial knowledge platform built around operational context awareness rather than query response: a system that continuously monitors the operational pulse of any asset-intensive facility, interprets it against a governed temporal knowledge graph, and delivers the right knowledge to the right person at the precise moment it is needed, without being asked.

Kairos is sector-agnostic by design. The architecture applies identically to oil and gas, power generation, pharmaceuticals, steel, mining, food and beverage, semiconductors, defence manufacturing, water utilities, or any other industry where complex assets generate heterogeneous documents and operational decisions carry real safety and financial consequences. The regulatory standards, drawing types, and document vocabularies differ by sector; the underlying platform does not.

---

## 2. The Fundamental Insight

Every solution that has attempted this problem — document management systems, enterprise search, RAG pipelines, knowledge graphs, predictive maintenance platforms — shares a single architectural assumption that makes them all structurally incapable of solving it.

They treat knowledge as something that must be retrieved.

The mental model is identical across all of them: knowledge exists somewhere, a person has a need, the person formulates a query, the system returns results. Making retrieval faster, smarter, and more semantically aware is the optimization axis every prior solution has competed on. The best of them are exceptional retrieval systems.

But retrieval cannot solve the actual problem. The most dangerous knowledge gaps in industrial operations are the ones nobody knows to query. The maintenance technician who doesn't know that this specific pump has failed under this exact thermal cycling condition before doesn't know to search for pump failure history. The planner who doesn't know that a regulatory amendment last month changed the inspection interval for this vessel class doesn't know to search for regulatory amendments. The shift lead who doesn't know that a near-identical sequence of events preceded a major incident at a sister facility doesn't know to search for sister facility incident reports. These are not retrieval failures. They are awareness failures. And no search engine, however sophisticated, can solve an awareness failure.

Kairos is built on the inversion of this assumption. The platform's primary job is not to answer questions. It is to ensure that critical knowledge reaches the people who need it before they know they need it. It does this by treating operational events — work order creation, permit-to-work issuance, shift handover, alarm acknowledgment, equipment tag-out, inspection completion — as triggers, not as user actions. The system interprets each event against the complete governed knowledge of the organization, identifies what the person about to do that work needs to know that they almost certainly don't know, and delivers it proactively. The unit of value is not a search result. It is a contextually relevant operational briefing, delivered at the kairos moment: the moment when action is most appropriate and knowledge is most needed.

The knowledge governance architecture — the immutable vault, the temporal graph, the authority hierarchy, the MoC integration, the quarantine layer — exists to ensure that what the system proactively delivers is accurate, provenance-backed, and trustworthy enough to act on in safety-critical conditions. Without proactive delivery, you have a better SharePoint. Without governed accuracy, you have a confident hallucination machine. Kairos requires both, which is why it is structured the way it is.

---

## 3. Complete System Architecture

Kairos is organized into thirteen layers. Each layer has a single, clearly bounded responsibility. No layer performs work that belongs to another layer.

---

### Layer 0: Empirical Validation and Model Safety Plane

**Purpose:** Ensure that every model update, extraction configuration change, or ontology revision improves rather than degrades system accuracy before it reaches production.

This layer runs a continuous benchmarking environment against a rolling validation corpus. The corpus is built dynamically from real operational data that has passed through the full human promotion workflow and been verified as canonical truth. Every document, every extracted fact, and every entity relationship that has been verified by human authority becomes part of the empirical baseline. The corpus grows with the deployment, and a static curated dataset alone would become obsolete as the site's equipment profile and document vocabulary evolve.

A curated corpus is still required to seed it. On day zero there is no stream of human-verified production facts to grow a rolling baseline from, so the deployment starts against a canonical dataset with declared ground truth (`dataset/`, canon in `00_KAIROS_CANON.md`) — which is also what makes deterministic grading possible, since a labelled answer key is the only way to score extraction and retrieval without an LLM judging its own output. The two mechanisms coexist: the canonical dataset is the fixed floor that regression-tests every change, and `validation_corpus` accumulates verified production facts alongside it as the deployment matures. The rolling corpus is what keeps validation relevant over time; it is not a replacement for the seed.

Before any model update (OCR model, LLM, extraction classifier, entity linker) is promoted to production, it must achieve equal or higher precision and recall on the rolling corpus compared to the incumbent. The gate is automated, and it evaluates per asset class as well as globally: a model that passes on global metrics but regresses on a specific asset class (e.g., rotating equipment) is identified for that class rather than being averaged into a passing score. Entity extraction is the gated artifact today; OCR, synthesis, and entity linking are the extension path along the same interface.

**The gate ships observing, not enforcing.** `MODEL_GATE_ENFORCE` defaults off: regressions are computed, recorded, and published in `blocked_asset_classes`, but they do not block promotion. This is deliberate and it is a function of corpus maturity, not of confidence in the mechanism. A hard gate over a thin corpus blocks legitimate model updates on sampling noise — the gate becomes the outage. Enforcement is a single flag, and the consumer is already wired: the Layer 7 circuit breaker reads `blocked_asset_classes` and halts graph writes for a blocked class. The gate is enabled when the corpus is large enough that a per-class regression means a real regression, which is a deployment decision rather than a code change. The same posture governs `TIMESTAMP_DRIFT_ENFORCE` and the Layer 12 phase flag: build the control, ship it reporting, promote it to enforcing on evidence.

This layer also captures the system's own track record: which answers led to which actions, which recommendations were overridden by human authority, which proactive briefs were marked as not relevant. This meta-data feeds the outcome attribution system in Layer 10.

---

### Layer 1: Deterministic Identity and MDM Backbone

**Purpose:** Establish the canonical asset identity skeleton that every subsequent layer builds on. No AI is permitted to invent, infer, or hallucinate primary asset identities.

Kairos begins every deployment by ingesting the enterprise golden record from the primary ERP/EAM system — SAP PM, IBM Maximo, Infor EAM, or equivalent. This creates a deterministic node for every registered asset in the plant: canonical asset ID, parent-child hierarchy, site and facility mapping, equipment class, criticality classification, tag number, and all known alias variants.

Where the golden record is incomplete — orphaned tag numbers, undocumented equipment, historical assets without EAM entries — the system does not speculate. It enters a human bootstrap workflow that requires a qualified asset authority to confirm identity before that asset can be linked to any extracted knowledge. AI-assisted linking is allowed only after human confirmation.

The MDM backbone is the skeleton. Everything else is flesh built onto this skeleton. A piece of extracted knowledge that cannot be linked to a confirmed asset identity goes to the quarantine layer under a provisional holding node, not into the canonical graph.

Tag alias resolution is a first-class function. Industrial facilities accumulate naming inconsistencies over decades: the same pump may be "P-101," "Pump 101," "Feed Pump A," "P101," and "the old Fischer" in five different documents. The alias resolver maintains a continuously updated map of how every known reference maps to a canonical asset ID, learned from the extraction process and confirmed by human review.

An alternative integration option for facilities where periodic EAM bulk import creates unacceptable staleness: a federated live-query layer (using zero-ETL graph query engines such as PuppyGraph) that queries a replicated operational data store rather than importing a scheduled snapshot. This approach keeps the MDM backbone current as EAM records are updated. One hard constraint that applies universally: this federated query layer must never target the production SAP ECC or S4/HANA transactional database directly. No enterprise IT or SAP Basis team will permit external ad-hoc queries against a production ERP — the unpredictable compute overhead and risk of transactional locking make it a standard security and operations veto. The correct target is a replicated downstream store: an SAP Landscape Transformation (SLT) replication server, an Operational Data Store synchronized via SAP CDS views, or an enterprise data lake fed by EAM change events. The freshness lag of these targets (typically minutes to hours) is operationally acceptable for MDM bootstrap purposes. This is not a replacement for the temporal reality graph; it is an integration option specifically for the MDM data plane where EAM data currency is operationally critical.

---

### Layer 2: Immutable Evidence Vault

**Purpose:** Preserve every source artifact exactly as received, forever, with complete provenance and access control. This is the ground truth that every subsequent layer derives from.

Every document that enters Kairos — PDFs, scanned drawings, maintenance work orders, inspection reports, operating procedures, OEM manuals, email archives, voice transcripts, shift logs, regulatory submissions — is stored in the vault unchanged. No preprocessing, no reformatting, no cleanup before storage. The vault stores the artifact in its original state.

On ingestion, each artifact receives: a SHA-256 cryptographic hash (integrity verification), an ingestion timestamp (immutable), a source system provenance tag, access control tags, a version chain pointer (linking to superseded versions of the same document), and a status: active, superseded, archived, or disputed.

Access control tags are assigned from Kairos's own identity plane — the role and the site scope carried on the verified token, never a value supplied by the request. Inheriting per-document permissions from each source system's IAM configuration is the richer model and is deferred: it requires a permission-mapping integration against every one of the 7–12 source systems a plant operates, and a stale or partial mapping fails open on documents it does not understand. A single authorization model that every artifact is evaluated against is the safer default, and site scope is the hard boundary — a blank site resolves to no rows, not all rows. Source-system permission inheritance becomes worthwhile at the point where a specific source system's access model is materially finer-grained than the role hierarchy, and it is added per connector rather than as a global mechanism.

The vault never overwrites. When a document is revised, the new version enters as a new artifact with a pointer to the previous version. The previous version's status is updated to "superseded" but the artifact itself is never deleted. This is non-negotiable for audit, legal defensibility, and RCA time-travel capabilities.

The vault is the foundation of trust. When Kairos produces an answer citing a source, that source is a direct pointer to a specific artifact in the vault, retrievable by any authorized party, at the exact byte-level fidelity of the original document. The answer is not derived from a processed copy. It is derived from an extraction whose lineage can be traced to an immutable original.

---

### Layer 3: Multimodal Perception Engine

**Purpose:** Extract structured, linkable knowledge from heterogeneous industrial documents in their actual state, not their ideal state. This engine must handle reality: poor scans, handwritten annotations, multi-script text, mixed languages, and complex technical drawings.

The perception engine operates as a pipeline of specialized models, not a single generalist model. Specialization is necessary because industrial document types are sufficiently different from each other that a generalist model optimized for one degrades significantly on another.

**Text extraction:** Two-path approach. Native digital PDFs are parsed directly via PyMuPDF — fast, zero API cost, preserves text fidelity. Scanned documents and images go to NVIDIA NIM Nemotron-OCR-v2 via the NIM cloud API, which handles mixed-script and multilingual documents. This cloud-first design eliminates local model dependencies and heavy infrastructure while maintaining strong accuracy on the document types Kairos ingests.

**Named entity recognition:** NVIDIA NIM `meta/llama-3.2-11b-vision-instruct` via structured JSON prompting as the primary path (was `mistralai/ministral-14b-instruct-2512` until NVIDIA deprecated it — that endpoint now hangs until timeout, which silently degrades extraction to the regex last resort, so the model was swapped 2026-07-25) — no local model, no package dependencies. Entity types extracted: ASSET_TAG, PROCESS_PARAMETER, FAILURE_MODE, REGULATION, ACTION_VERB, MATERIAL, PERSON, LOCATION, DATE, ORGANIZATION. Fallback: Ollama `llama3.1:8b` (local, for air-gapped or offline operation). Last resort: regex patterns for ASSET_TAG format matching. All three paths produce the same output schema. Model names are configured via `.env` (`NVIDIA_NIM_NER_MODEL`, `OLLAMA_NER_MODEL`) — no hardcoding in service code.

Kairos surfaces low-confidence entity extractions inline in search results through the **Active Learning Annotation Interface**, allowing operators to confirm, correct, or delete proposed entities in one tap. Every correction is stored in `ner_annotations` and linked back to the relevant quarantine item, building a facility-specific labeled dataset over time without imposing a separate annotation task on staff.

**Engineering drawing topology:** Standard OCR applied to engineering drawings destroys the spatial relationships that are the actual information content of the drawing — *which* valve isolates *which* pump, *which* loop controls *which* line. The perception engine therefore uses **vision-understanding**, not text extraction, to reconstruct the physical topology (equipment nodes, flow connections, valve positions, instrumentation loops, isolation boundaries, line designations) as structured JSON. Two implementation paths deliver this same "vision, not OCR" principle:

- **Path B — Cloud vision-language model (current implementation).** A cloud VLM (NVIDIA NIM `meta/llama-3.2-11b-vision-instruct`) is prompted to emit the topology JSON directly from the drawing image. No GPU, no training, no labeled dataset — consistent with Kairos's cloud-only model plane (`NER`/`OCR`/`LLM` are all cloud). Implemented in `api/services/pid.py`, wired into the `run_ocr` activity for `document_type='pid_drawing'`; falls back to a demo fixture (flagged `topology_source`) when the model is unreachable, so the pipeline always completes.
- **Path A — Custom YOLOv9 + LayoutLMv3 on local GPU (future upgrade).** Sector-specific models trained on labeled P&IDs (ISA/IEEE/IEC/ISO symbology), run unquantized on local GPU. Higher accuracy and offline/air-gapped capability, but requires a labeled drawing dataset + GPU infrastructure + ML training. Deferred until that data is collected; adopt for high-volume or data-sovereign deployments.

The choice is an accuracy/effort trade-off, not a correctness one: both paths preserve topology (unlike OCR), and — critically — the mandatory engineer-verification gate below absorbs any extraction imperfection, which is what makes Path B's lower accuracy acceptable today.

Mandatory requirement regardless of model accuracy: every engineering drawing topology extraction must undergo element-by-element engineer verification before the extracted topology enters the canonical graph. Even purpose-built commercial drawing parsers report 70-80% automation rates with the remainder requiring engineer sign-off. In Kairos, safety-critical topology — isolation boundaries, instrumentation loops, pressure containment circuits, electrical protection zones — cannot be considered canonical until a qualified engineer has confirmed the extraction element by element. The perception engine produces candidate topology; the governance workflow in Layer 7 gates canonical promotion. Automation accelerates the verification process by pre-populating the review interface with highlighted elements requiring confirmation; it does not replace the verification step.

**Form and checklist parsing:** Layout-aware extraction that understands the structure of industrial forms — inspection checklists, work order fields, permit-to-work sections — and maps field contents to their semantic meaning rather than treating them as undifferentiated text blocks.

**Handwriting recognition:** Handwritten content is prevalent in field inspection forms and shift logs, and it is handled by routing rather than by a dedicated model. Documents that reach extraction through the image path — the only path on which handwriting occurs, since a native digital PDF carries a text layer instead — are flagged `handwriting_suspect` in the extraction output, and that flag travels with the extraction into review. The OCR and vision models already read the image; a separate handwriting model would add a third specialist to maintain for a gain the confidence-routing gate largely absorbs, because low-confidence extractions go to human review regardless of what produced them. The flag is deliberately not a confidence penalty: downgrading every scanned form on suspicion would push clean typed scans into review queues alongside genuine handwriting. Adopt a dedicated model when measured extraction quality on handwritten field forms is the binding constraint on a deployment — it is a swap behind the same output schema, like the NER paths.

**Voice-to-structured-knowledge:** Groq API (`whisper-large-v3`) for transcription of voice notes captured in the elicitation engine (Layer 9) — cloud API, no local model. Transcript fed through the NER pipeline for structured entity extraction.

All extraction outputs carry confidence scores per field. Outputs below configurable confidence thresholds route to human review before canonical consideration. No extraction result automatically becomes truth.

---

### Layer 4: Temporal Reality Graph

**Purpose:** Store the governed, time-bounded, authority-weighted, provenance-linked knowledge of the organization about its assets, their states, their histories, and the relationships between them.

This is the cognitive core of Kairos. Every piece of knowledge stored in the graph is not a fact — it is a claim, with explicit metadata about when it was true, who says it is true, how confident we are that it is true, and where the evidence lives.

**Node types:** Assets (equipment, systems, facilities), Events (failures, inspections, incidents, maintenance actions), Documents (procedures, manuals, regulations, standards), Concepts (failure modes, regulatory clauses, process parameters), Persons (personnel with authority levels and domain expertise), and Organizations (sites, departments, external vendors, regulatory bodies).

**Edge properties — every edge in the graph carries all six:**

- **Validity window:** valid_from and valid_to timestamps. A fact about a pressure limit is only true for the period that the governing procedure was in effect. When the procedure is superseded, the fact's validity window closes. The old fact is not deleted; its window is closed. Time-travel queries can retrieve the exact state of knowledge at any historical moment.

  Timestamp normalization is a first-class ingestion requirement. Brownfield plants commonly operate EAM, DMS, SCADA, and email archive systems whose server clocks are not synchronized to a common NTP source. A work order timestamp from SAP PM that is four hours ahead of the maintenance log timestamp from a different system will produce incorrect temporal ordering in the graph, corrupting time-travel RCA queries. The ingestion pipeline applies a timestamp alignment pass before committing any validity window to the graph: cross-referencing timestamps from the same event across multiple source systems, detecting drift, flagging discrepancies beyond a configurable tolerance for human review, and normalizing to a site-canonical time reference derived from the most authoritative available source (typically the historian, which is the most precisely clock-synchronized system in an industrial plant). Drift is measured only across sibling rows of the same correlated event — the same real-world action reported by two systems. A comparison between an event's occurrence and its ingestion is not drift, and treating it as such manufactures skew out of ordinary pipeline latency.

  Like the Layer 0 model gate, this pass ships reporting rather than blocking: `TIMESTAMP_DRIFT_ENFORCE` defaults off, so a drifting event is detected, logged, and surfaced in the drift report, but still commits its validity window. Holding events out of the graph on a drift signal that has not yet been calibrated against a specific site's clock estate would silently stall ingestion, and an event missing from the graph is a worse failure than an event with a known, reported timestamp uncertainty. Enforcement is enabled per deployment once the observed drift distribution establishes what tolerance actually means at that site.

- **Authority level:** A five-level hierarchy that is non-negotiable in the industrial governance model. Level 1: Regulatory requirement — the applicable national and industry regulations for the sector (examples: OISD/PESO for Indian oil and gas, FDA 21 CFR Part 11 for pharmaceuticals, CEA regulations for power utilities, ISO 45001 for occupational safety across all industries). Level 2: Engineering standard or site-specific policy document. Level 3: OEM manual or approved technical specification. Level 4: Site operating procedure or maintenance standard. Level 5: Field observation, informal note, or unverified report. When facts at different authority levels conflict, the system does not average them, does not present them as equivalent, and does not default to the most recent. It ranks by authority, presents the conflict explicitly, and escalates for resolution.

- **Provenance pointer:** A direct link to the specific artifact in the immutable vault, and the specific extraction event that produced this fact. Every claim in the graph can be traced to its source document.

- **Confidence score:** The extraction model's confidence in this specific fact, informed by source document quality, extraction model performance on this document type, and any human corrections applied during review.

- **Verification status:** Unverified (extracted but not reviewed), Verified (confirmed by human authority), Disputed (flagged as potentially incorrect), Superseded (valid_to window closed), Quarantined (from unverified field input, searchable but not canonical).

**Blast-radius analysis:** When a source document is superseded or a fact's verification status changes, Kairos automatically traverses all downstream facts, recommendations, and relationships that derive from the affected source, marks them for review, and generates a blast-radius report identifying everything potentially contaminated by the change. This prevents the silent propagation of outdated information through the knowledge base — one of the most dangerous failure modes of traditional document management.

---

### Layer 5: Zero-Copy OT Virtualization Layer

**Purpose:** Make live operational telemetry accessible to the knowledge system without ingesting, storing, or duplicating time-series data.

Kairos does not bulk-ingest historian data. Storing live sensor telemetry — thousands of data points per second across hundreds of instruments — in the same infrastructure as the knowledge graph would collapse the system under the volume, create a second copy of data that the historian already manages better, and generate enormous compliance complexity around data retention.

Instead, the temporal reality graph stores semantic references to OT data sources: "Pump P-101's vibration is measured by instrument FT-3047, accessible via the site PI Web API at endpoint [reference]." When a query requires current or historical OT data, the system executes an ephemeral, federated query to the historian, retrieves the relevant time window, reasons over it in memory, and discards the raw data. The historian remains the system of record for operational telemetry. Kairos is the system of record for knowledge about what that telemetry means.

This architecture is critical for the outcome attribution system (Layer 10). When a maintenance recommendation is made and Kairos needs to evaluate whether it worked, it queries the historian for post-maintenance telemetry and compares it against pre-failure baselines. The comparison happens in-memory; the raw telemetry is not stored.

The OT virtualization layer targets four historian interfaces behind one connector contract: OSIsoft PI Web API, OPC-UA client connections, Honeywell Uniformance REST API, and a generic GraphQL federation layer for non-standard historians. New connector types are added without changing the core layer.

Only PI Web API is implemented. The other three are registered against the contract and return an explicit "not implemented in this build" rather than an empty result set, and the connector registry endpoint reports each one's true state — supported, configured, reachable — so the gap is inspectable instead of asserted. This is the deliberate posture, not an oversight in the write-up: an unimplemented connector that returns an empty series is indistinguishable from a healthy historian with no data for that tag, and in a layer whose output feeds outcome attribution, that silence would read as evidence. A connector is written against a real endpoint or it says it is not there. Each remaining protocol is implemented when a deployment supplies a historian to verify it against — OPC-UA in particular requires the `gopcua` client and a live server, and a client written blind is a client that has never been correct.

As part of historian registration, the OT virtualization layer constructs and maintains an **instrumentation coverage map**: a structured record of which physical assets and which specific components on those assets are directly monitored by historian tags. This map is derived from two sources — the engineering drawing topology extracted by Layer 3 (which identifies what instruments exist and where they sit in the process flow) and the historian tag registry (which identifies which of those instruments are actually connected and reporting). The instrumentation coverage map is queried by Layer 10 (outcome attribution) to determine whether a given maintenance action can be evaluated via telemetry or must rely on human-verified closeout documentation.

**IEC 62443 compliance is a non-negotiable prerequisite for any OT federation connection.** IEC 62443 (the international standard for operational technology network security, with significant 2024/2025 updates) governs how IT-side systems connect to OT networks through its zones, conduits, and security level (SL-1 through SL-4) framework. Any Kairos-to-historian connection creates a conduit between the IT knowledge plane and the OT operational network — a conduit that the facility's OT security policy will require to be formally scoped, threat-modelled, and governed before it can be authorized. The IEC 62443 design (zone boundaries, conduit specification, target security level, microsegmentation between the Kairos federation layer and the OT historian endpoint) must be completed and approved by the facility's OT security authority before any historian connection is activated. This is a gating requirement for Layer 5, not a post-deployment hardening task.

The gate is organisational, and Kairos does not model it in software. Zone boundaries, conduit specification, and target security level are approvals granted by a facility's OT security authority against that facility's network topology — there is no artifact the platform could check to know whether they have been issued, and a self-asserted "62443 approved" flag in Kairos's own configuration would provide the appearance of a control while enforcing nothing. What the platform does instead is make the connection surface explicit: the connector registry names every historian endpoint, its protocol, and its configuration state, so the conduit inventory the 62443 design has to cover can be read directly rather than reconstructed. Activation remains gated by the facility's process, and by which endpoints are configured in deployment — not by an in-app switch.

---

### Layer 6: Quarantine Knowledge Layer

**Purpose:** Provide a searchable, clearly non-canonical holding space for unverified operational knowledge — field observations, voice notes, informal reports, deviation flags — that is useful as reference without contaminating governed truth.

Industrial knowledge does not arrive in clean, verified packages. A field technician notices something unusual about a rotating component but hasn't formally raised it yet. A retiring engineer records a voice note about a piece of equipment that operates counterintuitively. A shift log mentions a near-miss that hasn't been formally reported. An operator flags a physical deviation from the engineering drawings that exists in the actual facility but not in the documentation.

All of this is operationally valuable. None of it should automatically become canonical fact.

The quarantine layer holds all unverified inputs with full searchability but explicit labeling: every query result surfacing quarantined knowledge is visually distinct and textually labeled as "Unverified field input — not reviewed by engineering authority." Users can find this knowledge, cite it, and act on it with informed judgment. The system never pretends it is the same as verified canonical fact.

Quarantined knowledge is linked to the canonical graph for discoverability — a quarantined observation about a specific asset is searchable in the context of that asset — but does not participate in confident answer synthesis. Synthesized answers that draw on quarantined knowledge explicitly flag that dependency.

The quarantine layer has a review queue. Every item in quarantine is assigned to a domain owner for review. The owner can promote to canonical (with authority level assignment), dispute, archive, or request more information. Items that remain unreviewed for a configurable period are escalated.

---

### Layer 7: Dual-Track Governance and Adjudication Plane

**Purpose:** Resolve conflicts between sources of knowledge through governance processes appropriate to the severity and nature of the conflict, without creating bureaucratic paralysis or allowing safety-critical contradictions to persist unresolved.

The fundamental mistake of single-track conflict handling is treating a formatting inconsistency between two maintenance records the same as a contradiction between an OEM pressure limit and a site operating procedure. They are categorically different in their safety implications and require categorically different resolution processes.

**Administrative conflict track:** Minor inconsistencies — varying date formats for the same event, different spellings of a location name, minor timestamp discrepancies between linked records, metadata mismatches — route to a lightweight internal data review queue. The assigned data steward resolves these without engineering sign-off. The resolution is logged. No MoC is triggered.

**Structural engineering conflict track:** Conflicts involving safety-critical parameters — pressure limits, temperature thresholds, electrical ratings, inspection intervals, isolation procedures, material specifications — route to a formal Management of Change workflow. Kairos auto-drafts the Engineering Work Request with the conflict description, the conflicting sources with their authority levels, and the blast-radius impact. The draft enters the plant's existing MoC system via webhook. Kairos does not update the canonical graph for the affected fact until the MoC returns a digitally signed resolution webhook. Until then, every query touching that fact displays an explicit warning banner identifying the pending MoC by number.

**Case management operating model:** Both tracks have owners, SLAs, escalation paths, and backlog monitoring. Administrative conflicts: 5-day SLA, automatic escalation to data governance lead at 7 days. Engineering conflicts: SLA based on criticality classification of the affected equipment (24 hours for safety-critical, 5 days for non-critical). Backlog volume is surfaced in the operations dashboard. The governance load is manageable because the dual-track classification prevents trivial issues from consuming engineering time.

**SPC-based adaptive circuit breaker:** Rather than a static threshold on human override rate, the circuit breaker uses Statistical Process Control charts with rolling Z-scores calculated per asset class. When override rates for a specific asset class drift outside the control limits derived from that class's own historical baseline, the circuit breaker halts automated extraction for that class and routes new inputs to human-only processing until the model is retrained and passes Layer 0 validation. The breaker also halts on a Layer 0 signal directly: an asset class the model gate has marked as regressed is blocked without waiting for override rates to move.

The per-class rolling baseline is the mechanism that makes this adaptive, and it already absorbs most of what a deployment-maturity axis would add. A new deployment processing its first 500 work orders expects elevated override rates as the knowledge base builds — but those elevated rates *are* that class's baseline during that period, so the Z-score is computed against them and does not trip on the expected level. What a maturity axis would add is sensitivity to the second-order case: a deployment whose override rate is stable but stable at a level that should have improved by now. That is a knowledge-coverage question rather than a model-drift question, and it is visible in the coverage dashboard without a second control chart. The maturity dimension is added if a deployment demonstrates drift the per-class baseline absorbs rather than catches.

---

### Layer 8: Operational Event Subscription and Proactive Delivery Layer

**Purpose:** Transform Kairos from a system that answers questions into a system that delivers knowledge at the moment of operational need, without requiring a query.

This is the layer that does not exist in any prior solution and is the architectural expression of Kairos's fundamental insight.

The event subscription layer maintains persistent connections to the operational systems that produce events signaling that work is about to happen or is happening. When an event arrives, Kairos determines whether it is a knowledge-relevant moment — a moment when a person is about to take an action that organizational knowledge should inform — and if so, assembles and delivers a contextual brief to the right person before they act.

**Canonical Event Normalization**

Before any operational event reaches the trigger governance subsystem, it passes through a canonical event normalization layer. Kairos subscribes to events from multiple source systems — SAP PM, the site CMMS, the DCS alarm management system, the PTW workflow, and manual data entry — each with different schemas, timestamps, event semantics, and propagation delays. Without normalization, the same real-world event (a work order being raised) can arrive as multiple events from multiple systems, producing duplicate briefs. A manually issued PTW may arrive seconds before or after the corresponding DCS event for the same isolation action. A CMMS work order may be created with a 15-minute delay relative to the SAP PM event it mirrors.

The normalization layer performs three operations before any event enters the priority queue. First, deduplication: events that share a canonical asset ID and event type within a configurable time window (default 10 minutes) are collapsed to a single authoritative event, with the event from the highest-authority source system taking precedence. Second, correlation: events from different source systems that refer to the same physical action (e.g., a PTW issuance and the associated DCS tag-out confirmation) are linked as a single compound event, enriching the brief content without generating separate deliveries. Third, delay compensation: events that arrive out of sequence due to system propagation delays are buffered and reordered before being committed to the trigger queue. The normalization layer maintains a configurable late-arrival window (default 5 minutes) during which out-of-order events are held before the trigger queue is committed.

**Subscribed event sources (via Redis Streams):**

- Work order creation (CMMS/EAM): a technician is about to be assigned to work on specific equipment
- Permit-to-Work generation: isolation work, hot work, confined space entry, or high-pressure line work is about to begin
- Shift handover: a new crew is taking responsibility for the plant and must receive contextual knowledge about the current state
- Alarm acknowledgment: an operator has acknowledged a process alarm and is evaluating response
- Equipment tag-out: equipment is being taken out of service for maintenance
- Inspection completion: a new inspection result has been recorded, potentially triggering graph updates
- MoC completion: a change has been formally authorized, triggering canonical graph update and blast-radius notification
- Recurring failure detection: a work order has been opened for equipment that has failed recently in a similar way
- Recurring non-conformance detection: an inspection or quality record has been raised against a clause that has already been breached on comparable equipment

The last two are the same mechanism pointed at the two axes on which a plant degrades. Recurring *failure* detection is asset-scoped and reactive to breakdown; recurring *non-conformance* detection is clause-scoped and is what catches a quality problem while it is still an isolated finding. The escalation the industry cares about is not one deviation growing worse — it is the same deviation appearing on the third asset, at which point it is no longer a maintenance matter but a systemic one: a procedure that reads ambiguously, a spare from a bad batch, a calibration drifting across a fleet. A per-record view cannot see that; a clause-scoped graph traversal can, because the clause is already a node and the findings already link to it.

This is deliberately pattern detection over recorded findings, not prediction of a finding that has not happened yet. The trigger is a real non-conformance on real equipment; what Kairos adds is the observation that it is the *n*th of its kind, delivered to the quality manager while acting on it is still cheap. Consistent with Layer 10: the system reports what the evidence already contains, earlier than a human would assemble it.

**Proactive brief content by event type:**

For work order creation: complete failure history of the specific equipment, OEM-recommended corrective actions for the identified failure mode, current regulatory obligations for this equipment class, any open compliance items related to this equipment, similar failures at other assets in the same equipment class (site-wide and cross-site if multi-site), pending MoC items that affect this equipment, and any quarantined field observations that have been linked to this asset.

For PTW generation: precise isolation point locations from engineering drawing topology for the defined isolation boundary, maintenance history of every isolation device in the boundary, regulatory requirements for this specific PTW type, recent near-misses in the same work area, relevant lessons from similar historical PTWs, and any known deviations between the engineering drawings and physical facility state for this area.

For shift handover: equipment with open work orders and their current status, alarms that are currently active and their history, any knowledge conflicts awaiting resolution that affect current operations, quarantine items pending review from the outgoing shift, and a summary of any system-detected anomalies since the last handover.

**Brief format:** Mobile-first, 30-second read time for field briefs, 2-minute read time for PTW briefs, 5-minute read time for shift handover briefs. Every brief includes: the equipment or area of concern, the critical finding (what you need to know), the supporting evidence (what this is based on), the authority level of the information (how confident you should be), and a direct link to source documents in the vault. Briefs do not replace existing safety processes. They augment them with the knowledge the system has assembled that the person is unlikely to have themselves.

**Trigger Governance Subsystem — EEMUA 191 / ISA-18.2 Compliance**

The proactive push architecture introduces the most thoroughly documented failure mode in process industry safety operations: alarm fatigue. EEMUA Publication 191 and ISA-18.2 — the operational standards governing alarm and notification system design in every serious industrial facility — establish that notification rates exceeding approximately 6 events per operator per hour in normal operation degrade human performance and produce a reflexive dismissal response. A proactive push engine without explicit trigger governance is structurally identical to an alarm system without alarm rationalization: the condition these standards were written to prevent.

Kairos implements trigger governance as a named, first-class subsystem within Layer 8, not as an assumed property of good configuration. Its components:

*Per-user push rate ceiling:* A hard limit targeting ≤6 push events per operator per hour in steady-state normal operation, consistent with EEMUA 191's benchmark. The governor maintains a rolling count per user identity and suppresses lower-priority pushes when the ceiling is approached, queuing them for delivery when the rate drops.

*Priority queue with explicit suppression logic:* When multiple events fire simultaneously for the same user, the governor applies a defined priority order: PTW-triggered safety briefs are never suppressed; shift handover briefs are delivered once per handover regardless of other activity; work order briefs for safety-critical equipment take precedence over routine equipment; recurring failure detections take precedence over first-occurrence detections. Lower-priority briefs are held, not dropped — they are delivered when the user's push rate allows.

*State-based suppression for known abnormal operating periods:* During turnarounds, planned shutdowns, and declared plant emergencies — conditions where operator cognitive load is highest and event rates are elevated — the push governor automatically raises the suppression threshold, delivering only the highest-priority briefs and holding all others. The operating state is fed from the plant's own DCS or EAM scheduling system.

*Notification state management:* A brief is not re-delivered if the same equipment generates a second triggering event within a configurable cool-down window (default: 4 hours). This prevents a single failing asset from generating a cascade of briefs.

*Pilot monitoring gate:* Before Phase 3 (governed proactive mode) activates, the deployment must demonstrate that push volume in the pilot population has stayed within EEMUA 191 norms for 30 consecutive operating days. If pilot push volume consistently exceeds the ceiling, Phase 3 activation is deferred and the trigger configuration is revised. The push thesis is a hypothesis; this gate tests it against real operational data before it becomes the default operating mode.

**Human sign-off requirement:** For safety-critical briefs (PTW-triggered, high-criticality equipment), the brief interface requires explicit digital acknowledgment from the authorized human before it is logged as delivered. The acknowledgment is cryptographically signed with the user's identity and the complete evidence lineage displayed. This creates an audit trail of what knowledge was available, when it was delivered, to whom, and that they confirmed receipt. Legal accountability remains with the human authority. Kairos provides evidence and traceability, not autonomous authorization.

---

### Layer 9: Structured Knowledge Elicitation Engine

**Purpose:** Extract tacit operational knowledge from experienced practitioners at the moment it is most accessible and accurate, with minimum burden on the practitioner.

"Record a voice note" is not a knowledge engineering strategy. Experienced practitioners under operational pressure will not stop their workflow to document knowledge that lives in their heads. They may intend to, but shift pressure, cognitive load, and the absence of a structured prompt mean that voluntary documentation happens rarely and inconsistently.

Kairos captures tacit knowledge through event-triggered, contextually targeted micro-interviews. The trigger condition: a work order with a rare failure code (occurring fewer than three times in the site history for this equipment class), an unusually long resolution time (exceeding the 90th percentile for this failure type), or a work order explicitly marked as requiring novel troubleshooting by the technician. When any of these conditions are met, Kairos generates a micro-interview at the moment of work order closeout — when the knowledge is at peak clarity and the cognitive context is fully loaded.

**Near-miss capture is the same problem, and it is the one worth solving hardest.** Near-misses appear throughout this architecture as *content* — surfaced in PTW briefs for the work area, held in quarantine when a shift log mentions one informally, promoted cross-site as a pattern. What makes them difficult is capture, not use. A near-miss is the highest-value safety record a plant produces, because it carries the causal sequence of an incident without the consequence, and it is chronically the most under-reported: filing one is a form the reporter fills in on their own time, about something that did not happen, with a non-zero perception of blame attached.

The elicitation engine addresses exactly that asymmetry, so near-miss capture is a trigger condition rather than a separate subsystem. Three signals warrant a prompt: a PTW closed with an isolation deviation from the planned boundary, an alarm acknowledged and cleared without a corresponding work order, and a shift handover whose free text a quarantine-bound extraction flags as describing an unplanned event. The prompt is the same two-minute, three-question form delivered at closeout, and it asks what happened rather than requiring the reporter to classify it — classification is the reviewer's job and demanding it up front is most of the reporting friction.

Responses enter quarantine like any other elicitation output, non-canonical until a safety authority reviews them. This matters more here than elsewhere: a near-miss that automatically became canonical fact would be a system inferring an incident that the organisation has not agreed occurred. The reviewer decides whether it is a near-miss, a hazard observation, or nothing — and only then does it become a leading indicator the graph can count.

**Interview design:** 3 to 5 questions maximum. Questions are generated by the knowledge graph based on: what is already known about this failure mode, what is not known and is most operationally valuable, what specifically about this incident deviates from the typical pattern, and what the graph would need to make better recommendations next time. Questions are not generic ("What did you observe?"). They are specific and context-derived — for example: "The previous two failures on this asset were attributed to lubrication intervals. Did you observe any differences in the component condition this time that suggested a different root cause?" Multiple choice where appropriate; short free-text where contextual detail is essential. Two minutes maximum. Delivered on the mobile field app at shift closeout.

Responses enter the quarantine layer immediately, linked to the specific asset, failure code, and work order. The question context is preserved alongside the answer, so reviewers understand exactly what was being asked. Reliability engineers see quarantine items grouped by equipment class and failure mode, making domain-focused review efficient.

The elicitation engine also supports structured off-boarding interviews for personnel approaching retirement: a scheduled series of 15-minute sessions over 4-6 weeks, each focused on a specific equipment family or failure mode that the system has identified as poorly covered in the knowledge base and heavily dependent on that individual's historical work orders.

---

### Layer 10: Telemetry-Grounded Outcome Attribution and Learning Loop

**Purpose:** Enable the system to learn from operational outcomes without corrupting the knowledge base with false causal inferences.

The 30-day recurrence flag — used naively — is an attribution disaster. If Kairos recommends a seal replacement and the pump fails 15 days later with an electrical fault, naive learning would degrade the confidence of the seal replacement recommendation. That is the opposite of correct learning. The system would become progressively less accurate the more it "learned."

Real attribution requires three parallel checks before any confidence adjustment is made:

**Telemetry baseline comparison:** When a maintenance work order closes, Kairos executes a federated historian query for the specific instruments monitoring the affected equipment. It establishes the post-maintenance telemetry baseline: did vibration, temperature, and other relevant parameters return to normal operating range? If a new work order opens within 30 days, Kairos queries the historian again and compares: did the parameters hold at baseline before the recurrence, or did they drift immediately after maintenance?

A critical constraint on this check: brownfield industrial facilities — many operating for 20-40 years across any sector — typically have macro-level instrumentation, not component-level sensors. A facility may have an overall motor current reading and a discharge pressure reading on a rotating asset, but no dedicated sensor for a specific internal component such as a seal, bearing, or lining condition. If the recommended maintenance action targeted that specific component, the macro-sensors may return to normal baseline after repair (confirming the asset is operational) without being able to confirm that the specific failure mode has been resolved. Under these instrumentation conditions, telemetry baseline comparison cannot be the primary attribution check — it can only confirm that the equipment is running, not that the specific failure mode has been resolved.

When the system's instrumentation coverage map (derived from the engineering drawing topology and historian tag registry) indicates that the affected component is not directly instrumented, the telemetry check is downgraded from primary to supporting evidence. The primary attribution check in this case becomes the human-verified operational testing documented in the CMMS work order closeout notes. Technicians closing a work order in this instrumentation context are prompted to record the operational verification performed — "ran equipment for 30 minutes at design load, no abnormal noise, temperature, or vibration observed" — and this human attestation becomes the primary evidence that the repair succeeded. The telemetry record serves as a secondary corroboration where available.

**Failure code cross-reference:** The new work order's failure code is compared against the original work order's failure code. If the new failure is in a different failure mode family (e.g., original was mechanical seal failure, new is electrical insulation failure), the recurrence is classified as counterfactual. No confidence adjustment on the original recommendation. Confidence adjustment is only triggered when the failure code and symptom profile explicitly match the original.

**Execution verification:** Kairos cross-references the recommended action against what was actually documented as completed in the work order. If the recommendation was to replace the mechanical seal but the work order records only a repack (not a replacement), the failure is classified as execution deviation, not recommendation failure. The system flags the deviation for the reliability engineering team rather than penalizing the source knowledge.

Only when all three checks confirm a genuine recommendation failure — telemetry didn't recover, same failure mode recurred, recommended action was executed correctly — does Kairos downgrade the authority ranking of the specific source document and flag it for engineering review. The adjustment is not permanent: engineering review can restore the authority level if they determine the specific case was anomalous.

This attribution architecture ensures that the learning loop improves the system without corrupting it.

**What this layer deliberately does not do: forecast.** Kairos produces no failure predictions, no remaining-useful-life estimates, and no optimised maintenance schedules. That is a stated position, not an omission, and it follows from the same reasoning as §2.

A predictive model earns its confidence from failure histories across many comparable assets under comparable conditions. A brownfield deployment on day one has a sparse graph and a handful of documented failures per asset class; a model fitted on that produces an output shaped like a prediction with none of the evidence behind it. In a safety-critical setting that is worse than silence, because a maintenance planner cannot tell a well-grounded forecast from a poorly-grounded one by looking at it — and the whole architecture above exists to make exactly that distinction visible. Shipping a confidence number the evidence does not support would contradict the refusal gate, the authority hierarchy, and the quarantine layer in a single feature.

What Kairos provides instead is the input a forecast would need, made legible: the complete failure history for the asset, the same failure mode at comparable assets, the OEM position, current telemetry against the pre-failure signature from previous incidents, and recurring-failure detection when a work order opens on equipment that has failed this way before. The planner does the forecasting; Kairos ensures they are not doing it from memory. Scheduling stays in the CMMS, which owns crews, spares, and shutdown windows — none of which are in this graph.

The honest condition for revisiting: once a deployment has accumulated enough verified failure history for a specific asset class that a per-class base rate is meaningful, forecasting for *that class* becomes defensible, and Layer 0's rolling corpus is the mechanism that would establish it. Forecasting is gated on evidence, like everything else here.

---

### Layer 11: Reasoning and Synthesis Layer

**Purpose:** Assemble retrieved knowledge, graph context, and OT data into coherent, provenance-backed, confidence-annotated answers and operational outputs.

The synthesis layer never originates knowledge. It assembles, organizes, explains, and presents knowledge that exists in the vault, the graph, or the quarantine layer. Constraining synthesis to explicit retrieval outputs with mandatory source citation substantially reduces hallucination risk — but does not eliminate it. The residual risk is extractive hallucination: the model confidently citing the correct document while misreading a value from the wrong row of a table, misinterpreting a unit conversion, or referencing a section adjacent to but not identical with the relevant passage. Unlike free hallucination (fabricating a source), extractive hallucination is harder to detect because the cited source is real. In safety-critical parameter queries, extractive hallucination is as dangerous as fabrication. The explicit refusal behavior for safety-critical queries (described below) and the mandatory source-link in every answer — which allows the receiving technician to verify the cited passage directly — are the primary mitigations. Layer 0's outcome attribution tracking provides the feedback signal that identifies when synthesis errors are occurring systematically on a specific document type or extraction class.

**Retrieval strategy:** Hybrid retrieval using four complementary methods. Exact match retrieval for tag numbers, part numbers, document IDs, and regulatory clause references — structured search where precision matters. Semantic retrieval using vector embeddings over extracted knowledge fragments for conceptual queries ("what causes bearing failure in high-temperature applications"). Graph traversal for relationship queries ("what procedures govern this equipment during this regulatory context") and time-travel queries ("what did we know about this failure mode three years ago"). Authority-ranked re-ranking that adjusts retrieval results by the authority level of their source, ensuring a regulatory requirement outranks a field observation in answer construction.

**Output types:** Query answers (with mandatory source citations, confidence indicators, and explicit uncertainty flagging where evidence is incomplete), RCA packs (timeline of events, failure mode hypotheses ranked by evidence weight, supporting documents), compliance gap reports (regulatory requirement mapped against current procedure or equipment state, evidence of compliance or gap, suggested remediation), maintenance briefings (full equipment context assembled for a specific work order), proactive push briefs (assembled by Layer 8 triggers), and evidence packages (compiled for audit submission).

**The Copilot — conversational access to the same synthesis path.** Query answers are delivered through a multi-turn conversational surface, not a single-shot search box. Each turn carries its own as-of timestamp, so a conversation can move through time — asking what is true now, then what was true before a procedure was superseded, without restating the question. Every turn is an independent, fully governed synthesis call: the same retrieval, the same authority ranking, the same mandatory citations, and the same safety-critical refusal gate apply per turn. Conversation history is context for interpreting the *question*, never a source for the *answer* — a fact stated in an earlier turn does not become citable evidence in a later one, because that would let the model launder its own output into provenance. A turn that retrieves nothing renders an error with retry, never a fabricated answer or a fallback to a previous turn's content. The surface is available on both the field and desktop interfaces described in Layer 12.

**Uncertainty handling:** When evidence is insufficient to answer with confidence, the system does not guess. It states what is known, what is not known, what would be needed to answer confidently, and where the person should escalate. Confidence below a configurable threshold for a specific query type triggers an explicit escalation recommendation rather than a low-confidence answer presented as reliable.

For a defined category of safety-critical parameter queries — confirming a maximum allowable operating pressure, verifying an isolation interlock sequence, specifying a torque value for a critical fastener — the system applies a stricter posture than hedged uncertainty: explicit refusal to synthesize an answer when the evidence base does not meet the confidence threshold for that category. The system returns the source documents directly, identifies the specific gap, and directs the user to the appropriate human authority for confirmation. A hedged partial answer in a safety-critical context is more dangerous than no answer, because a technician under time pressure will treat ambiguity as confirmation. Explicit refusal removes that risk. The refusal behavior is configurable per query category and per equipment criticality class, and all refusals are logged for governance review.

---

### Layer 12: Phased Deployment, Trust Architecture, and Point-of-Action Interface

**Purpose:** Ensure that Kairos earns operational trust through a structured deployment arc rather than demanding trust on day one, and delivers knowledge in formats appropriate to the physical conditions of industrial work.

The history of failed industrial knowledge platforms is substantially a history of failed organizational change management. A technically excellent system that enters a hierarchical, shift-pressure industrial culture without a trust-building strategy will be used as a slightly better filing system and then abandoned. Kairos embeds the adoption architecture into the software's release gates.

**Phase 1 — Shadow / Retrieval Mode (Months 1 to 3):** Kairos functions as an advanced search layer over the immutable vault. No proactive briefs. No synthesis. No recommendations. Workers learn to find documents faster and more completely. The system builds the temporal graph and resolves the MDM in the background. Trust in retrieval accuracy is established before trust in synthesis is requested. User feedback in this phase (rating retrieval quality, flagging incorrect results) feeds directly into Layer 0 validation.

**Phase 2 — Human-in-the-Loop Assist Mode (Months 3 to 6):** Synthesis activates. Query answers are generated with full provenance. The elicitation engine activates. The governance workflow for conflicts activates. Every synthesized output presented to a user includes a mandatory feedback interface: a single-tap rating (Accurate, Missing Context, Incorrect) and an optional free-text note. This feedback is not user experience research — it is direct input to the outcome attribution system and Layer 0 validation. Workers who provide feedback see the system visibly improve in response to their input. This is the trust-building mechanism.

**Phase 3 — Governed Proactive Mode (Month 6 onward):** Proactive PTW and work order briefs activate. The full event subscription layer goes live. Shift handover integration begins. Every proactive brief requires explicit acknowledgment, and the feedback loop remains active. At this phase, workers have six months of experience with Kairos as a reliable retrieval and synthesis tool, which is the foundation for trusting its proactive outputs.

**Two disclosure contracts, enforced rather than encouraged.** Trust is lost faster by one confidently-presented placeholder than it is built by a hundred correct answers, so the interface is constrained so that presenting unverified material as verified is not an available failure.

*Nothing degraded is rendered as if it were real.* Where a backend path falls back to a fixture — the P&ID topology path when the vision model is unreachable is the live example — the response carries the provenance of that fallback (`topology_source`), and the interface renders it as a fixture. The pipeline completing is not permission to present its output as extracted data.

*No silent fallback in the client.* The frontend has exactly one data source: live. There is no fixture tier to degrade into, and this is enforced by the type system rather than by convention — the data-source type has a single member, so a fallback branch cannot return without a compile error. Fetchers throw. The user sees real data, a loading state, or an error with a retry — never a plausible-looking placeholder they have no way to distinguish from a result.

Both are the same principle the quarantine layer and the synthesis refusal gate enforce elsewhere: the system states what it does not know rather than filling the gap. Applying it at the interface closes the last place where a governed backend could still be misrepresented on its way to a person.

**Field interface — any device, any conditions:** Mobile application built for industrial field conditions. Single-handed operation. Legible in direct sunlight. Functions in offline mode with automatic sync when connectivity is restored. Voice input option for hands-free querying and elicitation responses. Brief format is designed for reading while standing: key finding in the first two lines, detail below for those who need it. No interface that requires navigating menus or formulating a search query to get the answer to an urgent operational question.

**Engineer and reliability desktop workspace:** Full graph visualization, timeline view, document comparison, conflict resolution workflow, RCA assembly workspace, and audit trail viewer. This is where the depth of the knowledge graph is accessible in full for maintenance planners, reliability engineers, and process engineers.

**Quality and compliance cockpit:** A dedicated interface for quality managers and regulatory compliance officers. Continuous compliance gap dashboard mapped to the facility's applicable regulatory framework, evidence package assembly for audits, non-conformance tracking linked to root cause history, and inspection record management. Addresses the PS requirement for Quality and Regulatory Compliance Intelligence directly.

**Project and procurement workspace:** Engineering document registry for project teams, drawing revision tracking, vendor document management, and equipment history accessible during procurement decisions. A procurement officer evaluating a replacement asset can see the complete failure and maintenance history of the asset class being replaced.

**Management and cross-functional dashboard:** Executive-level KPI view covering knowledge coverage by asset class, unresolved knowledge conflicts, compliance posture, and cross-site pattern alerts. Designed for Plant Managers and Operations Directors who need situational awareness without operational detail.

**Self-reporting surfaces:** Kairos exposes its own operational posture to the people relying on it — component health and store reachability, the current benchmark figures with the date they were measured, and the deployment's configuration including which model providers and connectors are actually live. A knowledge platform that asks operators to trust it in safety-critical conditions cannot be a black box about its own state: an operator who can see that the historian connector is unreachable reads a telemetry-free brief correctly, and one who cannot will read it as an absence of findings.

**API and integration layer:** Headless API access for any function or system that needs to query the knowledge base programmatically — enabling Kairos knowledge to surface inside ERP screens, CMMS work orders, quality management systems, and third-party applications without requiring users to switch interfaces.

**QMS integration — named targets, same honesty as the historians.** The quality and compliance cockpit above is a Kairos-native surface; it is not a replacement for the plant's Quality Management System, and a deployment that already runs one should not be asked to keep non-conformance records in two places. The integration targets are **SAP QM**, **ETQ Reliance**, and **MasterControl**, with a generic REST adapter for QMS platforms outside that set.

Two directions matter, and only one of them is Kairos writing anything. Inbound: non-conformance records, CAPA actions and inspection results enter as documents, becoming graph claims linked to the asset with the QMS as their provenance — which is what lets a compliance gap cite the actual NCR rather than a restatement of it. Outbound: Kairos supplies the evidence package and the clause-scoped gap analysis, and the QMS remains the system of record for the quality process itself. Kairos does not open, route, or close a CAPA. The same division holds as with the historian: the external system owns its domain, Kairos owns knowledge about what its records mean.

**None of these connectors is implemented.** They are named here for the same reason Layer 5 names four historian protocols and implements one — a connector written without a live instance to verify against has never been correct, and an unimplemented connector that silently returns an empty result set is indistinguishable from a QMS with no findings. That silence would read as a clean compliance posture, which is precisely the false negative the compliance intelligence module is designed against. A QMS connection is built when a deployment supplies the instance to build it against.

---

## 4. End-to-End Data Flows

### Flow A: Work Order Opens — Proactive Brief Delivery

A work order is created in the facility's CMMS for Asset EQ-101 (a critical rotating asset in a manufacturing plant), assigned to a field technician, failure code: mechanical seal failure.

The event subscription layer detects the work order creation event via Redis Streams within seconds. Layer 8 identifies this as a knowledge-relevant event for the assigned technician. The reasoning engine queries the temporal graph for EQ-101's complete history: 4 prior seal failures in 8 years, OEM recommendation for the current seal variant (last updated 18 months ago — note the update), two similar assets in the same production unit with a combined 3 additional seal failures, a quarantined field observation from 6 months ago noting unusual vibration before the last seal failure, a pending compliance item for seal replacement documentation in the next regulatory audit, and current telemetry from the historian showing thermal cycling that matches the pre-failure signature from the previous incident.

Layer 11 synthesizes a brief: "EQ-101 has failed on mechanical seal 4 times. The previous failure (14 months ago) was preceded by the same thermal cycling pattern currently visible in telemetry. The OEM updated the seal specification 18 months ago — confirm you have the current seal variant (P/N [current] not the previous P/N [old]). A field technician noted unusual vibration before the last failure; this was not formally investigated. Consider checking bearing housing clearances during this repair. Audit requires seal replacement documentation before [date]." Three source documents are linked. One quarantined observation is flagged as unverified.

The brief arrives on the technician's mobile before they leave the maintenance workshop. They know, before they touch the asset, what the organizational knowledge says about this specific failure on this specific equipment.

---

### Flow B: PTW Issuance — Safety Brief and Sign-off

An engineer generates a Permit-to-Work for isolation work on Production Line 3, Section 2, to replace Valve V-247.

Layer 8 detects PTW generation. The engineering drawing topology (Layer 3 outputs, resident in the graph) identifies the complete isolation boundary for this work: the primary isolation is XV-203, with a secondary bleed at XV-204 and a local gauge bypass at PG-18. The graph records that XV-203 was last inspected 14 months ago and is approaching its 18-month inspection interval. XV-204 is a newer device with no failure history. PG-18 is flagged in the quarantine layer — a field observation 3 weeks ago noted this bypass device may not be seating fully.

Layer 11 generates a PTW brief: isolation sequence with exact device positions (from engineering drawing topology), inspection status of each isolation device, the quarantined deviation flag on PG-18 marked explicitly as unverified, the regulatory requirement for double-block-and-bleed isolation at this pressure rating, and a link to the last PTW executed on this line with outcome documentation.

The brief is delivered to the issuing engineer. Before the PTW is formally issued, the interface requires: (a) the engineer's acknowledgment of the brief content, and (b) the Shift Lead's digital signature confirming the isolation strategy has been reviewed. Both acknowledgments are cryptographically logged with the complete evidence lineage. The engineer makes the call on PG-18 — they may send someone to physically verify the device state before proceeding. Kairos provided the knowledge. The human authority made the decision and retained the accountability.

---

### Flow C: Document Ingestion — OEM Bulletin Revises Pressure Limit

A revised OEM service bulletin arrives for a class of heat exchangers covering maximum operating pressure.

The document enters the immutable vault unchanged (SHA-256 hashed, timestamped). The perception engine parses it: OCR over the PDF, entity extraction identifies the affected equipment class and the specific pressure parameter, extraction produces a candidate fact: "Maximum operating pressure for HE-3xx series: [new value] kPa (revised from [old value] kPa, effective [date])."

The governance layer maps this against the temporal graph. It finds: an existing edge for this equipment class with a pressure limit of [old value] from a previous OEM bulletin (Level 3 authority). The new bulletin is also Level 3 authority, but more recent. Conflict detected: this is a parameter change — structural engineering conflict track.

Blast-radius analysis: which other graph elements reference this pressure limit? The system finds: 4 site operating procedures that specify operating ranges up to the old limit, 2 inspection records that reference the old specification, and 1 maintenance procedure that includes a hydrotest at 110% of operating pressure. All 6 are flagged for review. MoC auto-draft is generated identifying the conflict, both sources, and the blast-radius list. The draft enters the plant's SAP MoC workflow.

Until the MoC is signed: every query touching the affected equipment's pressure limit displays a warning banner identifying the pending MoC. Both values are shown, authority levels and dates are explicit, and the resolution status is live-linked. Operations continue safely under caution.

When the Chief Engineer signs the MoC, a webhook fires to Kairos. The temporal graph closes the validity window on the old pressure limit edge and promotes the new one to verified canonical status. The warning banners across all 6 affected elements are cleared. The blast-radius review items are marked resolved. The audit trail captures the complete chain from document arrival to canonical update, including who made every decision and when.

---

### Flow D: Expert Elicitation — Retiring Engineer Knowledge Transfer

A senior reliability engineer announces retirement in 3 months. The system identifies her as a high-knowledge-density individual: she has been the primary author or reviewer on 847 work orders over 22 years, with concentrated expertise on the site's critical multi-stage production units — complex, failure-prone systems with poor knowledge coverage in the current graph.

The elicitation engine initiates an off-boarding interview series. Over the next 10 weeks, it schedules 6 sessions of 20 minutes each, each focused on a specific failure mode family where the graph has low coverage and her historical work orders show high authority. Sessions are conducted through the desktop interface with voice input option. Each session presents: the current state of graph knowledge on the topic ("here's what we know"), the specific gaps ("here's what we don't know and what's most valuable"), and targeted questions generated from both. Questions are not generic. They are specific and graph-derived — for example: "This asset class has experienced 4 critical failures in the past 12 years. The documented root cause in 3 of those cases was process feed variation. The 4th (2019) was attributed to temperature excursion. Do you believe the 2019 attribution was accurate, or is there an alternative explanation you observed at the time?"

Her responses enter the quarantine layer with session context, linked to specific equipment and failure modes. The reliability engineering team reviews and promotes over the following weeks. By her retirement date, her operational knowledge — the part that lived only in her head — is in the graph, verified, attributed to her, and available to every technician who will ever work on those assets after she leaves.

---

## 5. Full Feature Set with Reasoning

**Asset-centric truth model — not document-centric, not query-centric**
Every piece of knowledge in the system orbits a canonical asset node. Users think in equipment, lines, systems, and facilities — not in document types or folder structures. Organizing knowledge by asset makes the system intuitive to industrial practitioners and ensures that all knowledge about a piece of equipment is discoverable regardless of its original document format or source system.

**MDM-backed deterministic identity bootstrap**
AI identity inference from messy historical documents is statistically reliable in aggregate and catastrophically wrong in specific cases. In industrial operations, a specific case where a maintenance procedure is linked to the wrong asset can mean performing the wrong procedure on the wrong equipment. The MDM bootstrap eliminates this risk by requiring deterministic human confirmation before any AI-inferred identity is treated as canonical.

**Immutable, cryptographically anchored evidence vault**
Industrial operations are subject to regulatory audit, legal discovery, and safety investigation. An evidence base that can be modified after the fact is not a defensible operational record. Immutability is a legal and safety requirement, not a technical preference.

**Five-level authority hierarchy on every knowledge edge**
Industrial decision-making is structured around engineering authority. A regulatory requirement is not equal to a field observation, regardless of which is more recent. Encoding authority hierarchy into the graph ensures that answer synthesis reflects the actual governance structure of industrial operations rather than flattening all sources to equivalent status.

**Blast-radius analysis on source supersession**
The most dangerous form of knowledge degradation in industrial systems is silent — outdated information persisting in downstream references long after the source document was revised. Blast-radius analysis makes knowledge decay visible and actionable.

**Dual-track conflict governance**
Single-track conflict handling creates bureaucratic paralysis when every formatting inconsistency triggers a formal MoC, and creates safety risk when safety-critical contradictions are handled with the same lightweight process as administrative mismatches. Dual-track classification applies the right governance process to the right class of conflict.

**SPC-based adaptive circuit breaker**
Static thresholds applied to a system operating across brownfield deployments of widely varying data maturity are operationally brittle. SPC-based control charts adapt to the deployment's actual operating conditions rather than enforcing a universal threshold that is wrong for every deployment at some phase.

**Temporal validity with time-travel query capability**
Industrial investigations are inherently historical. An RCA for an incident that occurred 6 months ago requires knowing what procedures and knowledge were in effect at the time — not the current state, which may have been updated in response to the very incident being investigated. The temporal graph's validity windows and the vault's immutable record enable accurate historical reconstruction.

**Zero-copy OT virtualization**
Historian data is time-series data operating at fundamentally different scales and with fundamentally different operational requirements than documentary knowledge. Conflating the two architectures collapses both. Virtualization gives Kairos access to operational context without inheriting the operational complexity of historian infrastructure.

**Proactive event-driven delivery via operational event subscription**
The core feature. Without this, Kairos is a sophisticated retrieval system. With this, it is an operational intelligence platform. The distinction is not incremental — it is categorical.

**PTW-specific safety briefs with mandatory sign-off**
Permit-to-Work is the highest-leverage safety moment in industrial field operations. Every PTW represents a decision that, if made with incomplete information, has the potential for a serious safety incident. Delivering a knowledge-backed brief at the moment of PTW issuance, with mandatory acknowledgment from both the issuing engineer and the Shift Lead, maximizes the probability that the most relevant organizational knowledge is considered before work begins.

**Shift handover knowledge delivery**
Shift handovers are the moment when operational awareness transfers between crews. The outgoing shift knows what happened during their watch. The incoming shift needs to inherit that awareness plus the knowledge context for what they're about to face. Kairos delivers this as a structured briefing rather than depending on informal verbal communication.

**Multi-script and multilingual perception**
In Indian industrial deployments, English-only document processing means losing a significant fraction of the operational knowledge captured in maintenance forms, shift logs, and inspection records. Supporting Hindi, Hinglish, and mixed-script documents is not an edge case feature — it is a core capability for the stated deployment context.

**Context-derived micro-interview elicitation**
Generic knowledge capture prompts produce generic, unhelpful responses. Questions generated from specific graph gaps about specific equipment produce specific, operationally valuable answers. The difference between "what did you learn from this repair?" and "did the bearing housing show signs of thermal cycling beyond what the temperature records show, and if so, at what stage of the failure progression?" is the difference between anecdote and operational intelligence.

**Telemetry-grounded causal attribution**
Naive feedback learning from recurrence data degrades a knowledge system over time by penalizing correct recommendations for failures that were counterfactual, execution-related, or coincidental. Telemetry-grounded attribution provides the causal evidence needed to distinguish these cases and update confidence only where the update is warranted.

**Phased trust-building deployment architecture**
Trust in an AI system in a safety-critical industrial environment is earned through demonstrated accuracy over time, not claimed on day one. The phased deployment structure — retrieval mode, assisted mode, proactive mode — maps the system's increasing autonomy to the trust that has been earned through demonstrated performance. This is not a product decision. It is an organizational change management necessity.

**Layer 0 rolling validation gate**
Model updates that degrade performance on production data are more dangerous than no update at all. The rolling validation corpus, built from verified operational data rather than curated examples, ensures that the validation environment stays relevant to actual deployment conditions as the site's equipment profile and document corpus evolve.

**Compliance intelligence as audit-preparation acceleration**
Kairos accelerates audit preparation by continuously mapping the facility's applicable regulatory requirements against current procedures, equipment states, and inspection records — identifying gaps, organizing evidence by regulatory clause, and pre-populating the documentation auditors require for desk review. The regulatory framework is configured per deployment: process industries map against OISD, PESO, and the Factories Act; pharmaceutical manufacturers against FDA 21 CFR Part 11 and Schedule M; power utilities against CEA and IEC standards; food manufacturers against FSSAI and ISO 22000; any sector against its applicable ISO management system standards. The compliance intelligence is sector-configurable, not sector-specific.

**Environmental compliance is the one regime whose evidence is telemetry, not documents.** Environmental norms — CPCB consent-to-operate conditions, MoEF&CC notifications, state pollution control board limits, and the ISO 14001 management system — are configured per deployment like any other framework. They verify differently, and that difference is structural rather than a matter of adding another clause set.

Every other regime above is satisfied by an artifact: a procedure exists, an inspection is current, a calibration certificate is on file. A consent condition is satisfied by a *continuous measured value staying inside a limit* — stack emissions, effluent parameters, ambient monitoring — reported to the regulator on a fixed cycle. The compliance question is not "is the document present" but "did this parameter breach its consented limit, for how long, and was the excursion reported".

This maps onto Layer 5 rather than requiring new machinery. Consent limits are regulatory clauses at Level 1 authority, held in the graph like any other requirement; the measured values stay in the historian and are queried ephemerally. A consent condition therefore becomes a clause whose evidence is a bounded historian query rather than a document link, and an excursion becomes an operational event with a reporting deadline attached — which is exactly the shape Layer 8 already delivers on. The instrumentation coverage map governs it honestly: a consent parameter with no instrument backing it is an unverifiable clause and must be reported as such, never cleared. Environmental compliance is where the false-negative controls below matter most, because an unreported excursion is a prosecutable offence rather than an audit finding.

The honest scope of this claim: most regulatory audits combine desk review with physical field inspection and mandatory human SME sign-off. Kairos can credibly reduce audit desk-preparation time; it cannot generate a compliant evidence package without human verification and field confirmation. The feature is positioned as audit-preparation acceleration with mandatory human sign-off, not automated compliance.

The specific design risk in AI compliance intelligence is the false negative: a real compliance gap that the system fails to flag. False positives (spuriously flagged non-gaps) are an operational nuisance; false negatives are a safety and legal liability, because violations persist undetected until a regulator or incident surfaces them. The compliance intelligence module is designed with explicit false-negative controls: high-recall retrieval that errs toward flagging rather than clearing, mandatory human review of all compliance clearances for safety-critical regulatory requirements, and data-quality gates that block compliance clearances when the underlying evidence base is below the confidence threshold.

**EEMUA 191 / ISA-18.2 trigger governance**
The proactive push architecture is only valuable if it does not contribute to the very problem it is solving. Notification overload — alarm fatigue — is the most thoroughly documented failure mode in process industry safety operations. Kairos's trigger governance subsystem enforces the EEMUA 191 benchmark of ≤6 push events per operator per hour in normal operation, with a priority queue, state-based suppression during abnormal operating periods, cool-down windows per asset, and a pilot monitoring gate that must be satisfied before Phase 3 activates. This makes proactive delivery safe rather than just possible.

**Active Learning Annotation Interface**
Kairos converts normal Phase 1 search usage into annotation activity: low-confidence entity extractions surface inline in search results with one-tap correction for operators. Every correction is stored in `ner_annotations` and linked to the relevant quarantine item, accumulating a facility-specific labeled dataset as a byproduct of normal search usage — no separate annotation project required. By the time synthesis activates in Phase 2, the annotation corpus reflects the facility's own document vocabulary and entity patterns.

**PII redaction pipeline for cross-site knowledge promotion**
Cross-site pattern detection requires knowledge to flow from local data planes to the central control plane. Shift handovers, incident reports, and elicitation responses contain personnel data that labor agreements and India's Digital Personal Data Protection Act 2023 prohibit from crossing facility boundaries without anonymization. The PII redaction pipeline strips names, shift identifiers, and personal attributes before any knowledge edge is promoted cross-site, ensuring that only the sanitized technical pattern reaches sister facilities.

---

## 6. Tech Stack

### Storage

| Layer | Tool | Notes |
|-------|------|-------|
| Document vault | **Supabase Storage** | S3-compatible, free tier, stores all original files immutably |
| Relational DB | **Supabase PostgreSQL** | Auth, workflows, review queues, audit logs — all in one |
| Knowledge graph | **Neo4j 5.20** | Cloud (Neo4j Aura); property graph with Cypher. Local `kairos-neo4j` profile-gated for dev/test |
| Vector search | **Qdrant** | Cloud (Qdrant Cloud); payload filtering handles keyword needs alongside semantic search. Local `kairos-qdrant` profile-gated |
| Exact search | **Elasticsearch** (Docker) | Tag numbers, clause references, document ID lookup |
| Cache | **Redis** (Docker) | Hot asset views, brief delivery, event streaming via Redis Streams |

---

### AI and Models

| What | Tool | Notes |
|------|------|-------|
| Cloud LLM synthesis | **NVIDIA NIM** | Nemotron 3 Super 120B (`nvidia/nemotron-3-super-120b-a12b`), OpenAI-compatible API. Cascade: **NIM → OpenRouter → Gemini → Ollama**. The tiers are redundancy across different failure modes (NIM: free, largest token budget; OpenRouter: `llama-3.1-70b`, a different model since NVIDIA retired it as tier 1 in 2026-09; Gemini: fast, different model family). Any fallthrough is a different model, so the benchmark verdict flags it |
| Local LLM fallback | **Ollama** | Qwen2.5 14B — edge/offline synthesis fallback |
| OCR | **NVIDIA NIM Nemotron-OCR-v2** | Cloud API; PyMuPDF fast path for native digital PDFs |
| Named entity recognition | **NVIDIA NIM llama-3.2-11b-vision** | JSON-prompted NER; Ollama llama3.1:8b local fallback; regex last resort |
| Embeddings | **Jina AI** (`jina-embeddings-v3`) | Cloud API, 1024-dim; Ollama nomic-embed-text fallback |
| Voice transcription | **Groq API** (`whisper-large-v3`) | Cloud API, no local model |
| Engineering drawing parser | **Cloud VLM** (NIM `llama-3.2-11b-vision-instruct`) now; **YOLOv9 + LayoutLMv3** later | Path B (cloud vision → topology JSON) implemented in `pid.py`; Path A (custom GPU models) is the future upgrade once a labeled P&ID dataset exists |

---

### Backend

| What | Tool | Notes |
|------|------|-------|
| Primary API | **FastAPI** (Python) | Async, ML-native, handles retrieval and synthesis orchestration |
| High-throughput connectors | **Go** | OT federation, ingestion at volume, low-latency APIs |
| Async task processing | **Celery + Redis** | Document processing pipelines, extraction jobs |
| Durable workflow engine | **Temporal.io** (Docker) | Long-running pipelines that survive crashes and resume — critical for ingestion reliability |

Temporal runs as a single Docker container. Worth the setup — document extraction pipelines that fail midway and need to resume cleanly are a real problem, not a hypothetical one.

---

### Orchestration and Events

| What | Tool | Notes |
|------|------|-------|
| Event streaming | **Redis Streams** | Already in the stack via Redis — handles work order, PTW, shift handover events cleanly at MVP scale |
| Production event backbone (architecture story) | **Redpanda** | Kafka-compatible, single binary, no JVM — reference in the architecture diagram for enterprise scale |

Redis Streams is the pragmatic choice for the build. Redpanda is the honest story for what this becomes at enterprise scale — show it in the architecture, reference it in the presentation, don't spend time setting it up for the demo.

---

### Security and Governance

| What | Tool | Notes |
|------|------|-------|
| Auth and row-level security | **Supabase Auth** | Built-in JWT (**ES256**, asymmetric — one verifier, `dependencies.resolve_token`; a hand-rolled HS256 decode silently rejects every real token and degrades authz to the dev bypass). Site scope is derived from the verified token, never a query parameter, and a blank site resolves to *no* rows rather than all rows |
| Policy enforcement | **Open Policy Agent** (Docker) | Governance rules in Rego. **Fails closed** — an unreachable OPA denies rather than allows. Reads are gated as well as writes, so every sensitive `read_*` action must also be registered in the sensitive-action list or the catch-all re-grants it to every role. `OPTIONS` is never gated: this middleware is outermost and a CORS preflight carries no token. Read grants mirror the frontend's role map — a role that can open a page but cannot call its API is a broken page, not a closed boundary |
| Secrets management | **Supabase Vault** (cloud) | Encrypted secrets in Supabase; no local Vault container |
| Observability | **OpenTelemetry → Grafana Cloud** | Backend exports traces/metrics directly to Grafana Cloud; no local otel-collector/Tempo/Grafana containers |

OPA runs as a single Docker container and makes the governance story credible. Secrets live in Supabase Vault (cloud) and observability ships to Grafana Cloud — the former local Vault / Grafana / OTEL-collector containers were removed.

---

### Frontend

| What | Tool | Notes |
|------|------|-------|
| Web and desktop interfaces | **Next.js 16 + React 19** | App Router, server components, TypeScript strict |
| Mobile field app | **Responsive Next.js** (MVP) | Same codebase, mobile-first field routes; Expo + React Native is the future native-app option |
| UI components | **Custom primitives (`ui.tsx`) + Tailwind CSS v4** | Design-token driven; no component-library dependency |
| Graph visualisation | **React Flow** | Renders the graph from JSON returned by the API (Neovis.js was the alternative) |

---

### Local Infrastructure — One Docker Compose

Everything self-hosted runs from a single `docker-compose.yml`:

```
services (default, 12): frontend, backend-api, backend-go,
                        celery-worker, temporal-activity-worker, elicitation-worker,
                        elasticsearch, redis, temporal, temporal-ui, temporal-postgres, opa

--profile local-stores: neo4j, qdrant   # cloud by default; local only for offline dev / tests
--profile prod:         caddy           # TLS reverse proxy, not started in dev
# neo4j + qdrant   → cloud by default; local containers are profile-gated (--profile local-stores)
# vault / grafana / tempo / otel-collector → removed (Supabase Vault + Grafana Cloud)
```

One command starts the entire local stack. Agents generate this file in minutes.

---

### What to Build vs What to Mock

**Build fully:**
- Document upload → NIM OCR (PyMuPDF fast path for digital PDFs) → NIM NER → Neo4j graph → Qdrant vectors
- Hybrid retrieval + NVIDIA NIM synthesis with source citations
- Work order event → proactive brief → mobile delivery
- Supabase auth with role-based access
- Compliance gap detection against a configured regulatory framework

**Mock or simulate for demo:**
- YOLOv9 custom drawing parser (show architecture, use simplified pre-processed topology)
- EEMUA 191 governor (implement rate limiting logic, mock the DCS state feed)
- Cross-site control plane (single-site for MVP, show multi-site in architecture diagram)
- MoC webhook loop (manual approval UI stands in for the full webhook cycle)

---

### Build Priority — Four Weeks

| Week | Focus |
|------|-------|
| **Week 1** | Supabase + ingestion pipeline — upload, OCR, NER, Neo4j graph, Qdrant vectors |
| **Week 2** | Query interface + NIM synthesis + compliance gap detection + Next.js frontend |
| **Week 3** | Redis Streams event system + proactive brief engine + auth + mobile-responsive UI |
| **Week 4** | Demo polish + Grafana dashboard + architecture diagram + presentation + demo video |



---

## 7. Scalability: Day One to Enterprise Scale

### Days 1 to 30: Brownfield Entry and Immediate Value

Kairos enters with the MDM import. The asset skeleton is established. The immutable vault begins receiving documents from the first connected source system — typically the document management system or a file share. No graph synthesis runs yet.

Value delivered immediately: a single search interface over all ingested documents, with multilingual support, returning results ranked by recency and authority. For a plant operating across 7 to 12 disconnected document systems, this alone eliminates the majority of the time spent hunting for documents. The perception engine runs asynchronously, building its extraction outputs in the background. Workers experience faster document discovery from day one without waiting for a complete knowledge graph.

Infrastructure footprint at this phase: modest. Three Kubernetes nodes handle the vault, search index, vector store, and API layer. Redis Streams handles the ingestion stream. Neo4j is provisioned but sparsely populated.

### Days 31 to 60: Entity Mapping and Asset-Centric Organization

Multi-script entity extraction has processed the majority of ingested documents. Tag alias resolution has mapped the known naming variants to canonical asset IDs. Documents are now navigable by asset — a technician searching for Pump P-101 gets all documents that reference P-101 in any of its known naming variants, organized by document type and date.

The temporal graph begins populating with high-confidence extracted facts from verified source types (OEM manuals, regulatory documents, currently approved procedures). The quarantine layer begins receiving lower-confidence extractions for human review. The governance plane is active: conflicts are being detected and classified.

Infrastructure scales: additional Kubernetes nodes for the graph and the extraction pipeline. Human review capacity for the governance queue requires two to three dedicated hours per week from a reliability engineer or document control specialist — a minimal investment for the organizational benefit.

### Days 61 to 90: Active Knowledge Graph and Phase 2 Transition

P&ID topology extraction has completed for the facility's core engineering drawings. The spatial relationship model of the plant is resident in the graph, pending element-by-element engineer verification for safety-critical topology. The temporal graph is now populated with high-confidence canonical facts for core asset classes.

The phased deployment gate moves from Phase 1 (retrieval only) to Phase 2 (human-in-the-loop assisted synthesis). Workers have 60 days of experience with Kairos as a reliable retrieval tool, which is the foundation for trust in its synthesis outputs. Synthesized query answers activate. The elicitation engine activates for complex work orders. The governance workflow for conflicts is fully operational.

The proactive delivery layer does not activate at this phase. Layer 8's trigger governance pilot — which requires push volume to stay within EEMUA 191 norms for 30 consecutive operating days — must be completed before Phase 3 (governed proactive mode) is enabled. This pilot runs during Phase 2, typically completing during months 4 to 5, enabling Phase 3 to activate at month 6 for deployments where push volume meets the gate criteria.

### Multi-Site Scale

The control plane / data plane architecture enables consistent multi-site deployment without coupling individual plants together in ways that create data sovereignty or latency problems.

The control plane (deployed centrally, either cloud or corporate data center) manages: enterprise-wide IAM and RBAC, cross-site ontology governance (ensuring that "P-101 at Site A" and "P-101 at Site B" are correctly identified as different assets despite identical nomenclature), cross-site failure pattern detection (a failure mode identified at Plant A generates a proactive advisory for Plant B with similar equipment operating under similar conditions), regulatory intelligence updates (new regulatory requirements propagate to all affected sites), and Layer 0 validation governance (model updates are validated once centrally before deploying to all sites).

Each plant's data plane manages: its own temporal graph, its own vault, its own OT connectors, and its own user-facing services. Data does not leave the plant's data plane without explicit cross-site sharing authorization. Sub-second query latency is maintained because the knowledge most relevant to a specific plant is co-located with that plant's services.

Cross-site pattern detection is the most significant enterprise-scale feature. Failure modes, near-misses, and regulatory gaps identified at one site are automatically evaluated for relevance to equivalent equipment at all other sites. The proactive delivery layer at a receiving site surfaces the pattern with explicit attribution to the originating site and original incident, allowing the receiving site to make an informed decision about relevance to their specific conditions.

**External industry failure databases — the same mechanism, a different boundary.** Sector-wide incident and advisory sources (regulatory incident registers, OEM safety bulletin feeds, industry association failure databases) are the natural extension of cross-site detection: a failure mode confirmed at another operator's facility is evidence about your equipment class in exactly the way a failure at a sister site is.

Architecturally this needs nothing new. Such a feed enters through the same path as any other source — into the immutable vault, through the perception engine, onto the graph as claims carrying the same six edge properties, at an authority level assigned to that source. A regulatory incident register sits high in the hierarchy; an unattributed industry forum post would sit at Level 5 or go to quarantine. The authority hierarchy is what makes mixed-provenance evidence safe to hold together, and it already exists.

What blocks it is not architecture. It is licensing and redistribution terms, per-source schema mapping with no common standard across them, and the fact that an external claim about "a pump of this class" cannot be linked to a canonical asset without the alias resolution and human confirmation that Layer 1 requires — an external advisory is evidence about an equipment *class*, not about your specific tag, and collapsing that distinction is the failure mode to avoid. External sources are therefore out of scope for this build and are an integration decision per deployment, not a platform capability gap.

**Data Sanitization and PII Redaction Pipeline — mandatory for cross-site promotion.** Shift handover notes, incident reports, elicitation interview responses, and work order closeout records routinely contain personally identifiable information: technician names, shift identifiers, contractor details, and performance-related observations ("operator over-torqued the valve"). India's Digital Personal Data Protection Act 2023, corporate labor agreements, and standard union contracts prohibit transferring this class of information across facility boundaries or corporate networks without explicit anonymization. Any knowledge edge promoted from a local data plane to the control plane for cross-site sharing must first pass through a redaction pipeline that strips all PII before the pattern is transmitted.

The redaction pipeline operates as follows: before any cross-site promotion, a PII detection classifier identifies spans containing names, role identifiers, shift codes, and other personal attributes in the knowledge fragment to be shared. Identified spans are replaced with role-generalized tokens ("Maintenance Technician [REDACTED]", "Shift [REDACTED]"). Only the technical failure pattern — the equipment class, failure mode, operational conditions, and corrective action — crosses the site boundary. The originating facility retains the full unredacted record locally. The receiving site's control plane receives only the sanitized technical pattern. This architecture means that cross-site knowledge transfer is institutionally useful without creating a cross-facility surveillance system or privacy compliance liability. All redaction operations are logged and auditable.

**The primary scaling engineering challenge: temporal graph query performance.** Production experience with Neo4j temporal graphs at enterprise scale has demonstrated that naive validity-window versioning, without deliberate query optimization, can produce catastrophic performance degradation. Time-bounded queries with authority-level filtering and multi-hop traversal on a graph with tens of millions of nodes are expensive operations. The performance engineering workstream for the temporal graph is not optional and must begin in the Days 31-60 phase, not as a late-stage hardening activity. Specific requirements: composite indices on (asset_id, valid_from, valid_to) for all high-frequency query patterns; traversal depth limits enforced by query policy; authority-level pre-filtering applied before relationship traversal, not after; hot asset view precomputation via Redis for the most frequently queried equipment; and query performance regression testing as part of the Layer 0 validation gate for graph schema changes.

### Air-Gapped and Edge Deployment

For facilities with strict data sovereignty requirements or no reliable external connectivity, Kairos deploys entirely within the plant's network perimeter. The full data plane deploys on bare-metal Kubernetes. OCR, entity extraction, and P&ID parsing run on plant-local GPU infrastructure unquantized. The synthesis LLM deploys as quantized Llama 3.1 70B or Qwen 3 for text synthesis over structured inputs. Performance characteristics are within acceptable operating bounds for synthesis tasks because the LLM is receiving structured JSON from the graph, not raw documents.

Control plane connectivity synchronizes on a scheduled basis when network connectivity is available, pushing model updates (validated against Layer 0 before sync) and receiving cross-site pattern updates. If connectivity is severed for extended periods, the plant data plane continues operating fully. No operational dependency on external connectivity.

---

## 8. Edge Cases and Failure Handling

**MDM is incomplete or has wrong data**
The deterministic human bootstrap flow is invoked before any AI linking is permitted for the affected asset. Operations continue for correctly identified assets. The incomplete portion of the knowledge base is clearly labeled as pending identity resolution, not absent. No fabricated identity is ever inserted.

**Conflicting OEM manuals for the same equipment**
Dual-track governance classifies parameter conflicts as structural engineering (MoC required). Informational conflicts as administrative (lightweight review). Both versions are preserved in the vault with explicit validity windows. The query layer presents both with authority levels, dates, and the pending resolution status. The system does not choose between them — it shows the conflict clearly and escalates for human resolution.

**Stale or superseded documents retrieved in queries**
Every document's status (active, superseded, archived) is a first-class graph property. Retrieval queries filter on status by default. Superseded documents appear only when: the user explicitly requests historical context, a time-travel query specifies a date when the document was active, or the system's blast-radius analysis identifies that the document is referenced by a still-active downstream fact (triggering a separate review). Superseded documents never appear in default query results as if they were current.

**Poor quality scans or handwritten documents below confidence threshold**
The perception engine routes low-confidence extractions to human review before they touch the canonical graph. The original artifact remains in the vault regardless of extraction quality. Query interfaces can surface the original artifact directly when extraction quality is insufficient for structured retrieval. A human reviewer can manually confirm or correct extractions, and those confirmations are logged with the reviewer's identity.

**LLM synthesis layer is unavailable**
The retrieval layer — exact match, semantic vector, and graph traversal — continues operating independently of the synthesis layer. Users receive retrieval results with source documents rather than synthesized answers. The proactive brief delivery layer switches to a simplified mode: raw retrieval results for the queried asset context are delivered rather than synthesized briefs. Plant operations are never completely blinded.

**OT historian is unavailable**
Document-based answers continue without the telemetry context. Every query or brief that would normally include OT data displays an explicit notice: "Live telemetry is unavailable — the following analysis is based on documented history only." The outcome attribution system pauses telemetry-grounded attribution for the affected equipment during the outage and resumes automatically when historian connectivity restores.

**MoC backlog grows faster than it is resolved**
Warning banners persist on all affected facts until resolution. Operations continue safely with explicit acknowledgment that certain facts are under pending review. The governance dashboard surfaces backlog volume, aging, and overdue cases to the appropriate escalation authority. The system does not silently allow contested facts to be treated as canonical simply because the MoC queue is full.

**A physically undocumented modification is discovered in the field**
A field technician discovers that a valve was replaced with a different type than what the P&ID shows. They raise a Physical Deviation flag through the mobile app. This immediately freezes all downstream automated workflows that depend on the topological path through that valve — PTW briefs that reference that isolation point, compliance checks that depend on that valve's specification, and maintenance briefs that reference adjacent equipment through that topology. The freeze persists until a site engineer surveys the actual plant state and either confirms the P&ID or raises a formal MoC to update it.

**Senior expert refuses to participate in elicitation**
Elicitation is not mandatory. The system tracks participation rates by department and individual as an organizational metric reported to operations leadership — not to coerce individuals but to identify where the knowledge transfer program needs support or incentive design. The knowledge gap for non-participating experts is explicitly surfaced in the knowledge coverage dashboard rather than hidden.

**Multi-site cross-site knowledge conflict (Plant A's procedure contradicts Plant B's for the same equipment class)**
Cross-site conflicts do not trigger a single MoC. Each site's knowledge governance is independent. The control plane flags the cross-site discrepancy to both sites' engineering authorities for independent review. Either site may update their procedure, or both may confirm that site-specific conditions justify the difference. The cross-site discrepancy is documented in both sites' knowledge bases regardless of resolution outcome.

**Attempted injection of false knowledge through field elicitation**
Elicitation responses enter the quarantine layer. They do not become canonical without human domain expert review. Quarantined items are searchable with explicit non-canonical labeling. A deliberately false elicitation response can cause confusion at the quarantine layer — it cannot corrupt the canonical graph without human promotion. The review workflow ensures that elicitation outputs from the same individual that are repeatedly inconsistent with canonical facts are flagged for the reviewer's attention.

**Gradual model drift as the extraction LLM's performance degrades on new document types**
The SPC circuit breaker per asset class catches this before it propagates widely. Layer 0 rolling validation catches it at the model update gate. The combination means drift is detected and contained: either at the point of a model update (prevented from deploying) or during production operation (circuit breaker halts extraction for the drifting class and routes to human review).

**Adversarial data poisoning through document ingestion or model supply-chain**
A sophisticated attacker targeting a high-value industrial facility could attempt to corrupt the knowledge base by submitting documents containing subtly falsified parameters — a revised operating procedure with an incorrect pressure limit, an OEM bulletin with a modified inspection interval — designed to pass human review and enter the canonical graph. A second vector is model supply-chain compromise: a maliciously modified extraction model or LLM weight file introduced during an update.

The architecture's existing safeguards address much of this: the immutable vault preserves originals so falsified parameters can be identified if the underlying document is inspected, the human promotion workflow requires engineering sign-off for safety-critical parameters, and Layer 0 validates model updates against the rolling corpus before deployment. Additional mitigations that should be implemented: cryptographic signing of all model weight files at source, anomaly detection over extraction outputs flagging parameters that deviate significantly from historical distributions for a given equipment class (a pressure limit that is 40% above or below the existing canonical value should trigger automatic review regardless of source authority), and audit monitoring for unusual patterns of document submission from specific source accounts. The system cannot guarantee immunity from a sophisticated insider threat with engineering authority, but it can ensure that any successful poisoning leaves a complete audit trail that enables detection and rollback.
---

## 9. Measured Performance

The layers above describe intent. This section names the instrument that tests it, so the architecture
is falsifiable rather than merely asserted.

Thirteen harnesses run against the live stack — one per row below; results, methodology and caveats are recorded in
[`benchmark/RESULTS.md`](../benchmark/RESULTS.md) and [`docs/BENCHMARKS.md`](BENCHMARKS.md). Grading is
deterministic — required-fact matching with negation and provenance checks — never an LLM judging
another LLM's output, because a model scoring its own family's answers measures agreement, not
correctness.

| Harness | What it establishes |
|---|---|
| `verify_layers.py` | Every layer reachable end to end, with per-layer latency |
| `run_benchmark.py` | Answer quality over a 46-question domain-expert set: does the answer state the correct fact, un-negated, with sources |
| `run_retrieval_baseline.py` | Reach per retrieval arm — exact, semantic, hybrid — isolating what each contributes |
| `run_model_validation.py` | Layer 0 entity-extraction precision/recall/F1 per entity type and per asset class |
| `run_compliance_eval.py` | Compliance gap detection precision and recall against labelled clause-asset pairs |
| `run_safety_eval.py` | Adversarial safety: whether the Layer 11 refusal gate holds under questions designed to extract an unsourced safety parameter |
| `run_brief_eval.py` | Proactive brief structure and content against per-event-type expectations |
| `run_time_to_answer.py` | Time to a *trusted* answer versus BM25 keyword search, counting documents opened before the fact is found |
| `run_load_test.py` | Concurrency knee and error rate under a virtual-user sweep |
| `run_soak_test.py` | Memory and connection-pool behaviour over hours, including idle-connection recovery |
| `run_ocr_gate.py` | OCR recall of operationally salient tokens — asset tags, measurements with units, standards references, dates — against the clean sibling documents the dataset manifest pairs them with |
| `run_kg_completeness.py` | Linkage completeness: the fraction of active vault documents whose knowledge is reachable in the graph, with the unlinked remainder classified rather than left as a percentage |
| `run_cross_functional.py` | Cross-functional discovery as a counterfactual — full-corpus retrieval against retrieval restricted to one function's documents, over the same 37 questions |

Three conventions make the numbers readable rather than decorative. Every run states a **validity
verdict** — a run that fell through to a different model tier is marked suspect rather than reported as
clean, so an exhausted quota can never be read as poor answer quality. Every proportion carries a
**Wilson confidence interval**, because 33 of 37 is not a percentage, it is a small sample. And
**regressions are published, not re-baselined**: the measured time-to-answer advantage fell from 25.6%
to 9.5% across two runs, and the file records the fall and its two causes rather than quietly restating
the better figure.

The binding limit on all of it is corpus size. These figures characterise the golden dataset, not a
production archive: on a 20-document corpus BM25 already finds the answer at rank 1.35, which caps how
much retrieval can win, and RRF scores barely discriminate across hits. The harnesses are built to be
re-run as the corpus grows — the numbers are a floor established under measurement, not a claim about
scale.
