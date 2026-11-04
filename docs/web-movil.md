# Web móvil de NicheRadar

Interfaz móvil (FastAPI + Jinja2 + HTMX, paquete `src/nicheradar/web/`) que reemplaza al dashboard de
Streamlit en el mismo dominio. Habla con la API privada igual que el dashboard; no accede a la base.

## Variables

| Variable | Uso |
|---|---|
| `NR_DASHBOARD_UI` | `streamlit` (por defecto) o `web`. Elige qué interfaz sirve la imagen del dashboard |
| `NR_API_URL`, `NR_SERVICE_TOKEN`, `NR_DASHBOARD_PASSWORD` | Las mismas que usa el dashboard |

## Cambiar y volver atrás

Cambiar: fijar `NR_DASHBOARD_UI=web` en la app del dashboard y reiniciarla. Volver atrás: quitar la
variable (o ponerla en `streamlit`) y reiniciar, o desplegar la imagen anterior. No hay migraciones ni
datos propios, así que el retroceso no pierde nada. El cambio en producción requiere la aprobación del propietario.

## Sesión y seguridad

- Cookie firmada de 12 horas, con la clave derivada del token de servicio.
- CSRF en todos los formularios `POST`; límite de intentos de acceso (una sola clave, la app es de un propietario).
- CSP sin recursos externos; las páginas con datos llevan `Cache-Control: no-store`.
- Salir solo borra la cookie: las sesiones no se pueden revocar en el servidor, así que una cookie copiada sigue válida hasta 12 h. Rotar `NR_SERVICE_TOKEN` invalida todas las sesiones.
- El proxy debe enviar `X-Forwarded-Proto: https` para que la cookie lleve la marca `Secure` (verificarlo al desplegar).
- htmx no guarda copias de páginas (`historyCacheSize: 0`): no quedan datos ni el token CSRF en el teléfono.
- `/_stcore/health` se conserva para el `healthcheck` de compose y las sondas.

## Recursos incluidos

HTMX 2.0.4 e Inter 4.0 (con su licencia) viven en `src/nicheradar/web/static/`; las huellas están en
`static/js/VENDOR.md`. No se carga nada de terceros en tiempo de ejecución.

## PWA

Manifiesto, iconos y un service worker que solo guarda los estáticos (nunca páginas con datos); hay una
página sin conexión.

## Pantallas del corte 1

| Pantalla | Ruta | API que usa |
|---|---|---|
| Hoy (M1, M14 parcial) | `/` | `/market/niches`, `/flow-research`, `/pilots`, `/subniches`; cada tarjeta degrada sola si su fuente falla |
| Nichos (M2) y decisión | `/nichos`, `POST /nichos/decidir` | `/market/niches` (hasta 200), `/flow-research` (últimos 100), `/market/niches/{etiqueta}/decisions` |
| Iniciar investigación (M8) | `/nichos/investigar?etiqueta=&formato=`, `POST` | `/market/niches/{etiqueta}`, `POST /flow-research` |
| Informe (M3, M11) | `/informes/{id}` | `/flow-research/{id}` (dossier v1, v2 y v3; v1/v2 con aviso; subnicho con aviso de confianza y fecha) |
| Autorizar piloto (M4, M12) | `/pilotos/autorizar?informe=`, `POST` | `/flow-research/{id}`, `/pilots` (canales ocupados), `POST /pilots` |
| Subnichos (M9, M10) | `/subnichos`, `/subnichos/{slug}`, `POST /subnichos/{slug}/investigar` | `/subniches`, `/subniches/{slug}`, `POST /flow-research` |

Todas las pantallas de datos son `GET` protegidos por sesión; todo `POST` exige CSRF (salvo `/login`).

### Rulings del plan

1. La etiqueta del nicho viaja por query (`?etiqueta=`), no por ruta, porque la API de mercado no admite etiquetas con `/`.
2. «Descartar» solo aparece para nichos de backlog (no subnichos).
3. Autorizar un piloto no pide cadencia, preparación ni receta.
4. `authorized_by` es un valor fijo.
5. La pestaña Pilotos se activa en el corte 2a; «Más» sigue desactivada hasta el corte 3.

### Límites conocidos

- `/market/niches`, `/flow-research` y `/pilots` se leen con tope de 100 a 200 registros y sin paginar: con más, la web ve los más recientes y lo avisa (por ejemplo, «Puede haber investigaciones más antiguas que no se ven; el botón Investigar podría repetir una»).
- Etiquetas con `/` en el nombre del nicho: la API de mercado las rechaza (limitación de su ruta); la web no las puede abrir.
- Un cuerpo de la API con forma inesperada (campos que faltan, `NaN`, tipos incorrectos) en cualquier `GET` de pantalla o en los `POST` que redibujan una pantalla (autorizar piloto, iniciar investigación) muestra un 503 en español («formato inesperado»); en un fragmento HTMX es un aviso pequeño con estado 200. Las cifras no finitas se ven como «—» y una fecha sin zona horaria se lee como UTC.
- Autorizar: «Canal nuevo» ignora el nombre escrito (no se envía `target_channel`); «Usar el canal que escribo» lo envía. El presupuesto mostrado es el del informe y no cambia con el tope de videos.
- Si la API cae, cada pantalla muestra su mensaje en español con 503 (o 200 en fragmentos HTMX).

### Lo que no se muestra a propósito

Porque la API no entrega el dato o el diseño lo difiere: Fit, Demanda y Volumen de un nicho; el idioma en la lista de nichos (y su filtro); Cadencia, Preparación y Receta al autorizar; la barra de proporción por etapa del informe; «Descartar» en subnichos; «Más» (corte 3). No se inventa ningún valor para estos huecos.

