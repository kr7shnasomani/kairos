import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ConflictDetailPage from "./page";

const mocks = vi.hoisted(() => ({ getConflictDetail: vi.fn(), resolveConflict: vi.fn(), role: "engineer" }));

vi.mock("@/lib/api", () => ({ getConflictDetail: mocks.getConflictDetail, resolveConflict: mocks.resolveConflict }));
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "c-1" }) }));
vi.mock("@/components/lazy", () => ({ BlastRadiusPanel: ({ documentId }: { documentId: string }) => <div>Blast radius {documentId}</div> }));
vi.mock("@/components/use-role", () => ({ useRole: () => mocks.role, RESOLVE_ROLES: ["engineer", "reliability", "admin"] }));

window.matchMedia = ((query: string) => ({
  matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
})) as unknown as typeof window.matchMedia;

function conflict(over: Record<string, unknown> = {}) {
  return {
    conflict_id: "c-1", track: "administrative", asset_id: "HE-301", parameter: "max_operating_pressure",
    source_a: { document_id: "DOC-OEM", value: "18.5 bar", source: "OEM manual", authority_level: 1 },
    source_b: { document_id: "DOC-LOG", value: "16.2 bar", authority_level: 4, confidence: 0.8 },
    authority_a: 1, authority_b: 4, severity: "major", status: "open",
    sla_due_at: new Date(Date.now() + 48 * 3_600_000).toISOString(), is_overdue: false,
    created_at: new Date().toISOString(), ...over,
  };
}

describe("ConflictDetailPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    mocks.role = "engineer";
  });

  it("shows both sources with provenance links and the blast radius of source A", async () => {
    mocks.getConflictDetail.mockResolvedValue({ data: conflict(), source: "live" });
    render(<ConflictDetailPage />);

    expect(await screen.findByText("18.5 bar")).toBeInTheDocument();
    expect(screen.getByText("16.2 bar")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "DOC-OEM" })).toHaveAttribute("href", "/documents/DOC-OEM");
    expect(screen.getByRole("link", { name: "HE-301" })).toHaveAttribute("href", "/assets/HE-301");
    expect(screen.getByText("Blast radius DOC-OEM")).toBeInTheDocument();
    expect(mocks.getConflictDetail).toHaveBeenCalledWith("c-1");
  });

  it("resolves an administrative conflict with the note", async () => {
    mocks.getConflictDetail.mockResolvedValue({ data: conflict(), source: "live" });
    mocks.resolveConflict.mockResolvedValue({});
    render(<ConflictDetailPage />);

    fireEvent.change(await screen.findByLabelText("Resolution note"), { target: { value: "OEM governs" } });
    fireEvent.click(screen.getByRole("button", { name: "Accept higher authority" }));

    await waitFor(() => expect(mocks.resolveConflict).toHaveBeenCalledWith("c-1", { decision: "accept_higher_authority", note: "OEM governs" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Resolved");
  });

  it("routes an engineering conflict to MoC instead of offering a resolve button", async () => {
    mocks.getConflictDetail.mockResolvedValue({ data: conflict({ track: "engineering" }), source: "live" });
    render(<ConflictDetailPage />);

    expect(await screen.findByRole("link", { name: "Open MoC queue" })).toHaveAttribute("href", "/governance/moc");
    expect(screen.queryByRole("button", { name: "Accept higher authority" })).not.toBeInTheDocument();
  });

  it("does not offer resolution to a role that cannot resolve", async () => {
    mocks.role = "field_worker";
    mocks.getConflictDetail.mockResolvedValue({ data: conflict(), source: "live" });
    render(<ConflictDetailPage />);

    expect(await screen.findByText(/requires the engineer/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept higher authority" })).not.toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    mocks.getConflictDetail.mockRejectedValue(new Error("HTTP 404"));
    render(<ConflictDetailPage />);

    expect(await screen.findByText("Couldn't load this conflict.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
