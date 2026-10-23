// Moved out of app/page.tsx (2,205 lines): the landing page imports these. Presentational only.
/**
 * Hero artwork. Designed rather than a screenshot, mirroring how the reference
 * leads with a rendered scene and saves product captures for the use-case
 * panels. It shows the actual claim: every source system the plant owns, wired
 * into one governed answer that carries its evidence on its face.
 *
 * The geometry is computed, never eyeballed. One ellipse defines everything —
 * where a chip sits, where its wire starts, where the rings are drawn — so a
 * chip can never drift off the orbit or a wire end up connected to nothing.
 * `ORBIT` is in the SVG's user units; the chips read the same points back as
 * percentages, and `preserveAspectRatio="none"` maps the viewBox onto the field
 * exactly, so the two coordinate systems stay locked together at any width.
 *
 * Layout is one tree, two shapes. Below `lg` the chips are a wrapped row above
 * the card; from `lg` up the wrapper becomes `display: contents` and each chip
 * takes its place on the ring from `--orbit-x` / `--orbit-y`. Same DOM, so the
 * card's text is never duplicated for a screen reader. The break is `lg` and
 * not `sm` because the orbit needs a chip's width clear either side of the
 * card: below roughly 1000px of panel the two collide.
 */
const ORBIT = {
  cx: 500,
  cy: 265,
  /* The chip ring. rx is capped near 41% of the field: any wider and the
     outermost chip's own width pushes it past the panel edge. */
  rx: 400,
  /* Tall enough that the 120°/60° pair clears the top of the answer card. The
     field is short, so this is the measurement the whole composition turns on. */
  ry: 256,
  /* Where the wires terminate: the same ellipse scaled down, which is what makes
     every spoke exactly radial. A third of the way in puts it well inside the
     answer card at every breakpoint, so all ten vanish beneath the card rather
     than stopping in mid-air against its edge. */
  hub: 0.33,
} as const;

/** A point on an ellipse concentric with the orbit. Degrees, 0° = due right. */
function orbitPoint(deg: number, rx: number, ry: number): [number, number] {
  const rad = (deg * Math.PI) / 180;
  return [ORBIT.cx + rx * Math.cos(rad), ORBIT.cy - ry * Math.sin(rad)];
}

/**
 * The spoke from a chip in to the hub. Start and end sit on concentric copies of
 * the same ellipse, so the line is exactly radial: ten spokes on one centre read
 * as a system converging, where ten curves crossing four rings read as clutter.
 */
function orbitWire(deg: number): string {
  const [x0, y0] = orbitPoint(deg, ORBIT.rx, ORBIT.ry);
  const [x1, y1] = orbitPoint(deg, ORBIT.rx * ORBIT.hub, ORBIT.ry * ORBIT.hub);
  return `M ${x0.toFixed(1)} ${y0.toFixed(1)} L ${x1.toFixed(1)} ${y1.toFixed(1)}`;
}

/**
 * Five sources a side, mirrored across the vertical, which is what makes the ring
 * read as deliberate. They span 60° either side of horizontal rather than the
 * full 90°: the field is twice as wide as it is tall, so equal angles bunch the
 * top and bottom pairs against the card while leaving the flanks empty. `cited` marks the three the
 * answer card actually stands on: those get the accent wire and the pulse, the
 * other seven stay connected but quiet. Array order is the phone reading order,
 * where the ring collapses to a wrapped row.
 */
const heroSources: { tag: string; label: string; deg: number; cited?: boolean }[] = [
  { tag: "DWG", label: "P&IDs and drawings", deg: 120 },
  { tag: "OEM", label: "Vendor manuals", deg: 150, cited: true },
  { tag: "OT", label: "OT tag history", deg: 180 },
  { tag: "NDT", label: "Inspection reports", deg: 210 },
  { tag: "AUDIO", label: "Field voice notes", deg: 240, cited: true },
  { tag: "REG", label: "Regulations", deg: 60, cited: true },
  { tag: "CMMS", label: "Work orders", deg: 30 },
  { tag: "SOP", label: "Standard procedures", deg: 0 },
  { tag: "LOG", label: "Shift handovers", deg: -30 },
  { tag: "PTW", label: "Permits to work", deg: -60 },
];

/**
 * The three sources behind the answer on the card. Every one is a real record in
 * the golden dataset (`dataset/00_Reference/00_KAIROS_CANON.md` § Master
 * Timeline), and FP-SB-2025-04 is retrievable from the running system, so a
 * reader who asks the product this question gets this citation back. The third is
 * deliberately unverified: disclosing weak evidence rather than blending it into
 * the rest is the whole product argument, so the hero states it instead of
 * hiding it.
 */
