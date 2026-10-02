# Enriquecimiento con YouTube Data API

YouTube complementa candidatos ya descubiertos por vidIQ. No ejecuta búsquedas temáticas:
la etapa toma IDs de video retenidos, los agrupa de 50 en 50 y llama únicamente a
`videos.list(part=snippet,contentDetails,statistics)`.

## Datos y precedencia

- YouTube puede completar título, descripción, fecha, vistas, duración e idioma declarado.
- El idioma `defaultAudioLanguage` tiene precedencia sobre una inferencia heredada del canal.
- La clasificación long/Shorts y las métricas exclusivas de vidIQ permanecen en su fuente.
- vidIQ y YouTube comparten la identidad canónica `youtube` para el mismo ID; las
  observaciones, solicitudes, costes y políticas siguen separadas por proveedor.
- Las evaluaciones enlazan las dos observaciones cuando usan campos complementarios.
- La duración no se usa por sí sola para declarar que un video es Short.

La etapa está entre consulta y normalización. Guarda un recibo después de cada lote y usa
la caché común; un reinicio no repite una respuesta confirmada. Si se agota el límite de
llamadas o cuota, el trabajo continúa como parcial con la evidencia de vidIQ. Fallos de
autenticación, cuota remota o cobro incierto requieren atención y no generan un bucle.

## Configuración

La clave pertenece a un proyecto propio de Google Cloud con YouTube Data API v3 habilitada.
Una suscripción de Google AI Pro no es una credencial de esta API.

```dotenv
NR_YOUTUBE_API_KEY=<secreto>
NR_YOUTUBE_AUTH_SCOPE=personal-youtube-project
NR_YOUTUBE_CONNECTION_VALIDATED_AT=<fecha ISO-8601 de la comprobación>
NR_YOUTUBE_LIVE_ENABLED=true
NR_YOUTUBE_QUOTA_PER_RUN=2
NR_YOUTUBE_QUOTA_PER_WEEK=10
NR_YOUTUBE_QUOTA_PER_MONTH=40
NR_YOUTUBE_MAXIMUM_VIDEOS=100
```

Los valores son límites del radar y no intentan representar la cuota total del proyecto.
Cada `videos.list` cuesta una unidad según la documentación verificada el 23 de septiembre
de 2026. El límite mensual se aplica con el calendario `America/Lima`; Google conserva su
propio límite diario y puede rechazar una llamada antes que el radar.

El diagnóstico local no usa red por defecto:

```bash
uv run nicheradar-youtube
```

La comprobación explícita consume una unidad y no guarda el video ni muestra su contenido:

```bash
uv run nicheradar-youtube --check-video <VIDEO_ID_PUBLICO>
```

El campo `validated_at` de la salida se registra como
`NR_YOUTUBE_CONNECTION_VALIDATED_AT`. La clave se coloca en el entorno secreto de API y
worker para que el preflight y la ejecución vean la misma configuración; nunca en
`.env.example`, argumentos o logs.

Con todos los valores en el `.env` privado, la configuración remota acotada es:

```bash
node scripts/easypanel_stage.mjs configure-youtube-paused
node scripts/easypanel_stage.mjs activate-live-db
```

El primer comando actualiza solo API y worker y conserva la pausa. El segundo registra las
políticas idempotentes, comprueba el preflight programado y también conserva la pausa.

## Políticas y conservación

Antes de activar se registran para proveedor `youtube`, operación `videos`, tipo
`metadata`, los usos `query`, `storage`, `history`, `derived` y, para el calendario,
`scheduled`. El plazo operativo es siete días y el preflight rechaza cualquier plazo
superior a 30 días.

La política general de YouTube exige actualizar o eliminar datos no autorizados antes de
30 días y mostrar la información más reciente disponible. Las condiciones adicionales para
métricas derivadas no se presumen aceptadas por este proyecto:

- [videos.list y cuota](https://developers.google.com/youtube/v3/docs/videos/list)
- [políticas de desarrolladores](https://developers.google.com/youtube/terms/developer-policies)
- [condiciones para métricas derivadas](https://developers.google.com/youtube/terms/derived-metrics-policy)

La activación mantiene el radar pausado. Primero se valida configuración y políticas; una
ejecución manual acotada constituye un piloto separado.
