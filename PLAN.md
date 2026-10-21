# ProductForge — Plan de arquitectura (propuesta para aprobación)

> Respuesta a la sección 14 del spec. No hay código todavía. Al aprobar este plan (y responder las dudas de la sección 5), arranco la Fase 1.
>
> Estado del repo: vacío salvo el spec. **No existe un PDF Agent (FastAPI + ReportLab)** aquí, así que la decisión WeasyPrint vs. ReportLab queda abierta solo si me indicas dónde está (ver duda D10).

---

## 1. Plan por fases

Complejidad: **S** ≈ 1–2 días · **M** ≈ 3–5 días · **L** ≈ 1–2 semanas (de trabajo efectivo con Claude Code).

| Fase | Contenido | Complejidad | Entregable verificable |
|---|---|---|---|
| **1 — Base** | Monorepo, Supabase (migraciones SQL + RLS + seed de nichos/plantillas), auth en frontend, backend FastAPI con validación de JWT, `CLAUDE.md`, `.env.example`, CI (lint + tests + `pip-audit` + `npm audit`), Dockerfile del backend | **M** | Login funciona; `GET /me` responde con JWT válido; **test de acceso cruzado RLS entre 2 usuarios** en verde |
| **2 — Motor de contenido** | Cliente Claude con salida estructurada (Pydantic), prompts versionados `prompts/<mercado>/*.md`, motor de problemas (5 propuestas), generador de outline del paquete, generador de contenido por pieza, registro de uso/costo | **L** | `POST /problems` y `POST /outline` devuelven JSON válido en pt-BR y es-LATAM; tests con respuestas de IA mockeadas + validación de schema |
| **3a — Generadores núcleo** | Interfaz `FileGenerator` + registro; PDF/ebook (WeasyPrint + Jinja2) con 3 plantillas; checklist/workbook PDF | **M** | PDF con portada, índice, callouts, numeración y fuentes embebidas |
| **3b — Resto de formatos** | XLSX (fórmulas reales + validaciones + CSV), mapa mental y conceptual (Markmap/Mermaid + SVG/PNG/PDF + `.xmind`/`.opml`/`.mm`), DOCX, PPTX, EPUB, blueprint, planner, swipe file | **L** | Test que abre cada archivo generado con su librería lectora; XLSX recalculado con fórmulas OK |
| **3c — 10 plantillas** | Las 10 plantillas como datos (`template.json` + Jinja2), design tokens, generación automática de miniaturas | **M** | Script `make previews` genera 10 PNG; galería las muestra |
| **4 — Wizard UI** | Las 8 pantallas de la sección 3, outline editable, polling de jobs con progreso por pieza, ZIP, ficha comercial en pantalla | **L** | Flujo completo < 2 min de interacción (test E2E con IA mockeada) |
| **5 — Historial y remodelado** | Listado + filtros, detalle, árbol de versiones, remodelar (diff → solo piezas afectadas), regenerar pieza, duplicar al otro idioma | **M** | Cambiar plantilla regenera archivos **sin llamar a la IA** (test que falla si se invoca el cliente Claude) |
| **6 — OneDrive** | OAuth MSAL, tokens cifrados + refresh, `StorageProvider`, upload sessions, estructura de carpetas, reintentos | **M** | Archivos en `/ProductForge/<mercado>/<nicho>/...`; con Graph caído el archivo queda en Supabase y se reintenta |
| **7 — Endurecimiento** | Rate limit por usuario, tope de costo diario, E2E completo, deploy Netlify + Railway, docs finales | **M** | Checklist de la sección 13 completo |

Total estimado: **~6–9 semanas** de trabajo efectivo. Cada fase cierra con tests + commit + resumen.

### Decisiones de simplicidad que propongo

