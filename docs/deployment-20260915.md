# Despliegue inicial en Contabo — 2026-09-15

Registro histórico del despliegue inicial. Actualización posterior:
[candidata 002 desplegada y verificada](release-20260915-002.md), con tarea 9.3
completa y resolución normal del Mac ya dirigida al VPS (401 autenticado, no 404).

Estado: cuatro servicios ejecutándose, sintéticos y pausados. HTTPS y autenticación
externa verificados contra el VPS; algunos resolvedores todavía conservan la IP
anterior. No confundir este arranque con un piloto real.

## Destino y alcance

El propietario autorizó usar `proy1-credito-riesgo` por el límite de proyectos de su
plan. No se creó un proyecto separado, no se amplió licencia y no se modificaron
aplicaciones, bases, variables compartidas ni dominios ajenos. La red
`easypanel-proy1-credito-riesgo` es compartida: aislamiento de datos y credenciales,
no aislamiento de red respecto a las otras aplicaciones del proyecto.

CLI conectado al perfil `contabo`, panel `https://panel.soydavidrodriguez.com`,
Easypanel 2.34.0. La API key fue introducida por el propietario y se guarda en el
llavero de macOS. Los secretos nuevos se generaron aleatoriamente y se enviaron
por stdin al CLI; quedaron en la configuración privada de sus servicios, no en
archivos locales, argumentos de comandos, imágenes ni este informe.

## Configuración efectiva

| Servicio nuevo | CPU máxima | RAM máxima | Puertos publicados |
| --- | ---: | ---: | --- |
| `nicheradar-db` | 0,5 | 512 MiB | Ninguno |
| `nicheradar-api` | 1 | 512 MiB | Ninguno |
| `nicheradar-worker` | 1 | 512 MiB | Ninguno |
| `nicheradar-dashboard` | 0,5 | 512 MiB | Ninguno |

Una réplica por servicio; reservas de 128 MiB y 0,1 CPU. API y worker comparten
el digest backend de [la candidata publicada](release-20260915-001.md).
Dashboard usa su digest publicado. Swarm confirmó las referencias inmutables
y los límites. La imagen backend se descargó desde el VPS y ejecutó Alembic;
la migración puntual terminó con código 0 y revisión `0008`. Su contenedor
temporal se eliminó automáticamente con `--rm`, sin eliminar datos persistentes.

PostgreSQL 18.6 usa el digest fijado en Compose, con `PGDATA` explícito
`/var/lib/postgresql/data/pgdata`, dentro del bind mount administrado:
`/etc/easypanel/projects/proy1-credito-riesgo/nicheradar-db/data` →
`/var/lib/postgresql/data`. Se verificó `SHOW data_directory`, no solo el entorno.
La imagen también declara un volumen anónimo padre `/var/lib/postgresql`; el
directorio activo está en el bind anidado, no en ese volumen anónimo.
Los límites enviados al crear Postgres no quedaron aplicados; se corrigieron con
`postgres update-resources` y se verificaron en Swarm. No basta revisar el formulario.

Aplicaciones creadas sin dominios, sin puertos y con cero réplicas hasta completar
migración; posteriormente arrancadas. No se proporcionaron claves de proveedores,
modelos ni LLM. `NR_MODE=synthetic`, pausa persistida, concurrencia 1, lote 20,
poll de 30 segundos y LLM desactivado.

## Verificaciones realizadas

- API viva; endpoint protegido devuelve 401 sin token y responde desde dashboard
  con el token correcto. Estado sintético, base conectada y programación pausada.
- Consumo confirmado y reservas vacíos; `provider_requests` tenía cero filas.
  vidIQ/YouTube sin credenciales, explicaciones LLM desactivadas.
- Heartbeat del worker comprobado y salud HTTP de Streamlit disponible internamente.
- `AppTest` dentro de la imagen desplegada: antes del login no aparecen vistas ni
  datos; contraseña incorrecta rechazada; contraseña correcta permite Resumen,
  Backlog, Escenarios, Configuración y Operación sin excepciones. Son pruebas
  internas, no sustituyen una sesión de navegador a través de HTTPS/WebSocket.
- Perfil cambiado temporalmente de 15 a 17 horas: conservado tras reiniciar los
  tres servicios App y restaurado a 15. Se repitió el marcador para PostgreSQL:
  guardar límites idénticos no recreaba el contenedor, por lo que se ejecutó
  `docker service update --force --detach=true proy1-credito-riesgo_nicheradar-db`.
  Contenedor anterior `e50c1203e47d`, nuevo `bfd3969d5d56`; el probe confirmó que
  el marcador persistió y devolvió el perfil a 15 horas. La API mantuvo conexión,
  pausa y contabilidad vacía después de recrear PostgreSQL.
