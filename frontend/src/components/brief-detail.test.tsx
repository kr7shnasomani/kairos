import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Brief } from "@/lib/types";
import { BriefDetail } from "./brief-detail";

// getToken is pulled in transitively via useMe -> getMe; without it the whole-module mock
// leaves it undefined and the effect throws.
vi.mock("@/lib/api", () => ({
  ackBrief: vi.fn(),
  countersignBrief: vi.fn(),
  sendBriefFeedback: vi.fn(),
  getToken: vi.fn(() => null),
}));

// The signature box is only offered to the brief's recipient, so render as that user.
vi.mock("./use-role", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./use-role")>()),
  useMe: () => ({ user_id: "user-1", email: "engineer@kairos.local", role: "engineer", site_id: "SITE_001" }),
}));

const brief: Brief = {
  brief_id: "BRF-101",
  recipient_user_id: "user-1",
  priority: "high",
  trigger_event_type: "shift_handover",
  headline: "Verify P-101 seal condition before restart",
  body: "The latest inspection identified a seal condition that must be reviewed before restart.",
  action_items: ["Inspect seal housing", "Record vibration reading"],
  warnings: ["Do not restart above the governed envelope."],
  sources: [{ document_id: "DOC-1", document_type: "inspection_report", title: "P-101 inspection", authority_level: 2, relevant_excerpt: "Seal wear requires engineering review.", vault_url: null, is_quarantine: false }],
  requires_countersignature: false,
  delivery_frozen: false,
  delivered_at: "2026-07-15T08:00:00Z",
};

describe("BriefDetail", () => {
  afterEach(cleanup);

  it("uses a responsive reading and decision workspace", () => {
    render(<BriefDetail brief={brief} />);

    expect(screen.getByTestId("brief-detail-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("brief-detail-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_340px]");
    expect(screen.getByTestId("brief-content")).toHaveTextContent("What to do");
    expect(screen.getByTestId("brief-context")).toHaveTextContent("Evidence");
    expect(screen.getByTestId("brief-acknowledgment")).toHaveClass("lg:sticky");
    expect(screen.getByLabelText("Engineer signature")).toHaveClass("min-h-11");
  });

  // Regression guard for the dead-end this workstream fixed: a PTW brief that had been
  // acknowledged used to be unreachable — no countersign path existed, so it could never
  // be delivered. It must now render an explicit "awaiting second authority" state.
  it("shows a PTW brief as awaiting a second authority once acknowledged", () => {
    render(
      <BriefDetail
        brief={{
          ...brief,
          requires_countersignature: true,
          acknowledged_by: "eng-1",
          acknowledged_by_name: "Engineer One",
          acknowledged_at: null,
          countersigned_by: null,
        }}
      />,
    );

    const panel = screen.getByTestId("brief-countersign");
    expect(panel).toHaveTextContent("Step 2 of 2");
    // The signer is shown by name — the stored id is an opaque auth UUID.
    expect(panel).toHaveTextContent("Engineer One");
    // Unauthenticated in this test (getToken -> null), so no countersign button is offered.
    expect(panel).toHaveTextContent(/reliability engineer or administrator/i);
  });

  it("shows a fully signed PTW brief as complete", () => {
    render(
      <BriefDetail
        brief={{
          ...brief,
          requires_countersignature: true,
          acknowledged_by: "eng-1",
          acknowledged_at: "2026-07-15T09:00:00Z",
          countersigned_by: "rel-1",
          countersigned_at: "2026-07-15T09:00:00Z",
        }}
      />,
    );

    expect(screen.getByTestId("brief-acknowledgment")).toHaveTextContent("PTW signed off");
    expect(screen.queryByTestId("brief-countersign")).toBeNull();
  });
});
