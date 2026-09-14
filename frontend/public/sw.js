// Service worker do Ritmind — casca offline. Regras:
//  - /api/* NUNCA é cacheado (dado do atleta vem sempre da rede).
//  - assets do Next (/_next/static, hasheados) = cache-first (imutáveis).
//  - navegação = network-first, cai pra casca cacheada quando offline.
const CACHE = "ritmind-v1";
const SHELL = [
  "/inicio/",
  "/entrar/",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // dado do atleta: sempre rede, nunca cache
  if (url.pathname.startsWith("/api/")) return;

  // assets imutáveis do Next: cache-first
  if (url.pathname.startsWith("/_next/")) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }))
    );
    return;
  }

  // navegação: rede primeiro, casca cacheada como reserva offline
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).catch(() => caches.match(req).then((hit) => hit || caches.match("/inicio/")))
    );
    return;
  }

  // resto same-origin: cache com atualização em segundo plano
  e.respondWith(
    caches.match(req).then((hit) => {
      const net = fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
