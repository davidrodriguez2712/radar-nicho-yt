# NicheRadar

Radar personal de oportunidades de YouTube en inglés, con videos largos y Shorts
evaluados por separado. El flujo conecta catálogo, worker, PostgreSQL, backlog, decisiones
y escenarios. La integración vidIQ live ya pasó un piloto y dos ciclos programados acotados;
el radar desplegado volvió a pausa y conserva ocho entradas reales sin puntuación.
El arranque local predeterminado es sintético y pausado; no consume créditos, crea canales
ni publica videos.

## Desarrollo

Python 3.13 y [uv](https://docs.astral.sh/uv/guides/projects/). Las versiones resueltas
quedan fijadas en `uv.lock`; no se requiere una suscripción de API para desarrollar.

```sh
uv sync --locked
uv run nicheradar-api
uv run nicheradar-dashboard
uv run nicheradar-worker --once
```

Ejecuta cada servicio en una terminal independiente. API en `127.0.0.1:8000`,
dashboard en `127.0.0.1:8501`. `/health/live` es público y no expone datos.
El resto de la API exige Bearer `NR_SERVICE_TOKEN`. El dashboard exige
`NR_DASHBOARD_PASSWORD` y llama a la API con la credencial de servicio.
Ambos secretos deben tener al menos 32 caracteres aleatorios diferentes.
Configura las variables indicadas en `.env.example` en un `.env` privado.
No publiques directamente estos puertos: el despliegue remoto necesita HTTPS y protección
de acceso en el proxy, además de la autenticación de la aplicación.

Configuración con [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
y autenticación de servicio en FastAPI. Sin credenciales la interfaz muestra lo que falta;
no devuelve oportunidades ni secretos. Activar un modo no confirma condiciones de proveedores.

## Verificación

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Las pruebas no consultan servicios externos. Las pruebas de PostgreSQL se ejecutan
solo sobre una base aislada configurada expresamente con `NR_TEST_DATABASE_URL`.
Debe ser local, estar vacía y tener un nombre que empiece por `nicheradar_test`.
Alternativamente, `NR_TEST_POSTGRES_BIN` apunta al directorio que contiene `initdb`
y `pg_ctl`: pytest crea y detiene una instancia temporal con socket privado, sin
escuchar TCP ni tocar bases existentes. Ejemplo con Postgres.app en macOS:

```sh
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest
```

Migraciones mediante [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html),
con transacciones explícitas de [SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/connections.html):

```sh
uv run alembic upgrade head
```

Requiere `NR_DATABASE_URL` configurada. No ejecutes `downgrade` sobre datos reales
sin un respaldo: la reversión de la migración inicial elimina el esquema del radar.
Consulta el avance en `openspec/changes/continuous-niche-discovery/tasks.md`.

## Docker y operación

El entorno Compose local incluye migraciones, comprobaciones de salud y volumen PostgreSQL.
Configura primero los secretos del `.env` privado y ejecuta:

```sh
docker compose up --build --wait
```

El dashboard está en `http://127.0.0.1:8501`. Desde Operación puedes reanudar el radar
sintético para recorrer el catálogo sin créditos. Los resultados de prueba conservan
su etiqueta sintética aunque después cambie el modo global.

La prueba aislada `uv run python scripts/smoke_compose.py` construye imágenes, verifica
autenticación y persistencia tras recrear servicios; elimina solo su proyecto y volumen
temporales. No ejecutar `docker compose down --volumes` sobre una instalación con datos
que quieras conservar.

- [Guía de Easypanel y configuración](docs/deployment-easypanel.md).
- [Contexto y reglas para agentes](AGENTS.md).
- [Preparación de imágenes para Docker Hub](docs/release-dockerhub.md).
- [Usos pendientes y límites de proveedores](docs/provider-readiness.md).
- [Conexión propia y diagnóstico MCP de vidIQ](docs/vidiq-connection.md).
- [Enriquecimiento acotado con YouTube Data API](docs/youtube-enrichment.md).
- [Saldos, renovación y diferencias de consumo](docs/balance-reconciliation.md).
- [Respaldos, restauración aislada y rollback](docs/backup-restore.md).
- [Matriz de fallos, recuperación y concurrencia](docs/failure-verification.md).
- [Rotación, actualización y continuación de descubrimiento](docs/discovery-operation.md).
- [Agrupamiento temático opcional y sus límites](docs/topic-grouping.md).
- [Cambios observados de vistas y concentración](docs/temporal-metrics.md).
- [Recetas, Creator Fit y recursos de producción](docs/creator-fit-rubric.md).
- [Publicidad, puntuación combinada y confianza](docs/advertising-scoring.md).
- [Explicaciones trazables e IA opcional con presupuesto](docs/explanations.md).
- [Comparación de evaluaciones y posiciones históricas](docs/evaluation-history.md).
- [API privada, filtros y estados del observatorio](docs/private-console.md).
- [Operación live acotada](docs/live-operation.md).
- [Release desplegada 011](docs/release-20261001-011.md).
- [Piloto real YouTube/LLM](docs/youtube-llm-pilot-20260927.md).
- [Análisis competitivo de canal](docs/channel-analysis.md).

La candidata 011 está desplegada en Contabo, en modo live y pausada. El Home del
dashboard ahora resume el panorama de oportunidades (conteos por estado, candidatos
ordenados por madurez real) con una tarjeta "Hacia dónde ir ahora" que traduce los
bloqueos reales a lenguaje claro. Suma una ganancia mensual estimada por oportunidad:
rango entre el canal mejor y peor ya compitiendo en el nicho (velocidad de vistas real
observada, nunca una vista asumida) por una tasa publicitaria investigada (RPM real por
fuentes citadas, activado para "culture": US$0,83–3,00/1000 vistas largo, US$0,03–0,10
Shorts), menos el costo real de producción. Sin ese insumo real disponible, muestra
`incomplete` con la razón exacta, nunca un número inventado. Sin migración de esquema.
La release anterior (010) añadió la receta de producción por defecto (Creator Fit): toda
oportunidad nueva sin receta propia recibe automáticamente 7 etapas de IA local/API o
código determinista, con capacidad real de herramientas compartidas (topes de gasto de
US$5/semana en LLM y Gemini, holgura local sin cuello de botella), por lo que el score
resuelve `88.75` y `viable` desde la primera evaluación. YouTube y el enriquecimiento LLM
(modelo `gpt-6-luna`, tope US$5/semana) siguen validados con el piloto real de la release
009: 2 unidades de cuota YouTube y 16 enriquecimientos LLM exitosos, cero errores. Los
topes de créditos vidIQ están en 25/175/350 (ejecución/semana/ciclo). La calibración de
scores, benchmarks publicitarios reales y el respaldo futuro compatible con conservación
siguen pendientes. Consulta [el estado de implementación](docs/implementation-status.md).

## Decisiones iniciales

US$100/mes objetivo, US$150 techo compartido entre radar y producción, 15 horas/semana.
Claude, ChatGPT y Google AI Pro existentes quedan excluidos; no se asume saldo de API.
El catálogo versionado propone familias amplias, no nichos recomendados, y no requiere
temas ingresados. Los futuros escenarios pueden contemplar varios canales simultáneos.
