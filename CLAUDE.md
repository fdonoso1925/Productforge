# ProductForge

Genera paquetes de productos digitales low ticket (1 principal + 3 order bumps + 2 bonus) para pt-BR y es-LATAM.
Spec completo: `prompt-app-productos-digitales.md`. Plan, modelo de datos y decisiones: `PLAN.md`.

**Uso personal (un solo usuario).** Login con email y contraseña (Supabase Auth), sin registro público: el
usuario se crea en el dashboard (Authentication → Users → Add user). Restringido a `ALLOWED_EMAILS`
(backend) y a la tabla `app_allowed_emails` (un trigger en `auth.users` rechaza cualquier otro email).

## Stack

- `frontend/`: Next.js 16 (App Router, `proxy.ts` en vez de `middleware.ts`), TypeScript, Tailwind 4, shadcn/ui (base-ui), next-intl (`es` | `pt`), Supabase SSR. Deploy: Netlify.
- `backend/`: FastAPI, Python 3.12, uv, Pydantic. Deploy: Railway (Dockerfile).
- `supabase/`: migraciones SQL, seed, config local. Postgres + Auth + Storage, RLS en todas las tablas.
- `prompts/<mercado>/`: prompts versionados (`VERSION`), escritos nativos en pt-BR y es-LATAM. Ver `prompts/README.md`.
- `templates/<id>/template.json`: plantillas visuales como datos (paleta, fuentes, estilo) + `preview.png`. HTML/Jinja2 compartidos en `templates/_base/` (una plantilla puede reemplazar cualquiera con un archivo del mismo nombre o agregar `style.css`). Fuentes OFL en `templates/_fonts/`.

### Generadores de archivos (`backend/app/generators/`)

- `base.py`: `FileGenerator` (`generate(content, template, ctx) -> list[FileArtifact]`), `REGISTRY` y `@register`. Un módulo por familia: `pdf.py` (guía, checklist, blueprint, planner, swipe file), `epub.py`, `sheet.py` (XLSX con fórmulas + CSV), `maps.py` (SVG/PNG/PDF + XMind/OPML/FreeMind/Markmap/Mermaid/draw.io), `office.py` (DOCX/PPTX), `commercial.py` (ficha `.md`/`.docx`).
- `render.py`: HTML → PDF (WeasyPrint) y PDF → PNG (pdfium). En Windows carga las DLL de Pango desde `C:\msys64\ucrt64\bin` (MSYS2 + `mingw-w64-ucrt-x86_64-pango`).
- `samples.py`: contenido de ejemplo por formato (tests y miniaturas).

### Generación y jobs (Fase 4)

- `POST /outline` crea el producto (`outline_ready`); `PUT /products/{id}/outline` guarda ediciones (mismas reglas); `POST /products/{id}/generate` encola un job `generate` (409 si ya hay uno activo).
- `app/worker.py`: toma jobs con la función SQL `claim_job()` (`FOR UPDATE SKIP LOCKED`, reintenta jobs colgados tras 15 min). `WORKER_INLINE=true` lo corre dentro de la API en desarrollo; en producción, `python -m app.worker` como segundo servicio.
- `app/pipeline/generate.py`: piezas en paralelo (máx. 3) → contenido IA → archivos → Supabase Storage (`<user>/<product>/{principal,order-bumps,bonus}/...`) → ficha comercial → ZIP. Una pieza fallida queda en `error` y no frena las demás. El progreso va en `jobs.progress`. Si el job cae a medias (p. ej. sin créditos de IA al armar la ficha), el worker pasa el producto de `generating` a `error` (`release_product`) y regenerar la pieza fallida completa el paquete: también crea la ficha comercial si faltaba, sin volver a pagar las demás piezas.
- `GET /files/{id}/download` devuelve una URL firmada de 10 min (solo al dueño). `GET /templates` y `/templates/{id}/preview.png` son públicos.
- `app/storage/base.py`: `StorageProvider` (almacén principal: `SupabaseStorage`) y `SyncTarget` (destinos externos a los que se COPIA lo ya guardado: `GoogleDrive`; OneDrive o Dropbox implementarían lo mismo).
- Frontend: wizard en `/[locale]/new` (`components/wizard/`), progreso y resultado en `/[locale]/products/[id]` (polling directo a Supabase con RLS). El mercado se elige en el paso 1 porque los problemas se generan en ese idioma.

