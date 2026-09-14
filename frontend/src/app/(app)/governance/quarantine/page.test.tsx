import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { QuarantineItem } from "@/lib/types";
import QuarantinePage from "./page";

const mocks = vi.hoisted(() => ({
  getQuarantine: vi.fn(),
  promoteQuarantine: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getQuarantine: mocks.getQuarantine,
  promoteQuarantine: mocks.promoteQuarantine,
  disputeQuarantine: vi.fn(),
  requestQuarantineInfo: vi.fn(),
}));
vi.mock("@/components/use-role", () => ({
  useRole: () => "engineer",
  PROMOTE_ROLES: ["engineer"],
}));

function item(i: number, over: Partial<QuarantineItem> = {}): QuarantineItem {
  return {
    item_id: `q-${i}`,
    asset_id: null,
    content: `Observation ${i}`,
    input_type: "field_observation",
    submitted_by: "op-1",
    submitted_at: "2026-07-01T00:00:00Z",
    reviewer_id: null,
    review_status: "pending",
    work_order_id: null,
    session_context: null,
    sla_due_at: null,
    is_overdue: false,
    ...over,
  };
}

function respond(items: QuarantineItem[], total = items.length) {
  mocks.getQuarantine.mockResolvedValue({
    data: { items, total, limit: 100, offset: 0, note: "" },
    source: "live",
  });
}

describe("QuarantinePage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("paginates a 10k queue to at most 25 rendered rows", async () => {
    respond(Array.from({ length: 10_000 }, (_, i) => item(i)));

    render(<QuarantinePage />);

    await waitFor(() => expect(screen.getByText("Observation 0")).toBeInTheDocument());
    expect(document.querySelectorAll("tbody tr").length).toBeLessThanOrEqual(25);
    expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument();
  });

  it("shows the cleared empty state and zeroed pills when the queue is empty", async () => {
    respond([]);

    render(<QuarantinePage />);

    await waitFor(() => expect(screen.getByText("Quarantine is clear ✓")).toBeInTheDocument());
    expect(screen.getByTestId("quarantine-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("quarantine-summary")).toHaveTextContent("Pending0");
  });

  it("opens the item panel on row click and closes it on Escape", async () => {
    respond([item(0)]);

    render(<QuarantinePage />);

    await waitFor(() => expect(screen.getByText("Observation 0")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Observation 0"));
    expect(screen.getByTestId("quarantine-panel")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("quarantine-panel")).not.toBeInTheDocument();
  });

  // `document_type` is `field_observation`: typed as `procedure`, a promoted field input satisfied
  // compliance clauses that require a documented procedure.
  it("promotes through the panel as a field observation and refetches", async () => {
    respond([item(0)]);
    mocks.promoteQuarantine.mockResolvedValue({});

    render(<QuarantinePage />);

    await waitFor(() => expect(screen.getByText("Observation 0")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Observation 0"));
    fireEvent.click(screen.getByRole("button", { name: "Promote" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm promote" }));

    await waitFor(() =>
      expect(mocks.promoteQuarantine).toHaveBeenCalledWith("q-0", {
        authority_level: 4,
        relationship_type: "DOCUMENTED_BY",
        document_type: "field_observation",
        notes: undefined,
      }),
    );
    await waitFor(() =>
      expect(screen.getByText("Promoted q-0 to the canonical graph.")).toBeInTheDocument(),
    );
    expect(mocks.getQuarantine).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId("quarantine-panel")).not.toBeInTheDocument();
  });
});
