// Moved out of app/page.tsx (2,205 lines): the landing page imports these. Presentational only.
/* ── Capability mocks, one bespoke composition each ─────────────────────
   Shared atoms only; the layouts deliberately differ so the tab list reveals a
   genuinely different picture each time rather than the same card retitled. */

/** White chip used across the mocks. */
function Slab({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`lp-mock-sm bg-white px-3 py-2 text-[12px] text-(--lp-ink) ${className}`}>{children}</div>;
}

/** Briefs: a governor meter: six slots an hour, with PTW bypassing the gate. */
export function BriefsMock() {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Governor · this hour</p>
      <div className="mt-3 flex gap-1.5">
        {[true, true, true, true, false, false].map((used, i) => (
          <span key={i} className={`h-8 flex-1 ${used ? "bg-white" : "border border-white/45 bg-white/10"}`} />
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-white/80">
        <span>4 of 6 delivered</span>
        <span>2 remaining</span>
      </div>

      <div className="mt-6 grid gap-2 sm:grid-cols-2">
        <Slab>
          <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">Dispatched 07:41</p>
          <p className="mt-1 font-semibold">P-1101A isolation changed</p>
          <p className="mt-1 text-[11px] text-(--lp-muted)">Rank 1 · to the duty operator</p>
        </Slab>
        <Slab className="border-l-4 border-(--lp-accent)">
          <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">Permit to work</p>
          <p className="mt-1 font-semibold">Bypasses the governor</p>
          <p className="mt-1 text-[11px] text-(--lp-muted)">Safety work is never rate-limited</p>
        </Slab>
      </div>

      <div className="mt-4 flex items-center gap-2 bg-black/45 px-3 py-2">
        <span aria-hidden="true" className="size-2 shrink-0 bg-(--lp-accent)" />
        <span className="text-[11px] text-white/85">Brief 7 held until 08:00, quota reached and not urgent</span>
      </div>
    </div>
  );
}

/** Copilot: question, governed answer, and the refusal path beside it. */
export function CopilotMock() {
  return (
    <div>
      <div className="ml-auto w-fit max-w-[85%] bg-black/55 px-3 py-2 text-[12px] text-white">
        What changed on P-1101A since the last turnaround?
      </div>

      <div className="mt-3 max-w-[92%] border-l-2 border-(--lp-accent) bg-white p-3">
        <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">Checked answer</p>
        <div className="mt-2 space-y-1.5" aria-hidden="true">
          <span className="block h-1.5 bg-(--lp-band)" />
          <span className="block h-1.5 w-5/6 bg-(--lp-band)" />
          <span className="block h-1.5 w-2/3 bg-(--lp-band)" />
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
          <span className="bg-(--lp-accent-strong) px-2 py-1 font-medium text-white">3 sources</span>
          <span className="border border-(--lp-line) px-2 py-1 text-(--lp-muted)">Authority: regulation</span>
        </div>
        <div className="mt-3">
          <div className="flex justify-between text-[10px] text-(--lp-muted)"><span>Confidence</span><span className="font-semibold text-(--lp-ink)">0.91</span></div>
          <div className="mt-1 h-1.5 bg-(--lp-band)"><span className="block h-full w-[91%] bg-(--lp-accent)" /></div>
        </div>
      </div>

      <div className="mt-3 flex items-start gap-2 border border-dashed border-white/50 px-3 py-2">
        <span aria-hidden="true" className="mt-0.5 size-2 shrink-0 bg-white" />
        <span className="text-[11px] leading-4 text-white/85">
          Thin evidence on a safety question returns a <strong className="font-semibold text-white">refusal card</strong>, with its sources, never a hedge.
        </span>
      </div>
    </div>
  );
}

/**
 * Assets: a time slider over a small graph, with one edge superseded. Both edges
 * are real: V-247's isolation boundary is engineer-verified P&ID topology, and
 * FSL-2240A → FSL-2240B is the seal supersession the golden dataset is built
 * around (`FP-SB-2025-04`, 15 Jan 2025).
 */
export function AssetsMock() {
  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Graph as of</p>
        <span className="bg-black/60 px-2 py-1 text-[11px] font-semibold text-white">2025-05-15</span>
      </div>

      <div className="relative mt-3 h-1 bg-white/30">
        <span aria-hidden="true" className="absolute left-[62%] top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 bg-(--lp-accent)" />
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] uppercase tracking-[0.06em] text-white/70">
        <span>Commissioned</span><span>Now</span>
      </div>

      <div className="mt-6 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
        <Slab className="text-center font-semibold">V-247</Slab>
        <div className="text-center">
          <p className="text-[9px] uppercase tracking-[0.06em] text-white/80">isolated by</p>
          <div aria-hidden="true" className="my-1 h-px bg-(--lp-accent)" />
          <p className="text-[9px] text-white/70">verified</p>
        </div>
        <Slab className="text-center font-semibold">XV-203</Slab>
      </div>

      <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-2 opacity-55">
        <Slab className="text-center line-through">FSL-2240A</Slab>
        <div className="text-center">
          <p className="text-[9px] uppercase tracking-[0.06em] text-white/80">superseded</p>
          <div aria-hidden="true" className="my-1 h-px border-t border-dashed border-white/70" />
          <p className="text-[9px] text-white/70">valid_to closed</p>
        </div>
        <Slab className="text-center font-semibold">FSL-2240B</Slab>
      </div>

      <p className="mt-4 bg-black/45 px-3 py-2 text-[11px] text-white/85">
        Nothing was deleted. The old part number still answers questions about the May 2025 repair.
      </p>
    </div>
  );
}

