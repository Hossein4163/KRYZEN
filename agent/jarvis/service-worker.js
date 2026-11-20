const CACHE = "kryzen-offline-v3";
const OFFLINE = "/offline.html";

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.add(OFFLINE)));
});
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith("kryzen-offline-") && name !== CACHE) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.mode !== "navigate" || event.request.method !== "GET" ||
      url.origin !== self.location.origin || !["/", "/index.html"].includes(url.pathname)) return;
  event.respondWith(fetch(event.request).catch(async () => {
    return (await caches.match(OFFLINE, {cacheName: CACHE})) || Response.error();
  }));
});
