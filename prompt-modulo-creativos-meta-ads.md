# PROMPT — Módulo "Creativos para Meta Ads" (dentro de ProductForge)

> Pega este prompt en Claude Code, en el repo de tu app de productos digitales. También puedes guardarlo como `SPEC-creativos.md` y pedirle que lo lea.

---

## 0. Contexto y forma de trabajar

Actúa como **desarrollador full-stack senior y especialista en performance marketing para Meta Ads** (infoproductos low ticket, mercado Brasil y LATAM).

Vas a agregar un **módulo nuevo** a la app existente (ProductForge: Next.js + FastAPI + Supabase + OneDrive). No reescribas lo que ya existe: intégrate a su arquitectura, convenciones y `CLAUDE.md`.

Reglas:
1. **Primero explora el repo.** Antes de proponer nada, revisa:
   - modelo de datos,
   - generadores,
   - plantillas,
   - storage (`StorageProvider`),
   - jobs,
   - i18n.
   Luego entra en modo plan y devuélveme plan, cambios en la base de datos, interfaces nuevas y dudas. **No escribas código hasta que apruebe.**
2. Reutiliza lo existente:
   - auth,
   - RLS,
   - tabla de jobs,
   - prompts versionados por mercado (`prompts/<mercado>/`),
   - `StorageProvider` (OneDrive con respaldo en Supabase),
   - historial y versiones.
3. Trabaja por fases (sección 10). Al cerrar cada una: tests, commit y resumen corto.
4. Simplicidad ante todo. Las claves de API van solo en el backend, en variables de entorno, y se documentan en `.env.example`.
5. Actualiza `CLAUDE.md` con lo nuevo.

---

## 1. Objetivo

Agregar un menú **"Creativos"** en la navegación principal. El módulo genera **imágenes listas para subir como anuncios en Meta Ads** (Facebook e Instagram). Su objetivo es **atraer compradores del producto digital**, no conseguir likes.

Cada lote de creativos se construye a partir de **distintos ángulos de venta** del producto (sección 4). El usuario los prueba en Meta con un objetivo claro: **encontrar creativos ganadores**.

Por ahora, solo **imágenes estáticas** (y carrusel como extra opcional). Deja el diseño preparado para agregar video o motion más adelante.

---

## 2. Arquitectura de generación (híbrida): decisión clave

**No dependas de que la IA de imágenes escriba el texto dentro de la imagen.** Los modelos de imagen todavía se equivocan con acentos y ortografía en portugués y español, y además el texto quedaría "quemado" y no se podría editar.

El pipeline de cada creativo tiene 4 pasos:

1. **Estrategia y copy (Claude API, salida JSON validada con Pydantic).** Genera:
   - ángulo,
   - hook,
   - textos que van en la imagen,
   - textos del anuncio,
   - **descripción de la escena** para la imagen.
2. **Imagen base (API de generación de imágenes).** Genera la foto o ilustración **sin texto**: escena, persona, objeto, fondo.
   - Si el estilo lo permite, también puede usarse el mockup del producto generado por la app (portada del PDF o ebook).
3. **Composición (layout HTML/CSS → PNG con Playwright).** Una plantilla de anuncio combina imagen base, textos, colores, mockup y CTA visual.
   - El texto queda perfecto y es **editable desde la app**: cambiar el texto y re-renderizar **no vuelve a llamar a la IA de imágenes**.
4. **Export** en los tamaños de Meta (sección 6).

**Proveedor de imágenes intercambiable.** Crea una interfaz `ImageProvider` con un método del tipo `generate(prompt, aspect_ratio, style, negative_prompt) -> image_bytes`.

### 2.1 Estrategia de costo cero (decidida)

El módulo arranca **sin costo de imágenes**, combinando tres fuentes en este orden:

1. **`GeminiImageProvider` (principal).** Usa el **plan gratuito de la Gemini API** con el modelo de imagen Flash ("Nano Banana", hoy `gemini-2.5-flash-image` o el sucesor gratuito vigente).
   - Genera solo la escena, **sin texto**.
   - Antes de implementar, **verifica en la documentación oficial de Google AI** el ID del modelo, los límites diarios y por minuto del plan gratuito y sus condiciones de uso de datos. Resúmemelo en 3 líneas.
