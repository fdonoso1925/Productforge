# Deploy: Supabase + Railway + Netlify

Tres piezas, en este orden: **Netlify** (te da la URL del frontend) → **Railway** (API + worker, te da
la URL del backend) → volver a Netlify con la URL del backend. Supabase ya está creado.

Ningún secreto va al repo: todo se pone en los paneles de cada servicio.

## 0. Antes de empezar

- El repo está en GitHub y `main` tiene el CI en verde (incluye la construcción de la imagen Docker).
- Ya aplicaste las migraciones en Supabase (`npx supabase db push`) y tu usuario existe
  (*Authentication → Users*).
- Tienes a mano: URL y claves de Supabase, `ANTHROPIC_API_KEY`, y (si usas Drive) el ID y secreto de
  cliente de Google.

## 1. Netlify (frontend)

1. *Add new site → Import an existing project* → elige el repo. Netlify lee `netlify.toml`
   (carpeta base `frontend`, Node 22) y detecta Next.js.
2. *Site configuration → Environment variables*:

   | Variable | Valor |
   |---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | URL del proyecto Supabase (`https://xxxx.supabase.co`) |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | clave pública (*publishable* / anon) de Supabase |
   | `NEXT_PUBLIC_API_URL` | la URL de Railway del paso 2 (déjala vacía por ahora) |
   | `NEXT_PUBLIC_CONTACT_EMAIL` | opcional: contacto que sale en `/privacy` |

   Las `NEXT_PUBLIC_*` se incrustan **al compilar**: cada vez que las cambies hay que volver a
   desplegar (*Deploys → Trigger deploy*).
3. Despliega y anota la URL (`https://<sitio>.netlify.app`).

## 2. Railway (API + worker)

Dos servicios del mismo repo y la misma imagen (`backend/Dockerfile`, contexto = raíz).

**Servicio `api`**
1. *New project → Deploy from GitHub repo*. Railway lee `railway.json` (Dockerfile, healthcheck
   `/health`).
2. *Settings → Networking → Generate domain*. Anota la URL (`https://<api>.up.railway.app`).
3. *Variables*:

   | Variable | Valor |
   |---|---|
   | `SUPABASE_URL` | URL del proyecto Supabase |
   | `SUPABASE_SERVICE_ROLE_KEY` | clave `service_role` / secret (**solo aquí**, nunca en Netlify) |
   | `ALLOWED_EMAILS` | tu email |
   | `ANTHROPIC_API_KEY` | tu clave |
   | `CORS_ORIGINS` | la URL de Netlify, sin barra final |
   | `FRONTEND_URL` | la URL de Netlify |
   | `WORKER_INLINE` | `false` |
   | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | del cliente OAuth de Google |
   | `GOOGLE_REDIRECT_URI` | `https://<api>.up.railway.app/storage/drive/callback` |
   | `TOKEN_ENCRYPTION_KEY` | la misma clave Fernet que usas en local (si la cambias, hay que reconectar Drive) |

   **Creativos para Meta Ads** (opcional; sin estas variables el módulo igual funciona con plantillas
   de solo texto):

   | Variable | Valor |
   |---|---|
   | `PIXABAY_API_KEY` | clave gratis de https://pixabay.com/api/docs/ (fotos de stock) |
   | `IMAGE_PROVIDERS` | `pixabay` (por defecto). `gemini,pixabay` solo si quieres imágenes generadas |
   | `GEMINI_API_KEY` | solo si usas Gemini (**cobra**: no hay cuota gratis para imágenes) |
   | `GEMINI_DAILY_USD_CAP` | tope diario en USD. **`0` = Gemini apagado aunque haya clave** (por defecto) |

   Las claves viven solo en el backend. `GEMINI_IMAGE_MODEL` y `GEMINI_IMAGE_PRICE_USD` tienen
   valores por defecto (ver `.env.example`).

   Opcionales: `CLAUDE_MODEL_OUTLINE`, `CLAUDE_MODEL_CONTENT`, `CLAUDE_EFFORT`,
   `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_HOUR`. Si tu proyecto Supabase usa el secreto JWT legacy
   (HS256), agrega `SUPABASE_JWT_SECRET`; con claves asimétricas (lo normal hoy) se deja vacío.

   La imagen corre con `ENVIRONMENT=production`: **si falta o es inseguro algo de la tabla (URL local,
   clave vacía, CORS con `localhost`…), el servicio no arranca** y el log dice exactamente qué.

