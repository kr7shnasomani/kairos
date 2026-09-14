"use client";

import { PageHeader } from "@/components/ui";
import { SystemTabs } from "@/components/system-tabs";

// How Kairos works — a static, visual explainer. No data fetching; informational only.

const PIPELINE: { n: string; title: string; body: string; tech: string[] }[] = [
  { n: "1", title: "Ingest & perceive", body: "Documents, operational events, and voice notes enter through one gate. OCR and NER lift entities from unstructured text; P&ID drawings are parsed into topology.", tech: ["NVIDIA NIM", "Groq Whisper", "Jina embeddings"] },
  { n: "2", title: "Link into the graph", body: "Extracted facts become time-bounded edges. Each edge carries six governance properties, so the graph answers what was known on any past date.", tech: ["Neo4j", "temporal edges"] },
  { n: "3", title: "Govern", body: "Nothing unverified reaches an operator by accident. Conflicts, quarantine, Management of Change, an SPC circuit breaker, and a model gate hold the line.", tech: ["OPA", "human-in-the-loop"] },
  { n: "4", title: "Retrieve", body: "Hybrid retrieval across graph, vector, and exact search. Synthesis assembles a cited answer, refusing outright on safety-critical parameters.", tech: ["Qdrant", "Elasticsearch", "NIM synthesis"] },
  { n: "5", title: "Deliver", body: "Operational events assemble proactive briefs, governed by an EEMUA-191 push ceiling, reaching the field on a mobile-first, offline-capable interface.", tech: ["Redis Streams", "Temporal", "PWA"] },
];

const LAYERS: { n: number; name: string; body: string }[] = [
  { n: 0, name: "Empirical Validation & Model Safety", body: "Rolling validation corpus + model gate; tracks the system's own track record." },
  { n: 1, name: "Deterministic Identity & MDM", body: "Human-confirmed canonical asset IDs. Never AI-inferred. Always MERGE." },
  { n: 2, name: "Immutable Evidence Vault", body: "Byte-for-byte storage, SHA-256 dedup. Superseded, never deleted." },
  { n: 3, name: "Multimodal Perception Engine", body: "OCR, NER, and P&ID topology from PDFs, scans, handwriting, and voice." },
  { n: 4, name: "Temporal Reality Graph", body: "Every fact is a time-bounded, authority-ranked edge with provenance." },
  { n: 5, name: "Zero-Copy OT Virtualization", body: "Reads historian telemetry in-memory; raw signals are never stored." },
  { n: 6, name: "Quarantine Knowledge Layer", body: "Low-confidence inputs wait here. One-way gate — human promotion only." },
  { n: 7, name: "Dual-Track Governance", body: "Administrative vs engineering conflicts; MoC, circuit breaker, adjudication." },
  { n: 8, name: "Event Subscription & Delivery", body: "Detects events on Redis Streams; proactive briefs under an EEMUA-191 ceiling." },
  { n: 9, name: "Structured Knowledge Elicitation", body: "AI micro-interviews and off-boarding programmes capture tribal knowledge." },
  { n: 10, name: "Outcome Attribution & Learning", body: "Grounds recommendations against post-action telemetry to close the loop." },
  { n: 11, name: "Reasoning & Synthesis", body: "Assembles cited answers, RCA packs, and briefs. Never originates knowledge." },
  { n: 12, name: "Phased Deployment & Interface", body: "Shadow → assist → proactive. Point-of-action UI on field and desktop." },
];

const PRINCIPLES: { title: string; body: string }[] = [
  { title: "Never assert without provenance", body: "Every answer, brief, and hypothesis carries its source documents and an authority badge." },
  { title: "Never auto-promote unverified input", body: "Field inputs sit in a one-way quarantine. Only a human promotes them to the canonical graph." },
  { title: "Refuse rather than hedge", body: "On a safety-critical query with weak evidence, the copilot returns an explicit refusal, never a plausible guess." },
];

const STACK: { group: string; items: string[] }[] = [
  { group: "Backend", items: ["FastAPI · Python 3.12", "Go (Gin) OT connectors", "Celery", "Temporal"] },
  { group: "Datastores", items: ["Neo4j", "Qdrant", "Elasticsearch", "Redis", "Supabase (Postgres)"] },
  { group: "Models (cloud)", items: ["NIM Nemotron 3 Super 120B", "Llama 3.2 11B Vision NER", "Nemotron OCR", "Jina v3 embed", "Groq Whisper"] },
  { group: "Frontend & Ops", items: ["Next.js 16 · React 19", "Tailwind v4", "OPA", "OTEL → Grafana"] },
];

function Arrow() {
  return (
    <svg className="hidden size-5 shrink-0 self-center text-muted lg:block" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

export default function SystemInformationPage() {
  return (
    <div className="w-full">
      <SystemTabs />
      <PageHeader
        eyebrow="Architecture"
        title="System Information"
        lede="How Kairos turns fragmented, tribal knowledge into governed, cited, point-of-action intelligence."
      />

      {/* Core principles */}
      <section className="mt-6">
        <div className="grid gap-3 sm:grid-cols-3">
          {PRINCIPLES.map((p) => (
            <div key={p.title} className="rounded-xl border border-line bg-surface p-4">
              <p className="text-body font-semibold text-ink">{p.title}</p>
              <p className="mt-1.5 text-caption leading-relaxed text-muted">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* The pipeline */}
      <section className="mt-8">
        <h2 className="text-label font-bold uppercase tracking-[0.1em] text-muted">The pipeline</h2>
        <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-stretch">
          {PIPELINE.map((s, i) => (
            <div key={s.n} className="flex flex-1 gap-3 lg:contents">
              <div className="flex flex-1 flex-col rounded-xl border border-line bg-surface p-4">
                <div className="flex items-center gap-2.5">
                  <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-accent text-label font-bold text-on-accent">{s.n}</span>
                  <p className="text-body font-semibold text-ink">{s.title}</p>
                </div>
                <p className="mt-2 flex-1 text-caption leading-relaxed text-muted">{s.body}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {s.tech.map((t) => (
                    <span key={t} className="rounded-md bg-surface-2 px-2 py-0.5 text-label text-muted">{t}</span>
                  ))}
                </div>
              </div>
              {i < PIPELINE.length - 1 && <Arrow />}
            </div>
          ))}
        </div>
      </section>

      {/* 13 layers */}
      <section className="mt-8">
        <h2 className="text-label font-bold uppercase tracking-[0.1em] text-muted">The 13 layers</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {LAYERS.map((l) => (
            <div key={l.n} className="flex gap-3 rounded-xl border border-line bg-surface p-4">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-2 text-caption font-bold tabular text-ink">{l.n}</span>
              <div className="min-w-0">
                <p className="text-body font-medium text-ink">{l.name}</p>
                <p className="mt-1 text-caption leading-relaxed text-muted">{l.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Tech stack */}
      <section className="mt-8">
        <h2 className="text-label font-bold uppercase tracking-[0.1em] text-muted">Technology</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {STACK.map((s) => (
            <div key={s.group} className="rounded-xl border border-line bg-surface p-4">
              <p className="text-label font-bold uppercase tracking-wide text-accent">{s.group}</p>
              <ul className="mt-2 space-y-1">
                {s.items.map((it) => (
                  <li key={it} className="text-caption text-muted">{it}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
