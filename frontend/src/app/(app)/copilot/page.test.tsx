import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SUGGESTIONS, type CopilotAnswer } from "@/lib/copilot";
import { synthesize } from "@/lib/api";
import CopilotPage from "./page";

vi.mock("@/lib/api", () => ({
  synthesize: vi.fn(),
  createAnnotation: vi.fn(),
  submitAnswerFeedback: vi.fn().mockResolvedValue(true),
  getToken: () => null,
}));

const answer = (text: string): CopilotAnswer => ({
  answer: text, sources: [], confidence: 0.9, refused: false, safety_critical: false,
});

describe("CopilotPage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    // jsdom has no scrollIntoView; the page scrolls to the newest turn.
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(cleanup);

  it("uses a full-height governed conversation workspace", () => {
    render(<CopilotPage />);

    expect(screen.getByTestId("copilot-workspace")).toHaveClass("flex", "flex-col");
    expect(screen.getByTestId("copilot-conversation")).toHaveClass("overflow-y-auto");
    expect(screen.getByTestId("copilot-composer")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask the copilot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });

  it("drops a late answer from a conversation the user already left with New chat", async () => {
    let resolveOld: (a: CopilotAnswer) => void = () => {};
    vi.mocked(synthesize)
      .mockImplementationOnce(() => new Promise<CopilotAnswer>((r) => { resolveOld = r; }))
      .mockResolvedValueOnce(answer("NEW ANSWER"));

    render(<CopilotPage />);
    fireEvent.click(screen.getByRole("button", { name: new RegExp(SUGGESTIONS[0]!.slice(0, 20)) }));
    fireEvent.click(screen.getByRole("button", { name: "Start a new chat" }));
    fireEvent.click(screen.getByRole("button", { name: new RegExp(SUGGESTIONS[1]!.slice(0, 20)) }));
    expect(await screen.findByText(/NEW ANSWER/)).toBeInTheDocument();

    await act(async () => resolveOld(answer("OLD ANSWER")));

    expect(screen.queryByText(/OLD ANSWER/)).not.toBeInTheDocument();
    expect(screen.getByText(/NEW ANSWER/)).toBeInTheDocument();
  });
});
