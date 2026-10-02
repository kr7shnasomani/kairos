import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ingestDocument, supersedeDocument } from "@/lib/api";
import { SupersedeAction } from "./supersede-action";

vi.mock("@/lib/api", () => ({ ingestDocument: vi.fn(), supersedeDocument: vi.fn() }));
vi.mock("@/components/use-role", () => ({
  useIsDemo: () => false,
  visibleTo: (roles: string[], role: string) => role === "demo" || roles.includes(role),
  useRole: () => "engineer",
  RESOLVE_ROLES: ["engineer", "reliability", "admin"],
  AUTHORITY_ASSERT_ROLES: ["reliability", "admin"],
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

function submitReplacement() {
  fireEvent.click(screen.getByRole("button", { name: "Supersede document" }));
  const file = new File(["revised procedure"], "sop_rev2.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Replacement file"), { target: { files: [file] } });
  // Submit the form directly: jsdom's constraint validation reads the `required` file input's empty
  // `value` (a stubbed FileList does not set it) and would block a click on the submit button.
  fireEvent.submit(screen.getByRole("button", { name: "Confirm supersede" }).closest("form")!);
}

describe("SupersedeAction", () => {
  beforeEach(() => vi.mocked(supersedeDocument).mockResolvedValue({ status: "superseded", old_document_id: "DOC-OLD", new_document_id: "DOC-NEW", moc_required: false, moc_id: null }));
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // Regression: the file used to be posted straight to /supersede, which only accepts the id of a
  // document already in the vault — every supersede from the UI failed.
  it("ingests the replacement, then supersedes with its new document id", async () => {
    vi.mocked(ingestDocument).mockResolvedValue({ status: "accepted", document_id: "DOC-NEW", sha256: "x", message: "" });
    render(<SupersedeAction documentId="DOC-OLD" assetId="HE-301" />);

    submitReplacement();

    await waitFor(() => expect(supersedeDocument).toHaveBeenCalledWith("DOC-OLD", "DOC-NEW"));
    const fd = vi.mocked(ingestDocument).mock.calls[0][0];
    expect(fd.get("asset_id")).toBe("HE-301");
    expect(await screen.findByText("DOC-NEW")).toBeInTheDocument();
  });

  it("refuses an identical file instead of superseding a document with itself", async () => {
    vi.mocked(ingestDocument).mockResolvedValue({ status: "duplicate", document_id: "DOC-OLD", sha256: "x", message: "" });
    render(<SupersedeAction documentId="DOC-OLD" />);

    submitReplacement();

    expect(await screen.findByText(/identical to this document/)).toBeInTheDocument();
    expect(supersedeDocument).not.toHaveBeenCalled();
  });

  it("shows an awaiting-approval state with the MoC id, not success, when the supersede is held", async () => {
    vi.mocked(ingestDocument).mockResolvedValue({ status: "accepted", document_id: "DOC-NEW", sha256: "x", message: "" });
    vi.mocked(supersedeDocument).mockResolvedValue({
      status: "pending_moc_approval", old_document_id: "DOC-OLD", new_document_id: "DOC-NEW", moc_required: true, moc_id: "MOC-AB12CD34",
    });
    render(<SupersedeAction documentId="DOC-OLD" />);

    submitReplacement();

    expect(await screen.findByText(/Awaiting MoC approval/)).toBeInTheDocument();
    expect(screen.getByText("MOC-AB12CD34")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "the MoC page" })).toHaveAttribute("href", "/governance/moc/MOC-AB12CD34");
    expect(screen.queryByText(/superseded\.$/)).not.toBeInTheDocument();
  });

  it("offers authority levels 4 and 5 only to a role that cannot assert 1 to 3", () => {
    render(<SupersedeAction documentId="DOC-OLD" />);
    fireEvent.click(screen.getByRole("button", { name: "Supersede document" }));
    expect(screen.getAllByRole("option", { name: /^L\d$/ }).map((o) => o.textContent)).toEqual(["L4", "L5"]);
  });
});
