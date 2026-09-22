import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CompareRoute from "./page";

const documents = {
  "DOC-A": { document_id: "DOC-A", file_name: "manual-r2.pdf", document_type: "oem_manual", authority_level: 3, source_system: "OEM", vault_url: null, status: "superseded", ingested_at: "2025-01-01T00:00:00Z", ingested_by: "engineer", asset_links: ["P-101"] },
  "DOC-B": { document_id: "DOC-B", file_name: "manual-r3.pdf", document_type: "oem_manual", authority_level: 3, source_system: "OEM", vault_url: null, status: "active", ingested_at: "2026-01-01T00:00:00Z", ingested_by: "engineer", asset_links: ["P-101", "P-102"] },
};

vi.mock("next/navigation", () => ({ useSearchParams: () => ({ get: () => null }) }));
vi.mock("@/lib/api", () => ({
  getDocument: vi.fn(async (id: keyof typeof documents) => ({ data: documents[id] ?? null, source: "api" })),
}));

describe("CompareRoute", () => {
  afterEach(cleanup);

  it("renders document differences in one aligned responsive matrix", async () => {
    render(<CompareRoute />);
    fireEvent.change(screen.getByLabelText("Document A"), { target: { value: "DOC-A" } });
    fireEvent.change(screen.getByLabelText("Document B"), { target: { value: "DOC-B" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    await waitFor(() => expect(screen.getByTestId("document-compare-matrix")).toBeInTheDocument());
    expect(screen.getByTestId("compare-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("compare-toolbar")).toHaveClass("rounded-xl", "bg-surface");
    expect(screen.getByTestId("compare-row-file")).toHaveClass("md:grid-cols-[minmax(120px,0.45fr)_minmax(0,1fr)_minmax(0,1fr)]");
    expect(screen.getByTestId("compare-value-file-a")).toHaveClass("bg-[color-mix(in_srgb,var(--caution)_10%,transparent)]");
    expect(screen.getByTestId("compare-value-authority-a")).not.toHaveClass("bg-[color-mix(in_srgb,var(--caution)_10%,transparent)]");
    expect(screen.getByRole("link", { name: /Open document A/ })).toHaveAttribute("href", "/documents/DOC-A");
    expect(screen.getByRole("link", { name: /Open document B/ })).toHaveAttribute("href", "/documents/DOC-B");
  });
});
