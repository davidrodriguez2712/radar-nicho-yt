# Kit de identidad y arranque de un canal nuevo

Fuente canónica de **todo lo que un canal necesita para funcionar** cuando un piloto autorizado no tiene un
canal existente (`target_channel` vacío o un canal que aún no existe). Si el piloto usa un canal que ya existe
(p. ej. `canal-testedoftime` → @TestedOfTime), se omite la parte pública (secciones 1 y 2) y se hace el resto.

**Regla del flujo (pedida por el propietario el 2026-11-10):** el agente prepara el kit **completo** dentro de la
carpeta del canal (`kit-canal/` + `GUIA-CREAR-CANAL.md`) antes de que el propietario cree el canal. El propietario
solo ejecuta lo que exige su identidad (cuenta de Google, teléfono, aceptar términos, autorizar OAuth) copiando y
subiendo lo que el kit le entrega. No se le pide «sube un logo» ni «elige un nombre» sin una propuesta lista.

`foundry init --youtube` crea la guía con este índice; el agente la rellena. Ejemplo completo:
`~/Programming/youtube-project/canal-prehistoric-creatures/GUIA-CREAR-CANAL.md`.

## Cuándo va en el flujo

```text
piloto autorizado (NicheRadar)
  → foundry init --youtube canal-<slug>          (agente)
  → copiar pipeline de canal-historias           (agente, sin credentials/ ni datos/)
  → KIT DE IDENTIDAD: secciones 1 a 3 de abajo   (agente)   ← este documento
  → crear cuenta y canal con la guía             (propietario, ~30 min)
  → OAuth del canal                              (propietario, una vez)
  → tabla de estados + despliegue de la API      (agente, con aprobación)
  → token del canal + fetch del paquete          (agente, con aprobación; antes de valid_until)
  → derechos del material (rights_cleared)       (agente; bloqueante antes del primer video)
  → adaptar prompts y receta al nicho            (agente)
  → primer video
```

## Inventario

