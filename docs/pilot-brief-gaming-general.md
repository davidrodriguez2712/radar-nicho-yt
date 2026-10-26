# Brief del canal para el piloto `pil_20261026_gaming-general`

Para quien cree el proyecto del canal. Todo sale del dossier `154e5684` y del paquete autorizado
(`package_sha256` `e333f357…dbc78`, vigente hasta **2026-11-09**). Si algo de aquí contradice el
paquete, manda el paquete.

## Qué se va a probar

- Nicho `gaming_general`, formato **largo**, idioma **inglés**. Veredicto del dossier:
  `go_with_conditions`, confianza **baja**. La evidencia no sostiene el nicho amplio: es un
  experimento barato, no una apuesta.
- Acotar a **un subnicho** (historia de juegos, speedruns o análisis de un solo juego) con guion
  de análisis propio. Contenido en plantilla o reutilizado arriesga la monetización.
- Límite: **10 videos**. Presupuesto en efectivo (USD): bajo 12, probable 18, alto 66. La única
  partida es la voz sintética (ElevenLabs Starter, US$6/mes × 3). Lo demás es gratuito.

## Hoja de ruta (14 semanas)

| Fase | Semanas | Salida |
|---|---|---|
| Preparación y subnicho | 2 | Subnicho justificado; 3 canales de referencia con cadencia anotada de 10 videos; guion del video 1 |
| Piloto de 10 videos | 8 | 10 videos publicados; AVD ≥ 18 % en 3; minutos humanos registrados en los 10 |
| Evaluación | 2 | Decisión con datos: seguir, acotar más o cerrar |

Herramientas: DaVinci Resolve gratuito, YouTube Audio Library, ElevenLabs Starter (o voz propia,
gratis). Duda abierta del dossier: si la versión gratuita de DaVinci admite uso comercial.

## Reglas de parada (las que vigila NicheRadar)

| Regla | Hito | Cómo se mide |
|---|---|---|
| `pipeline-s6` | semana 6 | Flujo de punta a punta funcionando |
| `retencion-v10` | video 10 | `avd_pct` ≥ 18 en al menos 3 videos medidos |
| `tiempo-v10` | video 10 | **Manual**: minutos humanos registrados; promedio ≤ 420 por video |
| `politica-s12` | semana 12 | **Manual**: sin aviso pendiente de política de monetización y decisión registrada |

## Qué debe medir y reportar el canal (`channel-report-v1`)

Por video: estado interno (`source_state`), visibilidad, fecha de publicación, `cost_usd` (dinero
gastado de verdad), `machine_minutes` y, tras publicar, `measurement` (`avd_pct`, `views`,
`browse_share_pct`, `subscribers_gained`; ventana de 7 días). Los **minutos humanos** no van en
el reporte v1: llévalos aparte para decidir `tiempo-v10`.

## Incógnitas que el canal debe cerrar

1. Cadencia real de los competidores (la fuente no la daba).
2. Qué permiten los editores de juegos sobre material grabado.
3. Plazo y requisitos para que el canal sea elegible a monetizar.
4. Si la versión gratuita de DaVinci Resolve permite uso comercial.

## Pasos, en orden (los marcados «humano» no los hace Claude)

1. **Humano**: crear el proyecto del canal (id con patrón `canal-[a-z0-9-]{1,40}`, p. ej.
   `canal-gaming-historia`) y decidir el subnicho.
2. **Código, antes de reportar**: añadir la tabla de traducción de estados del canal en
   `src/nicheradar/pilots/translation.py` (`TABLES`). Sin ella, todo estado se traduce a
   `unknown` y el piloto queda a revisión humana. Hace falta la lista de estados del canal.
3. **Humano, producción**: emitir el token del canal
   (`scripts/pilots.py token-issue --channel <id> --label mac`, con el túnel abierto). Se
   imprime una sola vez: guardarlo en el gestor de contraseñas, no en el repo ni el chat.
4. Mac: `scripts/pilots_tunnel.py` y, con `NR_SYNC_URL`/`NR_SYNC_TOKEN` en el entorno,
   `channel_sync.py fetch --channel-dir <canal>`. El paquete sin canal asignado lo recibe el
   primer canal que confirme la entrega.
5. El canal produce y un script propio (solo lectura sobre su base) genera el reporte;
   `channel_sync.py report` lo envía.
6. **Humano**: ante «decisión pendiente», `pilots.py show` y `pilots.py decide`.

Si el 2026-11-09 ningún canal tomó el paquete, vence y hay que autorizar otro.
