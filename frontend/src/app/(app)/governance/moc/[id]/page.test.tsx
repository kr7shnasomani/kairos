import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MocDetailPage from "./page";

const mocks = vi.hoisted(() => ({ getMoc: vi.fn(), approveMoc: vi.fn(), draftMoc: vi.fn() }));

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "MOC-2024-001" }) }));
vi.mock("next/dynamic", () => ({ default: () => () => <div data-testid="blast-radius" /> }));
vi.mock("@/lib/api", () => ({ getToken: () => null, getMoc: mocks.getMoc, approveMoc: mocks.approveMoc, draftMoc: mocks.draftMoc }));

const moc = {
  moc_id: "MOC-2024-001",
  asset_id: "P-101",
  parameter: "operating_pressure",
  source_a: { value: "12.5 bar", document_id: "DOC-OEM-001" },
  source_b: { value: "14.0 bar", document_id: "DOC-INSP-007" },
  blast_radius_count: 7,
  status: "pending",
  created_at: "2026-07-14T10:00:00Z",
  draft_content: "Engineering review draft.",
};

describe("MocDetailPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("uses a case-file layout with a sticky engineering decision panel", async () => {
    mocks.getMoc.mockResolvedValue({ data: moc, source: "live" });

    render(<MocDetailPage />);

    await waitFor(() => expect(screen.getByText("Engineering review draft.")).toBeInTheDocument());
    expect(screen.getByTestId("moc-case-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("moc-case-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_320px]");
    expect(screen.getByTestId("moc-evidence")).toHaveTextContent("12.5 bar");
    expect(screen.getByTestId("moc-decision")).toHaveClass("lg:sticky", "lg:top-6");
    expect(screen.getByRole("button", { name: "Approve MoC" })).toHaveClass("min-h-11");
  });

  it("drafts the change on request and shows each edit with its citation", async () => {
    mocks.getMoc.mockResolvedValue({ data: { ...moc, draft: null }, source: "live" });
    mocks.draftMoc.mockResolvedValue({
      moc_id: moc.moc_id,
      draft_generated_at: "2026-10-18T10:00:00Z",
      draft: {
        summary: "Raise the minimum flow to 150 m3/h.",
        changes: [{ document_id: "DOC-SOP", title: "SOP-CDU-pump.pdf", location: "Step 4", current: "120 m3/h", proposed: "150 m3/h", reason: "Bulletin revision", cited: ["DOC-BUL"] }],
        open_questions: ["Re-issue the start-up checklist?"],
      },
    });
    render(<MocDetailPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Draft the change" }));

    expect(await screen.findByText("150 m3/h")).toBeInTheDocument();
    expect(mocks.draftMoc).toHaveBeenCalledWith("MOC-2024-001");
    expect(screen.getByRole("link", { name: "SOP-CDU-pump.pdf" })).toHaveAttribute("href", "/documents/DOC-SOP");
    expect(screen.getByText("DOC-BUL")).toBeInTheDocument();
    expect(screen.getByText("Re-issue the start-up checklist?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Redraft" })).toBeInTheDocument();
  });

  it("offers no drafting on a closed MoC", async () => {
    mocks.getMoc.mockResolvedValue({ data: { ...moc, status: "approved", draft: null }, source: "live" });
    render(<MocDetailPage />);
    await screen.findByText(/Approved/);
    expect(screen.queryByRole("button", { name: "Draft the change" })).not.toBeInTheDocument();
  });
});
