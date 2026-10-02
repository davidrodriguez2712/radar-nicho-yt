## 1. Base del proyecto y configuración

- [x] 1.1 Crear el paquete Python, entradas de API/dashboard/worker, gestión con uv y lockfile; verificar instalación limpia y arranque de las tres entradas sin llamar proveedores.
- [x] 1.2 Configurar calidad estática y pruebas con pytest, Ruff y comprobación de tipos; verificar que los comandos documentados y CI se ejecutan sobre una instalación limpia.
- [x] 1.3 Implementar configuración validada de entorno, secretos, zona horaria y modo sintético; verificar que faltan credenciales sin exponerlas y que el arranque no activa consultas pagadas.
- [x] 1.4 Incorporar el perfil inicial de recursos y catálogo versionado de familias; verificar que incluye ambos formatos, idioma inglés y exclusión de Claude, ChatGPT y Google AI Pro, sin requerir nichos del usuario.

## 2. Modelo de datos y migraciones

- [x] 2.1 Crear migraciones para identidades de canales/videos, observaciones, políticas y solicitudes de proveedor; verificar unicidad de identificadores y separación entre identidad y datos observados.
- [x] 2.2 Crear migraciones para exploraciones, jobs, cohortes, temas, oportunidades y evaluaciones; verificar pertenencia múltiple a temas sin doble conteo dentro de una cohorte.
- [x] 2.3 Crear migraciones para decisiones, recetas, escenarios, saldos y reservas; verificar que varias propuestas pueden coexistir sin una restricción de un solo canal.
- [x] 2.4 Implementar repositorios y límites transaccionales; verificar migración desde base vacía, lectura/escritura consistente y rollback de una transacción fallida en PostgreSQL de pruebas.

## 3. Integraciones, calidad y conservación

- [x] 3.1 Definir contratos de operaciones, unidades, costes, cobertura y procedencia, más un proveedor sintético; verificar casos de dato completo, cero, nulo, formato desconocido y crecimiento porcentual frente a absoluto.
- [x] 3.2 Implementar el cliente vidIQ MCP y mapeos de búsqueda, publicaciones, outliers, keywords y saldo; verificar contratos mediante fixtures sintéticos, paginación/cobertura disponible y errores de autenticación sin llamadas reales por defecto.
- [x] 3.3 Implementar el adaptador complementario de YouTube para canales, playlist de publicaciones y videos; verificar páginas, IDs duplicados, recursos ausentes y formato desconocido con fixtures, manteniendo usos sujetos a política.
- [x] 3.4 Implementar registro de usos habilitados y políticas por fuente/tipo de dato; verificar que `pending` deshabilita solo el uso dependiente y que el modo sintético y las funciones independientes siguen operativos.
- [x] 3.5 Implementar caché con parámetros canónicos y vigencia separada de conservación; verificar que solicitudes equivalentes reutilizan resultados y no confunden distintos filtros, cuentas o fechas originales.
- [x] 3.6 Implementar limpieza de observaciones, derivados, textos y referencias según política; verificar expiración con reloj controlado, explicación de evidencia no disponible y ausencia de datos expirados en logs.
- [x] 3.7 Conectar `videos.list` como enriquecimiento acotado de candidatos vidIQ; verificar lotes de 50, identidad canónica compartida, cuota/políticas propias, caché durable, combinación de campos con procedencia y cero llamadas cuando esté deshabilitado.

## 4. Presupuesto y ejecución durable

- [x] 4.1 Implementar límites en USD y créditos por operación, ejecución y periodo, más reservas transaccionales; verificar que solicitudes concurrentes no exceden el presupuesto y que costes desconocidos quedan aplazados.
- [x] 4.2 Implementar saldo renovable/adicional, renovación y conciliación de consumo externo; verificar que créditos adicionales no se convierten en asignación recurrente y que suscripción USD y consumo de créditos no duplican gasto.
- [x] 4.3 Implementar cola durable, reclamación con lease, heartbeat y etapas confirmadas; verificar recuperación tras reinicio sin repetir etapas ya persistidas.
- [x] 4.4 Implementar registro de solicitud y conciliación posterior al envío; verificar timeout con posible cobro, reserva incierta e idempotencia cuando la admita el proveedor, sin repetición ciega.
- [x] 4.5 Implementar planificador con ocurrencias únicas, pausa, reanudación y ejecución manual; verificar con reloj controlado dos planificadores, horarios Lima/UTC y límites idénticos para activación manual y programada.
- [x] 4.6 Implementar reintentos seguros acotados, resultados parciales y consolidación tras inactividad; verificar que autenticación/cuota no generan bucles y que varias ocurrencias perdidas no producen una ráfaga de gasto.