### Google Drive (Fase 6)

- **Supabase Storage sigue siendo el respaldo y la fuente de verdad.** Drive es una copia: `files.remote_status` = `pending` → `uploaded` | `failed` | `skipped` (el ZIP nunca se sube). Si Drive falla, el archivo queda `failed` con `upload_attempts` y se reintenta; nunca se pierde nada. (OneDrive se evaluó y se descartó: el usuario usa Gmail.)
- `app/storage/google_drive.py`: OAuth 2.0 con código + secreto de cliente (cliente "Aplicación web"), hablado directo con `httpx`. Permiso mínimo `drive.file` (+ `openid email` solo para mostrar la cuenta): la app solo ve lo que ella misma crea, nunca el resto del Drive. `access_type=offline` + `prompt=consent` para recibir refresh token; se rechaza la autorización si el usuario desmarcó el permiso de Drive.
- Tokens cifrados con Fernet (`TOKEN_ENCRYPTION_KEY`) en `storage_connections` (sin policies: solo la service role). Google NO rota el refresh token (se conserva el original). `invalid_grant` borra la conexión y pide reconectar. Al desconectar se revoca el acceso en Google. El `state` del flujo es opaco, vence a los 10 min y lleva el usuario; el callback no usa JWT y siempre redirige a `FRONTEND_URL`.
- **Drive no direcciona por ruta**: cada carpeta se busca o crea por nombre dentro de su padre, y Drive permite carpetas duplicadas, así que la creación se serializa con un candado por usuario y los ids se cachean. Si el usuario borra una carpeta a mano, se detecta (404) y se recrea. Los archivos se reemplazan en su lugar (idempotente); al regenerar una pieza, las copias viejas van a la **papelera** (recuperable), no se borran.
- Subida: hasta 5 MB en un request multipart; más, subida reanudable en partes de 8 MiB (si se corta, se consulta cuánto recibió Google y se retoma). Reintentos con `Retry-After`/backoff ante 429/5xx y 403 de límite de velocidad, y un único refresh ante 401.
- Carpeta (en Mi unidad): `ProductForge/<mercado>/<nicho>/<YYYY-MM-DD>_<slug-producto>/{principal,order-bumps,bonus}/…` + `ficha-comercial.md`. Las versiones derivadas añaden `-<id6>` para no pisar al original.
- Job `upload` (`pipeline/drive_sync.py`): lo encola `PackageBuilder.finish()` si el usuario está conectado, y el worker reencola pendientes/fallidos cada 10 min (máx. 5 intentos por archivo; el botón del producto reinicia los intentos).
- Endpoints: `GET /storage/drive/status`, `POST …/connect` (devuelve la URL de Google), `GET …/callback`, `DELETE /storage/drive`, `POST …/sync`, `GET|POST /products/{id}/drive[/sync]`. Frontend: `/[locale]/settings` y `DriveStatus` en cada paquete.

**Crear las credenciales de Google (una sola vez, gratis):**
1. https://console.cloud.google.com → proyecto nuevo `ProductForge`.
2. *APIs y servicios → Biblioteca* → **Google Drive API** → *Habilitar*.
3. *Pantalla de consentimiento de OAuth* (Google Auth Platform): tipo de usuario **Externo**; nombre `ProductForge`; correo de asistencia y de contacto; en *Acceso a datos* agrega el permiso `.../auth/drive.file`; en *Público* agrega tu Gmail como usuario de prueba.
4. **Publicar la app ("En producción")**. Mientras esté en modo *Prueba*, Google vence el acceso a los 7 días y habría que reconectar cada semana. `drive.file` no es un permiso sensible, así que no requiere revisión de Google, **pero el botón exige una URL de página principal y una de política de privacidad públicas**: la app trae `/[locale]/privacy` sin sesión; se podrá publicar cuando esté desplegada (ver `DEPLOY.md` §4). Antes, seguir en *Prueba* funciona igual.
5. *Credenciales → Crear credenciales → ID de cliente de OAuth* → tipo **Aplicación web**. URI de redirección autorizado: `http://localhost:8000/storage/drive/callback` (en producción, la URL pública del backend + la misma ruta, y `GOOGLE_REDIRECT_URI` igual). Copia el **ID de cliente** → `GOOGLE_CLIENT_ID` y el **secreto** → `GOOGLE_CLIENT_SECRET` en `backend/.env`.
6. Aplica la migración que renombra las columnas (`npx supabase db push`), reinicia el backend y, en `/settings`, pulsa *Conectar con Google Drive*. En la pantalla de Google deja marcado el permiso de Drive.

