import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "./page";

vi.mock("@/components/theme-toggle", () => ({ ThemeToggle: () => <button>Change theme</button>, ContrastToggle: () => <button>Change contrast</button> }));

describe("SettingsPage", () => {
  afterEach(cleanup);

  it("uses a responsive preferences navigation and content panel", () => {
    render(<SettingsPage />);

    expect(screen.getByTestId("settings-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("settings-layout")).toHaveClass("md:grid-cols-[220px_minmax(0,1fr)]");
    expect(screen.getByTestId("settings-navigation")).toHaveTextContent("Appearance");
    expect(screen.getByTestId("settings-panel")).toHaveTextContent("Display");
    expect(screen.getByRole("button", { name: "Change theme" }).parentElement).toHaveClass("min-h-11");
  });
});
