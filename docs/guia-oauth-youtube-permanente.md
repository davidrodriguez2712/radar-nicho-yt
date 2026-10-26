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

### Paso a paso

1. Entra con la cuenta de Google del canal en <https://console.cloud.google.com> y selecciona el
   proyecto del canal (p. ej. `canal-gaming`).
2. Abre **Google Auth Platform** (antes «Pantalla de consentimiento de OAuth»):
   <https://console.cloud.google.com/auth/overview>. Si te lo pide, completa la configuración: nombre
   de la app, correo de asistencia, **Público: Externo**, correo de contacto.
3. **Acceso a los datos** (*Data Access*) → **Agregar o quitar alcances** → añade solo:
   - `https://www.googleapis.com/auth/youtube.readonly`
   - `https://www.googleapis.com/auth/yt-analytics.readonly`

   Nada de escritura (`youtube`, `youtube.upload`) si el canal no va a subir videos por API. Menos
   permisos, menos riesgo si se filtra el token.
4. **Público** (*Audience*): estado de publicación → botón **Publicar la aplicación** (*Publish app*)
   → confirmar. El estado debe pasar de «Pruebas» a **«En producción»**.
5. **Clientes** (*Clients*) → **Crear cliente** → tipo **Aplicación de escritorio**. Descarga el JSON
   del cliente. Si ya habías creado el cliente en modo Pruebas, **no sirve el token viejo**: hay que
   autorizar de nuevo después de publicar.
6. Autoriza **una vez**, ya en producción, con tu cuenta del canal. Verás «Google no ha verificado
   esta app» → **Avanzado** → **Ir a <nombre de la app> (no seguro)** → marca los dos permisos →
   **Continuar**. Si la cuenta tiene un canal de marca (*brand account*), elige el canal correcto en
   la pantalla de selección.
7. Guarda el **refresh token** y el JSON del cliente fuera del repo, con permisos 0600 (carpeta
   privada del canal o gestor de contraseñas). Nunca en el chat ni en `git`.

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
