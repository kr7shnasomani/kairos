"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Panel,
  Position,
  useNodesState,
  useNodesInitialized,
  useReactFlow,
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
  Organisation: "--verified",
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
  // Position in the plant (the unit above, an event on the asset): a quiet solid line, no authority colour.
  if (e.structural) return { stroke: tokens["--muted"], strokeWidth: 1.2, opacity: 0.6 };
  const color = e.verification_status === "disputed" ? tokens["--danger"] : authorityStrokeColor(e.authority_level, tokens);
  return {
    stroke: color,
    strokeWidth: 1.2,
    strokeDasharray: e.verification_status === "unverified" ? "5,4" : e.verification_status === "superseded" ? "2,8" : undefined,
    opacity: e.verification_status === "superseded" ? 0.3 : 0.7,
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

const NODE_W = 132; // fixed card size: the layout below places nodes by these numbers
const NODE_H = 50;

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
        style={{ width: NODE_W, minHeight: NODE_H, borderColor: color }}
        title={nd.label}
        className={cn(
          "rounded-md border bg-surface px-2.5 py-1.5",
          selected && "ring-2 ring-accent ring-offset-1 ring-offset-surface"
        )}
      >
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em]" style={{ color }}>
          {nd.kind}
        </p>
        <p className="line-clamp-2 break-words text-caption font-semibold leading-tight text-ink">
          {nd.label}
        </p>
      </div>
      <Handle type="source" position={Position.Right} style={h} />
    </>
  );
});

// Module-scope type maps — never define inside a component (causes remount).
const nodeTypes = { kairos: KairosNode };
// A wide graph needs to zoom out further than React Flow's default floor of 0.5, or "fit" and the
// zoom-out button stop working once the network is bigger than the canvas.
const MIN_ZOOM = 0.05;
const MAX_ZOOM = 2.5;
const FIT_PADDING = 0.12;
const edgeTypes = { floating: FloatingEdge };

// ── Layout — two elliptical rings around the centre asset ───────────────────
// Ring one is everything the asset touches directly (the unit above and the instruments below, its
// documents, its events). Ring two is what only those reach: the people and organisations a document
// mentions and the other assets it covers, each placed at the average angle of the ring-one nodes it
// connects to, so a shared person sits between its documents and the lines stay short.
// The rings are ellipses (the canvas is wider than it is tall) and alternate ring-one nodes sit a little
// further out, so neighbours never overlap at the top and bottom where the ring runs horizontally.

const ASPECT = 1.75; // ellipse width over height
const STAGGER = 1.3; // every second ring-one node sits this much further out
const RING_GAP = 150;
const ARC = NODE_W + 6; // px of ring one node needs along the ring
const KIND_ORDER = ["Asset", "Document", "Event"];

function circularMean(angles: number[]): number {
  return Math.atan2(
    angles.reduce((s, a) => s + Math.sin(a), 0),
    angles.reduce((s, a) => s + Math.cos(a), 0),
  );
}

/** Spread desired angles so neighbours keep `minGap` radians apart; order is preserved. */
function spreadAngles(desired: number[], minGap: number): number[] {
  const order = desired.map((a, i) => [a, i] as const).sort((x, y) => x[0] - y[0]);
  const out = new Array<number>(desired.length);
  let prev = -Infinity;
  for (const [a, i] of order) {
    const placed = Math.max(a, prev + minGap);
    out[i] = placed;
    prev = placed;
  }
  return out;
}

export function buildRFNodes(graph: KnowledgeGraphData): Node[] {
  const center = graph.nodes.find((n) => n.id === graph.asset_id) ?? graph.nodes[0];
  const direct = new Set<string>();
  for (const e of graph.edges) {
    if (e.source === center.id) direct.add(e.target);
    if (e.target === center.id) direct.add(e.source);
  }
  const ringOne = graph.nodes
    .filter((n) => n.id !== center.id && direct.has(n.id))
    .sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind));
  const ringTwo = graph.nodes.filter((n) => n.id !== center.id && !direct.has(n.id));

  // Semi-height of ring one: enough perimeter for one card per node, with the stagger doing the rest.
  const b1 = Math.max(150, ringOne.length * 14);
  const b2 = b1 * STAGGER + RING_GAP;
  const angleOf = new Map<string, number>();
  ringOne.forEach((n, i) => angleOf.set(n.id, (i / (ringOne.length || 1)) * 2 * Math.PI - Math.PI / 2));

  // Ring two: the mean angle of whatever it is linked to in ring one, then spread apart.
  const desired = ringTwo.map((n) => {
    const linked = graph.edges
      .filter((e) => e.source === n.id || e.target === n.id)
      .flatMap((e) => [angleOf.get(e.source), angleOf.get(e.target)])
      .filter((a): a is number => a !== undefined);
    return linked.length ? circularMean(linked) : -Math.PI / 2;
  });
  const meanR2 = b2 * Math.sqrt((ASPECT * ASPECT + 1) / 2);
  const spread = spreadAngles(desired, ARC / meanR2);
  ringTwo.forEach((n, i) => angleOf.set(n.id, spread[i]));

  // Positions are card centres on the ellipse; React Flow positions the top-left corner.
  const at = (n: GraphNodeData, b: number) => {
    const angle = angleOf.get(n.id) ?? 0;
    return { x: Math.cos(angle) * b * ASPECT - NODE_W / 2, y: Math.sin(angle) * b - NODE_H / 2 };
  };
  const make = (n: GraphNodeData, position: { x: number; y: number }): Node => ({
    id: n.id,
    type: "kairos",
    position,
    data: n as unknown as Record<string, unknown>,
    draggable: true,
    focusable: true,
    ariaLabel: `${n.kind}: ${n.label}`,
  });
  return [
    make(center, { x: -NODE_W / 2, y: -NODE_H / 2 }),
    ...ringOne.map((n, i) => make(n, at(n, i % 2 ? b1 * STAGGER : b1))),
    ...ringTwo.map((n) => make(n, at(n, b2))),
  ];
}

