import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { BriefsResponse } from "@/lib/types";
import { BriefInbox } from "./brief-inbox";

const response: BriefsResponse = {
  briefs: [],
  total_pending: 4,
  suppressed_count: 0,
  governor_state: { push_count_last_hour: 2, ceiling: 8, state: "normal" },
  next_delivery_allowed_at: null,
};

describe("BriefInbox", () => {
  afterEach(cleanup);

  it("uses one compact toolbar with relevant status signals", () => {
    render(<BriefInbox response={response} />);

    expect(screen.getByTestId("brief-toolbar")).toHaveClass("md:flex-row");
    expect(screen.getByText("4 pending")).toBeInTheDocument();
    expect(screen.getByText("2/8 governor")).toBeInTheDocument();
  });

  it("reserves warning colors for status that needs action", () => {
    render(<BriefInbox response={{
      ...response,
      total_pending: 0,
      suppressed_count: 2,
      governor_state: { ...response.governor_state, state: "suppressed" },
    }} />);

    expect(screen.getByText("0 pending").parentElement).toHaveClass("text-verified");
    expect(screen.getByText("2/8 governor").parentElement).toHaveClass("text-danger");
  });
});

describe("held briefs", () => {
  afterEach(cleanup);

  const held = {
    brief_id: "b-held",
    asset_id: "EQ-101",
    recipient_user_id: "u1",
    priority: "high" as const,
    trigger_event_type: "vibration_alarm",
    headline: "Bearing vibration above 2-sigma baseline",
    body: "",
    action_items: [],
    warnings: [],
    sources: [],
    requires_countersignature: false,
    delivery_frozen: false,
    delivered_at: "2026-08-22T10:00:00Z",
  };

  it("shows which briefs are held, not just how many", () => {
    render(<BriefInbox response={{
      ...response,
      suppressed_count: 1,
      suppressed_held: [held],
      governor_state: { ...response.governor_state, state: "suppressed" },
    }} />);

    // the operator can judge relevance: asset and headline, not a bare counter
    expect(screen.getByText(/EQ-101/)).toBeInTheDocument();
    expect(screen.getByText(/Bearing vibration above 2-sigma baseline/)).toBeInTheDocument();
  });

  it("renders nothing extra when the governor is holding nothing", () => {
    render(<BriefInbox response={{
      ...response,
      suppressed_count: 2,
      governor_state: { ...response.governor_state, state: "suppressed" },
    }} />);

    // count still shown, but no held list when the backend sent none
    expect(screen.queryByText(/EQ-101/)).not.toBeInTheDocument();
  });
});

describe("governor card", () => {
  afterEach(cleanup);
  const queued = {
    brief_id: "b-q", asset_id: null, recipient_user_id: "u1", priority: "normal" as const, trigger_event_type: "shift_handover",
    headline: "Shift handover: 1 open work orders, 2 alarms", body: "", action_items: [], warnings: [], sources: [],
    requires_countersignature: false, delivery_frozen: false, delivered_at: "2026-08-22T10:00:00Z",
  };

  it("is a calm summary below the ceiling and keeps the queue closed until asked for", () => {
    render(<BriefInbox response={{ ...response, suppressed_count: 10, suppressed_held: [queued] }} />);
    expect(screen.getByText("10 routine briefs queued")).toBeInTheDocument();
    expect(screen.getByLabelText("Brief delivery governor")).not.toHaveClass("bg-danger");
    expect(screen.queryByText(/governor suppressed/)).not.toBeInTheDocument();
    const details = screen.getByText("Show the queued briefs").closest("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveTextContent("Shift handover: 1 open work orders, 2 alarms");
  });

  it("shows a brief with no asset by its headline alone", () => {
    render(<BriefInbox response={{ ...response, suppressed_count: 1, suppressed_held: [queued] }} />);
    expect(screen.getByText("Show the queued briefs").closest("details")!.textContent).not.toMatch(/DEMO-GENERAL|null/);
  });
});
