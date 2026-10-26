# Respaldo, restauración y rollback

## Decisión 9.4 (2026-10-25): se respaldan los datos de investigación

El propietario eligió la **opción A**: habilitar el respaldo cifrado en el Mac de los datos de
investigación de mercado y de flujo, con retención y custodia de clave definidas (abajo).
Sigue sin contratarse almacenamiento externo (R2/B2 no elegidos ni contratados). El resto de
este documento conserva el historial de la copia inicial de 2026-09-16.

Alcance del snapshot (`scripts/backup_snapshot.py`, falla cerrado):

| Grupo | Tablas | Estado |
|---|---|---|
| Arranque | configuración, catálogo, políticas, `radar_schedules`, `market_intel_schedule`, benchmarks | respaldado |
| Pilotos | `pilots`, `pilot_videos`, `pilot_shorts_measurements`, `pilot_events`, `channel_tokens` (solo SHA-256) | respaldado |
| Mercado | `market_scrape_runs`, `marketplace_listings`, `listing_observations`, `listing_classifications`, `listing_verifications`, `niche_automation_priors`, `market_niche_snapshots`, `market_niche_decisions` | respaldado |
| Flujo | `flow_research_requests`, `flow_research_dossiers` | respaldado |
| Evidencia de proveedores | `raw_observations`, `provider_requests`, `topics`, rankings, evaluaciones... | **no revisada: sigue bloqueando** (`research_data_backup_not_enabled`) |

Una tabla nueva queda fuera de las listas revisadas y, si tiene filas, bloquea el respaldo hasta
que alguien la clasifique en el código. Siguen exigiéndose: esquema exacto, revisión `0017`
(al migrar hay que revisar el alcance y subir esa constante), radar y programación de mercado
en pausa y ningún proveedor real habilitado.

El `scope` reportado es `bootstrap-only`, `bootstrap+pilots`, `bootstrap+research` o
`bootstrap+pilots+research`. El snapshot informa además `delete_after`: el menor `retain_until`
de la evidencia con caducidad (`backup_deadline`, que ahora incluye fichas, observaciones,
clasificaciones, verificaciones, snapshots de mercado y encargos/dossiers de flujo). Los datos
de mercado y flujo se conservan 183 días; las decisiones del propietario y los priors no caducan.
`backup` y `restore-drill` verifican también estas tablas (conteos idénticos tras restaurar).

### Política de retención de copias locales (Mac)

- **Diarias**: la copia más reciente de cada uno de los últimos **7 días** con copias.
- **Semanales**: la copia más reciente de cada una de las **4 semanas ISO** anteriores.
- Máximo ~11 copias vivas; las demás se consideran reemplazadas.
- **Vencimiento de datos**: una copia cuyo `delete_after` ya pasó se destruye aunque entre en
  los cupos anteriores. Una semanal puede durar menos de 4 semanas si contiene evidencia de
  caducidad cercana; las copias diarias nuevas ya no la contienen.
- `prune` es **simulación por defecto**; solo borra con `--apply`:

  ```sh
  uv run python scripts/backup_mac.py prune            # muestra qué borraría
  uv run python scripts/backup_mac.py prune --apply    # borra
  ```

  Seguridad: solo archivos regulares (no enlaces simbólicos) propiedad del usuario, directamente
  dentro de `backups/`, con el nombre exacto `bootstrap-<UTC>-<8hex>.gpg`. Nunca toca la clave,
  otros archivos ni el VPS. Un archivo ilegible (clave errónea o corrupto) se conserva y se
  informa. La fecha sale del nombre, no del mtime.
- No hay programación automática: ejecutar `backup` y luego `prune --apply`. Automatizarlo con
  `launchd` es decisión del propietario.
- **Réplicas fuera del control del script**: Time Machine, iCloud o copias del sistema pueden
  retener archivos ya borrados. Excluir la carpeta de respaldos (por ejemplo
  `tmutil addexclusion "$HOME/Library/Application Support/NicheRadar/backups"`) o aceptar que
  la caducidad de 183 días no es verificable en esas réplicas. Acción del propietario.
