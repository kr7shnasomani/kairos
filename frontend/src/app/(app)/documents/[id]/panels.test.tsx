import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExtractionPanel } from "./extraction-panel";
import { RedactedExport } from "./redacted-export";

const mocks = vi.hoisted(() => ({ getDocumentExtraction: vi.fn(), getRedactedDocument: vi.fn() }));

vi.mock("@/lib/api", () => mocks);

window.matchMedia = ((query: string) => ({
  matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
})) as unknown as typeof window.matchMedia;

describe("ExtractionPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows linked entities and what was held in quarantine", async () => {
    mocks.getDocumentExtraction.mockResolvedValue({
      source: "live",
      data: {
        document_id: "DOC-1", extraction_model: "ner + ocr", graph_edges_created: 3, extraction_path: "native", handwriting_suspect: false,
        entities: [
          { entity_type: "asset_tag", value: "HE-301", confidence: 0.95, linked_asset_id: "HE-301", requires_review: false },
          { entity_type: "person", value: "Ravi Kumar", confidence: 0.8, linked_asset_id: null, requires_review: true },
        ],
        review_items: [{ item_id: "q-1", content: "Low-confidence entity: 'HE301X'", review_status: "pending", submitted_at: "2026-07-14T10:00:00Z" }],
      },
    });
    render(<ExtractionPanel documentId="DOC-1" />);

    expect(await screen.findByRole("link", { name: "HE-301" })).toHaveAttribute("href", "/assets/HE-301");
    expect(screen.getByText("Ravi Kumar")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("Held in quarantine (1, 1 pending)")).toBeInTheDocument();
    expect(screen.getByText("Low-confidence entity: 'HE301X'")).toBeInTheDocument();
  });

  it("is honest when nothing was linked", async () => {
    mocks.getDocumentExtraction.mockResolvedValue({
      source: "live",
      data: { document_id: "DOC-1", extraction_model: "x", graph_edges_created: 0, extraction_path: "ocr", handwriting_suspect: true, entities: [], review_items: [] },
    });
    render(<ExtractionPanel documentId="DOC-1" />);

    expect(await screen.findByText("No entities from this document are linked into the graph.")).toBeInTheDocument();
    expect(screen.getByText("Read from image (OCR)")).toBeInTheDocument();
  });
});

describe("RedactedExport", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("fetches the export only on request and shows masked text with counts", async () => {
    mocks.getRedactedDocument.mockResolvedValue({
      document_id: "DOC-1", document_type: "shift_log", redacted_text: "Handed over by [PERSON_1].",
      pii_found: true, pii_counts: { person: 1, phone: 0 }, pii_span_count: 1, note: "",
    });
    render(<RedactedExport documentId="DOC-1" />);
    expect(mocks.getRedactedDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Export redacted text" }));

    expect(await screen.findByText("Handed over by [PERSON_1].")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 identifiers masked");
    expect(screen.getByText("person · 1")).toBeInTheDocument();
    expect(screen.queryByText(/phone/)).not.toBeInTheDocument();
  });

  it("shows the failure next to the action", async () => {
    mocks.getRedactedDocument.mockRejectedValue(new Error("/documents/DOC-1/redacted → HTTP 404"));
    render(<RedactedExport documentId="DOC-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Export redacted text" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 404");
  });
});