1. **Jobs: tabla `jobs` + un worker propio (no `BackgroundTasks`).** `BackgroundTasks` corre dentro del proceso web: si Railway reinicia el contenedor en medio de una generación, el job se pierde sin rastro. Un worker que hace `SELECT … FOR UPDATE SKIP LOCKED` sobre `jobs` cada 2 s es ~80 líneas, usa la misma imagen Docker (otro comando de arranque) y sobrevive reinicios. Sin Celery ni Redis.
2. **Lecturas desde el frontend directo a Supabase (con RLS); escrituras y todo lo que cuesta dinero pasan por el backend.** El historial, filtros y detalle no necesitan endpoints propios: RLS ya garantiza aislamiento. La IA, la generación de archivos y OneDrive solo existen en el backend.
3. **Backend accede a Postgres con la service role, pero siempre filtrando por `user_id` del JWT** en una capa de repositorio única (un solo lugar donde auditar). Las tablas igual tienen RLS como segunda barrera.
4. **Mapas mentales sin Chromium.** Mermaid/Markmap necesitan un navegador para renderizar. Propongo guardar las fuentes `.md` (Markmap) y `.mmd` (Mermaid) para el usuario, y renderizar el SVG con un layout de árbol propio en Python (≈150 líneas) → PDF vía WeasyPrint y PNG vía `cairosvg`. La imagen Docker queda ~300 MB más liviana que con Playwright. Si el resultado visual no te convence, se cambia a Playwright solo para este generador (es un módulo enchufable).
5. **Miniaturas de plantillas:** WeasyPrint ya no exporta PNG, así que: render de un documento de muestra → PDF → primera página a PNG con `pypdfium2`. Corre en CI/`make previews` y se sube a Storage.
6. **Fórmulas XLSX verificadas** con LibreOffice headless solo en CI (no en producción).
7. **Modelo IA configurable por env** (`CLAUDE_MODEL_OUTLINE`, `CLAUDE_MODEL_CONTENT`). Por defecto `claude-sonnet-5-5` para contenido y outline; se puede subir el outline a `claude-opus-5-5` si la calidad lo pide. Salida estructurada con el schema JSON derivado de cada modelo Pydantic, y validación estricta antes de persistir (si falla: 1 reintento con el error de validación como feedback, luego error del job).
8. **WeasyPrint en Windows** requiere GTK; el desarrollo local del backend será vía `docker compose` para no pelear con dependencias nativas. El frontend corre nativo.

---

## 2. Estructura de carpetas

```
productforge/
├── CLAUDE.md
├── PLAN.md
├── .env.example                  # documentado, sin valores reales
├── docker-compose.yml            # backend + worker (local)
├── Makefile                      # dev, test, lint, previews
├── .github/workflows/ci.yml      # lint, tests, pip-audit, npm audit
│
├── frontend/                     # Next.js App Router → Netlify
│   ├── app/
│   │   ├── [locale]/             # es | pt (next-intl)
│   │   │   ├── (auth)/login/
│   │   │   ├── new/              # wizard (pasos 1–8)
│   │   │   ├── history/          # listado + filtros
│   │   │   ├── products/[id]/    # detalle, versiones, remodelar
│   │   │   └── settings/         # conexión OneDrive
│   ├── components/
│   │   ├── ui/                   # shadcn/ui
│   │   ├── wizard/
│   │   └── history/
│   ├── lib/
│   │   ├── supabase/             # clientes browser/server
│   │   ├── api.ts                # cliente del backend (con JWT)
│   │   └── schemas/              # Zod (espejo de los Pydantic de entrada)
│   ├── messages/{es,pt}.json     # i18n de la interfaz
│   └── tests/                    # Vitest + Playwright E2E
│
├── backend/                      # FastAPI → Railway
│   ├── pyproject.toml            # uv, dependencias fijadas (uv.lock)
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py               # API (CORS, rate limit, auth)
│   │   ├── worker.py             # loop de jobs
│   │   ├── config.py             # pydantic-settings
│   │   ├── auth.py               # validación JWT Supabase
│   │   ├── db/                   # repositorios (único acceso a Postgres)
│   │   ├── api/                  # routers: problems, outline, products, jobs, files, storage
│   │   ├── content/
│   │   │   ├── claude_client.py
│   │   │   ├── prompts.py        # carga prompts/<mercado>/<pieza>.md
│   │   │   ├── engines.py        # ProblemEngine, OutlineEngine, ContentEngine
│   │   │   └── schemas/          # Pydantic: Problem, PackageOutline, contenidos por formato
│   │   ├── generators/
│   │   │   ├── base.py           # FileGenerator + registry
│   │   │   ├── pdf_guide.py  epub.py  mindmap.py  conceptmap.py
│   │   │   ├── sheet.py  checklist.py  blueprint.py  editable.py
│   │   │   └── planner.py  swipe.py  commercial_sheet.py
│   │   ├── templates_engine/     # carga template.json, tokens, Jinja2 (autoescape)
│   │   ├── storage/
│   │   │   ├── base.py           # StorageProvider
│   │   │   ├── supabase_storage.py
│   │   │   └── onedrive.py
│   │   ├── pipeline/             # orquestación: outline → contenido → archivos → subida; remodel diff
│   │   └── security/             # rate limit, cost guard, cifrado de tokens
│   └── tests/
│
├── templates/                    # plantillas visuales como DATOS
│   ├── _tokens/base.css          # design tokens compartidos
│   ├── _partials/                # cover, toc, callout, page-footer (Jinja2)
│   ├── _fonts/                   # Google Fonts OFL embebidas
│   ├── minimal-clean/{template.json, guide.html.j2, checklist.html.j2, ..., preview.png}
│   └── ... (10–12 carpetas)
│
├── prompts/
│   ├── pt-BR/{problems,outline,main,order_bump,bonus,commercial_sheet,adapt_market}.md
│   └── es-LATAM/{...}.md
│
└── supabase/
    ├── migrations/0001_init.sql
    ├── seed.sql                  # nichos + plantillas
    └── tests/rls_cross_user.sql  # o test en pytest contra Supabase local
```

