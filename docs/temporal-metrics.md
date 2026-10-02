# Métricas temporales y concentración

Implementación de la tarea 6.3, probada con observaciones sintéticas. No se consultan
proveedores para completar el historial: se utiliza únicamente evidencia conservable
que ya esté en la base. La integración real y la calibración siguen pendientes.

## Qué se calcula

El panel temporal se fija con los videos incluidos de publicaciones recientes de la
cohorte actual. Los ejemplos obtenidos solo como outliers no forman ese panel. Se
utilizan las últimas tres fechas distintas disponibles por video, separando formato,
idioma, proveedor, cuenta, operación, versión de normalización, perfil y modo.

- Una observación no permite medir cambio reciente.
- Dos observaciones por cada video permiten medir aumento de vistas y velocidad
  observada: suma de los cambios individuales divididos por sus intervalos reales,
  expresada en vistas/día. No es el promedio desde la publicación.
- Tres observaciones permiten comparar dos velocidades: `(reciente - anterior) /
  anterior`, únicamente con fechas y recuentos comparables y velocidad anterior positiva.

El valor relativo 1 significa un aumento del 100 % de la velocidad observada del panel;
no significa duplicación de vistas acumuladas, rentabilidad ni probabilidad de éxito.
Un valor negativo puede representar desaceleración sin pérdida de vistas acumuladas.
Si un recuento disminuye, se registra revisión a la baja sin atribuir una causa.

La cobertura muestra qué fracción de los videos tiene tres fechas disponibles. No se
descartan silenciosamente videos con historia incompleta para calcular una tendencia
solo sobre los que permanecen. Al añadirse nuevos videos puede dejar de ser calculable
hasta reunir su historial. La tendencia describe el panel actual, no todo el nicho.

## Comparabilidad y límites

`observed-panel-v1` admite una tolerancia inicial del 10 % en la duración de los dos
intervalos por video. También exige que las fechas de los distintos videos estén
alineadas dentro de esa tolerancia del intervalo más corto. Las velocidades usan los
segundos reales: la tolerancia no transforma una semana en un día.

`NR_TREND_INTERVAL_TOLERANCE` configura ese margen entre 0 y 0,25; cero exige igualdad.
`NR_TREND_LOOKBACK_DAYS` limita la búsqueda a 90 días inicialmente, entre 1 y 90.
La conservación del proveedor puede permitir menos historia; estas variables no la
extienden. Son controles iniciales versionados, pendientes de revisión con el piloto.

La fecha utilizada es `observed_at`; cuando el proveedor no la ofrece, la normalización
usa la fecha original de consulta. Reutilizar caché no cambia esa fecha. Respuestas
repetidas con la misma fecha cuentan una vez; contradicciones en esa fecha bloquean la
comparación, en vez de elegir un recuento arbitrario. No se utilizan fechas futuras ni
observaciones posteriores a la evidencia actual de cada video.

## Conservación y visualización

La evaluación enlaza todas las fuentes históricas consultadas, incluidas las respuestas
duplicadas que sustentan la consistencia de una fecha. Su plazo es como máximo el de la
fuente más restrictiva. La limpieza invalida la explicación y los scores si expira una
fuente necesaria; no se conserva la tendencia dentro de checkpoints o logs.

El dashboard muestra el cambio relativo, o el motivo por el que no es calculable, junto
con intervalos y cobertura. El componente `T` recibe la métrica observada solo cuando
existe; sin una referencia calibrada sigue sin producir un score numérico. La comparación
histórica de posiciones en el ranking es otra tarea (7.3) y permanece pendiente.

## Concentración

`cohort-metrics-v2` calcula HHI como la suma de las cuotas de vistas al cuadrado y top-5
share como la cuota acumulada de los cinco canales con más vistas en la muestra.
Se requieren al menos dos canales con recuentos conocidos y un total positivo. Con
menos de cinco canales, top-5 share es 1 por construcción; no demuestra por sí solo
concentración del mercado. Las cuotas no representan toda la población de YouTube.

El componente de concentración normalizado conserva la fórmula existente: con `n > 1`,
`100 × (1 - (HHI - 1/n) / (1 - 1/n))`. No mide directamente dificultad de entrada.

Verificación: `tests/test_temporal_history.py`, pruebas previas de métricas y batería
integral. No se requiere una migración nueva para este bloque.