function buildRFEdges(graph: KnowledgeGraphData, tokens: CanvasTokens, focusId: string | null): Edge[] {
  return graph.edges.map((e) => ({
    id: e.id,
    type: "floating",
    source: e.source,
    target: e.target,
    // No label on the line: the same few relationship names repeated on every edge were clutter.
    // The relationship is in the panel that opens on click, and node colours are in the legend.
    // With a node selected, only its own lines stay at full strength.
    style: focusId && e.source !== focusId && e.target !== focusId
      ? { ...edgeStyle(e, tokens), opacity: 0.12 }
      : edgeStyle(e, tokens),
    markerEnd: arrowMarker(e.structural ? tokens["--muted"] : e.verification_status === "disputed" ? tokens["--danger"] : authorityStrokeColor(e.authority_level, tokens)),
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
  if (edge.structural) {
    return (
      <SidePanel title={edge.label.replace(/_/g, " ").toLowerCase()} onClose={onClose}>
        <p className="text-label text-muted">
          {edge.label === "PARENT_OF" ? "Where the asset sits in the plant hierarchy." : "An event recorded against the asset."}{" "}
          It is not a knowledge fact, so it has no authority level or validity window.
        </p>
      </SidePanel>
    );
  }
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
      ? `Direct sensors, ${cov.sensor_tags.slice(0, 2).join(", ")}${cov.sensor_tags.length > 2 ? "…" : ""}`
      : cov.coverage_type === "macro"
      ? "Macro monitoring only"
      : "No sensor coverage";

  return (
    <div className="absolute top-4 left-4 z-10">
      <StatusBadge tone={tone}>{label}</StatusBadge>
    </div>
  );
}

// ── Canvas toolbar — lives inside <ReactFlow> so it can fit the view ──────────

const TOOL_BTN =
  "inline-flex h-8 items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 text-label font-semibold text-muted shadow-sm transition-colors hover:bg-surface-2 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent";

function GraphToolbar({ full, layoutKey, onToggleFull, onRearrange }: { full: boolean; layoutKey: number; onToggleFull: () => void; onRearrange: () => void }) {
  const { fitView } = useReactFlow();
  const measured = useNodesInitialized();
  const fit = useCallback(() => void fitView({ padding: FIT_PADDING, minZoom: MIN_ZOOM, duration: 250 }), [fitView]);
  // Fit once every card has been measured (fitting earlier works from zero-sized cards and zooms far
  // too wide), and again whenever the canvas changes size or the layout is reset.
  useEffect(() => {
    if (!measured) return;
    const t = window.setTimeout(fit, 120);
    return () => window.clearTimeout(t);
  }, [measured, full, layoutKey, fit]);
  return (
    <Panel position="bottom-right" className="flex gap-2">
      <button type="button" onClick={fit} title="Fit the whole graph in view" className={TOOL_BTN}>Fit</button>
      <button type="button" onClick={onRearrange} title="Put every node back where it started" className={TOOL_BTN}>Rearrange</button>
      <button type="button" onClick={onToggleFull} title={full ? "Exit full screen (Esc)" : "Full screen"} className={TOOL_BTN}>
        <Icon name={full ? "arrows-in" : "arrows-out"} size={14} />
        {full ? "Exit full screen" : "Full screen"}
      </button>
    </Panel>
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
  const [full, setFull] = useState(false);
  const [layoutKey, setLayoutKey] = useState(0);
  const frameRef = useRef<HTMLDivElement>(null);

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
    if (graphData) setEdges(buildRFEdges(graphData, tokens, selectedNode?.id ?? null));
  }, [graphData, tokens, selectedNode, setEdges]);

  // Full screen: the browser's own when it allows it, else the canvas fills the window. Esc leaves either.
  useEffect(() => {
    const sync = () => setFull(document.fullscreenElement === frameRef.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);
  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.fullscreenElement) setFull(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full]);
  const toggleFull = useCallback(async () => {
    const el = frameRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (full) setFull(false);
      else await el.requestFullscreen();
    } catch {
      setFull((f) => !f);
    }
  }, [full]);

  const rearrange = useCallback(() => {
    if (!graphData) return;
    setNodes(buildRFNodes(graphData));
    setLayoutKey((k) => k + 1);
  }, [graphData, setNodes]);

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

  const frame = (
    <div
      ref={frameRef}
      className={cn("overflow-hidden border border-line bg-canvas", full ? "fixed inset-0 z-50 h-dvh rounded-none" : "relative rounded-xl")}
      style={full ? undefined : { height }}
    >
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
        fitViewOptions={{ padding: FIT_PADDING, minZoom: MIN_ZOOM }}
        minZoom={MIN_ZOOM}
        maxZoom={MAX_ZOOM}
        nodesFocusable
        edgesFocusable
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} size={1} color={tokens["--line"]} />
        <Controls showInteractive={false} showFitView={false} />
        <GraphToolbar full={full} layoutKey={layoutKey} onToggleFull={() => void toggleFull()} onRearrange={rearrange} />
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

  // The window-filling fallback goes through a portal: inside the page, an ancestor with a transform
  // (the route transition) would make `fixed` fill that ancestor instead of the window.
  return full && !document.fullscreenElement ? createPortal(frame, document.body) : frame;
}
