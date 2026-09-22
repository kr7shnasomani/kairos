"use client";

import { memo, useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
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
  type NodeMouseHandler,
  type EdgeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { getKnowledgeGraph, getOtCoverage } from "@/lib/api";
import type { GraphNodeData, GraphEdgeData, KnowledgeGraphData, OtCoverage, AuthorityLevel } from "@/lib/types";
import { AuthorityBadge, EmptyState, StatusBadge } from "@/components/ui";
import { cn } from "@/lib/utils";
import { useCanvasTokens, arrowMarker, type CanvasTokens } from "@/lib/graph-theme";

import { Icon } from "@/components/icon";
// ── Color helpers ─────────────────────────────────────────────────────────────
// Colors are resolved Paper design tokens (see lib/graph-theme.tsx), not hardcoded
// hex — this canvas now recolors with the rest of the UI on theme/contrast toggle.

const KIND_TOKENS: Record<string, CanvasTokenNameKey> = {
  Asset: "--accent",
  Event: "--danger",
  Document: "--caution",
  Concept: "--muted",
  Person: "--info",
  Organization: "--verified",
  Valve: "--accent",
  Instrument: "--caution",
  Procedure: "--info",
};

type CanvasTokenNameKey = keyof CanvasTokens;

function kindColor(kind: string, tokens: CanvasTokens) {
  return tokens[KIND_TOKENS[kind] ?? "--muted"];
}

function authorityStrokeColor(level: number, tokens: CanvasTokens): string {
  if (level <= 2) return tokens["--verified"];
  if (level === 3) return tokens["--info"];
  return tokens["--caution"];
}

function edgeStyle(e: GraphEdgeData, tokens: CanvasTokens): React.CSSProperties {
  const color = e.verification_status === "disputed" ? tokens["--danger"] : authorityStrokeColor(e.authority_level, tokens);
  return {
    stroke: color,
    strokeWidth: 1.8,
    strokeDasharray: e.verification_status === "unverified" ? "5,4" : e.verification_status === "superseded" ? "2,8" : undefined,
    opacity: e.verification_status === "superseded" ? 0.3 : 1,
  };
}

// ── Floating edge — draws straight line between node border intersection points ─
// Computes the exact point where the line between two node centers crosses each
// node's rectangular border, so edges always attach to the nearest side.


function nodeCenter(node: ReturnType<typeof useInternalNode>) {
  const x = node?.internals.positionAbsolute.x ?? 0;
  const y = node?.internals.positionAbsolute.y ?? 0;
  const hw = (node?.measured?.width  ?? 120) / 2;
  const hh = (node?.measured?.height ??  50) / 2;
  return { cx: x + hw, cy: y + hh, hw, hh };
}

function borderIntersect(
  { cx, cy, hw, hh }: ReturnType<typeof nodeCenter>,
  other: { cx: number; cy: number },
) {
  const dx = other.cx - cx;
  const dy = other.cy - cy;
  if (!dx && !dy) return { x: cx, y: cy };
  const sx = hw / Math.abs(dx || 1e-9);
  const sy = hh / Math.abs(dy || 1e-9);
  const s  = Math.min(sx, sy);
  return { x: cx + dx * s, y: cy + dy * s };
}

function FloatingEdge({ id, source, target, style, markerEnd, label }: EdgeProps) {
  const srcNode = useInternalNode(source);
  const tgtNode = useInternalNode(target);
  if (!srcNode || !tgtNode) return null;
  const sc = nodeCenter(srcNode);
  const tc = nodeCenter(tgtNode);
  const sp = borderIntersect(sc, tc);
  const tp = borderIntersect(tc, sc);
  const [path, lx, ly] = getStraightPath({ sourceX: sp.x, sourceY: sp.y, targetX: tp.x, targetY: tp.y });
  return <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} label={label} labelX={lx} labelY={ly} />;
}

// ── Custom node — MUST be at module scope + wrapped in memo ──────────────────

const KairosNode = memo(function KairosNode({ data, selected }: NodeProps) {
  const nd = data as unknown as GraphNodeData;
  const tokens = useCanvasTokens();
  const color = kindColor(nd.kind, tokens);
  // Single centered handles — position is irrelevant for floating edges.
  const h: React.CSSProperties = { opacity: 0, pointerEvents: "none", top: "50%", left: "50%" };
  return (
    <>
      <Handle type="target" position={Position.Left} style={h} />
      <div
        style={{ borderColor: color }}
        className={cn(
          "min-w-[90px] max-w-[150px] rounded-xl border-2 bg-surface px-3 py-2 text-center shadow-sm",
          selected && "ring-2 ring-accent ring-offset-1 ring-offset-surface"
        )}
      >
        <p className="text-[9px] font-bold uppercase tracking-[0.1em]" style={{ color }}>
          {nd.kind}
        </p>
        <p className="mt-0.5 truncate text-label font-semibold leading-snug text-ink">
          {nd.label}
        </p>
      </div>
      <Handle type="source" position={Position.Right} style={h} />
    </>
  );
});

