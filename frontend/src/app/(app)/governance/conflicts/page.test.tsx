import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Conflict } from "@/lib/types";
import ConflictsPage from "./page";

const mocks = vi.hoisted(() => ({ getConflicts: vi.fn(), resolveConflict: vi.fn() }));

vi.mock("@/lib/api", () => ({
  getConflicts: mocks.getConflicts,
  resolveConflict: mocks.resolveConflict,
}));

function item(i: number, over: Partial<Conflict> = {}): Conflict {
  return {
    conflict_id: `CONF-${i}`, track: "administrative", asset_id: `P-${i}`,
    parameter: "operating_pressure", source_a: { value: "1" }, source_b: { value: "2" },
    authority_a: 1, authority_b: 2, severity: "major", status: "open",
    sla_due_at: null, is_overdue: false, created_at: "2026-07-01T00:00:00Z", ...over,
  };
}

function respond(items: Conflict[]) {
  mocks.getConflicts.mockResolvedValue({ data: { items, total: items.length, limit: 100, offset: 0 }, source: "live" });
}

describe("ConflictsPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("paginates a 10k queue to at most 25 rendered rows with stat pills", async () => {
    respond(Array.from({ length: 10_000 }, (_, i) => item(i)));

    render(<ConflictsPage />);

    await waitFor(() => expect(screen.getByText("CONF-0")).toBeInTheDocument());
    expect(document.querySelectorAll("tbody tr").length).toBeLessThanOrEqual(25);
    expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument();
    expect(screen.getByTestId("conflicts-summary")).toHaveTextContent("Open");
  });

  it("resolves an administrative conflict optimistically and hides engineering resolve", async () => {
    mocks.resolveConflict.mockResolvedValue({});
    respond([item(1), item(2, { track: "engineering", status: "pending_moc" })]);

    render(<ConflictsPage />);

    await waitFor(() => expect(screen.getByText("CONF-1")).toBeInTheDocument());
    // Engineering row routes to MoC instead of exposing a resolve action.
    expect(screen.getByRole("link", { name: "MoC required ›" })).toHaveAttribute("href", "/governance/moc");

    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));
    await waitFor(() => expect(mocks.resolveConflict).toHaveBeenCalledWith("CONF-1", { decision: "accept_higher_authority" }));
    // Optimistic: still under the default "Open" tab the row drops out.
    await waitFor(() => expect(screen.queryByText("CONF-1")).not.toBeInTheDocument());
  });

  it("shows the tailored empty state and an error surface with retry", async () => {
    respond([]);
    render(<ConflictsPage />);
    await waitFor(() => expect(screen.getByText("No conflicts — knowledge is consistent ✓")).toBeInTheDocument());
    cleanup();

    mocks.getConflicts.mockRejectedValueOnce(new Error("offline"));
    respond([item(9)]);
    render(<ConflictsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByText("CONF-9")).toBeInTheDocument());
  });
});

describe("parameter & sources column", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // The flagship engineering conflict. It is the one row that carries `value`, and it is the
  // reason this column exists — it must keep rendering the disagreement verbatim.
  it("shows the disagreement when the conflict records contradicting values", async () => {
    respond([
      item(1, {
        parameter: "Max Operating Pressure",
        source_a: { value: "18.5 bar", source: "Meridian OEM Manual (2019)", authority_level: 3 },
        source_b: { value: "16.2 bar", source: "Meridian Service Bulletin", authority_level: 3 },
      }),
    ]);

    render(<ConflictsPage />);

    await waitFor(() => expect(screen.getByText("18.5 bar vs 16.2 bar")).toBeInTheDocument());
  });

  // Regression: 93 of 94 live conflicts come from detect_conflict, which never compares values
  // and therefore stores none. Reading source.value on those rendered the literal "— vs —".
  it("names both sources instead of printing dashes when no values were recorded", async () => {
    respond([
      item(2, {
        parameter: "DOCUMENTED_BY",
        source_a: { document_id: "DOC-AAA", authority_level: 4 },
        source_b: { document_id: "DOC-BBB", authority_level: 4 },
      }),
    ]);

    render(<ConflictsPage />);

    await waitFor(() => expect(screen.getByText("DOC-AAA (L4), DOC-BBB (L4)")).toBeInTheDocument());
    expect(screen.queryByText(/—\s*vs\s*—/)).not.toBeInTheDocument();
  });

  // "vs" asserts a disagreement. Co-documentation is not one, so it must not borrow the word.
  it("reserves 'vs' for a real contradiction", async () => {
    respond([
      item(3, {
        parameter: "DOCUMENTED_BY",
        source_a: { document_id: "DOC-AAA", authority_level: 4 },
        source_b: { document_id: "DOC-BBB", authority_level: 4 },
      }),
    ]);

    render(<ConflictsPage />);

    await waitFor(() => expect(screen.getByText(/DOC-AAA/)).toBeInTheDocument());
    expect(screen.queryByText(/ vs /)).not.toBeInTheDocument();
  });

  it("says so plainly when a conflict records no sources at all", async () => {
    respond([item(4, { parameter: "DOCUMENTED_BY", source_a: {}, source_b: {} })]);

    render(<ConflictsPage />);

    await waitFor(() => expect(screen.getByText("Sources not recorded")).toBeInTheDocument());
  });
});
