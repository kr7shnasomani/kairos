import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { rcaFor } from "@/lib/rca";
import type { RcaPack } from "@/lib/types";
import RcaPage from "./page";

const mocks = vi.hoisted(() => ({ getRcaPack: vi.fn() }));

vi.mock("@/lib/api", () => ({ getRcaPack: mocks.getRcaPack }));

// jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one.
vi.stubGlobal("ResizeObserver", class {
  observe() {}
  unobserve() {}
  disconnect() {}
});

async function assemble() {
  fireEvent.click(screen.getByRole("button", { name: "Assemble RCA pack" }));
  await waitFor(() => expect(mocks.getRcaPack).toHaveBeenCalled());
}

describe("RcaPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("uses a responsive analysis workspace and structured result panels", async () => {
    mocks.getRcaPack.mockResolvedValue(rcaFor("EQ-101", "SEAL-FAIL"));

    render(<RcaPage />);

    expect(screen.getByTestId("rca-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("rca-builder")).toHaveClass("rounded-xl", "bg-surface");
    expect(screen.getByTestId("rca-builder-fields")).toHaveClass("lg:grid-cols-[minmax(140px,0.7fr)_minmax(180px,1fr)_180px_auto]");

    await assemble();
    // Page default asset is EQ-101 (canonical golden asset).
    expect(mocks.getRcaPack).toHaveBeenCalledWith(
      "EQ-101",
      "SEAL-FAIL",
      expect.stringMatching(/T00:00:00Z$/),
      false,
    );
    expect(await screen.findByTestId("rca-result-grid")).toHaveClass("lg:grid-cols-[3fr_2fr]");
    expect(screen.getByRole("heading", { name: "Timeline" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ranked hypotheses" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Supporting documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export JSON" })).toHaveAttribute("download", "EQ-101-SEAL-FAIL-rca.json");
  });

  it("renders dashes, not crashes, for missing confidence and evidence weights", async () => {
    const base = rcaFor("P-101", "SEAL-FAIL");
    const pack = {
      ...base,
      confidence: undefined,
      hypotheses: [{ hypothesis: "Seal wear", evidence_weight: undefined, sources: [] }],
      supporting_documents: [{ ...base.supporting_documents[0], confidence: undefined }],
    } as unknown as RcaPack;
    mocks.getRcaPack.mockResolvedValue(pack);

    render(<RcaPage />);
    await assemble();

    expect(await screen.findByText("Confidence —")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it("replaces everything below the header with a RefusalCard on refusal", async () => {
    mocks.getRcaPack.mockResolvedValue(rcaFor("P-101", "PSV-RELIEF"));

    render(<RcaPage />);
    await assemble();

    expect(await screen.findByText(/does not synthesize hypotheses/i)).toBeInTheDocument();
    expect(screen.queryByTestId("rca-result-grid")).not.toBeInTheDocument();
  });

  it("shows the synthesis-unavailable notice and empty-hypotheses state", async () => {
    const pack = { ...rcaFor("P-101", "SEAL-FAIL"), synthesis_available: false, hypotheses: [] };
    mocks.getRcaPack.mockResolvedValue(pack);

    render(<RcaPage />);
    await assemble();

    expect(await screen.findByText("Synthesis unavailable")).toBeInTheDocument();
    expect(screen.getByText("No hypotheses generated")).toBeInTheDocument();
  });

  it("shows an error card with retry when assembly fails", async () => {
    mocks.getRcaPack.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(rcaFor("P-101", "SEAL-FAIL"));

    render(<RcaPage />);
    await assemble();

    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("rca-result-grid")).toBeInTheDocument();
  });

  it("ignores an older pack that resolves after a newer request", async () => {
    let resolveOld: (p: RcaPack) => void = () => {};
    mocks.getRcaPack
      .mockImplementationOnce(() => new Promise<RcaPack>((r) => { resolveOld = r; }))
      .mockResolvedValueOnce(rcaFor("HE-301", "TUBE-FOUL"));

    render(<RcaPage />);
    fireEvent.click(screen.getByRole("button", { name: /mechanical seal failure/ }));
    fireEvent.click(screen.getByRole("button", { name: /tube fouling/ }));
    expect(await screen.findByTestId("rca-result-grid")).toBeInTheDocument();
    expect(screen.getByText("HE-301")).toBeInTheDocument();

    await act(async () => resolveOld(rcaFor("EQ-101", "SEAL-FAIL")));

    expect(screen.getByText("HE-301")).toBeInTheDocument();
    expect(screen.queryByText("SEAL-FAIL")).not.toBeInTheDocument();
  });
});
