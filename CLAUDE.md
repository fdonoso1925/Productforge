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
- `app/pipeline/generate.py`: piezas en paralelo (máx. 3) → contenido IA → archivos → Supabase Storage (`<user>/<product>/{principal,order-bumps,bonus}/...`) → ficha comercial → ZIP. Una pieza fallida queda en `error` y no frena las demás. El progreso va en `jobs.progress`.
- `GET /files/{id}/download` devuelve una URL firmada de 10 min (solo al dueño). `GET /templates` y `/templates/{id}/preview.png` son públicos.
- `app/storage/base.py`: interfaz `StorageProvider`; hoy solo `SupabaseStorage` (OneDrive en Fase 6).
- Frontend: wizard en `/[locale]/new` (`components/wizard/`), progreso y resultado en `/[locale]/products/[id]` (polling directo a Supabase con RLS). El mercado se elige en el paso 1 porque los problemas se generan en ese idioma.

### Historial y remodelado (Fase 5)

- `app/pipeline/package.py`: `PackageBuilder` es el núcleo común de todos los jobs que producen archivos (contenido por pieza → archivos → Storage → ficha comercial → ZIP reconstruido descargando de Storage). `generate.py` y `remodel.py` solo orquestan.
- **Regla de oro: no llamar a la IA si no cambia el contenido.** `plan_remodel` decide por pieza `rerender` (reusa `product_items.content`) o `generate` (IA). Cambiar plantilla o pasar entre formatos con el mismo schema (guía PDF ↔ EPUB) es gratis; cambiar tono/público o a un formato con otro schema usa IA. `frontend/lib/remodel.ts` espeja esta lógica para avisar el costo antes de crear la versión: si cambia una, cambia la otra.
- `POST /products/{id}/remodel`: crea un producto hijo (`parent_product_id`, `root_product_id` = raíz del árbol, nulo en la raíz) con sus piezas ya copiadas y encola un job `remodel`. Solo viaja lo que cambia (`tone: null` borra el tono). Aplica las mismas reglas del paquete (422 con la lista de errores).
- `POST /products/{id}/items/{item_id}/regenerate`: job `regenerate_item`. Los archivos viejos se reemplazan solo cuando los nuevos están listos; si falla, la pieza conserva lo que tenía.
- `POST /products/{id}/duplicate {market}`: job `duplicate_market` = `adapt_to_market` (nicho + problema + outline, prompt `adapt_market.md` nativo del mercado destino, mismos formatos y orden que el original) y después generación normal con contenido nativo. No traduce el contenido ya generado.
- Los tres exigen un paquete `ready`/`error` sin jobs activos (409) y pertenecer al usuario (404).
- Frontend: `/[locale]/history` (filtros: búsqueda, nicho, mercado, formato, fechas; lectura directa a Supabase con RLS; `sanitizeSearch` antes de armar el `or()` de PostgREST), paneles de remodelar/duplicar y árbol de versiones (`lib/versions.ts`) en `/[locale]/products/[id]`. Las acciones que usan IA piden doble clic (`ConfirmButton`).

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
- **Modelo:** `claude-opus-5-5` por defecto para todo (configurable con `CLAUDE_MODEL_*`), effort `high`. Opus 5.5 no permite desactivar thinking ni forzar `tool_choice`; la salida estructurada va por `output_format`.
- **Prompt injection:** los datos del usuario van como JSON dentro de `<datos_del_usuario>` / `<dados_do_usuario>` (con `</` escapado), nunca interpolados en el prompt; el system prompt indica tratarlos como datos. Toda salida se valida contra schema y reglas.
- **Docker:** el build del backend usa la raíz como contexto (`docker build -f backend/Dockerfile .`) porque copia `prompts/`.
- **OneDrive:** cuenta personal, `Files.ReadWrite.AppFolder` → `/Aplicaciones/ProductForge/...`.
- **Node:** el proyecto compila con Node 20, pero Supabase JS y vitest 4+ piden Node 22. CI usa 22; vitest queda en 3.x hasta actualizar Node local.
