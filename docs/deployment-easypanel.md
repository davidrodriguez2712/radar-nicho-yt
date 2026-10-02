# Despliegue privado en Easypanel

Estado: **cuatro servicios desplegados en Contabo, en modo live y pausados**.
Migración, autenticación interna, login del dashboard y persistencia tras recrear
contenedores comprobados. DNS autoritativo actualizado; HTTPS, Basic Auth y handshake
WebSocket externos verificados contra el VPS. La resolución normal del Mac ya devuelve
la IP correcta. Candidata activa:
[009, rediseño completo del dashboard y piloto real de YouTube/LLM](release-20260927-009.md).
Ver también [registro del despliegue inicial](deployment-20260915.md).
Esta guía no autoriza eliminar aplicaciones existentes.

El 2026-09-15 el propietario autorizó crear y configurar únicamente los servicios de
NicheRadar en Easypanel, sin modificar aplicaciones existentes. La autorización no
incluye actualizar el panel, cambiar el firewall compartido ni habilitar proveedores.
El propietario configuró posteriormente el CLI `contabo` con autenticación mediante
el llavero de macOS y autorizó usar `proy1-credito-riesgo` al alcanzar su límite de
proyectos. No se creó el proyecto separado `nicheradar`.

## Destino confirmado y DNS

- Dominio: `nicheradar.soydavidrodriguez.com`.
- Cuenta Docker Hub: `davidrodriguez2712`.
- Repositorios públicos verificados: `davidrodriguez2712/nicheradar-backend`,
  `davidrodriguez2712/nicheradar-worker` y `davidrodriguez2712/nicheradar-dashboard`.
- Proyecto Easypanel autorizado: `proy1-credito-riesgo`, ya existente.
- Servicios nuevos: `nicheradar-api`, `nicheradar-worker`, `nicheradar-dashboard`,
  `nicheradar-db`. Datos, credenciales y recursos propios; red interna compartida
  con las otras aplicaciones del proyecto. No cambiar sus variables compartidas.
- VPS previsto: `194.61.28.253`, arquitectura `linux/amd64` observada por SSH.

Consulta DNS de solo lectura del 2026-09-15: servidores autoritativos
`ns5922.banahosting.com` y `ns5923.banahosting.com`; el subdominio resolvía
a `66.225.221.53`, no al VPS. No se obtuvo respuesta AAAA ni CNAME. Esto no comprueba
qué aplicación sirve esa IP ni autoriza sobrescribir un registro existente. Posteriormente
el propietario aclaró que acaba de crear el subdominio en cPanel y apenas lo ha configurado;
se mantiene el orden acordado: preparar la app primero, cambiar únicamente su DNS después.

El propietario actualizó posteriormente el registro; ambos DNS autoritativos y
`1.1.1.1` confirmaron el nuevo destino. La configuración es:

| Tipo | Nombre dentro de la zona | Destino previsto |
| --- | --- | --- |
| A | `nicheradar` | `194.61.28.253` |

No cambiar nameservers, dominio raíz, `www`, correo ni otros subdominios. No añadir
AAAA sin verificar una dirección IPv6 del VPS y su ruta HTTPS. Registrar el valor anterior
y revisar la resolución después del cambio; la caché DNS puede conservarlo hasta su TTL.
Si el registro actual atiende otra aplicación, detenerse antes de modificarlo.

## Publicación de imágenes

Seguir [la preparación de release para Docker Hub](release-dockerhub.md). El propietario
autorizó imágenes públicas al comienzo y privadas más adelante, entendiendo que proteger
el dashboard no impide descargar el código de una imagen pública. No comprar capacidad
privada ni cambiar visibilidad automáticamente. API y worker deben usar el mismo digest backend.

