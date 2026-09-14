import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import VoiceCapturePage from "./page";

vi.mock("@/components/voice-recorder", () => ({ VoiceRecorder: () => <button>Start recording</button> }));
// getToken: the page resolves the signed-in user (useMe → getMe) to attribute the note.
vi.mock("@/lib/api", () => ({ submitVoiceNote: vi.fn(), getToken: () => null }));

describe("VoiceCapturePage", () => {
  afterEach(cleanup);

  it("presents ad-hoc capture as a responsive field task", () => {
    render(<VoiceCapturePage />);

    expect(screen.getByTestId("field-voice-workspace")).toHaveClass("max-w-[1100px]");
    expect(screen.getByTestId("field-voice-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_300px]");
    expect(screen.getByTestId("field-voice-capture")).toHaveTextContent("Start recording");
    expect(screen.getByTestId("field-voice-context")).toHaveTextContent("Engineering review");
    expect(screen.getByLabelText(/Asset \/ work-order tag/)).toHaveClass("min-h-11");
  });
});