---

## 3. Modelo de datos final (SQL Supabase)

Cambios respecto al mínimo del spec (justificados):

- `products` agrega `title`, `slug`, `outline` (outline del paquete aprobado), `commercial` (ficha comercial JSON), `tone`, `audience_override`, `prompt_version` (reproducibilidad) y `root_product_id` (para traer el árbol de versiones con una sola consulta).
- `product_items` agrega `content_hash` (para saber qué piezas cambian al remodelar) y `status` (progreso por pieza).
- `files` agrega `user_id` (RLS sin joins, más rápido y simple), `onedrive_status` y `upload_attempts` (reintentos sin tabla aparte).
- `jobs` agrega `user_id`, `kind` (generate | regenerate_item | remodel | duplicate_market | upload), `payload`, `locked_at`, `attempts`.
- **Nuevas:** `ai_usage` (tokens y costo por llamada → límite diario), `storage_connections` (tokens OAuth cifrados por proveedor).

```sql
-- 0001_init.sql
create extension if not exists pgcrypto;

create type market_t      as enum ('pt-BR', 'es-LATAM');
create type item_role_t   as enum ('main', 'order_bump', 'bonus');
create type product_status_t as enum ('draft', 'outline_ready', 'generating', 'ready', 'error');
create type job_status_t  as enum ('queued', 'running', 'done', 'error', 'cancelled');
create type format_t as enum (
  'pdf_guide', 'epub', 'mind_map', 'concept_map', 'sheet',
  'checklist', 'blueprint', 'editable_template', 'planner', 'swipe_file'
);

-- Catálogos (lectura pública para usuarios autenticados, escritura solo service role)
create table niches (
  id         uuid primary key default gen_random_uuid(),
  slug       text not null,
  name       text not null,
  market     market_t not null,
  active     boolean not null default true,
  sort_order int not null default 0,
  unique (slug, market)
);

create table templates (
  id          text primary key,                 -- 'minimal-clean'
  name        text not null,
  config      jsonb not null,                   -- copia de template.json
  preview_url text,
  active      boolean not null default true,
  sort_order  int not null default 0
);

-- Datos del usuario
create table products (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users(id) on delete cascade,
  parent_product_id uuid references products(id) on delete set null,
  root_product_id   uuid references products(id) on delete set null,
  title             text,
  slug              text,
  niche             text not null check (char_length(niche) <= 120),
  problem           jsonb not null,             -- Problem (público, dolor, resultado, plazo, por qué, urgencia)
  market            market_t not null default 'pt-BR',
  main_format       format_t not null,
  template_id       text not null references templates(id),
  tone              text check (char_length(tone) <= 200),
  audience_override text check (char_length(audience_override) <= 300),
  outline           jsonb,                      -- PackageOutline aprobado
  commercial        jsonb,                      -- ficha comercial
  prompt_version    text not null,
  status            product_status_t not null default 'draft',
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index on products (user_id, created_at desc);
create index on products (root_product_id);

create table product_items (
  id           uuid primary key default gen_random_uuid(),
  product_id   uuid not null references products(id) on delete cascade,
  user_id      uuid not null references auth.users(id) on delete cascade,
  role         item_role_t not null,
  format       format_t not null,
  title        text not null,
  outline      jsonb not null,
  content      jsonb,                           -- contenido estructurado validado
  content_hash text,
  status       text not null default 'pending', -- pending | generating | ready | error
  "order"      int not null,
  created_at   timestamptz not null default now(),
  unique (product_id, role, "order")
);

create table files (
  id               uuid primary key default gen_random_uuid(),
  product_item_id  uuid references product_items(id) on delete cascade, -- null = ficha comercial / ZIP
  product_id       uuid not null references products(id) on delete cascade,
  user_id          uuid not null references auth.users(id) on delete cascade,
  file_type        text not null,               -- pdf, epub, xlsx, csv, docx, pptx, svg, png, xmind, opml, mm, md, mmd, zip
  storage_path     text not null,               -- Supabase Storage (siempre)
  size             bigint not null,
  onedrive_item_id text,
  onedrive_url     text,
  onedrive_status  text not null default 'pending', -- pending | uploaded | failed | skipped
  upload_attempts  int not null default 0,
  created_at       timestamptz not null default now()
);
create index on files (product_id);
create index on files (onedrive_status) where onedrive_status in ('pending', 'failed');

create table jobs (
  id         uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  user_id    uuid not null references auth.users(id) on delete cascade,
  kind       text not null,                     -- generate | regenerate_item | remodel | duplicate_market | upload
  payload    jsonb not null default '{}',
  status     job_status_t not null default 'queued',
  progress   jsonb not null default '{}',       -- {item_id: pct, ...} y total
  error      text,
  logs       jsonb not null default '[]',       -- sin datos sensibles
  attempts   int not null default 0,
  locked_at  timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on jobs (status, created_at) where status = 'queued';

create table ai_usage (
  id            bigint generated always as identity primary key,
  user_id       uuid not null references auth.users(id) on delete cascade,
  product_id    uuid references products(id) on delete set null,
  model         text not null,
  input_tokens  int not null,
  output_tokens int not null,
  cost_usd      numeric(10,5) not null,
  created_at    timestamptz not null default now()
);
create index on ai_usage (user_id, created_at);

create table storage_connections (
  user_id           uuid not null references auth.users(id) on delete cascade,
  provider          text not null,              -- 'onedrive'
  account_label     text,
  access_token_enc  bytea not null,             -- Fernet (clave en env del backend)
  refresh_token_enc bytea not null,
  expires_at        timestamptz not null,
  created_at        timestamptz not null default now(),
  primary key (user_id, provider)
);

-- RLS
alter table niches              enable row level security;
alter table templates           enable row level security;
alter table products            enable row level security;
alter table product_items       enable row level security;
alter table files               enable row level security;
alter table jobs                enable row level security;
alter table ai_usage            enable row level security;
alter table storage_connections enable row level security;

create policy "catalog read" on niches    for select to authenticated using (active);
create policy "catalog read" on templates for select to authenticated using (active);

-- El usuario solo LEE sus datos desde el frontend; las escrituras van por el backend (service role).
create policy "own rows" on products      for select to authenticated using (user_id = auth.uid());
create policy "own rows" on product_items for select to authenticated using (user_id = auth.uid());
create policy "own rows" on files         for select to authenticated using (user_id = auth.uid());
create policy "own rows" on jobs          for select to authenticated using (user_id = auth.uid());
create policy "own rows" on ai_usage      for select to authenticated using (user_id = auth.uid());
-- storage_connections: sin policy para authenticated → invisible desde el frontend (tokens).

-- Storage: bucket privado 'products', ruta '<user_id>/<product_id>/...', descargas por URL firmada del backend.
```