2. **`PixabayProvider` (respaldo automático).** Usa la API gratuita de Pixabay (la emisión de nuevas keys de Pexels está pausada).
   - Claude genera 2-3 **palabras clave en inglés** a partir de la escena. Se busca con `image_type=photo`, `safesearch=true` y la orientación según el ratio; luego se elige la foto y se recorta al ratio.
   - Se usa cuando:
     - se agota la cuota diaria de Gemini,
     - Gemini falla o rechaza el prompt,
     - el usuario elige "foto real" en la plantilla.
   - Cumple los términos de la API de Pixabay:
     - **descarga la imagen a nuestro storage** antes de usarla (está prohibido el hotlinking permanente a URLs de Pixabay);
     - **cachea las respuestas de búsqueda 24 h**;
     - respeta el rate limit (aprox. 100 requests por 60 s; lee los headers `X-RateLimit-*` y haz backoff ante un 429);
     - cuando la app muestre resultados de búsqueda al usuario, indica que vienen de Pixabay.
   - Guarda en la base de datos: ID de Pixabay, autor, URL de la página y licencia.
   - Revisa la **Content License de Pixabay** y respétala. En particular, no uses fotos con personas identificables de forma que sugiera que respaldan el producto o en contextos sensibles (salud, deudas, etc.). Para esos ángulos, prefiere escenas sin rostros reconocibles o generadas con IA.
   - Deja un `PexelsProvider` como esqueleto, por si más adelante se reabre la emisión de keys.
3. **Plantillas sin imagen.** Headline bold, mockup, checklist y nota no consumen ningún proveedor.

Reglas del sistema de respaldo (`ImageRouter`):
- Orden configurable por variable de entorno: `IMAGE_PROVIDERS=gemini,pixabay`.
- **Contador de cuota diaria** en la base de datos, por proveedor, que se reinicia según el reset del proveedor (Gemini: medianoche UTC). Antes de llamar a Gemini se revisa el contador; si no queda cuota, se pasa directo a Pixabay sin intentar.
- Ante un error 429 o de cuota, cambia a Pixabay de inmediato y registra el evento.
- **Caché** de imágenes base por hash del prompt de escena, para no gastar cuota en repeticiones.
- En la UI se muestra:
  - "Generaciones IA gratis restantes hoy: X",
  - un aviso cuando se está usando el respaldo de fotos de stock.
- Agregar un proveedor pagado más adelante (OpenAI, Imagen, Ideogram, Flux) debe ser **solo una clase nueva y una variable de entorno**. Deja un `OpenAIImageProvider` como esqueleto vacío para documentar el patrón, sin implementarlo.

Variables de entorno nuevas (documentar en `.env.example`):
```
GEMINI_API_KEY=
PIXABAY_API_KEY=
IMAGE_PROVIDERS=gemini,pixabay
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
GEMINI_DAILY_LIMIT=   # valor del plan gratuito vigente; deja margen de seguridad (~90%)
```

---

## 3. Flujo del usuario (wizard)

1. **Origen**:
   - **(a)** elegir un producto del historial (recomendado): reutiliza su nicho, problema, público, promesa, bonus y mockup, todo ya guardado como JSON; o
   - **(b)** ingresar nicho y producto manualmente: nicho, problema, público, promesa y precio.
2. **Mercado / idioma**: pt-BR (por defecto) o es-LATAM. El copy se genera **nativo** para cada mercado, no traducido.
3. **Investigación de avatar** (automática, editable). La IA propone:
   - 2-3 avatares, con situación, dolor, deseo, objeciones y lenguaje que usan;
   - el usuario elige uno o varios.
4. **Ángulos**: la app sugiere los 5-6 ángulos más prometedores para ese producto, con una breve justificación. El usuario marca cuáles quiere.
5. **Estilos visuales y formatos**: plantillas de anuncio (sección 5) y ratios (sección 6).
6. **Cantidad**: N creativos por ángulo (por defecto 2), para tener variaciones que testear.
7. **Revisión previa**:
   - tabla con cada creativo planificado (ángulo, hook, texto en imagen, estilo, escena);
   - el usuario edita o descarta filas **antes** de gastar en imágenes.
