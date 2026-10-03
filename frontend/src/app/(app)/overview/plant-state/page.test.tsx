import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PlantStatePage from "./page";

vi.mock("@/lib/auth", () => ({ getMe: vi.fn().mockResolvedValue({ user_id: "U-1", email: "admin@kairos.test", role: "admin", site_id: "SITE-A" }) }));
vi.mock("@/lib/api", () => ({
  getPlantState: vi.fn().mockResolvedValue({ data: { site_id: "SITE-A", state: "normal", set_by: "admin@kairos.test", set_at: "2026-07-15T08:00:00Z" }, source: "live" }),
  setPlantState: vi.fn(),
}));

describe("PlantStatePage", () => {
  afterEach(cleanup);

  it("uses a responsive operating-state control workspace", async () => {
    render(<PlantStatePage />);
    await waitFor(() => expect(screen.getAllByText("Full operations. All ingestion, briefs, and governors active.").length).toBeGreaterThan(0));

    expect(screen.getByTestId("plant-state-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("plant-state-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_300px]");
    expect(screen.getByTestId("plant-state-control")).toHaveTextContent("Transition to");
    expect(screen.getByTestId("plant-state-context")).toHaveTextContent("SITE-A");
    expect(screen.getByRole("button", { name: /Turnaround/ })).toHaveClass("min-h-[96px]");
  });
});
