import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./error";

const flags = vi.hoisted(() => ({ refreshed: false }));
vi.mock("@/lib/api", async (importActual) => ({
  ...(await importActual<typeof import("@/lib/api")>()),
  refreshedThisPageLoad: () => flags.refreshed,
}));

const reload = vi.fn();
const jwt = (exp: number) => `h.${btoa(JSON.stringify({ exp }))}.s`;

describe("app error boundary", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    flags.refreshed = false;
    reload.mockReset();
    Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, reload } });
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("refreshes an expired session and reloads the page instead of showing the error", async () => {
    localStorage.setItem("kairos-token", jwt(1));
    localStorage.setItem("kairos-refresh", "refresh-token");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ access_token: jwt(4e9) }), { status: 200 })));

    render(<ErrorBoundary error={new Error("redacted")} reset={vi.fn()} />);

    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
  });

  it("reloads once when the shell already refreshed the session during this page load", () => {
    // Seen in the browser: the shell refreshes before it renders the page, so the token looks valid
    // here, but the server rendered the page with the old cookie.
    localStorage.setItem("kairos-token", jwt(4e9));
    flags.refreshed = true;

    render(<ErrorBoundary error={new Error("redacted")} reset={vi.fn()} />);

    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("shows the error instead of reloading again straight after a reload", async () => {
    localStorage.setItem("kairos-token", jwt(4e9));
    flags.refreshed = true;
    sessionStorage.setItem("kairos-error-reload", String(Date.now()));

    render(<ErrorBoundary error={new Error("boom")} reset={vi.fn()} />);

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();
  });

  it("shows the error when the session is valid and was not refreshed", async () => {
    localStorage.setItem("kairos-token", jwt(4e9));

    render(<ErrorBoundary error={new Error("boom")} reset={vi.fn()} />);

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();
  });
});
