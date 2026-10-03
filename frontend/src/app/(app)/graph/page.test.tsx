import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GraphPage from "./page";

const mocks = vi.hoisted(() => ({ getKnowledgeGraph: vi.fn() }));

vi.mock("@/lib/api", () => ({ getKnowledgeGraph: mocks.getKnowledgeGraph }));
vi.mock("@/components/knowledge-graph", () => ({
  KnowledgeGraph: ({ assetId, asOf }: { assetId: string; asOf?: string }) => (
    <div data-testid="knowledge-graph" data-asset={assetId} data-as-of={asOf} />
  ),
}));

const graph = {
  asset_id: "P-101",
  as_of: "2026-07-15T00:00:00Z",
  nodes: [
    { id: "P-101", label: "Pump P-101", kind: "Asset", properties: {} },
    { id: "DOC-1", label: "Seal procedure", kind: "Document", properties: {} },
    { id: "EV-1", label: "Seal alarm", kind: "Event", properties: {} },
  ],
  edges: [
    { id: "E-1", source: "P-101", target: "DOC-1", label: "governed_by", authority_level: 2, verification_status: "verified" as const, valid_from: "2024-01-01T00:00:00Z", valid_to: "9999-12-31T23:59:59Z", document_id: "DOC-1", confidence: 0.94 },
    { id: "E-2", source: "P-101", target: "EV-1", label: "reported_by", authority_level: 4, verification_status: "unverified" as const, valid_from: "2025-01-01T00:00:00Z", valid_to: "9999-12-31T23:59:59Z", document_id: "", confidence: 0.62 },
  ],
};

describe("GraphPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("presents the temporal graph as a responsive investigation workspace", async () => {
    mocks.getKnowledgeGraph.mockResolvedValue({ data: graph, source: "live" });

    render(<GraphPage />);

    expect(screen.getByTestId("graph-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("graph-controls")).toHaveClass("rounded-xl", "bg-surface");
    expect(screen.getByTestId("graph-layout")).toHaveClass("min-w-0");
    expect(screen.getByTestId("graph-context")).toHaveTextContent("Authority & verification");
    await waitFor(() => expect(screen.getByTestId("graph-summary")).toHaveTextContent("3 nodes"));
    expect(screen.getByTestId("graph-summary")).toHaveTextContent("2 relationships");
    expect(screen.getByTestId("knowledge-graph")).toHaveAttribute("data-asset", "DEMO-P-1101A");
  });
});
