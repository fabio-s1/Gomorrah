// Service worker do Gomorrah: cacheia só arquivos estáticos (dados financeiros nunca vão para o cache).
const V = "gomorrah-v1";
const ASSETS = ["/static/style.css", "/static/icons/icon-192.png", "/offline"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(V).then((c) => c.addAll(ASSETS)));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== V).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin) return;
  if (r.mode === "navigate") {
    e.respondWith(fetch(r).catch(() => caches.match("/offline")));
  } else if (u.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(r).then((hit) => {
      const net = fetch(r).then((res) => { const c = res.clone(); caches.open(V).then((x) => x.put(r, c)); return res; }).catch(() => hit);
      return hit || net;
    }));
  }
});
