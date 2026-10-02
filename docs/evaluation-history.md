# Evaluaciones y posiciones históricas

En **Backlog → detalle → Historial y decisión** puedes seleccionar dos versiones
entre las últimas 20 evaluaciones. La API privada también permite comparar versiones
anteriores concretas mediante
`GET /api/v1/opportunities/{id}/comparison?previous_version=1&current_version=2`.
Las dos deben pertenecer a esa oportunidad, y la anterior debe preceder a la actual.
El detalle incluye la comparación de las dos últimas versiones y los últimos 20
cortes de clasificación del perfil y modo de la última evaluación.

## Qué distingue

- **Datos:** cambios en métricas y evidencia temporal conservada.
- **Método:** fórmula, referencias, rúbrica, pesos y parámetros del análisis.
  Si cambian, se muestran los valores anteriores y actuales, pero no un delta que
  los presente como directamente comparables. También se avisa si cambia el conjunto
  de componentes disponibles: un componente desconocido no equivale a cero.
- **Supuestos:** receta, perfil, publicidad o revisión de relevancia.
- **Posición relativa:** desplazamiento por otros candidatos cuando la evaluación
  propia permanece igual. Si también cambia la evaluación propia, se informa de
  ambos cambios sin atribuir una causa única.

Las etiquetas y el texto generado por IA no constituyen cambios de métricas o método.
Las diferencias describen lo guardado, no prueban causalidad ni predicen rentabilidad.
No se reconstruyen valores vencidos ni se inventa una comparación para la primera versión.

## Cómo se guardan los puestos

La migración `0007` añade `ranking_snapshots` y `ranking_entries`. El worker guarda
un corte al cerrar la etapa de backlog, en la misma transacción que su confirmación.
Un reintento de esa ejecución devuelve el mismo corte; un bloqueo por perfil serializa
la secuencia. No se reconstruyen retrospectivamente clasificaciones anteriores a esta
funcionalidad: no se conoce el estado histórico completo de sus competidores.

Cada corte usa la última evaluación por oportunidad del mismo perfil y modo,
incluyendo la ejecución que está cerrando y las anteriores terminadas. Se excluyen
evaluaciones intermedias de otros trabajos; una ejecución parcial solo participa
después de alcanzar backlog. Una evaluación actual sin puntuación o caducada nunca
se sustituye por una versión antigua mejor puntuada.

Los grupos separan formato, idioma, modo, método/referencias, componentes disponibles
y perfil de Creator Fit. Shorts no desplazan vídeos largos. Los empates comparten
puesto con clasificación `1, 1, 3`. Los descartados y las evaluaciones sin puntuación
no reciben puesto. Un grupo puede contener un solo candidato: ser primero en él no
prueba una buena oportunidad. Los filtros y las páginas de la lista no renumeran los
puestos guardados; el orden visual general del backlog no es una clasificación común.

Las decisiones posteriores no reescriben el pasado; se reflejan en el siguiente corte.
Por eso el panel muestra fecha y número de corte y no los llama posiciones en vivo.
La clasificación no autoriza gastos ni sustituye los límites de recursos o confianza.

## Conservación

Las entradas no copian puntuaciones ni textos de evidencia: apuntan a sus evaluaciones
y guardan puesto, ámbito de comparación y estado de revisión. El plazo del corte es
el más corto entre todas las evaluaciones incluidas. Si vence o se retira cualquiera,
se eliminan **todas** las entradas de ese corte y se conserva solo su cabecera invalidada.
Es una política conservadora: incluso otra posición es un dato derivado del competidor
retirado. La lectura comprueba también los plazos y el estado de sus evaluaciones.

## Verificación y límites

`tests/test_ranking.py` comprueba datos/métodos simultáneos, supuestos, cobertura,
caducidad de un competidor, ausencia de reemplazos antiguos, perfiles/modos, empates,
reintentos concurrentes y API privada. `test_pipeline.py` verifica que el worker
guarda cortes sin crear puestos para resultados no calibrados;
`test_dashboard_navigation.py` recorre la comparación desde el panel.

Las pruebas usan PostgreSQL temporal y datos sintéticos, sin llamadas pagadas.
La migración y esta versión de las imágenes aún no están desplegadas en Contabo.