/** Governance: a one-way gate splitting the stream by confidence. */
export function GovernanceMock() {
  const rows = [
    ["Pump seal plan", "0.94", true],
    ["Vendor torque spec", "0.61", false],
    ["Scanned margin note", "0.42", false],
  ] as const;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Extraction · confidence gate at 0.70</p>
      <div className="mt-3 space-y-1.5">
        {rows.map(([name, score, promoted]) => (
          <div key={name} className="grid grid-cols-[1fr_auto_auto] items-center gap-2 bg-white px-3 py-2">
            <span className="truncate text-[12px] text-(--lp-ink)">{name}</span>
            <span className={`text-[12px] font-semibold ${promoted ? "text-(--lp-ink)" : "text-(--lp-accent-text)"}`}>{score}</span>
            <span className={`px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.06em] ${promoted ? "bg-(--lp-band) text-(--lp-muted)" : "bg-(--lp-accent-strong) text-white"}`}>
              {promoted ? "Graph" : "Held"}
            </span>
          </div>
        ))}
      </div>

      {/* Counted off the rows above rather than typed in: a tile that disagreed
          with the three lines directly over it is the one thing this panel
          cannot afford to get wrong. */}
      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="border border-white/40 px-3 py-2.5 text-center">
          <p className="lp-display text-[24px] text-white">{rows.filter(([, , promoted]) => promoted).length}</p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-white/75">Into the graph</p>
        </div>
        <div className="bg-white px-3 py-2.5 text-center">
          <p className="lp-display text-[24px] text-(--lp-accent-text)">{rows.filter(([, , promoted]) => !promoted).length}</p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-(--lp-muted)">Held for review</p>
        </div>
      </div>
      <p className="mt-3 text-center text-[11px] text-white/85">Promotion is a human decision. There is no auto-promote.</p>
    </div>
  );
}

