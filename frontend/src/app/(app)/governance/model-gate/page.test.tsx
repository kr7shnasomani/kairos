import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ModelGateResult } from "@/lib/types";
import ModelGatePage from "./page";

const mocks = vi.hoisted(() => ({
  getModelGateHistory: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getModelGateHistory: mocks.getModelGateHistory,
  runModelGate: vi.fn(),
}));

// The "Run gate now" button is admin-gated; render as admin so it appears.
vi.mock("@/components/use-role", () => ({
  useIsDemo: () => false,
  visibleTo: (roles: string[], role: string) => role === "demo" || roles.includes(role),
  useRole: () => "admin",
  ADMIN_ROLES: ["admin"],
  ADMIN_VIEW_ROLES: ["admin", "demo"],
}));

function run(i: number, passed = true): ModelGateResult {
  return {
    run_id: `mg-${i}`,
    task_id: null,
    precision: 0.9,
    recall: 0.85,
    f1: 0.875,
    passed,
    corpus_size: 100 + i,
    run_at: new Date(Date.UTC(2026, 0, 1) + i * 3600000).toISOString(),
  };
}

describe("ModelGatePage", () => {
  beforeAll(() => {
    // jsdom has no matchMedia; useReducedMotion needs it
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders KPI strip, both charts, and the run table from live history", async () => {
    mocks.getModelGateHistory.mockResolvedValue({ data: { history: [run(1), run(2, false), run(3)] }, source: "live" });

    render(<ModelGatePage />);

    await waitFor(() => expect(screen.getByText("Quality trend")).toBeInTheDocument());
    expect(screen.getByTestId("model-gate-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("model-gate-summary")).toHaveClass("sm:grid-cols-2", "xl:grid-cols-4");
    expect(screen.getByTestId("model-gate-layout")).toHaveClass("lg:grid-cols-[2fr_3fr]");
    expect(screen.getByText("Pass mix")).toBeInTheDocument();
    // KPI strip: latest-run percentages via fmtPct — never NaN
    expect(screen.getAllByText("90%").length).toBeGreaterThan(0);
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    // Table renders one row per run with pass/fail badges
    expect(screen.getAllByText("passed")).toHaveLength(2);
    expect(screen.getAllByText("failed")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Run gate now" })).toHaveClass("min-h-11");
    expect(screen.queryByText("Demo data")).not.toBeInTheDocument();
  });

  it("shows the empty state when live history has no runs", async () => {
    mocks.getModelGateHistory.mockResolvedValue({ data: { history: [] }, source: "live" });

    render(<ModelGatePage />);

    await waitFor(() => expect(screen.getAllByText("No gate runs yet.").length).toBeGreaterThanOrEqual(3));
    expect(screen.queryByText("Demo data")).not.toBeInTheDocument();
  });

  it("shows a retry-able error when history is unavailable (live-only — no fixture fallback)", async () => {
    // Unavailability is a rejection now. It used to be modelled as `source: "demo"`, which the
    // hook translated into an error — that indirection is gone along with the fixture fallback.
    mocks.getModelGateHistory.mockRejectedValue(new Error("backend unavailable"));

    render(<ModelGatePage />);

    await waitFor(() => expect(screen.getByTestId("model-gate-error")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText("Demo data")).not.toBeInTheDocument();
  });

  it("does not crash on a single-run history", async () => {
    mocks.getModelGateHistory.mockResolvedValue({ data: { history: [run(1)] }, source: "live" });

    render(<ModelGatePage />);

    await waitFor(() => expect(screen.getByText("passed")).toBeInTheDocument());
    expect(screen.getByText("1 of 1 runs")).toBeInTheDocument();
  });

  it("guards partial data — null precision renders an em dash, never NaN", async () => {
    const partial = { ...run(1), precision: null as unknown as number };
    mocks.getModelGateHistory.mockResolvedValue({ data: { history: [partial] }, source: "live" });

    render(<ModelGatePage />);

    await waitFor(() => expect(screen.getByText("passed")).toBeInTheDocument());
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it("paginates 10k simulated rows at 25 per page", async () => {
    const history = Array.from({ length: 10_000 }, (_, i) => run(i));
    mocks.getModelGateHistory.mockResolvedValue({ data: { history }, source: "live" });

    render(<ModelGatePage />);

    await waitFor(() => expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  }, 20_000); // 10k rows rendered into jsdom: slow when the whole suite runs in parallel
});
