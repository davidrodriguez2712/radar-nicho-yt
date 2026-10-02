# Agrupamiento temático opcional

La tarea 5.5 conecta el agrupamiento al pipeline y conserva sus resultados en SQL.
Las pruebas utilizan vectores inventados para verificar contratos e identidades; no
demuestran calidad semántica, rentabilidad ni rendimiento de un modelo real.

## Comportamiento

El worker deduplica y limita el conjunto de videos. Primero aplica exclusiones léxicas
explícitas y usa similitud semántica local únicamente para resolver relevancia desconocida.
Con modelo, solo agrupa evidencia elegible según relevancia, idioma, formato y ventana. Los elementos no verificables se
conservan como un grupo sin clasificar. Los grupos demasiado pequeños se identifican
como ruido. No se generan títulos de subnichos para rellenar esos resultados.

Un modelo versionado codifica títulos/descripciones truncados. El algoritmo determinista
`bounded-greedy-v2` usa similitud coseno, un umbral y un tamaño mínimo. Es una heurística
dependiente del orden estable por identificador, no una validación estadística del nicho.
La identidad incorpora miembros y método; una correspondencia única con un centroide
anterior permite conservarla aunque cambien los videos. La comparación separa familia,
perfil, modo, idioma y configuración del método.

Una coincidencia con varios grupos anteriores, o dos grupos nuevos que parecen dividir
uno anterior, queda ambigua: se registran relaciones sin fusionar oportunidades. Una
actualización ambigua de un seleccionado conserva la evaluación y decisión anteriores,
registra la evidencia nueva y deja el lote parcial. Ruido, desconocidos y ambigüedades
no obtienen una evaluación de subnicho respaldada. Las métricas siguen separadas por
formato aunque ambos formatos puedan pertenecer al mismo tema.

Las etiquetas son opcionales y no definen la identidad. El camino semántico deja la
etiqueta vacía; el etiquetado LLM pertenece a la integración opcional pendiente, no se
ha activado. La alternativa sin modelo muestra la categoría del proveedor como tal.

## Configuración y límites

El target Docker `worker` instala el extra `embeddings` y una variante ONNX cuantizada
por arquitectura de `sentence-transformers/paraphrase-MiniLM-L3-v2`, fijada a la revisión
`4ca70771034acceecb2e72475f72050fcdde4ddc`. Cada archivo se comprueba por SHA-256 durante
la construcción. La [ficha oficial del modelo](https://huggingface.co/sentence-transformers/paraphrase-MiniLM-L3-v2)
declara licencia Apache-2.0 y 384 dimensiones. API y dashboard no incluyen el modelo. Fuera de esa imagen, la ausencia
de configuración conserva la alternativa explícita por categoría del proveedor.

| Variable | Valor inicial | Límite |
| --- | --- | --- |
| `NR_EMBEDDING_MODEL_DIRECTORY` | Sin configurar | Directorio local existente |
| `NR_EMBEDDING_MODEL_VERSION` | Sin configurar | Obligatoria junto con el directorio |
| `NR_EMBEDDING_BATCH_SIZE` | 16 | 1–32 textos por lote del modelo |
| `NR_TOPIC_RELEVANCE_THRESHOLD` | 0,35 | Mayor que 0, hasta 1 |
| `NR_TOPIC_MINIMUM_SIZE` | 3 | 2–200, no mayor que el lote |
| `NR_TOPIC_SIMILARITY_THRESHOLD` | 0,8 | Mayor que 0, hasta 1 |
| `NR_TOPIC_MAXIMUM_VIDEOS` | 200 | 2–200 |
| `NR_TOPIC_MAXIMUM_TEXT_CHARS` | 2000 | 100–4000 por video |

El runtime ONNX usa CPU, un solo hilo y archivos exclusivamente locales; no descarga modelos
ni ejecuta código remoto. Una exclusión léxica explícita nunca se revierte por similitud.
El proceso conserva en caché como máximo un modelo configurado; cambiar archivos bajo
la misma versión no es válido: usar otra versión y reiniciar el worker. Si la carga falla,
se usa `model_unavailable`; la ausencia de configuración usa `model_not_configured`.
Un fallo de codificación o vector inválido produce `embedding_failed`, sin copiar el
texto de la excepción. No se compran recursos ni se llama a un modelo remoto.

Se admiten vectores de hasta 1024 dimensiones. La comparación histórica considera hasta
200 temas compatibles; si hay más, se usa `history_limit` y la alternativa por categoría,
sin ocultar candidatos que podrían hacer ambigua una correspondencia. Los videos que
exceden el lote se omiten en orden estable y su cantidad queda visible; el resultado no
representa cobertura exhaustiva ni un muestreo estadísticamente representativo.

La variante arm64 local codificó 200 textos en 0,085 s con 109,1 MiB de pico dentro de un
contenedor limitado a 512 MiB. La variante amd64 procesó los 100 videos retenidos en el VPS
en 3,602 s con 172 MiB de pico. La calibración agregada separó los controles ajenos por
debajo de 0,35 y produjo 4 candidatos largos y 5 Shorts sobre ese umbral; esto verifica
recursos y un corte inicial, no calidad estadística ni exhaustividad.

## Evidencia, conservación e interfaz

`topic_artifacts` guarda centroide, miembros, método, parámetros y relaciones con
artefactos previos. La migración `0004` añade `topic_artifact_sources`, que enlaza todas
las observaciones utilizadas: no basta con una única fuente principal.

Cada artefacto vence como máximo con su fuente de menor plazo. Si se acorta o revoca
cualquier fuente, la limpieza elimina el artefacto completo y sus enlaces. Los datos
vencidos tampoco se usan para nuevas correspondencias. Las evaluaciones enlazan las
fuentes de su agrupamiento además de las estadísticas; las decisiones propias no se
eliminan. Las referencias a artefactos anteriores son identificadores, no copias de sus
vectores: después de expirar pueden dejar de ser reconstruibles.

El detalle del backlog muestra método, límites y correspondencias sin volcar los
vectores. Operación muestra alternativa utilizada, videos omitidos, ruido y ambigüedades.
Los checkpoints no guardan títulos, descripciones ni centroides. La integración conserva
solo conteos del verificador semántico en los criterios de cohorte; los textos permanecen
sujetos a su procedencia y conservación.

Aplicar `uv run alembic upgrade head` únicamente en la base del radar antes de usar el
worker actualizado. No ejecutar la reversión de `0004` sin evaluar la pérdida de enlaces
de procedencia. Las pruebas de migración y restauración usan bases temporales aisladas.

Verificación: `tests/test_topic_pipeline.py`, `tests/test_topics_backlog.py`, pruebas de
API/dashboard y batería completa de conservación, persistencia y recuperación.
