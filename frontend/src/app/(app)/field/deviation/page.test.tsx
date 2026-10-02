import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DeviationPage from "./page";

vi.mock("@/lib/api", () => ({ getToken: () => null, postDeviationFlag: vi.fn() }));

describe("DeviationPage", () => {
  afterEach(cleanup);

  it("shows the observation form beside its operational consequence", () => {
    render(<DeviationPage />);

    expect(screen.getByTestId("deviation-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("deviation-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_300px]");
    expect(screen.getByTestId("deviation-form")).toHaveTextContent("Description of deviation");
    expect(screen.getByTestId("deviation-context")).toHaveTextContent("What happens next");
    expect(screen.getByLabelText(/Asset \/ tag number/)).toHaveClass("min-h-[52px]");
  });
});
