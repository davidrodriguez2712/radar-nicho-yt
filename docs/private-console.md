# API y consola privada

La navegación inicial es en español; la evidencia conserva su idioma y contenido
originales. El acceso requiere contraseña de dashboard y credencial de servicio
para la API. No se llama a proveedores desde una petición HTTP del panel.

## Solicitudes y seguimiento

`POST /api/v1/runs` requiere `Idempotency-Key` de 8 a 100 caracteres. Devuelve HTTP
202 con `job_id` y `status_url`; significa **aceptado**, no análisis finalizado.
`GET /api/v1/jobs/{id}` muestra estado, etapa, etapas confirmadas y cobertura.
No expone la clave de solicitud, identidad interna del worker ni contenido completo
de los checkpoints. No hay endpoints para crear canales, comprar o publicar vídeos.

Repetir la misma clave para el mismo perfil y modo devuelve el mismo trabajo,
incluso si el radar se pausó después. Una clave nueva con el radar pausado devuelve
409. La pausa no elimina resultados ni cancela retroactivamente solicitudes. Las
claves de la versión anterior siguen reconociéndose para el mismo perfil y modo.
Las solicitudes reales nuevas siguen bloqueadas mientras la conexión real y las
políticas estén pendientes, aunque la programación sintética se hubiera reanudado.

Los listados de trabajos y políticas admiten `limit` (1–100) y `offset` (desde 0),
devuelven total y mantienen un desempate estable por ID. El panel incluye páginas
para ambos. Las políticas mostradas incluyen versiones históricas; la presencia de
una fila no confirma que todos los usos de un proveedor estén habilitados.

Errores de validación devuelven 422 sin copiar valores enviados. Los conflictos de
edición devuelven 409, recursos inexistentes 404 y fallos de base de datos 503 sin
detalles de conexión. La autenticación se comprueba antes de acceder a los datos.

## Backlog

Admite búsqueda literal por tema —no patrones SQL—, formato, revisión, confianza,
viabilidad estimada, puntuación mínima y fecha mínima de evaluación. Puede ordenarse
por puntuación, fecha, tema, formato, revisión, confianza y viabilidad. Los valores
sin puntuación quedan al final; cero no se confunde con desconocido.

La fecha introducida en el panel empieza a medianoche en la zona configurada
(`America/Lima` inicialmente). La API exige una zona horaria explícita en
`evaluated_after`. Cambiar filtros u orden vuelve a la primera página. Una página
vacía no se presenta como prueba de que no existan nichos. No se añaden resultados
para completar un top; el orden de una lista no modifica los puestos históricos.

## Estado de la investigación

El estado operativo distingue proveedor/configuración pendiente, presupuesto o
cobro incierto, trabajo en curso, error técnico, cobertura parcial, evidencia
caducada, evaluación incompleta y ausencia de resultados. La pausa se muestra por
separado. Los avisos pueden coexistir: pausar no convierte un fallo anterior en éxito.

La última ejecución satisfactoria y los contadores se separan por modo y perfil:
una prueba sintética no acredita una ejecución real. La fecha de la última observación
disponible y su antigüedad no se actualizan por reutilizar caché ni por recalcular una
evaluación. Esa fecha resume la observación más reciente, no garantiza que todos los
candidatos tengan datos igual de recientes; el detalle mantiene las fechas de evidencia.

Los motivos de aplazamiento describen el último trabajo; no son una consulta de saldo
remoto ni prueban que una condición ya haya sido resuelta. Antes de cada operación,
el worker sigue aplicando los controles de presupuesto y uso.

## Verificación

`test_api_contracts.py` cubre autorización, validación sin eco de valores, paginación,
seguimiento asíncrono y reintentos concurrentes. `test_console_states.py` prueba estados,
fechas, filtros y ausencia de un top artificial. `test_dashboard_navigation.py` recorre
el panel con la API y PostgreSQL temporales, incluida la evidencia original y el cambio
de páginas/filtros. No se usan llamadas pagadas ni servicios del VPS.
