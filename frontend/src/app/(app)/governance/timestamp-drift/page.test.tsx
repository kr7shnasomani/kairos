import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TimestampDriftPage from "./page";

const mocks = vi.hoisted(() => ({ getTimestampDrift: vi.fn() }));

vi.mock("@/lib/api", () => ({ getTimestampDrift: mocks.getTimestampDrift }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

window.matchMedia = ((query: string) => ({
  matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
})) as unknown as typeof window.matchMedia;

describe("TimestampDriftPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("lists drifting compound events with their source systems", async () => {
    mocks.getTimestampDrift.mockResolvedValue({
      source: "live",
      data: {
        compound_events_checked: 12, drift_detected_count: 1, tolerance_minutes: 5, enforcement: "advisory_only",
        items: [{ compound_event_id: "CE-9", drift_minutes: 17.5, reason: "cross_system_drift", sources: ["SCADA", "SAP PM"], canonical_timestamp: "2026-07-14T10:00:00Z", canonical_source: "SCADA", action: "reported_only" }],
      },
    });
    render(<TimestampDriftPage />);

    expect(await screen.findByText("CE-9")).toBeInTheDocument();
    expect(screen.getByText("SCADA · SAP PM")).toBeInTheDocument();
    expect(screen.getByText("17.5 min")).toBeInTheDocument();
    expect(screen.getByText("Advisory")).toBeInTheDocument();
  });

  it("says plainly when nothing drifted", async () => {
    mocks.getTimestampDrift.mockResolvedValue({
      source: "live",
      data: { compound_events_checked: 8, drift_detected_count: 0, tolerance_minutes: 5, enforcement: "advisory_only", items: [] },
    });
    render(<TimestampDriftPage />);

    expect(await screen.findByText("No drift beyond 5 minutes across 8 compound events.")).toBeInTheDocument();
  });
});
