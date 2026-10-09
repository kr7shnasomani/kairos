import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CrossSiteAlertsPage from "./page";
import { getCrossSitePatterns } from "@/lib/api";

vi.mock("@/lib/api", () => ({ getCrossSitePatterns: vi.fn() }));

const base = { sites: ["SITE_A", "SITE_B"], window_days: 180, min_events: 2, truncated: false };
const live = (data: object) => vi.mocked(getCrossSitePatterns).mockResolvedValue({ data: { ...base, ...data }, source: "live" } as never);

describe("CrossSiteAlertsPage", () => {
  afterEach(cleanup);

  it("renders each pattern with every site's share, and marks a site that has not seen it", async () => {
    live({
      patterns: [
        {
          equipment_class: "rotating_centrifugal_pump", failure_family: "seal", kind: "advisory", total_events: 3,
          sites: [
            { site_id: "SITE_A", events: 3, assets_affected: 2, assets_in_class: 5, last_seen: "2026-10-01T00:00:00+00:00" },
            { site_id: "SITE_B", events: 0, assets_affected: 0, assets_in_class: 4, last_seen: null },
          ],
        },
      ],
    });
    render(<CrossSiteAlertsPage />);
    const card = await screen.findByTestId("cross-site-pattern");
    expect(within(card).getByRole("heading")).toHaveTextContent("Seal on Rotating centrifugal pump");
    expect(card).toHaveTextContent("Advisory");
    const rows = within(card).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("SITE_A");
    expect(rows[0]).toHaveTextContent("2 of 5");
    expect(rows[1]).toHaveTextContent("Not seen here");
  });

  it("says there is nothing to compare when the account covers one site (no fabricated alerts)", async () => {
    live({ patterns: [], sites: ["SITE_A"] });
    render(<CrossSiteAlertsPage />);
    expect(await screen.findByTestId("cross-site-empty")).toHaveTextContent(/covers one site/i);
    expect(screen.queryByTestId("cross-site-pattern")).not.toBeInTheDocument();
  });
});
