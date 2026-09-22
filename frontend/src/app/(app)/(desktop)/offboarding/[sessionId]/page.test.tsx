import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OffboardingSessionPage from "./page";

vi.mock("next/navigation", () => ({ useParams: () => ({ sessionId: "P-1" }) }));
vi.mock("@/components/voice-recorder", () => ({ VoiceRecorder: () => <div>Voice recorder</div> }));
vi.mock("@/lib/api", () => ({
  getOffboarding: vi.fn().mockResolvedValue({
    data: {
      id: "P-1", personnel_id: "U-1", personnel_email: "priya.sharma@plant.in", retirement_date: "2026-09-30", total_sessions: 3, status: "active", created_at: "2026-01-01",
      session_items: [
        { id: "S-1", session_number: 1, equipment_family: "Centrifugal pumps", status: "completed", scheduled_for: "2026-07-01" },
        { id: "S-2", session_number: 2, equipment_family: "Control valves", status: "questions_ready", scheduled_for: "2026-07-15" },
        { id: "S-3", session_number: 3, equipment_family: "Isolation", status: "pending", scheduled_for: "2026-07-30" },
      ],
    },
    source: "api",
  }),
  getOffboardingQuestions: vi.fn().mockResolvedValue({ data: { "S-2": ["Which failure pattern appears first?", "What should the next engineer verify?"] }, source: "api" }),
  submitOffboardingResponses: vi.fn().mockResolvedValue({ status: "queued", items_queued: 2 }),
}));

describe("OffboardingSessionPage", () => {
  afterEach(cleanup);

  it("renders a focused expert interview with real progress and submit gating", async () => {
    render(<OffboardingSessionPage />);

    await waitFor(() => expect(screen.getByTestId("offboarding-session-workspace")).toBeInTheDocument());
    expect(screen.getByTestId("offboarding-session-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("offboarding-profile-header")).toHaveTextContent("PS");
    expect(screen.getByTestId("offboarding-profile-header")).toHaveTextContent(/1\s*of 3 sessions/);
    expect(screen.getByTestId("offboarding-session-navigation")).toHaveTextContent("Control valves");
    expect(screen.getByTestId("offboarding-interview")).toHaveTextContent(/0\s*of 2 answered/);

    const submit = screen.getByRole("button", { name: "Submit session responses" });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Which failure pattern appears first?"), { target: { value: "Seal drag increases." } });
    fireEvent.change(screen.getByLabelText("What should the next engineer verify?"), { target: { value: "Check actuator travel." } });
    expect(screen.getByTestId("offboarding-interview")).toHaveTextContent(/2\s*of 2 answered/);
    expect(submit).toBeEnabled();

    fireEvent.click(screen.getAllByRole("button", { name: "Use voice instead" })[0]);
    expect(screen.getByText(/memory aid only/)).toBeInTheDocument();
  });
});
