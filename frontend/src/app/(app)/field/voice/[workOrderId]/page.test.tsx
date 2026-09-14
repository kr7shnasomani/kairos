import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import VoicePage from "./page";

vi.mock("next/navigation", () => ({ useParams: () => ({ workOrderId: "WO-118" }) }));
vi.mock("@/components/voice-recorder", () => ({ VoiceRecorder: () => <button>Start recording</button> }));
// getToken: the page resolves the signed-in user (useMe → getMe) to attribute the note.
vi.mock("@/lib/api", () => ({ submitVoiceNote: vi.fn(), getToken: () => null }));

describe("VoicePage", () => {
  afterEach(cleanup);

  it("keeps work-order context visible around the capture task", () => {
    render(<VoicePage />);

    expect(screen.getByTestId("work-order-voice-workspace")).toHaveClass("max-w-[1100px]");
    expect(screen.getByTestId("work-order-voice-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_300px]");
    expect(screen.getByTestId("work-order-voice-capture")).toHaveTextContent("Start recording");
    expect(screen.getByTestId("work-order-voice-context")).toHaveTextContent("WO-118");
    expect(screen.getByTestId("work-order-voice-context")).toHaveTextContent("Quarantine");
  });
});