---

## 4. Interfaces clave (Python)

```python
# backend/app/content/engines.py
class ContentGenerator(Protocol):
    """Única puerta a la IA. El input del usuario va delimitado como dato."""
    async def propose_problems(self, niche: str, market: Market) -> list[Problem]: ...           # 5
    async def build_outline(self, req: PackageRequest) -> PackageOutline: ...                    # 1+3+2
    async def generate_item(self, item: ItemOutline, ctx: PackageContext) -> ProductContent: ... # schema según formato
    async def commercial_sheet(self, pkg: PackageContext) -> CommercialSheet: ...
    async def adapt_to_market(self, pkg: PackageContext, target: Market) -> PackageOutline: ...  # no traducción literal

# backend/app/generators/base.py
@dataclass(frozen=True)
class FileArtifact:
    filename: str          # 'guia-principal.pdf'
    file_type: str         # 'pdf'
    content: bytes
    mime: str

class FileGenerator(Protocol):
    format: ClassVar[Format]
    content_schema: ClassVar[type[ProductContent]]   # schema Pydantic propio del formato
    outputs: ClassVar[tuple[str, ...]]               # ('xlsx', 'csv')
    def generate(self, content: ProductContent, template: Template) -> list[FileArtifact]: ...

REGISTRY: dict[Format, FileGenerator] = {}
def register(gen: FileGenerator) -> FileGenerator: ...   # decorador; agregar formato = agregar módulo

# backend/app/templates_engine/model.py
class Template(BaseModel):
    id: str
    name: str
    palette: Palette           # primary, secondary, accent, bg, text, muted, callout_*
    fonts: Fonts               # heading, body, mono (Google Fonts OFL, archivos en templates/_fonts)
    spacing: Spacing
    cover_style: Literal["full-bleed", "split", "centered", "band", "notebook"]
    callout_style: Literal["boxed", "left-bar", "pill", "sticky-note"]
    base_dir: Path             # templates/<id>/
    def render_html(self, kind: str, context: dict) -> str: ...   # Jinja2 con autoescape=True
    def office_theme(self) -> OfficeTheme: ...                    # solo colores + tipografías (xlsx/docx/pptx)

# backend/app/storage/base.py
class StorageProvider(Protocol):
    name: ClassVar[str]                      # 'supabase' | 'onedrive' | futuro 'gdrive'
    async def ensure_folder(self, user_id: UUID, path: str) -> str: ...
    async def upload(self, user_id: UUID, path: str, data: bytes, mime: str) -> StoredRef: ...  # upload session si > 4 MB
    async def share_url(self, user_id: UUID, ref: StoredRef, expires_in: int) -> str: ...
```

