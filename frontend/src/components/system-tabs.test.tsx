import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SystemTabs } from "./system-tabs";

// test/setup.ts registers no global cleanup and vitest `globals` is off, so RTL does not
// auto-unmount. Without this, renders accumulate and every query matches twice.
afterEach(cleanup);

const mocks = vi.hoisted(() => ({ pathname: null as string | null, role: "admin" as string }));

vi.mock("next/navigation", () => ({ usePathname: () => mocks.pathname }));
vi.mock("./use-role", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./use-role")>();
  return { ...actual, useRole: () => mocks.role };
});

describe("SystemTabs", () => {
  beforeEach(() => {
    mocks.pathname = "/system-health";
    mocks.role = "admin";
  });

  it("renders every system surface for an admin", () => {
    render(<SystemTabs />);
    for (const label of ["Health", "Settings"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("marks the active tab with aria-current", () => {
    render(<SystemTabs />);
    expect(screen.getByRole("link", { name: "Health" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Settings" })).not.toHaveAttribute("aria-current");
  });

  it("renders nothing for a non-admin, who would only have the Settings tab", () => {
    mocks.role = "engineer";
    render(<SystemTabs />);
    expect(screen.queryByRole("navigation", { name: "System" })).not.toBeInTheDocument();
  });

  it("survives a null pathname", () => {
    // usePathname() returns null with no router context. Calling .startsWith on it threw
    // and took the whole page down — this pins the guard.
    mocks.pathname = null;
    render(<SystemTabs />);
    expect(screen.getByRole("navigation", { name: "System" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Health" })).not.toHaveAttribute("aria-current");
  });
});
