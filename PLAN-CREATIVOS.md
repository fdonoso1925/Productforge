# Plan — Módulo «Creativos para Meta Ads»

Respuesta a `prompt-modulo-creativos-meta-ads.md` §13. **Sin código todavía**: se espera aprobación.
Lo único hecho: las claves de Gemini y Pixabay están en `backend/.env` (ignorado por git).

## 1. Lo que encontré y qué se reutiliza

| Pieza existente | Uso en el módulo |
|---|---|
| Auth Supabase + RLS (solo `select` al dueño, escrituras por el backend) | Mismo patrón para las tablas `ad_*` |
| Tabla `jobs` + worker (`FOR UPDATE SKIP LOCKED`) | Jobs nuevos: `ad_plan`, `ad_render`, `ad_images`. **Requiere migración**: `jobs.kind` tiene un `check` con la lista cerrada de tipos |
| `prompts/<mercado>/` versionado, nativo por mercado | `prompts/<mercado>/ads/` (ángulos, avatar, copy, políticas, score) |
| `ContentService` / `claude_client` (salida Pydantic, reintento con feedback, costo en `ai_usage`) | Motor de estrategia, copy, revisión de políticas y pre-score |
| `PackageBuilder`, `package_request`, historial/versiones (`parent`/`root`) | Un lote parte de un producto del historial (nicho, problema, público, promesa, bonus, referencia, portada) |
| `templates/<id>/template.json` + `_base/` Jinja2 + fuentes OFL (12 familias) | Misma idea para `ad_templates/<id>/`; se reusa la paleta de la plantilla del producto |
| `render.py` (WeasyPrint → PDF → pdfium PNG) | **Composición de anuncios** (ver decisión 2) |
| `StorageProvider` + `SyncTarget` (Google Drive, copia con reintentos) | Archivos finales y copia a Drive (**Drive, no OneDrive**: el documento quedó desactualizado) |
| `safe_fetch` anti-SSRF, `cover_image` (validación de imágenes), rate limit, `wrap_user_data` | Descarga de fotos de Pixabay, validación de imágenes, defensa ante inyección |
| Wizard, `CoverPicker`, historial, `ConfirmButton` | UI del módulo y confirmación de acciones con costo |

Navegación: no hay menú principal; el inicio tiene tarjetas y cada pantalla un enlace «Inicio». «Creativos» irá como tarjeta nueva en el inicio y enlace en los encabezados.

## 2. Hallazgo que cambia el diseño: Gemini NO tiene plan gratuito para imágenes

