# Verificación de conexión y contrato vidIQ — 2026-09-21

Conexión directa desde el Mac al endpoint oficial `https://mcp.vidiq.com/mcp`, con
clave API propia de NicheRadar. Inicialización MCP aceptada y catálogo de **59
herramientas** recibido. No se ejecutó `tools/call`, no se consultó saldo ni contenido
y no se inició el piloto. No se modificaron el VPS, las políticas o el presupuesto.

La clave se trasladó del archivo de ejemplo al `.env` privado con permisos 0600;
`.env.example` quedó sin ella. Ningún valor secreto forma parte de este registro.

## Contrato anunciado

Los nombres esperados están disponibles sin ambigüedades. Costes anunciados por
las descripciones de `tools/list`, **no recibos de cargos ni mediciones de consumo**:

| Operación | Herramienta | Créditos anunciados por llamada |
| --- | --- | ---: |
| Saldo | `vidiq_balance` | 0 |
| Búsqueda de canales | `vidiq_channel_search` | 5 |
| Publicaciones | `vidiq_channel_videos` | 5 |
| Outliers | `vidiq_outliers` | 5 |
| Keywords | `vidiq_keyword_research` | 5 |

Huellas SHA-256 de los esquemas de entrada, serializados con claves ordenadas:

| Herramienta | SHA-256 |
| --- | --- |
| `vidiq_balance` | `a6e59a0e9cc2caac9d3c507e367aa670ade389ec327faa9adb78114ce6267e71` |
| `vidiq_channel_search` | `44539c2401fe46d05b7cfdec727f27f0292ba0ba054b9b3801e36ccdce5d2beb` |
| `vidiq_channel_videos` | `ef97ee1291abf520b9cda630a1c501fbbd0ca6181051495de9f7f8c49387af23` |
| `vidiq_outliers` | `6d18aaf312a51d3fff624f2d34cd4f3638859b7c4a7bc39fc3379b216561d5de` |
| `vidiq_keyword_research` | `b4f4ca5660a84a246384417d1a30729225f2e028ebef8123710a9e5de0de299e` |

## Corrección derivada de la inspección

El descubrimiento utiliza `query` y `videoFormat`; outliers exige `keyword` y
`contentType`. El adaptador ahora traduce esos dos campos antes de enviar la llamada.
Así mantiene el tema y separa `long`/`short`. No modifica los parámetros originales
que utiliza el gateway para la caché. Si se reciben ambos nombres con valores
distintos, rechaza la solicitud antes de enviarla. El campo interno `family` tampoco
se envía al proveedor. Cinco casos nuevos prueban ambas traducciones, nombres
nativos, alias iguales y conflictos sin envío, usando respuestas inventadas.

Publicaciones mantiene `popular=false` explícito: el valor por defecto anunciado
por vidIQ es `true`. Búsqueda de canales acepta los filtros usados de idiomas,
suscriptores y límite. Esta inspección verifica contratos, no calidad de resultados.

## Dependencias para el worker y piloto

- El esquema de saldo no aporta el comienzo del ciclo ni una identidad de cuenta:
  deben configurarse/verificarse antes de usarlo para presupuestar.
- Publicaciones y outliers no aportan un idioma de audio verificado. El filtro de
  idioma de outliers describe títulos. Esos videos siguen con idioma desconocido;
  la conexión no habilita cohortes confirmadas en inglés por sí sola.
- Las categorías externas de canales no equivalen a las familias internas del radar.
  No se debe traducir una clasificación amplia a un nicho confirmado automáticamente.
- El coste anunciado no confirma el cargo de una solicitud concreta. El adaptador
  conserva `actual=None` para investigación; siguen pendientes las confirmaciones
  individuales de consumo y la conciliación de resultados inciertos.
- Faltan la conexión del worker, políticas de conservación/derivados, configuración
  presupuestaria y autorización del piloto. No se consultó ni actualizó el saldo.

La validación remota queda registrada aquí. El preflight de API/dashboard continúa
leyendo configuración local: no usa este Markdown como un permiso ni convierte una
clave presente en autorización para ejecutar investigación. 10.6 sigue abierta.

Verificación posterior: 341 pruebas aprobadas con PostgreSQL aislado y respuestas
sintéticas, Ruff/formato/mypy correctos y OpenSpec válido. Dos advertencias conocidas
de dependencias de pruebas. Ninguna prueba ejecutó herramientas reales de vidIQ.

## Actualización del piloto — 2026-09-22

El contrato se ejercitó después en un [piloto real aislado](vidiq-pilot-20260922.md).
Dos saldos gratuitos rodearon una búsqueda de canales: 175 → 170 créditos. La diferencia
confirma el coste fijo de 5 para esa llamada exitosa, por lo que el adaptador registra
`actual=5` en ese caso. Fallos posteriores al envío siguen quedando como cobro incierto.
El worker y las políticas manuales funcionaron mediante el gateway; 10.6 quedó completada.
