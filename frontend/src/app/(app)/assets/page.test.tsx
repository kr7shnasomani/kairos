import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AssetSummary } from "@/lib/types";
import AssetsPage from "./page";
import AssetsError from "./error";

const mocks = vi.hoisted(() => ({ getAssets: vi.fn(), push: vi.fn() }));

// getToken is pulled in transitively (useRole -> getMe -> getToken). A whole-module mock that
// omits it leaves it undefined, and the effect throws as an unhandled rejection — the tests still
// pass, which is exactly what makes it dangerous: a real failure in the same effect would be
// invisible for the same reason.
vi.mock("@/lib/api", () => ({ getAssets: mocks.getAssets, getToken: vi.fn(() => null) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));

function asset(i: number, over: Partial<AssetSummary> = {}): AssetSummary {
  return {
    asset_id: `A-${i}`, name: `Asset ${i}`, equipment_class: "Rotating equipment",
    criticality: "critical", site_id: "SITE-A",
    // GET /assets/ returns these on every row now (0 when the asset has none), so the
    // fixture carries them too — a factory that omits them stops matching the API.
    open_work_orders_count: 0, compliance_gap_count: 0,
    ...over,
  };
}

function respond(items: AssetSummary[]) {
  mocks.getAssets.mockResolvedValue({ data: { items, total: items.length, limit: 100, offset: 0 }, source: "live" });
}

describe("AssetsPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("paginates a 10k registry to at most 25 rendered rows with class pills", async () => {
    respond(Array.from({ length: 10_000 }, (_, i) => asset(i)));

    render(await AssetsPage());

    expect(document.querySelectorAll("tbody tr").length).toBeLessThanOrEqual(25);
    expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument();
    expect(screen.getByTestId("assets-summary")).toHaveTextContent("Rotating equipment");
  });

  it("shows open work orders and compliance gaps per asset, muting zeroes", async () => {
    respond([asset(1, { asset_id: "P-101", open_work_orders_count: 3, compliance_gap_count: 2 }), asset(2, { asset_id: "V-247" })]);

    render(await AssetsPage());

    expect(screen.getByRole("columnheader", { name: /Open WOs/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Compliance gaps/ })).toBeInTheDocument();
    const row = screen.getByText("P-101").closest("tr")!;
    expect(row).toHaveTextContent("3");
    expect([...row.querySelectorAll("td")].at(-1)).toHaveClass("text-right");
    expect(row.querySelector(".text-danger")).toHaveTextContent("2");
    expect(screen.getByText("V-247").closest("tr")!.querySelector(".text-danger")).toBeNull();
  });

  it("filters the registry and routes row clicks to the asset detail", async () => {
    respond([
      asset(1, { asset_id: "P-101", name: "Feed pump", criticality: "safety_critical" }),
      asset(2, { asset_id: "V-247", name: "Isolation valve", equipment_class: "Valve" }),
    ]);

    render(await AssetsPage());

    fireEvent.change(screen.getByRole("searchbox", { name: "Search assets" }), { target: { value: "valve" } });
    await waitFor(() => expect(screen.queryByText("Feed pump")).not.toBeInTheDocument());
    expect(screen.getByText("Isolation valve")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 assets")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Isolation valve").closest("tr")!);
    expect(mocks.push).toHaveBeenCalledWith("/assets/V-247");
  });

  it("humanises equipment class rather than printing the raw key", async () => {
    respond([asset(1, { equipment_class: "he-3xx_series" })]);

    render(await AssetsPage());

    expect(screen.queryByText(/he-3xx_series/)).not.toBeInTheDocument();
    expect(screen.getAllByText("HE-3xx series").length).toBeGreaterThan(0);
  });

  it("renders the asset id as a link colour, not the brand accent", async () => {
    respond([asset(1, { asset_id: "HE-301" })]);

    render(await AssetsPage());

    expect(screen.getByText("HE-301")).toHaveClass("text-link");
    expect(screen.getByText("HE-301")).not.toHaveClass("text-accent");
  });

  it("separates the registered total from the per-class breakdown", async () => {
    respond([asset(1), asset(2, { equipment_class: "Valve" })]);

    render(await AssetsPage());

    expect(screen.getByTestId("kpi-total")).toHaveTextContent("Registered assets");
    expect(screen.getByTestId("kpi-total")).toHaveTextContent("2");
    expect(screen.getByTestId("kpi-total")).not.toHaveTextContent("By equipment class");
  });

  it("does not render a single-value Site column", async () => {
    respond([asset(1)]);

    render(await AssetsPage());

    expect(screen.queryByRole("columnheader", { name: /^site$/i })).not.toBeInTheDocument();
  });

  it("shows the tailored empty state and a route error surface with retry", async () => {
    respond([]);
    render(await AssetsPage());
    expect(screen.getByText("No assets registered yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Register assets" })).toHaveAttribute("href", "/assets/register");
    // Register and identity confirmation are separate pages; register must not land on the review queues.
    expect(await screen.findByRole("link", { name: "Register asset" })).toHaveAttribute("href", "/assets/register");
    cleanup();

    const reset = vi.fn();
    render(<AssetsError error={new Error("boom")} reset={reset} />);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(reset).toHaveBeenCalled();
  });
});
