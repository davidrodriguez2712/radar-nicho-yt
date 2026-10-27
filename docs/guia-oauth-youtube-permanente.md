# Guía: OAuth de YouTube que no caduca cada 7 días

Para el propietario. Complementa el paso 6 de [`guia-crear-canal-piloto.md`](guia-crear-canal-piloto.md).
Fuente: documentación oficial de Google (consultada el 2026-10-26):
[caducidad de refresh tokens](https://developers.google.com/identity/protocols/oauth2#expiration) y
[publicar la app](https://support.google.com/cloud/answer/15549945).

## Por qué caduca a los 7 días

Un proyecto de Google Cloud con la pantalla de consentimiento en estado **«Pruebas»** (*Testing*)
emite refresh tokens que caducan a los **7 días**. Solo se libran los alcances básicos (`openid`,
correo y perfil). Los alcances de YouTube (`youtube.readonly`, `yt-analytics.readonly`) no lo son.
Cada semana el exportador del canal fallaría con `invalid_grant` hasta volver a autorizar.

## La solución: pasar la app a «En producción»

Para **uso propio** (una app tuya que lee tu propio canal) no necesitas la verificación completa de
Google. Se publica la app y se acepta el aviso de «app no verificada».

### Paso a paso (verificado con la consola real el 2026-10-26)

1. Entra en <https://console.cloud.google.com> y crea un **proyecto nuevo** por canal (p. ej.
   `canal-gaming-yt`). Puede estar en cualquier cuenta tuya: la que autoriza en el paso 7 es la
   dueña del canal, no la del proyecto.
2. **APIs y servicios → Biblioteca**: habilita **YouTube Data API v3** y **YouTube Analytics API**.
3. **Google Auth Platform → Comenzar**: nombre de la app, correo de asistencia, **Público: Externo**,
   correo de contacto.
4. **Acceso a los datos** → añade solo estos dos permisos de lectura:
   - `https://www.googleapis.com/auth/youtube.readonly`
   - `https://www.googleapis.com/auth/yt-analytics.readonly`
5. **Información de la marca**. **No se puede dejar en blanco**: sin nombre, correo de asistencia,
   **página principal** y **política de privacidad** el botón *Publicar app* sigue deshabilitado
   («Se requieren un nombre de app, un correo electrónico de asistencia, una URL de página principal y
   una URL de política de privacidad válidos»). Hacen falta dos páginas públicas y su dominio en
   **Dominios autorizados**. Lo más simple es un sitio estático mínimo en Vercel (`*.vercel.app`, que
   Google acepta como dominio autorizado). Ejemplo ya publicado para el canal gaming:
   `https://canal-gaming-sync.vercel.app/` y `…/privacy.html`; dominio autorizado
   `canal-gaming-sync.vercel.app`. Deja vacíos el logotipo (subirlo obliga a verificar) y las
   condiciones del servicio.
6. **Clientes → Crear cliente → App de escritorio**. Descarga el JSON y guárdalo fuera del repo, en
   `~/Library/Application Support/NicheRadar/oauth/` (carpeta 0700, archivo 0600).
7. **Público → Publicar app** → confirmar. El estado pasa a **«En producción»**. Aparecerá un banner
   «Tu app requiere una verificación»: se ignora para uso propio. No pulses «Prepare for
   verification».
8. Autoriza **una sola vez** con la cuenta dueña del canal, ya en producción:

   ```sh
   uv run python scripts/youtube_oauth.py authorize
   ```

   Abre el navegador. Verás «Google no ha verificado esta app» → **Avanzado** → **Ir a … (no seguro)**
   → marca los dos permisos → **Continuar**. Si el canal es de marca, elige el canal correcto. El
   script guarda el refresh token en `~/Library/Application Support/NicheRadar/oauth/canal-gaming-token.json`
   (0600) y no imprime ningún secreto.
9. Comprueba que funciona contra las dos APIs:

   ```sh
   uv run python scripts/youtube_oauth.py check
   ```

   Muestra el id y el título del canal y si Analytics responde.

## Permiso para subir videos (`--upload`, decisión A2 del 2026-10-26)

Cuando el agente sube los videos por API hace falta un tercer permiso, de **escritura**:
`https://www.googleapis.com/auth/youtube.upload`. No va por defecto.

1. En **Google Auth Platform → Acceso a los datos → Agregar o quitar permisos**, añade
   `youtube.upload` (junto a los dos de lectura) y guarda. La app ya publicada sigue «En producción».
2. Autoriza de nuevo con la bandera, con la cuenta dueña del canal:

   ```sh
   uv run python scripts/youtube_oauth.py authorize --upload --force
   ```

   Si Google no concede el permiso, el script falla y **no** guarda el token. `--force` reemplaza el token
   de solo lectura anterior.
3. Comprueba: `uv run python scripts/youtube_oauth.py check` debe mostrar `"upload_scope": true`.

**Restricción de YouTube (verificada en la documentación de `videos.insert`):** los videos subidos por API
desde un proyecto no verificado creado después del 2020-07-28 quedan **restringidos a privado** hasta que el
proyecto pasa una auditoría de cumplimiento. `canal-gaming-yt` es nuevo; mientras no se apruebe la
auditoría, la publicación pública no es automática. Ver el contrato
[`channel-onboarding-v1`](contracts/channel-onboarding-v1.md), sección «Subida por API».

## Qué lo hace «permanente» y qué todavía lo puede invalidar

Un refresh token de una app en producción **no tiene** el límite de 7 días. Sigue dejando de
funcionar si:

| Causa | Qué hacer |
|---|---|
| Lo revocas en <https://myaccount.google.com/permissions> | No revocarlo; si lo haces, autorizar de nuevo |
| **Seis meses sin usarse** | El reporte semanal ya lo usa; no dejar el canal parado medio año |
| Superas **100 refresh tokens vivos** por cliente | No autorizar en bucle: reutiliza el token guardado |
| Cambias contraseña **y** el token tiene alcances de Gmail | No aplica: no pedimos Gmail |
| Un administrador restringe el servicio (Workspace) | Usa una cuenta Google normal, no de organización |

Límite de las apps no verificadas: **100 usuarios nuevos en total** (tope que no se reinicia).
Con una sola cuenta (la tuya) es irrelevante. Para canales de terceros habría que pedir la
verificación de Google (nombre, logo, política de privacidad y justificación de alcances).

## Buenas prácticas para el exportador del canal

- Guardar el refresh token una vez y pedir *access tokens* nuevos con él; no volver a autorizar.
- Si Google responde `invalid_grant`, no reintentar en bucle: marcar el check `youtube_oauth` con
  `ok: false` en el reporte (campo `checks[]` de `channel-report`) y avisarte.
- Rellenar `expires_at` del check solo si el estado fuera «Pruebas» (7 días). En producción va `null`.
- Un canal, un cliente de OAuth. No compartir el token entre canales.

## Cómo comprobarlo

1. En **Público** el estado dice **En producción**.
2. Autorizas, esperas más de 7 días y el exportador sigue obteniendo métricas sin pedirte nada. Si
   al octavo día falla con `invalid_grant`, la app seguía en «Pruebas»: vuelve al paso 4.

## Alternativa descartada: tipo de usuario «Interno»

Solo existe para cuentas de Google Workspace de una organización y el canal tendría que ser de esa
organización. No encaja con un canal propio y una cuenta dedicada.