// Module-scope type maps — never define inside a component (causes remount).
const nodeTypes = { kairos: KairosNode };
const edgeTypes = { floating: FloatingEdge };

// ── Layout — radial around the center asset ──────────────────────────────────


function buildRFNodes(graph: KnowledgeGraphData): Node[] {
  const others = graph.nodes.filter((n) => n.id !== graph.asset_id);
  const count = others.length || 1;
  const nodes: Node[] = [];
  // Center node
  const center = graph.nodes.find((n) => n.id === graph.asset_id) ?? graph.nodes[0];
  nodes.push({ id: center.id, type: "kairos", position: { x: 0, y: 0 }, data: center as unknown as Record<string, unknown>, draggable: true, focusable: true, ariaLabel: `${center.kind}: ${center.label}` });
  // Satellite nodes
  others.forEach((n, i) => {
    const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
    const r = 280;
    nodes.push({
      id: n.id,
      type: "kairos",
      position: { x: Math.cos(angle) * r, y: Math.sin(angle) * r },
      data: n as unknown as Record<string, unknown>,
      draggable: true,
      focusable: true,
      ariaLabel: `${n.kind}: ${n.label}`,
    });
  });
  return nodes;
}

function buildRFEdges(graph: KnowledgeGraphData, tokens: CanvasTokens): Edge[] {
  return graph.edges.map((e) => ({
    id: e.id,
    type: "floating",
    source: e.source,
    target: e.target,
    label: e.label,
    style: edgeStyle(e, tokens),
    markerEnd: arrowMarker(e.verification_status === "disputed" ? tokens["--danger"] : authorityStrokeColor(e.authority_level, tokens)),
    data: e as unknown as Record<string, unknown>,
    focusable: true,
    ariaLabel: `${e.label}: ${e.verification_status}`,
  }));
}

// ── Selection panels ─────────────────────────────────────────────────────────

const VERIF_TONE: Record<string, "verified" | "caution" | "danger" | "neutral"> = {
  verified: "verified",
  unverified: "caution",
  disputed: "danger",
  superseded: "neutral",
};

