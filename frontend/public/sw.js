// Kairos Service Worker — shell cache + selective API data cache.
// Navigations: network-first (fresh HTML + current chunk hashes always win online;
// cache is offline fallback only). Static assets: stale-while-revalidate.
// API GETs: network-first; the cache is an offline fallback only, and is keyed per signed-in user
// (the Bearer token's `sub`) so one user's data is never served to another. Write queue lives in idb.ts.
// Sign-out posts {type:"LOGOUT"}, which deletes every cache.
// Registered in production only (app-shell.tsx) — in dev a cached shell fights HMR.

const SHELL = "kairos-shell-v2";
// v2: v1 held unkeyed, cache-first entries that any user could be served.
const DATA = "kairos-data-v2";

// API paths worth caching offline (GET only)
const DATA_PATTERNS = ["/briefs", "/assets", "/elicitation"];

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== SHELL && k !== DATA).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

// `sub` of the JWT the page sent, or null when there is none to key the cache on.
function bearerSub(request) {
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return null;
  try {
    const payload = auth.slice(7).split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload)).sub || null;
  } catch {
    return null;
  }
}

// One entry per (user, URL): the Cache API keys by URL alone, so the user goes into the key.
function cacheKey(url, sub) {
  return new Request(`${self.location.origin}/__api-cache/${encodeURIComponent(sub)}/${encodeURIComponent(url)}`);
}

// Sign-out: forget every cached page and API response, whatever user they belonged to.
self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "LOGOUT") {
    e.waitUntil(caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k)))));
  }
});

self.addEventListener("fetch", (e) => {
  const { request } = e;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // The API is the only cross-origin fetch the app makes, so any non-frontend
  // origin is API traffic — works for :8000 in dev and real domains in prod.
  const isApi = url.origin !== self.location.origin || url.pathname.startsWith("/api/");

  if (isApi) {
    const shouldCache = DATA_PATTERNS.some((p) => url.pathname.includes(p));
    const sub = bearerSub(request);
    if (!shouldCache || !sub) return; // uncached API calls, and anything not tied to a user, pass through
    const key = cacheKey(request.url, sub);
    e.respondWith(
      fetch(request)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(DATA).then((cache) => cache.put(key, copy));
          }
          return res;
        })
        .catch(() =>
          caches.open(DATA).then((cache) => cache.match(key)).then((cached) => cached ?? Response.error()),
        ),
    );
    return;
  }

  // Page navigations: network-first. Serving a cached HTML shell here is what
  // breaks the app — after any rebuild/deploy the chunk hashes change, the stale
  // shell references dead chunks, and the client hard-reloads into the same cache
  // (infinite refresh loop). Cache is only a fallback when the network is down.
  if (request.mode === "navigate") {
    e.respondWith(
      fetch(request)
        .then((res) => {
          if (res.ok) caches.open(SHELL).then((cache) => cache.put(request, res.clone()));
          return res;
        })
        .catch(() => caches.match(request).then((cached) => cached ?? caches.match("/briefs"))),
    );
    return;
  }

  // Static assets (hashed, immutable): stale-while-revalidate
  e.respondWith(
    caches.open(SHELL).then((cache) =>
      cache.match(request).then((cached) => {
        const fresh = fetch(request).then((res) => {
          if (res.ok) cache.put(request, res.clone());
          return res;
        });
        return cached ?? fresh;
      }),
    ),
  );
});