8. **Generación**: progreso por creativo.
9. **Resultado**:
   - galería por ángulo,
   - editor rápido de textos (re-render instantáneo),
   - regenerar solo la imagen base,
   - descarga individual o ZIP,
   - subida a OneDrive.

---

## 4. Ángulos de venta (biblioteca configurable)

Los ángulos se guardan en base de datos o en archivos de prompts, **no hardcodeados**. Cada ángulo tiene: descripción, cuándo usarlo, estructura de hook, ejemplos por mercado y estilos visuales recomendados.

Ángulos iniciales:

1. **Dolor**: nombra la situación frustrante tal como la vive el avatar.
2. **Solución / mecanismo**: el "cómo" único del producto ("el método X en 15 minutos al día").
3. **Transformación / resultado**: el después deseado, concreto y con plazo.
4. **Persona / identificación**: "para mamás que trabajan y…". Habla a un público específico **sin afirmar atributos personales del espectador** (ver sección 7).
5. **Objeción**: derriba la excusa principal ("aunque no tengas tiempo…").
6. **Curiosidad / secreto**: un dato o error poco conocido.
7. **Mito vs. verdad**.
8. **Error común**: "el error que comete el 90% al…".
9. **Lista / beneficios**: "5 cosas que…".
10. **Oferta / precio**: lo que incluye el paquete (principal + bonus) frente a un precio bajo. Solo con precio real.
11. **Autoridad / prueba**: solo con **datos o testimonios reales** que entregue el usuario (sección 7).
12. **Urgencia / oportunidad**: solo si existe una urgencia real (lanzamiento, precio de lanzamiento).
13. **Comparación**: tu método frente a la forma tradicional.
14. **Nativo / UGC**: imagen que parece contenido orgánico (nota, post, foto casera), menos "anuncio".

**Framework de hook** obligatorio para cada creativo:
- el hook se lee en **menos de 2 segundos**;
- máximo ~8-10 palabras en el titular de la imagen;
- texto total en la imagen mínimo: legible en el celular, con alto contraste.

---

## 5. Plantillas de anuncio (mínimo 10, definidas como datos)

Cada plantilla vive en `ad_templates/<id>/`, con un `template.json` (zonas, tipografías, colores, si usa imagen de IA, mockup o solo texto) y su HTML/CSS. Usa los **design tokens** que ya existen en la app y permite aplicar la paleta de la plantilla del producto, para mantener coherencia con el ebook.

1. **Headline bold**: solo texto grande sobre color sólido. No usa IA de imágenes.
2. **Foto + titular**: imagen de IA a sangre completa, titular con overlay y degradado.
3. **Mockup del producto**: portada o mockup del ebook, beneficios y precio/CTA.
4. **Nota / post-it**: texto estilo nota manuscrita (nativo).
5. **Post de texto genérico**: estilo publicación de red social **sin logos ni marcas de ninguna plataforma real**.
6. **Notificación genérica**: estilo alerta del celular, sin imitar la interfaz de una app real.
7. **Checklist / lista**: lista de beneficios o errores con ✓ o ✗.
8. **Antes → Después (situación)**: contraste de situación o emocional, **no de cuerpos** (sección 7).
9. **Comparativo**: dos columnas, "forma tradicional" vs. "con el método".
10. **Pregunta / curiosidad**: pregunta grande que abre un loop.
11. **Testimonio real**: cita y nombre/iniciales. **Solo** con testimonios cargados por el usuario.
12. **Oferta / stack**: el paquete completo con valor de cada pieza y precio final.

Requisitos de las plantillas:
- respetar las **zonas seguras** de 9:16 (márgenes arriba y abajo libres de texto clave para no chocar con la interfaz de Stories y Reels);
- tipografías con licencia libre, embebidas;
- preview en miniatura generada automáticamente.

---

## 6. Formatos de export (Meta)

