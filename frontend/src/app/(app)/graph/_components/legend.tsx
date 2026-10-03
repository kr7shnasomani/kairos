// Graph context-panel helpers: authority legend + validity-window mapping.
import type { GraphEdgeData } from "@/lib/types";
import type { TimelineEvent } from "@/components/ui";

const LEGEND_ITEMS = [
  { var: "var(--verified)", label: "L1–L2 verified" },
  { var: "var(--info)",     label: "L3 standard" },
  { var: "var(--caution)",  label: "L4–L5 field" },
  { var: "var(--muted)",    label: "Unverified", dashed: true },
  { var: "var(--danger)",   label: "Disputed" },
] satisfies { var: string; label: string; dashed?: boolean }[];

// What each node colour means (the same tokens the canvas uses in `knowledge-graph.tsx`).
const NODE_ITEMS = [
  { var: "var(--accent)", label: "Asset" },
  { var: "var(--caution)", label: "Document" },
  { var: "var(--info)", label: "Person" },
  { var: "var(--verified)", label: "Organisation" },
  { var: "var(--danger)", label: "Event" },
] satisfies { var: string; label: string }[];

export function GraphLegend() {
  return (
    <div className="grid gap-2 text-label text-muted">
      <div className="mb-1 flex flex-wrap gap-x-3 gap-y-1.5 border-b border-line pb-2.5">
        {NODE_ITEMS.map(({ var: c, label }) => (
          <span key={label} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-1.5 rounded-sm" style={{ backgroundColor: c }} />
            {label}
          </span>
        ))}
      </div>
      {LEGEND_ITEMS.map(({ var: c, label, dashed }) => (
        <div key={label} className="flex items-center gap-1.5">
          {dashed
            ? <span className="inline-block h-2 w-6 border-t-2 border-dashed" style={{ borderColor: c }} />
            : <span className="inline-block h-2 w-6" style={{ backgroundColor: c }} />}
          {label}
        </div>
      ))}
    </div>
  );
}

const SENTINEL_YEAR = 9999;

function edgeTone(e: GraphEdgeData): TimelineEvent["tone"] {
  if (e.verification_status === "disputed") return "danger";
  if (e.verification_status === "superseded") return "neutral";
  if (e.authority_level <= 2) return "verified";
  if (e.authority_level === 3) return "info";
  return "caution";
}

/** Map graph edges to shared Timeline events (validity windows). */
export function validityEvents(edges: GraphEdgeData[], labelOf?: (id: string) => string | undefined): TimelineEvent[] {
  return edges.map((e) => {
    const end = new Date(e.valid_to);
    const open = end.getFullYear() >= SENTINEL_YEAR;
    // Label with the distinguishing TARGET node (the doc/concept the edge points to)
    // — most edges share the same relationship type (e.g. DOCUMENTED_BY) and the same
    // provenance document, so those repeat for every row. Relationship stays as a caption.
    const rel = e.label ? e.label.replace(/_/g, " ").toLowerCase() : "relationship";
    const target = labelOf?.(e.target);
    return {
      id: e.id,
      label: target || e.document_id || e.label || "relationship",
      timestamp: new Date(e.valid_from).toLocaleDateString("en-IN", { month: "short", year: "numeric" }),
      meta: open ? "Current" : `until ${end.toLocaleDateString("en-IN", { month: "short", year: "2-digit" })}`,
      description: rel,
      tone: edgeTone(e),
    };
  });
}
