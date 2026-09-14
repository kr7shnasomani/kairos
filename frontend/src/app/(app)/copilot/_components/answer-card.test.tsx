import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CopilotAnswer } from "@/lib/copilot";
import { Answer, provisionalText } from "./answer-card";

vi.mock("@/lib/api", () => ({ submitAnswerFeedback: vi.fn().mockResolvedValue(true) }));

const base: CopilotAnswer = {
  answer: null,
  sources: [],
  confidence: 0,
  refused: false,
  safety_critical: false,
};

describe("streamed answer text", () => {
  afterEach(cleanup);

  it("renders streamed text while synthesis is still running", () => {
    render(<Answer data={{ ...base, is_synthesizing: true }} streaming="The pump was last" />);

    expect(screen.getByText(/The pump was last/)).toBeInTheDocument();
    // Marked as in-progress, so it cannot be mistaken for a finished, sourced answer.
    expect(screen.getByText(/sources and confidence are attached once/i)).toBeInTheDocument();
  });

  it("falls back to the spinner when synthesizing with no text yet", () => {
    render(<Answer data={{ ...base, is_synthesizing: true }} />);

    expect(screen.getByText(/Assembling evidence/i)).toBeInTheDocument();
  });

  it("never shows streamed text once a refusal has arrived", () => {
    /* The safety gate can convert a completed answer into a refusal. If stale streamed text
       survived that transition the operator would read a claim the system just retracted —
       the exact 'hedged partial answer' the architecture forbids. */
    render(
      <Answer
        data={{ ...base, refused: true, safety_critical: true, refusal_reason: "insufficient evidence" }}
        streaming="probably about 16 bar"
      />,
    );

    expect(screen.queryByText(/probably about 16 bar/)).not.toBeInTheDocument();
    expect(screen.getByText(/Safety-critical query — refused/i)).toBeInTheDocument();
  });

  it("does not show streamed text alongside a completed answer", () => {
    render(
      <Answer
        data={{ ...base, answer: "Final governed answer.", confidence: 0.9 }}
        streaming="Final governed ans"
      />,
    );

    expect(screen.queryByText("Final governed ans")).not.toBeInTheDocument();
  });
});

describe("unreported confidence is not zero confidence", () => {
  afterEach(cleanup);

  // Regression: the backend returns confidence: null whenever the synthesis output carries no
  // parseable CONFIDENCE marker — 130 of 573 non-refused answers in audit_log, ~23%. The client
  // coerced that to 0, so a perfectly good answer rendered "Low confidence · 0%" and an empty
  // meter: a score the system never produced.
  it("does not call a null-confidence answer low confidence", () => {
    render(<Answer data={{ ...base, answer: "Seal replaced on 12 Mar.", confidence: null }} />);

    expect(screen.queryByText(/Low confidence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument();
  });

  it("says confidence was not reported rather than showing a meter", () => {
    render(<Answer data={{ ...base, answer: "Seal replaced on 12 Mar.", confidence: null }} />);

    expect(screen.getByText(/Confidence not reported/i)).toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });

  // The other half of the fix: a genuinely low score must still warn. Without this, "stop
  // showing 0%" could be satisfied by suppressing the warning entirely.
  it("still warns when the model really did report low confidence", () => {
    render(<Answer data={{ ...base, answer: "Possibly 16 bar.", confidence: 0.4 }} />);

    expect(screen.getByText(/Low confidence · 40%/i)).toBeInTheDocument();
  });

  it("still renders a real meter when confidence is reported", () => {
    render(<Answer data={{ ...base, answer: "Seal replaced on 12 Mar.", confidence: 0.9 }} />);

    expect(screen.getByRole("meter")).toBeInTheDocument();
    expect(screen.queryByText(/Confidence not reported/i)).not.toBeInTheDocument();
  });
});

// Regression: the raw `ANSWER:` / `CONFIDENCE:` contract flashed on screen while an answer streamed.
describe("provisional streamed text", () => {
  it("drops the ANSWER: prefix and everything from the first section marker", () => {
    expect(provisionalText("ANSWER: The seal failed.\nCONFIDENCE: 0.95\nSOURCES_USED: 1,2")).toBe("The seal failed.");
  });

  it("hides a marker that has only partly arrived", () => {
    expect(provisionalText("ANSWER: The seal failed.\nCONFID")).toBe("The seal failed.");
    expect(provisionalText("ANS")).toBe("");
  });

  it("leaves ordinary answer text, including capitalised tags, untouched", () => {
    expect(provisionalText("ANSWER: Replace FSL-2240B on EQ-101")).toBe("Replace FSL-2240B on EQ-101");
  });

  it("renders the cleaned text while synthesizing", () => {
    render(<Answer data={{ ...base, is_synthesizing: true }} streaming={"ANSWER: The pump was last\nCONFIDENCE: 0.9"} />);
    expect(screen.getByText(/The pump was last/)).toBeInTheDocument();
    expect(screen.queryByText(/CONFIDENCE/)).not.toBeInTheDocument();
  });
});