Las referencias activas están en [la candidata 009](release-20260927-009.md#trazabilidad).
El despliegue ya descargó y ejecutó esas referencias desde el VPS.

## Comprobación previa de solo lectura

Con el alias que facilite el propietario, comprobar `uname -m`, versión del sistema,
`free -h`, `df -h`, `docker version`, `docker ps` y `docker stats --no-stream`.
Registrar únicamente arquitectura, cantidades agregadas y puertos relevantes; no volcar
variables de entorno, claves, logs completos ni configuración secreta de otros servicios.
No instalar paquetes ni detener aplicaciones durante la inspección.

La inspección del 2026-09-13 observó 6 CPU, 8,7 GiB de RAM disponible y 338 GiB de
disco disponible, con 21 servicios Swarm. Fue una muestra poco después del arranque,
no una validación de carga sostenida. Docker era 28.3.2; Easypanel usaba `latest`,
sin identificar su versión efectiva. Ver [estado y advertencias](implementation-status.md).
Perfil inicial de prueba: PostgreSQL 512 MiB/0,5 CPU; API 512 MiB/1 CPU;
worker 512 MiB/1 CPU; dashboard 512 MiB/0,5 CPU. Son límites iniciales, no mediciones
del VPS ni garantías de capacidad. Migraciones necesitan capacidad temporal adicional.
Concurrencia externa 1. Solo la imagen del worker incluye ONNX Runtime y el modelo local
cuantizado; API y dashboard conservan la imagen base. La medición amd64 alcanzó 172 MiB,
por debajo del límite de 512 MiB.

Inspección actualizada del 2026-09-15, de solo lectura: arquitectura x86_64,
7.809 GiB aproximadamente de memoria disponible (7997 MiB), 343 GiB de disco libre,
21 servicios Swarm con 1/1 réplicas y casi dos días de uptime. Carga media
0,05/0,02/0,01; dos intervalos de `vmstat` mostraron 98–99% de CPU inactiva.
Es una comprobación puntual, no una prueba de carga sostenida. Easypanel instalado:
`2.34.0`, leído de su `package.json`; interfaz local respondió HTTP 200.
En esa inspección todavía no existía CLI `easypanel` en el PATH del Mac ni del VPS;
el propietario lo instaló después en el Mac y configuró el perfil `contabo`.
Un servicio Postgres administrado existente monta `/var/lib/postgresql/data`;
solo se leyó la ruta de destino del montaje, sin consultar sus credenciales.
La base nueva se verificó posteriormente con `PGDATA` explícito y recreación real;
ver el registro del despliegue.

### Acceso de administración

La [documentación oficial del CLI](https://easypanel.io/docs/cli) describe acceso con
una API key del usuario, generada en Settings → Server → Users, y conexión mediante
Connect → CLI. Confirmar que esas opciones existen en la versión instalada antes de
usarlas; no actualizar Easypanel automáticamente para obtenerlas. El acceso root por
SSH no se utilizará para extraer contraseñas, falsificar sesiones ni editar directamente
la configuración interna del panel. Si esa vía no está disponible, configurar los
servicios desde la interfaz con el propietario.

Panel confirmado: `https://panel.soydavidrodriguez.com`; perfil CLI `contabo` conectado.
No pedir contraseñas ni claves por el chat. El propietario introdujo la API key mediante
el CLI en su terminal. La lectura agregada de proyectos no ocultó todos los secretos
anidados: no imprimir resultados completos, incluso con la ocultación predeterminada.
Capturar las respuestas y emitir únicamente campos permitidos (nombre, tipo, estado,
límites, dominios sin tokens). No usar credenciales de servicios ajenos.

## Imágenes y servicios

Construir los targets `backend`, `worker` y `dashboard` del Dockerfile para la arquitectura
verificada. Publicar solo en un registro elegido por el propietario y registrar los
digests resultantes antes de desplegar. No usar `latest`. No incrustar `.env` o credenciales.
Los digests de las imágenes base ya están fijados en el Dockerfile y Compose.

| Servicio nuevo en el proyecto existente | Imagen/comando | Exposición |
| --- | --- | --- |
| PostgreSQL | PostgreSQL compatible con migraciones, volumen persistente | Solo dirección interna |
| Migración puntual | Imagen backend: `alembic upgrade head` | Ninguna |
| API | Imagen backend: `nicheradar-api` | Puerto interno 8000, sin dominio público |
| Worker, una réplica | Imagen worker con ONNX local: `nicheradar-worker` | Sin puerto HTTP |
| Dashboard | Imagen dashboard: `nicheradar-dashboard` | Dominio HTTPS hacia 8501 |

Easypanel admite fuentes de imagen, variables de entorno, dominios y controles de recursos.
Configurar el proceso web en `0.0.0.0` y el puerto interno correcto; usar un digest inmutable.
Proteger el dominio con autenticación del proxy, además de la contraseña de la aplicación.
La API mantiene su token incluso en red interna. Ver [App Service](https://easypanel.io/docs/services/app).

Crear la base y volumen propios; usar el host interno mostrado por Easypanel, sin suponer
que será `postgres`. No habilitar el puerto externo ni reutilizar una base de otras apps.
Ver [Postgres Service](https://easypanel.io/docs/services/postgres). Compose usa PostgreSQL 18
y su montaje `/var/lib/postgresql`; no trasladar sin revisar rutas de otra versión.

**Persistencia comprobada en el destino:** Easypanel monta `/var/lib/postgresql/data`.
Para la imagen PostgreSQL 18 fijada se configuró
`PGDATA=/var/lib/postgresql/data/pgdata`. `SHOW data_directory` y la recreación
efectiva del contenedor confirmaron que los datos permanecen en ese bind mount.
No copiar la configuración a otra versión sin revisar de nuevo montaje y `PGDATA`.
Nunca realizar estas pruebas sobre bases ajenas.

Al crear los servicios App, revisar y quitar cualquier dominio automático de API, worker
y migración **antes del primer Deploy**. Dejar vacía la publicación de puertos de todos los
servicios; el dashboard se publica solo mediante el proxy, no mapeando 8501 al host.
Deshabilitar también dominios alternativos del dashboard que no tengan la misma protección.
Easypanel documenta los dominios automáticos y la autenticación HTTP Basic en Security;
configurar esta última antes de exponer el dashboard, además de su contraseña interna.
Ver [App: dominios y seguridad](https://easypanel.io/docs/services/app).

Mantener Expose de PostgreSQL sin configurar y los administradores PgWeb/DbGate apagados.
Ver [Postgres: red y almacenamiento](https://easypanel.io/docs/services/postgres).

## Configuración inicial

API y worker: `NR_MODE=synthetic`, `NR_RADAR_PAUSED=true`, `NR_TIMEZONE=America/Lima`,
`NR_DATABASE_URL` con esquema `postgresql+psycopg`, `NR_SERVICE_TOKEN` aleatorio,
`NR_EXTERNAL_CONCURRENCY=1`, `NR_WORKER_POLL_SECONDS=30`, `NR_WORKER_MAXIMUM_ATTEMPTS=3`;
API: `NR_API_HOST=0.0.0.0`.
Codificar caracteres reservados si aparecen en la contraseña dentro de la URL de PostgreSQL.

Dashboard: el mismo token de servicio, `NR_API_URL=http://HOST_INTERNO_API:8000`,
`NR_DASHBOARD_HOST=0.0.0.0` y otra contraseña aleatoria `NR_DASHBOARD_PASSWORD`.
Ambos secretos tienen mínimo 32 caracteres y deben ser distintos. Guardarlos solo en el
gestor/configuración privada del entorno. No publicar los valores en capturas o logs.

En API y worker, fijar también `NR_BATCH_SIZE=20` y `NR_LLM_ENABLED=false`; no cargar
credenciales de vidIQ, YouTube o LLM ni rutas de modelos en el smoke test. El worker no
necesita `NR_API_HOST=0.0.0.0`, contraseña del dashboard ni credenciales de publicación.
La migración necesita solo la conexión a la base nueva y la misma imagen backend.
No montar carpetas del Mac, el socket Docker ni directorios de otras aplicaciones.

En Domains del dashboard, configurar el hostname confirmado, ruta `/`, destino HTTP
interno en el puerto 8501, HTTPS y redirección de HTTP a HTTPS. Verificar el certificado
y que la sesión Streamlit mantiene su conexión WebSocket. No desactivar CORS/XSRF para
resolver un problema de proxy. Las opciones precisas deben comprobarse en el Easypanel
instalado; si falta la protección de acceso, no publicar el dominio.

Primero iniciar PostgreSQL, luego ejecutar la migración una vez y comprobar su salida.
Después iniciar API, worker y dashboard. El estado de pausa persistido prevalece en operación:
editar una variable de entorno no debe considerarse una pausa de emergencia de una base activa.
Al restaurar, aplicar obligatoriamente [el procedimiento de recuperación](backup-restore.md).

La migración se ejecuta una vez, sin política de reinicio continuo ni dominio. No utilizar
el worker como migrador. Registrar código de salida 0 y revisión de Alembic antes de iniciar
API/worker. Si falla, mantenerlos detenidos y revisar el error sin imprimir la URL de conexión.
No repetir automáticamente migraciones destructivas ni ejecutar `downgrade` como recuperación.

## Pruebas antes de activar

- API interna: `/health/live` responde; `/api/v1/status` requiere token y muestra pausa.
- Dashboard: HTTPS válido, acceso anónimo sin datos, login correcto, conexión interna a API.
- Worker: `python -m nicheradar.workers.health`; heartbeat reciente y conexión a base disponible.
  Un tick sin progreso por más de cinco minutos da señal de salud fallida con el intervalo inicial.
- Cambiar un dato inocuo del perfil, recrear solo los servicios del radar y comprobar persistencia.
- Comprobar que no aparecen llamadas o cargos y que base/worker no tienen puertos públicos.
- Probar copia y restauración en un volumen/base separados antes de conservar datos reales.

Registrar por servicio digest, arquitectura, límites, comprobación de salud y resultado de
autenticación, sin valores secretos. Confirmar que no hay rutas alternativas que eviten el
proxy. Los comandos `docker service inspect` completos pueden mostrar secretos: inspeccionar
solo campos necesarios de los servicios del radar, como puertos publicados o límites.

La tarea 9.2 queda verificada: imágenes fijadas, comunicación interna, límites,
persistencia y acceso externo autenticado con TLS válido. Tras corregir DNS se
guardó únicamente el dominio con el resolver existente `letsencrypt`, sin reiniciar
el proxy compartido. Ver pruebas y limitaciones en el registro del despliegue.
El probe externo conserva validación TLS y hostname aunque fije la IP para evitar
cachés antiguas; la sesión manual de navegador no se considera realizada por ese probe.

El VPS ejecuta worker y programación sin el dashboard abierto ni el Mac encendido.
Los procesos ya corren en Contabo y el worker está pausado. El pipeline real
y sus condiciones siguen pendientes según la [matriz de proveedores](provider-readiness.md).

## Compose local

Configurar `POSTGRES_PASSWORD`, `NR_SERVICE_TOKEN` y `NR_DASHBOARD_PASSWORD` en un `.env`
privado. Ejecutar `docker compose up --build --wait`. Entrar a `http://127.0.0.1:8501`.
API y dashboard publican puertos únicamente en loopback; PostgreSQL y worker usan una red
aislada. API/dashboard tienen además una red de acceso local para el mapeo de puertos,
siguiendo la separación de [redes Docker](https://docs.docker.com/engine/network/).
No presentar Compose local como equivalente a un despliegue público HTTPS.

`uv run python scripts/smoke_compose.py` crea un proyecto sintético único, prueba salud,
autenticación y persistencia, y elimina exclusivamente su propio volumen temporal al terminar.
Las imágenes de prueba permanecen en la caché local; no se limpian imágenes ajenas.
