import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExtractFormAction } from "./extract-form-action";
import { extractFormFields } from "@/lib/api";
import { useRole } from "@/components/use-role";

vi.mock("@/lib/api", () => ({ extractFormFields: vi.fn() }));
vi.mock("@/components/use-role", async (orig) => ({ ...(await orig<typeof import("@/components/use-role")>()), useRole: vi.fn() }));

describe("ExtractFormAction", () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("sends the fields on click and points the reviewer at the queue", async () => {
    vi.mocked(useRole).mockReturnValue("engineer");
    vi.mocked(extractFormFields).mockResolvedValue({ status: "quarantined", fields: 13 });
    render(<ExtractFormAction documentId="DOC-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Extract form fields" }));
    expect(await screen.findByRole("status")).toHaveTextContent("13 fields sent to the review queue.");
    expect(extractFormFields).toHaveBeenCalledWith("DOC-1");
    expect(screen.getByRole("link", { name: "Open the queue" })).toHaveAttribute("href", "/governance/quarantine");
  });

  it("says so when the fields are already in the queue (HTTP 409), without an error screen", async () => {
    vi.mocked(useRole).mockReturnValue("reliability");
    vi.mocked(extractFormFields).mockRejectedValue(new Error("POST /documents/DOC-1/extract-form: HTTP 409"));
    render(<ExtractFormAction documentId="DOC-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Extract form fields" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/already in the review queue/);
  });

  it("is not offered to a role that cannot call the route", () => {
    vi.mocked(useRole).mockReturnValue("field_worker");
    const { container } = render(<ExtractFormAction documentId="DOC-1" />);
    expect(container).toBeEmptyDOMElement();
  });
});
