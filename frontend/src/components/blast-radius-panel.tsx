"use client";

import { memo, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  useInternalNode,
  getStraightPath,
  BaseEdge,
  type Node,
  type Edge,
  type NodeProps,
  type EdgeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { getBlastRadius } from "@/lib/api";
import type { BlastRadiusReport } from "@/lib/types";
import { StatusBadge, EmptyState } from "@/components/ui";
import Link from "next/link";
import { useCanvasTokens, arrowMarker, type CanvasTokens } from "@/lib/graph-theme";

// ── Mini diagram ─────────────────────────────────────────────────────────────
// Colors are resolved Paper design tokens (lib/graph-theme.tsx), not hardcoded hex.

const ITEM_TYPE_TOKENS: Record<string, keyof CanvasTokens> = {
  procedure: "--info",
  inspection: "--caution",
  fact: "--muted",
  document: "--accent",
  compliance: "--danger",
};

const BlastNode = memo(function BlastNode({ data }: NodeProps) {
  const d = data as { label: string; itemType: string; isCenter: boolean; flagged: boolean };
  const tokens = useCanvasTokens();
  const color = d.isCenter ? tokens["--accent"] : tokens[ITEM_TYPE_TOKENS[d.itemType] ?? "--muted"];
  const h: React.CSSProperties = { opacity: 0, pointerEvents: "none", top: "50%", left: "50%" };
  return (
    <div
      style={{ borderColor: color }}
      className={`relative min-w-[80px] max-w-[130px] rounded-xl border-2 px-2.5 py-1.5 text-center shadow-sm ${d.isCenter ? "bg-[color-mix(in_srgb,var(--accent)_8%,var(--surface))]" : "bg-surface"}`}
    >
      <Handle type="target" position={Position.Left}  isConnectable={false} style={h} />
      <p className="text-[9px] font-bold uppercase tracking-[0.1em]" style={{ color }}>{d.itemType}</p>
      <p className="mt-0.5 truncate text-micro font-semibold leading-snug text-ink">{d.label}</p>
      {d.flagged && <p className="mt-0.5 text-label font-bold text-danger">FLAGGED</p>}
      <Handle type="source" position={Position.Right} isConnectable={false} style={h} />
    </div>
  );
});

function BlastFloatingEdge({ id, source, target, style, markerEnd }: EdgeProps) {
  const srcNode = useInternalNode(source);
  const tgtNode = useInternalNode(target);
  if (!srcNode || !tgtNode) return null;
  const sc = blastNodeCenter(srcNode);
  const tc = blastNodeCenter(tgtNode);
  const sp = blastBorderIntersect(sc, tc);
  const tp = blastBorderIntersect(tc, sc);
  const [path] = getStraightPath({ sourceX: sp.x, sourceY: sp.y, targetX: tp.x, targetY: tp.y });
  return <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />;
}

function blastNodeCenter(node: ReturnType<typeof useInternalNode>) {
  const x = node?.internals.positionAbsolute.x ?? 0;
  const y = node?.internals.positionAbsolute.y ?? 0;
  const hw = (node?.measured?.width  ?? 110) / 2;
  const hh = (node?.measured?.height ??  45) / 2;
  return { cx: x + hw, cy: y + hh, hw, hh };
}

function blastBorderIntersect(
  { cx, cy, hw, hh }: ReturnType<typeof blastNodeCenter>,
  other: { cx: number; cy: number },
) {
  const dx = other.cx - cx;
  const dy = other.cy - cy;
  if (!dx && !dy) return { x: cx, y: cy };
  const s = Math.min(hw / Math.abs(dx || 1e-9), hh / Math.abs(dy || 1e-9));
  return { x: cx + dx * s, y: cy + dy * s };
}

const blastNodeTypes = { blast: BlastNode };
const blastEdgeTypes = { floating: BlastFloatingEdge };

function buildBlastDiagram(report: BlastRadiusReport, tokens: CanvasTokens): { nodes: Node[]; edges: Edge[] } {
  const center: Node = {
    id: "__doc__",
    type: "blast",
    position: { x: 0, y: 0 },
    data: { label: report.document_id, itemType: "document", isCenter: true, flagged: false },
    draggable: false,
  };

  const shown = report.items.slice(0, 12);
  const rfNodes: Node[] = [
    center,
    ...shown.map((item, i) => {
      const angle = (i / (shown.length || 1)) * 2 * Math.PI - Math.PI / 2;
      const r = 200;
      return {
        id: item.item_id,
        type: "blast",
        position: { x: Math.cos(angle) * r, y: Math.sin(angle) * r },
        data: { label: item.description.slice(0, 28), itemType: item.item_type, isCenter: false, flagged: item.flagged_for_review },
        draggable: false,
      };
    }),
  ];

  const rfEdges: Edge[] = shown.map((item) => {
    const color = item.flagged_for_review ? tokens["--danger"] : tokens["--line"];
    return {
      id: `e-${item.item_id}`,
      type: "floating",
      source: "__doc__",
      target: item.item_id,
      style: { stroke: color, strokeWidth: 1.2 },
      markerEnd: arrowMarker(color, 10),
    };
  });

  return { nodes: rfNodes, edges: rfEdges };
}

// ── Panel ─────────────────────────────────────────────────────────────────────

export function BlastRadiusPanel(props: { documentId: string }) {
  return <BlastRadiusPanelInner {...props} />;
}

function BlastRadiusPanelInner({ documentId }: { documentId: string }) {
  const tokens = useCanvasTokens();
  const [report, setReport] = useState<BlastRadiusReport | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    let alive = true;
    // No fixture fallback. This used to render fabricated blast-radius items — invented
    // asset ids and a "Design pressure rating 15 bar" fact — whenever `data` was null,
    // which is fabricated safety-relevant data presented as a real impact analysis.
    // A null report leaves the panel in its own empty state.
    getBlastRadius(documentId)
      .then(({ data }) => { if (alive) setReport(data); })
      .catch(() => { if (alive) setReport(null); });
    return () => { alive = false; };
  }, [documentId]);

  // Edge/node colors are baked-in token strings, so rebuild whenever the report
  // or the resolved theme tokens change.
  useEffect(() => {
    if (report && report.items.length > 0) {
      const { nodes: n, edges: e } = buildBlastDiagram(report, tokens);
      setNodes(n);
      setEdges(e);
    }
  }, [report, tokens, setNodes, setEdges]);

  if (!report) return null;

  return (
    <section className="mt-8">
      <div className="flex w-full items-center text-xs font-bold uppercase tracking-[0.1em] text-muted">
        <span>
          Blast Radius
          {report.affected_count > 0 && (
            <span className="ml-2 inline-flex items-center bg-danger px-1.5 py-0.5 text-micro font-semibold text-on-danger">
              {report.affected_count}
            </span>
          )}
        </span>
      </div>

      <p className="mt-1.5 text-caption text-pretty text-muted">
        Everything that relies on this source document. If the document is superseded or disputed,
        each item here is flagged for review, so outdated knowledge cannot spread unnoticed.
      </p>

      <div className="mt-3 space-y-4">

          {report.items.length === 0 ? (
            <div className="rounded-xl border border-line bg-surface">
              <EmptyState message="No downstream items affected." />
            </div>
          ) : (
            <>
              {/* Mini React Flow diagram */}
              <div className="overflow-hidden rounded-xl border border-line" style={{ height: 300 }}>
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  nodeTypes={blastNodeTypes}
                  edgeTypes={blastEdgeTypes}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  fitView
                  fitViewOptions={{ padding: 0.3 }}
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={false}
                  proOptions={{ hideAttribution: true }}
                  zoomOnScroll={false}
                  panOnScroll={false}
                  panOnDrag={false}
                >
                  <Background gap={20} size={1} color={tokens["--line"]} />
                </ReactFlow>
              </div>

              {/* Item list */}
              <div className="divide-y divide-line rounded-xl border border-line overflow-hidden">
                {report.items.map((item) => (
                  <div key={item.item_id} className="flex items-start gap-3 bg-surface px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-caption text-ink leading-snug">{item.description}</p>
                      <p className="mt-0.5 text-label text-muted capitalize">{item.item_type}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {item.asset_id && (
                        <Link href={`/assets/${item.asset_id}`} className="text-label text-accent hover:underline">
                          {item.asset_id}
                        </Link>
                      )}
                      {item.flagged_for_review && (
                        <StatusBadge tone="danger">Flagged</StatusBadge>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {report.affected_count > report.items.length && (
                <p className="text-center text-label text-muted">
                  + {report.affected_count - report.items.length} more items
                </p>
              )}
            </>
          )}
        </div>
    </section>
  );
}
