# Conexión propia de vidIQ

Preparación local de 10.6 — 2026-09-21. Autenticación real e inspección del catálogo
comprobadas desde el Mac con una clave propia; ver [registro](vidiq-contract-20260921.md).
No desplegada. El worker y la API mantienen su bloqueo del modo real hasta completar
todos los controles del preflight.
No se ejecutó ninguna herramienta de vidIQ.

## Autenticación admitida

La [página oficial de vidIQ MCP](https://vidiq.com/mcp/), consultada el 2026-09-21,
documenta claves API MCP como Bearer y las recomienda, además de admitir OAuth.
La [guía de soporte](https://support.vidiq.com/en/articles/15082430-vidiq-mcp)
describe OAuth y fija el endpoint `https://mcp.vidiq.com/mcp`. Se mantiene ese endpoint.
La nueva opción permite preparar NicheRadar sin registro de cliente OAuth, callback
público ni almacenamiento de refresh tokens. No cambia las políticas de datos o gasto.

Generar una clave propia en [Account Settings → MCP](https://app.vidiq.com/account/settings/mcp).
No reutilizar credenciales del conector de conversación, enviarla por chat ni incluirla
en comandos, capturas o archivos versionados.

Para una comprobación sin guardarla, ejecutar desde una terminal interactiva local:

```sh
uv run nicheradar-vidiq --check-connection --prompt-token
```

La entrada se oculta y solo vive en memoria del proceso. Sin terminal interactiva,
se rechaza la captura para impedir que `getpass` utilice una entrada visible.

Para configuración persistente, usar `NR_VIDIQ_TOKEN` en el `.env` privado con permisos
0600 o en el entorno secreto del servicio worker de Easypanel. La herramienta nunca
escribe credenciales ni modifica servicios; preparar la clave no activa investigación.
Mantener `NR_MODE=synthetic` y la programación pausada durante esta preparación.

## Comprobación explícita

```sh
# Solo presencia local de configuración; ninguna solicitud de red.
uv run nicheradar-vidiq

# Usa la clave configurada y conecta exclusivamente con el endpoint oficial.
uv run nicheradar-vidiq --check-connection
```

La comprobación remota inicializa MCP y consulta `tools/list`, hasta cinco páginas y
250 herramientas, con un límite total de 45 segundos. No usa `tools/call`: no consulta
saldo, canales, videos, outliers, feedback ni funciones de generación. No escribe en
PostgreSQL, guarda respuestas, registra permisos ni habilita trabajos. `tool_calls: 0`
se refiere a esta comprobación; sí hay solicitudes HTTP de protocolo.

La salida solo contiene estados, conteos, nombres reconocidos y huellas SHA-256 de
esquemas de entrada. No reproduce descripciones, instrucciones del servidor, nombres
arbitrarios, errores remotos ni la clave. Reconoce nombres con/sin prefijo `vidiq_` y
declara `missing` o `ambiguous` cuando corresponda; no cambia el mapeo del adaptador.

`connected` indica éxito de la conexión de protocolo. **No valida identidad de cuenta,
tarifas, semántica de campos o condiciones de investigación**. El informe conserva
`pilot_ready: false`. El diagnóstico del dashboard sigue siendo local y de solo lectura:
no ejecuta este comando ni deduce que una clave presente haya sido validada remotamente.

El transporte envía la clave solo al origen HTTPS de vidIQ y no usa proxies del entorno.
No repite llamadas tras errores de autenticación/cuota. Un fallo previo a `tools/call`
certifica que esa herramienta no se envió; un fallo posterior conserva la posibilidad de
cobro y nunca autoriza un reenvío automático.

## Siguiente paso

La clave propia y el catálogo real ya se comprobaron. Se corrigió la traducción de
parámetros de outliers, se registraron los costes anunciados y el worker local ya usa
el adaptador real a través del gateway. Faltan configurar identidad de cuenta,
saldo/ciclo, políticas, presupuesto y alcance del piloto. Este diagnóstico no completa
la tarea 10.6.

`tests/test_vidiq_connection.py` prueba el SDK real con HTTP en memoria: autenticación,
paginación, límites, respuestas ocultas, redirección a otro origen, errores antes/después
del envío y comportamiento del comando sin credenciales. No son pruebas de una cuenta real.
