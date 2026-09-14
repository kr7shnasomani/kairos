import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DocumentDetailPage from "./page";

vi.mock("@/lib/api", () => ({
  getDocument: vi.fn().mockResolvedValue({
    data: {
      document_id: "DOC-1", file_name: "P-101 inspection.pdf", document_type: "inspection_report",
      authority_level: 2, source_system: "SAP PM", vault_url: null, status: "active",
      ingested_at: "2026-07-15T08:00:00Z", ingested_by: "engineer@kairos.test",
      file_size_bytes: 2048, mime_type: "application/pdf", sha256_hash: "abc123",
      version_chain: null, asset_links: ["P-101"],
    },
    source: "api",
  }),
}));

vi.mock("./extraction-panel", () => ({ ExtractionPanel: () => <div>Extraction</div> }));
vi.mock("./redacted-export", () => ({ RedactedExport: () => <div>Redacted export</div> }));
vi.mock("@/components/lazy", () => ({
  BlastRadiusPanel: () => <div>Blast radius</div>,
  SupersedeAction: () => <button>Supersede</button>,
}));

describe("DocumentDetailPage", () => {
  afterEach(cleanup);

  it("presents an immutable document case file with responsive context", async () => {
    render(await DocumentDetailPage({ params: Promise.resolve({ id: "DOC-1" }) }));

    expect(screen.getByTestId("document-detail-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("document-detail-summary")).toHaveClass("sm:grid-cols-2", "xl:grid-cols-4");
    expect(screen.getByTestId("document-detail-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_320px]");
    expect(screen.getByTestId("document-evidence")).toHaveTextContent("Provenance");
    expect(screen.getByTestId("document-context")).toHaveClass("lg:sticky");
    expect(screen.getByTestId("document-context")).toHaveTextContent("Linked assets");
  });
});