function SidePanel({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="absolute inset-x-3 bottom-3 z-10 max-h-[55%] overflow-y-auto rounded-xl border border-line bg-surface shadow-lg sm:inset-x-auto sm:bottom-auto sm:right-3 sm:top-3 sm:w-72">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <p className="truncate text-body font-semibold text-ink">{title}</p>
        <button
          onClick={onClose}
          aria-label="Close panel"
          className="nodrag grid min-h-11 min-w-11 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-ink"
        >
          <Icon name="x" size={14} />
        </button>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function NodePanel({ node, onClose }: { node: GraphNodeData; onClose: () => void }) {
  const props = Object.entries(node.properties);
  return (
    <SidePanel title={node.label} onClose={onClose}>
      <p className="text-micro font-bold uppercase tracking-[0.1em] text-muted">{node.kind}</p>
      {props.length > 0 && (
        <dl className="mt-2.5 space-y-1.5">
          {props.map(([k, v]) => (
            <div key={k} className="flex gap-2 text-label">
              <dt className="w-24 shrink-0 truncate font-medium text-muted">{k}</dt>
              <dd className="min-w-0 break-words text-ink">{String(v ?? "—")}</dd>
            </div>
          ))}
        </dl>
      )}
    </SidePanel>
  );
}

function EdgePanel({ edge, onClose }: { edge: GraphEdgeData; onClose: () => void }) {
  const isOpen = edge.valid_to.startsWith("9999");
  const validTo = isOpen ? "Current" : edge.valid_to.slice(0, 10);
  return (
    <SidePanel title={edge.label} onClose={onClose}>
      <dl className="space-y-2">
        <div className="flex items-center gap-2 text-label">
          <dt className="w-24 shrink-0 font-medium text-muted">Authority</dt>
          <dd><AuthorityBadge level={edge.authority_level as AuthorityLevel} /></dd>
        </div>
        <div className="flex items-center gap-2 text-label">
          <dt className="w-24 shrink-0 font-medium text-muted">Verification</dt>
          <dd><StatusBadge tone={VERIF_TONE[edge.verification_status] ?? "neutral"}>{edge.verification_status}</StatusBadge></dd>
        </div>
        {[
          ["Document", edge.document_id || "—"],
          ["Confidence", `${Math.round(edge.confidence * 100)}%`],
          ["Valid from", edge.valid_from.slice(0, 10)],
          ["Valid to", validTo],
        ].map(([label, value]) => (
          <div key={label} className="flex gap-2 text-label">
            <dt className="w-24 shrink-0 font-medium text-muted">{label}</dt>
            <dd className="min-w-0 break-words text-ink">{value}</dd>
          </div>
        ))}
      </dl>
    </SidePanel>
  );
}

// ── OT coverage indicator ────────────────────────────────────────────────────

function CoverageIndicator({ assetId }: { assetId: string }) {
  const [cov, setCov] = useState<OtCoverage | null>(null);
  useEffect(() => {
    let alive = true;
    // getOtCoverage throws on failure (live-only). Without this catch the rejection was
    // unhandled and the indicator silently never appeared.
    getOtCoverage(assetId)
      .then(({ data }) => { if (alive) setCov(data); })
      .catch(() => { if (alive) setCov(null); });
    return () => { alive = false; };
  }, [assetId]);
  if (!cov) return null;

  const tone: "verified" | "caution" | "danger" =
    cov.coverage_type === "direct" ? "verified" : cov.coverage_type === "macro" ? "caution" : "danger";
  const label =
    cov.coverage_type === "direct"
      ? `Direct sensors · ${cov.sensor_tags.slice(0, 2).join(", ")}${cov.sensor_tags.length > 2 ? "…" : ""}`
      : cov.coverage_type === "macro"
      ? "Macro monitoring only"
      : "No sensor coverage";

  return (
    <div className="absolute bottom-12 left-14 z-10">
      <StatusBadge tone={tone}>{label}</StatusBadge>
    </div>
  );
}

// ── Public component ─────────────────────────────────────────────────────────

export function KnowledgeGraph(props: { assetId: string; asOf?: string; height?: number }) {
  return <KnowledgeGraphInner {...props} />;
}

function KnowledgeGraphInner({
  assetId,
  asOf,
  height = 480,
}: {
  assetId: string;
  asOf?: string;
  height?: number;
}) {
  const tokens = useCanvasTokens();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [graphData, setGraphData] = useState<KnowledgeGraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdgeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      setLoading(true);
      setFailed(false);
      setSelectedNode(null);
      setSelectedEdge(null);
      try {
        const { data } = await getKnowledgeGraph(assetId, asOf);
        if (!alive) return;
        setGraphData(data);
        if (data) setNodes(buildRFNodes(data));
      } catch {
        // Without this the rejection was unhandled and `setLoading(false)` never ran, so a
        // timed-out fetch left the canvas bouncing its loading dots forever with no error and
        // no way back. `getKnowledgeGraph` throws by design (live-only policy) — the caller
        // owes it a catch.
        if (!alive) return;
        setFailed(true);
      } finally {
        if (alive) setLoading(false);
      }
    };
    void load();
    return () => { alive = false; };
  }, [assetId, asOf, setNodes, reloadKey]);

  // Edge colors are baked-in token strings (see lib/graph-theme.tsx), so rebuild
  // whenever the graph data or the resolved theme tokens change.
  useEffect(() => {
    if (graphData) setEdges(buildRFEdges(graphData, tokens));
  }, [graphData, tokens, setEdges]);

  const onNodeClick = useCallback<NodeMouseHandler>((_evt, node) => {
    setSelectedNode(node.data as unknown as GraphNodeData);
    setSelectedEdge(null);
  }, []);

  const onEdgeClick = useCallback<EdgeMouseHandler>((_evt, edge) => {
    setSelectedEdge((edge.data as unknown as GraphEdgeData) ?? null);
    setSelectedNode(null);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, []);

  if (loading) {
    return (
      <div
        className="flex items-center justify-center rounded-xl border border-line bg-surface"
        style={{ height }}
      >
        <span className="inline-flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="size-2 animate-pulse rounded-full bg-muted"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </span>
      </div>
    );
  }

  if (failed) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-3 rounded-xl border border-line bg-surface px-6 text-center"
        style={{ height }}
      >
        <p className="text-body font-medium text-ink">Could not load the graph for {assetId}.</p>
        <p className="max-w-sm text-caption text-muted">
          The knowledge request failed or timed out. Nothing is cached — this shows real data or
          nothing at all.
        </p>
        <button
          type="button"
          onClick={() => setReloadKey((k) => k + 1)}
          className="min-h-9 rounded-lg border border-line bg-surface px-3 text-caption font-semibold text-ink transition-colors hover:bg-surface-2"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-xl border border-line bg-surface"
        style={{ height }}
      >
        <EmptyState message="No knowledge graph data for this asset." />
      </div>
    );
  }

  return (
    <div className="relative overflow-hidden rounded-xl border border-line" style={{ height }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        fitView
        fitViewOptions={{ padding: 0.35 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} size={1} color={tokens["--line"]} />
        <Controls showInteractive={false} />
      </ReactFlow>
      <CoverageIndicator assetId={assetId} />
      {selectedNode && (
        <NodePanel node={selectedNode} onClose={() => setSelectedNode(null)} />
      )}
      {selectedEdge && (
        <EdgePanel edge={selectedEdge} onClose={() => setSelectedEdge(null)} />
      )}
    </div>
  );
}
