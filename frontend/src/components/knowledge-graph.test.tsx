import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KnowledgeGraph, buildRFNodes } from "./knowledge-graph";

const mocks = vi.hoisted(() => ({ getKnowledgeGraph: vi.fn(), getOtCoverage: vi.fn() }));

vi.mock("@/lib/api", () => ({
  getKnowledgeGraph: mocks.getKnowledgeGraph,
  getOtCoverage: mocks.getOtCoverage,
}));

vi.mock("@/lib/graph-theme", () => {
  const tokens = {
    "--accent": "#2563eb",
    "--danger": "#dc2626",
    "--caution": "#d97706",
    "--muted": "#64748b",
    "--info": "#0284c7",
    "--verified": "#16a34a",
    "--surface": "#fff",
    "--line": "#e2e8f0",
  };
  return {
    arrowMarker: vi.fn(() => undefined),
    useCanvasTokens: () => tokens,
  };
});

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    ReactFlow: ({ nodes, onNodeClick, children }: { nodes: Array<{ data: unknown }>; onNodeClick: (event: unknown, node: unknown) => void; children: React.ReactNode }) => (
      <div>
        {nodes[0] && <button onClick={() => onNodeClick({}, nodes[0])}>Select graph node</button>}
        {children}
      </div>
    ),
    Background: () => null,
    Controls: () => null,
    Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    useReactFlow: () => ({ fitView: vi.fn() }),
    useNodesInitialized: () => true,
    Handle: () => null,
    Position: { Top: "top", Bottom: "bottom" },
    useNodesState: (initial: unknown[]) => {
      const [nodes, setNodes] = React.useState(initial);
      return [nodes, setNodes, vi.fn()];
    },
    useEdgesState: (initial: unknown[]) => {
      const [edges, setEdges] = React.useState(initial);
      return [edges, setEdges, vi.fn()];
    },
  };
});

describe("KnowledgeGraph", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("uses a mobile-safe inspection panel with an accessible close target", async () => {
    mocks.getKnowledgeGraph.mockResolvedValue({
      source: "live",
      data: {
        asset_id: "P-101",
        as_of: "2026-07-15T00:00:00Z",
        nodes: [{ id: "P-101", label: "Pump P-101", kind: "Asset", properties: { site: "SITE-A" } }],
        edges: [],
      },
    });
    mocks.getOtCoverage.mockResolvedValue({ data: null, source: "live" });

    render(<KnowledgeGraph assetId="P-101" />);
    fireEvent.click(await screen.findByRole("button", { name: "Select graph node" }));

    const panel = screen.getByText("Pump P-101").closest("div.absolute");
    expect(panel).toHaveClass("inset-x-3", "bottom-3", "sm:right-3", "sm:top-3", "sm:w-72");
    expect(screen.getByRole("button", { name: "Close panel" })).toHaveClass("min-h-11", "min-w-11");
  });

  it("keeps the coverage indicator clear of the lower-left zoom controls", async () => {
    mocks.getKnowledgeGraph.mockResolvedValue({
      source: "live",
      data: {
        asset_id: "P-101",
        as_of: "2026-07-15T00:00:00Z",
        nodes: [{ id: "P-101", label: "Pump P-101", kind: "Asset", properties: {} }],
        edges: [],
      },
    });
    mocks.getOtCoverage.mockResolvedValue({
      source: "live",
      data: { coverage_type: "none", sensor_tags: [] },
    });

    render(<KnowledgeGraph assetId="P-101" />);

    expect((await screen.findByText("No sensor coverage")).parentElement).toHaveClass("top-4", "left-4");
  });
});

describe("buildRFNodes layout", () => {
  const edge = (id: string, source: string, target: string) => ({
    id, source, target, label: "X", authority_level: 3, verification_status: "verified" as const,
    valid_from: "2025-01-01T00:00:00Z", valid_to: "9999-12-31T23:59:59Z", document_id: "", confidence: 1,
  });
  const node = (id: string, kind: string) => ({ id, label: id, kind, properties: {} });
  const docs = Array.from({ length: 12 }, (_, i) => node(`D${i}`, "Document"));
  const graph = {
    asset_id: "A", as_of: "now", excluded_test_documents: 0,
    nodes: [node("A", "Asset"), node("U", "Asset"), ...docs, node("P1", "Person"), node("O1", "Organisation"), node("A2", "Asset")],
    edges: [
      edge("u", "U", "A"),
      ...docs.map((d) => edge(`d-${d.id}`, "A", d.id)),
      edge("p1a", "D0", "P1"), edge("p1b", "D1", "P1"), edge("o1", "D6", "O1"), edge("a2", "A2", "D6"),
    ],
  };
  const pos = (nodes: ReturnType<typeof buildRFNodes>, id: string) => nodes.find((n) => n.id === id)!.position;

  // Each card is 132 by 50; the layout is built on those numbers.
  const overlaps = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.abs(a.x - b.x) < 132 && Math.abs(a.y - b.y) < 50;
  // Distance from the centre in the ellipse's own units (the rings are wider than tall).
  const reach = (nodes: ReturnType<typeof buildRFNodes>, id: string) => Math.hypot((pos(nodes, id).x + 66) / 1.75, pos(nodes, id).y + 25);

  it("puts the asset in the centre, what it touches on an inner ring and what only those reach on an outer one", () => {
    const nodes = buildRFNodes(graph);
    expect(pos(nodes, "A")).toEqual({ x: -66, y: -25 });
    for (const inner of ["D0", "D7", "U"]) expect(reach(nodes, "P1")).toBeGreaterThan(reach(nodes, inner) + 50);
  });

  it("never lets two cards overlap, however many documents an asset has", () => {
    const many = Array.from({ length: 30 }, (_, i) => node(`M${i}`, "Document"));
    const big = { ...graph, nodes: [...graph.nodes, ...many], edges: [...graph.edges, ...many.map((d) => edge(`m-${d.id}`, "A", d.id))] };
    for (const g of [graph, big]) {
      const nodes = buildRFNodes(g);
      for (const a of nodes) for (const b of nodes) {
        if (a.id < b.id) expect(overlaps(a.position, b.position), `${a.id} overlaps ${b.id}`).toBe(false);
      }
    }
  });

  it("places a person shared by two documents between them", () => {
    const nodes = buildRFNodes(graph);
    const angle = (id: string) => Math.atan2(pos(nodes, id).y, pos(nodes, id).x);
    const [lo, hi] = [angle("D0"), angle("D1")].sort((x, y) => x - y);
    expect(angle("P1")).toBeGreaterThanOrEqual(lo - 0.05);
    expect(angle("P1")).toBeLessThanOrEqual(hi + 0.05);
  });
});
