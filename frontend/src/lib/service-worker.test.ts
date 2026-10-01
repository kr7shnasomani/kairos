import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

// M10: the service worker is a plain script, so run it against a fake worker scope.
const SRC = readFileSync(join(process.cwd(), "public", "sw.js"), "utf8");
const jwt = (sub: string) => `h.${btoa(JSON.stringify({ sub }))}.s`;

type Handler = (e: unknown) => void;

function load() {
  const handlers: Record<string, Handler> = {};
  const stores = new Map<string, Map<string, Response>>();
  const store = (n: string) => stores.get(n) ?? stores.set(n, new Map()).get(n)!;
  const caches = {
    keys: async () => [...stores.keys()],
    delete: async (n: string) => stores.delete(n),
    match: async () => undefined,
    open: async (n: string) => ({
      match: async (r: Request) => store(n).get(r.url)?.clone(),
      put: async (r: Request, res: Response) => { store(n).set(r.url, res); },
    }),
  };
  const self = {
    location: { origin: "https://app.test" },
    skipWaiting: () => {},
    clients: { claim: async () => {} },
    addEventListener: (t: string, h: Handler) => { handlers[t] = h; },
  };
  const fetchMock = vi.fn();
  new Function("self", "caches", "fetch", SRC)(self, caches, fetchMock);
  const get = (auth: string | null) => {
    const req = new Request("https://api.test/briefs/", { headers: auth ? { Authorization: auth } : {} });
    let out: Promise<Response> | undefined;
    handlers.fetch({ request: req, respondWith: (p: Promise<Response>) => { out = p; } });
    return out;
  };
  return { handlers, stores, fetchMock, get };
}

describe("service worker API cache", () => {
  let sw: ReturnType<typeof load>;
  beforeEach(() => { sw = load(); });

  it("goes to the network first even when a cached copy exists", async () => {
    sw.fetchMock.mockResolvedValue(new Response("fresh"));
    await (await sw.get(`Bearer ${jwt("a")}`))!.text();
    sw.fetchMock.mockResolvedValue(new Response("fresher"));
    expect(await (await sw.get(`Bearer ${jwt("a")}`))!.text()).toBe("fresher");
  });

  it("falls back to the cache only when the network fails, and only for the same user", async () => {
    sw.fetchMock.mockResolvedValue(new Response("a-data"));
    await (await sw.get(`Bearer ${jwt("a")}`))!.text();
    await Promise.resolve();
    sw.fetchMock.mockRejectedValue(new TypeError("offline"));
    expect(await (await sw.get(`Bearer ${jwt("a")}`))!.text()).toBe("a-data");
    const other = await sw.get(`Bearer ${jwt("b")}`);
    expect((await other!).type).toBe("error");
  });

  it("does not touch requests with no user to key on", () => {
    expect(sw.get(null)).toBeUndefined();
    expect(sw.get("Bearer not-a-jwt")).toBeUndefined();
  });

  it("deletes every cache on LOGOUT", async () => {
    sw.stores.set("kairos-data-v2", new Map());
    sw.stores.set("kairos-shell-v2", new Map());
    let done: Promise<unknown> | undefined;
    sw.handlers.message({ data: { type: "LOGOUT" }, waitUntil: (p: Promise<unknown>) => { done = p; } });
    await done;
    expect([...sw.stores.keys()]).toEqual([]);
  });
});