Verificado en la [página de precios oficial](https://ai.google.dev/gemini-api/docs/pricing) y con una llamada real a tu clave:

- **Ningún modelo de imagen tiene Free Tier** (todas las celdas dicen «Not available»).
- Tu clave devolvió `429 … generate_content_free_tier_requests, limit: 0` (no se cobró nada).
- `gemini-2.5-flash-image` (el del documento) figura como **deprecated**. Modelos vigentes y precio por imagen 1K:
  `gemini-3.1-flash-lite-image` ≈ **0,034 USD** (0,017 en batch) · `gemini-nano-banana-2.1` ≈ 0,034 · `gemini-3.1-flash-image` ≈ 0,067 · `gemini-3-pro-image` ≈ 0,134.
- Las cuotas gratuitas, donde existen, se reinician a **medianoche del Pacífico**, no UTC.

**Pixabay** (verificado en su [documentación](https://pixabay.com/api/docs/) y con tu clave): 100 peticiones / 60 s por clave (cabeceras `X-RateLimit-*`, 429 si se excede), caché obligatoria de 24 h, prohibido el hotlinking permanente (hay que descargar), `webformatURL` caduca en 24 h, mostrar la fuente al usuario, `safesearch`/`orientation`/`image_type` disponibles. Gratis.

Consecuencias para el diseño (a decidir, §7):
- «Contador de cuota gratis» pasa a **presupuesto diario en USD** (gasto real por proveedor).
- Pixabay sigue siendo gratis, pero son fotos de stock: pueden traer texto o marcas incrustadas (la foto de mi prueba traía un cartel con letras), y personas reales. Hace falta un filtro y no usarlas en nichos sensibles.

## 3. Motor de composición: WeasyPrint en vez de Playwright

El documento pide Playwright (Chromium). Prueba hecha con tu stack: **1080×1350 en ~1,0 s, 1080×1920 en ~1,2 s, 1080×1080 en ~0,8 s**, tildes correctas, fuente embebida, degradado y zona segura de Stories. Chromium sumaría ~400 MB a la imagen de Railway y una dependencia nueva. Riesgos y mitigaciones:
- El degradado con transparencia deja una banda visible en pdfium → se compone el velo como PNG o con tramos escalonados.
- Sin `backdrop-filter` ni `mix-blend-mode`: las 12 plantillas se diseñan sin ellos.

## 4. Plan por fases

| Fase | Entrega | Gasto de imágenes |
|---|---|---|
| 1 | Este plan | — |
| 2 | Motor de estrategia: avatares, ángulos (archivos de prompts nativos pt-BR / es-LATAM), hook, copy de Ads Manager, checklist de políticas (🟢🟡🔴 con reescritura) y pre-score; salida Pydantic; tests con `FakeLLM` | 0 |
| 3 | Composición WeasyPrint: 4 plantillas sin IA (headline bold, mockup, checklist, nota), 3 ratios con zonas seguras, editar texto y re-render sin IA. **Se verifican los specs vigentes en la Ads Guide de Meta** | 0 |
| 4 | `ImageProvider` + `ImageRouter` (+ `PixabayProvider`, `GeminiImageProvider`, esqueletos Pexels/OpenAI), presupuesto, caché por hash de escena, las 12 plantillas | Según decisión 1 |
| 5 | Wizard, galería, editor rápido, ZIP, CSV de copys, copia a Drive | — |
| 6 | Historial, iteración de creativos, carga de métricas (CSV de Ads Manager), panel de aprendizaje | — |
| 7 | Tests end-to-end, rate limits, documentación | — |

Cada fase cierra con tests en verde, commit y resumen corto. El valor llega pronto: tras la fase 3 ya hay anuncios publicables sin ningún proveedor de imágenes.

## 5. Base de datos (migración `…_ads.sql`)

Se separan las bibliotecas configurables: **ángulos, políticas y plantillas viven en archivos versionados** (`prompts/<mercado>/ads/…`, `ad_templates/<id>/`), igual que los prompts y plantillas actuales (se editan con git, no necesitan tablas). En la base va lo que es dato del usuario.

```sql
create table ad_batches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  product_id uuid references products(id) on delete set null,   -- nulo = ingreso manual
  parent_batch_id uuid references ad_batches(id) on delete set null,  -- duplicado a otro idioma
  niche text not null, market market_t not null,
  brief jsonb not null,            -- nicho, problema, público, promesa, precio, bonus (copia del momento)
  avatars jsonb not null default '[]', angles jsonb not null default '[]',
  status text not null default 'planning' check (status in ('planning','review','generating','ready','error')),
  prompt_version text not null, created_at timestamptz not null default now()
);

create table ad_creatives (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references ad_batches(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  angle text not null, template_id text not null, ratio text not null check (ratio in ('4x5','9x16','1x1')),
  copy jsonb not null,             -- hook, textos de imagen, primary_short/long, headline, description, cta
  scene_prompt text, image_provider text, base_image_path text, image_credit jsonb,  -- id/autor/url/licencia
  final_image_path text, drive_url text,
  policy_status text check (policy_status in ('green','yellow','red')), policy_notes jsonb,
  pre_score int check (pre_score between 1 and 10), score_notes text,
  parent_creative_id uuid references ad_creatives(id) on delete set null, version int not null default 1,
  status text not null default 'planned', filename text not null,  -- <slug>_<mercado>_<angulo>_<plantilla>_<ratio>_v<n>.png
  created_at timestamptz not null default now(), unique (batch_id, filename)
);

create table ad_results (
  id uuid primary key default gen_random_uuid(),
  creative_id uuid not null references ad_creatives(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  day date not null, spend numeric, impressions int, clicks int, ctr numeric, cpc numeric,
  purchases int, cpa numeric, roas numeric, unique (creative_id, day)
);

create table ad_proofs (            -- testimonios y datos REALES cargados por el usuario (nunca inventados)
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  product_id uuid references products(id) on delete cascade,
  kind text not null check (kind in ('testimonial','stat','authority')),
  text text not null, author text, created_at timestamptz not null default now()
);

create table ad_image_cache (       -- caché de imágenes base por hash de la escena
  scene_hash text primary key, provider text not null, storage_path text not null,
  credit jsonb, created_at timestamptz not null default now()
);

create table ad_provider_usage (    -- presupuesto/consumo diario por proveedor
  provider text not null, day date not null, requests int not null default 0,
  cost_usd numeric not null default 0, primary key (provider, day)
);
-- + RLS (select del dueño) en todas, y jobs.kind ampliado con 'ad_plan','ad_render','ad_images'.
```

## 6. Interfaces (Python)

```python
class ImageProvider(Protocol):
    name: ClassVar[str]
    async def generate(self, *, prompt: str, aspect_ratio: str, style: str | None,
                       negative_prompt: str | None) -> ProviderImage: ...   # bytes + credit + coste
    def remaining(self) -> Budget: ...        # presupuesto restante (USD / peticiones)

class ImageRouter:                             # IMAGE_PROVIDERS=pixabay,gemini (orden configurable)
    async def image_for(self, scene: Scene) -> BaseImage   # caché → presupuesto → 429/falla → siguiente

class AdTemplate(BaseModel):                   # ad_templates/<id>/template.json
    id: str; zones: list[Zone]; fonts: Fonts; palette_from: Literal["ad","product"]
    uses_image: bool; uses_mockup: bool; safe_zones: dict[str, SafeZone]

class AdStrategyGenerator(Protocol):
    async def avatars(self, brief) -> list[Avatar]
    async def angles(self, brief, avatars, winners) -> list[AngleSuggestion]
    async def creatives(self, brief, angle, n) -> list[CreativeDraft]   # hook, copy, escena

class PolicyChecker(Protocol):
    async def review(self, draft, niche, proofs) -> PolicyVerdict       # 🟢🟡🔴 + motivo + reescritura
```

## 7. Decisiones que necesito de ti

1. **Imágenes de IA (Gemini no es gratis).** Recomendado: *Pixabay + plantillas sin imagen por defecto, y Gemini opcional* (activas la facturación de Google y fijas un tope diario en USD). Un lote de 6 imágenes ≈ 0,20 USD con `gemini-3.1-flash-lite-image`. Alternativas: (a) solo gratis, sin escenas de IA; (b) Gemini como principal con tope.
2. **Composición con WeasyPrint** (recomendado, probado) en lugar de Playwright.
3. **Destino de archivos: Google Drive** (el que ya usas), no OneDrive.
4. **Empezar por las fases 2 y 3** (sin gasto de imágenes) y decidir el proveedor al llegar a la 4.
5. Confirmo que «pixalab» es **Pixabay** (la clave funciona contra su API).

## 8. Riesgos y notas

- **Políticas de Meta**: el checklist es una ayuda, no una garantía de aprobación. Ningún creativo se publica solo.
- **Creativos ganadores**: no se pueden garantizar; la app maximiza variedad y aprende de métricas cargadas a mano.
- **Fotos de stock**: pueden traer texto, marcas o personas reconocibles; se filtrarán por etiquetas y se evitarán en salud, finanzas y maternidad.
- **Specs de Meta**: los tamaños del documento (1080×1350, 1080×1920, 1080×1080) no los verifiqué aún en la Ads Guide; se hará al cerrar la fase 3, como pide el documento.
- **Claves**: viven solo en `backend/.env`; pegadas en un chat, conviene **regenerarlas** al terminar el desarrollo.
- Costo de Claude por lote (estrategia + copy + políticas + score de ~12 creativos): del orden de centavos con Sonnet; se mostrará la estimación antes de generar.
