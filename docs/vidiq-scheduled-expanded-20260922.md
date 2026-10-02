# Ciclo programado ampliado y reevaluación — 2026-09-22

El segundo ciclo programado real elevó el límite por ejecución a 20 créditos, mantuvo
25 por semana y 100 por ciclo, y volvió a dejar el radar pausado. No hubo compras,
recargas ni reservas sin resolver.

| Medida | Resultado |
| --- | --- |
| Trabajo | `5b76a5f1-6ca9-49c2-bd7c-6e341f741f83` |
| Estado | `partial`; `run_budget_exhausted` |
| Operaciones | 1 búsqueda de canales, 3 publicaciones de canal, 5 saldos |
| Créditos | 20 confirmados |
| Saldo | 165 → 145; 105 renovables y 40 adicionales al final |
| Evidencia | 100 videos, 50 largos y 50 Shorts |
| Backlog | 2 entradas reales, ambas sin puntuación por evidencia insuficiente |

La primera formación de cohortes dejó los 100 videos como `language_unknown`. La release
004 corrigió ese punto heredando únicamente la declaración de idioma del canal retenida,
con evidencia explícita de que el audio del video no fue verificado. Una ejecución desde
caché reutilizó los 100 videos, realizó solo una consulta gratuita de saldo, consumió cero
créditos pagados y trasladó los 100 casos a `relevance_unknown`. Esto separó el problema de
idioma del problema semántico sin modificar el payload original del proveedor.

La calibración de solo lectura probó el modelo ONNX cuantizado fijado sobre esa evidencia.
El proceso amd64 usó 172 MiB de pico y 3,602 segundos. Con umbral 0,35 confirmó 4 videos
largos y 5 Shorts; con 0,40 no confirmó largos y con 0,45 confirmó solo un Short. Un conjunto
controlado adicional situó cinco ejemplos relevantes entre 0,4296 y 0,7253, y cinco ajenos
entre -0,2112 y 0,0743. El corte 0,35 es una configuración inicial conservadora, no una
validación estadística ni una recomendación de nicho.

El tope semanal quedó agotado en 25 créditos. La release 005 puede reevaluar evidencia
retenida sin nuevas llamadas pagadas. La ejecución `b0d29c1b-a539-44d6-970b-9bac3045c9f5`
confirmó 4 largos dentro de la ventana; los 5 Shorts relevantes tenían más de 90 días.
Los cuatro largos quedaron en grupos individuales de ruido, de modo que el snapshot creció
a 8 entradas pero todas permanecen sin puntuación. El worker usaba 128,8 MiB después de
esta ejecución, dentro de su límite de 512 MiB, y el radar quedó pausado.

La calibración de Market Score continúa pendiente: nueve coincidencias semánticas no
garantizan grupos de tamaño suficiente ni referencias reales congelables. Reducir el umbral
de agrupamiento para unir piezas distintas forzaría una conclusión que la evidencia actual
no respalda.

Los datos estructurados están en [vidiq-scheduled-expanded-20260922.json](vidiq-scheduled-expanded-20260922.json).
