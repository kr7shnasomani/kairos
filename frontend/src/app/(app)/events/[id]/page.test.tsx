import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EventDetailPage from "./page";

const mocks = vi.hoisted(() => ({ getEvent: vi.fn(), ackEvent: vi.fn(), getMe: vi.fn() }));

vi.mock("@/lib/api", () => ({ getEvent: mocks.getEvent, ackEvent: mocks.ackEvent }));
vi.mock("@/lib/auth", () => ({ getMe: mocks.getMe }));

const event = {
  event_id: "EVT-ALM-2049",
  event_type: "alarm",
  event_subtype: "pressure_high_high",
  asset_id: "P-101",
  site_id: "SITE_001",
  occurred_at: "2026-07-14T10:00:00Z",
  priority: "critical" as const,
  payload: { alarm_tag: "PAHH-101", value: 14.8, unit: "bar" },
  brief_id: "BRF-01",
  correlated_event_ids: ["EVT-WO-88213"],
  acknowledged: false,
};

describe("EventDetailPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("uses a responsive event-detail hierarchy with readable payload fields", async () => {
    mocks.getEvent.mockResolvedValue({ data: event, source: "demo" });
    mocks.getMe.mockResolvedValue({ user_id: "operator-7", role: "engineer" });

    await act(async () => render(<EventDetailPage params={Promise.resolve({ id: event.event_id })} />));

    expect(await screen.findByRole("heading", { name: "Alarm" })).toBeInTheDocument();
    expect(screen.getByTestId("event-detail-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("event-summary")).toHaveClass("rounded-xl", "bg-surface");
    expect(screen.getByTestId("event-detail-columns")).toHaveClass("fluid-tile-pair");
    expect(screen.getByTestId("event-detail-columns")).not.toHaveClass("lg:items-start");
    expect(screen.getByText("Alarm tag")).toBeInTheDocument();
    expect(screen.getByText("PAHH-101")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /EVT-WO-88213/ })).toHaveAttribute("href", "/events/EVT-WO-88213");
  });

  it("acknowledges with the signed-in user and updates the status", async () => {
    mocks.getEvent.mockResolvedValue({ data: event, source: "live" });
    mocks.getMe.mockResolvedValue({ user_id: "operator-7", role: "engineer" });
    mocks.ackEvent.mockResolvedValue({ status: "acknowledged" });

    await act(async () => render(<EventDetailPage params={Promise.resolve({ id: event.event_id })} />));
    fireEvent.click(await screen.findByRole("button", { name: "Acknowledge event" }));

    await waitFor(() => expect(mocks.ackEvent).toHaveBeenCalledWith(event.event_id, {
      user_id: "operator-7",
      role: "engineer",
    }));
    expect(await screen.findByText(/Acknowledged by/)).toHaveTextContent("operator-7");
  });

  it("lets the demo account acknowledge, on the showcase plant", async () => {
    mocks.getEvent.mockResolvedValue({ data: event, source: "live" });
    mocks.getMe.mockResolvedValue({ user_id: "demo-1", role: "demo" });
    mocks.ackEvent.mockResolvedValue({ acknowledged_by: "demo-1" });

    await act(async () => render(<EventDetailPage params={Promise.resolve({ id: event.event_id })} />));

    await waitFor(() => expect(screen.getByRole("button", { name: "Acknowledge event" })).toBeEnabled());
  });

  it("shows an error with retry when the fetch fails, instead of loading forever", async () => {
    mocks.getEvent.mockRejectedValueOnce(new Error("HTTP 500")).mockResolvedValueOnce({ data: event, source: "live" });
    mocks.getMe.mockResolvedValue({ user_id: "operator-7", role: "engineer" });

    await act(async () => render(<EventDetailPage params={Promise.resolve({ id: event.event_id })} />));

    expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Alarm" })).toBeInTheDocument();
  });
});