**Remodelar sin IA:** el pipeline calcula qué cambió. Plantilla o formato de salida → solo se re-ejecutan `FileGenerator`s sobre el `content` guardado (si el nuevo formato tiene otro schema, se hace una conversión determinista cuando existe; si no existe, esa pieza sí pasa por la IA y la UI lo avisa antes de confirmar). Idioma, tono, público o "regenerar pieza" → IA solo para las piezas afectadas.

---

## 5. Decisiones tomadas (2026-10-20)

| # | Decisión | Impacto en el plan |
|---|---|---|
| D1 | **Uso personal** (un solo usuario) | Sin pagos ni onboarding. Igual se mantiene RLS y el test de acceso cruzado (criterio de aceptación). |
| D2 | **Email y contraseña** (Supabase Auth). *Cambiado el 2026-10-21; antes era Google.* | Sin registro público: el usuario se crea en el dashboard. Además, el backend y un trigger en la base aceptan solo los emails permitidos. |
| D3 | Cuentas de Supabase y Netlify ya existen; Railway se crea después | Proyectos y dominios se configuran juntos al llegar al deploy (Fase 7). En desarrollo se usa Supabase local (`npx supabase start`, Docker). |
| D4 | **LATAM en USD** por defecto | Moneda configurable en `config`, sin selector en la UI de v1. |
| D5 | Principal de 25 a 40 páginas; order bumps y bonus de 5 a 15 | Se fija en los prompts y en los schemas (mínimos de secciones). |
| D6 | **Sin tope de costo** | Se quita el cost guard por usuario. Se mantiene el registro en `ai_usage` solo para ver cuánto cuesta cada paquete. El rate limit queda como protección mínima ante loops (no por cuota). |
| D7 | Mapas mentales con **render SVG propio en Python** | Sin Chromium en la imagen. |
| D8 | Checklist con **espacios para escribir a mano** | Sin AcroForm en v1. |
| D9 | Mockup de portada con **CSS 3D** | Sin imágenes de IA. |
| D10 | No hay PDF Agent previo | **WeasyPrint**. |
| D11 | ~~OneDrive personal~~ → **Google Drive** (*cambiado el 2026-10-22: el usuario usa Gmail*), carpeta `Mi unidad/ProductForge/...` | Permiso `drive.file`. OneDrive se implementó y se descartó. |
| D12 | Plantillas 11 y 12 **después** de v1 | 10 plantillas en Fase 3c. |
| D13 | **Git solo local** por ahora | `git init` en `C:\Proyecto-Donoso`, sin remoto. |

