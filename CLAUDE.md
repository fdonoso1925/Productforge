# ProductForge

Genera paquetes de productos digitales low ticket (1 principal + 3 order bumps + 2 bonus) para pt-BR y es-LATAM.
Spec completo: `prompt-app-productos-digitales.md`. Plan, modelo de datos y decisiones: `PLAN.md`.

**Uso personal (un solo usuario).** Login con Google, restringido a `ALLOWED_EMAILS` (backend) y a la tabla
`app_allowed_emails` (un trigger en `auth.users` rechaza cualquier otro email).

## Stack

- `frontend/`: Next.js 16 (App Router, `proxy.ts` en vez de `middleware.ts`), TypeScript, Tailwind 4, shadcn/ui (base-ui), next-intl (`es` | `pt`), Supabase SSR. Deploy: Netlify.
- `backend/`: FastAPI, Python 3.12, uv, Pydantic. Deploy: Railway (Dockerfile).
- `supabase/`: migraciones SQL, seed, config local. Postgres + Auth + Storage, RLS en todas las tablas.
- `prompts/<mercado>/`: prompts versionados (`VERSION`), escritos nativos en pt-BR y es-LATAM. Ver `prompts/README.md`.
- `templates/`: plantillas visuales como datos (Fase 3).

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
