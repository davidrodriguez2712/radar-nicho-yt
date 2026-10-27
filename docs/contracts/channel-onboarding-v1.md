# channel-onboarding-v1

Estado: **aprobado por el propietario el 2026-10-26; implementado solo en la parte que no depende del
nicho** (tabla de estados, permiso `--upload` y estos documentos). Primer caso: `canal-speedrun-ledger`.
Pasos operativos: [`../runbook-canal-piloto.md`](../runbook-canal-piloto.md). Mapa del ecosistema:
[`../ecosistema-youtube.md`](../ecosistema-youtube.md). Contratos hermanos:
[`pilot-package-v1.md`](pilot-package-v1.md), [`channel-report-v1.md`](channel-report-v1.md) y
[`channel-report-v2.md`](channel-report-v2.md).

## Qué es

La lista de cosas que deben existir para que un canal pueda recibir un piloto, **quién hace cada una**
(el propietario o el agente) y **cómo se comprueba**. Es un contrato de proceso, no un archivo que viaje por
la API: no añade claves a `pilot-package-v1` (que rechaza las desconocidas) ni a `channel-report-v*`. Lo que
el canal necesita saber sale **del paquete y del dossier**; el propietario no vuelve a escribirlo.

Principio: **el propietario hace solo lo que ningún agente puede hacer** (identidad, autorización
interactiva, aprobaciones puntuales). Todo lo demás lo hace y lo documenta el agente.

## Decisiones del propietario (2026-10-26)

| # | Tema | Decisión | Consecuencia |
|---|---|---|---|
| A | Quién sube los videos | **El agente, por API** (A2) | Hace falta el permiso `youtube.upload` y pasar la auditoría de la API (ver «Subida por API») |
| B | Minutos humanos | **Automatizar al máximo y aceptar el riesgo de política** (B2) | El dossier calcula ~420 min humanos por video y política `alto`; la regla `politica-s12` sigue vigilando y la decide el propietario |
| C | Aprobación de operaciones en producción | **Aprobación única para este piloto** | Emitir el token del canal, `fetch` y `report` por el túnel no piden otra aprobación. **No** cubre otros pilotos, despliegues ni cambios de esquema |

El alcance de C es `pil_20261026_gaming-general` y su canal. Cualquier otra operación sobre producción
(despliegues, migraciones, borrar datos) sigue pidiendo aprobación explícita.

## Identidad del canal (primer caso)

| Dato | Valor |
|---|---|
| `channel_id` en NicheRadar | `canal-speedrun-ledger` (patrón `^canal-[a-z0-9-]{1,40}$`; también es el nombre de la carpeta) |
| Canal de YouTube | `@SpeedrunLedger` · `UCx60iZtPE3Tfzh0_Pn1ZC7g` · <https://www.youtube.com/channel/UCx60iZtPE3Tfzh0_Pn1ZC7g> |
| Carpeta | `~/Programming/youtube-project/canal-speedrun-ledger` (repo propio) |
| Piloto | `pil_20261026_gaming-general` (`gaming_general`, formato `long`, idioma `en`), vigente hasta 2026-11-09 |
| Proyecto de Google Cloud | `canal-gaming-yt` (app «Canal Gaming Sync», en producción) |

## Reparto: humano y agente

| # | Paso | Quién | Comprobación |
|---|---|---|---|
| 1 | Crear el canal de YouTube (cuenta de Google, nombre, handle) | **Humano** | Hecho 2026-10-26 |
| 2 | Verificar el teléfono del canal (videos de más de 15 min) | **Humano** | `checks.phone_verified` (declarado por el propietario: ninguna API lo confirma) |
| 3 | Añadir `youtube.upload` en Google Auth Platform → Acceso a los datos | **Humano** (consola de Google) | `youtube_upload_scope` |
| 4 | Clic de autorización OAuth con la cuenta dueña del canal (`youtube_oauth.py authorize --upload`) | **Humano** (interactivo, una vez) | `youtube_oauth` y `youtube_upload_scope` |
| 5 | Solicitar la auditoría de la API de YouTube | **Humano** envía el formulario con su cuenta; el agente redacta la solicitud | `api_audit` |
| 6 | Crear la carpeta del canal, manifiesto, `.nicheradar/` y exportador de reporte | **Agente** | `check` de la carpeta |
| 7 | Tabla de traducción de estados (`translation.py`) | **Agente** | Pruebas de `test_channel_onboarding.py` |
| 8 | Emitir el token del canal, abrir el túnel, `fetch` y confirmar la entrega | **Agente** (cubierto por la aprobación C) | `package_delivered` |
| 9 | Elegir el subnicho y el calendario de videos, investigar guiones y fuentes | **Agente** | Dossier y brief |
| 10 | Investigar derechos del material visual | **Agente** | `rights_cleared` (**BLOQUEANTE**) |
| 11 | Voz de referencia y visuales del nicho | **Agente** | `voice_ref`, `visual_assets` |
| 12 | Producir, subir, medir y reportar cada video | **Agente** | Reporte `channel-report-v1` |
| 13 | Decidir `seguir` o `cerrar` ante «decisión pendiente» | **Humano** | `pilots.py decide` |
| 14 | Resolver las reglas manuales `tiempo-v10` y `politica-s12` | **Humano** | `pilots.py show` |

