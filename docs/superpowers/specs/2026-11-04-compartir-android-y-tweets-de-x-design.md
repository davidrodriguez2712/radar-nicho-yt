# Entrada por «Compartir» (Android) y lectura de tweets de X — diseño

Estado: **borrador para revisión del propietario** (2026-11-04). Cubre el «subproyecto C» del descubrimiento de subnichos
(`docs/superpowers/specs/2026-10-31-subniche-discovery-youtube-design.md`) y lo une a la pantalla «Proponer subnicho» (3d del
corte 3). Pantallas en Figma `JmBvlfNURrV226WOZLuCEz`, página «M · Móvil», fila «2b»: M29 a M34 (más M25 a M28 de
«Proponer subnicho» y la nota de sesión en M22).

## Objetivo

Que el propietario, desde su teléfono **Android**, comparta un enlace desde X o YouTube a NicheRadar y siga el mismo flujo que
si lo hubiera pegado a mano: propuesta → aprobación → medición → investigación → informe → piloto. Los tweets suelen traer
**texto e imagen con texto** y pueden mencionar **varios canales**.

## Decisiones del propietario (2026-11-04)

1. Solo Android (PWA instalada, `share_target`). iPhone queda fuera.
2. Lectura de tweets: **servicio gratuito de terceros (FxTwitter) como principal y compartir la imagen como respaldo.** La API
   oficial de X (de pago por uso, unos 0,005 USD por post) solo si el principal deja de funcionar y con su aprobación.
3. Compartir nunca crea nada solo: pide un toque en cada paso que lee, gasta o cambia estado.
4. Acceso: **solo la contraseña de la app** (`NR_DASHBOARD_PASSWORD`). La autenticación Basic del proxy de Easypanel se quita
   (acción del propietario en Easypanel; no se toca producción desde el código).
5. **Sesión de 5 días** en el teléfono (hoy 12 horas).

## Flujo

1. En X o YouTube: Compartir → «NicheRadar» (M29). La app abre `GET /compartir?title=&text=&url=`.
2. «Compartido contigo» (M30): detecta el tipo y lo muestra. Canal o video de YouTube → botón «Proponer» (va a M25 relleno).
   Tweet de X → botón «Leer tweet». Un enlace no reconocido → mensaje claro, sin acción. Si no hay sesión: login y regreso.
3. Tweet: el servidor lee el tweet (M31, estado «En cola»; no se llama a proveedores desde una petición web). Extrae el texto,
   las imágenes y, con el modelo de lenguaje con visión, los canales mencionados.
4. «Canales encontrados» (M32): cada canal con casilla, de dónde salió (texto o imagen) y su resolución: `@handle` o enlace de
   YouTube → «resuelto en YouTube»; solo un nombre → «buscar por nombre (100 unidades)» y no se busca hasta que el propietario lo
   pida; sin coincidencia → «no encontrado» (sin marcar). El propietario marca los que quiere.
5. «Proponer N canales» → una propuesta por canal, con origen `lead` y el canal como canal semilla (M34 y luego M27/M28, ya
   diseñados). Aprobar cada propuesta gasta cuota de búsqueda y es un paso aparte.
6. Respaldo: si el tweet no se puede leer, compartir la imagen (mantener pulsada) lleva a «Imagen recibida» (M33) → «Leer
   imagen» → mismo paso 4.

## Arquitectura

- **Manifiesto:** `share_target` con `method: "GET"`, `action: "/compartir"`, parámetros `title`, `text`, `url`. Para imágenes,
  `share_target` con `method: "POST"`, `enctype: "multipart/form-data"` y `files` solo para `image/png`, `image/jpeg`,
  `image/webp`; el service worker recibe el POST, guarda el archivo temporalmente (caché del navegador, nunca en el servidor
  hasta que el propietario toque «Leer imagen») y redirige a `GET /compartir/imagen`. Cuidado: el service worker hoy solo
  cachea `/static`; el cambio se limita a esa ruta y se prueba.
- **Ruta `/compartir`** (GET, solo lectura): extrae el enlace de `url` o, si falta, del primer enlace de `text` (Android a veces
  pone el enlace en `text`); reutiliza `parse_input` (`subniche_discovery/inputs.py`) para clasificar; no llama a ningún
  servicio ni escribe nada. El POST que sí actúa lleva CSRF, como todos los de la web.
