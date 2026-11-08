/* Same-origin only. Pre-caches static assets, NEVER HTML: index.html carries the per-install POST token, so pages are network-only
   (offline gets a built-in token-free notice) and no text/html or Cache-Control: no-store response is ever stored. Same-origin only (incl. local HTTPS); never caches /api/ or HTML.
   Local alerts: clients may postMessage {type:"notify", title, body}; there is NO push server and no keys. */
var C = "clipping-hub-shell-v35", SHELL = ["/app.css", "/app.js", "/sky-air-tokens.css", "/motion.css", "/logo.svg?v=lg1030", "/theme-init.js"];
var OFFLINE = '<!doctype html><meta charset="utf-8"><title>Clipping Hub</title><p>Clipping Hub is offline. Start the local server and reload.</p>';
self.addEventListener("install", function (e) { e.waitUntil(caches.open(C).then(function (c) { return c.addAll(SHELL); })); self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(caches.keys().then(function (ks) { return Promise.all(ks.filter(function (k) { return k !== C; }).map(function (k) { return caches.delete(k); })); })); self.clients.claim(); });
function storable(r) {
  // Never cache partial media (206) — a cached 206 breaks subsequent full/range playback.
  var t = (r.headers.get("Content-Type") || "").toLowerCase(), cc = (r.headers.get("Cache-Control") || "").toLowerCase();
  return r.status === 200 && t.indexOf("text/html") === -1 && cc.indexOf("no-store") === -1;
}
self.addEventListener("fetch", function (e) {
  var u = new URL(e.request.url);
  // /samples/ is Range-served media: network-only (never cache 206 or full mp4 in SW).
  if (e.request.method !== "GET" || u.origin !== self.location.origin || u.pathname.indexOf("/api/") === 0 || u.pathname.indexOf("/samples/") === 0) return;
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(function () { return new Response(OFFLINE, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } }); }));
    return;
  }
  e.respondWith(fetch(e.request).then(function (r) { if (storable(r)) { var k = r.clone(); caches.open(C).then(function (c) { c.put(e.request, k); }); } return r; })
    .catch(function () { return caches.match(e.request).then(function (m) { return m || Response.error(); }); }));
});
self.addEventListener("message", function (e) {
  var d = e.data || {};
  if (d.type !== "notify" || !d.title) return;
  e.waitUntil(self.registration.showNotification(String(d.title).slice(0, 80), {
    body: String(d.body || "").slice(0, 160),
    tag: String(d.tag || "clipping-hub"),
    renotify: !!d.renotify
  }));
});
self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) { if (list[i].url.indexOf(self.registration.scope) === 0) return list[i].focus(); }
    if (clients.openWindow) return clients.openWindow("/approvals");
  }));
});
