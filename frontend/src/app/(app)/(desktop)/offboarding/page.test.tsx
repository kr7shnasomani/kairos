import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getOffboardingList } from "@/lib/api";
import OffboardingPage from "./page";

vi.mock("@/lib/api", () => ({
  getOffboardingList: vi.fn().mockResolvedValue({
    data: [
      { id: "P-1", personnel_id: "U-1", personnel_email: "priya.sharma@plant.in", retirement_date: "2026-09-30", total_sessions: 5, sessions_completed: 3, status: "active", created_at: "2026-01-01" },
      { id: "P-2", personnel_id: "U-2", personnel_email: "ramesh@plant.in", retirement_date: "2026-11-15", total_sessions: 3, sessions_completed: 1, status: "active", created_at: "2026-01-01" },
      { id: "P-3", personnel_id: "U-3", personnel_email: "neha.patel@plant.in", retirement_date: "2026-08-01", total_sessions: 2, sessions_completed: 2, status: "completed", created_at: "2026-01-01" },
    ],
    source: "api",
  }),
}));

describe("OffboardingPage", () => {
  afterEach(cleanup);

  it("renders a data-driven expert handover overview", async () => {
    render(await OffboardingPage());

    expect(screen.getByTestId("offboarding-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("offboarding-summary")).toHaveTextContent(/2\s*active programmes/);
    expect(screen.getByTestId("offboarding-summary")).toHaveTextContent(/1\s*complete/);
    expect(screen.getByTestId("offboarding-summary")).toHaveTextContent(/6\s*of 10 sessions/);
    expect(screen.getByTestId("offboarding-programmes")).toHaveClass("md:grid-cols-2");

    const priya = screen.getByTestId("offboarding-programme-P-1");
    expect(priya).toHaveTextContent("priya.sharma@plant.in");
    expect(priya).toHaveTextContent("60%");
    expect(priya).toHaveAttribute("href", "/offboarding/P-1");
  });

  it("keeps identifiers honest and makes retirement timing explicit", async () => {
    vi.mocked(getOffboardingList).mockResolvedValueOnce({
      data: [
        { id: "P-email", personnel_id: "EXPERT-1", personnel_email: "resp_F001AE52@kairos.local", retirement_date: "2026-09-21", total_sessions: 6, sessions_completed: 0, status: "active", created_at: "2026-01-01" },
        { id: "P-id", personnel_id: "EXPERT-2", personnel_email: "", retirement_date: "invalid", total_sessions: 1, sessions_completed: 0, status: "active", created_at: "2026-01-01" },
        { id: "P-past", personnel_id: "EXPERT-3", personnel_email: "departed@kairos.local", retirement_date: "2020-01-01", total_sessions: 1, sessions_completed: 1, status: "completed", created_at: "2026-01-01" },
      ],
      source: "live",
    });

    render(await OffboardingPage());

    expect(screen.getByTestId("offboarding-programme-P-email")).toHaveTextContent("resp_F001AE52@kairos.local");
    expect(screen.getByTestId("offboarding-programme-P-email")).toHaveTextContent(/Retires 21 Sept 2026/);
    expect(screen.getByTestId("offboarding-programme-P-email")).toHaveTextContent(/Retires in \d+ days/);
    expect(screen.getByTestId("offboarding-programme-P-id")).toHaveTextContent("EXPERT-2");
    expect(screen.getByTestId("offboarding-programme-P-id")).toHaveTextContent("Retirement date unavailable");
    expect(screen.getByTestId("offboarding-programme-P-past")).toHaveTextContent(/Retired \d+ days ago/);
  });
});
