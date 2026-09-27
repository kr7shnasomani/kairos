import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProjectsPage from "./page";

vi.mock("@/lib/api", () => ({
  getAssets: vi.fn().mockResolvedValue({ data: { items: [
    { asset_id: "P-101", name: "Process pump", equipment_class: "centrifugal_pump", criticality: "critical" },
    { asset_id: "P-102", name: "Standby pump", equipment_class: "centrifugal_pump", criticality: "critical" },
    { asset_id: "V-247", name: "Isolation valve", equipment_class: "control_valve", criticality: "non_critical" },
  ] }, source: "api" }),
  getDocuments: vi.fn().mockResolvedValue({ data: { items: [
    { document_id: "DOC-PUMP-R2", file_name: "seal_series_MS44_service_bulletin_r3.pdf", document_type: "oem_manual", authority_level: 3, source_system: "OEM_portal", status: "active", ingested_at: "2026-07-14T10:00:00Z", ingested_by: "engineer", asset_links: ["P-101"] },
    { document_id: "DOC-PUMP-R1", file_name: "pump-r1.pdf", document_type: "oem_manual", authority_level: 3, source_system: "OEM", status: "superseded", ingested_at: "2025-07-14T10:00:00Z", ingested_by: "engineer", asset_links: ["P-101"], version_chain: "DOC-PUMP-R2" },
    { document_id: "DOC-VALVE", file_name: "valve.pdf", document_type: "procedure", authority_level: 4, source_system: "manual_upload", status: "active", ingested_at: "2026-07-13T10:00:00Z", ingested_by: "engineer", asset_links: ["V-247"] },
  ] }, source: "api" }),
  getEvents: vi.fn().mockResolvedValue({ data: { items: [
    { event_id: "EV-1", event_type: "recurring_failure_detected", asset_id: "P-101", occurred_at: "2026-07-15T08:00:00Z", priority: "high", payload: { failure_code: "SEAL-FAIL" }, acknowledged: false },
    { event_id: "EV-2", event_type: "alarm_acknowledged", asset_id: "V-247", occurred_at: "2026-07-14T08:00:00Z", priority: "normal", payload: {}, acknowledged: true },
  ] }, source: "api" }),
}));

describe("ProjectsPage", () => {
  afterEach(cleanup);

  it("renders and filters a data-driven procurement portfolio", async () => {
    render(<ProjectsPage />);

    await waitFor(() => expect(screen.getByTestId("projects-portfolio-pulse")).toHaveTextContent("2 equipment classes"));
    expect(screen.getByTestId("projects-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("projects-portfolio-pulse")).toHaveTextContent(/3\s*assets/);
    expect(screen.getByTestId("projects-portfolio-pulse")).toHaveTextContent(/3\s*documents/);
    expect(screen.getByTestId("projects-portfolio-pulse")).toHaveTextContent(/2\s*maintenance signals/);
    expect(screen.getByTestId("projects-class-navigation")).toBeInTheDocument();
    expect(screen.getByTestId("projects-portfolio")).toHaveClass("lg:grid-cols-[220px_minmax(0,1fr)]");

    const pump = screen.getByTestId("project-class-centrifugal-pump");
    expect(pump).toHaveTextContent("P-101");
    expect(pump).toHaveTextContent("1 revision");
    expect(screen.getByRole("link", { name: "DOC-PUMP-R2" })).toHaveAttribute("href", "/documents/DOC-PUMP-R2");

    fireEvent.click(screen.getByRole("button", { name: /Control Valve/ }));
    await waitFor(() => expect(screen.queryByTestId("project-class-centrifugal-pump")).not.toBeInTheDocument());
    expect(screen.getByTestId("project-class-control-valve")).toBeInTheDocument();
  });

  it("renders evidence ids as links, not in the brand accent", async () => {
    render(<ProjectsPage />);

    const evidenceId = await screen.findAllByTestId("evidence-id");
    expect(evidenceId[0]).toHaveClass("text-link");
    expect(evidenceId[0]).not.toHaveClass("text-accent");
  });

  it("pluralises correctly", async () => {
    render(<ProjectsPage />);

    await screen.findByTestId("projects-portfolio-pulse");
    expect(screen.queryByText(/^1 signals$/)).not.toBeInTheDocument();
  });

  it("shows the whole filename", async () => {
    render(<ProjectsPage />);

    expect(await screen.findByTitle("seal_series_MS44_service_bulletin_r3.pdf, OEM_portal")).toBeInTheDocument();
  });
});