- Los 25 servicios del VPS aparecieron con 1/1 réplicas (21 previos + 4 nuevos).
  Última muestra: 7696 MiB de RAM disponible y 341 GiB de disco libre. Antes de
  recrear PostgreSQL, los cuatro nuevos sumaban aproximadamente 271 MiB de RAM.
  Son muestras de reposo, no validación de rendimiento bajo carga real.

Los scripts `scripts/easypanel_stage.mjs` y `scripts/easypanel_probe.py` están
restringidos al destino y nombres anteriores. Las operaciones de creación no son
un reconciliador general: se detienen si ya existen los servicios. No ejecutarlos
a ciegas para actualizar o volver a desplegar una base con datos reales.

## Dominio: DNS actualizado y HTTPS verificado

`nicheradar.soydavidrodriguez.com` está asociado únicamente al dashboard (HTTP
interno 8501), con HTTPS configurado y HTTP Basic Auth, además del login de la app.
Sin dominios alternativos de NicheRadar. Desde el VPS, el proxy respondió 401 al
acceso HTTPS anónimo y 301 de HTTP hacia HTTPS. Se omitió la validación del
certificado **solo en esa prueba local sin credenciales**: todavía no demuestra
un certificado público válido.

El propietario cambió el registro A de `66.225.221.53` a `194.61.28.253` en cPanel.
Ambos servidores autoritativos y el resolvedor `1.1.1.1` confirmaron el destino nuevo,
TTL 14400 segundos. El resolvedor local todavía devolvía la IP anterior al finalizar.
No se cambiaron raíz, www, correo ni nameservers.

El error ACME inicial de las 21:57:57 UTC apuntaba a la IP antigua y recibió 404.
Se guardó de nuevo únicamente este dominio mediante el CLI oficial, explicitando
el resolver existente `letsencrypt`; se mantuvieron HTTPS y Basic Auth, sin reiniciar
el proxy compartido ni editar su almacén de certificados. Posteriormente:

- HTTPS contra `194.61.28.253`, conservando hostname/SNI y validación de confianza:
  certificado aceptado, `ssl_verify_result=0`, acceso anónimo 401.
- Probe externo: `/`, `/_stcore/health` y el upgrade de `/_stcore/stream` rechazan
  acceso anónimo; contraseña incorrecta rechazada. Con Basic Auth correcto, página
  y salud devuelven 200 y WebSocket negocia 101, protocolo `streamlit` y handshake válido.
- Se repitió `AppTest` en el contenedor: login incorrecto rechazado, correcto aceptado,
  cinco vistas sin excepciones. API conectada, sintética y pausada; consumo y reservas
  vacíos, proveedores sin credenciales.

`node scripts/easypanel_stage.mjs public-probe` lee solo las credenciales del propio
dashboard en memoria; no las imprime, no sigue redirecciones y no desactiva TLS.
Fija la IP para evitar la caché local antigua. No equivale a una sesión completa
de navegador: la comprobación manual del propietario queda recomendada cuando su
resolvedor vea la nueva IP. Si aparece una advertencia TLS, no introducir credenciales.

Credenciales de acceso: usuario HTTP Basic `david`; contraseña en Security del
servicio dashboard. La contraseña interna de la app está en su variable
`NR_DASHBOARD_PASSWORD`. Son diferentes; no copiarlas a mensajes o capturas.
Las tareas 9.2 y 10.5 se completan con estas pruebas externas y las verificaciones
previas de comunicación interna, salud, recreación y persistencia.

## Incidencia de ocultación del CLI

Una lectura de `projects inspect` imprimió campos secretos anidados que el CLI no
ocultó pese a no usar `--show-secrets`. La salida incluyó los tokens de despliegue
de los cuatro servicios preexistentes de `proy1-credito-riesgo` y una credencial
de Docker Hub del servicio `riesgo-credito-api`. No se reproduce ningún valor aquí;
no se detectó ni se afirma publicación externa de esos secretos.

Recomendación: rotar esos tokens de despliegue y la credencial de Docker Hub,
actualizando cualquier consumidor antes de revocar. No se rotaron automáticamente:
podría afectar las aplicaciones existentes y requiere autorización separada.
Las respuestas posteriores se capturaron y se imprimieron solo campos permitidos;
la ocultación predeterminada del CLI no se considera suficiente.

## Pendientes

Propagación restante de cachés DNS y comprobación manual en navegador; observabilidad
completa; respaldos cifrados, destino y
caducidad de todas las copias; piloto autorizado con proveedores reales,
calibración y ciclo programado. El radar permanece pausado y no se habilitaron
compras, llamadas pagadas, producción ni publicación de videos.
