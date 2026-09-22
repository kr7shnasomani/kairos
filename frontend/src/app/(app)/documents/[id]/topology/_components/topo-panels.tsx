"use client";

// Topology side panels: selected-node inspector + verification legend.
import type { TopologyNode } from "@/lib/types";
import { nodeVar } from "./topo-node";

import { Icon } from "@/components/icon";
export function NodeDetail({ node, onClose }: { node: TopologyNode; onClose: () => void }) {
  const color = nodeVar(node.node_type, node.verification_status);
  return (
    <div className="absolute inset-x-3 bottom-3 z-10 rounded-xl border border-line bg-surface shadow-lg sm:inset-x-auto sm:bottom-auto sm:right-3 sm:top-3 sm:w-64">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <p className="truncate text-body font-semibold text-ink">{node.label}</p>
        <button
          onClick={onClose}
          aria-label="Close"
          className="nodrag grid size-11 shrink-0 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink"
        >
          <Icon name="x" size={14} />
        </button>
      </div>
      <div className="p-4 space-y-2 text-label">
        <div className="flex gap-2">
          <span className="w-24 shrink-0 font-medium text-muted">Type</span>
          <span style={{ color }} className="font-semibold">{node.node_type}</span>
        </div>
        <div className="flex gap-2">
          <span className="w-24 shrink-0 font-medium text-muted">Verification</span>
          <span style={{ color }} className="capitalize">{node.verification_status}</span>
        </div>
        {Object.entries(node.properties ?? {}).slice(0, 5).map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span className="w-24 shrink-0 truncate font-medium text-muted capitalize">{k.replace(/_/g, " ")}</span>
            <span className="min-w-0 truncate text-ink">{String(v ?? "—")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const TOPO_LEGEND = [
  { cssVar: "var(--verified)", label: "Verified" },
  { cssVar: "var(--caution)", dashed: true, label: "Unverified" },
  { cssVar: "var(--danger)", label: "Disputed" },
  { cssVar: "var(--info)", label: "Flow connection" },
  { cssVar: "var(--caution)", dashed: true, label: "Instrumentation loop" },
] satisfies { cssVar: string; dashed?: boolean; label: string }[];

export function TopoLegend() {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2 text-label text-muted">
      {TOPO_LEGEND.map(({ cssVar, dashed, label }) => (
        <div key={label} className="flex items-center gap-1.5">
          {dashed
            ? <span className="inline-block h-2 w-6 border-t-2 border-dashed" style={{ borderColor: cssVar }} />
            : <span className="inline-block h-2 w-6 rounded-full" style={{ backgroundColor: cssVar }} />}
          {label}
        </div>
      ))}
    </div>
  );
}
