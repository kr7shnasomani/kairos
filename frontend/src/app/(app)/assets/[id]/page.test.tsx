import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AssetDetailPage from "./page";

const mocks = vi.hoisted(() => ({ getAssetDetail: vi.fn() }));

vi.mock("@/lib/api", () => ({ getAssetDetail: mocks.getAssetDetail }));
vi.mock("./asset-search", () => ({ AssetSearch: () => <div>Asset search</div> }));
vi.mock("./hierarchy-panel", () => ({ HierarchyPanel: () => <div>Hierarchy</div> }));
vi.mock("@/components/lazy", () => ({
  KnowledgeGraph: ({ assetId }: { assetId: string }) => <div data-testid="knowledge-graph">{assetId}</div>,
}));

describe("AssetDetailPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("uses a responsive reference-style detail hierarchy", async () => {
    mocks.getAssetDetail.mockResolvedValue({
      source: "live",
      data: {
        asset_id: "P-207",
        name: "Primary feed pump",
        equipment_class: "centrifugal_pump",
        criticalityLabel: "Critical",
        criticalityColor: "#dc2626",
        parent: "TRAIN-A",
        open_work_orders: 4,
        compliance_gaps: 1,
        last_inspection: "2026-06-18",
        aliases: ["Pump-207", "P207-A"],
        knowledge: [{
          claim: "Seal inspection is required every 90 days.",
          authority_level: 2,
          verification: "verified",
          source_doc: "SOP-PUMP-04",
        }],
      },
    });

    render(await AssetDetailPage({ params: Promise.resolve({ id: "P-207" }) }));

    expect(mocks.getAssetDetail).toHaveBeenCalledWith("P-207");
    expect(screen.getByTestId("asset-detail-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("asset-summary")).toHaveClass("rounded-xl", "bg-surface");
    expect(screen.getByTestId("asset-detail-columns")).toHaveClass("fluid-tile-pair");
    expect(screen.getByTestId("asset-detail-columns")).not.toHaveClass("lg:items-start");
    expect(screen.getByRole("heading", { name: "Primary feed pump" })).toBeInTheDocument();
    expect(screen.getByText("Seal inspection is required every 90 days.")).toBeInTheDocument();
    expect(screen.getByText("Pump-207")).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-graph")).toHaveTextContent("P-207");
  });
});