- **4:5 — 1080×1350 px**: feed (formato principal).
- **9:16 — 1080×1920 px**: Stories y Reels. Es una **composición propia**, no un recorte del feed.
- **1:1 — 1080×1080 px**: carrusel y ubicaciones generales.
- Opción de export en alta resolución (1440×1800 y 1440×2560).
- PNG (o JPG de alta calidad), por debajo de 30 MB.
- Los specs se definen en un archivo de configuración, para actualizarlos sin tocar código.
- Antes de cerrar la fase 3, **verifica los specs vigentes en la Ads Guide oficial de Meta**.

**Nomenclatura de archivos** para testear y leer resultados:

```
<producto-slug>_<mercado>_<angulo>_<plantilla>_<ratio>_v<n>.png
```

---

## 7. Cumplimiento de políticas de Meta (obligatorio)

Agrega un **paso de revisión automática** (Claude con un checklist) antes de renderizar. Cada creativo recibe un semáforo: 🟢 OK, 🟡 revisar, 🔴 bloquear, con el motivo y una **reescritura sugerida**.

Reglas mínimas:
- **Atributos personales**: no afirmar ni insinuar características del espectador. Esto incluye salud física o mental, peso, situación financiera, embarazo, religión, orientación, etc.
  - ❌ "¿Estás endeudado?"
  - ✅ "Para quien quiere salir de las deudas"
- **Salud, peso y estética**: nada de antes/después de cuerpos, promesas de resultados garantizados ni enfoque en partes del cuerpo.
- **Finanzas**: nada de promesas de ingresos garantizados ni "hazte rico rápido".
- **Prueba social**: prohibido **inventar** testimonios, cifras, reseñas o "X personas ya compraron". Solo se usan datos que el usuario cargue explícitamente.
- **Marcas e interfaces**: nada de logos, marcas o interfaces de plataformas reales (Instagram, WhatsApp, iPhone, etc.) ni personas famosas.
- **Urgencia falsa**: prohibida (contadores o "últimas unidades" falsos).
- **Imágenes de IA con personas**: deben verse naturales. Nada de menores en contextos sensibles.

Los nichos sensibles (salud, maternidad, finanzas, peso) activan una revisión más estricta. Este checklist vive en un archivo editable.

---

## 8. Copy del anuncio (además de la imagen)

Para cada creativo genera, en el idioma del mercado:
- **Texto principal** (primary text): 2 variantes, una corta (≤125 caracteres) y una larga con historia, beneficios y CTA;
- **Título** (headline, ≤40 caracteres);
- **Descripción** (≤30 caracteres);
- **CTA sugerido** de Meta (Comprar, Más información, etc.).

Todo se puede copiar con un clic y se exporta en un `.csv` por lote, con columnas compatibles para cargar en Ads Manager.

---

## 9. "Creativos ganadores": testing y aprendizaje

No se puede garantizar que un creativo gane. La app sí debe **maximizar la probabilidad y aprender**:

1. **Pre-score heurístico**: Claude puntúa cada creativo (1-10) según:
   - claridad del hook,
   - especificidad,
   - relevancia para el avatar,
   - contraste visual,
   - legibilidad en celular,
   - riesgo de política.
   Explica el puntaje y sugiere una mejora.
2. **Diversidad obligatoria**: cada lote cubre al menos 3 ángulos distintos y 2 estilos visuales, para que Meta tenga variedad real que testear.
3. **Registro de resultados (manual en esta fase)**:
   - el usuario carga métricas por creativo (CTR, CPC, CPA, ROAS, compras) a mano o importando un CSV exportado de Ads Manager;
   - el emparejamiento se hace por nombre de archivo.
4. **Aprendizaje**:
   - un panel muestra qué ángulos, plantillas y hooks funcionan mejor por nicho y mercado;
   - en los lotes siguientes, la app **prioriza los ángulos ganadores** y propone **iteraciones de los ganadores**: mismo ángulo, nuevo hook o nueva imagen.
5. **Futuro (no implementar ahora, solo dejar preparado)**: integración con la **Meta Marketing API** para subir creativos y leer métricas automáticamente.

---

## 10. Datos, historial y almacenamiento

