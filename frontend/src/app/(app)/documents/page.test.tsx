import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { VaultDocument } from "@/lib/types";
import DocumentsPage from "./page";

const mocks = vi.hoisted(() => ({ getDocuments: vi.fn(), push: vi.fn() }));

vi.mock("@/lib/api", () => ({ getDocuments: mocks.getDocuments, getToken: () => null }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));

function doc(i: number, over: Partial<VaultDocument> = {}): VaultDocument {
  return {
    document_id: `DOC-${i}`, file_name: `file-${i}.pdf`, document_type: "oem_manual",
    authority_level: 2, source_system: "manual_upload", vault_url: null, status: "active",
    ingested_at: "2026-07-12T10:00:00Z", ingested_by: "admin", asset_links: [], ...over,
  };
}

function respond(items: VaultDocument[]) {
  mocks.getDocuments.mockImplementation(async (opts: { status?: string } = {}) => {
    const scoped = opts.status === "active" ? items.filter((d) => d.status === "active") : items;
    return { data: { items: scoped, total: scoped.length, limit: 100, offset: 0 }, source: "live" };
  });
}

const open = (page?: string) => DocumentsPage({ searchParams: Promise.resolve({ page }) });

describe("DocumentsPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("paginates a 10k vault to at most 25 rendered rows", async () => {
    respond(Array.from({ length: 10_000 }, (_, i) => doc(i)));

    render(await open());

    expect(document.querySelectorAll("tbody tr").length).toBeLessThanOrEqual(25);
    expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument();
  });

  it("shows vault pills, filters by state, and routes row clicks to the document", async () => {
    respond([
      doc(1, { asset_links: ["P-101", "P-102"] }),
      doc(2, { status: "superseded", file_name: "old.pdf" }),
    ]);

    render(await open());

    expect(screen.getByTestId("documents-summary")).toHaveTextContent("Active");
    expect(screen.getByText("2 linked assets")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ingest document" })).toHaveAttribute("href", "/documents/ingest");

    fireEvent.click(screen.getByRole("button", { name: /Superseded/ }));
    await waitFor(() => expect(screen.queryByText("file-1.pdf")).not.toBeInTheDocument());
    expect(screen.getByText("old.pdf")).toBeInTheDocument();

    fireEvent.click(screen.getByText("old.pdf").closest("tr")!);
    expect(mocks.push).toHaveBeenCalledWith("/documents/DOC-2");
  });

  it("shows the tailored empty state with an ingest CTA", async () => {
    respond([]);

    render(await open());

    expect(screen.getByText("No documents ingested")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ingest a document" })).toHaveAttribute("href", "/documents/ingest");
  });

  it("renders document ids quietly, not in the brand accent", async () => {
    respond([doc(1)]);

    render(await open());

    expect(screen.getByText("DOC-1")).not.toHaveClass("text-accent");
    expect(screen.getByText("DOC-1")).toHaveClass("text-muted", "tabular");
  });

  // This previously asserted an <a href={vault_url}>, which LOCKED IN a bug: that
  // URL is Supabase's /object/authenticated/ endpoint and a browser navigation to
  // it returns 400, because the required Authorization header cannot be sent. The
  // download must go through getArtifactUrl() for a signed URL instead.
  it("gives each row a download action that does not link straight to the vault URL", async () => {
    respond([doc(1, { vault_url: "https://vault.example/doc-1" })]);

    render(await open());

    expect(screen.getByRole("button", { name: /download/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /download/i })).not.toBeInTheDocument();
    expect(document.querySelector('[href="https://vault.example/doc-1"]')).toBeNull();
  });

  it("omits the download action when there is no artifact", async () => {
    respond([doc(1, { vault_url: null })]);

    render(await open());

    expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
  });

  it("shows the exact ingest timestamp", async () => {
    respond([doc(1)]);

    render(await open());

    expect(screen.getByText("2026-07-12 10:00:00")).toBeInTheDocument();
  });

  it("does not render the raw ingested_by UUID", async () => {
    respond([doc(1, { ingested_by: "123e4567-e89b-12d3-a456-426614174000" })]);

    render(await open());

    expect(screen.queryByText(/^[0-9a-f]{8}-/)).not.toBeInTheDocument();
  });

  it("pages the vault and counts the whole vault in the pills, not the page in view", async () => {
    mocks.getDocuments.mockImplementation(async (opts: { status?: string; offset?: number } = {}) => ({
      data: { items: [doc(1)], total: opts.status === "active" ? 230 : 250, limit: 100, offset: opts.offset ?? 0 }, source: "live",
    }));

    render(await open("2"));

    expect(mocks.getDocuments).toHaveBeenCalledWith({ limit: 100, offset: 100 });
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("href", "/documents?page=3");
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/documents?page=1");
    expect(screen.getByTestId("documents-summary")).toHaveTextContent(/250[\s\S]*230[\s\S]*20/);
  });
});