Si pierdes `TOKEN_ENCRYPTION_KEY`, los tokens guardados quedan ilegibles: basta con reconectar.

### Endurecimiento y deploy (Fase 7)

- `app/security.py`: **rate limit** por usuario (ventana deslizante en memoria, `RATE_LIMIT_PER_MINUTE`/`_PER_HOUR`, 30/300 por defecto) como dependencia `ai_rate_limit` en `/problems`, `/outline`, `generate`, `regenerate`, `remodel` y `duplicate`; es un freno ante loops, **no** una cuota de costo (D6). Cabeceras de seguridad en todas las respuestas, tope de tamaño de body (`Content-Length`, 1 MB), access log sin query string (el callback de Google trae `code`/`state`) y `httpx` en WARNING.
- `ENVIRONMENT=production` (la imagen Docker lo fija): `ensure_production_ready` impide arrancar API y worker con URLs locales, claves vacías, CORS con `localhost`/`*` o una `TOKEN_ENCRYPTION_KEY` inválida, y se apagan `/docs` y `/openapi.json`. Si agregas una variable obligatoria, súmala a `production_problems`.
- Frontend: cabeceras en `next.config.ts` (sin `script-src`: exigiría nonces), `/[locale]/privacy` pública (`lib/public-paths.ts`; `NEXT_PUBLIC_CONTACT_EMAIL` opcional).
- Tests: `tests/test_security.py` y `tests/test_e2e_flow.py` (recorrido completo por la API con repos e IA en memoria: 1+3+2, ≥3 formatos, cada archivo se abre, fórmulas XLSX, ZIP, descargas solo del dueño, plantilla sin IA, regenerar). El test de acceso cruzado de RLS sigue en `test_rls_integration.py` (CI con Supabase local).
- Deploy: `DEPLOY.md` (Netlify `netlify.toml`; Railway `railway.json` para la API y `railway.worker.json` para el worker, misma imagen). CI construye la imagen Docker.

### Historial y remodelado (Fase 5)

- `app/pipeline/package.py`: `PackageBuilder` es el núcleo común de todos los jobs que producen archivos (contenido por pieza → archivos → Storage → ficha comercial → ZIP reconstruido descargando de Storage). `generate.py` y `remodel.py` solo orquestan.
- **Regla de oro: no llamar a la IA si no cambia el contenido.** `plan_remodel` decide por pieza `rerender` (reusa `product_items.content`) o `generate` (IA). Cambiar plantilla o pasar entre formatos con el mismo schema (guía PDF ↔ EPUB) es gratis; cambiar tono/público o a un formato con otro schema usa IA. `frontend/lib/remodel.ts` espeja esta lógica para avisar el costo antes de crear la versión: si cambia una, cambia la otra.
- `POST /products/{id}/remodel`: crea un producto hijo (`parent_product_id`, `root_product_id` = raíz del árbol, nulo en la raíz) con sus piezas ya copiadas y encola un job `remodel`. Solo viaja lo que cambia (`tone: null` borra el tono). Aplica las mismas reglas del paquete (422 con la lista de errores).
- `POST /products/{id}/items/{item_id}/regenerate`: job `regenerate_item`. Los archivos viejos se reemplazan solo cuando los nuevos están listos; si falla, la pieza conserva lo que tenía.
- `POST /products/{id}/duplicate {market}`: job `duplicate_market` = `adapt_to_market` (nicho + problema + outline, prompt `adapt_market.md` nativo del mercado destino, mismos formatos y orden que el original) y después generación normal con contenido nativo. No traduce el contenido ya generado.
- Los tres exigen un paquete `ready`/`error` sin jobs activos (409) y pertenecer al usuario (404).
- Frontend: `/[locale]/history` (filtros: búsqueda, nicho, mercado, formato, fechas; lectura directa a Supabase con RLS; `sanitizeSearch` antes de armar el `or()` de PostgREST), paneles de remodelar/duplicar y árbol de versiones (`lib/versions.ts`) en `/[locale]/products/[id]`. Las acciones que usan IA piden doble clic (`ConfirmButton`).

