/* STUDY-BUDDY service worker (UX-04).
 * Cache-first for static assets (CSS/JS/images/fonts); network-first with
 * cache fallback for flashcard/quiz page shells so study decks work offline.
 * Sync of deck progress back to the server happens when online (deferred;
 * see the offline_banner() macro in templates/partials/states.html).
 * Versioned cache name so deploys invalidate cleanly.
 */
const CACHE = "studybuddy-static-v1";
const STATIC_ASSETS = [
  "/static/manifest.json",
  "/static/css/tokens.css",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

const isStaticAsset = (url) =>
  url.pathname.startsWith("/static/") ||
  url.pathname === "/static/manifest.json";

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // never cache third parties

  if (isStaticAsset(url)) {
    // Cache-first: static assets are versioned/busted by filename conventions.
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((res) => {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
            return res;
          })
      )
    );
    return;
  }

  // Page shells (flashcards/quizzes): network-first, fall back to cached shell.
  if (url.pathname.startsWith("/flashcards") || url.pathname.startsWith("/quiz")) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
          return res;
        })
        .catch(() => caches.match(request))
    );
  }
});