| # | Pieza | Especificación | Prepara | Queda en |
|---|---|---|---|---|
| 1.1 | Nombre del canal | Inglés, corto, dice el tema; no tiene que ser único | Agente (3 opciones, 1 recomendada) | `GUIA-CREAR-CANAL.md` |
| 1.2 | Handle | Debe estar libre: `https://www.youtube.com/@<handle>` responde 404. Comprobarlo el mismo día; puede ocuparse | Agente | `GUIA-CREAR-CANAL.md` |
| 1.3 | Descripción | Inglés, máx. 1.000 caracteres; qué se ve, cada cuánto y por qué verlo; sin promesas falsas | Agente | `kit-canal/descripcion.txt` |
| 1.4 | Palabras clave | Inglés, separadas por comas (`dinosaur documentary, paleontology, ice age`), sin comillas: así las pidió el propietario el 2026-11-10 | Agente | `kit-canal/palabras-clave.txt` |
| 1.5 | Ajustes de Studio | País, idioma, audiencia (no para niños), categoría, valores de carga, divulgación de contenido sintético | Agente (valores exactos) | `GUIA-CREAR-CANAL.md` |
| 2.1 | Logo | PNG cuadrado de 800×800; se ve a 98×98 y recortado en círculo; JPG/PNG/BMP/GIF sin animar, ≤15 MB; sin texto pequeño | Agente (generado en local) | `kit-canal/logo.png` |
| 2.2 | Banner | 2560×1440 recomendado (mín. 2048×1152, 16:9). Texto y logo solo en la zona segura central: 1235×338 a 2048 de ancho (1544×423 a 2560). ≤6 MB | Agente | `kit-canal/banner.png` |
| 2.3 | Vista previa del banner | El banner con la zona segura marcada, para revisar antes de subirlo | Agente | `kit-canal/banner-zona-segura.png` |
| 3.1 | Logo del video | El pipeline lo superpone en el video (`RUTA_LOGO_REL`) | Agente | `datos/logo/channels4_profile.jpg` y `_circular.png` |
| 3.2 | Voz del narrador | `referencia.wav` de 5 a 15 s + `referencia.txt` con el texto exacto; la clona Qwen3-TTS (`TTS_LOCAL_*`). Voz propia del canal, diseñada con Qwen3-TTS VoiceDesign (Apache 2.0); no se reutiliza la de otro canal | Agente | `datos/voz_narrador/` |
| 3.3 | Biblioteca de loops | Clips de fondo de 8 s, 1920×1080, 30 fps, H.264, sin audio, con `manifiesto.json` (`archivo`, `categoria`). Con 2-3 segmentos por video y ventana de 12 videos, conviene ≥24 clips en ≥4 categorías. Hechos con imágenes locales y paneo que vuelve al inicio (sin salto al repetir) | Agente | `datos/assets/loops/` |
| 3.4 | Onda de audio | `onda_audio.mp4` (720×1280, 10 s), superpuesta en el video (`RUTA_ONDA_AUDIO_REL`). Se genera en local con `scripts/generar_onda_audio.py` (está en `canal-prehistoric-creatures`; salida propia). No copiar la de `canal-historias`: se hizo con Veo y sus términos no están verificados | Agente | `datos/assets/overlays/` |
| 3.5 | Fuentes tipográficas | Licencia OFL, copiadas con el pipeline | (copiadas) | `assets/fonts/` |
| 4 | Cuenta, canal y teléfono | Cuenta de Google dedicada con verificación en dos pasos; canal; verificación del teléfono (videos de más de 15 min) | **Propietario** | — |
| 5 | OAuth de YouTube | Reutilizar el proyecto de Google Cloud ya publicado; autorizar con la cuenta dueña del canal ([guía](guia-oauth-youtube-permanente.md)) | **Propietario** | `credentials/` del canal (0600) |
| 6 | Conexión con NicheRadar | Canal en `pilots/translation.py` + despliegue de la API; token del canal; `channel_sync.py fetch` | Agente (con aprobación) | Producción y `.nicheradar/inbox/` |
| 7 | Derechos y adaptación | `rights_cleared` en `ok`; prompts, estilos y receta adaptados al nicho. Lo heredado de `canal-historias` que es de su nicho: `scripts/nicho.yaml`, `scripts/competidores.yaml` y sus CSV (inteligencia de competidores), `datos/assets/rostros/` (rostros de miniaturas) y la prueba `tests/test_loops.py`, que fija categorías y número de loops de la biblioteca | Agente | Repo del canal |

Las piezas 3.1 a 3.4 no son opcionales: sin ellas fallan el ensamblado y sus pruebas
(`tests/test_ensamblar.py`, `test_etapa_ensamblado.py`, `test_loops.py`, `test_voz_narrador_asset.py`).
El kit está completo cuando la suite del canal pasa entera.

## Cómo se genera (sin gasto)

- **Imágenes**: Z-Image Turbo 8 bits local (`~/modelos/LEEME.md`, Apache 2.0). El texto del banner y del logo no
  lo dibuja el modelo: se compone con Pillow y las fuentes OFL de `assets/fonts/`.
- **Voz**: `Qwen3TTSModel.generate_voice_design` con `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` y una descripción
  del narrador; el resultado es la referencia que luego clona el modelo `Base`.
- **Loops**: `scripts/crear_loops_desde_imagenes.py` del canal (`ffmpeg` sobre cada imagen `<categoria>_<n>.png`, escribe también `manifiesto.json`): escala a 2112×1188 y recorte 1920×1080 que se desplaza con
  `(1-cos(2πt/8))/2`, así el último fotograma coincide con el primero.

## Fuentes

- Medidas del banner y del logo: [Manage your channel branding](https://support.google.com/youtube/answer/10456525)
  y [Channel banner & profile picture tips](https://support.google.com/youtube/answer/12950272) (consultadas el
  2026-11-10; el límite de 6 MB del banner viene de una versión anterior de la página).
- Contenido sintético: <https://support.google.com/youtube/answer/14328491>.
- Pasos de cuenta, Studio y monetización: [`guia-crear-canal-piloto.md`](guia-crear-canal-piloto.md).