### Portadas (arte generativo e imagen propia)

- `products.cover` (jsonb) = `CoverSpec {art: auto|topo|waves|circles|bauhaus|facets|none, image_id}` (`app/generators/cover.py`). `{}` = producto anterior a la función: queda **sin arte**, como se veía antes; los nuevos arrancan en `auto`. La plantilla sigue aplicándose a todo el PDF; la portada solo agrega una capa bajo el texto.
- **Arte** (`cover_art.py`): SVG a 210x297 mm armado solo con números y colores de la paleta (nada del contenido de la IA ni del usuario entra al SVG). Un estilo por paquete (`auto` lo elige por la **raíz** del árbol de versiones, así las versiones comparten arte) y un motivo distinto por pieza (semilla = raíz + rol + orden). Sobre el arte va una "zona protegida" (degradado del color de fondo donde cae el título de cada diseño, `text_zone`): si agregas un diseño de portada o mueves el texto, actualiza `text_zone`.
- **Imagen propia** (`cover_image.py`): entrada no confiable. Máx. 5 MB y 40 Mpx, mín. 800 px de lado, solo JPEG/PNG/WebP reales (se mira el contenido), siempre se reencodea a JPEG (sin EXIF/GPS) y se guarda en `<user>/covers/<uuid>.jpg`. Con imagen la portada es siempre "full-bleed": texto con `on_primary` sobre un velo del color `primary` cuya opacidad (35–90 %) se calcula para llegar a contraste 4,5 con el 90 % de píxeles más claros de la zona del título. Si la imagen falta al generar, la pieza sale con el arte.
- Endpoints: `POST /cover-images` (el body ES el archivo; tope propio en `BodyLimitMiddleware.overrides`), `GET /cover-images/{id}/url`, `GET /cover/art/{style}.svg?template=&background=` (público, para el selector), `PUT /products/{id}/cover` (solo `outline_ready`, el asistente) y `cover` en `POST /outline` (`cover_art`) y en `POST /products/{id}/remodel`.
- **Cambiar la portada es gratis (sin IA):** remodelar con otra portada crea una versión hija y solo re-maqueta (`plan_remodel` no cambia). Aplica a PDF (guía, checklist, blueprint, planner, swipe file) y a la portada del EPUB; mapas, XLSX y DOCX/PPTX no llevan portada de plantilla.
- Frontend: `CoverPicker` (`components/cover/`) en el último paso del asistente y en el panel de remodelar; `lib/cover.ts`.

### Página de ventas de referencia (opcional, paso 1 del asistente)

- Flujo: `POST /reference {url | text, market}` lee la página, la IA la **resume** en un `SalesReference` (público, dolores, promesa, tono, ángulo, vocabulario; `schemas/reference.py`) y el cliente lo devuelve en `POST /problems` y `POST /outline`. Se guarda en `products.reference` (jsonb, nulo = sin referencia; la columna solo se escribe cuando hay una, y `child_row` la copia a versiones y duplicados). `package_request()` la incluye, así que **todas** las llamadas (problemas, outline, cada pieza, ficha comercial) llevan `sales_page_reference` dentro de `<datos_del_usuario>`; la URL no viaja a la IA.
- **Es inspiración, no copia**: los prompts nativos (`system.md`, `problems.md`, `outline.md`, `item.md`, `commercial.md`, nuevo `reference.md`) piden contenido original, sin frases, títulos ni nombres de la página, y mantienen las reglas de honestidad. Del texto ajeno solo se guarda el resumen, nunca la página.
- **Lectura segura de URLs (`app/web/safe_fetch.py`, SSRF)**: solo http/https en puertos 80/443, sin usuario:clave; el nombre se resuelve ANTES y todas las direcciones deben ser públicas (nada de loopback, privadas, link-local/metadatos de la nube, CGNAT); se conecta a la IP ya validada (con `Host` y SNI del nombre, anti DNS-rebinding); las redirecciones se siguen a mano y cada salto se revalida; tope de 1,5 MB **ya descomprimido**, 20 s en total, solo HTML/texto, sin proxies del entorno. Si tocas esto, corre `tests/test_safe_fetch.py` (77 casos).
- **Texto no confiable (`app/web/extract.py`)**: stdlib `html.parser`; descarta scripts, navegación, pie, formularios y todo lo oculto (`hidden`, `aria-hidden`, `display:none`, tamaño/opacidad 0…) y caracteres invisibles, que es donde se esconden instrucciones para la IA. Aun así el texto va como dato delimitado (`wrap_user_data`) y `reference.md` ordena ignorar instrucciones dentro de la página. Páginas armadas con JavaScript (casi sin texto) se rechazan con la sugerencia de pegar el texto (`text` en vez de `url`).
- La salida de la IA se recorta a los límites duros de `SalesReference` (`to_reference`); lo que manda el cliente se valida estricto (422).
- Frontend: `components/wizard/reference-panel.tsx` (URL o texto pegado, tarjeta con el resumen), `lib/reference.ts`; cambiar de mercado la descarta y cambiarla rehace problemas y outline (`inputsKey`).

