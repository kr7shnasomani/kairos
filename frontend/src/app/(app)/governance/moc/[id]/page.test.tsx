import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MocDetailPage from "./page";

const mocks = vi.hoisted(() => ({ getMoc: vi.fn(), approveMoc: vi.fn() }));

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "MOC-2024-001" }) }));
vi.mock("next/dynamic", () => ({ default: () => () => <div data-testid="blast-radius" /> }));
vi.mock("@/lib/api", () => ({ getToken: () => null, getMoc: mocks.getMoc, approveMoc: mocks.approveMoc }));

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
});
