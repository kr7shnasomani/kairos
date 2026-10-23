import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("getMe", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env.NEXT_PUBLIC_AUTH_STRICT = "true";
    localStorage.clear();
    localStorage.setItem("kairos-token", "expired-token");
    localStorage.setItem("kairos-refresh", "refresh-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.NEXT_PUBLIC_AUTH_STRICT;
    localStorage.clear();
  });

  it("returns the profile after refreshing an expired token", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "fresh-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ user_id: "u-1", role: "admin", email: "a@example.com", site_id: "site-1" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { getMe } = await import("./auth");

    await expect(getMe()).resolves.toMatchObject({ user_id: "u-1", role: "admin" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("fetches the profile once for any number of callers, and retries after a failure", async () => {
    localStorage.setItem("kairos-token", "valid-token");
    const profile = () => new Response(JSON.stringify({ user_id: "u-1", role: "admin" }), { status: 200 });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 500 }))
      .mockImplementation(async () => profile());
    vi.stubGlobal("fetch", fetchMock);

    const { getMe } = await import("./auth");

    await expect(getMe()).resolves.toBeNull();
    await expect(Promise.all([getMe(), getMe(), getMe()])).resolves.toMatchObject([{ user_id: "u-1" }, { user_id: "u-1" }, { user_id: "u-1" }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("mirrors the access token to a strict-mode cookie after login", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      access_token: "access-token",
      refresh_token: "refresh-token",
      token_type: "bearer",
      user_id: "u-1",
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { login } = await import("./auth");
    await login("a@example.com", "password");

    expect(document.cookie).toContain("kairos-access=access-token");
  });
});
