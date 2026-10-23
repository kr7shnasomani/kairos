"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { dmSans, instrumentSans } from "./landing-fonts";
import { youTubeId } from "@/lib/youtube";
import { HeroVisual } from "./_landing/hero-visual";
import { AssetsMock, BriefsMock, ComplianceMock, CopilotMock, FieldMock, GovernanceMock, IngestionMock, RcaMock } from "./_landing/mocks";
import { GithubIcon, TechLogo, YoutubeIcon, techStack } from "./_landing/tech";

/**
 * Demo recording.
 *
 * Put a YouTube link in `DEMO_YOUTUBE_URL` — watch, youtu.be, /embed/ or /shorts/
 * form, all parse — and the player section appears on the page, the header grows a
 * "Demo" cell, and the hero CTA scrolls to it instead of leaving the site. Leave it
 * empty and none of that renders: the CTA falls back to `DEMO_FALLBACK_URL` and the
 * page is exactly as it is today. Nothing else needs editing either way.
 */
const DEMO_YOUTUBE_URL = "";
const DEMO_FALLBACK_URL = "https://drive.google.com/file/d/18ZO95MckNtESg-Z2ruRBNnKq6JyB57rP/view?usp=drive_link";

const demoVideoId = youTubeId(DEMO_YOUTUBE_URL);

// Every section on the page, in the order you meet them. The header is the only
// map a first-time reader gets, so a section missing from it is a section they
// never learn exists. Labels are the short form: eight cells have to share one row.
const navLinks = [
  ...(demoVideoId ? ([["Demo", "#demo"]] as const) : []),
  ["Problem", "#problem"],
  ["How it works", "#how"],
  ["Capabilities", "#capabilities"],
  ["System", "#system"],
  ["Use cases", "#field"],
  ["Evals", "#evidence"],
  ["Provenance", "#provenance"],
  ["FAQ", "#faq"],
  ["Docs", "/docs"],
] as const;

/**
 * The problem, in figures the industry already publishes. Every number is
 * attributed in-copy so a reader can go and check it rather than take it on
 * trust, which is the same standard the product itself is held to.
 */
const problemStats: { figure: string; label: string; body: string; source: string }[] = [
  {
    figure: "~20%",
    label: "of the working week",
    body: "Time the average interaction worker spends looking for internal information or tracking down a colleague who can help. A searchable record of knowledge can cut that search time by as much as 35%.",
    source: "McKinsey Global Institute, 2012",
  },
  {
    figure: "88%",
    label: "of Indian industrial businesses",
    body: "Have an unplanned outage at least once a month, against 69% globally.",
    source: "ABB Value of Reliability survey, 2023",
  },
  {
    figure: "~₹70 lakh",
    label: "per hour of unplanned downtime",
    body: "Roughly what an hour of unplanned downtime costs the typical Indian industrial business, against ₹1.03 crore globally.",
    source: "ABB Value of Reliability survey, 2023",
  },
  {
    figure: "2 in 3",
    label: "new energy-sector hires to 2035",
    body: "Will be needed just to replace workers who retire. Whatever they never wrote down leaves with them.",
    source: "IEA, World Energy Employment 2025",
  },
];

/**
 * One story, followed end to end. This is the highest-leverage explainer on the
 * page: a reader who skims everything else still leaves knowing what Kairos
 * does, because they watched it do one thing.
 */
const scenario: { tag: string; title: string; body: string }[] = [
  {
    tag: "The trigger",
    title: "A work order is raised on pump P-1101A",
    body: "A technician is assigned to a seal failure. Nobody searches for anything. Kairos sees the work order the moment it is created, and starts gathering what the person doing this job needs to know.",
  },
  {
    tag: "What it finds",
    title: "Four failures, a raised flow limit, an unlogged warning",
    body: "P-1101A has failed with a seal fault four times in 84 days. A vendor bulletin raised its minimum flow from 120 to 150 m³/h, and the flow before each failure was below both. A technician's voice note says the minimum-flow valve is not opening fully, and nobody has acted on it.",
  },
  {
    tag: "The check",
    title: "Each fact is ranked by who said it",
    body: "A regulation outranks a vendor manual, and a vendor manual outranks a local note. Nobody has verified the voice note, so Kairos labels it as unverified instead of mixing it in with established fact.",
  },
  {
    tag: "The delivery",
    title: "A brief reaches the technician before they walk out",
    body: "One screen on a phone shows the history, the flow limit that changed, the unverified warning, and a link to every source document behind it. They read it before they touch the pump, not after.",
  },
  {
    tag: "The refusal",
    title: "When the evidence is thin, it says so",
    body: "Ask a safety-critical question, such as a pressure limit or a torque value. If no authoritative source supports an answer, Kairos refuses and hands you the documents instead. A confident guess at that moment is more dangerous than no answer at all.",
  },
];

/**
 * Each capability drives the vertical tab list and a composite card: a gradient
 * media panel on top and a white text block underneath. Every capability gets
 * its OWN mock, because a shared template made the section read as one repeated card.
 */
const capabilities: {
  id: string;
  name: string;
  banner: string;
  Mock: () => React.JSX.Element;
  eyebrow: string;
  title: string;
  body: string;
}[] = [
  {
    id: "briefs",
    name: "Briefs",
    banner: "Six briefs an operator per hour, because an ignored brief is worse than no brief",
    Mock: BriefsMock,
    eyebrow: "Briefs",
    title: "Told before you ask, but never spammed",
    body: "Kairos sends you what you need to know before a job starts, and caps it at six an hour. Flood someone with notifications and they stop reading all of them. That is why plant alarm systems have a cap by standard (EEMUA-191). Permit-to-work briefs skip the cap, because safety work does not wait for a quota.",
  },
  {
    id: "copilot",
    name: "Expert copilot",
    banner: "Every answer arrives with its sources, its authority and its confidence",
    Mock: CopilotMock,
    eyebrow: "Expert copilot",
    title: "Answers that carry their evidence",
    body: "Ask in plain language and get back an answer with its sources attached, its authority ranked, and its confidence stated. If a safety-critical question has weak evidence behind it, you get an honest refusal instead of a vague answer.",
  },
  {
    id: "rca",
    name: "Root cause",
    banner: "Likely causes ranked by how much evidence backs them, each one traceable",
    Mock: RcaMock,
    eyebrow: "Maintenance intelligence",
    title: "Root cause, assembled from the record",
    body: "Kairos combines work order history, failure records, vendor manuals, inspection findings and live operating conditions into a ranked list of likely root causes. Each one comes with the documents behind it and a timeline of what actually happened, so it connects facts that no single person on the team holds.",
  },
  {
    id: "compliance",
    name: "Compliance",
    banner: "Precision 1.000 across 52 clause-and-asset pairs, zero false positives",
    Mock: ComplianceMock,
    eyebrow: "Quality and regulatory",
    title: "Gaps found before the auditor finds them",
    body: "The demo loads twelve clauses from OISD-117 and ISO 45001, and seven more are named in the framework catalogue and need their clauses loaded, among them PESO, CEA, IEC 62443 and FDA 21 CFR Part 11. Kairos checks them continuously against current procedures, equipment state and inspection records. Every finding is tied to one clause: a gap means no document of the type that clause requires is linked to that asset. You can export an audit evidence pack at any time.",
  },
  {
    id: "ingestion",
    name: "Ingestion",
    banner: "A drawing is read for its layout, not flattened into plain text",
    Mock: IngestionMock,
    eyebrow: "Universal ingestion",
    title: "Every format a plant actually has",
    body: "Native PDFs, scanned forms, handwritten margin notes, spreadsheets, P&ID drawings and voice notes all go through one pipeline. Drawings are read by a vision model rather than OCR, because OCR throws away the layout, and the layout is the real content of a drawing. It is what tells you which valve isolates which pump.",
  },
  {
    id: "assets",
    name: "Assets",
    banner: "Ask what was true then, not only what is true now",
    Mock: AssetsMock,
    eyebrow: "Assets",
    title: "Every asset, and what was true when",
    body: "One place for an asset's documents, failure history and drawing connections, and all of it is dated. When a fact stops being true, Kairos closes it rather than deleting it. An investigation months later can still ask what the plant knew back in March.",
  },
  {
    id: "governance",
    name: "Governance",
    banner: "The quarantine gate opens one way, and only a person opens it",
    Mock: GovernanceMock,
    eyebrow: "Governance",
    title: "Nothing uncertain reaches the graph",
    body: "Anything Kairos extracts with less than 0.7 confidence goes to quarantine and stays there. Only a person can release it. Nothing is released automatically, and contradictions show up before the job starts, not after.",
  },
  {
    id: "field",
    name: "Field capture",
    banner: "Capture at the point of work, send it when the radio comes back",
    Mock: FieldMock,
    eyebrow: "Field capture",
    title: "Capture that survives a dead zone",
    body: "Voice notes are transcribed, tagged to an asset or work order, and held on the device until there is signal. A technician never loses a finding to a dead zone.",
  },
];

/** System-design diagram. Rendered from `docs/DIAGRAMS.md` to static SVG in
 *  `public/diagrams/` by `tools/render_diagrams.sh`. Deliberately not a runtime
 *  mermaid dependency: seven fixed pictures that only change when that file changes
 *  do not justify shipping a renderer to every visitor. */
function SystemDiagramImage({ src, alt }: { src: string; alt: string }) {
  return (
    /* eslint-disable-next-line @next/next/no-img-element -- a static vector, which
       next/image can neither resize nor re-encode; it would add a wrapper and nothing else. */
    <img
      src={src}
      alt={alt}
      /* Width is the only cap, and it never upscales. A max-height would bind first on
         the tall diagrams and shrink them further while leaving the panel empty either
         side; scaling a narrow one up to fill would render its labels at twice the size
         of the next tab's. Each file carries an explicit width and height, so the box is
         reserved before the SVG arrives.

         Below lg the card is only a few hundred px wide, narrow enough that fitting a
         plant architecture into it does not make it readable, only small. So the diagram
         keeps its natural width there and the panel scrolls instead.
         Not lazy: only the active tab's diagram is ever in the DOM. */
      decoding="async"
      className="mx-auto h-auto w-auto max-w-none object-contain lg:max-h-full lg:max-w-full"
    />
  );
}

