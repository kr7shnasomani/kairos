import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RegisterAssetPage from "./page";

const mocks = vi.hoisted(() => ({
  confirmAssetIdentity: vi.fn(),
  bulkImportAssets: vi.fn(),
  getMe: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  confirmAssetIdentity: mocks.confirmAssetIdentity,
  bulkImportAssets: mocks.bulkImportAssets,
  getToken: vi.fn(() => null),
}));
vi.mock("@/lib/auth", () => ({ getMe: mocks.getMe }));

describe("RegisterAssetPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // Regression: "Register asset" landed on the identity-confirmation queues, with no way to register.
  it("registers a new asset with the signed-in user's site and identity", async () => {
    mocks.getMe.mockResolvedValue({ user_id: "u-1", role: "engineer", site_id: "SITE-A" });
    mocks.confirmAssetIdentity.mockResolvedValue({ asset_id: "P-205", tag_number: "P-205", status: "created" });

    render(<RegisterAssetPage />);

    fireEvent.change(await screen.findByLabelText("Tag number"), { target: { value: "p-205" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Centrifugal Feed Pump" } });
    fireEvent.change(screen.getByLabelText("Equipment class"), { target: { value: "Rotating – Centrifugal Pump" } });
    fireEvent.change(screen.getByLabelText("Criticality"), { target: { value: "safety_critical" } });
    fireEvent.change(screen.getByLabelText("Facility"), { target: { value: "rpc" } });
    fireEvent.submit(screen.getByRole("button", { name: "Register asset" }).closest("form")!);

    await waitFor(() => expect(mocks.confirmAssetIdentity).toHaveBeenCalledWith({
      asset_id: "P-205",
      tag_number: "P-205",
      name: "Centrifugal Feed Pump",
      equipment_class: "Rotating – Centrifugal Pump",
      criticality: "safety_critical",
      site_id: "SITE-A",
      facility_id: "RPC",
      confirmed_by_user_id: "u-1",
    }));
    expect(await screen.findByText(/P-205 registered with a confirmed identity\./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open P-205" })).toHaveAttribute("href", "/assets/P-205");
  });

  it("imports the valid rows of an EAM CSV and reports the row it could not read", async () => {
    mocks.getMe.mockResolvedValue({ user_id: "u-1", role: "admin", site_id: "SITE-A" });
    mocks.bulkImportAssets.mockResolvedValue({
      submitted: 2, created: 2, created_asset_ids: ["P-301", "HX-9"],
      already_present: [], duplicate_in_payload: [], site_forbidden: [], failed: [],
    });

    render(<RegisterAssetPage />);

    const csv = [
      "tag_number,name,equipment_class,criticality,facility_id",
      'P-301,"Booster Pump, Line 4",Rotating – Centrifugal Pump,Critical,RPC',
      "HX-9,Plate Heat Exchanger,HE-3xx series,non-critical,RPC",
      "V-9,Gate Valve,Valve – Gate,somewhat,RPC",
    ].join("\n");
    const file = new File([csv], "eam_export.csv", { type: "text/csv" });
    fireEvent.change(await screen.findByLabelText("EAM export (CSV)"), { target: { files: [file] } });

    expect(await screen.findByText(/row\(s\) need fixing/)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Import 2 assets" }));

    await waitFor(() => expect(mocks.bulkImportAssets).toHaveBeenCalledTimes(1));
    const rows = mocks.bulkImportAssets.mock.calls[0][0];
    expect(rows.map((r: { tag_number: string }) => r.tag_number)).toEqual(["P-301", "HX-9"]);
    expect(rows[0]).toMatchObject({ name: "Booster Pump, Line 4", criticality: "critical", site_id: "SITE-A", facility_id: "RPC" });
    expect(rows[1].criticality).toBe("non_critical");
    expect(await screen.findByText("2 created")).toBeInTheDocument();
  });

  it("tells a role the API would refuse that it cannot register, instead of offering a form", async () => {
    mocks.getMe.mockResolvedValue({ user_id: "u-2", role: "reliability", site_id: "SITE-A" });

    render(<RegisterAssetPage />);

    expect(await screen.findByText(/requires the/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Tag number")).not.toBeInTheDocument();
  });
});
