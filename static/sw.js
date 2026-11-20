const CACHE_NAME = "gtracing-pwa-v8-exportacao";
const STATIC_ASSETS = [
  "/",
  "/static/style.css?v=6",
  "/static/app.js?v=10",
  "/static/classification-export.js?v=1",
  "/static/html2canvas-1.4.1.min.js",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/icon-maskable-192.png",
  "/static/icon-maskable-512.png",
  "/static/apple-touch-icon.png",
  "/static/logo-gt.jpeg"
];

// Install: Cache critical assets
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

// Activate: Clean up old caches
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Network-first for APIs, Stale-while-revalidate for static files
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // Skip non-GET
  if (e.request.method !== "GET") return;

  // Network-first for /api/ calls
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }

  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() => caches.match("/")));
    return;
  }

  // Stale-while-revalidate for static shell and files
  e.respondWith(
    caches.match(e.request).then((cached) => {
      const fetchPromise = fetch(e.request).then((networkRes) => {
        if (networkRes && networkRes.status === 200) {
          const resClone = networkRes.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(e.request, resClone));
        }
        return networkRes;
      }).catch(() => cached);

      return cached || fetchPromise;
    })
  );
});