## 5. Descubrimiento y formación de muestras

- [x] 5.1 Implementar rotación persistente de familias y reparto entre descubrimiento nuevo y actualización; verificar que familias poco exploradas reciben capacidad y que cobertura pendiente permanece visible.
- [x] 5.2 Implementar expansión de consultas y candidatos con trazabilidad hasta su familia de origen; verificar una ejecución sin nichos ingresados que produce candidatos desde el proveedor sintético.
- [x] 5.3 Implementar filtro de relevancia, idioma y formato con estado desconocido; verificar que coincidencias de espacio personal/decoración no puntúan como astronomía y que Shorts no se deducen únicamente por duración.
- [x] 5.4 Implementar muestreo por tamaño, publicaciones recientes, franjas de antigüedad y deduplicación; verificar que una muestra solo de outliers no produce tasa de breakout y que canales grandes y pequeños permanecen distinguibles.
- [x] 5.5 Implementar agrupamiento acotado por embeddings y etiquetas opcionales, con fallback explícito; verificar grupos conocidos sintéticos, ruido, correspondencias ambiguas y ausencia del modelo sin inventar subnichos.

## 6. Métricas y evaluación

- [x] 6.1 Implementar demanda, oferta por ventana, vistas/suscriptores, cobertura y estadísticos por cohorte; verificar ceros, nulos, denominadores inválidos, edades diferentes y separación de formatos con ejemplos calculables manualmente.
- [x] 6.2 Implementar baseline comparable y breakout propio, manteniendo aparte scores del proveedor; verificar exclusión del video evaluado, mínimo de baseline, umbral versionado y denominador efectivo con publicaciones no clasificables.
- [x] 6.3 Implementar HHI, top-5 share y cambios temporales observados; verificar concentración en distribuciones conocidas, mínimo de canales y que una única observación no produce tendencia reciente.
- [x] 6.4 Implementar normalizadores congelados, validación de referencias y pesos de Market Score; verificar reproducibilidad, estabilidad al añadir candidatos, componentes ausentes y rechazo de calibración sintética para resultados reales.
- [x] 6.5 Implementar recetas y rúbrica versionada de Creator Fit; entregar anclas documentadas y verificar que faceless no implica automatización, que falta de coste impide un Fit completo y que se muestran rangos, supuestos y dependencias pendientes de derechos/originalidad.
- [x] 6.6 Implementar componente publicitario opcional, puntuación combinada y confianza; verificar ingresos ausentes, geografía desconocida, condición de monetización y que alto score no evita límites duros.
- [x] 6.7 Implementar explicaciones estructuradas con enriquecimiento LLM opcional y presupuesto acotado; verificar evidencia de cada afirmación, números inmutables, contenido externo tratado como datos y fallback ante fallo del LLM.

## 7. Backlog y escenarios de recursos

- [x] 7.1 Implementar identidades estables y almacenamiento de evaluaciones sucesivas; verificar que cambios de etiqueta no duplican oportunidades y que una evidencia nueva genera una versión trazable.
- [x] 7.2 Implementar decisiones de seguimiento, selección y descarte con notas; verificar que redescubrimiento no reactiva descartes ni selecciona automáticamente y que seleccionar varios candidatos no inicia acciones externas.
- [x] 7.3 Implementar comparación de evaluaciones y posiciones; verificar que se distingue cambio de datos, cambio de método y desplazamiento por otros candidatos.
- [x] 7.4 Implementar escenarios manuales de varias propuestas de canal y formatos; verificar suma de variables, suscripciones contadas una vez, capacidad agregada, reserva y horas en unidades compatibles.
- [x] 7.5 Implementar resultado viable/no viable/no evaluable de escenarios con rangos; verificar límite conjunto excedido, costes desconocidos, extremo superior del rango y que las simulaciones no descuentan saldo real.

