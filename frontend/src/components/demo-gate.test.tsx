import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getMe: vi.fn() }));
vi.mock("@/lib/auth", () => ({ getMe: mocks.getMe }));

import { DemoGate } from "./demo-gate";
import { DEMO_DISABLED_MESSAGE } from "./use-role";

describe("DemoGate", () => {
  beforeEach(() => mocks.getMe.mockReset());
  afterEach(cleanup);

  it("disables the controls inside it for the demo account and says why", async () => {
    mocks.getMe.mockResolvedValue({ role: "demo" });
    render(<DemoGate><button>Supersede</button><input aria-label="note" /></DemoGate>);

    await waitFor(() => expect(screen.getByRole("button", { name: "Supersede" })).toBeDisabled());
    expect(screen.getByLabelText("note")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Supersede" }).closest("fieldset")).toHaveAttribute("title", DEMO_DISABLED_MESSAGE);
  });

  it.each(["admin", "engineer", "reliability"])("leaves %s untouched", async (role) => {
    mocks.getMe.mockResolvedValue({ role });
    render(<DemoGate><button>Supersede</button></DemoGate>);

    await waitFor(() => expect(mocks.getMe).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Supersede" })).toBeEnabled();
    expect(document.querySelector("fieldset")).toBeNull();
  });

  it("can be switched off for a control that only writes in some states", async () => {
    mocks.getMe.mockResolvedValue({ role: "demo" });
    render(<DemoGate when={false}><button>Next</button></DemoGate>);

    await waitFor(() => expect(mocks.getMe).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });
});