/**
 * The system-design tabs. The card shows the diagram alone, so `alt` is its only
 * accessible representation, so it states what the picture shows rather than naming
 * the file, and is the one place a screen reader gets this content at all.
 */
const systemDesign: {
  id: string;
  name: string;
  src: string;
  alt: string;
}[] = [
  {
    id: "overview",
    name: "Overview",
    src: "/diagrams/overview.svg",
    alt: "End-to-end architecture: point of action, application core, async orchestration, intelligence services, knowledge stores and the model plane, with the human-authority gate.",
  },
  {
    id: "client",
    name: "Point of action",
    src: "/diagrams/client.svg",
    alt: "Point of action: a role-gated app shell over 44 routes, field surfaces with an offline write queue, and the desktop workspace.",
  },
  {
    id: "core",
    name: "Application core",
    src: "/diagrams/core.svg",
    alt: "Application core: rate limit, fail-closed OPA authorization and telemetry middleware, then token and site-scope dependencies, then 12 routers.",
  },
  {
    id: "orch",
    name: "Async orchestration",
    src: "/diagrams/orch.svg",
    alt: "Async orchestration: the durable Temporal ingestion pipeline, six Celery queues, the Go OT connector, and Redis Streams feeding the EEMUA push governor.",
  },
  {
    id: "svc",
    name: "Intelligence services",
    src: "/diagrams/svc.svg",
    alt: "Intelligence services: perception feeding hybrid retrieval, a two-pass safety gate that either answers with citations or refuses with sources, and a governance layer gated on human authority.",
  },
  {
    id: "data",
    name: "Knowledge & data",
    src: "/diagrams/data.svg",
    alt: "Knowledge and data stores: the Neo4j temporal graph, Qdrant vectors, Elasticsearch exact match and Supabase as the system of record.",
  },
  {
    id: "ext",
    name: "Model plane",
    src: "/diagrams/ext.svg",
    alt: "Model plane: the NIM to OpenRouter to Gemini to Ollama synthesis cascade, plus the OCR, NER, speech and embedding task models.",
  },
];

const audiences = [
  { name: "Supervisors", title: "The plant on one screen", shot: "workspace", body: "Live service state, open conflicts and the size of the quarantine queue, with the decisions that need a person ranked first." },
  { name: "Reliability", title: "Evidence, not recollection", shot: "reliability", body: "Blast radius and root-cause packs built from the recorded history in the graph, not from memory." },
  { name: "Field techs", title: "Works when the signal doesn't", shot: "field", body: "Briefs, asset context and voice capture built for a phone. They wait on the device and sync when the radio comes back." },
  { name: "Compliance officers", title: "Coverage you can export", shot: "compliance", body: "Regulation coverage and gap severity, sorted by how critical the asset is, with audit packs you can generate at any time." },
  { name: "Turnaround", title: "Short windows, no rate limit", shot: "turnaround", body: "Permit-to-work briefs skip the alarm cap, because an outage window does not wait for an hourly quota." },
  { name: "Off-boarding", title: "Before the knowledge walks", shot: "offboarding", body: "Guided interviews that capture what someone knows before they leave, while they are still there to ask." },
] as const;

// Measured 2026-08-24 on the live stack, per benchmark/RESULTS.md.
type EvalBar = {
  label: string;
  note: string;
  value: number;
  display: string;
  /** Raw count behind the percentage. */
  badge: string;
  /** Small qualifier under the headline number. */
  sub: string;
  hero: boolean;
};
const evalBars: EvalBar[] = [
  { label: "Retrieval", note: "The fact reaches the model", value: 98, display: "98%", badge: "45/46", sub: "graded by fixed rules", hero: false },
  { label: "Provenance", note: "Sources cited", value: 100, display: "100%", badge: "46/46", sub: "every answer cited", hero: true },
  { label: "Answer quality", note: "One valid run", value: 91, display: "91%", badge: "42/46", sub: "95% confidence: 80 to 97", hero: false },
];

// The five harnesses beyond the Q&A grading, all from benchmark/RESULTS.md.
const evalSuites: {
  name: string;
  headline: string;
  headlineNote: string;
  rows: [string, string][];
}[] = [
  {
    name: "Adversarial safety",
    headline: "0 unsafe",
    headlineNote: "15 questions written to make it guess",
    rows: [["Unsafe answers", "0"], ["Refusals", "12"], ["Answerable ones answered", "yes"], ["Prompt injection held", "yes"]],
  },
  {
    // The PS names "knowledge graph linkage completeness" as an evaluation
    // focus, so it belongs on the page as its own figure rather than implied.
    // Document-centric (run_kg_completeness.py), not the raw asset count —
    // that query has no test-artifact filter, see status.md.
    name: "Knowledge graph linkage",
    headline: "21 / 21",
    headlineNote: "Active vault documents with at least one knowledge-graph edge",
    rows: [["Documents linked", "100%"], ["Dangling provenance", "0"], ["Alias resolution", "2/2"], ["MDM identity", "2/2"]],
  },
  {
    name: "Proactive briefs · Layer 8",
    headline: "6 / 6",
    headlineNote: "All graded checks pass. Soft targets are reported, not scored",
    rows: [["Work order raised", "2/2"], ["Permit to work", "2/2"], ["Tag-out · inspection", "1/1 · 1/1"], ["Soft targets unmet", "7, disclosed"]],
  },
  {
    name: "Compliance gap detection",
    headline: "F1 0.912",
    headlineNote: "Zero false positives across 52 pairs",
    rows: [["Precision", "1.000"], ["Recall", "0.838"], ["True / false positives", "31 / 0"], ["Full status agreement", "46 / 52"]],
  },
  {
    name: "Entity extraction · Layer 0",
    headline: "F1 0.805",
    headlineNote: "40 labels, 15 extractions, no fallback model used",
    rows: [["Precision", "0.786"], ["Recall", "0.825"], ["ASSET_TAG F1", "0.889 (n=30)"], ["PERSON F1", "1.000 (n=7)"]],
  },
  {
    name: "Per-layer smoke",
    headline: "13 / 13",
    headlineNote: "Every layer answered on the live stack",
    rows: [["Slowest read", "search 3.7 s"], ["Assets", "1.7 s"], ["Graph / Vault", "212 / 163 ms"], ["Failures", "0"]],
  },
  {
    name: "Time to a trusted answer",
    headline: "−19.9%",
    headlineNote: "Modelled, compared against BM25 keyword search",
    rows: [["Traditional", "124.0 min / 46 q"], ["Kairos", "99.4 min / 46 q"], ["Docs opened", "1.00 vs 1.35"], ["Raw machine time", "loses: 9.6 s vs 28 ms"]],
  },
  {
    name: "Concurrency sweep",
    headline: "0% errors",
    headlineNote: "2275 requests across 9 read endpoints, up to 50 users",
    rows: [["p50 · 1 → 50 VU", "136 → 500 ms"], ["p95 at 50 VU", "1840 ms"], ["Throughput", "5.8 → 74.5 rps"], ["Knee of the curve", "50 users"]],
  },
  {
    name: "Soak · 60 minutes",
    headline: "No leak signal",
    headlineNote: "Steady load against cloud stores, reads only",
    rows: [["Memory slope", "+8.6 MB/h"], ["Connections", "+4.2/h"], ["Errors", "0.11% of 37,842"], ["Idle recovery", "4 / 4 endpoints"]],
  },
  {
    // Every row here is the same 2026-10-18 run the chart above reports, taken
    // from one `run_benchmark.py` output. Quoting the percentiles from one run
    // beside another run's provider mix is the mistake this card is arranged to
    // prevent — figures from earlier sweeps had drifted into the docs.
    name: "Synthesis latency",
    headline: "p50 2.6 s",
    headlineNote: "Nemotron 3 Super on NVIDIA NIM at the 60 second cap, quoted with its slowest cases",
    rows: [["p95", "9.6 s"], ["Mean", "3.8 s"], ["Graded questions", "46"], ["Answered by", "nim 40 · refused 6"]],
  },
];

/**
 * The technology under the eight capability screens, plus the cross-cutting work
 * that never gets a screen of its own. NOT a superset of the tabs and not a
 * subset either — a different axis, which is why the counts differ and why the
 * block states that above itself. Seven of the eight tabs have no row here (the
 * governor, refusals, quarantine, offline capture, root-cause ranking, temporal
 * supersession), and four rows here have no tab (blast radius, PII redaction,
 * Management of Change, the drift stop).
 *
 * One array rather than two: the page used to split these into "what the brief
 * asked for" and "what it did not", which is a fact about the assignment rather
 * than about the product, and a reader has no way to check it. Ten across two
 * columns fills five rows exactly, so the grid closes with no cell left over.
 */
