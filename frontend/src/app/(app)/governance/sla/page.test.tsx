import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SlaReport } from "@/lib/types";
import { buildRows } from "./_components/columns";
import SlaPage from "./page";

const mocks = vi.hoisted(() => ({ getSlaReport: vi.fn(), push: vi.fn() }));

vi.mock("@/lib/api", () => ({ getSlaReport: mocks.getSlaReport }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));

const HOUR = 3_600_000;

function makeReport(over: Partial<SlaReport> = {}): SlaReport {
  const now = Date.now();
  return {
    checked_at: new Date(now).toISOString(),
    escalated_this_run: { conflicts: 1, quarantine_items: 0 },
    overdue_conflicts: [
      { conflict_id: "c1", track: "engineering", asset_id: "P-101", sla_deadline: new Date(now - 30 * HOUR).toISOString(), escalated_at: new Date(now - 2 * HOUR).toISOString(), status: "open" },
      { conflict_id: "c2", track: "administrative", asset_id: null, sla_deadline: new Date(now - 5 * HOUR).toISOString(), escalated_at: null, status: "open" },
    ],
    overdue_conflicts_total: 2,
    overdue_quarantine_items: [
      { item_id: "q1", asset_id: "V-247", input_type: "voice_note", sla_due_at: new Date(now - 8 * 24 * HOUR).toISOString(), escalated_at: null },
    ],
    overdue_quarantine_total: 1,
    ...over,
  };
}

describe("SlaPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("first paint is skeletons — no fabricated fixture items before data lands", () => {
    mocks.getSlaReport.mockReturnValue(new Promise(() => undefined)); // never resolves
    const { container } = render(<SlaPage />);

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(screen.queryByText(/CONF-00/)).toBeNull();
    expect(container.querySelector("table")).toBeNull();
  });

  it("renders KPIs, charts, and the merged table from live data", async () => {
    mocks.getSlaReport.mockResolvedValue({ data: makeReport(), source: "live" });
    render(<SlaPage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "SLA Escalations" })).toBeInTheDocument());
    expect(screen.getByTestId("sla-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("sla-summary")).toHaveClass("grid-cols-2", "lg:grid-cols-4");
    expect(screen.getByTestId("sla-charts")).toHaveClass("lg:grid-cols-2");

    // KPI deep links.
    expect(screen.getByRole("link", { name: /overdue conflicts/i })).toHaveAttribute("href", "/governance/conflicts");
    expect(screen.getByRole("link", { name: /overdue quarantine/i })).toHaveAttribute("href", "/governance/quarantine");

    // Merged table, worst-first: q1 (8d) above c1 (1.25d) above c2 (0.2d).
    const cells = screen.getAllByRole("cell").map((c) => c.textContent);
    expect(cells.indexOf("q1")).toBeLessThan(cells.indexOf("c1"));
    expect(screen.getByRole("link", { name: "q1" })).toHaveAttribute("href", "/governance/quarantine");

    // Row click deep-links.
    fireEvent.click(screen.getByText("c1").closest("tr") as HTMLElement);
    expect(mocks.push).toHaveBeenCalledWith("/governance/conflicts");

    // Filter tabs narrow the table.
    fireEvent.click(screen.getByRole("button", { name: /Quarantine\s?1/ }));
    expect(screen.queryByText("c1")).toBeNull();
    expect(screen.getByText("q1")).toBeInTheDocument();
  });

  it("paginates 10k rows at 25 per page", async () => {
    const now = Date.now();
    const items = Array.from({ length: 10_000 }, (_, i) => ({
      item_id: `q${i}`,
      asset_id: null,
      input_type: "voice_note",
      sla_due_at: new Date(now - (i + 1) * HOUR).toISOString(),
      escalated_at: null,
    }));
    mocks.getSlaReport.mockResolvedValue({
      data: makeReport({ overdue_conflicts: [], overdue_conflicts_total: 0, overdue_quarantine_items: items, overdue_quarantine_total: items.length }),
      source: "live",
    });
    render(<SlaPage />);

    await waitFor(() => expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument());
    expect(screen.getAllByRole("row")).toHaveLength(26); // header + 25
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(/Showing 26–50 of 10000/)).toBeInTheDocument();
  });

  it("buckets days-overdue without NaN", () => {
    const now = Date.now();
    const rows = buildRows(makeReport({ overdue_conflicts: [{ conflict_id: "bad", track: "engineering", asset_id: null, sla_deadline: "not-a-date", escalated_at: null, status: "open" }], overdue_conflicts_total: 1 }), now);
    expect(rows.every((r) => Number.isFinite(r.days_overdue))).toBe(true);
    const q1 = rows.find((r) => r.id === "q1");
    expect(q1?.days_overdue).toBeCloseTo(8, 1);
  });

  it("surfaces error + retry on charts and table when the load fails", async () => {
    mocks.getSlaReport.mockRejectedValue(new Error("backend unreachable"));
    render(<SlaPage />);

    await waitFor(() => expect(screen.getByText(/Couldn't load the SLA report — backend unreachable/)).toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: "Retry" }).length).toBeGreaterThanOrEqual(2);
  });

  it("zero overdue → verified KPIs, empty charts, on-time table state", async () => {
    mocks.getSlaReport.mockResolvedValue({
      data: makeReport({ overdue_conflicts: [], overdue_conflicts_total: 0, overdue_quarantine_items: [], overdue_quarantine_total: 0, escalated_this_run: { conflicts: 0, quarantine_items: 0 } }),
      source: "live",
    });
    render(<SlaPage />);

    await waitFor(() => expect(screen.getByText("All SLAs on time ✓")).toBeInTheDocument());
    expect(screen.getAllByText("No overdue items.").length).toBe(3);
  });
});