La parte del propietario son los pasos 2 a 5, 13 y 14: pocos minutos y ninguno repetido por video.

## Qué se deriva del paquete y del dossier (el propietario no lo escribe)

| Dato | Fuente | Uso en el canal |
|---|---|---|
| Idioma `en`, formato `long` | `niche.language`, `niche.format` del paquete | Guion y voz en inglés; videos largos; el reporte es `channel-report-v1` |
| Presupuesto y `max_videos` (10) | `budget` | Tope de gasto real y de videos; más videos publicados que `max_videos` pasa a revisión humana |
| Reglas de parada | `stop_rules` | `pipeline-s6`, `retencion-v10` (AVD ≥ 18 % en 3 videos), `tiempo-v10`, `politica-s12` |
| Cadencia y preparación | `planned_cadence_per_week`, `preparation_days` | Calendario de los 10 videos; plazo para dejar el canal listo |
| Herramientas y precios | `dossier.tools` | Voz sintética (ElevenLabs) y edición; se sustituyen si el canal copia el pipeline de `canal-historias` y lo justifica |
| Competidores y referencias | `dossier.competitors` | Tipologías de video y cadencia de referencia |
| Flujo de producción y riesgos | `dossier.production_flow`, `automation_map`, `policy_risk` | Qué pasos se automatizan y cuáles llevan control de calidad |
| Incógnitas | `verdict.unknowns` | Lista de investigación del agente (derechos, monetización, licencia de DaVinci) |

## Lista de estados y traducción

El canal copia la máquina de estados de `canal-historias` (receta del foundry). NicheRadar la traduce
con la **misma tabla** (`TABLES['canal-speedrun-ledger']`):

| `stage` | `source_state` |
|---|---|
| `in_production` | `IDEA_CRUDA`, `IDEA_VALIDADA`, `GUION_BORRADOR`, `GUION_APROBADO`, `GUION_FINAL`, `ASSETS_LISTOS`, `RENDER_COMPLETO`, `QA_APROBADO`, `EMPAQUETADO` |
| `awaiting_human` | `VEREDICTOS_PENDIENTES` |
| `uploaded` | `PROGRAMADO`, y `PUBLICADO` con `visibility = private` |
| `published` | `PUBLICADO` con `visibility = public` |
| `measuring` | `EN_MEDICION` |
| `killed` | `KILL` |
| `blocked` | `BLOQUEADO_POLITICA`, `FALLO_QA` |

Un estado fuera de la tabla se traduce a `unknown`: el reporte se acepta con advertencia y el piloto queda
para revisión humana. Si el canal cambia su vocabulario, se separa su tabla y se añade una prueba.

## `checks[]` del canal

Los define el canal (ver `channel-report-v1`). Para este canal, el exportador debe informar al menos:

| `id` | Cuándo es `ok` | Quién lo cambia |
|---|---|---|
| `youtube_oauth` | Existe el token y `youtube_oauth.py check` responde a la Data API y a Analytics. `expires_at` es `null` (app en producción) | Agente |
| `youtube_upload_scope` | El token tiene `youtube.upload` (`check` informa `upload_scope: true`) | Agente |
| `phone_verified` | El propietario lo confirmó | Humano |
| `api_audit` | La auditoría de la API fue aprobada (sin eso, los videos subidos por API quedan privados) | Humano informa, agente registra |
| `rights_cleared` | La investigación de derechos concluye que hay una fuente de material visual viable ([`../pilot-speedrun-ledger-rights.md`](../pilot-speedrun-ledger-rights.md)) | Agente |
| `voice_ref` | Hay voz de referencia probada | Agente |
| `visual_assets` | Hay biblioteca visual del nicho | Agente |