/** Field capture: a device with a mic and an offline write queue. */
export function FieldMock() {
  const queue = [
    ["Seal weep on P-1101A", "Sent"],
    ["Gasket weep, WO-4471", "Queued"],
    ["Photo · gauge reading", "Queued"],
  ] as const;
  return (
    <div className="grid gap-5 sm:grid-cols-[auto_1fr] sm:items-start">
      <div className="mx-auto w-[132px] border-2 border-white/60 bg-black/55 p-3 sm:mx-0">
        <p className="text-center text-[9px] uppercase tracking-[0.08em] text-(--lp-accent)">● Offline</p>
        <div className="mt-4 grid place-items-center">
          <span className="grid size-14 place-items-center rounded-full bg-(--lp-accent) text-white">
            <svg width="18" height="22" viewBox="0 0 20 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <rect x="6" y="1" width="8" height="14" rx="4" />
              <path d="M3 11a7 7 0 0 0 14 0M10 18v5" />
            </svg>
          </span>
        </div>
        <p className="mt-3 text-center text-[10px] font-medium text-white">Hold to record</p>
      </div>

      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Write queue · on device</p>
        <div className="mt-3 space-y-1.5">
          {queue.map(([text, state]) => (
            <div key={text} className="flex items-center justify-between gap-2 bg-white px-3 py-2">
              <span className="truncate text-[12px] text-(--lp-ink)">{text}</span>
              <span className={`shrink-0 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.06em] ${state === "Sent" ? "bg-(--lp-band) text-(--lp-muted)" : "bg-(--lp-accent-strong) text-white"}`}>
                {state}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-4 bg-black/45 px-3 py-2 text-[11px] text-white/85">
          Transcribed and tagged on the device. Sent the moment the radio returns.
        </p>
      </div>
    </div>
  );
}

/** Ingestion: the heterogeneous-input claim, shown as six formats into one graph. */
export function IngestionMock() {
  // The PS names six input classes. All six are handled, so all six are shown:
  // spreadsheets and email archives are the two people assume you skipped.
  const inputs = [
    ["Native PDF", "Parsed direct · no API cost"],
    ["Scanned form", "OCR, multi-script"],
    ["P&ID drawing", "Computer vision"],
    ["Spreadsheet", "xlsx · xls · ods"],
    ["Email archive", "eml · mbox + attachments"],
    ["Voice note", "Speech to text"],
  ] as const;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">One pipeline · six kinds of source</p>
      <div className="mt-3 grid gap-1.5 sm:grid-cols-2">
        {inputs.map(([name, how]) => (
          <Slab key={name}>
            <p className="font-semibold">{name}</p>
            <p className="mt-0.5 text-[11px] text-(--lp-muted)">{how}</p>
          </Slab>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-2 text-[10px] uppercase tracking-[0.06em] text-white/80">
        <span aria-hidden="true" className="h-px flex-1 bg-(--lp-accent)" />
        <span>extract · link · index</span>
        <span aria-hidden="true" className="h-px flex-1 bg-(--lp-accent)" />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-1.5 text-center">
        {[["Neo4j", "graph"], ["Qdrant", "meaning"], ["Elastic", "exact"]].map(([store, role]) => (
          <div key={store} className="border border-white/40 px-2 py-2.5">
            <p className="text-[12px] font-semibold text-white">{store}</p>
            <p className="mt-0.5 text-[10px] text-white/70">{role}</p>
          </div>
        ))}
      </div>

      <p className="mt-4 bg-black/45 px-3 py-2 text-[11px] text-white/85">
        Six formats, one path. A voice note and a P&amp;ID land in the same three stores, so either can answer the same question.
      </p>
    </div>
  );
}

/** RCA: hypotheses ranked by evidence weight, with the timeline behind them. */
export function RcaMock() {
  const hypotheses = [
    ["Thermal cycling fatigue", 82, "3 prior failures · telemetry"],
    ["Superseded seal variant", 61, "OEM bulletin FP-SB-2025-04"],
    ["Bearing housing clearance", 28, "1 unverified field note"],
  ] as const;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Ranked by evidence weight, not by guess</p>
      <div className="mt-3 space-y-2">
        {hypotheses.map(([name, weight, basis]) => (
          <div key={name} className="bg-white px-3 py-2">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[12px] font-semibold text-(--lp-ink)">{name}</span>
              <span className="text-[12px] font-semibold text-(--lp-accent-text)">{weight}</span>
            </div>
            <div className="mt-1.5 h-1.5 bg-(--lp-band)">
              <span className="block h-full bg-(--lp-accent)" style={{ width: `${weight}%` }} />
            </div>
            <p className="mt-1.5 text-[10px] text-(--lp-muted)">{basis}</p>
          </div>
        ))}
      </div>
      <p className="mt-4 bg-black/45 px-3 py-2 text-[11px] text-white/85">
        Every hypothesis carries the documents behind it. Thin evidence ranks low rather than disappearing.
      </p>
    </div>
  );
}

/**
 * Compliance: clause-scoped coverage in the three states the API actually
 * returns. Every row is a real finding from `GET /compliance/gaps` on the golden
 * dataset, and the clause numbers belong to the framework they are labelled
 * with: 4.x is OISD-117, 8.x to 10.x is ISO 45001 (`seed_regulations.py`).
 */
export function ComplianceMock() {
  const clauses = [
    ["OISD-117 · 4.1.1", "EQ-101", "Covered"],
    ["ISO 45001 · 9.1.1", "EQ-102", "Gap"],
    ["OISD-117 · 4.1.2", "EQ-101", "Unverified"],
  ] as const;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Clause × asset · continuously mapped</p>
      <div className="mt-3 space-y-1.5">
        {clauses.map(([clause, asset, state]) => (
          <div key={clause} className="grid grid-cols-[1fr_auto_auto] items-center gap-2 bg-white px-3 py-2">
            <span className="truncate text-[12px] text-(--lp-ink)">{clause}</span>
            <span className="text-[11px] text-(--lp-muted)">{asset}</span>
            <span
              className={`px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.06em] ${state === "Gap"
                ? "bg-(--lp-accent-strong) text-white"
                : state === "Unverified"
                  ? "border border-(--lp-accent) text-(--lp-accent-text)"
                  : "bg-(--lp-band) text-(--lp-muted)"
                }`}
            >
              {state}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="bg-white px-3 py-2.5 text-center">
          <p className="lp-display text-[24px] text-(--lp-ink)">1.000</p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-(--lp-muted)">Precision, 52 pairs</p>
        </div>
        <div className="border border-white/40 px-3 py-2.5 text-center">
          <p className="lp-display text-[24px] text-white">0</p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-white/75">False positives</p>
        </div>
      </div>
      <p className="mt-3 text-center text-[11px] text-white/85">A gap means no document of that clause&apos;s required type is linked to that asset. Evidence nobody has verified is called out, never counted as covered.</p>
    </div>
  );
}