### Creativos para Meta Ads (fases 2 a 7; spec `prompt-modulo-creativos-meta-ads.md`, plan `PLAN-CREATIVOS.md`)

- Flujo: brief (de un producto o manual) → avatares → ángulos → **lote** (job `ad_plan`: copy, semáforo de políticas 🟢🟡🔴 y pre-score por creativo) → el usuario revisa/edita el texto → composición (job `ad_render`, sin IA). Cada borrador se compone en 1–3 formatos (`4x5` 1080×1350, `9x16` 1080×1920, `1x1` 1080×1080) y comparte `group_id`.
- `app/ads/`: `schemas.py` (Pydantic, todo lo que devuelve la IA), `rules.py` (largos, ángulos disponibles, semáforo por reglas; **precio, urgencia y pruebas solo entran si el usuario los da**: nunca se inventan testimonios, cifras ni marcas), `strategy.py` (`AdStrategyService` sobre `ContentService._call` con el system prompt propio `prompts/<mercado>/ads/system.md`), `render.py` (WeasyPrint → PDF → PNG con pdfium), `jobs.py` (handlers del worker + `AdDeps`), `repo.py`, `naming.py`.
- Composición: `ad_templates/<id>/{template.json,ad.html.j2}` + `_base/page.html.j2`; 12 plantillas (ver abajo) que toman paleta y fuentes de la plantilla del producto. Los márgenes seguros y tamaños viven en `ad_templates/specs.json` (verificados en la Ads Guide oficial de Meta: 14 % arriba, 35 % abajo y 6 % a los lados en 9:16; Meta no publica zona segura para Feed). Si algo se sale de la zona segura se reduce el contenido y se reintenta (`SHRINKS`). WeasyPrint mide mal la altura de un titular que envuelve dentro de un flex sin ancho explícito (el texto se pisaba): `.safe > *:not(.cta)` lleva ancho fijo; `test_lines_of_text_never_overlap_whatever_the_wrapping` lo vigila.
- Texto no confiable: el copy se escapa siempre (Jinja con autoescape); el brief viaja a la IA como dato delimitado (`wrap_user_data`), la URL de la referencia no.
- Editar el texto de un creativo (`PUT /ads/creatives/{id}`) pasa por las mismas reglas y el mismo semáforo que el de la IA, actualiza sus otros formatos y recompone lo ya renderizado **sin llamar a la IA**.
- Tablas `ad_batches`, `ad_creatives`, `ad_proofs` (migración `20261025000000_ads.sql`; RLS solo `select`); `jobs.product_id` pasa a ser opcional y se agrega `jobs.batch_id`. Archivos en Storage: `<user>/ads/<lote>/<formato>/<producto>_<mercado>_<angulo>_<plantilla>_<ratio>_v<n>.png`.
- Endpoints (`app/api/ads.py`, prefijo `/ads`): `GET /templates`, `POST /brief|avatars|angles`, `POST|GET /batches`, `GET /batches/{id}`, `POST /batches/{id}/render`, `PUT /creatives/{id}`, `POST /creatives/{id}/render|discard`, `GET /creatives/{id}/url`, `GET|POST|DELETE /proofs`. Los que usan IA llevan `ai_rate_limit`.
- **Imágenes base (fase 4, `app/ads/images/`)**: `ImageProvider` (`base.py`) con `PixabayProvider` (stock gratis: descarga la foto a Storage, caché de búsqueda 24 h, 90 peticiones/min, `safesearch`, sin fotos de personas en nichos sensibles, guarda autor y licencia) y `GeminiImageProvider` (de pago; **apagado mientras `GEMINI_DAILY_USD_CAP` sea 0**, aunque haya clave), más esqueletos `PexelsProvider`/`OpenAIImageProvider` (`stubs.py`). `ImageRouter` (`router.py`): caché por escena (usuario + escena + formato, tabla `ad_image_cache`) → proveedores en el orden de `IMAGE_PROVIDERS` → tope diario en USD y «sin cuota» por proveedor (`ad_provider_usage`) → si ninguno puede, el creativo pasa solo a `headline_bold` (cambia de nombre) y el lote no se cae. Toda imagen se recorta al formato y se reencodea a JPEG sin EXIF. Agregar un proveedor = una clase + registrarla en `build_router` + variables de entorno.
- 12 plantillas (`TEMPLATE_IDS`): solo `photo_headline` usa foto (velo del color de marca con opacidad calculada para contraste 4,5 contra el 90 % de píxeles más claros de la zona de texto; la foto de fondo no cuenta como contenido fuera de la zona segura). Reglas propias en `rules.py`: `before_after`/`comparison` exigen 2 o 4 bullets (mitad «antes», mitad «después»), `offer_stack` exige precio real del brief, `testimonial` solo cita **textualmente** una prueba real (`proof_id`, autor tal cual). Las plantillas que el motor puede elegir hoy salen de `available_templates` (fotos solo con proveedor activo, oferta solo con precio, testimonio solo con pruebas).
- Claves en `backend/.env` (`GEMINI_API_KEY`, `PIXABAY_API_KEY`, `IMAGE_PROVIDERS`, `GEMINI_DAILY_USD_CAP`…); nunca en el frontend. Migración `20261026000000_ads_images.sql`. `GET /ads/images/status` muestra qué proveedores están activos.
- **Entrega (fase 5)**: `app/ads/export.py` arma el CSV de copys (UTF-8 con BOM, cabeceras nativas por mercado, celdas que empiezan con `= + - @` se neutralizan con `'`) y el ZIP (`<carpeta del formato>/<archivo>.png` + `copys.csv` + `creditos-imagenes.txt` si hay fotos). `POST /ads/batches/{id}/export` los sube a Storage y devuelve URLs firmadas; `POST /ads/batches/{id}/urls` firma todas las imágenes para la galería. Copia a Drive: job `ad_drive` (`run_ad_drive`) → `ProductForge/<mercado>/<nicho>/anuncios_<fecha>_<producto>_<id6>/<formato>/…` + `copys.csv`; el estado vive en `ad_batches.drive` y **no cambia el estado del lote**; `GET|POST /ads/batches/{id}/drive`. Migración `20261027000000_ads_export.sql`.
- **Frontend**: `/[locale]/ads` (lotes), `/ads/new` (asistente: producto o brief manual + precio/urgencia/pruebas reales → avatares → ángulos, variaciones, formatos y plantilla visual) y `/ads/[id]` (progreso, galería con semáforo y pre-score, editor rápido, componer, ZIP+CSV, Drive). Lee de Supabase con RLS y escribe por el backend (`lib/api.ts` → `adsX`). `lib/ads.ts` espeja los límites de `rules.py` solo para avisar antes de enviar; el backend vuelve a validar. Textos en `messages/{es,pt}.json` (`ads.*`, con test de paridad de claves).
- **Resultados y aprendizaje (fase 6)**: tabla `ad_results` (por creativo y día; **CTR/CPC/CPA/ROAS no se guardan, se calculan de los totales** en `app/ads/learning.py` y `frontend/lib/ads.ts`). Carga a mano (`PUT /ads/creatives/{id}/results`, mismas validaciones que el frontend) o importando el CSV de Ads Manager (`POST /ads/results/import`, el body ES el archivo, tope propio de 2 MB en `BodyLimitMiddleware.overrides`). `app/ads/results_import.py` entiende cabeceras es/pt/en, `,` `;` tab, números `1.234,56` / `1,234.56` (un único separador seguido de 3 dígitos = miles), fechas ISO o d/m/a; empareja por **nombre de archivo** (igual sin extensión o contenido en el nombre del anuncio), nunca adivina si un nombre apunta a varios creativos y suma las filas repetidas del mismo anuncio y día. Reimportar reemplaza el día (idempotente).
- Aprendizaje (`GET /ads/insights?market=&niche=`): ángulos, plantillas y hooks (por borrador, sumando sus formatos) con métricas y ganadores. Se ordena por la mejor métrica disponible: ROAS si todo lo que vendió tiene valor de conversión, si no CPA, y CTR si nadie vendió; con menos de 1000 impresiones nunca se declara ganador. `POST /ads/angles` pasa los **ángulos ganadores** (mismo nicho y mercado; si no hay datos, el mercado) a la IA y los devuelve en `winners` (★ en el asistente).
- Iterar: `POST /ads/creatives/{id}/iterate` (job `ad_iterate`, IA): mismo ángulo y avatar, hooks nuevos con las métricas del original en el prompt (`iterate_from`); los borradores entran al mismo lote con `parent_creative_id`. `POST /ads/creatives/{id}/variant` (sin IA): mismo texto en otra plantilla/formato/foto, pasa por `check_draft` y el semáforo; otro formato de la misma plantilla queda en el mismo `group_id`. `POST /ads/batches/{id}/duplicate {market}`: `adapt_brief` (prompt nativo `ads/adapt.md` del mercado destino, **adapta, no traduce**; precio y urgencia se copian tal cual; la referencia se descarta) y se planifica un lote nuevo (`parent_batch_id`) con los mismos ángulos, formatos y plantilla. Migración `20261028000000_ads_results.sql`.
- Frontend: `/ads/insights` (panel de aprendizaje), panel de resultados e importación en el lote, iterar/variantes en cada borrador, duplicar a otro idioma, filtros en `/ads`. **Para la Meta Marketing API (subir creativos y leer métricas solos) solo queda preparado el modelo: `ad_results.source` distingue `manual`/`csv` y bastaría un tercero.**
- **Endurecimiento (fase 7)**: `work_rate_limit` (`app/security.py`) es un cupo aparte del de IA (`ai_rate_limit`) para lo que gasta CPU, disco o red sin IA: componer, editar-y-recomponer, exportar, importar, variantes, resultados, pruebas y Drive; lecturas sin límite. `RedactingFormatter` (instalado por `configure_logging`) tapa claves y tokens en cualquier log o traceback (`?key=`, `x-goog-api-key`, `sk-ant-…`, `AIza…`, JWT): Pixabay lleva su clave en la URL. Pixabay solo descarga de `https://*.pixabay.com` (la URL viene en la respuesta de su API: anti-SSRF) y Gemini rechaza imágenes anómalas por tamaño. `production_problems` ahora exige que existan `PROMPTS_DIR`, `TEMPLATES_DIR` y `AD_TEMPLATES_DIR` (el `Dockerfile` olvidaba copiar `ad_templates/`: hay un test que lo vigila) y valida `IMAGE_PROVIDERS`/tope de Gemini. `GET /ads/images/status` devuelve uso de hoy y tope por proveedor; la UI lo muestra en `/ads`.
- Tests del módulo: `test_e2e_ads.py` (recorrido completo con los criterios de aceptación: ≥3 ángulos × 2 variantes en 4:5 y 9:16, nada inventado —la IA intenta un testimonio falso y se rechaza—, edición sin IA, Gemini sin cuota → Pixabay sin errores, resultados → ganadores → siguiente lote, ZIP/CSV/Drive), `test_ads_hardening.py` y las tablas `ad_*` en `test_rls_integration.py` (corren en CI con Supabase local).
- Pendiente a futuro (no implementado): Meta Marketing API para subir creativos y leer métricas automáticamente.