### Pruebas transversales

`tests/test_web_smoke_screens.py` recorre las rutas de los cortes 1 y 2a (incluidas las cinco pestañas del piloto, las confirmaciones y el cierre) con texto hostil en todas las cadenas, con la API caída, con cuerpos mal formados (cada campo reemplazado por `null`, texto, número, `NaN`, infinito, listas y objetos vacíos), con fechas sin zona horaria, y comprueba que no haya orígenes de terceros, código en línea, CSP distinto entre rutas ni `POST` sin CSRF que toque la API (también los de pilotos), y que un `POST` con CSRF en un estado no permitido no escriba nada.


## Pantallas del corte 2a (pilotos)

| Pantalla | Ruta | API que usa |
|---|---|---|
| Lista de pilotos (M5) | `/pilotos?filtro=todos\|activos\|bloqueo\|cerrados` | `GET /pilots?limit=100` (con `valid_until`, `delivered_at` y `channel`, campos aditivos de la lista) |
| Panel (M6) con Resumen, Preparación (M7), Videos, Reglas e Historial | `/pilotos/{id}?pestana=…`; `/pilotos/{id}/preparacion` redirige (303) a la pestaña | `GET /pilots/{id}`; la pestaña Videos además `GET /pilots/{id}/videos` (endpoint nuevo del corte 2a) |
| Seguir o cerrar | `/pilotos/{id}/decidir?accion=seguir\|cerrar`, `POST` | `GET /pilots/{id}`, `POST /pilots/{id}/decision` |
| Cancelar | `/pilotos/{id}/cancelar`, `POST` | `GET /pilots/{id}`, `POST /pilots/{id}/cancel` |
| Resumen de cierre | `/pilotos/{id}/cierre` | `GET /pilots/{id}/closing-summary` (texto, tope 256 KiB) |
| Hoy (M14 parcial) | `/` | las tarjetas de pilotos enlazan al panel; los informes ya con piloto se excluyen |

Los `POST` validan CSRF, el id y la nota localmente, releen el piloto y solo entonces escriben; la decisión
sale de la ruta y el actor lo fija el servidor. Tras una acción se vuelve al panel con un aviso
(`?aviso=`, claves fijas).

### Lo que el corte 2a omite a propósito

- La frase de postura editorial, la URL del canal y la emisión de tokens (se hace por línea de comandos).
- El plazo de preparación y la cadencia: el contrato del paquete no tiene esos campos, así que no se muestran ni se calculan.
- Las fechas sin una base real; las que se muestran van rotuladas «tentativa».

### Límites del corte 2a

- `GET /pilots` se lee con tope de 100: con exactamente 100 la lista y Hoy avisan de que puede haber más. Los videos, reglas y eventos se muestran hasta un tope fijo por pestaña, también con aviso.
- Un id de piloto con `%2F` no llega a la ruta: responde 404 por defecto.
- Una zona horaria de configuración inválida cae a UTC en vez de romper la pantalla.

### Corte 2b: calibración (M13) y pilotos en calibración (M14)

- Pestaña **Calibración** del panel: aparece solo si el paquete del piloto trae un dossier v3; solo ella lee `GET /flow-research/{id}` (el dossier) y `GET /pilots/{id}/videos`. Si el dossier o los videos no se pueden leer, la pestaña lo dice y el resto del panel sigue.
- La calibración se calcula al leer, en la web, y es una sugerencia en texto («Pasa a régimen»): el servidor no evalúa nada y no hay botones nuevos.
- El criterio de salida `max_minutes_per_video` es **inclusivo**: un video lo cumple con `human_minutes <= max`. La racha cuenta los últimos videos consecutivos que cumplen; un video sin medir (`null` o un valor inválido: negativo, no finito o no entero) la corta; un cero medido es válido y cuenta («0 min»).
- Las horas de preparación del dossier son un plan: se rotulan «Preparación del canal (hecha)» solo con el piloto en ejecución, con decisión pendiente o cerrado; antes se rotulan «(prevista)» y las horas de calibración dicen «(incluye preparación prevista)».
- Nunca se muestra «0 min» por datos sin medir: se dice «Aún sin minutos medidos» (el total de la API suma solo los medidos). La etiqueta del método sale de `human_minutes_method` de los videos («estimado (método X)»; varios métodos, «métodos mezclados»). Hasta que exista el productor de minutos, en producción todos los videos aparecen «sin medir».
- Hoy: tarjeta «N pilotos en calibración» con la racha y el último video, solo para pilotos activos con calibración legible; mira como máximo 5 pilotos (tres lecturas cada uno) y avisa «y N más».

## Comprobación visual contra el Figma

```
uv run python scripts/web_preview.py --out /tmp/web-preview
```

Renderiza Subnichos (lista y ficha), Hoy, Nichos, Investigar, Informe v3, Autorizar y, del corte 2a, Pilotos, Piloto (Resumen), Preparación y Confirmar con datos de ejemplo
(`scripts/web_preview_data.py`, sin API real) y guarda `lista`, `ficha`, `hoy`, `nichos`, `investigar`,
`informe`, `autorizar`, `pilotos`, `piloto`, `preparacion` y `confirmar` como `.html` y, si hay Chrome (`--chrome RUTA`), como `.png` a 390 px de ancho con
escala 2. Compárense con el Figma M9 (`29:2`) y M10 (`30:2`) y los demás marcos del archivo. Los estados de investigación de la lista son
ilustrativos, como en el Figma. Las rutas `file://` solo existen en esta vista previa. Chrome headless no
baja de 500 px de ventana, por eso la página se mide dentro de un `iframe` de 390 px y se recorta con `sips`
(macOS).
