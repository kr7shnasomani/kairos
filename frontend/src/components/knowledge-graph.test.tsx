import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KnowledgeGraph } from "./knowledge-graph";

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