- Con el Mac apagado no hay copia nueva ni borrado: el vencimiento se aplica en el siguiente `prune`.

### Custodia de la clave (procedimiento propuesto; no ejecutado)

`~/Library/Application Support/NicheRadar/keys/backup.key` protege todas las copias: perderla
es perder las copias; filtrarla expone los datos. Este procedimiento **no genera, mueve ni lee**
claves reales; es lo que el propietario debe ejecutar.

1. **Custodia externa**: copia de la clave en un gestor de contraseñas del propietario con 2FA,
   o impresa en un sobre en un lugar físico seguro. Nunca en el repo, chat, correo ni VPS.
   Una copia en el mismo Mac no cubre su pérdida.
2. **Verificar la custodia**: con la copia externa, reconstruir un archivo de clave 0600 bajo
   otro `--root` temporal y ejecutar `verify` sobre una copia reciente; borrar luego ese directorio.
3. **Rotación** (cada 12 meses o ante sospecha de exposición): `init --root <nuevo>` genera una
   clave nueva sin reemplazar la vieja; hacer `backup` con ella, comprobar `restore-drill`,
   guardarla en custodia externa y destruir la antigua y las copias cifradas con ella (con la
   retención, quedan como máximo ~4 semanas). Mientras existan copias con la clave vieja, se conserva.
4. **Prueba de restauración**: al menos mensual y tras cada cambio de esquema,
   `restore-drill` sobre la última copia (clúster temporal sin TCP; no toca producción).
5. **Compromiso de la clave**: rotar de inmediato y destruir copias antiguas y réplicas del sistema.

---

## Histórico: prioridad acordada el 2026-09-16 (almacenamiento externo aplazado)


El 2026-09-16 el propietario decidió dejar la evaluación/configuración de almacenamiento
externo para el futuro y continuar con el radar. Cloudflare R2 y Backblaze B2 fueron
alternativas evaluadas, **no seleccionadas ni contratadas**. No crear cuentas, buckets,
automatizaciones ni cargos por esta decisión. Se conserva la copia manual inicial del Mac.

(Superado en parte por la decisión 9.4 de arriba: mercado y flujo ya se respaldan. Siguen
pendientes la custodia externa de la clave, la limpieza de réplicas del sistema y una prueba
de rollback; la evidencia de proveedores sigue bloqueada.)
El piloto puede prepararse independientemente, manteniendo sus propios requisitos de
conexión, permisos, conservación en SQL, límites y aprobación de gasto.

## Estado verificado — 2026-09-16

Primera copia **cifrada y restaurada con éxito** del estado inicial del VPS:

- Archivo: `~/Library/Application Support/NicheRadar/backups/bootstrap-20260916T133239Z-b0c0184e.gpg`
  (148.801 bytes; nombre con fecha UTC).
- Clave aleatoria: `~/Library/Application Support/NicheRadar/keys/backup.key`;
  no se imprime, publica ni envía al servidor. Directorios 0700 y archivos 0600.
- Esquema `0008`, candidata desplegada `v1-candidate-20260915-002`.
- Restauración en un clúster PostgreSQL 18 nuevo, solo socket local, sin worker ni
  acceso público. Conteos y configuración comprobados; recuperación deja una
  programación pausada y deshabilita la confirmación de gasto. Fuente intacta.
- Eliminados únicamente los clústeres temporales de prueba. Se conserva el archivo
  cifrado; no se dejó un dump sin cifrar en disco ni en el VPS.

**Alcance limitado, no una política terminada de respaldo:** el script rechaza datos
de investigación, incluso sintéticos, proveedores reales habilitados, programación
activa y esquemas no revisados. Solo admite las tablas iniciales de configuración,
catálogo y políticas; todas las demás deben estar vacías. No se ha activado ninguna
programación de backups ni limpieza automática. La tarea 9.4 continúa abierta.

