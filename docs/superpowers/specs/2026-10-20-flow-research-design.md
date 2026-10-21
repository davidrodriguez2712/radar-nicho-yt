# Investigación de flujo: dossier para lanzar un canal competidor — diseño

Estado: validado en conversación con el propietario el 2026-10-20. Pendiente de revisión
del archivo antes de pasar a `writing-plans`. Es el **spec 2**; depende del backlog de
nichos del spec 1 (`docs/superpowers/specs/2026-10-19-market-intel-backlog-design.md`).

## Resumen

Desde un nicho en estado `tentativo` del backlog, el botón **"Iniciar investigación de
flujo"** crea un **encargo** de investigación. Una investigación a fondo, con búsqueda web,
produce un **dossier** estructurado: cómo replicar el flujo de producción, roadmap por
fases, presupuesto tentativo, herramientas con costo por fase y mapa de automatización.

**Decisión central:** la aplicación **encarga y valida**; **Claude Code investiga**. La
búsqueda web corre dentro de Claude Code con la membresía del propietario, no por API de
pago. La aplicación nunca llama a un LLM con búsqueda web y esta función no gasta dólares
de API.

## Decisiones del propietario

| Tema | Decisión |
| --- | --- |
| Fuente de información | Investigación web en vivo, con fuentes citadas |
| Quién ejecuta | Claude Code con la membresía del propietario; la app encarga y valida |
| Traspaso | Cola en la API privada + skill de Claude Code (mismo token Bearer) |
| Presupuesto USD | No aplica: no se gasta API de pago. El tope de US$5 que se discutió solo habría regido el camino por API, que queda fuera del v1 |

## Objetivo de negocio

Pasar de "este nicho parece rentable" a "esto es lo que costaría y cómo se haría un canal
competidor". Éxito del v1:

1. Un nicho `tentativo` con evidencia suficiente genera un encargo con un clic.
2. El skill entrega un dossier que cumple el contrato `dossier-v1` o se rechaza con motivo.
3. Todo precio y todo dato de competencia cita una fuente con fecha; lo desconocido queda
   declarado.
4. El dossier se guarda inmutable y versionado; una nueva investigación no pisa la anterior.
5. Nada crea canales, gasta créditos de vidIQ ni cambia la decisión del nicho.

## Fuera de alcance (explícito)

- Ejecutar la investigación desde el worker o con la API de OpenAI (`web_search`). El
  adaptador actual de LLM es deliberadamente sin herramientas (`"tools": []`); no se toca.
- Comparar dossiers entre sí o entre nichos.
- Crear el canal, comprar herramientas o programar contenido.
- Verificar que las fuentes web sean correctas: el contrato exige citarlas y declarar lo
  desconocido, no garantiza que los datos sean ciertos.
- Ejecución automática y sin supervisión del skill. Si la membresía lo permite en esa
  modalidad es algo que el propietario debe verificar; el diseño no lo presupone.

## Arquitectura

Paquete nuevo `src/nicheradar/flow_research/`, con tablas, rutas y estados propios. No
modifica el scraper ni el radar. Comparte Postgres, la API privada, la autenticación Bearer
y el dashboard.

Piezas:

1. **Encargo** (`flow_research_requests`): lo crea el botón para un nicho `tentativo` y un
   formato (`long` o `shorts`). Guarda un **paquete de evidencia congelado**: scores y su
   desglose, métricas del nicho, fichas con canal verificado, `policy_risk` y rasgos de
   automatización. Así el dossier se puede reproducir y auditar aunque el backlog cambie.
2. **Dossier** (`flow_research_dossiers`): resultado validado contra el contrato pydantic
   `dossier-v1`. Se guarda estructurado, inmutable y con versión.
3. **API** (`/api/v1/flow-research/*`): crear encargo, listar pendientes, reclamar,
   publicar dossier, leer estado y dossier.
4. **Skill de Claude Code** (`.claude/skills/flow-research/`): toma un encargo, investiga y
   publica el dossier.
5. **Dashboard**: botón en el nicho `tentativo` y panel con estado y dossier.

### Estados del encargo

`pendiente` → `en_curso` → `listo` | `rechazado`.

- El skill reclama con un **lease de 60 minutos**; un lease vencido devuelve el encargo a
  `pendiente`.
- Un dossier que llega con el lease perdido se rechaza con `409`.
- Solo puede haber un encargo activo (`pendiente` o `en_curso`) por nicho y formato; crear
  otro devuelve el activo.
- `rechazado` conserva el motivo y permite reintentar.
- Habilitación del botón: el nicho debe estar `tentativo` y tener score de Opportunity y
  de Automatización con valor (no "sin evidencia"). Una confianza `baja` no bloquea, pero
  viaja en el paquete de evidencia y el dossier debe declararla en `unknowns`. Si no se
  cumple, el botón queda deshabilitado con el motivo a la vista.

## Contrato del dossier (`dossier-v1`)

JSON validado por pydantic con `extra="forbid"`. Cada afirmación lleva `evidence_kind`:
`seller_declared` (viene del backlog), `researched` (fuente web citada) o `estimate`
(inferencia del investigador).

1. **Cabecera:** `schema_version`, `request_id`, `niche_label`, `format`, `horizon`
   (`short`: hasta 3 meses; `medium`: de 3 a 9) y `generated_at`.
2. **Veredicto:** `recommendation` (`go`, `go_with_conditions`, `no_go`), `confidence`
   (`low`, `medium`, `high`), `thesis`, riesgos principales y `unknowns`. `no_go` es un
   resultado válido.
