import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getElicitationQuestions, submitElicitationResponses } from "@/lib/api";
import { enqueueWrite } from "@/lib/idb";
import ElicitationPage from "./page";

vi.mock("next/navigation", () => ({ useParams: () => ({ workOrderId: "WO-118" }) }));
vi.mock("@/lib/api", () => ({
  getToken: () => null,
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

  it("shows the no-questions state instead of crashing when the session has none", async () => {
    vi.mocked(getElicitationQuestions).mockResolvedValueOnce({
      data: { session_id: "S-2", work_order_id: "WO-118", status: "pending", created_at: "2026-07-15T08:00:00Z", questions: [] },
      source: "live",
    });
    render(<ElicitationPage />);
    expect(await screen.findByText("No questions available")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  async function answerAndSubmit() {
    render(<ElicitationPage />);
    fireEvent.click(await screen.findByRole("radio", { name: /Noise/ }));
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "Seal weeping" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit responses" }));
  }

  it("does not queue a submission the server rejected, and says so", async () => {
    vi.mocked(enqueueWrite).mockClear();
    vi.mocked(submitElicitationResponses).mockRejectedValueOnce(new Error("/elicitation/WO-118/responses → HTTP 422"));
    await answerAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent(/nothing was saved/);
    expect(enqueueWrite).not.toHaveBeenCalled();
    expect(screen.queryByText("Responses queued")).not.toBeInTheDocument();
  });

  it("blames the server, not the answers, for a 5xx", async () => {
    vi.mocked(enqueueWrite).mockClear();
    vi.mocked(submitElicitationResponses).mockRejectedValueOnce(new Error("/elicitation/WO-118/responses → HTTP 503"));
    await answerAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not save these responses just now/);
    expect(enqueueWrite).not.toHaveBeenCalled();
  });

  it("queues the submission when the network is down", async () => {
    vi.mocked(enqueueWrite).mockClear().mockResolvedValueOnce(undefined);
    vi.mocked(submitElicitationResponses).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await answerAndSubmit();

    expect(await screen.findByText("Responses queued")).toBeInTheDocument();
    expect(enqueueWrite).toHaveBeenCalledOnce();
  });
});