const heroEvidence: { doc: string; tier: string; date: string; unverified?: boolean }[] = [
  { doc: "FP-SB-2025-04", tier: "OEM", date: "15 Jan 25" },
  { doc: "WO-2025-0631", tier: "Site record", date: "15 May 25" },
  { doc: "Vibration note, unlogged", tier: "Unverified", date: "15 Jan 26", unverified: true },
];

/* Ring radii as multiples of the orbit. 1 is the chip ring itself; the wider one
   frames it, and the inner one shows only as slivers either side of the card,
   which is what gives the field depth rather than a single flat hoop. */
/* Graduations around the chip ring, every 7.5°. Chip angles are all multiples of
   30, so a tick lands under every chip and the ring reads as one dial rather
   than a hoop with labels stuck to it. Radial, so they stay true on an ellipse
   this eccentric. */
const heroTicks = Array.from({ length: 48 }, (_, i) => i * 7.5);

const heroRings: { scale: number; opacity: number }[] = [
  { scale: 1.18, opacity: 0.1 },
  { scale: 1, opacity: 0.3 },
  { scale: 0.62, opacity: 0.14 },
];

export function HeroVisual() {
  return (
    <div>
      {/* Reads as an instrument panel legend: what goes in, what comes out. */}
      <div className="flex items-center justify-between gap-3 text-[9px] font-semibold uppercase tracking-[0.1em] text-white/60 lg:text-[10px] lg:tracking-[0.14em]">
        <span className="whitespace-nowrap">Ten source systems</span>
        <span className="flex items-center gap-2 whitespace-nowrap">
          <span aria-hidden="true" className="size-1.5 bg-(--lp-accent)" />
          One governed answer
        </span>
      </div>

      <div className="mt-5 flex flex-col gap-4 lg:relative lg:mt-6 lg:block lg:aspect-[16/9] xl:aspect-[16/7.8]">
        <svg
          viewBox="0 0 1000 530"
          className="pointer-events-none absolute inset-0 hidden size-full lg:block"
          aria-hidden="true"
          preserveAspectRatio="none"
        >
          {/* Every pale stroke is drawn twice: a wider dark pass underneath, then
              the light one over it. The panel runs from near-black in one corner
              to bright orange in the other, and a single white hairline simply
              disappears into the bright half. */}
          {heroRings.map((ring) => (
            <g key={ring.scale}>
              <ellipse
                cx={ORBIT.cx}
                cy={ORBIT.cy}
                rx={ORBIT.rx * ring.scale}
                ry={ORBIT.ry * ring.scale}
                fill="none"
                stroke="#000000"
                strokeWidth="2.5"
                opacity={ring.opacity * 0.6}
              />
              <ellipse
                cx={ORBIT.cx}
                cy={ORBIT.cy}
                rx={ORBIT.rx * ring.scale}
                ry={ORBIT.ry * ring.scale}
                fill="none"
                stroke="#ffffff"
                opacity={ring.opacity}
              />
            </g>
          ))}

          {heroTicks.map((deg) => {
            const [x1, y1] = orbitPoint(deg, ORBIT.rx, ORBIT.ry);
            const [x2, y2] = orbitPoint(deg, ORBIT.rx * 1.035, ORBIT.ry * 1.035);
            return (
              <g key={deg}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#000000" strokeWidth="2.5" opacity="0.12" />
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#ffffff" opacity="0.22" />
              </g>
            );
          })}

          {heroSources.map((source) => (
            <g key={source.tag}>
              {!source.cited && (
                <path d={orbitWire(source.deg)} fill="none" stroke="#000000" strokeWidth="2.5" opacity="0.18" />
              )}
              <path
                d={orbitWire(source.deg)}
                fill="none"
                strokeWidth={source.cited ? 1.5 : 1}
                stroke={source.cited ? "var(--lp-accent)" : "#ffffff"}
                opacity={source.cited ? 0.75 : 0.34}
              />
            </g>
          ))}

          {/* A pulse on every wire, so the whole ring reads as live. The cited
              three run brighter and faster; the rest are ambient. */}
          {heroSources.map((source, i) => (
            <circle
              key={source.tag}
              className={`lp-orbit-pulse${source.cited ? " lp-orbit-pulse--cited" : ""}`}
              r={source.cited ? 3.5 : 2.2}
              fill={source.cited ? "var(--lp-accent)" : "#ffffff"}
              style={{ offsetPath: `path("${orbitWire(source.deg)}")`, animationDelay: `${(i % 5) * 0.9 + (i > 4 ? 0.45 : 0)}s` }}
            />
          ))}
        </svg>

        {/* `lg:contents` hands each chip straight to the orbit field, so one
            element can be a flow chip on a phone and a ring node on a laptop. */}
        <div className="flex flex-wrap gap-1.5 lg:contents">
          {heroSources.map((source) => {
            const [x, y] = orbitPoint(source.deg, ORBIT.rx, ORBIT.ry);
            return (
              <span
                key={source.tag}
                className={`lp-orbit-node inline-flex items-center gap-2 border bg-(--lp-dark)/78 px-2.5 py-1.5 text-[11px] text-white shadow-lg backdrop-blur-md xl:px-3 xl:py-2 xl:text-[12px] ${source.cited ? "border-(--lp-accent)/70" : "border-white/12"
                  }`}
                style={
                  {
                    "--orbit-x": `${((x / 1000) * 100).toFixed(2)}%`,
                    "--orbit-y": `${((y / 530) * 100).toFixed(2)}%`,
                  } as React.CSSProperties
                }
              >
                <span
                  className={`shrink-0 text-[9px] font-semibold tracking-[0.08em] ${source.cited ? "text-(--lp-accent)" : "text-white/50"
                    }`}
                >
                  {source.tag}
                </span>
                <span className="whitespace-nowrap">{source.label}</span>
              </span>
            );
          })}
        </div>

        {/* The governed answer, and the evidence it stands on. */}
        <div className="lg:absolute lg:left-1/2 lg:top-1/2 lg:w-[44%] lg:-translate-x-1/2 lg:-translate-y-1/2 xl:w-[min(42%,450px)]">
          <div className="lp-mock border border-white/15 bg-(--lp-surface) p-4 sm:p-5">
            <div className="flex items-center justify-between border-b border-(--lp-line) pb-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">
                Checked answer
              </span>
              <span className="text-[11px] tabular-nums text-(--lp-muted)">3.8 s</span>
            </div>

            <p className="lp-display mt-3 text-[17px] leading-tight text-pretty text-(--lp-ink) sm:text-[19px]">
              The EQ-101 seal spec became FSL-2240B on 15 January 2025. A repair four months later still fitted the superseded part.
            </p>

            <div className="mt-4 border-t border-(--lp-line) pt-3">
              <p className="text-[9px] font-semibold uppercase tracking-[0.1em] text-(--lp-muted)">Evidence</p>
              <ul className="mt-2 space-y-1.5">
                {heroEvidence.map((item) => (
                  <li key={item.doc} className="flex items-baseline gap-2 text-[11px]">
                    <span
                      aria-hidden="true"
                      className={`size-1.5 shrink-0 ${item.unverified ? "border border-(--lp-accent)" : "bg-(--lp-accent)"}`}
                    />
                    <span className="min-w-0 flex-1 truncate text-(--lp-ink)">{item.doc}</span>
                    <span
                      className={`shrink-0 ${item.unverified ? "font-semibold text-(--lp-accent-text)" : "text-(--lp-muted)"}`}
                    >
                      {item.tier}
                    </span>
                    <span className="hidden shrink-0 tabular-nums text-(--lp-muted) min-[420px]:inline">{item.date}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="mt-4 flex flex-wrap gap-1.5 text-[11px]">
              <span className="bg-(--lp-accent-strong) px-2 py-1 font-medium text-white">3 sources</span>
              <span className="border border-(--lp-line) px-2 py-1 text-(--lp-muted)">Authority: OEM</span>
              <span className="border border-(--lp-line) px-2 py-1 text-(--lp-muted)">Verified</span>
            </div>

            <div className="mt-4">
              <div className="flex justify-between text-[11px] text-(--lp-muted)">
                <span>Confidence</span>
                <span className="font-semibold tabular-nums text-(--lp-ink)">0.91</span>
              </div>
              <div className="mt-1.5 h-1.5 bg-(--lp-band)">
                <span className="block h-full w-[91%] bg-(--lp-accent)" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-t border-white/15 pt-4 text-[11px] text-white/70 lg:mt-6">
        <span>No claim without its source</span>
        <span>A safety question with thin evidence is refused, not hedged</span>
      </div>
    </div>
  );
}
