# Preparación de release — Docker Hub

Destino elegido por David: `davidrodriguez2712`. Autorizada la publicación inicial
**pública**, con intención de pasar a privada tras las pruebas. El propietario entiende
que ese cambio no revoca copias ya descargadas. No se compra capacidad ni se cambia
visibilidad automáticamente.

La candidata activa es `v1-candidate-20260915-002`, publicada para amd64 y verificada
en Contabo. La 001 se conserva como versión anterior. Ver [registro de 002](release-20260915-002.md).
Las instrucciones siguientes sirven para futuras releases, sin sobrescribir etiquetas.

## Antes de publicar

1. Mantener pública la primera publicación, según autorización del propietario. Antes de
   pasar a privada, verificar disponibilidad en la cuenta sin contratar un plan automáticamente.
2. Crear o comprobar los repositorios `nicheradar-backend` y `nicheradar-dashboard` dentro
   de la cuenta elegida. No confiar en el comportamiento de creación implícita de un push.
3. Autenticar Docker localmente como `davidrodriguez2712`, sin compartir credenciales en el
   chat. Para un registro privado en Easypanel, configurar aparte acceso de solo lectura;
   el servidor no necesita permiso de publicación.

Docker permite elegir la visibilidad al [crear un repositorio](https://docs.docker.com/docker-hub/repos/create/).
El comando siguiente pide la credencial de forma interactiva; no añadirla como argumento.
Usar el mecanismo admitido por la cuenta, incluido un token cuando corresponda. Ver
[autenticación de Docker CLI](https://docs.docker.com/reference/cli/docker/login/).

```sh
docker login --username davidrodriguez2712
```

No copiar la configuración de autenticación Docker a una imagen ni al repositorio.

## Construcción local sin publicación

Trabajar sobre una copia de código revisada que no cambie durante la release. Elegir una
etiqueta nueva en cada intento publicado y registrar el código/lockfile exactos. `v1-candidate-001`
es un ejemplo, no una versión ya construida o un identificador de fuente confirmado.

El VPS observado es amd64; especificar su plataforma al construir desde el Mac.
`--load` carga la imagen en Docker local y no la publica. Ver
[plataformas Docker](https://docs.docker.com/build/building/multi-platform/) y
[opciones de Buildx](https://docs.docker.com/reference/cli/docker/buildx/build/).

```sh
docker buildx build --platform linux/amd64 --target backend --load --tag davidrodriguez2712/nicheradar-backend:v1-candidate-001 .
docker buildx build --platform linux/amd64 --target dashboard --load --tag davidrodriguez2712/nicheradar-dashboard:v1-candidate-001 .
docker image inspect --format '{{.Os}}/{{.Architecture}}' davidrodriguez2712/nicheradar-backend:v1-candidate-001
docker image inspect --format '{{.Os}}/{{.Architecture}}' davidrodriguez2712/nicheradar-dashboard:v1-candidate-001
```

Comprobar `linux/amd64` en ambas. No utilizar un constructor remoto o de pago sin aprobarlo.
Revisar `.dockerignore` y los `COPY` del Dockerfile: no incluir `.env`, claves, backups,
datos de usuarios ni credenciales mediante `ARG`/`ENV`. Las exclusiones no sustituyen
una revisión del código, dependencias y contenido final antes de distribuirlo.

Ejecutar calidad estática, suite PostgreSQL y smoke de Compose aislado antes de publicar.
Sin opciones, el smoke construye sus propias imágenes. Para probar la candidata exacta
ya construida, sin reconstruirla ni descargar otra versión:

```sh
uv run python scripts/smoke_compose.py --backend-image davidrodriguez2712/nicheradar-backend:v1-candidate-20260915-001 --dashboard-image davidrodriguez2712/nicheradar-dashboard:v1-candidate-20260915-001 --platform linux/amd64
```

El PostgreSQL fijado en Compose debe estar descargado para esa plataforma antes de esta
prueba (`--pull never`). El script ignora el `.env` local, genera credenciales inventadas
y elimina únicamente su proyecto y volumen temporal. Las imágenes candidatas se conservan.
Esto no prueba el pull desde Docker Hub ni el arranque en Contabo. La aceptación remota
debe comprobar los digests publicados, con modo sintético y programación pausada.

## Publicación explícita y referencias inmutables

**No ejecutar este bloque hasta confirmar visibilidad, acceso y aprobación de publicación.**
No reutilizar etiquetas de releases previas ni cambiar a `latest`.

```sh
docker push davidrodriguez2712/nicheradar-backend:v1-candidate-001
docker push davidrodriguez2712/nicheradar-dashboard:v1-candidate-001
docker buildx imagetools inspect davidrodriguez2712/nicheradar-backend:v1-candidate-001
docker buildx imagetools inspect davidrodriguez2712/nicheradar-dashboard:v1-candidate-001
```

Guardar el digest remoto que devuelve el registro, no el ID local de configuración de
imagen. En Easypanel usar `davidrodriguez2712/nicheradar-backend@sha256:<digest-verificado>`
para API, worker y migración; el digest dashboard correspondiente para la interfaz.
Los textos entre `<...>` son marcadores, no referencias desplegables. Easypanel admite
fuentes Docker Image con versiones o digests fijados y credenciales para registros
privados. [Configuración de imágenes](https://easypanel.io/docs/services/app).

## Registro de aceptación por completar

- Etiqueta y fecha de construcción: registradas para `v1-candidate-20260915-001`.
- Huella verificable del código y checksum de `uv.lock`: registrados en la candidata.
- Digests remotos backend/dashboard y arquitectura: verificados para la candidata.
- Visibilidad inicial pública: confirmada. Descarga y ejecución desde el VPS: verificadas.
- Imagen/digest PostgreSQL, montaje y `PGDATA`: verificados en el destino.
- Migración 0008 y arranque sintético pausado en VPS: comprobados.
- Autenticación interna, ausencia de puertos públicos y persistencia: comprobadas.
  DNS autoritativo, certificado, acceso público autenticado y handshake WebSocket:
  verificados contra el VPS; caché DNS local antigua y sesión manual pendientes.
- Digest anterior compatible para rollback: no existe una release anterior a esta candidata.

Ver [registro del despliegue inicial](deployment-20260915.md) para alcance y evidencia.

Volver a [la guía de Easypanel](deployment-easypanel.md) para configuración y controles.
No activar consultas pagadas ni copiar datos reales mientras esos controles sigan pendientes.
