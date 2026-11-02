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
- `/_stcore/health` se conserva para el `healthcheck` de compose y las sondas.

## Recursos incluidos

HTMX 2.0.4 e Inter 4.0 (con su licencia) viven en `src/nicheradar/web/static/`; las huellas están en
`static/js/VENDOR.md`. No se carga nada de terceros en tiempo de ejecución.

## PWA

Manifiesto, iconos y un service worker que solo guarda los estáticos (nunca páginas con datos); hay una
página sin conexión.

## Pantallas de este corte

Hechas: M9 (lista de subnichos, `/subnichos`) y M10 (ficha del subnicho con inicio de la investigación).
Faltan: Hoy, Nichos con decisiones, iniciar investigación de un nicho, informe y autorizar piloto (resto del
corte 1), y los cortes 2 y 3. La barra inferior muestra «Pilotos» y «Más» desactivados hasta que existan.

## Comprobación visual contra el Figma

```
uv run python scripts/web_preview.py --out /tmp/web-preview
```

Renderiza `/subnichos` y la ficha con datos de ejemplo (`scripts/web_preview_data.py`, sin API real) y guarda
`lista.html`, `ficha.html` y, si hay Chrome (`--chrome RUTA`), `lista.png` y `ficha.png` a 390 px de ancho con
escala 2. Compárense con el Figma M9 (`29:2`) y M10 (`30:2`). Los estados de investigación de la lista son
ilustrativos, como en el Figma. Las rutas `file://` solo existen en esta vista previa. Chrome headless no
baja de 500 px de ventana, por eso la página se mide dentro de un `iframe` de 390 px y se recorta con `sips`
(macOS).