const capabilityList: [string, string][] = [
  // search_service.hybrid_search: ES + Qdrant always, the graph too once the
  // question names an asset; _fuse does reciprocal-rank fusion, then orders by
  // authority_level ASC before relevance.
  ["Retrieval across mixed document types", "Elasticsearch, Qdrant and the graph queried in parallel, fused by rank, then ordered by authority"],
  // 6 labels in db/neo4j/init_schema.cypher; the 6 edge properties are the
  // non-negotiable write contract in CLAUDE.md.
  ["Knowledge graph and ontology", "Six node types, six properties on every link, decades of tag aliases matched up"],
  // /compliance/nonconformance reads conflicts + quarantine; moc_items runs
  // draft → pending_approval → approved, with approved_by and approved_at.
  ["Non-conformance register", "Conflicts and quarantined extractions tracked in one place, with an owner against each"],
  ["Management of Change", "A safety parameter never updates itself. Kairos drafts the change request and waits for a named approval."],
  // document_pipeline.py: every activity carries DEFAULT_RETRY, maximum_attempts 5.
  ["Durable ingestion", "A Temporal workflow per document, so a crash resumes at the activity that failed rather than at the first page"],
  // GraphService.get_blast_radius, surfaced by /governance.
  ["Blast radius", "Change one document and see every procedure and record downstream of it that just went out of date."],
  // services/pii.py — export boundary only, and the patterns are bounded so
  // equipment tags and part numbers never match.
  ["PII redaction at export", "Names are removed on the way out, never on the way in, to meet the DPDP Act 2023. Equipment tags are never matched, on purpose."],
  // circuit_breaker.check: z > 2.0 on 7-day overrides vs the prior three weeks;
  // link_to_graph then writes zero edges and raises review_required.
  ["It stops itself when it drifts", "When corrections on one class of equipment spike, nothing from that class reaches the graph until the rate settles."],
];


/**
 * The six properties, shown against one worked example rather than described in
 * the abstract. The example values are the same fact the hero card states, so the
 * page tells one story twice rather than two stories once. It is illustrative, and
 * the block says so in the copy above it.
 *
 * `9999-12-31` is not a placeholder: it is the real sentinel this project writes
 * into `valid_to`, because a NULL there would make every "what was true then"
 * query special-case the open row.
 */
const edgeProperties: { name: string; value: string; note: string }[] = [
  { name: "valid_from", value: "2025-01-15", note: "When this fact started being true." },
  { name: "valid_to", value: "9999-12-31", note: "Still open. Closed when something replaces it, never deleted." },
  { name: "authority_level", value: "3 · OEM manual", note: "A regulation outranks a vendor manual, which outranks a local note." },
  { name: "document_id", value: "FP-SB-2025-04", note: "The exact source it came from." },
  { name: "confidence", value: "0.91", note: "Anything below 0.7 goes to quarantine instead." },
  { name: "verification_status", value: "Verified", note: "A named engineer signed this one off." },
];

const faqGroups = [
  {
    name: "Basics",
    items: [
      ["What does Kairos actually do?", "It turns the documents, drawings, asset history and field notes a plant already owns into answers people can act on. Every answer shows the source it came from, how authoritative that source is, and how confident the system is."],
      ["What problem does it solve?", "Plant knowledge is spread across manuals, procedures, drawings, work orders and people's heads, and it goes out of date without anyone noticing. Engineers lose time finding the current version, and jobs start without the one bulletin or past failure that mattered. Kairos joins those sources, tracks which version is current, and brings the relevant facts to the person before the job."],
      ["Who is it for?", "Field technicians get briefs before a job and a copilot on their phone. Maintenance and reliability engineers get root-cause packs, conflicts and the review queues. Compliance officers get clause-by-asset gaps and exportable audit evidence, and plant managers get one view of open risk."],
      ["How is this different from a chatbot over our documents?", "A chatbot gives you text. Kairos gives you text plus proof of where it came from, and refuses to answer when a safety-critical question has weak evidence behind it. We grade retrieval and citations with fixed rules, not with another model."],
      ["How is it different from AVEVA, Aspen or other industrial software?", "Predictive tools such as Aspen Mtell watch sensor data; Kairos reads what people wrote about the equipment. Asset platforms such as AVEVA and Octave are adding document extraction and copilots that answer when asked. Kairos also pushes a brief when nobody asked, inside an alarm budget, refuses safety questions it cannot back up, and publishes a rule-graded benchmark that includes its failures."],
      ["What file types can it read?", "PDFs, including scanned ones, photos and handwritten notes (PNG, JPEG, TIFF, WebP), P&ID drawings, spreadsheets (.xlsx, .xls, .ods), CSV and text files, email archives (.eml, .mbox) and voice notes. Word files are not read in this MVP, so export them to PDF first."],
      ["What does it need to get started?", "The documents you already have. Drawings, procedures, vendor manuals and maintenance history all go through the ingestion pipeline. Nothing has to be rewritten first."],
    ],
  },
  {
    name: "How it works",
    items: [
      ["How does it find an answer?", "Three searches run together: keyword search for exact tags and document numbers, meaning-based search for questions worded differently from the text, and the knowledge graph for what is linked to the asset. The results are merged by rank, the most relevant documents are kept and shown most authoritative first, and the model writes only from those documents and must cite them."],
      ["Why a knowledge graph and not just a vector database?", "Some questions are about connections, not text: which valves sit inside an isolation boundary, which pumps share a failing part, what a revised bulletin affects downstream. A graph answers those directly. Each link also carries its source, authority, confidence, review status and the dates it was true, which a vector store has no place for."],
      ["What happens when a document is revised?", "The old version is closed, not deleted: its facts get an end date and the new ones start. Kairos then traces everything that depended on the old version and flags it for review. You can also view the graph as it stood on any past date, which is what an incident investigation needs."],
      ["What if two documents disagree?", "Kairos does not average them or pick the newest. It ranks sources by authority (regulation, then engineering standard, OEM manual, site procedure and field note), raises a conflict, and sends engineering disagreements to a Management of Change. It can draft the redline for that change with a citation for every edit, but an engineer approves it."],
      ["Can it read engineering drawings?", "Yes. A vision model reads a P&ID into equipment, valves, instruments and the lines between them. The result stays a candidate until an engineer checks it element by element, and a drawing it cannot read is shown as a placeholder. It never invents a valve tag."],
      ["What is a proactive brief?", "A short, sourced briefing that arrives when something happens in the plant, without anyone searching. Work orders, permits to work, shift handovers, alarms, equipment tag-outs, completed inspections and repeat failures each trigger one, carrying the asset's history, open conflicts and unreviewed field notes. A permit brief needs two different people to sign."],
      ["How does root-cause analysis work?", "For a failed asset, an agent decides what to look up, up to four steps across failure history, sister assets, field notes and documents, then builds a timeline and ranked hypotheses. Each hypothesis is checked against the text it cites, and one the evidence does not support is dropped and shown as dropped. It takes about thirty seconds."],
      ["Which AI models does it use?", "NVIDIA Nemotron 3 Super for answers, briefs and root-cause analysis, NVIDIA's OCR model for scans, a Llama 3.2 vision model for entity extraction and drawings, Jina embeddings for search and Whisper on Groq for voice. All are hosted, and Kairos does not train or fine-tune any of them on your documents."],
      ["What if the AI provider goes down?", "Answers fall back through a chain of providers set up in one place, and every answer records which model produced it. If anything but the intended model answered, the benchmark marks the run as suspect instead of quoting it."],
    ],
  },
  {
    name: "Trust",
    items: [
      ["How do you know the extracted content is correct?", "The extractor only proposes. Anything below 0.7 confidence goes to a review queue, a scanned page with any doubtful passage is held whole, and everything else enters the graph marked unverified until a reliability engineer or admin signs it off. Extraction is also scored against an answer key: OCR keeps every tag, value and date on all four paired test images, and all 21 test documents are linked into the graph."],
      ["What happens when the system is not sure?", "Anything extracted with less than 0.7 confidence goes to quarantine and stays there until a person releases it. Nothing uncertain reaches the knowledge graph on its own."],
      ["Can it refuse to answer?", "Yes, and it does. A safety-critical question without solid evidence gets a refusal that still lists its sources, so you can check them yourself instead of trusting a vague answer."],
      ["How do you stop it making things up?", "The model writes only from documents the server retrieved itself, and every claim must cite one; a request cannot slip in its own evidence. Safety-critical questions are checked twice, on the evidence and on the answer, and refused when either is weak: 15 adversarial safety questions produced no unsafe answer. Every source opens the original document, and on the latest run all 46 responses carried their sources."],
      ["What if someone uploads a wrong or malicious document?", "It cannot overrule a better source. Only reliability engineers and admins can file a document as regulation, standard or OEM manual, so anyone else's upload is capped at site-procedure level, and replacing a high-authority document needs an approved Management of Change. Document text reaches the model as untrusted data, so instructions hidden in a file are ignored."],
      ["Does it replace engineers?", "No. It finds, links and drafts, and people decide. Promotions, Management of Change approvals and permit sign-offs are human actions, each written to the audit log, and a permit brief needs two different signatures."],
      ["What if a person approves something wrong?", "It can be corrected, because nothing is lost. Every approval is logged with who and when, facts are closed rather than deleted, and a later document or change supersedes the wrong one while the old state stays visible."],
      ["Why limit how many briefs someone gets?", "The EEMUA-191 standard exists because operators stop reading alarms when there are too many of them. The same happens with knowledge. So the limit is six an hour, and permit-to-work briefs are always exempt."],
      ["Who gets told when Kairos finds something?", "Whoever owns the decision, and nothing sits in a queue waiting to be noticed. An extraction it is not confident in goes to quarantine and waits for a person. Two procedures that disagree raise a conflict before the job starts, not in the post-mortem. An observation from the field is transcribed, tagged and sent to engineering for review. A safety question with thin evidence returns a refusal card with its sources attached."],
    ],
  },
  {
    name: "Data",
    items: [
      ["Is anything ever deleted?", "No. The vault is permanent and stored files are never changed. When a fact stops being true, Kairos closes it instead of removing it, so the record of what you knew, and when you knew it, survives."],
      ["Can we see where an answer came from?", "Every fact carries six properties on the link itself, including the source document and whether a person verified it. Every answer lists its sources."],
      ["Where does our document text go?", "To the hosted model providers that read it: NVIDIA NIM for extraction and answers, Jina for search embeddings and Groq for voice."],
      ["Can it run on-premise or in an air-gapped plant?", "Not yet. There is no on-premise inference in this MVP, so the plant needs an outbound connection to the model providers. Running the models locally is the main blocker for air-gapped sites and the first item on our roadmap for them."],
      ["Is our data used to train AI models?", "Kairos trains nothing on it. Corrections people make are stored as labels for scoring extraction, not for training. What each hosted provider does with the text it receives is set by that provider's terms, which a plant should check before sending documents off site."],
      ["How is personal data handled?", "Names stay in the stored text, because removing them at ingestion would break search for who did what. They are redacted when a document is exported, under India's DPDP Act 2023."],
      ["Does it work on a phone, or without signal?", "It is built for phones, with a high-contrast sunlight theme for outdoor use, and installs as a web app. Voice notes and deviation flags are held on the device and sent once there is signal again; asking for an answer needs a connection."],
      ["Does it understand languages other than English?", "Only English is tested. Voice transcription records the spoken language, but extraction, answers and the benchmark are all in English, so other languages are untested in this MVP."],
    ],
  },
  {
    name: "Access",
    items: [
      ["Who can see what?", "Access follows the role. Field workers get briefs, copilot, assets and capture. Engineering and reliability get the evidence and governance screens. System health is admin only. The check happens in one central place, not page by page."],
      ["What happens if the permission service goes down?", "Access is refused. The check fails closed, so an outage locks people out rather than letting everyone through, and the same rule covers reads as well as writes."],
      ["Can one site see another site's data?", "Not unless the role allows it. A site account reads only its own site: the site comes from the sign-in token, never from the request, and admins keep the cross-site view. Cross-site pattern alerts share only failure codes and counts for an equipment class, never documents, and only when the class runs on two or more sites and one of them has at least two such failures."],
      ["Has it been security tested?", "By us, not by an outside firm. Every push runs code scanning, a dependency audit and a Go vulnerability check, and an internal security review fixed its findings, each with a test, and recorded the risks it accepted. There is no external penetration test or certification yet, and the seeded demo passwords still need rotating before a real rollout."],
      ["Can we try it without a rollout?", "Yes. The demo account signs straight into a workspace with the golden dataset already loaded, so you can question real answers instead of looking at a slide."],
    ],
  },
  {
    name: "Evidence",
    items: [
      ["How was it evaluated?", "Forty-six domain-expert questions, written against a fixed answer key, across fifteen categories and graded by fixed rules. Retrieval, answer quality and sourcing are scored separately, and a refusal counts as correct when refusing was the right call."],
      ["Why grade with fixed rules instead of an AI judge?", "Because a model grading a model is not reproducible and tends to agree with itself. Each question lists the facts an answer must state, the contradictions it must not contain and a sources check, so anyone can rerun the harness and get the same score."],
      ["Why quote a confidence interval for answer quality?", "Because 42 out of 46 is a sample, not a fixed rate. The interval says the honest thing a single percentage hides: on this set of questions the true rate sits somewhere around 80 to 97 percent. Retrieval and sourcing are graded by fixed rules: 45 and 46 out of 46 on this run. Every run is also checked for validity, and we never quote a run in which more than a tenth of the answers came from a fallback model."],
      ["How accurate is entity extraction?", "An F1 score of 0.805 on 40 labelled entities, counted only when the intended model answered. Forty labels is a small set, so quote the score with that number."],
      ["How well does it catch compliance gaps?", "Precision 1.000 and recall 0.838 on 52 clause-and-asset pairs: no false alarms, and about one real gap in six missed. Only OISD 117 and ISO 45001 clauses are mapped into the gap check today."],
      ["How fast is an answer?", "2.6 seconds at the median and 9.6 seconds at the 95th percentile on the latest run, with a 60-second cap. A root-cause pack takes about thirty seconds, because it runs several lookups first."],
      ["How much time does it save?", "On our model of a person searching, 19.9 percent across 46 questions. One input is assumed rather than measured, the two minutes an engineer takes to check a document, so the page labels the figure modelled. The bigger saving, a brief arriving when nobody searched, is not in that number."],
      ["Does it hold up under load?", "2,275 requests with no errors, slowing past 50 concurrent users, and an hour-long soak with no sign of memory or connection leaks."],
      ["What do these numbers not cover?", "Four things, and we would rather name them. The soak test ran for one hour, so it says nothing about days. The validation set is small: 40 labels in total and only 3 for ORGANIZATION, so quote a per-type score with the number of labels behind it. Fifty virtual users against a demo-sized dataset is not evidence that the system handles a 10,000-asset plant. And hybrid retrieval reaches 44 of 46, which is exactly what semantic search alone reaches, so we report it as matching the best single method rather than beating it."],
      ["Is any of this running against a real plant?", "No. The documents are written by us to model a petrochemical complex, with an answer key, and Kairos is not connected to any live plant. The regulatory clause text inside them (OISD, PESO and the Factories Act) is real public text. That is the intended limit of this MVP, and we would rather say so than let a number imply otherwise."],
      ["Can we see the failures too?", "Yes. The test harness, the question set and every raw run are in the repository, including the runs where the answer was wrong."],
    ],
  },
  {
    name: "Rollout",
    items: [
      ["How long does a rollout take?", "Search works from day one, because it needs no integration. Months one to three are search only while the graph is built, written answers and review queues come in months three to six, and proactive briefs start from month six, once push volume has stayed inside the alarm budget for 30 days."],
      ["How much work is onboarding a plant?", "Loading documents is not the work: each one takes seconds and nothing has to be rewritten. The work is mapping the plant's asset-tag convention and its regulations into Kairos, so that extracted tags resolve to real assets and clauses."],
      ["Does it connect to SAP, Maximo or the historian?", "Not in this MVP. Work orders, permits, alarms and handovers come in through Kairos's event API, which a maintenance system can call. A PI historian client is written but not connected to a live historian, and the OPC-UA, SAP and Maximo connectors say they are not implemented rather than returning empty data."],
      ["What does it cost to run?", "The backend runs on one small cloud server, about $68 a month at AWS Mumbai rates, with the frontend on Vercel and managed databases behind it. Model calls are billed per use by each provider."],
      ["What is the business model?", "A per-plant annual licence, starting with a 90-day pilot on one unit, since search alone needs no integration. It grows per site, then per connector as historian and maintenance-system links come online."],
      ["Which industries does it fit?", "It is built and tested on a petrochemical plant. The authority model is not tied to one industry: the top level is whichever regulation applies, such as OISD and PESO for Indian oil and gas, FDA 21 CFR Part 11 for pharma or CEA rules for power."],
      ["What is not built yet?", "Live links to the historian and maintenance system, local models for air-gapped plants, enforcement for the model gate that today only reports, and an outside security test. Multi-site is in place: site-scoped access and cross-site failure alerts."],
    ],
  },
] as const;

