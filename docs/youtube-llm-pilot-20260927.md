# Piloto real: YouTube y enriquecimiento LLM — 27 de septiembre de 2026

Primera ejecución programada real con YouTube y el enriquecimiento LLM habilitados a la
vez (release `v1-candidate-20260927-009`), tras subir los topes de créditos vidIQ a
25/175/350 (ejecución/semana/ciclo). El radar volvió a pausa automáticamente al terminar.

## Resultado

| Control | Resultado |
| --- | --- |
| Trabajo | `ab282d20-7107-4538-bdb6-2c48a904509c` |
| Estado | `partial`; `run_budget_exhausted` |
| Operaciones | 5 publicaciones de canal, 6 saldos, 2 `videos.list` (YouTube), 16 explicaciones (OpenAI) |
| Créditos vidIQ | 25 confirmados; saldo 185 → 160 |
| Cuota YouTube | 2 unidades confirmadas |
| Gasto LLM | US$0,003044 confirmados; 0 reservas inciertas |
| Cobertura | 301 videos recibidos, 200 procesados, 30 cohortes evaluadas, 14 grupos de ruido |
| Backlog | Creció de 8 a 21 entradas; todas siguen sin puntuación (`insufficient_evidence`) |

## YouTube — evidencia del piloto

El enriquecimiento detectó **46 videos con `different_language`** que vidIQ había
heredado como inglés por idioma del canal — es decir, corrigió activamente supuestos de
idioma incorrectos antes no detectables. También confirmó 14 videos largos como
relevantes por idioma real. Esto valida el propósito del enriquecimiento: mejorar la
confianza del filtro de idioma, no solo agregar metadatos.

## LLM — evidencia del piloto

Verificado con `node scripts/easypanel_stage.mjs read-llm-enrichment` (agregado en esta
release, solo lectura, sin payloads de proveedor):

```json
{"narrative_enrichment_outcomes":{"llm_emphasis_only":16,"deterministic":12},
 "openai_request_states":{"('completed', None)":16}}
```

**16 evaluaciones recibieron enriquecimiento real de `gpt-6-luna`** (narrativa
reordenada y validada), las 16 solicitudes a OpenAI terminaron `completed` sin errores
ni cobros inciertos. El modelo, la tarifa y los límites configurados el 2026-09-27
funcionan en producción con datos reales.

## Estado tras el piloto

- Radar pausado (`radar_paused_after: true`), sin acumular ejecuciones adicionales.
- Ningún backlog quedó puntuado todavía: la fragmentación de cohortes sigue siendo el
  cuello de botella (14 grupos de ruido de 200 procesados), no un problema de YouTube ni
  de LLM.
- Ambos proveedores quedan validados end-to-end con datos reales; la activación deja de
  ser solo configuración y pasa a ser operación comprobada.

## Siguiente paso pendiente

Observar más ciclos para que la calibración semántica tenga suficiente evidencia; no
elevar más los topes hasta decidirlo conscientemente. Ver
[implementation-status.md](implementation-status.md) para el estado agregado.