## Permisos de OAuth

| Permiso | Para qué | Cuándo |
|---|---|---|
| `youtube.readonly` | Leer datos del canal | Siempre |
| `yt-analytics.readonly` | Leer métricas (AVD, vistas, tráfico) | Siempre |
| `youtube.upload` | Subir videos | Solo con `--upload` (decisión A2). Escritura: nunca por defecto |

`youtube_oauth.py authorize --upload` pide los tres; si Google no concede `youtube.upload`, el script falla y
no guarda el token. Un token solo de lectura sigue siendo válido para medir. Ver
[`../guia-oauth-youtube-permanente.md`](../guia-oauth-youtube-permanente.md).

## Subida por API (decisión A2): restricciones

- **Auditoría obligatoria.** Según la documentación de YouTube, los videos subidos con `videos.insert` desde
  proyectos de API no verificados creados después del 2020-07-28 quedan **restringidos a privado** hasta que el
  proyecto pasa una auditoría de cumplimiento ([`videos.insert`](https://developers.google.com/youtube/v3/docs/videos/insert)).
  `canal-gaming-yt` es nuevo, así que **hasta aprobar la auditoría el agente prepara y sube en privado y la
  publicación pública no es automática**. No se da por verificado cómo se desbloquea un video ya subido: el
  agente lo comprueba con el primer video antes de apoyarse en ello.
- **Modo de publicación del canal:** `api` cuando `api_audit` sea `ok`; `studio` (el propietario sube desde
  Studio un paquete listo) mientras no lo sea. El reporte distingue los dos con `visibility`.
- **Cuota.** El límite diario de la API acota las subidas por día (ver `ecosistema-youtube.md` §10). Un solo
  canal con cadencia semanal no se acerca.
- **Compuerta de cumplimiento.** El canal conserva su `compliance-gate` previo a publicar. Aceptar el riesgo de
  política (B2) no desactiva divulgación de contenido sintético ni derechos.

## Compuertas humanas (mínimas y por qué existen)

1. **Autorización OAuth (una vez).** Google exige un clic interactivo del dueño del canal.
2. **Auditoría de la API (una vez).** La envía el titular del proyecto de Google.
3. **`seguir`/`cerrar` ante «decisión pendiente».** NicheRadar propone, no decide.
4. **`tiempo-v10` y `politica-s12`.** Reglas manuales: ninguna API mide los minutos humanos ni los avisos de
   monetización.
5. **Cualquier operación fuera del alcance de C** (despliegue, migración, otro piloto).

No hay compuerta humana por video. El agente aplica el control de calidad y el `compliance-gate`.

## Criterios de aceptación

Un canal está **listo para producir** cuando:

- La carpeta del canal existe, con manifiesto y `.nicheradar/`, y no contiene secretos en el repo.
- `translate('<channel_id>', …)` no devuelve `unknown` para ningún estado de su máquina.
- `youtube_oauth.py check` responde a las dos APIs; con `--upload`, informa `upload_scope: true`.
- Existe el token del canal en NicheRadar y `channel_sync.py fetch` guardó el paquete en `inbox/` con la huella
  verificada y la entrega confirmada.
- `rights_cleared` es `ok`. **Sin esto no se produce ningún video.**
- El primer reporte `channel-report-v1` es aceptado sin advertencias de estado.

## Si falla

| Situación | Efecto | Respuesta |
|---|---|---|
| `rights_cleared` no llega a `ok` | No se produce el primer video | El agente propone un subnicho alternativo o cierra el piloto; la decisión es del propietario |
| Google no concede `youtube.upload` | `authorize --upload` falla, sin token | Añadir el permiso en Acceso a los datos y repetir |
| Auditoría de la API sin aprobar | Los videos subidos por API quedan privados | Modo `studio`; el agente prepara y el propietario sube |
| Token OAuth inválido (`invalid_grant`) | Sin métricas ni subidas | Check `youtube_oauth` en `ok: false`; el agente avisa; el propietario repite el clic |
| Paquete vencido (2026-11-09) | `fetch` ya no lo entrega | Autorizar otro piloto (aprobación del propietario) |
| Estado desconocido en el reporte | `stage = unknown`, advertencia | Corregir la tabla de traducción |

## Qué NO cubre

- No cambia `pilot-package-v1` ni `channel-report-v*`.
- No decide el nicho ni el veredicto de la investigación.
- No crea cuentas, canales ni proyectos de Google: eso es del propietario.
- No cubre otro canal: cada canal repite este contrato con su `channel_id`.
