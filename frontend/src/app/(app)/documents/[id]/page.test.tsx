import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getDocument, getDocumentStatus } from "@/lib/api";
import DocumentDetailPage from "./page";

vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("NEXT_NOT_FOUND"); } }));

vi.mock("@/lib/api", () => ({
  isForbidden: () => false,
  isNotFound: (e: unknown) => e instanceof Error && e.message.endsWith("HTTP 404"),
  getDocumentStatus: vi.fn().mockResolvedValue({
    data: { document_id: "DOC-1", stage: "complete", updated_at: "2026-07-15T08:00:00Z", details: null },
    source: "live",
  }),
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
vi.mock("./ocr-review-actions", () => ({ OcrReviewActions: () => <div>Review actions</div> }));
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
    expect(screen.queryByTestId("ocr-review-held")).not.toBeInTheDocument();
  });

  it("says plainly when the OCR gate held the document for review", async () => {
    vi.mocked(getDocumentStatus).mockResolvedValueOnce({
      data: {
        document_id: "DOC-1", stage: "review_required", updated_at: "2026-07-15T08:00:00Z",
        details: "OCR span-confidence gate: 4 span(s) below 0.7 (min=0.253, overall=0.719)",
      },
      source: "live",
    });
    render(await DocumentDetailPage({ params: Promise.resolve({ id: "DOC-1" }) }));

    const held = screen.getByTestId("ocr-review-held");
    expect(held).toHaveTextContent("Held for OCR review");
    expect(held).toHaveTextContent("4 span(s) below 0.7");
    expect(held).toHaveTextContent("has not been indexed or linked");
  });

  it("sends an unknown document id to the not-found page instead of the error screen", async () => {
    vi.mocked(getDocument).mockRejectedValueOnce(new Error("/documents/DOC-GONE → HTTP 404"));
    await expect(DocumentDetailPage({ params: Promise.resolve({ id: "DOC-GONE" }) })).rejects.toThrow("NEXT_NOT_FOUND");
  });
});
