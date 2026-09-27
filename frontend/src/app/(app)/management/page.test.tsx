import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getConflicts, getHealthDetailed } from "@/lib/api";
import ManagementPage from "./page";

vi.mock("@/lib/api", () => ({
  getConflicts: vi.fn().mockResolvedValue({ data: { total: 3, items: [] }, source: "live" }),
  getComplianceDashboard: vi.fn().mockResolvedValue({
    data: { total_gaps: { critical: 2, major: 1, minor: 0 }, by_framework: {}, by_asset_class: {} },
    source: "live",
  }),
  getSlaReport: vi.fn().mockResolvedValue({
    data: {
      checked_at: "2026-07-15T08:00:00Z",
      escalated_this_run: { conflicts: 0, quarantine_items: 0 },
      overdue_conflicts: [{ conflict_id: "c1", track: "technical", asset_id: "P-101", sla_deadline: "2026-07-14T08:00:00Z", escalated_at: null, status: "open" }],
      overdue_conflicts_total: 1,
      overdue_quarantine_items: [{ item_id: "q1", asset_id: null, input_type: "field_note", sla_due_at: "2026-07-13T08:00:00Z", escalated_at: null }],
      overdue_quarantine_total: 1,
    },
    source: "live",
  }),
  getQuarantine: vi.fn().mockResolvedValue({ data: { items: [], total: 5 }, source: "live" }),
  getEvents: vi.fn().mockResolvedValue({
    data: {
      items: [{ event_id: "e1", event_type: "work_order_created", occurred_at: "2026-07-15T07:00:00Z", priority: "high", payload: {}, acknowledged: false }],
      total: 1,
    },
    source: "live",
  }),
  getHealthDetailed: vi.fn().mockResolvedValue({
    data: {
      overall: "degraded",
      checked_at: "2026-07-15T08:00:00Z",
      services: [{ name: "Neo4j", status: "healthy", latency_ms: 12 }, { name: "Qdrant", status: "degraded" }],
    },
    source: "live",
  }),
}));

describe("ManagementPage", () => {
  afterEach(cleanup);

  it("keeps the overview decision flow responsive and data-driven", async () => {
    render(<ManagementPage />);

    expect(screen.getByTestId("overview-workspace")).toHaveClass("max-w-[1400px]");
    await waitFor(() => expect(screen.getByTestId("overview-health")).toHaveTextContent("Qdrant"));
    expect(screen.getByTestId("overview-kpis")).toHaveClass("grid-cols-2", "lg:grid-cols-4");
    expect(screen.getByTestId("overview-priority-layout")).toHaveClass("lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]");
    expect(screen.getByTestId("overview-health")).toHaveTextContent("Degraded");
    expect(screen.getByRole("link", { name: /plant state.*degraded/i })).toHaveAttribute("href", "/management/plant-state");

    // KPI deep links (spec §4).
    expect(screen.getByRole("link", { name: /open conflicts/i })).toHaveAttribute("href", "/governance/conflicts");
    expect(screen.getByRole("link", { name: /overdue sla items/i })).toHaveAttribute("href", "/governance/sla");
    expect(screen.getByRole("link", { name: /critical gaps/i })).toHaveAttribute("href", "/compliance");

    // Attention ranking (spec §5): overdue conflict first, then quarantine, then gaps.
    const attention = screen.getByTestId("overview-needs-attention");
    expect(attention).toHaveTextContent("Overdue conflict, Technical");
    expect(attention).toHaveTextContent("Overdue quarantine, Field note");
    expect(attention).toHaveTextContent("2 critical compliance gaps");

    // Signals feed rows deep-link to the event.
    const signals = screen.getByTestId("overview-recent-signals");
    expect(signals.querySelector('a[href="/events/e1"]')).not.toBeNull();
    expect(signals.querySelector('a[href="/events/e1"] span[title="Work Order Created"]')).toHaveClass("whitespace-normal", "break-words");
  });

  it("surfaces a retry-able error card when the load fails outright", async () => {
    vi.mocked(getConflicts).mockRejectedValueOnce(new Error("backend unreachable"));
    render(<ManagementPage />);

    await waitFor(() => expect(screen.getByTestId("overview-error")).toHaveTextContent("backend unreachable"));
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("distinguishes unavailable plant health from a healthy state", async () => {
    vi.mocked(getHealthDetailed).mockRejectedValueOnce(new Error("health unavailable"));
    render(<ManagementPage />);

    await waitFor(() => expect(screen.getByRole("link", { name: /plant state.*unavailable/i })).toBeInTheDocument());
  });
});
