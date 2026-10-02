# Ciclo programado vidIQ — 22 de septiembre de 2026

Se observó una ocurrencia creada por el planificador del VPS, sin depender del dashboard
ni del Mac. El informe agregado reproducible está en
[`vidiq-scheduled-20260922.json`](vidiq-scheduled-20260922.json).
La ejecución ampliada posterior y su reevaluación están en
[`vidiq-scheduled-expanded-20260922.md`](vidiq-scheduled-expanded-20260922.md).

## Resultado

| Control | Resultado |
| --- | --- |
| Modo y disparador | `live`, `scheduled` |
| Estado | `partial`, esperado por `run_budget_exhausted` |
| Duración | 4,294 segundos |
| Llamadas | 3 completadas: 2 saldo, 1 búsqueda de canales |
| Créditos | 5 confirmados; 0 reservas inciertas |
| Saldo | 170 antes; 165 después |
| Límites persistidos | 5 por ejecución, 25 por semana, 100 por ciclo |
| Estado final | calendario `live`, radar pausado |

Las siete etapas quedaron confirmadas: planificación, consulta, normalización, cohorte,
métricas, evaluación y backlog. El ciclo creó un nuevo snapshot de ranking con cero
entradas. Es una actualización verificable del backlog y un estado vacío válido: el tope
detuvo el flujo antes de consultar videos, no hubo cohortes ni evidencia para crear
oportunidades, y el sistema no completó el ranking con candidatos artificiales.

La primera prueba de la mecánica programada heredó `mode=synthetic` de la configuración
persistida anterior. Terminó sin llamar al proveedor ni consumir créditos y volvió a
pausar el radar. Se corrigió el modo del calendario mientras seguía pausado y solo entonces
se ejecutó la ocurrencia real descrita aquí.

## Estado operativo

El código real permanece desplegado, pero la programación quedó pausada después de la
observación. La reanudación continua requiere una decisión explícita de presupuesto y de
cobertura: con 5 créditos por ejecución solo se valida una búsqueda de canales y no se
alimenta un backlog de oportunidades con videos. La operación comprobada se documenta en
[live-operation.md](live-operation.md).

Siguen pendientes un modelo local evaluado, referencias reales calibradas, benchmarks
publicitarios, LLM opcional y el cierre del procedimiento futuro de respaldo y conservación.
YouTube API continúa sin configurar. Ninguna de esas dependencias se sustituyó con datos
inventados.
