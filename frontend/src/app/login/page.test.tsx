import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  login: vi.fn(),
  getMe: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push, replace: mocks.replace }) }));
vi.mock("@/components/theme-toggle", () => ({ ThemeToggle: () => <span /> }));
vi.mock("@/lib/auth", () => ({ login: mocks.login, getMe: mocks.getMe }));
vi.mock("@/lib/api", () => ({ getToken: () => null }));

import LoginPage from "./page";

// The demo credentials are read once at module load (Next inlines NEXT_PUBLIC_* at build time), so
// each case sets the env first and then loads a fresh copy of the page.
async function loadPage() {
  vi.resetModules();
  return (await import("./page")).default;
}

describe("LoginPage", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
  });

  beforeEach(() => {
    mocks.push.mockReset();
    mocks.replace.mockReset();
    mocks.login.mockResolvedValue(undefined);
    mocks.getMe.mockResolvedValue({ role: "engineer" });
  });

  it("sends an authenticated staff user straight to the management dashboard", async () => {
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "engineer@kairos.local" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "password" } });
    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/management"));
  });

  it("provides a back link to the public landing page", () => {
    render(<LoginPage />);

    expect(screen.getByRole("link", { name: /back to landing page/i })).toHaveAttribute("href", "/");
  });

  it("uses a responsive sign-in and workspace-context layout", () => {
    render(<LoginPage />);

    expect(screen.getByTestId("login-workspace")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.72fr)]");
    expect(screen.getByTestId("login-context")).toHaveTextContent("Evidence-linked operations");
    expect(screen.getByTestId("login-form-panel")).toHaveTextContent("Sign in to Kairos");
    expect(screen.getByLabelText(/email/i)).toHaveClass("min-h-11");
  });

  it("hides the demo button when no demo credentials are configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_EMAIL", "");
    vi.stubEnv("NEXT_PUBLIC_DEMO_PASSWORD", "");
    const Page = await loadPage();
    render(<Page />);

    expect(screen.queryByRole("button", { name: /live demo/i })).toBeNull();
  });

  it("signs the demo button in with the configured read-only credentials and lands on the Copilot", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_EMAIL", "demo@kairos.local");
    vi.stubEnv("NEXT_PUBLIC_DEMO_PASSWORD", "public-demo-pw");
    mocks.getMe.mockResolvedValue({ role: "demo" });
    const Page = await loadPage();
    render(<Page />);

    fireEvent.click(screen.getByRole("button", { name: /live demo/i }));

    await waitFor(() => expect(mocks.login).toHaveBeenCalledWith("demo@kairos.local", "public-demo-pw"));
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/copilot"));
  });
});