**Servicio `worker`** (el que genera paquetes y sube a Drive)
1. En el mismo proyecto: *New → GitHub repo* (el mismo repo).
2. *Settings → Config-as-code → Railway Config File* = `railway.worker.json` (arranca
   `python -m app.worker`, sin puerto ni healthcheck).
3. Variables: las **mismas** que `api` (puedes usar *Shared variables* o referencias
   `${{api.NOMBRE}}`). No necesita dominio público.

> Alternativa más barata: un solo servicio con `WORKER_INLINE=true` en `api` y sin `worker`. Funciona
> igual para uso personal, pero la generación (WeasyPrint) compite por CPU con la API y un reinicio
> durante una generación obliga a esperar el reintento del job (15 min).

## 3. Cerrar el círculo

1. **Netlify**: pon `NEXT_PUBLIC_API_URL` = URL de Railway y vuelve a desplegar.
2. **Supabase → Authentication → URL Configuration**: *Site URL* = URL de Netlify.
3. **Supabase → Authentication → Sign In / Providers**: desactiva *Allow new users to sign up*
   (además hay un trigger que rechaza emails que no estén en `app_allowed_emails`; confirma que tu
   email está en esa tabla de producción).
4. **Google Cloud → Credenciales → tu cliente OAuth**: agrega en *URI de redirección autorizados*
   `https://<api>.up.railway.app/storage/drive/callback` (déjala junto a la de `localhost`).
5. Entra a la URL de Netlify e inicia sesión. Si producción usa el **mismo proyecto Supabase** que
   en local y la **misma** `TOKEN_ENCRYPTION_KEY`, Drive ya aparece conectado (los tokens están en la
   base, cifrados). Si usas otro proyecto o otra clave, conéctalo de nuevo en *Ajustes*.

## 4. Publicar la app de Google (opcional, evita reconectar cada 7 días)

En modo *Prueba*, Google vence el acceso a los 7 días. Para publicarla, *Google Auth Platform → Marca*
exige URL de página principal y de política de privacidad:

- Página principal: `https://<sitio>.netlify.app`
- Política de privacidad: `https://<sitio>.netlify.app/es/privacy` (pública, sin sesión)

Luego *Público → Publicar app*. `drive.file` no es un permiso sensible, así que no pide revisión. Si
Google exige que el dominio esté en *Dominios autorizados* y `netlify.app` no te deja (es un dominio
compartido), hace falta un dominio propio apuntando a Netlify; sin eso, la reconexión semanal sigue.

## 5. Verificación

- `https://<api>.up.railway.app/health` → `{"status":"ok"}`; `/docs` → 404 (apagado en producción).
- Login en Netlify, crear un paquete corto, ver el progreso y descargar el ZIP.
- Subida a Drive: el paquete muestra «Drive: N de N archivos».
- Anuncios: en `/ads` aparece la línea «Fotos: Pixabay (gratis) · Gemini apagado (sin gasto)»; crea un
  lote corto, compón las imágenes y descarga el ZIP + CSV.
- Logs de Railway: sin tokens ni claves; el callback de Google no muestra `code` ni `state`.

## 6. Conectar Meta Ads (opcional)

La app crea campaña, conjunto y anuncios **siempre en pausa** y lee las métricas sola. Necesitas una
cuenta publicitaria y una página de Facebook; el resto se crea una sola vez:

1. **Business Manager**: https://business.facebook.com → *Configuración del negocio*. Si la cuenta
   publicitaria y la página aún no están dentro, agrégalas (*Cuentas → Cuentas publicitarias / Páginas*).
