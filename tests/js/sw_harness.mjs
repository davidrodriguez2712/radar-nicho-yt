// Carga sw.js en un ámbito de service worker falso y ejecuta un escenario; imprime JSON.
import { readFileSync } from "node:fs";
import vm from "node:vm";

const [swPath, scenario] = process.argv.slice(2);
const store = new Map();
const cacheFor = (name) => ({
  put: async (key, response) => {
    store.set(`${name} ${key}`, { type: response.headers.get("Content-Type"), body: Buffer.from(await response.arrayBuffer()) });
  },
  match: async (key) => {
    const hit = store.get(`${name} ${typeof key === "string" ? key : new URL(key.url).pathname}`);
    return hit ? new Response(hit.body, { headers: { "Content-Type": hit.type } }) : undefined;
  },
  delete: async (key) => store.delete(`${name} ${key}`),
  addAll: async () => {},
});
const caches = { open: async (name) => cacheFor(name), keys: async () => [...new Set([...store.keys()].map((k) => k.split(" ")[0]))], delete: async () => true };
const listeners = {};
const self = { location: { origin: "https://app.test" }, addEventListener: (type, fn) => { listeners[type] = fn; }, skipWaiting() {}, clients: { claim() {} } };
vm.runInNewContext(readFileSync(swPath, "utf8"), { self, caches, fetch: async () => new Response("red"), Response, Request, URL, URLSearchParams, FormData, Blob, File, console });

async function dispatch(request) {
  let answered = null;
  listeners.fetch({ request, respondWith: (promise) => { answered = promise; } });
  if (answered === null) return { handled: false };
  const response = await answered;
  return { handled: true, status: response.status, location: response.headers.get("Location"), type: response.headers.get("Content-Type") };
}

const post = (form, path = "/compartir") => new Request(`https://app.test${path}`, { method: "POST", body: form });
const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0]);
const out = {};
if (scenario === "image") {
  const form = new FormData();
  form.append("imagen", new File([png], "a.png", { type: "image/png" }));
  out.post = await dispatch(post(form));
  out.cached = [...store.keys()];
  out.get = await dispatch(new Request("https://app.test/compartir/imagen/archivo"));
} else if (scenario === "too_big" || scenario === "gif") {
  const form = new FormData();
  const file = scenario === "gif"
    ? new File([new Uint8Array(10)], "a.gif", { type: "image/gif" })
    : new File([new Uint8Array(5 * 1024 * 1024 + 1)], "a.png", { type: "image/png" });
  form.append("imagen", file);
  out.post = await dispatch(post(form));
  out.cached = [...store.keys()];
} else if (scenario === "link") {
  const form = new FormData();
  form.append("title", "Mira");
  form.append("text", "https://x.com/autor_x/status/123");
  out.post = await dispatch(post(form));
} else if (scenario === "other") {
  out.post = await dispatch(post(new FormData(), "/otra"));
  out.missing = await dispatch(new Request("https://app.test/compartir/imagen/archivo"));
}
process.stdout.write(JSON.stringify(out));
