import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PushVolumeGatePage from "./page";

const mocks = vi.hoisted(() => ({ getPushVolumeGate: vi.fn() }));

vi.mock("@/lib/api", () => ({ getPushVolumeGate: mocks.getPushVolumeGate }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

window.matchMedia = ((query: string) => ({
  matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
})) as unknown as typeof window.matchMedia;

const gate = (over: Record<string, unknown> = {}) => ({
  source: "live",
  data: {
    window_days: 30, ceiling_per_operator_per_hour: 6, peak_per_operator_per_hour: 8, breach_count: 1,
    breaches: [{ recipient_user_id: "operator-7", hour: "2026-07-14T10", count: 8 }],
    briefs_delivered: 140, within_eemua_norms: false, current_phase: 3, enforcement: "advisory_only", ...over,
  },
});

describe("PushVolumeGatePage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("reports a breach with the operator-hour that caused it", async () => {
    mocks.getPushVolumeGate.mockResolvedValue(gate());
    render(<PushVolumeGatePage />);

    expect(await screen.findByText("Ceiling breached")).toBeInTheDocument();
    expect(screen.getByText("operator-7")).toBeInTheDocument();
    expect(screen.getByText("2026-07-14 10:00")).toBeInTheDocument();
    expect(mocks.getPushVolumeGate).toHaveBeenCalledWith(30);
  });

  it("refetches when the window changes", async () => {
    mocks.getPushVolumeGate.mockResolvedValue(gate({ within_eemua_norms: true, breach_count: 0, breaches: [], peak_per_operator_per_hour: 3 }));
    render(<PushVolumeGatePage />);

    expect(await screen.findByText("Within EEMUA 191 norms")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "7" } });
    await waitFor(() => expect(mocks.getPushVolumeGate).toHaveBeenCalledWith(7));
  });
});