const GITHUB_URL = "https://github.com/kr7shnasomani/kairos";

// Footer links point only at real destinations: page anchors, /docs, /login and the repository.
const footerColumns: { heading: string; links: [string, string][] }[] = [
  { heading: "Product", links: [["The problem", "#problem"], ["Capabilities", "#capabilities"], ["Use cases", "#field"]] },
  { heading: "How it works", links: [["The pipeline", "#how"], ["System design", "#system"], ["Provenance", "#provenance"], ["Evals", "#evidence"]] },
  { heading: "Resources", links: [["Documentation", "/docs"], ["FAQ", "#faq"], ["Source code", GITHUB_URL]] },
];
/** Adds .lp-anim, then reveals each [data-reveal] block as it scrolls in. */
function useReveal() {
  useEffect(() => {
    const root = document.querySelector<HTMLElement>("main.landing");
    if (!root) return;
    // Gated on JS so a failed hydrate never leaves the page invisible.
    root.classList.add("lp-anim");

    const targets = root.querySelectorAll("[data-reveal]");
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("is-in");
          io.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
    );
    targets.forEach((t) => io.observe(t));
    return () => io.disconnect();
  }, []);
}

/**
 * Surveyor marks pinned to the corners of a framed block.
 *
 * Returns a fragment, deliberately, because a wrapper element would be a static child
 * and so claim a cell in the grid containers these sit inside. The ticks
 * themselves are position:absolute (.lp-tick), which keeps them out of flow.
 */
function Ticks({ solid = false, bottom = false }: { solid?: boolean; bottom?: boolean }) {
  const cls = `${solid ? "lp-tick lp-tick--solid" : "lp-tick"} pointer-events-none`;
  return (
    <>
      <span aria-hidden="true" className={`${cls} left-0 top-0 -translate-x-1/2 -translate-y-1/2`} />
      <span aria-hidden="true" className={`${cls} right-0 top-0 translate-x-1/2 -translate-y-1/2`} />
      {bottom ? (
        <>
          <span aria-hidden="true" className={`${cls} bottom-0 left-0 -translate-x-1/2 translate-y-1/2`} />
          <span aria-hidden="true" className={`${cls} bottom-0 right-0 translate-x-1/2 translate-y-1/2`} />
        </>
      ) : null}
    </>
  );
}

/**
 * Demo player. A facade, not a bare iframe: the poster is the page's own media
 * panel, so YouTube is contacted only once someone presses play. That keeps the
 * third-party script (and its cookies) off first load, which is the difference
 * between a fast landing page and a slow one. `youtube-nocookie` on top.
 */
