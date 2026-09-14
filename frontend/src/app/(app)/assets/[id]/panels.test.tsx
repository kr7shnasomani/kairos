import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssetSearch } from "./asset-search";
import { HierarchyPanel } from "./hierarchy-panel";

const mocks = vi.hoisted(() => ({ getAssetHierarchy: vi.fn(), searchAsset: vi.fn() }));

vi.mock("@/lib/api", () => mocks);

window.matchMedia = ((query: string) => ({
  matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
})) as unknown as typeof window.matchMedia;

describe("HierarchyPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("links the parent chain and the children", async () => {
    mocks.getAssetHierarchy.mockResolvedValue({
      source: "live",
      data: {
        asset: { asset_id: "P-101" },
        ancestors: [{ asset_id: "SITE-A", name: "Site A" }, { asset_id: "TRAIN-A" }],
        children: [{ asset_id: "P-101-SEAL", name: "Mechanical seal" }],
      },
    });
    render(<HierarchyPanel assetId="P-101" />);

    expect(await screen.findByRole("link", { name: "TRAIN-A" })).toHaveAttribute("href", "/assets/TRAIN-A");
    expect(screen.getByRole("link", { name: /SITE-A/ })).toHaveAttribute("href", "/assets/SITE-A");
    expect(screen.getByRole("link", { name: /P-101-SEAL/ })).toHaveAttribute("href", "/assets/P-101-SEAL");
    expect(screen.getByText("Children (1)")).toBeInTheDocument();
  });

  it("says when an asset is top-level with no children", async () => {
    mocks.getAssetHierarchy.mockResolvedValue({ source: "live", data: { asset: { asset_id: "P-101" }, ancestors: [], children: [] } });
    render(<HierarchyPanel assetId="P-101" />);

    expect(await screen.findByText("Top-level asset — no parent recorded.")).toBeInTheDocument();
    expect(screen.getByText("No child assets.")).toBeInTheDocument();
  });
});

describe("AssetSearch", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("searches within the asset and links results to their documents", async () => {
    mocks.searchAsset.mockResolvedValue([
      { document_id: "DOC-9", document_type: "sop", title: "Seal replacement SOP", snippet: "Replace the seal when…", authority_level: 2 },
    ]);
    render(<AssetSearch assetId="P-101" />);

    fireEvent.change(screen.getByRole("searchbox", { name: "Search P-101" }), { target: { value: "seal" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("link", { name: "Seal replacement SOP" })).toHaveAttribute("href", "/documents/DOC-9");
    expect(mocks.searchAsset).toHaveBeenCalledWith("P-101", "seal");
  });

  it("reports no matches", async () => {
    mocks.searchAsset.mockResolvedValue([]);
    render(<AssetSearch assetId="P-101" />);

    fireEvent.change(screen.getByRole("searchbox", { name: "Search P-101" }), { target: { value: "nothing" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("No documents for P-101 match that query.")).toBeInTheDocument();
  });
});