2. **App**: https://developers.facebook.com/apps → *Crear app* → caso de uso **Otro** → tipo **Empresa**,
   vinculada a tu Business Manager. No hace falta publicarla ni pasar la revisión de Meta: con acceso
   estándar basta para operar tus propias cuentas.
3. **Usuario del sistema**: Business Manager → *Usuarios → Usuarios del sistema → Agregar* (rol
   Administrador). Asígnale la app, la cuenta publicitaria (control total) y la página.
4. **Token**: en ese usuario, *Generar token* → elige tu app → permisos **`ads_management`** (y
   `ads_read`) → expiración *Nunca*. Cópialo **una sola vez** a `backend/.env` (`META_ACCESS_TOKEN`);
   no lo pegues en el chat ni en el frontend. Si lo expones, revócalo y genera otro.
5. Completa en `backend/.env`: `META_AD_ACCOUNT_ID` (el número de la cuenta, con o sin `act_`),
   `META_PAGE_ID` y, si lo usas, `META_INSTAGRAM_USER_ID` y `META_PIXEL_ID` (el píxel habilita el
   objetivo «Ventas»). En Railway, las mismas variables en la API **y** en el worker.
6. Reinicia el backend. En un lote con imágenes compuestas aparece «Subir a Meta Ads»: pon el enlace de
   destino (https), el presupuesto diario y los países, y pulsa dos veces *Crear anuncios en pausa*.
   Revisa y activa en Ads Manager cuando quieras invertir.

## 7. Conectar Hotmart (opcional, solo lectura)

El dashboard de Hotmart (`/hotmart`) lee tus ventas; la app nunca crea, reembolsa ni modifica nada en
Hotmart.

1. En Hotmart: *Herramientas → Credenciales de desarrollador → Crear credencial* (tipo API de
   Hotmart). Te muestra **Client ID**, **Client Secret** y **Basic**.
2. En `backend/.env`: `HOTMART_CLIENT_ID`, `HOTMART_CLIENT_SECRET` y `HOTMART_BASIC` (el valor
   «Basic …»; si lo dejas vacío se arma con el ID y el secreto). En Railway, en la API.
3. Reinicia el backend y abre *Hotmart* en el menú: la primera lectura trae los últimos 90 días y se
   repite sola al abrir si pasaron más de 30 minutos (o con el botón *Actualizar*).
4. Para cruzar con Meta Ads, vincula cada producto de Hotmart con el de la app en la tabla «Por
   producto». El cruce solo incluye campañas subidas a Meta desde la app (guardan la moneda de la
   cuenta) y compara en la misma moneda.

## Qué hacer si algo falla

| Síntoma | Causa probable |
|---|---|
| `api` se reinicia en bucle | falta/insegura una variable: el log empieza con `configuración de producción inválida` |
| El login funciona pero todo da error de red | `NEXT_PUBLIC_API_URL` vacía o sin redeploy; o `CORS_ORIGINS` no coincide exactamente con la URL de Netlify |
| «usuario no autorizado» (403) | el email no está en `ALLOWED_EMAILS` |
| Los paquetes quedan «en cola» | no hay servicio `worker` (o `WORKER_INLINE=false` sin worker) |
| Drive: `redirect_uri_mismatch` | la URI de Railway no está en el cliente OAuth, o `GOOGLE_REDIRECT_URI` difiere en una letra |
| Drive pide reconectar cada semana | la app de Google sigue en modo *Prueba* (sección 4) |
| 429 al generar | el freno por usuario (30/min, 300/h por defecto); sube `RATE_LIMIT_*` si lo necesitas. Componer, exportar, importar y Drive tienen su propio cupo, aparte del de IA |
| `api` no arranca y dice `AD_TEMPLATES_DIR no existe` | la imagen no trae `ad_templates/` (revisa que el `Dockerfile` la copie y que el build use la raíz como contexto) |
| `IMAGE_PROVIDERS tiene proveedores desconocidos` | solo existen `pixabay` y `gemini` |
| Los anuncios salen sin fotos | falta `PIXABAY_API_KEY` (o Pixabay sin resultados): el creativo pasa solo a la plantilla de texto, no es un error |
