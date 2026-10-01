import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getDocumentStatus, ingestDocument } from "@/lib/api";
import IngestPage from "./page";

let mockRole = "engineer";
vi.mock("@/components/use-role", () => ({
  useRole: () => mockRole,
  RESOLVE_ROLES: ["engineer", "reliability", "admin"],
  AUTHORITY_ASSERT_ROLES: ["reliability", "admin"],
}));

vi.mock("@/lib/api", () => ({
  ingestDocument: vi.fn(),
  getDocumentStatus: vi.fn(),
}));

describe("IngestPage", () => {
  afterEach(() => {
    cleanup();
    mockRole = "engineer";
  });

  it("uses a guided intake while preserving document metadata fields", () => {
    render(<IngestPage />);

    expect(screen.getByTestId("ingest-workspace")).toHaveClass("max-w-[1400px]");
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
    mockRole = "admin";
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

  it("does not offer levels 1 to 3 to a role that cannot assert them, even for an OEM manual", () => {
    render(<IngestPage />);

    fireEvent.change(screen.getByLabelText("Document type"), { target: { value: "oem_manual" } });

    expect(screen.getAllByRole("option", { name: /^L\d$/ }).map((o) => o.textContent)).toEqual(["L4", "L5"]);
    expect(screen.getByLabelText("Authority level")).toHaveValue("4");
  });

  it("tells the uploader when the authority level was capped", async () => {
    vi.mocked(ingestDocument).mockResolvedValue({
      status: "accepted", document_id: "DOC-1", sha256: "x", message: "",
      authority_level: 4, authority_requested: 3, authority_capped: true,
    });
    vi.mocked(getDocumentStatus).mockResolvedValue({ data: null, source: "live" } as never);
    mockRole = "admin"; // asserts L3 client side; the server's verdict is what the notice reflects
    render(<IngestPage />);
    fireEvent.change(screen.getByLabelText("Document file"), { target: { files: [new File(["x"], "m.pdf")] } });
    fireEvent.click(screen.getByRole("button", { name: "Ingest document" }));

    const notice = await screen.findByTestId("ingest-authority-capped");
    expect(notice).toHaveTextContent("You asked for L3");
    expect(notice).toHaveTextContent("stored as L4");
  });

  it("shows no capped notice when the level stuck", async () => {
    vi.mocked(ingestDocument).mockResolvedValue({
      status: "accepted", document_id: "DOC-2", sha256: "x", message: "",
      authority_level: 4, authority_requested: 4, authority_capped: false,
    });
    vi.mocked(getDocumentStatus).mockResolvedValue({ data: null, source: "live" } as never);
    render(<IngestPage />);
    fireEvent.change(screen.getByLabelText("Document file"), { target: { files: [new File(["x"], "m.pdf")] } });
    fireEvent.click(screen.getByRole("button", { name: "Ingest document" }));

    await screen.findByText("DOC-2");
    expect(screen.queryByTestId("ingest-authority-capped")).not.toBeInTheDocument();
  });
});
