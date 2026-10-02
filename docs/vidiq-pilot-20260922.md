# Piloto real vidIQ — 22 de septiembre de 2026

Piloto manual, personal y aislado de NicheRadar. Se ejecutó desde el Mac contra el
endpoint MCP oficial con la clave propia ya configurada. PostgreSQL vivió únicamente
durante la ejecución y se eliminó al terminar. El informe agregado reproducible está en
[`vidiq-pilot-20260922.json`](vidiq-pilot-20260922.json).

## Límites y resultado

| Control | Resultado |
| --- | --- |
| Tope por operación, ejecución, semana y ciclo | 5 créditos |
| Conservación configurada | 7 días; la base temporal se eliminó al terminar |
| Llamadas | 3 completadas: 2 saldo, 1 búsqueda de canales |
| Créditos | 5 confirmados; 0 reservas inciertas |
| Saldo | 175 antes; 170 después |
| Compra incremental en USD | US$0; no se atribuyó el coste de la suscripción |
| Tiempo total del pipeline | 6,748 segundos |
| Estado | `partial`, esperado por `run_budget_exhausted` |

La primera comprobación observó 135 créditos renovables y 40 adicionales. Después de
la búsqueda quedaron 130 renovables y 40 adicionales. La diferencia de 5 coincide con
el coste registrado por el gateway. La renovación informada es el 4 de octubre de 2026
a las 01:49:11 UTC. Para este piloto único se usó como inicio operativo el 4 de septiembre,
inferido un mes antes; no se presenta como fecha confirmada por el contrato MCP.

## Cobertura y relevancia

La rotación eligió la familia interna `culture`. La búsqueda devolvió 10 canales y el
proveedor informó 10.000 coincidencias posibles. Los 10 declararon inglés entre sus
idiomas de contenido, pero el proveedor no confirma idioma de audio.

Ninguna categoría externa coincidió literalmente con la clave interna `culture`. Este
resultado no prueba que los canales sean irrelevantes, pero sí impide usar la categoría
del proveedor como confirmación automática de la familia. El informe no conserva nombres,
identificadores ni texto de consulta.

Los formatos `long` y `shorts` quedaron `not_queried_budget_cap`: obtener publicaciones
u outliers habría requerido otra llamada de 5 créditos. No hubo videos, cohortes ni
evidencia suficiente para calibrar puntuaciones.

## Decisión de calibración y siguiente ciclo

Las referencias y rúbricas permanecen `uncalibrated`; no se congelaron referencias.
Esto satisface la salida prevista para evidencia insuficiente de la tarea 10.7. Ejecutar
un ciclo programado requiere desplegar esta versión, registrar la política `scheduled`
y asignar un nuevo presupuesto semanal explícito. No se reutilizará la base temporal ni
se simulará un presupuesto nuevo para eludir el límite de este piloto.

