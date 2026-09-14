import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getDocumentStatus, ingestDocument } from "@/lib/api";
import IngestPage from "./page";

vi.mock("@/components/use-role", () => ({
  useRole: () => "engineer",
  RESOLVE_ROLES: ["engineer", "admin"],
}));

vi.mock("@/lib/api", () => ({
  ingestDocument: vi.fn(),
  getDocumentStatus: vi.fn(),
}));

describe("IngestPage", () => {
  afterEach(cleanup);

  it("uses a guided intake while preserving document metadata fields", () => {
    render(<IngestPage />);

    expect(screen.getByTestId("ingest-workspace")).toHaveClass("max-w-[1200px]");
    expect(screen.getByTestId("ingest-intake")).toHaveClass("lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)]");
    expect(screen.getByTestId("ingest-file-drop")).toBeInTheDocument();
    expect(screen.getByTestId("ingest-metadata")).toBeInTheDocument();
    expect(screen.getByTestId("ingest-guide")).toHaveTextContent("Vault storage");
    expect(screen.getByLabelText("Document type")).toBeInTheDocument();
    expect(screen.getByLabelText("Authority level")).toBeInTheDocument();
    expect(screen.getByLabelText(/Asset link/)).toBeInTheDocument();
    expect(screen.getByLabelText("Source system")).toBeInTheDocument();

    const file = new File(["procedure"], "procedure.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Document file"), { target: { files: [file] } });
    expect(screen.getByText("procedure.pdf")).toBeInTheDocument();
  });

  it("defaults the authority level from the chosen document type", () => {
    render(<IngestPage />);

    fireEvent.change(screen.getByLabelText("Document type"), { target: { value: "regulation" } });

    expect(screen.getByLabelText("Authority level")).toHaveValue("1");
  });

  it("marks every step done once the pipeline completes — nothing left in progress", async () => {
    vi.mocked(ingestDocument).mockResolvedValue({ document_id: "DOC-1", status: "queued" } as never);
    vi.mocked(getDocumentStatus).mockResolvedValue({
      data: { document_id: "DOC-1", stage: "complete", updated_at: "", details: null },
      source: "live",
    });
    render(<IngestPage />);

    const file = new File(["x"], "report.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Document file"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Ingest document" }));

    expect(await screen.findAllByText("done")).toHaveLength(6);
    expect(screen.queryByText("in progress")).not.toBeInTheDocument();
  });
});