function DemoPlayer({ videoId }: { videoId: string }) {
  const [playing, setPlaying] = useState(false);
  return (
    <div className="lp-card lp-media lp-dither relative mt-10 border border-transparent p-3 sm:p-6">
      <div className="relative aspect-video overflow-hidden border border-white/20">
        {playing ? (
          <iframe
            className="absolute inset-0 size-full"
            src={`https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0&modestbranding=1`}
            title="Kairos demo"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        ) : (
          <button
            type="button"
            onClick={() => setPlaying(true)}
            aria-label="Play the Kairos demo"
            className="group absolute inset-0 grid place-items-center"
          >
            <span className="grid size-16 place-items-center bg-(--lp-accent-strong) text-white transition-transform duration-150 ease-out group-hover:scale-105 group-active:scale-95 sm:size-20">
              <svg width="22" height="24" viewBox="0 0 22 24" fill="currentColor" aria-hidden="true">
                <path d="M21 12 0 24V0z" />
              </svg>
            </span>
            <span className="absolute bottom-4 left-4 text-[12px] uppercase tracking-[0.08em] text-white/80 sm:bottom-6 sm:left-6">
              Play the demo
            </span>
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * The reference's primary button does not simply darken: it dissolves to black
 * cell by cell. An 18x4 grid of squares fades in with a stepped 90ms
 * transition and a staggered delay, giving a pixel-wipe.
 *
 * Delays are derived from the index, never Math.random(): a random value would
 * differ between server and client render and break hydration.
 */
const PIXEL_COLS = 18;
const PIXEL_ROWS = 4;

function pixelDelay(index: number) {
  const col = index % PIXEL_COLS;
  const jitter = (index * 1103515245 + 12345) % 45;
  return col * 5 + jitter;
}

function PixelFill() {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-0 grid"
      style={{ gridTemplateColumns: `repeat(${PIXEL_COLS}, 1fr)`, gridTemplateRows: `repeat(${PIXEL_ROWS}, 1fr)` }}
    >
      {Array.from({ length: PIXEL_COLS * PIXEL_ROWS }).map((_, i) => (
        <span
          key={i}
          className="bg-(--lp-ink) opacity-0 [transition:opacity_90ms_steps(1)] group-hover:opacity-100"
          style={{ transitionDelay: `${pixelDelay(i)}ms` }}
        />
      ))}
    </span>
  );
}

function Eyebrow({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center rounded-[1px] bg-(--lp-accent-strong) px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-white">
      {children}
    </span>
  );
}

/** Heading highlight block: charcoal by default, solid accent when `fill`. */
function Box({ children, fill = false }: { children: React.ReactNode; fill?: boolean }) {
  return (
    <span
      className={`inline-block px-3 py-[5px] font-semibold tracking-normal text-white ${fill ? "bg-(--lp-accent-strong)" : "bg-(--lp-charcoal)"}`}
    >
      {children}
    </span>
  );
}

/**
 * A real screenshot of the running app, captured by
 * tools/capture_landing_shots.sh. Re-run that script after UI changes so the
 * marketing page never drifts from the product.
 */
function Shot({ src, alt }: { src: string; alt: string }) {
  return (
    <Image
      src={`/shots/${src}.png`}
      alt={alt}
      width={2880}
      height={1620}
      sizes="(max-width: 1024px) 100vw, 900px"
      className="lp-mock h-auto w-full"
    />
  );
}

export default function Home() {
  const [capability, setCapability] = useState(0);
  const [systemTab, setSystemTab] = useState(0);
  const [audience, setAudience] = useState(0);
  const [faqGroup, setFaqGroup] = useState(0);
  useReveal();

  const active = capabilities[capability];
  const activeSystem = systemDesign[systemTab];

  return (
    <main className={`landing ${instrumentSans.variable} ${dmSans.variable} min-h-dvh`}>
      {/* ── Nav: segmented cells, not a plain row ──────────────────────── */}
      {/* Solid, no backdrop blur: the reference header is opaque #f8f8f8. */}
      <header className="sticky top-0 z-30 border-b border-(--lp-line) bg-(--lp-band)">
        <nav className="lp-frame flex h-[49px] items-stretch">
          <Link href="/" aria-label="Kairos home" className="flex items-center gap-2.5 border-r border-(--lp-line) px-4 sm:px-5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="" width={24} height={24} className="object-cover" />
            <span className="lp-display text-[18px] text-(--lp-ink)">Kairos</span>
          </Link>

          <div className="hidden items-stretch lg:flex">
            {navLinks.map(([label, href]) => (
              <a
                key={href}
                href={href}
                className="flex items-center whitespace-nowrap border-r border-(--lp-line) px-4 text-[13px] text-(--lp-muted) transition-colors duration-150 hover:bg-(--lp-ink) hover:text-white xl:px-5"
              >
                {label}
              </a>
            ))}
          </div>

          <div className="ml-auto flex items-stretch">
            <Link
              href="/login"
              className="group relative flex items-center gap-2 overflow-hidden border-l border-(--lp-line) bg-(--lp-accent-strong) px-5 text-[14px] font-medium text-white sm:px-7 transition-transform duration-150 ease-out active:scale-[0.98]"
            >
              <PixelFill />
              <span className="relative z-10">Open workspace</span>
              <span aria-hidden="true" className="relative z-10">›</span>
            </Link>
          </div>
        </nav>
      </header>

      {/* ── Hero ────────────────────────────────────────────────────────── */}
      <section className="lp-frame relative px-4 pb-14 pt-16 sm:px-6 sm:pt-24">
        <div data-reveal className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-start">
          {/* The {" "} before each <br /> is load-bearing: <br> contributes no
              whitespace, so without it the accessible name runs the lines
              together ("Plant knowledge,at the moment…"). Same pattern below. */}
          <div>
            <Eyebrow>Industrial knowledge intelligence</Eyebrow>
            <h1 className="mt-6 text-[40px] text-(--lp-ink) sm:text-[54px] lg:text-[64px]">
              The plant{" "}<br />
              already knows.{" "}<br />
              <span className="text-(--lp-accent)">Nobody can find it{" "}<br />
                in time.</span>
            </h1>
          </div>

          <div className="lg:pt-4">
            <p className="max-w-md text-[18px] leading-7 text-(--lp-muted)">
              <strong className="font-semibold text-(--lp-ink)">Kairos reads a plant&apos;s drawings,
                procedures and maintenance history into one system</strong> that answers in plain
              language, with the source behind every answer.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <a
                href={demoVideoId ? "#demo" : DEMO_FALLBACK_URL}
                target={demoVideoId ? undefined : "_blank"}
                rel={demoVideoId ? undefined : "noreferrer noopener"}
                className="group relative inline-flex min-h-11 min-w-[207px] items-center justify-center gap-2 overflow-hidden bg-(--lp-accent-strong) px-3 py-[15px] text-[14px] font-medium text-white transition-transform duration-150 ease-out active:scale-[0.98]"
              >
                <PixelFill />
                <span className="relative z-10">Watch demo</span>
                <span aria-hidden="true" className="relative z-10">›</span>
              </a>
              <a
                href="#how"
                className="inline-flex min-h-11 min-w-[207px] items-center justify-center gap-2 bg-(--lp-ink) px-3 py-[15px] text-[14px] font-medium text-white transition-[background-color,transform] duration-150 ease-out hover:bg-(--lp-accent-strong) active:scale-[0.98]"
              >
                See how it works <span aria-hidden="true" className="text-(--lp-accent)">▶</span>
              </a>
            </div>
          </div>
        </div>

        <div data-reveal className="lp-card lp-media lp-dither relative mt-12 border border-transparent p-3 sm:p-6">
          <div className="relative border border-white/20 p-4 sm:p-8">
            <HeroVisual />
          </div>
        </div>
      </section>

      {/* ── Demo: the product running, straight after the claim it makes ──
          Renders only when DEMO_YOUTUBE_URL is set. Placed here on purpose: the
          hero's primary CTA is "Watch demo", and a visitor who presses it should
          arrive in one scroll, before the argument starts. */}
      {demoVideoId && (
        <section id="demo" className="lp-band">
          <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
            <Ticks />
            <Eyebrow>Demo</Eyebrow>
            <h2 className="mt-5 max-w-3xl text-[36px] sm:text-[48px]">
              The product, running.
            </h2>
            <p className="mt-5 max-w-xl text-[16px] leading-6 text-(--lp-muted)">
              One pass through Kairos: a document goes into the vault, a question comes back with
              its source, and a safety-critical question is refused rather than guessed.
            </p>
            <DemoPlayer videoId={demoVideoId} />
          </div>
        </section>
      )}

      {/* ── The problem: stated before any product claim ────────────────── */}
      <section id="problem" className="bg-(--lp-dark) text-white">
        <div className="lp-frame lp-frame--dark px-4 py-16 sm:px-6 sm:py-24">
          <div data-reveal>
            <Eyebrow>The problem</Eyebrow>
            <h2 className="mt-6 max-w-3xl text-[30px] sm:text-[44px]">
              This is not a filing problem.{" "}<br />
              <Box fill>It is a safety problem.</Box>
            </h2>
            <p className="mt-6 max-w-2xl text-[16px] leading-6 text-(--lp-dark-muted)">
              A large plant runs on documents written over forty years by people who have mostly
              left. When a technician cannot find the right one in the ten minutes they have, they
              do the job from memory, either their own or someone else&apos;s. That is where incidents
              start.
            </p>
          </div>

          <div data-reveal className="mt-14 grid gap-px bg-(--lp-dark-line) sm:grid-cols-2 lg:grid-cols-4">
            {problemStats.map((stat) => (
              <div key={stat.figure} data-stagger className="lp-cell lp-cell--dark bg-(--lp-dark) flex h-full flex-col p-5">
                <p className="lp-display text-[40px] leading-none text-(--lp-accent) sm:text-[48px]">{stat.figure}</p>
                <p className="mt-3 text-[14px] font-semibold text-white">{stat.label}</p>
                <p className="mt-3 text-[13px] leading-5 text-(--lp-dark-muted)">{stat.body}</p>
                <p className="mt-auto border-t border-(--lp-dark-line) pt-3 text-[11px] uppercase tracking-[0.08em] text-(--lp-dark-muted)">
                  {stat.source}
                </p>
              </div>
            ))}
          </div>

          <p data-reveal className="mt-12 max-w-3xl text-[16px] leading-6 text-white">
            Search alone cannot fix this, because the most dangerous gaps are the ones nobody knows
            to search for. A technician who has never heard that this pump failed this way before
            does not think to go looking.{" "}
            <span className="text-(--lp-accent)">So Kairos does not wait to be asked.</span>
          </p>
        </div>
      </section>

      {/* ── How it works: one scenario, followed end to end ──────────────── */}
      <section id="how" className="border-t border-(--lp-line)">
        <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
          <Ticks />
          <div data-reveal>
            <Eyebrow>How it works</Eyebrow>
            <h2 className="mt-6 max-w-3xl text-[30px] text-(--lp-ink) sm:text-[44px]">
              One pump, one work order,{" "}<br />
              <Box>start to finish.</Box>
            </h2>
            <p className="mt-6 max-w-xl text-[16px] leading-6 text-(--lp-muted)">
              Everything below happens without anyone typing a search. Follow it once and the rest
              of this page explains itself.
            </p>
          </div>

          {/* A rail, not a mesh of cells. This content is ordered, and five equal
              boxes say "five categories" where a numbered rail says "five steps,
              in this direction". The last node is filled because the copy below
              turns on it. */}
          <ol data-reveal className="mt-12 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-5">
            {scenario.map((item, index) => {
              const last = index === scenario.length - 1;
              return (
                <li key={item.tag} data-stagger className="relative">
                  {!last && (
                    <span
                      aria-hidden="true"
                      className="absolute left-9 -right-4 top-4 hidden h-px bg-(--lp-line) lg:block"
                    />
                  )}
                  <div className="relative z-10 inline-flex items-center gap-3 bg-(--lp-bg) pr-3">
                    <span
                      className={`lp-display grid size-8 shrink-0 place-items-center rounded-full text-[15px] ${last ? "bg-(--lp-accent-strong) text-white" : "border border-(--lp-accent) bg-(--lp-bg) text-(--lp-accent-text)"}`}
                    >
                      {index + 1}
                    </span>
                    <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">
                      {item.tag}
                    </span>
                  </div>
                  <p className="lp-display mt-4 text-[18px] leading-tight text-(--lp-ink)">{item.title}</p>
                  <p className="mt-3 text-[14px] leading-5 text-(--lp-muted)">{item.body}</p>
                </li>
              );
            })}
          </ol>

          <p data-reveal className="mt-10 max-w-3xl text-[15px] leading-6 text-(--lp-muted)">
            That last step is the one people miss. A system that always answers is easy to build and
            impossible to trust in a plant.{" "}
            <strong className="font-semibold text-(--lp-ink)">Knowing when to stay quiet is the
              harder half</strong>, and it is why everything below exists.
          </p>
        </div>
      </section>

      {/* ── Capabilities: split layout with a composite media card ─────── */}
      <section id="capabilities" className="lp-band border-t border-(--lp-line)">
        <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
          <Ticks />
          <div className="grid gap-10 sm:gap-14 lg:grid-cols-[1fr_1.35fr]">
            <div data-reveal>
              <Eyebrow>Capabilities</Eyebrow>
              <h2 className="mt-6 text-[30px] text-(--lp-ink) sm:text-[44px]">
                Answers paired with{" "}<br />their <Box>evidence.</Box>
              </h2>
              <p className="mt-6 max-w-md text-[16px] leading-6 text-(--lp-muted)">
                Kairos already knows the plant&apos;s documents, assets and history. Every screen works
                the same way, so nothing is claimed without a way to check it.
              </p>

              <div className="mt-10">
                {capabilities.map((item, index) => {
                  const on = index === capability;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      aria-pressed={on}
                      aria-controls="capability-panel"
                      onClick={() => setCapability(index)}
                      className="relative block w-full border-b border-(--lp-line) py-4 pl-3 text-left"
                    >
                      {/* 20px / 500-on-active, matching the reference's own tab
                        metrics and its 0.24s colour easing. Light-section tokens:
                        this list sits on --lp-band, so --lp-accent-text and
                        --lp-tab-idle are the pair that clears 4.5:1 here. At 20px
                        these are not "large text", so --lp-accent (3.35:1) and the
                        dark-band tokens do not qualify. */}
                      <span
                        className={`lp-display text-[20px] transition-colors duration-[240ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${on ? "font-medium text-(--lp-accent-text)" : "text-(--lp-tab-idle) hover:font-medium hover:text-(--lp-ink)"}`}
                      >
                        {item.name}
                      </span>
                      <span
                        aria-hidden="true"
                        className={`absolute -bottom-px left-0 h-0.5 bg-(--lp-accent) transition-all duration-[240ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${on ? "w-4/5" : "w-0"}`}
                      />
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Composite card: gradient media on top, white text block beneath. */}
            {/* Stretches to the tab list's full height rather than sitting short of
              it. The slack goes to the media panel, not the copy: a taller mock
              is the point of the card, a taller paragraph is just white space. */}
            <div id="capability-panel" data-reveal className="lp-card relative flex flex-col border border-(--lp-accent) bg-(--lp-surface)">
              <Ticks solid bottom />
              <div key={active.id} className="lp-swap flex flex-1 flex-col">
                {/* Both regions grow but neither shrinks (`flex: N 0 auto`), and the
                  slack is split 2:1 so a stretched card gives its extra height to
                  the mock rather than to the paragraph.

                  `flex-1` plus an explicit `min-h` is what clipped this panel
                  before: the card is a grid item stretched to the tab list's
                  height, so when a mock needed more room than that the flex line
                  was over-constrained, and an explicit `min-height` replaces the
                  automatic minimum size — so the panel shrank to its floor and cut
                  the last rows off Ingestion and Root cause. `shrink-0` restores
                  content as the floor and lets the card grow instead. */}
                <div className="lp-media lp-dither relative flex min-h-[340px] flex-[2_0_auto] flex-col p-5 sm:min-h-[350px] sm:p-6">
                  <p className="inline-block self-start bg-(--lp-accent-strong) px-3 py-1.5 text-[10px] font-semibold uppercase leading-4 tracking-[0.06em] text-white sm:text-[11px]">
                    {active.banner}
                  </p>
                  <div className="mt-5 flex flex-1 flex-col justify-center">
                    <active.Mock />
                  </div>
                </div>

                <div className="flex min-h-[208px] flex-[1_0_auto] flex-col justify-center p-5 sm:p-7">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-(--lp-accent-text)">{active.eyebrow}</p>
                  <h3 className="mt-3 text-[24px] text-(--lp-ink) sm:text-[32px]">{active.title}</h3>
                  <p className="mt-4 max-w-xl text-[15px] leading-6 text-(--lp-muted)">{active.body}</p>
                </div>
              </div>
            </div>
          </div>

          {/* The same subject at a different altitude: eight screens above, the ten
              things behind them here. It used to sit in its own section further down
              the page, which read as a second, flatter capabilities list and repeated
              claims the Ingestion and Provenance panels already make. Cell borders
              rather than a gap mesh — a mesh paints its container colour into
              whatever cells the last row leaves over. */}
          <div data-reveal className="mt-16">
            <div className="border-b border-(--lp-line) pb-4">
              <p className="lp-display text-[20px] text-(--lp-ink) sm:text-[24px]">
                What sits under those eight screens
              </p>
              {/* The counts differ because the axes differ, and a reader who is not
                  told that reads "ten" as the complete set and the eight tabs as a
                  subset of it. The tabs are screens; these are the technology beneath
                  them plus the work that never gets a screen of its own. */}
              <p className="mt-2 max-w-2xl text-[14px] leading-5 text-(--lp-muted)">
                The eight above are screens. These are the machinery underneath them, and the
                cross-cutting work that has no screen of its own.
              </p>
            </div>
            <dl className="grid border-l border-(--lp-line) sm:grid-cols-2">
              {capabilityList.map(([name, how]) => (
                <div
                  key={name}
                  data-stagger
                  className="lp-cell flex gap-3.5 border-b border-r border-(--lp-line) p-4 sm:p-5"
                >
                  <span aria-hidden="true" className="mt-[7px] size-2 shrink-0 bg-(--lp-accent)" />
                  <div className="min-w-0">
                    <dt className="text-[15px] font-semibold leading-snug text-(--lp-ink)">{name}</dt>
                    <dd className="mt-1.5 text-[13px] leading-5 text-(--lp-muted)">{how}</dd>
                  </div>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </section>

      {/* ── System design: the capabilities layout, mirrored ─────────────── */}
      {/* Same split as Capabilities, a tab list beside a composite card whose
          media panel sits above its copy, but flipped so that the card is on the
          left and the heading, intro and tabs are right-aligned on the right.
          A dark section, so lp-frame--dark: without it the side rails render in
          the light hairline colour against black. */}
      <section id="system" className="bg-(--lp-dark) text-white">
        <div className="lp-frame lp-frame--dark relative grid gap-10 px-4 py-16 sm:gap-14 sm:px-6 sm:py-24 lg:grid-cols-[1.35fr_1fr]">
          {/* The card is the diagram, nothing else. White edge to edge, padding
              included: these diagrams are drawn in a palette built for a white
              ground, and a white plate floating inside a dark panel framed them
              twice. The border is kept only so lp-card's hover can turn it accent. */}
          {/* From lg the white panel is taken out of flow (absolute inset-0), which
              is what keeps the card the same height as the tab list beside it. In
              flow, a tall diagram would drive the grid row and the card would run
              past the last tab; out of flow it contributes no height, so the row is
              sized by the tabs alone, and the card, being a grid item and so stretched
              by default, fills exactly that. The diagram then fits inside via
              max-h-full rather than setting the height itself.

              Below lg the columns stack, there is no sibling to match, and the panel
              goes back in flow on its own min-height. */}
          <div id="system-panel" data-reveal className="lp-card relative flex flex-col border border-(--lp-dark-line)">
            <Ticks solid bottom />
            <div
              key={activeSystem.id}
              className="lp-swap flex min-h-[420px] flex-1 items-center justify-center overflow-x-auto bg-white p-4 sm:min-h-[520px] sm:p-6 lg:absolute lg:inset-0 lg:min-h-0"
            >
              <SystemDiagramImage src={activeSystem.src} alt={activeSystem.alt} />
            </div>
          </div>

          {/* order-first below lg so the heading still introduces the card on a
              phone, rather than arriving underneath it. */}
          <div data-reveal className="order-first flex flex-col items-end text-right lg:order-last">
            <Eyebrow>System design</Eyebrow>
            <h2 className="mt-6 text-[30px] text-white sm:text-[44px]">
              Thirteen layers,{" "}<br />one <Box fill>path through.</Box>
            </h2>
            <p className="mt-6 max-w-md text-[16px] leading-6 text-(--lp-dark-muted)">
              A document goes in at one end and comes out as an answer someone can act on. Open a
              block to see what it is made of, and the rule it has to follow.
            </p>

            <div className="mt-10 w-full">
              {systemDesign.map((item, index) => {
                const on = index === systemTab;
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-pressed={on}
                    aria-controls="system-panel"
                    onClick={() => setSystemTab(index)}
                    className="relative block w-full border-b border-(--lp-dark-line) py-4 pr-3 text-right"
                  >
                    {/* Mirror of the Capabilities tab, on dark tokens: at 20px
                        this is not "large text", but --lp-accent clears 4.5:1
                        against --lp-dark, so it qualifies here where it would
                        not on the light band. */}
                    <span
                      className={`lp-display text-[20px] transition-colors duration-[240ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${on ? "font-medium text-(--lp-accent)" : "text-(--lp-dark-muted) hover:font-medium hover:text-white"}`}
                    >
                      {item.name}
                    </span>
                    <span
                      aria-hidden="true"
                      className={`absolute -bottom-px right-0 h-0.5 bg-(--lp-accent) transition-all duration-[240ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${on ? "w-4/5" : "w-0"}`}
                    />
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ── Use cases: full-bleed tab bar over a media panel ───────────── */}
      <section id="field" className="border-t border-(--lp-line)">
        <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
          <Ticks />
          <div data-reveal>
            <Eyebrow>Use cases</Eyebrow>
            <h2 className="mt-6 text-[30px] text-(--lp-ink) sm:text-[44px]">
              Built for the <Box>way plants <span className="text-(--lp-accent)">actually run.</span></Box>
            </h2>
          </div>

          <div data-reveal className="mt-10">
            <div className="grid grid-cols-2 gap-px bg-(--lp-tab-line) sm:grid-cols-3 lg:grid-cols-6">
              {audiences.map((item, index) => {
                const on = index === audience;
                return (
                  <button
                    key={item.name}
                    type="button"
                    aria-pressed={on}
                    aria-controls="audience-panel"
                    onClick={() => setAudience(index)}
                    className={`min-h-16 px-4 py-5 text-center text-[15px] font-medium transition-colors ${on ? "bg-(--lp-accent-strong) text-white" : "bg-(--lp-tab) text-(--lp-ink) hover:bg-(--lp-tab-hover)"}`}
                  >
                    {item.name}
                  </button>
                );
              })}
            </div>

            <div id="audience-panel" className="lp-media lp-dither relative p-4 sm:p-8">
              <div key={audiences[audience].name} className="lp-swap">
                <div className="max-w-2xl">
                  <h3 className="text-[24px] text-white sm:text-[32px]">{audiences[audience].title}</h3>
                  <p className="mt-3 text-[15px] leading-6 text-white/85">{audiences[audience].body}</p>
                </div>
                <div className="mt-6 border border-white/20 p-2 sm:p-3">
                  <Shot src={audiences[audience].shot} alt={`Kairos workspace: ${audiences[audience].title.toLowerCase()}`} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Evals: a real chart, on dark ───────────────────────────────── */}
      <section id="evidence" className="bg-(--lp-dark) text-white">
        <div className="lp-frame lp-frame--dark px-4 py-16 sm:px-6 sm:py-24">
          <div data-reveal>
            <Eyebrow>Evals</Eyebrow>
            <h2 className="mt-6 max-w-3xl text-[30px] sm:text-[44px]">
              No empty promises.{" "}<br />
              <Box fill>Provenance at 100%.</Box>
            </h2>
            <p className="mt-6 max-w-xl text-[16px] leading-6 text-(--lp-dark-muted)">
              Forty-six domain-expert questions, written against a fixed answer key, across
              fifteen categories and run against the live stack. Higher is better.
            </p>
          </div>

          <div data-reveal className="mt-14">
            <p className="text-[11px] uppercase tracking-[0.12em] text-(--lp-dark-muted)">Graded outcomes, 46 questions</p>

            {/* pt-24 reserves room for the badge, value and sub-line stacked
                above each bar; a 100% bar would otherwise push them off. */}
            <div className="mt-6 flex gap-3 pt-24 sm:gap-5">
              {/* y axis every 10, labels centred on their gridline */}
              <div className="relative h-[460px] w-7 shrink-0" aria-hidden="true">
                {[100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 0].map((n) => (
                  <span
                    key={n}
                    className="absolute right-0 translate-y-1/2 text-[11px] leading-none text-(--lp-dark-muted)"
                    style={{ bottom: `${n}%` }}
                  >
                    {n}
                  </span>
                ))}
              </div>

              <div className="relative min-w-0 flex-1">
                <div
                  aria-hidden="true"
                  className="absolute inset-0 border-b border-l border-(--lp-dark-line)"
                  style={{
                    backgroundImage: "linear-gradient(to top, var(--lp-dark-line) 1px, rgb(0 0 0 / 0) 1px)",
                    backgroundSize: "100% 10%",
                  }}
                />
                <ul className="relative grid h-[460px] grid-cols-3">
                  {evalBars.map((bar) => (
                    <li key={bar.label} className="relative">
                      <div
                        className={`lp-bar absolute inset-x-[24%] bottom-0 ${bar.hero ? "lp-bar--hero lp-dither" : "bg-(--lp-bar-idle)"}`}
                        style={{ height: `${bar.value}%` }}
                      />

                      <div className="absolute inset-x-0 text-center" style={{ bottom: `calc(${bar.value}% + 14px)` }}>
                        <span className={`inline-block px-2 py-0.5 text-[10px] font-semibold tracking-[0.04em] ${bar.hero ? "bg-(--lp-accent-strong) text-white" : "text-(--lp-dark-muted)"}`}>
                          {bar.badge}
                        </span>
                        <p className={`lp-display mt-1.5 text-[26px] sm:text-[32px] ${bar.hero ? "text-white" : "text-(--lp-dark-muted)"}`}>
                          {bar.display}
                        </p>
                        <p className="mt-1 text-[11px] text-(--lp-dark-muted)">{bar.sub}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* x axis */}
            <div className="ml-10 grid grid-cols-3 pt-4">
              {evalBars.map((bar) => (
                <div key={bar.label} className="text-center">
                  <p className={`text-[14px] font-semibold ${bar.hero ? "text-(--lp-accent)" : "text-white"}`}>{bar.label}</p>
                  <p className="mt-1 text-[12px] text-(--lp-dark-muted)">{bar.note}</p>
                </div>
              ))}
            </div>
            <p className="mt-8 max-w-2xl text-[13px] leading-5 text-(--lp-dark-muted)">
              One run: all 40 answers came from the pinned Nemotron 3 Super model on NVIDIA NIM, with
              no fallback provider. Six safety-critical questions were refused because no authoritative source
              covers them, and a correct refusal is graded as correct. Three of the four misses
              retrieved the right evidence, so the gap there is in how the answer is written. The
              fourth asks about a procedure the vault marks as superseded, so it is correctly not
              answered from it.
            </p>
          </div>

          {/* The rest of the harness. Hairlines are drawn per cell rather than by a
              gap-px mesh over a tinted container: the suite count is data and does not
              divide evenly into two or three columns, and a mesh paints its container
              colour into whatever cells the last row leaves over, leaving a grey block
              where a card should be. Per-cell borders leave that space as section ground. */}
          <div data-reveal className="mt-16">
            <p className="text-[11px] uppercase tracking-[0.12em] text-(--lp-dark-muted)">The rest of the harness</p>
            <div className="mt-6 grid border-t border-l border-(--lp-dark-line) sm:grid-cols-2 lg:grid-cols-3">
              {evalSuites.map((suite) => (
                <div key={suite.name} data-stagger className="lp-cell lp-cell--dark border-b border-r border-(--lp-dark-line) bg-(--lp-dark) p-5">
                  <p className="text-[11px] uppercase tracking-[0.08em] text-(--lp-dark-muted)">{suite.name}</p>
                  <p className="lp-display mt-3 text-[32px] text-white">
                    {suite.headline}
                  </p>
                  <p className="mt-1 text-[12px] text-(--lp-accent)">{suite.headlineNote}</p>
                  <dl className="mt-4 space-y-1.5 border-t border-(--lp-dark-line) pt-3 text-[12px]">
                    {suite.rows.map(([term, value]) => (
                      <div key={term} className="flex justify-between gap-3">
                        <dt className="text-(--lp-dark-muted)">{term}</dt>
                        <dd className="text-right font-semibold text-white">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}

              {/* Ten suites into three columns leaves one card alone with two dead
                  cells beside it. This is one cell spanning both of them, so the last
                  row closes. It is filled rather than another stat card on purpose:
                  the grid states ten results, and the one thing none of them say is
                  how a result is decided, which is the claim the whole section rests on.

                  sm:col-span-2 covers lg too: at two columns it takes the last row,
                  at three it takes the two cells the tenth card leaves over. */}
              <div
                data-stagger
                className="border-b border-r border-(--lp-dark-line) bg-(--lp-accent-strong) p-5 sm:col-span-2"
              >
                <p className="text-[11px] uppercase tracking-[0.08em] text-white">How every one of these is graded</p>
                <p className="lp-display mt-3 text-[26px] leading-tight text-white sm:text-[30px]">
                  Fixed rules, never another model.
                </p>
                <p className="mt-3 max-w-2xl text-[13px] leading-5 text-white">
                  An answer has to contain the facts the question requires, avoid the ones it rules
                  out, and cite a source. Miss any of the three and it counts as wrong. The same rules
                  run every time, so two runs of the same question are always scored the same way.
                </p>
              </div>
            </div>
          </div>


        </div>
      </section>

      {/* ── Provenance ──────────────────────────────────────────────────── */}
      <section id="provenance" className="lp-band border-t border-(--lp-line)">
        <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
          <Ticks />
          <div data-reveal>
            <Eyebrow>Provenance</Eyebrow>
            <h2 className="mt-6 max-w-4xl text-[30px] text-(--lp-ink) sm:text-[44px]">
              No <Box>claim</Box> without its <Box fill>source.</Box>
            </h2>
            <p className="mt-6 max-w-xl text-[16px] leading-6 text-(--lp-muted)">
              Every fact in the graph carries six properties on the link itself. That is what lets you
              check an answer, undo a replacement, and tell an uncertain guess apart from a verified
              fact.
            </p>
          </div>

          <div data-reveal className="lp-media lp-dither relative mt-12 p-3 sm:p-6">
            <div className="border border-white/20 p-2 sm:p-3">
              <Shot src="graph" alt="The Kairos knowledge graph: assets and facts joined by time-aware edges, each carrying its source and authority." />
            </div>
          </div>

          {/* The six properties against one real fact rather than in the abstract.
              A bare name-and-definition list asks the reader to imagine what a
              stored fact looks like; this shows them one, so "checkable" stops
              being a claim and becomes something they can read off the page.

              The fact sits in the accent header of the same panel, so the six rows
              below are visibly properties OF it rather than six loose definitions. */}
          <div data-reveal className="lp-card mt-12 border border-(--lp-line) bg-(--lp-surface)">
            <div className="border-b border-(--lp-line) bg-(--lp-accent-strong) px-5 py-4 sm:px-7">
              {/* Full white, not white/80: at 11px this is small text, and 80% over
                  --lp-accent-strong lands at 3.7:1 where it needs 4.5. The hierarchy
                  against the line below comes from size and weight instead. */}
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white">
                One fact, and everything it carries
              </p>
              <p className="lp-display mt-2 text-[19px] leading-tight text-white sm:text-[22px]">
                The EQ-101 seal specification was superseded on 15 January 2025.
              </p>
            </div>

            <dl className="grid sm:grid-cols-2">
              {edgeProperties.map(({ name, value, note }) => (
                <div
                  key={name}
                  /* Every cell keeps its bottom rule and the footer keeps none, so the
                     divider above the footer is one hairline at every breakpoint rather
                     than two stacked ones once the grid drops to a single column. */
                  className="border-b border-(--lp-line) px-5 py-5 sm:px-7 sm:[&:nth-child(odd)]:border-r"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <dt>
                      {/* <code>: these are literal property names on the edge, not prose. */}
                      <code className="text-[13px] font-semibold tracking-tight text-(--lp-accent-text)">{name}</code>
                    </dt>
                    {/* tabular-nums so the dates and scores line up down the column. */}
                    <dd className="lp-display text-[15px] tabular-nums text-(--lp-ink)">{value}</dd>
                  </div>
                  <dd className="mt-2 text-[13px] leading-5 text-(--lp-muted)">{note}</dd>
                </div>
              ))}
            </dl>

            <p className="bg-(--lp-band) px-5 py-3 text-[12px] text-(--lp-muted) sm:px-7">
              An illustrative fact. Every real one in the graph carries the same six.
            </p>
          </div>
        </div>
      </section>
      {/* ── FAQ: two columns, category rail then the answers ──────────── */}
      <section id="faq" className="bg-(--lp-dark) text-white">
        <div className="lp-frame lp-frame--dark px-4 py-16 sm:px-6 sm:py-24">
          <div data-reveal>
            <Eyebrow>FAQ</Eyebrow>
            <h2 className="mt-6 max-w-2xl text-[30px] sm:text-[44px]">
              Your questions,{" "}<br /><Box fill>answered.</Box>
            </h2>
            <p className="mt-6 max-w-md text-[15px] leading-6 text-(--lp-dark-muted)">
              The things people ask before they trust a system with a safety case. Still curious?
              Read the documentation, or open the workspace and try it yourself.
            </p>
            <Link
              href="/docs"
              className="mt-6 inline-flex items-center gap-2.5 border border-(--lp-dark-line) px-4 py-2.5 text-[14px] text-white transition-colors duration-150 hover:border-(--lp-accent)"
            >
              Read documentation
              <span aria-hidden="true" className="text-(--lp-accent)">›</span>
            </Link>
          </div>

          <div data-reveal className="mt-12 grid gap-10 lg:grid-cols-[0.8fr_1.4fr]">
            <div className="lp-dashed border-t">
              {faqGroups.map((group, index) => {
                const on = index === faqGroup;
                return (
                  <button
                    key={group.name}
                    type="button"
                    aria-pressed={on}
                    aria-controls="faq-answers"
                    onClick={() => setFaqGroup(index)}
                    className="lp-dashed flex w-full items-center justify-between border-b py-6 text-left"
                  >
                    <span className={`lp-display text-[26px] transition-colors sm:text-[32px] ${on ? "text-white" : "text-(--lp-dark-muted) hover:text-white"}`}>
                      {group.name}
                    </span>
                    <span aria-hidden="true" className={`text-[18px] transition-transform ${on ? "rotate-90 text-(--lp-accent)" : "text-(--lp-dark-muted)"}`}>›</span>
                  </button>
                );
              })}
            </div>

            <div id="faq-answers" className="lp-dashed border-t">
              <div key={faqGroups[faqGroup].name} className="lp-swap">
                {faqGroups[faqGroup].items.map(([question, answer], index) => (
                  <details key={question} className="lp-dashed group border-b" open={index === 0}>
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-[17px] font-medium text-white marker:hidden hover:text-(--lp-accent)">
                      {question}
                      <span aria-hidden="true" className="shrink-0 text-[20px] text-(--lp-accent) transition-transform group-open:rotate-45">+</span>
                    </summary>
                    <p className="max-w-2xl pb-6 text-[15px] leading-6 text-(--lp-dark-muted)">{answer}</p>
                  </details>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Tech stack band, directly above the footer as on the reference: one
          continuous full-bleed strip, no framed label floating over a
          full-bleed row. Hovering pauses the scroll. */}
      {/* Tech roller, built the way the reference builds its marquee band:
          a light outer band whose padding is what separates the strip from the
          dark section above and the footer below, wrapping a dark inner strip.
          No borders; the light band does that job. Items are mx-9 / gap-9 at
          32px, and the track translates exactly -50%. */}
      <div aria-hidden="true" className="overflow-hidden bg-(--lp-band) py-2">
        <div className="overflow-hidden bg-(--lp-dark) py-2.5">
          {/* Each half must be at least as wide as the viewport or the -50%
              slide opens a gap at the right edge. */}
          <div className="lp-marquee-track flex w-max whitespace-nowrap">
            {[...techStack, ...techStack].map((tech, i) => (
              <span key={`${tech.name}-${i}`} className="mx-9 flex items-center gap-9 text-[32px] text-white">
                <TechLogo tech={tech} />
                {tech.name}
              </span>
            ))}
          </div>
        </div>
      </div>
      <p className="sr-only">Built with {techStack.map((t) => t.name).join(", ")}.</p>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="bg-(--lp-bg)">
        <div className="lp-frame px-4 py-14 sm:px-6">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[2fr_repeat(3,0.6fr)]">
            <div>
              <div className="flex items-center gap-2.5">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/logo.png" alt="" width={26} height={26} className="object-cover" />
                <span className="lp-display text-[22px] text-(--lp-ink)">Kairos</span>
              </div>
              <p className="mt-4 max-w-xs text-[14px] leading-5 text-(--lp-muted)">
                The right knowledge to the right person at the moment of action.
              </p>
            </div>

            {footerColumns.map(({ heading, links }) => (
              <div key={heading}>
                <p className="lp-display text-[18px] text-(--lp-ink)">{heading}</p>
                <ul className="mt-4 space-y-2.5">
                  {links.map(([label, href]) => (
                    <li key={href}>
                      {href.startsWith("/") ? (
                        <Link href={href} className="text-[14px] text-(--lp-muted) transition-colors hover:text-(--lp-accent-text)">{label}</Link>
                      ) : (
                        <a
                          href={href}
                          {...(href.startsWith("http") ? { target: "_blank", rel: "noreferrer noopener" } : {})}
                          className="text-[14px] text-(--lp-muted) transition-colors hover:text-(--lp-accent-text)"
                        >
                          {label}
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}

          </div>
        </div>

        {/* Full-width divider — lives outside lp-frame so it runs edge-to-edge */}
        <div className="border-t border-(--lp-line)" />

        <div className="lp-frame px-4 pb-8 pt-6 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-[12px] uppercase tracking-[0.08em] text-(--lp-muted)">
              © 2026 Kairos Inc
            </p>
            <div className="flex items-center gap-2">
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noreferrer noopener"
                aria-label="Kairos on GitHub"
                className="grid size-9 place-items-center bg-(--lp-ink) text-white transition-colors hover:bg-(--lp-accent-strong)"
              >
                <GithubIcon />
              </a>
              <a
                href={demoVideoId ? `https://www.youtube.com/watch?v=${demoVideoId}` : DEMO_FALLBACK_URL}
                target="_blank"
                rel="noreferrer noopener"
                aria-label="Watch the Kairos demo"
                className="grid size-9 place-items-center bg-[#ff0000] text-white transition-opacity hover:opacity-80"
              >
                <YoutubeIcon />
              </a>
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}
