import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import BootstrapPage from "./page";

const mocks = vi.hoisted(() => ({
  confirmAssetIdentity: vi.fn(),
  getProvisionalAssets: vi.fn(),
  getAliasCandidates: vi.fn(),
  confirmAlias: vi.fn(),
  rejectAlias: vi.fn(),
  getMe: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  confirmAssetIdentity: mocks.confirmAssetIdentity,
  getProvisionalAssets: mocks.getProvisionalAssets,
  getAliasCandidates: mocks.getAliasCandidates,
  confirmAlias: mocks.confirmAlias,
  rejectAlias: mocks.rejectAlias,
}));
vi.mock("@/lib/auth", () => ({ getMe: mocks.getMe }));

const provisional = {
  asset_id: "P-207",
  tag_number: "P-207",
  name: "Provisional pump (EAM import)",
  equipment_class: "centrifugal_pump",
  criticality: "critical",
  site_id: "SITE-A",
  facility_id: "FAC-1",
  eam_source: "eam_sync",
};
const alias = { alias: "FSL-2240A", canonical_asset_id: "EQ-101", confidence: 0.9, alias_source: "ner_extraction:DOC-1" };

function live<T>(data: T) {
  return Promise.resolve({ data, source: "live" as const });
}

describe("BootstrapPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("presents identity work as two responsive review queues from live data", async () => {
    mocks.getMe.mockResolvedValue({ user_id: "u-1", role: "admin", site_id: "SITE-A" });
    mocks.getProvisionalAssets.mockImplementation(() => live([provisional]));
    mocks.getAliasCandidates.mockImplementation(() => live([alias]));

    render(<BootstrapPage />);

    expect(await screen.findByRole("heading", { name: "Asset identity confirmation" })).toBeInTheDocument();
    expect(screen.getByTestId("identity-workspace")).toHaveClass("max-w-5xl");
    expect(screen.getByTestId("identity-guardrail")).toHaveClass("rounded-xl", "bg-surface");
    expect(screen.getByTestId("provisional-queue")).toHaveClass("rounded-xl", "bg-surface");
    expect(screen.getByTestId("alias-queue")).toHaveClass("rounded-xl", "bg-surface");
    expect(await screen.findByTestId("provisional-P-207")).toHaveClass("grid", "md:grid-cols-[minmax(0,1fr)_minmax(150px,0.55fr)_auto]");
    expect(screen.getByText("FSL-2240A")).toBeInTheDocument();
  });

  it("confirms an identity with the record's own fields and refetches", async () => {
    mocks.getMe.mockResolvedValue({ user_id: "u-1", role: "admin", site_id: "SITE-A" });
    mocks.getProvisionalAssets.mockImplementationOnce(() => live([provisional])).mockImplementation(() => live([]));
    mocks.getAliasCandidates.mockImplementation(() => live([]));
    mocks.confirmAssetIdentity.mockResolvedValue({});

    render(<BootstrapPage />);

    await screen.findByText("Provisional pump (EAM import)");
    fireEvent.click(screen.getByRole("button", { name: "Confirm identity" }));

    await waitFor(() => expect(mocks.confirmAssetIdentity).toHaveBeenCalledWith({
      asset_id: "P-207",
      tag_number: "P-207",
      name: "Provisional pump (EAM import)",
      equipment_class: "centrifugal_pump",
      criticality: "critical",
      site_id: "SITE-A",
      facility_id: "FAC-1",
      confirmed_by_user_id: "u-1",
    }));
    await waitFor(() => expect(screen.queryByTestId("provisional-P-207")).not.toBeInTheDocument());
  });

  it("sends Reject to the reject endpoint, not the confirm one", async () => {
    mocks.getMe.mockResolvedValue({ user_id: "u-1", role: "admin", site_id: "SITE-A" });
    mocks.getProvisionalAssets.mockImplementation(() => live([]));
    mocks.getAliasCandidates.mockImplementation(() => live([alias]));
    mocks.rejectAlias.mockResolvedValue({ status: "rejected" });

    render(<BootstrapPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Reject alias FSL-2240A" }));

    await waitFor(() => expect(mocks.rejectAlias).toHaveBeenCalledWith("EQ-101", "FSL-2240A"));
    expect(mocks.confirmAlias).not.toHaveBeenCalled();
  });

  // The API allows engineers to confirm identities and aliases; the page used to be admin-only.
  it("lets an engineer confirm, as the API does", async () => {
    mocks.getMe.mockResolvedValue({ user_id: "eng-7", role: "engineer", site_id: "SITE-A" });
    mocks.getProvisionalAssets.mockImplementation(() => live([provisional]));
    mocks.getAliasCandidates.mockImplementation(() => live([]));
    mocks.confirmAssetIdentity.mockResolvedValue({});

    render(<BootstrapPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Confirm identity" }));
    await waitFor(() => expect(mocks.confirmAssetIdentity).toHaveBeenCalledWith(expect.objectContaining({ confirmed_by_user_id: "eng-7" })));
  });

  it("tells a role the API would refuse that it cannot confirm, instead of offering the queues", async () => {
    mocks.getMe.mockResolvedValue({ user_id: "rel-1", role: "reliability", site_id: "SITE-A" });
    mocks.getProvisionalAssets.mockImplementation(() => live([provisional]));
    mocks.getAliasCandidates.mockImplementation(() => live([alias]));

    render(<BootstrapPage />);

    expect(await screen.findByText(/requires the/)).toHaveTextContent("requires the engineer or admin role");
    expect(screen.queryByRole("button", { name: "Confirm identity" })).not.toBeInTheDocument();
  });
});
