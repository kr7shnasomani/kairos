"use client";

// Interactive P&ID topology canvas for a vault document (React Flow).
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { getDocumentTopology, verifyTopologyElements } from "@/lib/api";
import type { TopologyNode } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";
import { useCanvasTokens } from "@/lib/graph-theme";
import { RESOLVE_ROLES, useRole } from "@/components/use-role";
import { Button, EmptyState, PageHeader } from "@/components/ui";
import { nodeTypes, edgeTypes, nodeVar } from "./_components/topo-node";
import { NodeDetail, TopoLegend } from "./_components/topo-panels";
import { buildLayout } from "./_components/topo-data";

import { Icon } from "@/components/icon";
export default function TopologyPage() {
  return <TopologyPageInner />;
}

function TopologyPageInner() {
  const { id } = useParams<{ id: string }>();
  const tokens = useCanvasTokens();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [busyElement, setBusyElement] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Bumped after a verification decision to re-read derived status rather than guess it locally.
  const [refreshKey, setRefreshKey] = useState(0);
  const role = useRole();
  const canVerify = RESOLVE_ROLES.includes(role);

  // Live-only via the shared hook: loading → live → error+retry. There used to be a
  // `data ?? FIXTURE` here, which would have rendered fabricated elements — some labelled
  // "verified" — through the very gate this page exists to enforce. And the old `.then()`
  // had no `.catch()`, so a /topology 404 (by design for non-pid_drawing documents) left
  // the page spinning forever.
  const state = useFetch(() => getDocumentTopology(id), [id, refreshKey]);
  const topo = state.status === "live" ? state.data : null;
  const loading = state.status === "loading";
  // The backend pipeline can fall back to its own demo fixture when the vision model is
  // unreachable. That returns source:"live" with plausible elements, so it must be disclosed.
  const isDemo = topo?.topology_source === "demo_fixture";

  async function decide(elementId: string, decision: "confirmed" | "rejected") {
    if (busyElement) return;
    setBusyElement(elementId);
    setSaveError(null);
    try {
      await verifyTopologyElements(id, [{ element_id: elementId, decision }]);
      setRefreshKey((k) => k + 1);
    } catch {
      setSaveError("Verification failed to save. Your decision was not recorded — try again.");
    } finally {
      setBusyElement(null);
    }
  }

  // Node/edge colors are baked-in token strings, so rebuild whenever the
  // topology data or the resolved theme tokens change. (Not merged with the
  // fetch effect: a theme toggle must rebuild the layout without refetching.)
  useEffect(() => {
    if (!topo) return;
    const { nodes: n, edges: e } = buildLayout(topo, tokens);
    setNodes(n);
    setEdges(e);
  }, [topo, tokens, setNodes, setEdges]);

  const onNodeClick = useCallback<NodeMouseHandler>((_evt, node) => {
    setSelectedNode(node.data as unknown as TopologyNode);
  }, []);

  const onPaneClick = useCallback(() => setSelectedNode(null), []);

  return (
    <div data-testid="topology-workspace" className="mx-auto max-w-[1400px]">
      <div className="flex items-center justify-between">
        <Link
          href={`/documents/${id}`}
          className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink"
        >
          <Icon name="caret-left" size={15} />
          Document
        </Link>
        {isDemo && (
          <span
            title="This topology was not extracted from the drawing — do not treat it as engineering data."
            className="inline-flex items-center gap-1.5 border border-line bg-surface-2 px-2 py-0.5 text-label text-muted"
          >
            <span className="size-1.5 rounded-full bg-caution" aria-hidden="true" />
            {topo?.topology_source === "demo_fixture" ? "Fixture — vision model unavailable" : "Demo topology"}
          </span>
        )}
      </div>

      <PageHeader
        compact
        className="mt-4 mb-5"
        eyebrow="Knowledge · P&ID topology"
        title={id}
        lede="Equipment, valves, instruments, and flow connections extracted from the P&ID drawing. Candidate topology until an engineer confirms it element by element — confirm or reject each element below."
      />

      <div data-testid="topology-layout" className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div data-testid="topology-canvas" className="relative min-h-[420px] h-[min(62dvh,680px)] overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <span className="inline-flex gap-1.5">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="size-2 animate-pulse rounded-full bg-muted" style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </span>
            </div>
          ) : state.status === "error" ? (
            <div data-testid="topology-error" className="flex h-full flex-col items-center justify-center gap-3 p-4 text-center">
              <EmptyState message="No P&ID topology for this document. Only drawings ingested as 'pid_drawing' have extracted topology." />
              <Button variant="ghost" onClick={state.retry}>Retry</Button>
            </div>
          ) : !topo || topo.nodes.length === 0 ? (
            <div className="flex h-full items-center justify-center p-4"><EmptyState message="No topology extracted from this document yet." /></div>
          ) : (
            <>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                fitView
                fitViewOptions={{ padding: 0.35 }}
                proOptions={{ hideAttribution: true }}
              >
                <Background gap={24} size={1} color={tokens["--line"]} />
                <Controls showInteractive={false} />
              </ReactFlow>
              {selectedNode && (
                <NodeDetail node={selectedNode} onClose={() => setSelectedNode(null)} />
              )}
            </>
          )}
        </div>

        <aside data-testid="topology-context" className="rounded-xl border border-line bg-surface p-4 shadow-sm lg:sticky lg:top-6">
          <h2 className="text-label font-bold uppercase tracking-[0.1em] text-muted">Verification key</h2>
          <div className="mt-3"><TopoLegend /></div>
          {topo && (
            <>
              <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4 text-caption">
                <div><p className="text-muted">Elements</p><p className="tabular mt-1 text-title font-semibold">{topo.nodes.length}</p></div>
                <div><p className="text-muted">Connections</p><p className="tabular mt-1 text-title font-semibold">{topo.edges.length}</p></div>
              </div>
              {/* The Layer 7 canonical gate, stated plainly. Safety-critical topology is not
                  canonical until an engineer has confirmed it element by element. */}
              <div data-testid="topology-gate" className="mt-4 border-t border-line pt-4 text-caption">
                <p className="text-muted">Engineer verification</p>
                <p className="tabular mt-1 text-body font-semibold">
                  {topo.elements_verified} of {topo.elements_total} confirmed
                  {topo.elements_disputed > 0 && (
                    <span className="text-danger"> · {topo.elements_disputed} disputed</span>
                  )}
                </p>
                <p className="mt-2 text-label text-muted">
                  Safety-critical: {topo.safety_critical_verified}/{topo.safety_critical_total}
                </p>
                <p
                  className={`mt-3 rounded-lg px-2 py-1.5 text-label ${
                    topo.canonical_ready ? "bg-verified/10 text-verified" : "bg-surface-2 text-muted"
                  }`}
                >
                  {topo.canonical_ready
                    ? "Canonical — safety-critical topology confirmed."
                    : "Candidate topology — not canonical until every safety-critical element is confirmed."}
                </p>
              </div>
            </>
          )}
        </aside>
      </div>

      {topo && (
        <section data-testid="topology-register" className="mt-6">
          <h2 className="mb-3 text-label font-bold uppercase tracking-[0.1em] text-muted">
            Elements ({topo.nodes.length})
          </h2>
          {saveError && (
            <p data-testid="topology-save-error" role="alert" className="mb-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-caption text-danger">
              {saveError}
            </p>
          )}
          <div className="divide-y divide-line rounded-xl border border-line overflow-hidden">
            {topo.nodes.map((n) => {
              const color = nodeVar(n.node_type, n.verification_status);
              return (
                <div key={n.node_id} className="flex flex-wrap items-center gap-3 px-4 py-3 bg-surface">
                  <span className="size-2 rounded-full shrink-0" style={{ backgroundColor: color }} aria-hidden="true" />
                  <span className="text-caption font-semibold w-24 shrink-0">{n.label}</span>
                  <span className="text-label text-muted">{n.node_type}</span>
                  <span className="ml-auto text-label capitalize" style={{ color }}>{n.verification_status}</span>
                  {canVerify && n.verification_status === "unverified" && (
                    <span className="flex gap-1.5">
                      <Button
                        variant="ghost"
                        onClick={() => decide(n.node_id, "confirmed")}
                        disabled={busyElement !== null}
                        aria-label={`Confirm ${n.label}`}
                      >
                        {busyElement === n.node_id ? "Saving…" : "Confirm"}
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => decide(n.node_id, "rejected")}
                        disabled={busyElement !== null}
                        aria-label={`Reject ${n.label}`}
                      >
                        Reject
                      </Button>
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