Herramientas locales: Node 20 + npm (no hay pnpm), `uv` para instalar Python 3.12 y las dependencias del backend, Docker para Supabase local y para WeasyPrint.

## 5b. Preguntas originales (resueltas arriba)

**Bloqueantes para Fase 1**

- **D1. ¿Quién usa la app?** ¿Solo tú (herramienta interna) o es un SaaS para clientes? Cambia auth, límites de costo, pagos y onboarding. *Mi supuesto si no respondes: herramienta interna con pocos usuarios invitados, sin cobros.*
- **D2. Método de login:** email + magic link, email + contraseña, Google, o Microsoft (reutilizaría el login para OneDrive). *Supuesto: magic link.*
- **D3. ¿Ya tienes proyecto Supabase, Railway y Netlify creados?** ¿Dominios para CORS?

**Bloqueantes para Fase 2**

- **D4. Moneda LATAM:** ¿un país objetivo (MXN, COP, CLP, ARS…), USD como neutra, o selector por producto? *Supuesto: USD por defecto + selector.*
- **D5. Extensión objetivo del producto principal** (p. ej. 25–40 páginas) y de bumps/bonus (5–15). Impacta directamente el costo por paquete.
- **D6. Presupuesto de IA:** ¿tope diario por usuario en USD? *Supuesto: US$5/día configurable.*

**Bloqueantes para Fase 3**

- **D7. Mapas mentales:** ¿aceptas el render SVG propio en Python (decisión 4), o prefieres fidelidad exacta de Markmap/Mermaid usando Playwright (imagen Docker más pesada)?
- **D8. Checklist rellenable:** ¿lo quieres en v1 (campos AcroForm) o basta con espacios para escribir a mano?
- **D9. Mockup de portada:** "mockup simple" = render CSS 3D del libro/tablet con la portada. Sin imágenes generadas por IA. ¿Ok?

**Otras**

- **D10. PDF Agent (FastAPI + ReportLab):** no está en este directorio. Si existe en otro repo, pásame la ruta y evalúo. Trade-off anticipado: ReportLab da control fino y no necesita GTK, pero cada plantilla sería código Python; WeasyPrint permite plantillas HTML/CSS como datos (requisito de la sección 5). Mi recomendación preliminar es WeasyPrint y reutilizar del PDF Agent solo lo que sirva (helpers, endpoints).
- **D11. OneDrive personal o de trabajo (Microsoft 365)?** `Files.ReadWrite.AppFolder` funciona en ambos, pero con cuenta de empresa puede requerir consentimiento del administrador del tenant. Con AppFolder la ruta real será `/Aplicaciones/ProductForge/...` en lugar de `/ProductForge/...`. ¿Te sirve?
- **D12. Plantillas opcionales 11 y 12** (Brasil Vibrante, Tech/Notion-like): ¿en v1 o después?
- **D13. Git:** el directorio no es un repo. ¿Lo inicializo aquí (`C:\Proyecto-Donoso`) y lo subo a GitHub (¿qué nombre de repo?), o solo local por ahora?
