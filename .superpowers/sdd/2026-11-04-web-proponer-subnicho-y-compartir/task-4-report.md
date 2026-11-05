# Task 4 - Compartir desde Android (M29/M30)

## Estado: DONE_WITH_CONCERNS (ver Preocupaciones)

## Cambios
- `static/manifest.webmanifest`: `share_target` GET (`/compartir`, params title/text/url), sin `files`.
- `web/share.py`: `extract_link` (url > text > title; http(s), hosts conocidos sin esquema o `@handle`; recorte a 500; rechaza NUL/Cc/Cf/RLO) y `classify` (host exacto: tweet = x.com/twitter.com/mobile.twitter.com y `www.`; YouTube = youtube.com/www/m/youtu.be con `parse_input` sobre host+ruta+`v` solamente, para que un tweet enterrado en la query no cuente; userinfo/puerto -> unknown).
- `web/routes_share.py` + `templates/compartir.html`: `GET /compartir` solo lectura, `@shape_guard`, enlace como texto escapado, «Proponer» -> `/subnichos/proponer?q=<quote(enlace, safe="")>`.
- `web/deps.py`: `safe_next` endurecido (ya existia `next` en el login): rechaza `//`, `\`, controles/espacios, >2048; se reconstruye desde path+query (sin esquema, host ni fragmento).
- `app.py`: registra el router. Service worker sin cambios (prueba lo verifica).
- `tests/test_web_share.py` (72 pruebas), RED visto (error de coleccion por falta de `share`), luego verde.

## Figma (M29 60:2, M30 60:21)
- M29 es una pantalla del sistema Android (no se implementa; es la hoja de compartir del SO).
- M30 se copio: titulo «Compartido contigo», chip «Tweet de X», boton «Cancelar», tarjeta «Si compartes otra cosa» con sus 3 lineas y «Compartir nunca crea nada solo: siempre pide tu toque.»
- No implementado a proposito: el boton «Leer tweet» y el texto «Todavia no se leyo...» (la lectura de tweets es otro plan); en su lugar el aviso fijo pedido. Etiquetas de chip «Canal de YouTube», «Video de YouTube», «Enlace no reconocido», «Sin enlace» son mias (Figma solo muestra el caso tweet).

## Validacion
- tests/test_web_share.py + session + assets + proposals_routes: 174 passed.
- ruff check y format: limpios; mypy: sin errores (362 archivos).
- Suite completa: 3098 passed (409 s).

## Suposiciones
- Un enlace de YouTube con forma no soportada (p. ej. /results) -> «No reconocimos ese enlace.»
- Un `next` de login >2048 caracteres cae a `/` (un share absurdamente largo sin sesion pierde el regreso).
- Sin esquema se aceptan hosts conocidos (youtube.com/..., x.com/...) y `@handle` completo; `//evil` y `javascript:` -> none/unknown.

## Preocupaciones
- Pagina con sesion expirada usa el mecanismo existente de `current_session` (303 a /login?next=...).
- M30 muestra «Leer tweet» en Figma; el diseno deberia actualizarse o dejarse para el plan de tweets.
