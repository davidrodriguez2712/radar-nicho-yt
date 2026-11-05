(function () {
  var button = document.getElementById("leer-imagen");
  if (!button) return;
  var SHARE = "nicheradar-share-v1", FILE = "/compartir/imagen/archivo";
  var status = document.getElementById("estado-imagen");
  var generic = button.dataset.generic;
  function fail(text) { status.textContent = text || generic; button.disabled = false; }
  function link(text, href) {
    var anchor = document.createElement("a");
    anchor.textContent = text;
    anchor.href = href;
    status.appendChild(document.createTextNode(" "));
    status.appendChild(anchor);
  }
  // Sin imagen en la caché: mensaje claro en lugar de una imagen rota.
  caches.open(SHARE)
    .then(function (cache) { return cache.match(FILE); })
    .then(function (hit) {
      if (hit) return;
      var missing = document.getElementById("sin-imagen"), preview = document.getElementById("vista-imagen");
      if (missing) missing.hidden = false;
      if (preview) preview.hidden = true;
      button.hidden = true;
    })
    .catch(function () {});
  function forget() { return caches.open(SHARE).then(function (c) { return c.delete(FILE); }); }
  button.addEventListener("click", function () {
    button.disabled = true;
    status.textContent = button.dataset.sending;
    caches.open(SHARE)
      .then(function (cache) { return cache.match(FILE); })
      .then(function (hit) { if (!hit) throw new Error("sin_imagen"); return hit.blob(); })
      .then(function (blob) {
        return fetch("/compartir/imagen/leer", {
          method: "POST", credentials: "same-origin", body: blob,
          headers: { "Content-Type": blob.type, "X-CSRF-Token": button.dataset.csrf, "X-Nonce": button.dataset.nonce },
        });
      })
      .then(function (response) { return response.json().then(function (data) { return [response.ok, data, response.status]; }); })
      .then(function (pair) {
        var next = pair[1] && pair[1].next;
        if (pair[0] && typeof next === "string" && /^\/lecturas\/[0-9a-f-]{36}$/.test(next)) {
          return forget().then(function () { location.assign(next); });
        }
        fail(pair[1] && pair[1].error);
        if (pair[2] === 401) link(button.dataset.login, "/login?next=/compartir/imagen");
        else if (pair[2] === 403) status.textContent = button.dataset.reload;
      })
      .catch(function () { fail(); });
  });
  var cancel = document.getElementById("cancelar-imagen");
  if (cancel) cancel.addEventListener("click", function (event) {
    event.preventDefault();
    forget().then(function () { location.assign("/subnichos"); });
  });
})();
