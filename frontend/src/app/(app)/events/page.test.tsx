import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EventsPage from "./page";

const mocks = vi.hoisted(() => ({ getEvents: vi.fn(), getMe: vi.fn(), postTagOut: vi.fn(), postWorkOrder: vi.fn(), push: vi.fn() }));

vi.mock("@/lib/api", () => ({
  getEvents: mocks.getEvents,
  postTagOut: mocks.postTagOut,
  postWorkOrder: mocks.postWorkOrder,
  postPtw: vi.fn(),
  postInspectionComplete: vi.fn(),
  postAlarm: vi.fn(),
  postShiftHandover: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ getMe: mocks.getMe }));
vi.mock("@/components/use-role", () => ({
  useRole: () => "engineer",
  RESOLVE_ROLES: ["engineer"],
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));

// jsdom has no matchMedia; useReducedMotion needs it.
window.matchMedia = ((query: string) => ({
  matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
})) as unknown as typeof window.matchMedia;

const events = [
  { event_id: "EV-1", event_type: "alarm", event_subtype: null, asset_id: "P-101", site_id: "SITE-A", occurred_at: "2026-07-14T10:00:00Z", priority: "high", payload: { alarm_description: "High pressure on pump" }, correlated_event_ids: [], acknowledged: false },
  { event_id: "EV-2", event_type: "inspection_complete", event_subtype: "recurring", asset_id: "HX-2", site_id: "SITE-A", occurred_at: "2026-07-14T09:00:00Z", priority: "normal", payload: {}, correlated_event_ids: ["EV-8"], acknowledged: true },
  { event_id: "EV-3", event_type: "shift_handover", event_subtype: null, asset_id: null, site_id: "SITE-A", occurred_at: "2026-07-13T08:00:00Z", priority: "normal", payload: {}, correlated_event_ids: [], acknowledged: false },
];

function mockLoaded(source = "live") {
  mocks.getMe.mockResolvedValue({ user_id: "u-1", site_id: "SITE-A" });
  mocks.getEvents.mockResolvedValue({ data: { items: events, total: 12, limit: 50, offset: 0 }, source });
}

describe("EventsPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders trend header, filter tabs, and table", async () => {
    mockLoaded();
    render(<EventsPage />);

    expect(await screen.findByRole("heading", { name: "Operational events" })).toBeInTheDocument();
    expect(screen.getByTestId("events-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByText("Event volume")).toBeInTheDocument();
    expect(screen.getByTestId("events-filter-toolbar")).toBeInTheDocument();
    // Table content: payload summary, fallback description, priority badges.
    expect(screen.getByText("High pressure on pump")).toBeInTheDocument();
    expect(screen.getByText("HX-2")).toBeInTheDocument();
    expect(screen.getByText("acknowledged")).toBeInTheDocument();
    // getEvents params unchanged (spec §10.4).
    expect(mocks.getEvents).toHaveBeenCalledWith({ limit: 50 });
  });

  it("never flashes the empty state while loading", () => {
    mocks.getMe.mockResolvedValue(null);
    mocks.getEvents.mockReturnValue(new Promise(() => {})); // never resolves
    const { container } = render(<EventsPage />);

    expect(screen.queryByText(/No events/)).not.toBeInTheDocument();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument(); // skeletons on first paint
  });

  it("filters via search and priority tabs", async () => {
    mockLoaded();
    render(<EventsPage />);

    fireEvent.change(await screen.findByRole("searchbox", { name: "Search events" }), { target: { value: "HX-2" } });
    expect(screen.getByText("1 of 3 events")).toBeInTheDocument();
    expect(screen.queryByText("P-101")).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search events" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /High/ }));
    expect(screen.getByText("1 of 3 events")).toBeInTheDocument();
    expect(screen.getByText("P-101")).toBeInTheDocument();
    expect(screen.queryByText("HX-2")).not.toBeInTheDocument();
  });

  it("shows the record count exactly once", async () => {
    mocks.getMe.mockResolvedValue(null);
    mocks.getEvents.mockResolvedValue({ data: { items: events, total: 3, limit: 50, offset: 0 }, source: "live" });
    render(<EventsPage />);

    await screen.findByText("High pressure on pump");
    expect(screen.getAllByText(/\d+ of \d+/)).toHaveLength(1);
  });

  it("derives priority filter options from the data, not a fixed list", async () => {
    mockLoaded();
    render(<EventsPage />);

    await screen.findByText("High pressure on pump");
    expect(screen.getByRole("button", { name: /High/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Normal/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Critical/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Low/ })).not.toBeInTheDocument();
  });

  it("renders asset references as links, not in the brand accent", async () => {
    mockLoaded();
    render(<EventsPage />);

    const asset = await screen.findByRole("link", { name: "P-101" });
    expect(asset).toHaveAttribute("href", "/assets/P-101");
    expect(asset).not.toHaveClass("text-accent");
  });

  it("navigates to the detail page on row click", async () => {
    mockLoaded();
    render(<EventsPage />);

    fireEvent.click(await screen.findByText("High pressure on pump"));
    expect(mocks.push).toHaveBeenCalledWith("/events/EV-1");
  });

  it("shows an error surface with retry", async () => {
    mocks.getMe.mockResolvedValue(null);
    mocks.getEvents.mockRejectedValue(new Error("backend unreachable"));
    render(<EventsPage />);

    expect(await screen.findByText("Could not load operational events.")).toBeInTheDocument();
    mockLoaded();
    fireEvent.click(screen.getAllByRole("button", { name: "Retry" })[0]);
    expect(await screen.findByText("High pressure on pump")).toBeInTheDocument();
  });

  it("attributes emitted events to the signed-in user", async () => {
    mocks.getMe.mockResolvedValue({ user_id: "operator-7", site_id: "SITE-B" });
    mocks.getEvents.mockResolvedValue({ data: { items: events, total: 3, limit: 50, offset: 0 }, source: "live" });
    mocks.postWorkOrder.mockResolvedValue({ status: "accepted", event_id: "EV-4" });

    render(<EventsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Emit event" }));
    // Work order is the default type: the headline flow, assigned to the signed-in user.
    fireEvent.click(screen.getByRole("button", { name: "Emit" }));

    await waitFor(() => expect(mocks.postWorkOrder).toHaveBeenCalledWith(expect.objectContaining({
      site_id: "SITE-B",
      assigned_technician_id: "operator-7",
    })));
  });
});