Tablas nuevas (ajústalas a lo que ya existe y justifica los cambios):
- `ad_batches`: id, user_id, product_id (nullable), niche, market, avatars (JSON), created_at.
- `ad_creatives`:
  - id, batch_id, angle, template_id, ratio,
  - copy (JSON: hook, textos de imagen, primary text, headline, descripción, CTA),
  - scene_prompt, base_image_path,
  - final_image_path, onedrive_url,
  - policy_status, policy_notes,
  - pre_score,
  - parent_creative_id (iteraciones), version.
- `ad_results`: creative_id, fecha, spend, impressions, clicks, ctr, cpc, purchases, cpa, roas.
- `ad_angles` y `ad_templates`: bibliotecas configurables.

En el historial, igual que en productos, se puede:
- filtrar,
- ver versiones,
- **iterar un creativo**,
- cambiar plantilla o ratio **sin regenerar la imagen base**,
- duplicar un lote al otro idioma.

OneDrive, usando el `StorageProvider` existente:

```
/ProductForge/<mercado>/<nicho>/<producto>/creativos/<YYYY-MM-DD>_lote-<n>/
    feed-4x5/
    stories-9x16/
    cuadrado-1x1/
    copys.csv
```

**Costos**:
- mostrar el costo estimado antes de generar;
- límite diario configurable por usuario;
- guardar en caché las imágenes base para reutilizarlas.

---

## 11. Fases

1. **Exploración y plan**: leer el repo y proponer plan, base de datos e interfaces. Esperar aprobación.
2. **Motor de estrategia**: avatares, ángulos, hooks y copy con salida JSON. Incluye el checklist de políticas y el pre-score.
3. **Composición**: Playwright → PNG, 4 plantillas que **no** usan IA de imágenes (headline bold, mockup, checklist, nota), los 3 ratios y las zonas seguras.
4. **Proveedores de imagen (costo cero)**:
   - `GeminiImageProvider` + `PixabayProvider` + `ImageRouter`,
   - contador de cuota,
   - caché y prompts de escena,
   - las 12 plantillas completas.
5. **UI del wizard y galería**: editor rápido, ZIP, CSV de copys, OneDrive.
6. **Historial, iteración y resultados**: carga de métricas, panel de aprendizaje, priorización de ángulos.
7. **Endurecimiento**: tests end-to-end, rate limits y documentación.

---

## 12. Criterios de aceptación

- [ ] Desde un producto del historial obtengo un lote con al menos 3 ángulos × 2 variantes, en 4:5 y 9:16, sin errores.
- [ ] El texto en las imágenes no tiene errores de acentos ni ortografía en pt-BR ni en es (el texto lo renderiza el HTML, no la IA de imágenes).
- [ ] Puedo editar el texto de un creativo y re-renderizarlo en segundos **sin costo de IA de imágenes**.
- [ ] Cada creativo tiene copy completo para Ads Manager, semáforo de políticas y pre-score con explicación.
- [ ] Ningún creativo contiene testimonios, cifras o marcas inventadas.
- [ ] Los archivos llegan a OneDrive en la estructura definida, con la nomenclatura de testeo.
- [ ] Puedo cargar resultados y la app prioriza los ángulos ganadores en el siguiente lote.
- [ ] Las claves de Gemini y Pixabay viven solo en el backend.
- [ ] Con la cuota de Gemini agotada (simúlala en un test), el lote se completa igual usando Pixabay, sin errores visibles para el usuario.
- [ ] El costo de imágenes del módulo es USD 0 en uso normal; la UI muestra la cuota gratis restante.

---

## 13. Primera respuesta que espero

Sin código. Respóndeme con:
1. Lo que encontraste en el repo y qué piezas vas a reutilizar.
2. Plan por fases.
3. SQL de las tablas nuevas.
4. Interfaces: `ImageProvider`, `ImageRouter`, `AdTemplate`, `AdStrategyGenerator`, `PolicyChecker`.
5. Resumen de los límites vigentes del plan gratuito de Gemini (imagen) y de la API de Pixabay, verificados en su documentación oficial.
6. Dudas que necesito resolver.
