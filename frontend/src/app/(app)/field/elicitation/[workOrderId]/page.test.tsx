import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ElicitationPage from "./page";

vi.mock("next/navigation", () => ({ useParams: () => ({ workOrderId: "WO-118" }) }));
vi.mock("@/lib/api", () => ({
  getElicitationQuestions: vi.fn().mockResolvedValue({
    data: {
      session_id: "S-1", work_order_id: "WO-118", status: "in_progress", created_at: "2026-07-15T08:00:00Z",
      questions: [
        { question_id: "q1", question_text: "What did you observe?", context: "Record the condition at shutdown.", options: ["Noise", "Vibration"], question_type: "multiple_choice" },
        { question_id: "q2", question_text: "Anything else?", context: null, options: null, question_type: "free_text" },
      ],
    },
    source: "api",
  }),
  submitElicitationResponses: vi.fn(),
}));
vi.mock("@/lib/idb", () => ({ enqueueWrite: vi.fn() }));

describe("ElicitationPage", () => {
  afterEach(cleanup);

  it("uses a responsive step and session-context workspace", async () => {
    render(<ElicitationPage />);
    await waitFor(() => expect(screen.getByText("What did you observe?")).toBeInTheDocument());

    expect(screen.getByTestId("elicitation-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("elicitation-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_280px]");
    expect(screen.getByTestId("elicitation-question")).toHaveTextContent("Noise");
    expect(screen.getByTestId("elicitation-context")).toHaveTextContent("WO-118");
    expect(screen.getByRole("progressbar")).toHaveClass("rounded-xl");
    expect(screen.getByRole("button", { name: /Next/ })).toHaveClass("min-h-[52px]");
  });
});