## 8. API y dashboard privado

- [x] 8.1 Implementar endpoints autenticados de perfil, radar, proveedores y ejecuciones, con respuestas de trabajos asíncronos; verificar autorización, validación, paginación e idempotencia de solicitudes manuales.
- [x] 8.2 Implementar endpoints de oportunidades, evidencias y decisiones; verificar filtros por formato/estado/confianza y mantenimiento de decisiones ante una actualización concurrente.
- [x] 8.3 Implementar endpoints de consumo y escenarios; verificar distinción entre gasto confirmado, reservas, cobros inciertos y estimaciones de producción.
- [x] 8.4 Construir dashboard de resumen, backlog y detalle en español; verificar con datos sintéticos navegación, evidencia original, fechas y estados vacíos diferenciados, sin un top artificial.
- [x] 8.5 Construir vistas de configuración, escenarios y operación; verificar edición de límites, pausa/reanudación, varias propuestas y visibilidad de antigüedad/fallos sin exponer secretos.

## 9. Empaquetado y preparación de Easypanel

- [x] 9.1 Crear imágenes de API/worker compartida y dashboard, y entorno Compose local; verificar arranque, healthchecks y persistencia tras recrear contenedores en un entorno aislado.
- [x] 9.2 Documentar configuración de servicios App/Postgres, red interna, HTTPS, autenticación, secretos y migraciones; verificar que la guía permite desplegar imágenes fijadas sin publicar PostgreSQL ni depender del Mac encendido.
- [x] 9.3 Preparar límites de recursos y registro de métricas operativas sin secretos; verificar memoria/concurrencia configurable, última ejecución, errores, coste y cobertura desde el dashboard.
- [ ] 9.4 Preparar respaldo, restauración y rollback compatibles con conservación; verificar restauración aislada, limpieza de datos vencidos y programación pausada antes de reactivar servicios.

## 10. Verificación integral y habilitación del piloto

- [x] 10.1 Ejecutar el flujo completo sintético desde catálogo hasta backlog; verificar trazabilidad, ambos formatos, datos insuficientes y que una segunda ejecución reutiliza caché y conserva descartes.
- [x] 10.2 Ejecutar pruebas integradas de fallos y concurrencia; verificar reinicio a mitad de pipeline, cobro incierto, pérdida de conexión, presupuesto agotado, expiración y ausencia de llamadas repetidas no conciliadas.
- [x] 10.3 Revisar condiciones y costes actuales de proveedores antes de habilitar usos reales; entregar una matriz de operaciones/almacenamiento/derivados con evidencia, estados y límites, manteniendo pendientes explícitos si no hay resolución.
- [x] 10.4 Inspeccionar el VPS y preparar el despliegue aislado con los recursos disponibles; verificar arquitectura CPU, servicios existentes, memoria/disco libre y límites elegidos, sin detener ni eliminar aplicaciones ajenas.
- [x] 10.5 Desplegar la V1 inicialmente pausada cuando exista acceso autorizado al VPS; verificar autenticación externa, comunicación interna, persistencia, salud y recuperación sin activar consultas pagadas durante el smoke test.
- [x] 10.6 Ejecutar un piloto real acotado con operaciones habilitadas y presupuesto configurado; entregar informe de llamadas, créditos, coste, tiempos, relevancia y cobertura por familia/formato, sin recomendar compras automáticamente.
- [x] 10.7 Congelar referencias iniciales y rúbricas con el piloto cuando la evidencia alcance los mínimos; verificar reproducción de puntuaciones y sensibilidad a pesos, o mantener `uncalibrated` y registrar la calibración como pendiente si faltan datos.
- [x] 10.8 Activar y observar un ciclo programado dentro del presupuesto; verificar ejecución sin dashboard abierto, actualización del backlog y límites efectivos, y entregar guía de operación con dependencias pendientes explícitas.