### Motor de contenido (`backend/app/content/`)

- `schemas/`: Pydantic del paquete (`Problem`, `PackageOutline`, `CommercialSheet`) y un schema por formato (`FORMAT_SCHEMAS`).
- `claude_client.py`: única puerta a Claude. Streaming + `output_format` (Pydantic) + `fallbacks="default"` + system prompt cacheado. Lanza `LLMRefusal` / `LLMTruncated` / `LLMInvalidOutput`.
- `rules.py`: reglas de negocio que el schema no expresa (1+3+2, formatos distintos, páginas, coherencia interna por formato).
- `engines.py`: `ContentService` (problemas, outline, pieza, ficha comercial). Si las reglas fallan, reintenta con los errores como feedback (3 intentos) y registra el costo en `ai_usage`.
- Endpoints: `POST /problems`, `POST /outline` (crea el producto en `outline_ready`). La generación de piezas se expone vía jobs en la Fase 4.
- Tests: `tests/fakes.py` tiene `FakeLLM`; ningún test llama a la API real.

Next.js 16 cambió APIs: antes de escribir código de Next, lee la guía en `frontend/node_modules/next/dist/docs/`.

## Comandos

```bash
# Supabase local (requiere Docker Desktop corriendo)
npx supabase start            # imprime URL y claves; también: npx supabase status
npx supabase db reset         # reaplica migraciones + seed.sql
npx supabase migration new <nombre>

# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload       # http://localhost:8000
uv run ruff check . && uv run ruff format .
uv run pytest -m "not integration"         # unit
uv run pytest -m integration               # RLS contra Supabase local (exporta SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY)
uv run pip-audit
uv run python -m app.templates_engine.fonts      # baja las fuentes de templates/*/template.json
uv run python -m app.templates_engine.previews   # regenera templates/*/preview.png

# Frontend
cd frontend
npm run dev                                # http://localhost:3000
npm run lint && npm run typecheck && npm test
npm run build
npm audit --omit=dev --audit-level=high
```

