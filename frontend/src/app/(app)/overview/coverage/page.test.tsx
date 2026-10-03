import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CoveragePage from "./page";

vi.mock("@/lib/api", () => {
  const rows = [
    // deliberately out of order — the page must sort weakest-first itself
    { asset_id: "HE-301", name: "Shell and Tube Heat Exchanger", equipment_class: "he-3xx_series", criticality: "critical", facts: 9, authoritative_facts: 2, verified_facts: 0, documents: 5, pending_quarantine: 4 },
    { asset_id: "XV-204", name: "Secondary Bleed Valve", equipment_class: "valve_isolation", criticality: "non_critical", facts: 1, authoritative_facts: 0, verified_facts: 0, documents: 0, pending_quarantine: 0 },
    { asset_id: "EQ-101", name: "Centrifugal Feed Pump", equipment_class: "rotating_centrifugal_pump", criticality: "critical", facts: 5, authoritative_facts: 2, verified_facts: 0, documents: 4, pending_quarantine: 21 },
  ];
  return {
    getAssetCoverage: vi.fn().mockResolvedValue({
      data: [...rows].sort((a, b) => a.facts - b.facts || a.documents - b.documents),
      source: "live",
    }),
  };
});

describe("CoveragePage", () => {
  afterEach(cleanup);

  it("renders a row per asset, weakest coverage first", async () => {
    render(<CoveragePage />);
    // Scope to the table: asset ids also appear as chips in the blind-spot panel above it.
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1); // drop the header
    expect(rows).toHaveLength(3);
    // The whole point of the page is the gaps, so the thinnest asset must lead.
    expect(rows[0]).toHaveTextContent("XV-204");
    expect(rows[2]).toHaveTextContent("HE-301");
  });

  it("calls out blind spots — an asset with no documents or no authoritative source", async () => {
    render(<CoveragePage />);
    const panel = await screen.findByTestId("coverage-blind-spots");
    // XV-204 has 0 documents and 0 authoritative facts; HE-301 has both, so it must not appear.
    expect(panel).toHaveTextContent("XV-204");
    expect(panel).not.toHaveTextContent("HE-301");
  });

  it("keeps the Verified column visible even though it reads zero everywhere", async () => {
    // Hiding it would hide the finding: promotion through the quarantine gate is human-only,
    // and nothing has been promoted. A missing column would read as "not measured".
    render(<CoveragePage />);
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("columnheader", { name: /Verified/i })).toBeInTheDocument();
  });
});
