const CACHE = "nicheradar-static-v1";
const SHARE = "nicheradar-share-v1";
const SHARED_FILE = "/compartir/imagen/archivo";
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_IMAGE = 5 * 1024 * 1024;
const OFFLINE = "/sin-conexión";
const PRECACHE = [
  OFFLINE,
  "/static/css/app.css",
  "/static/js/htmx.min.js",
  "/static/js/app.js",
  "/static/fonts/InterVariable.woff2",
];

const here = (path) => new URL(path, self.location.origin).href;

// Un POST de «Compartir»: la imagen solo se guarda, en la caché del teléfono y bajo una ruta fija.
async function receiveShare(request) {
  try {
    const form = await request.formData();
    const file = form.get("imagen");
    if (file && typeof file === "object") {
      if (!IMAGE_TYPES.includes(file.type) || file.size > MAX_IMAGE) {
        return Response.redirect(here("/compartir/imagen?aviso=imagen_no_valida"), 303);
      }
      const cache = await caches.open(SHARE);
      await cache.put(SHARED_FILE, new Response(file, { headers: { "Content-Type": file.type } }));
      return Response.redirect(here("/compartir/imagen"), 303);
    }
    const params = new URLSearchParams();
    for (const key of ["title", "text", "url"]) {
      const value = form.get(key);
      if (typeof value === "string" && value) params.set(key, value.slice(0, 2000));
    }
    return Response.redirect(here("/compartir?" + params.toString()), 303);
  } catch (error) {
    return Response.redirect(here("/compartir"), 303);
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE && k !== SHARE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method === "POST" && url.origin === self.location.origin && url.pathname === "/compartir") {
    event.respondWith(receiveShare(request));
    return;
  }
  if (request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/static/")) {
    // Stale-while-revalidate: answer from the cache, refresh it in the background.
    event.respondWith(
      caches.open(CACHE).then((cache) =>
        cache.match(request).then((hit) => {
          const fresh = fetch(request).then((response) => {
            if (response.ok) cache.put(request, response.clone());
            return response;
          });
          if (hit) {
            fresh.catch(() => {});
            return hit;
          }
          return fresh;
        })
      )
    );
    return;
  }
  if (url.pathname === SHARED_FILE) {
    event.respondWith(
      caches.open(SHARE).then((cache) => cache.match(SHARED_FILE)).then((hit) => hit || new Response("", { status: 404 }))
    );
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE)));
  }
});
