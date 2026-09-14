// Kairos Service Worker — shell cache + selective API data cache.
// Navigations: network-first (fresh HTML + current chunk hashes always win online;
// cache is offline fallback only). Static assets: stale-while-revalidate.
// API GETs: cache-first-with-revalidate for offline reads. Write queue lives in idb.ts.
// Registered in production only (app-shell.tsx) — in dev a cached shell fights HMR.

const SHELL = "kairos-shell-v2";
const DATA = "kairos-data-v1";

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

self.addEventListener("fetch", (e) => {
  const { request } = e;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // The API is the only cross-origin fetch the app makes, so any non-frontend
  // origin is API traffic — works for :8000 in dev and real domains in prod.
  const isApi = url.origin !== self.location.origin || url.pathname.startsWith("/api/");

  if (isApi) {
    const shouldCache = DATA_PATTERNS.some((p) => url.pathname.includes(p));
    if (!shouldCache) return; // pass through uncached API calls
    e.respondWith(
      caches.open(DATA).then((cache) =>
        cache.match(request).then((cached) => {
          const fresh = fetch(request)
            .then((res) => {
              if (res.ok) cache.put(request, res.clone());
              return res;
            })
            .catch(() => cached ?? Response.error());
          return cached ?? fresh;
        }),
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
