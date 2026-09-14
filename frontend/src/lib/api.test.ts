import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Regression: outside strict mode reads went out with no token, so the backend answered as its dev
// mock user — a field worker saw that user's inbox and their own brief 404'd.
describe("reads outside strict mode", () => {
  beforeEach(() => {
    vi.resetModules();
    delete process.env.NEXT_PUBLIC_AUTH_STRICT;
    localStorage.clear();
    document.cookie = "kairos-access=; Path=/; Max-Age=0";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("still sends the signed-in user's token", async () => {
    localStorage.setItem("kairos-token", "field-token");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ briefs: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { getBriefs } = await import("./api");
    await getBriefs();

    expect(fetchMock.mock.calls[0][1]).toEqual(expect.objectContaining({
      headers: expect.objectContaining({ Authorization: "Bearer field-token" }),
    }));
  });

  it("mirrors the token into the cookie server components read", async () => {
    const { storeSession } = await import("./api");
    storeSession("field-token");

    expect(document.cookie).toContain("kairos-access=field-token");
  });

  it("sends no Authorization header when nobody is signed in", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ briefs: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { getBriefs } = await import("./api");
    await getBriefs();

    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty("Authorization");
  });
});

describe("strict-auth reads", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env.NEXT_PUBLIC_AUTH_STRICT = "true";
    localStorage.clear();
    localStorage.setItem("kairos-token", "access-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.NEXT_PUBLIC_AUTH_STRICT;
    localStorage.clear();
  });

  it("attaches the access token to a protected GET", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ briefs: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { getBriefs } = await import("./api");
    await getBriefs();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/briefs/"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer access-token" }),
      }),
    );
  });

  it("refreshes once and retries a protected GET after a 401", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "refreshed-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ briefs: [{ brief_id: "b-1" }] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("kairos-refresh", "refresh-token");

    const { getBriefs } = await import("./api");
    await getBriefs();

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[2][1]).toEqual(expect.objectContaining({
      headers: expect.objectContaining({ Authorization: "Bearer refreshed-token" }),
    }));
  });

  it("clears the session when the refreshed GET is also rejected", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "refreshed-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("kairos-refresh", "refresh-token");

    const { getBriefs } = await import("./api");
    // Rejects rather than resolving to a fixture — the session teardown is what matters here.
    await expect(getBriefs()).rejects.toThrow();

    expect(localStorage.getItem("kairos-token")).toBeNull();
    expect(localStorage.getItem("kairos-refresh")).toBeNull();
  });

  it("clears the session when the refreshed write is also rejected", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "refreshed-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("kairos-refresh", "refresh-token");

    const { ackBrief } = await import("./api");
    await expect(ackBrief("brief-1", {})).rejects.toThrow("HTTP 401");

    expect(localStorage.getItem("kairos-token")).toBeNull();
    expect(localStorage.getItem("kairos-refresh")).toBeNull();
  });

  it("refreshes before retrying a multipart voice upload", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "refreshed-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ task_id: "task-1", status: "queued" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("kairos-refresh", "refresh-token");

    const { submitVoiceNote } = await import("./api");
    await expect(submitVoiceNote("wo-1", new Blob(["audio"]), "u-1")).resolves.toMatchObject({ task_id: "task-1" });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[2][1]).toEqual(expect.objectContaining({
      headers: expect.objectContaining({ Authorization: "Bearer refreshed-token" }),
    }));
  });
});

describe("no fixture fallbacks", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("throws when the audit-pack backend is unavailable, instead of serving a fixture", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const { getAuditPack } = await import("./api");

    // Was: returned a fabricated AuditPack tagged source:"demo" with invented clauses and
    // evidence. The live-only guard discarded it anyway, so the only thing it achieved was
    // making a failure look like a compliance record in the source.
    await expect(getAuditPack("OISD-117")).rejects.toThrow();
  });
});

describe("events: empty and offline are honest", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("throws when the backend is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const { getEvents } = await import("./api");

    await expect(getEvents({ limit: 4 })).rejects.toThrow();
  });

  it("returns an empty live list rather than substituting demo events", async () => {
    // This is the important one. getEvents used to swap in fixtures when a *successful*
    // request returned zero items — fabricating data on a 200, not just on failure.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      items: [], total: 0, limit: 50, offset: 0,
    }), { status: 200, headers: { "Content-Type": "application/json" } })));

    const { getEvents } = await import("./api");
    const result = await getEvents();

    expect(result.source).toBe("live");
    expect(result.data.items).toHaveLength(0);
  });
});
