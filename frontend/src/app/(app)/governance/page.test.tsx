import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GovernancePage from "./page";

vi.mock("@/lib/api", () => ({
  getConflicts: vi.fn().mockResolvedValue({
    data: { items: [
      { conflict_id: "C-1", status: "open", track: "engineering", is_overdue: true },
      { conflict_id: "C-2", status: "pending_moc", track: "engineering", is_overdue: false },
      { conflict_id: "C-3", status: "resolved", track: "administrative", is_overdue: false },
    ] },
    source: "live",
  }),
  getQuarantine: vi.fn().mockResolvedValue({
    data: { items: [
      { item_id: "Q-1", review_status: "pending", is_overdue: true },
      { item_id: "Q-2", review_status: "pending", is_overdue: false },
      { item_id: "Q-3", review_status: "promoted", is_overdue: false },
    ] },
    source: "live",
  }),
}));

describe("GovernancePage", () => {
  afterEach(cleanup);

  it("uses a responsive operational overview with data-driven queue status", async () => {
    render(<GovernancePage />);

    expect(screen.getByTestId("governance-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("governance-summary")).toHaveClass("mesh", "lg:grid-cols-4");
    expect(screen.getByTestId("governance-surfaces")).toHaveClass("md:grid-cols-2", "xl:grid-cols-3");

    await waitFor(() => expect(screen.getByTestId("governance-surface-conflicts")).toHaveTextContent("2 open"));
    expect(screen.getByTestId("governance-surface-quarantine")).toHaveTextContent("2 pending");
    expect(screen.getByTestId("governance-surface-sla")).toHaveTextContent("2 overdue");

    expect(screen.getByTestId("governance-surface-moc")).toHaveAttribute("href", "/governance/moc");
    expect(screen.getByTestId("governance-surface-model-gate")).toHaveAttribute("href", "/governance/model-gate");
  });

  it("names each card's destination without nesting another interactive control", async () => {
    render(<GovernancePage />);

    await waitFor(() => expect(screen.getByTestId("governance-surface-conflicts")).toHaveTextContent("2 open"));

    const surfaces = [
      "conflicts",
      "quarantine",
      "moc",
      "sla",
      "circuit-breaker",
      "model-gate",
    ].map((key) => screen.getByTestId(`governance-surface-${key}`));
    const ctas = surfaces.map((surface) => surface.lastElementChild?.textContent?.trim());

    expect(ctas).toEqual([
      "Review 2 open conflicts ›",
      "Review 2 pending inputs ›",
      "Review 1 pending changes ›",
      "Inspect 2 overdue decisions ›",
      "Inspect anomaly gates ›",
      "Review model validation ›",
    ]);
    expect(new Set(ctas).size).toBe(surfaces.length);
    for (const surface of surfaces) {
      expect(surface).toHaveProperty("tagName", "A");
      expect(surface).not.toHaveAttribute("tabindex", "-1");
      expect(surface.querySelectorAll("a, button")).toHaveLength(0);
    }
  });
});
