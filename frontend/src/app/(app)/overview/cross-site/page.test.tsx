import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import CrossSiteAlertsPage from "./page";

describe("CrossSiteAlertsPage", () => {
  afterEach(cleanup);

  it("shows an honest unavailable state (no fabricated cross-site alerts)", () => {
    render(<CrossSiteAlertsPage />);

    expect(screen.getByTestId("cross-site-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("cross-site-unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cross-site matching is not available yet" })).toBeInTheDocument();
    expect(screen.getByText(/does not correlate sites yet/i)).toBeInTheDocument();
  });
});
