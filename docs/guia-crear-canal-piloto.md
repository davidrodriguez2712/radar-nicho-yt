# Guía: crear el canal del piloto `gaming_general` (paso a paso)

Para el propietario. Claude **no puede** hacer estos pasos: exigen una cuenta de Google a tu
nombre, aceptar términos, verificar un teléfono y autorizar accesos. Lo que sí hace Claude se marca
al final. Contexto del piloto: [`pilot-brief-gaming-general.md`](pilot-brief-gaming-general.md).
Verificado en la ayuda oficial de YouTube el 2026-10-26; las pantallas de Google cambian, así que
manda lo que veas en pantalla.

**Plazo:** el paquete del piloto vence el **2026-11-09**. Los pasos 1 a 5 se hacen en una tarde.

## 1. Cuenta de Google del canal

1. Usa una cuenta de Google **dedicada** al canal (no la personal). Crear una: <https://accounts.google.com/signup>.
2. Activa la **verificación en dos pasos**: <https://myaccount.google.com/security>. Es requisito
   del Programa de Socios de YouTube (YPP).

## 2. Crear el canal

1. Entra en <https://www.youtube.com> con esa cuenta.
2. Avatar → **Crear un canal** (o <https://www.youtube.com/create_channel>). Elige nombre y
   *handle*. El nombre es público; el subnicho (paso 0 del brief) puede condicionarlo.
3. Sube foto y banner provisionales. Se pueden cambiar sin límite.

## 3. Verificar el teléfono (funciones intermedias)

1. <https://www.youtube.com/verify> → verifica tu número por SMS o llamada.
2. Esto habilita videos de más de 15 minutos y miniaturas personalizadas. Los videos del piloto
   son largos, así que sin este paso no sirve.
3. Funciones avanzadas: se activan solas con historial o con verificación de identidad.
   Ayuda: <https://support.google.com/youtube/answer/9890437>.

## 4. Configurar YouTube Studio

1. <https://studio.youtube.com> → **Configuración → Canal → Información básica**: país, palabras
   clave, idioma **inglés**.
2. **Configuración → Canal → Ajustes avanzados**: audiencia → «No, este contenido no está
   dirigido a niños».
3. **Configuración → Cargas → Valores predeterminados**: idioma del video inglés, categoría
   «Juegos».
4. **Contenido sintético**: si la voz de ElevenLabs imita a una persona real o el video muestra
   algo realista que no ocurrió, hay que marcar la divulgación al subir. Una narración sintética
   genérica no la exige; léete el criterio y decide por video:
   <https://support.google.com/youtube/answer/14328491>. No divulgar de forma reiterada puede
   costar la monetización.
5. Política de contenido reutilizado o inauténtico: es el riesgo principal del dossier. El guion
   de análisis propio no es opcional.

## 5. Monetización: qué esperar (para no confundir el piloto)

Requisitos oficiales hoy (<https://support.google.com/youtube/answer/72851>):

- 1.000 suscriptores **y** 4.000 horas de reproducción válidas en 12 meses (o 10 millones de vistas
  de Shorts en 90 días).
- Aviso: desde el **2026-02-01 de 2027** el umbral para canales nuevos sube a 8.000 horas (o 20
  millones de vistas de Shorts), según la ayuda
  (<https://support.google.com/youtube/answer/12843009>).
- Acceso temprano a financiación de fans: 500 suscriptores y 3.000 horas.

Un piloto de 10 videos en 14 semanas **no llegará a esas cifras**. Por eso la regla `politica-s12`
mira avisos de política y no ingresos. Los ingresos no se miden en este piloto.

## 6. Acceso a la API de YouTube (para que el reporte lea las métricas)

Solo necesario para automatizar `measurement` (AVD, vistas, tráfico). Para empezar se puede
reportar a mano desde Studio.

1. <https://console.cloud.google.com> → proyecto nuevo (p. ej. `canal-gaming`) con la cuenta del canal.
2. **APIs y servicios → Biblioteca**: habilita **YouTube Data API v3** y **YouTube Analytics API**.
3. **APIs y servicios → Pantalla de consentimiento de OAuth** (ahora «Google Auth Platform»): tipo
   *Externo*, agrega tu cuenta como usuario de prueba, alcances de solo lectura
   (`youtube.readonly`, `yt-analytics.readonly`).
4. **Publicar la app** (pasar de «Pruebas» a «Producción»). En modo Pruebas el refresh token caduca
   a los **7 días** y el reporte dejaría de funcionar sola cada semana. Para uso propio no hace
   falta la verificación completa de Google; verás un aviso de «app no verificada».
5. **Credenciales → Crear credenciales → ID de cliente OAuth → Aplicación de escritorio**; descarga
   el JSON.
6. Guarda ese JSON y los tokens **fuera del repo** y de cualquier chat (gestor de contraseñas o
   carpeta privada del proyecto del canal con permisos 0600). Nunca se pegan a Claude.

Duda abierta (sin verificar): si ya hay un proyecto de Google Cloud en `canal-historias`, puede
reutilizarse el proyecto, pero cada canal necesita su propia autorización.

## 7. Carpeta del proyecto del canal

1. Copia `~/Programming/youtube-project/canal-historias` a
   `~/Programming/youtube-project/canal-<slug>` (el id debe ser `canal-[a-z0-9-]{1,40}`, p. ej.
   `canal-gaming-historia`). Ver [`ecosistema-youtube.md`](ecosistema-youtube.md).
2. Ajusta `.foundry/manifest.yaml` (receta y puertas del canal) y `.nicheradar/`.
3. El pipeline de `canal-historias` está hecho para otro nicho: revisa receta, voz y estados antes
   de producir.

## 8. Lo que me das para continuar

- El **id del canal** (`canal-…`) y el subnicho elegido.
- La **lista de estados internos** del pipeline del canal (`source_state`), para escribir su tabla
  de traducción en `translation.py`. Sin ella, todo se ve como `unknown`.
- Confirmación de que el canal existe (nada de claves ni tokens).

## 9. Lo que hago yo después

1. Tabla de traducción de estados del canal + prueba (en una rama, con PR).
2. Con tu aprobación, emitir el **token del canal** (`pilots.py token-issue`, túnel abierto). Se
   imprime una sola vez: lo guardas tú en el gestor de contraseñas; no lo pegues en el chat.
3. Probar `channel_sync.py fetch` y `report` contra producción con ese token.
4. Si el exportador de métricas del canal lo requiere, prepararlo (solo lectura).

## Lista de comprobación

- [ ] Cuenta de Google dedicada con verificación en dos pasos
- [ ] Canal creado
- [ ] Teléfono verificado (videos largos habilitados)
- [ ] Studio configurado (idioma, no para niños, valores de carga)
- [ ] Decidido el subnicho
- [ ] (Opcional ahora) Proyecto de Google Cloud con OAuth publicado
- [ ] Carpeta `canal-<slug>` creada
- [ ] Id del canal y lista de estados enviados a Claude
