import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A JWT whose payload is {sub}. Signature is irrelevant: the client only reads the claim.
const jwt = (sub: string) => `h.${btoa(JSON.stringify({ sub, exp: 9999999999 }))}.s`;

// L3: a route param is data, never path.
describe("API path encoding", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("encodes route params so a crafted id cannot reach another API path", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { getEvent, getBrief, getDocument } = await import("./api");
    const evil = "x/../../admin?y=1#";
    await getEvent(evil);
    await getBrief(evil);
    await getDocument(evil);
    for (const [url] of fetchMock.mock.calls) {
      expect(url).toContain(encodeURIComponent(evil));
      expect(url).not.toContain("/../");
    }
  });

  it("api.ts has no unencoded path interpolation left", async () => {
    const { readFileSync } = await import("node:fs");
    const src = readFileSync(join(process.cwd(), "src", "lib", "api.ts"), "utf8");
    const bare = src
      .split("\n")
      .filter((l) => /`\/[a-z-]+[/?][^`]*\$\{/.test(l) && !/encodeURIComponent/.test(l))
      // Plain values the client builds itself: query strings and a number.
      .filter((l) => !/\$\{(qs|qs\.toString\(\)|days)\}/.test(l));
    expect(bare).toEqual([]);
  });
});

// L1 client + M10: sign-out leaves nothing behind.
describe("clearSession", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    sessionStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("revokes server-side, wipes caches, queue and Copilot history, and tells the service worker", async () => {
    localStorage.setItem("kairos-token", "tok");
    localStorage.setItem("kairos-refresh", "ref");
    sessionStorage.setItem("kairos:copilot:turns", "[1]");
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"status":"ok"}', { status: 200 }));
    const deleted: string[] = [];
    const deleteDatabase = vi.fn();
    const post = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("caches", { keys: async () => ["a", "b"], delete: async (k: string) => { deleted.push(k); return true; } });
    vi.stubGlobal("indexedDB", { deleteDatabase });
    Object.defineProperty(navigator, "serviceWorker", { value: { controller: { postMessage: post } }, configurable: true });

    const { clearSession } = await import("./api");
    clearSession();
    await vi.waitFor(() => expect(deleted).toEqual(["a", "b"]));

    expect(localStorage.getItem("kairos-token")).toBeNull();
    expect(sessionStorage.getItem("kairos:copilot:turns")).toBeNull();
    expect(deleteDatabase).toHaveBeenCalledWith("kairos-queue");
    expect(post).toHaveBeenCalledWith({ type: "LOGOUT" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/auth\/logout$/);
    expect(init).toMatchObject({ method: "POST", headers: { Authorization: "Bearer tok" } });
  });

  it("a forced expiry drops the tokens but keeps the offline queue and caches", async () => {
    localStorage.setItem("kairos-token", "tok");
    localStorage.setItem("kairos-refresh", "ref");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 200 })));
    const keys = vi.fn().mockResolvedValue(["a"]);
    const deleteDatabase = vi.fn();
    const post = vi.fn();
    vi.stubGlobal("caches", { keys, delete: vi.fn() });
    vi.stubGlobal("indexedDB", { deleteDatabase });
    Object.defineProperty(navigator, "serviceWorker", { value: { controller: { postMessage: post } }, configurable: true });

    const { expireSession } = await import("./api");
    expireSession();

    expect(localStorage.getItem("kairos-token")).toBeNull();
    expect(localStorage.getItem("kairos-refresh")).toBeNull();
    expect(deleteDatabase).not.toHaveBeenCalled();
    expect(keys).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
  });

  it("a 401 that cannot be refreshed expires the session without wiping the queue", async () => {
    localStorage.setItem("kairos-token", "tok");
    localStorage.setItem("kairos-refresh", "ref");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));
    const deleteDatabase = vi.fn();
    vi.stubGlobal("indexedDB", { deleteDatabase });
    const { fetchWithSession } = await import("./api");
    const res = await fetchWithSession("/briefs/1/ack", { method: "POST" });
    expect(res.status).toBe(401);
    expect(localStorage.getItem("kairos-token")).toBeNull();
    expect(deleteDatabase).not.toHaveBeenCalled();
  });

  it("never blocks sign-out when the backend or the browser APIs fail", async () => {
    localStorage.setItem("kairos-token", "tok");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    vi.stubGlobal("caches", { keys: () => { throw new Error("blocked"); } });
    vi.stubGlobal("indexedDB", { deleteDatabase: () => { throw new Error("blocked"); } });
    const { clearSession } = await import("./api");
    expect(() => clearSession()).not.toThrow();
    expect(localStorage.getItem("kairos-token")).toBeNull();
  });
});

// M10: queued writes belong to the user who made them.
describe("offline write queue", () => {
  type Row = { id: number; url: string; method: string; body: string; user?: string };
  let rows: Row[];

  // Smallest IndexedDB that idb.ts uses: one store with add/getAll/count/delete.
  const fakeIndexedDB = () => ({
    open: () => {
      const req: Record<string, unknown> = {};
      const db = {
        close() {},
        createObjectStore() {},
        transaction: () => {
          const tx: Record<string, unknown> = {};
          const op = <T,>(fn: () => T) => {
            const r: { result?: T; onsuccess?: () => void } = {};
            queueMicrotask(() => { r.result = fn(); r.onsuccess?.(); (tx.oncomplete as (() => void) | undefined)?.(); });
            return r;
          };
          tx.objectStore = () => ({
            add: (v: Omit<Row, "id">) => op(() => rows.push({ ...v, id: rows.length + 1 })),
            getAll: () => op(() => [...rows]),
            count: () => op(() => rows.length),
            delete: (id: number) => op(() => { rows = rows.filter((r) => r.id !== id); }),
          });
          return tx;
        },
      };
      queueMicrotask(() => { req.result = db; (req.onupgradeneeded as (() => void) | undefined)?.(); (req.onsuccess as () => void)(); });
      return req;
    },
  });

  beforeEach(() => {
    vi.resetModules();
    rows = [];
    localStorage.clear();
    vi.stubGlobal("indexedDB", fakeIndexedDB());
  });
  afterEach(() => vi.unstubAllGlobals());

  it("records the user id on each queued write", async () => {
    localStorage.setItem("kairos-token", jwt("user-a"));
    const { enqueueWrite } = await import("./idb");
    await enqueueWrite("/elicitation/WO-1/responses", "POST", { a: 1 });
    expect(rows[0].user).toBe("user-a");
  });

  it("drops another user's writes instead of replaying them as the current user", async () => {
    rows = [
      { id: 1, url: "http://x/a", method: "POST", body: "{}", user: "user-a" },
      { id: 2, url: "http://x/b", method: "POST", body: "{}", user: "user-b" },
      { id: 3, url: "http://x/legacy", method: "POST", body: "{}" },
    ];
    localStorage.setItem("kairos-token", jwt("user-b"));
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { flushQueue } = await import("./idb");
    const out = await flushQueue();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("http://x/b");
    expect(out).toEqual({ replayed: 1, failed: 0 });
    expect(rows).toEqual([]);
  });

  it("keeps the queue untouched when nobody is signed in", async () => {
    rows = [{ id: 1, url: "http://x/a", method: "POST", body: "{}", user: "user-a" }];
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { flushQueue } = await import("./idb");
    await flushQueue();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(rows).toHaveLength(1);
  });
});
