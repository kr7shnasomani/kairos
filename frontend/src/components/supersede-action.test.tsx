import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ingestDocument, supersedeDocument } from "@/lib/api";
import { SupersedeAction } from "./supersede-action";

vi.mock("@/lib/api", () => ({ ingestDocument: vi.fn(), supersedeDocument: vi.fn() }));
vi.mock("@/components/use-role", () => ({
  useRole: () => "engineer",
  RESOLVE_ROLES: ["engineer", "reliability", "admin"],
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
  beforeEach(() => vi.mocked(supersedeDocument).mockResolvedValue({}));
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
});
