import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmitPanel } from "./emit-panel";

const mocks = vi.hoisted(() => ({
  postWorkOrder: vi.fn(),
  postPtw: vi.fn(),
  postShiftHandover: vi.fn(),
  postTagOut: vi.fn(),
  postInspectionComplete: vi.fn(),
  postAlarm: vi.fn(),
}));

vi.mock("@/lib/api", () => mocks);

const accepted = { status: "accepted", event_id: "ev-1" };

function renderPanel() {
  const onEmitted = vi.fn();
  render(<EmitPanel siteId="SITE-A" userId="user-42" onEmitted={onEmitted} />);
  return onEmitted;
}

describe("EmitPanel", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((m) => m.mockResolvedValue(accepted));
  });
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // Regression: work orders could not be started from the UI at all.
  it("emits a work order assigned to the signed-in user, so its brief reaches a real inbox", async () => {
    const onEmitted = renderPanel();

    fireEvent.change(screen.getByLabelText("Asset"), { target: { value: "eq-102" } });
    fireEvent.change(screen.getByLabelText("Failure code"), { target: { value: "elec-insul-fail" } });
    fireEvent.click(screen.getByRole("button", { name: "Emit" }));

    await waitFor(() => expect(mocks.postWorkOrder).toHaveBeenCalledTimes(1));
    const body = mocks.postWorkOrder.mock.calls[0][0];
    expect(body).toMatchObject({ site_id: "SITE-A", asset_id: "EQ-102", failure_code: "ELEC-INSUL-FAIL", assigned_technician_id: "user-42" });
    expect(body.work_order_id).toMatch(/^WO-MANUAL-/);
    expect(onEmitted).toHaveBeenCalled();
  });

  // Regression: the handover went to the literal id "shift-B", which is no one.
  it("addresses a shift handover to the signed-in user, not a placeholder id", async () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "shift-handover" } });
    fireEvent.click(screen.getByRole("button", { name: "Emit" }));

    await waitFor(() => expect(mocks.postShiftHandover).toHaveBeenCalledTimes(1));
    expect(mocks.postShiftHandover.mock.calls[0][0]).toMatchObject({ incoming_shift_lead_id: "user-42", site_id: "SITE-A" });
    expect(mocks.postShiftHandover.mock.calls[0][0].incoming_shift_lead_id).not.toBe("shift-B");
  });

  it("emits a permit to work over every boundary asset, issued by the signed-in user", async () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "ptw" } });
    fireEvent.change(screen.getByLabelText("Boundary assets"), { target: { value: "v-247, xv-203" } });
    fireEvent.change(screen.getByLabelText("Work area"), { target: { value: "Line 3 isolation" } });
    fireEvent.click(screen.getByRole("button", { name: "Emit" }));

    await waitFor(() => expect(mocks.postPtw).toHaveBeenCalledTimes(1));
    expect(mocks.postPtw.mock.calls[0][0]).toMatchObject({
      asset_ids: ["V-247", "XV-203"], work_area: "Line 3 isolation", ptw_type: "isolation", issuing_engineer_id: "user-42",
    });
    expect(await screen.findByText(/wait for a reliability countersignature/)).toBeInTheDocument();
  });
});