La clave está separada del archivo, pero en el mismo Mac. Una pérdida simultánea del
Mac y del VPS no queda cubierta. Falta que el propietario conserve una copia segura
de recuperación de la clave fuera del Mac; no compartirla por chat ni subirla al repo.
Esto tampoco protege frente a una cuenta del Mac comprometida con acceso a ambos.

## Destino elegido y conservación pendiente

El propietario permite usar el Mac y delegó la elección frente a guardar todo en
el VPS. Se elige el Mac como destino principal externo, con cifrado; una copia en
el mismo VPS solo sería temporal y no protege ante pérdida de ese servidor/disco.
Se ha creado la copia manual inicial descrita arriba; no se ha comprado almacenamiento.
La recomendación de cifrar y probar restauraciones coincide con
[la guía de CISA](https://www.cisa.gov/stopransomware/ransomware-guide).

Si el Mac está apagado o desconectado, no se garantiza una copia externa nueva.
Además, su desconexión no permite garantizar eliminación puntual de archivos
vencidos: resolver conservación y posibles réplicas locales (por ejemplo, copias
del sistema) antes de habilitar backups que contengan evidencia real de proveedores.
El cifrado por sí solo no convierte un destino desconectado en compatible con TTL.
Ruta, clave, cifrado y recuperación inicial están verificados. Quedan programación,
limpieza de todas las réplicas y política operativa para datos externos futuros.

Antes de ampliar el respaldo se requiere decidir entre un destino externo con
eliminación comprobable o copias del Mac limitadas a información propia, regenerando
la evidencia externa tras una pérdida. La segunda opción cambia el alcance de la
recuperación y requiere aprobación; **no se ha implementado ni dado por aceptada**.

La candidata 005 conserva la 004 como imagen anterior compatible con el esquema
0008, pero todavía no se ha ejecutado una prueba de rollback en Contabo.

## Herramienta manual para el estado inicial

Desde la raíz del repositorio, con SSH existente, GnuPG y PostgreSQL locales:

```sh
uv run python scripts/backup_mac.py init
uv run python scripts/backup_mac.py backup
uv run python scripts/backup_mac.py verify --archive '/ruta/exacta/al/archivo.gpg'
uv run python scripts/backup_mac.py restore-drill --archive '/ruta/exacta/al/archivo.gpg'
uv run python scripts/backup_mac.py prune [--apply]   # retención local, ver arriba
```

`init` es idempotente: nunca reemplaza una clave existente. El respaldo verifica
exclusivamente los contenedores propios, conserva digests en el metadato cifrado y
obtiene un `pg_dump` en la misma instantánea exportada que se inspeccionó mediante
una transacción de solo lectura. Se evita validar una foto y copiar otra diferente.
El dump, sus metadatos y checksum viajan en un único sobre cifrado; se comprueba
descifrado completo antes de guardarlo. Una modificación del archivo o clave errónea
impide restaurar. No suministra credenciales mediante argumentos ni imprime errores
brutos de SQL/SSH/GnuPG. Rechaza archivos excesivos; pensado solo para el estado inicial.

`restore-drill` no acepta URL de destino: crea su propio clúster temporal sin TCP,
restaura únicamente allí y lo elimina al terminar. Elimina el esquema `public`
vacío de ese clúster, sin `CASCADE`, antes de importar el `CREATE SCHEMA` del dump.
No restaura en bases existentes ni arranca la aplicación. Solo usar archivos propios
y confiables: cifrado no implica que un SQL de origen desconocido sea seguro.

El uso de cifrado simétrico y clave en archivo sigue las opciones de
[GnuPG](https://www.gnupg.org/documentation/manuals/gnupg/GPG-Esoteric-Options.html);
la exportación coherente utiliza `--snapshot` de
[pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html).

## Alcance de restauración

La restauración debe realizarse en una base y volumen **nuevos y aislados**, sin worker,
dashboard, credenciales de proveedores ni tráfico público. Nunca restaurar encima de la base
activa. Solo aceptar dumps propios y verificados; restaurar un archivo puede ejecutar SQL.

## Crear un respaldo

1. Pausar el radar por su API/dashboard y esperar o detener de forma controlada únicamente
   su worker. Confirmar que no quedan solicitudes en vuelo; registrar las inciertas.
2. Aplicar las políticas vigentes y la limpieza antes de obtener la copia. Registrar esquema,
   versión de aplicación, hora UTC, digest y checksum del archivo, sin credenciales.
3. Usar `pg_dump --format=custom --no-owner --no-acl` contra la base exacta del radar;
   suministrar la conexión mediante configuración privada de PostgreSQL, no contraseñas
   en argumentos, historial del shell o logs. Proteger archivos y directorio de destino.
4. Para datos reales, cifrar y elegir un destino privado con eliminación por caducidad
   comprobada. No activar respaldos reales hasta configurar y probar ese destino y sus claves.
5. `backup_deadline(connection)` calcula la menor fecha de conservación de la evidencia.
   Destruir la copia inmutable antes de ese vencimiento; crear otra copia depurada si hace falta.
   Si una política se revoca antes, invalidar también sus copias, incluidas réplicas y versiones.
   La función calcula el plazo: **no existe todavía limpieza automática del destino de backups**.

No guardar copias indefinidamente ni suponer que el cifrado elimina las obligaciones de
conservación. Si no se puede garantizar eliminación a tiempo, no generar esa copia externa.

## Restaurar sin reactivar gasto

1. Crear la base destino y comprobar que está vacía. Mantenerla desconectada de proveedores.
2. Ejecutar `pg_restore --exit-on-error --no-owner --no-acl` contra ese destino. Conservar
   la base original intacta. Usar herramientas PostgreSQL compatibles con la versión del dump.
3. Aplicar migraciones compatibles y las políticas actuales: las incluidas en el dump pueden
   haber cambiado. Con `NR_DATABASE_URL` apuntando **solo al destino**, ejecutar:

   ```sh
   uv run python -m nicheradar.services.recovery --confirm-isolated-restore
   ```

   Este paso pausa toda programación, aplaza jobs incompletos, invalida la confirmación de
   presupuesto y la frescura del saldo, conserva reservas inciertas y elimina evidencia vencida.
   Una solicitud preparada en el respaldo pudo haberse enviado después: también requiere
   conciliación, aunque el dump no muestre `sent`.

4. Revisar perfil, decisiones, conteos y evidencias disponibles. No mostrar al usuario textos
   de evidencia vencida para reconstruir el historial.
5. Antes de reactivar, detener la instancia original del radar y conciliar **todo** consumo
   posterior al respaldo con el proveedor, incluido USD. Revisar reservas aunque el saldo
   remoto parezca suficiente. Confirmar límites nuevamente y aprobar el cambio de tráfico.
   No iniciar dos planificadores con la misma cuenta desde bases distintas.

## Rollback

Si la imagen anterior es compatible con el esquema actual, pausar y volver a su digest
verificado. Si no lo es, restaurar en una base separada y seguir el procedimiento anterior.
No ejecutar la reversión de la migración inicial sobre datos reales: elimina el esquema.
No borrar la base anterior hasta comprobar el resultado y acordar su conservación.

## Verificación automatizada

`tests/test_recovery.py` genera datos sintéticos, ejecuta `pg_dump`, restaura en una nueva
base de nombre aleatorio, adelanta el reloj y verifica pausa, decisiones, limpieza y reservas.
La fuente permanece intacta y al terminar se elimina solo esa base de pruebas. Esto comprueba
la limpieza SQL de evidencia vencida, no la eliminación puntual de copias desconectadas.

`tests/test_backup_mac.py` añade cifrado, integridad, clave errónea, permisos,
rechazo de symlinks/esquemas desconocidos/datos de investigación y restauración real
del esquema `public` desde un archivo cifrado en otro clúster. También se corrigió
`backup_deadline` para incluir configuraciones de puntuación y snapshots de ranking.
Ese cambio está desplegado desde la candidata 003, pero no resuelve la eliminación puntual
de copias externas ni constituye una prueba de rollback. No habilitar backups de
proveedores basándose únicamente en el cifrado del Mac.