Después de `npx supabase db reset`, autoriza tu email:
`insert into app_allowed_emails (email) values ('tu-email@gmail.com');` (desde Studio en http://127.0.0.1:54323).

## Convenciones

- Secretos solo en variables de entorno; documentar toda variable nueva en `.env.example`. El frontend solo usa `NEXT_PUBLIC_*`.
- Backend: dependencias fijadas con versión exacta (`uv add --bounds exact`); ruff con reglas `S` (seguridad).
- Frontend: lee de Supabase directo (RLS protege); todo lo que escribe, cuesta dinero o usa secretos pasa por el backend (`lib/api.ts` con el JWT de Supabase).
- Textos de la interfaz en `frontend/messages/{es,pt}.json`; nunca hardcodeados.
- Redirecciones internas siempre pasan por `safeNextPath` (`frontend/lib/redirect.ts`).
- Cada fase cierra con tests en verde + commit.

## Decisiones de arquitectura

- **Escrituras solo vía backend (service role).** Las tablas de usuario solo tienen policies `select` para `authenticated`; `storage_connections` y `app_allowed_emails` no tienen ninguna.
- **JWT:** el backend acepta HS256 (`SUPABASE_JWT_SECRET`, Supabase local) y ES256/RS256 vía JWKS del proyecto; exige `aud=authenticated`, `exp` y `sub`.
- **Jobs:** tabla `jobs` + worker propio con `FOR UPDATE SKIP LOCKED` (Fase 2+), no `BackgroundTasks` ni Celery.
- **Archivos:** WeasyPrint (HTML/Jinja2) para PDF; mapas mentales con render SVG propio en Python (sin Chromium).
- **Costo de IA:** sin tope (uso personal); se registra en `ai_usage` solo para visibilidad.
- **Modelo:** `claude-sonnet-5-5` por defecto para todo (configurable con `CLAUDE_MODEL_*`), effort `high`. Medido con el mismo tipo de paquete: unos 1,4 USD con Sonnet contra unos 3,4 USD con Opus 5.5 (`claude-opus-5-5`, que sigue disponible en `PRICES`). Los modelos 5.5 no permiten desactivar thinking ni forzar `tool_choice`; la salida estructurada va por `output_format`.
- **Prompt injection:** los datos del usuario van como JSON dentro de `<datos_del_usuario>` / `<dados_do_usuario>` (con `</` escapado), nunca interpolados en el prompt; el system prompt indica tratarlos como datos. Toda salida se valida contra schema y reglas.
- **Docker:** el build del backend usa la raíz como contexto (`docker build -f backend/Dockerfile .`) porque copia `prompts/`.
- **Destino externo:** Google Drive (cuenta Gmail), permiso `drive.file` → `Mi unidad/ProductForge/...`. Las columnas de `files` son genéricas (`remote_*`) por si se agrega otro destino.
- **Node:** el proyecto compila con Node 20, pero Supabase JS y vitest 4+ piden Node 22. CI usa 22; vitest queda en 3.x hasta actualizar Node local.