- **Lector de tweets:** una interfaz `TweetReader` con una implementación `FxTwitterReader` (host fijo `api.fxtwitter.com`,
  `GET /{usuario}/status/{id}`, con `id` solo dígitos; sin seguir redirecciones a otros hosts; tiempo de espera de 10 s; tamaño
  de respuesta acotado) y otra, de pago, que se podría añadir sin tocar el resto. Salida mínima: texto, URLs de imágenes
  (solo del dominio de medios de X, descargas acotadas a 5 MB y 4 imágenes) y autor.
- **Extractor de canales:** el modelo de lenguaje (el mismo adaptador Anthropic de la propuesta; modelo con visión) recibe el
  texto y las imágenes como **datos no confiables** y devuelve solo una lista cerrada de menciones (`@handle`, enlace de
  YouTube o nombre), máximo 10, validada contra patrones estrictos. Nada de lo que diga el tweet se ejecuta.
- **Resolución:** `@handle` o enlace → la API de YouTube (`channels.list`, 1 a 2 unidades). Un nombre sin enlace **no** se busca
  solo (`search.list` cuesta 100 unidades): queda «sin resolver» hasta que el propietario lo pida.
- **Asíncrono:** leer un tweet o imagen crea un trabajo (cola del worker), igual que «Proponer»: la web no llama a proveedores
  desde la petición. Idempotencia por clave firmada con el HMAC de la sesión.
- **Sesión:** `SESSION_SECONDS` pasa de 12 horas a 5 días. Rotar `NR_SERVICE_TOKEN` sigue invalidando todas las sesiones.
- **API nueva** (en el plan de API de 3d): lectura de tweet, estado, canales encontrados y alta de propuestas con origen
  `lead`; todo con el token de servicio.

## Seguridad

- Texto e imágenes de X son de terceros: se escapan al mostrarlos, nunca se interpretan como instrucciones ni se usan como
  consultas sin validar; las cifras de ingresos del tweet son solo pistas y no se guardan como datos.
- Anti-SSRF: solo se consulta el host fijo del lector y los medios de X; el `id` del tweet se valida con `fullmatch` de dígitos.
- Costos acotados: tope de tweets leídos por día (por definir en el plan, valor inicial 20) y de imágenes por tweet (4).
- Sesión larga: una cookie copiada sirve 5 días; mitigación: contraseña larga y aleatoria, límite de intentos de acceso y
  HTTPS. Al quitar la Basic Auth del proxy, la contraseña de la app es la única barrera: debe ser aleatoria de al menos 32
  caracteres.
- El servicio de terceros puede cambiar o desaparecer: el lector es reemplazable y el respaldo por imagen no depende de él.

## Fuera de alcance

iPhone; ejecutar sin abrir la app (atajos con credencial en el teléfono); leer hilos completos (solo el tweet compartido);
leer videos de X; usar la API oficial de X (queda como alternativa futura aprobada); guardar el contenido del tweet más allá del
trabajo (se guardan los canales resueltos y la URL del tweet como origen).

## Riesgos y casos a probar

1. Tweet borrado, privado o de cuenta protegida: «no se pudo leer» y se ofrece el respaldo con imagen.
2. Texto del tweet con instrucciones al modelo («ignora lo anterior…»): no cambia el resultado.
3. Un tweet con 30 menciones o una imagen enorme: se acota a 10 menciones y 5 MB.
4. Enlaces de X con parámetros (`?s=20`), `twitter.com`, `mobile.twitter.com` y `x.com/i/status/…`.
5. Compartir sin sesión: login y regreso al mismo enlace compartido.
6. Doble toque en «Leer tweet» o «Proponer»: un solo trabajo.
7. Mención duplicada (mismo canal en texto e imagen): una sola entrada.
8. Hipótesis ya existente para ese canal semilla: se informa como duplicado, no como error.

## Decisiones pendientes

1. Tope diario de tweets leídos (valor inicial propuesto: 20).
2. Si se quiere una pista visible del tweet en la propuesta (por ejemplo «Origen: tweet de @usuario») además del origen `lead`.