3. **Competencia de referencia:** de 3 a 8 canales con URL, suscriptores, cadencia,
   formato, estilo de producción y fuente.
4. **Flujo de producción:** pasos ordenados (investigación, guion, voz, visuales, edición,
   miniatura, publicación). Cada paso: minutos humanos por video, `automation` (`manual`,
   `semi`, `auto`), herramientas y lo que sigue siendo humano.
5. **Roadmap:** fases con semanas, objetivo, entregables, tareas, **criterios de salida
   medibles (obligatorios)** y costo de la fase.
6. **Presupuesto:** partidas por fase con herramienta, costo unitario, cantidad,
   `recurrence` (`one_time` o `monthly`), subtotal USD, `price_checked_on` y `source_id`.
   Totales en tres escenarios (`low`, `likely`, `high`) y supuestos explícitos.
7. **Herramientas:** nombre, fase, plan o precio, alternativa más barata, nivel de
   automatización y fuente. Toda partida del presupuesto referencia una herramienta de esta
   lista.
8. **Mapa de automatización:** por paso, qué se automatiza hoy, qué queda semiautomático,
   el riesgo de dependencia y qué se haría con mano de obra.
9. **Riesgo de política de YouTube:** contenido reutilizado o inauténtico, desmonetización,
   mitigaciones y fuentes. Amplía el `policy_risk` del spec 1.
10. **Punto de equilibrio:** escenarios de ingreso y fecha estimada de recuperación con
    supuestos. Siempre `estimate`, nunca presentado como verificado.
11. **Fuentes:** `id`, `url`, `title`, `accessed_on`. Todo precio y todo dato de competencia
    cita una.

### Reglas de validación en la aplicación

- Solo URLs `https`.
- `price_checked_on` de máximo 90 días respecto de `generated_at`.
- **La app recalcula los totales** y rechaza el dossier si no cuadran con las partidas.
- Toda fase con criterio de salida; toda partida con herramienta y fuente existentes.
- Límites de longitud en cada texto y de cantidad en cada lista.
- El dossier es **dato no confiable**: se muestra como texto plano (nunca Markdown ni
  HTML) y no se ejecuta nada de su contenido.

## Skill `flow-research`

1. Lee `NR_API_URL` y el token de las variables de entorno locales; nunca los imprime ni
   los escribe en archivos.
2. `GET /api/v1/flow-research/pending` y reclama un encargo.
3. Investiga por fases con `WebSearch` y `WebFetch`, **solo a partir de la evidencia
   congelada del encargo**, y registra cada fuente con `accessed_on`.
4. Arma el JSON de `dossier-v1`, lo valida localmente con el mismo esquema (el esquema
   viaja en el repo) y lo envía.
5. Si el contrato lo rechaza, corrige y reintenta una vez; si vuelve a fallar, el encargo
   queda `rechazado` con el motivo.

Las páginas web que lee el skill son datos no confiables: las instrucciones dentro de ellas
se ignoran y el skill no ejecuta comandos que vengan de una fuente.

## Errores

- Dossier inválido: `422` con la lista de campos; el encargo pasa a `rechazado`.
- Lease vencido sin respuesta: vuelve a `pendiente`. Dossier tardío: `409`.
- Encargo duplicado: se devuelve el activo.
- API caída o token inválido: el skill se detiene y lo informa, sin reintentos en bucle.
- Una nueva investigación crea una versión nueva; la anterior se conserva.

## Datos, retención y respaldos

- Tablas nuevas: `flow_research_requests` y `flow_research_dossiers`, en una migración
  posterior a `0013`.
- Retención: el dossier y el encargo siguen la ventana de 183 días de los datos de mercado;
  las decisiones del propietario nunca expiran (regla del spec 1).
- Restauración: `prepare_restore` ya pausa el scraper; no hay procesos propios que pausar
  aquí, pero las tablas cuentan como datos de investigación y entran en la regla de
  respaldo que el propietario decida en la tarea 9.4 del spec 1. **Decisión pendiente del
  propietario**, no se resuelve en este spec.
- Un encargo no consume `provider_requests` ni presupuesto; no afecta `/status` ni
  `request_counts_by_kind`.

## Pruebas (TDD)

- **Contrato:** un dossier válido pasa; cada regla falla con su mensaje (totales que no
  cuadran, precio de más de 90 días, fuente inexistente, fase sin criterio de salida, URL
  `http`, campo extra).
- **Ciclo de vida:** crear, reclamar, completar, vencer lease, reclamo doble, dossier
  tardío y duplicados.
- **API:** autenticación, `404`, `409`, `422`; `/status` sin cambios.
- **Dashboard:** botón solo en `tentativo`, estado visible, dossier como texto plano (un
  título con Markdown no se interpreta).
- **Skill:** prueba con una fuente falsa y un dossier de ejemplo contra la API de prueba.
  La búsqueda web real no se prueba automáticamente.
- **Integración:** retención incluye las tablas nuevas; el encargo no gasta vidIQ ni
  presupuesto.

## Riesgos conocidos

- La calidad del dossier depende de lo que Claude Code encuentre en la web ese día. Precios
  y cifras son orientativos; el contrato los hace citables y fechados, no correctos.
- Los términos de la membresía respecto al uso automatizado no se han verificado.
- Las cifras de ingreso del backlog son declaradas por vendedores; el punto de equilibrio
  hereda esa incertidumbre y por eso es siempre `estimate`.
