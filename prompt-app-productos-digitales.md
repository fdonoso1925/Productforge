# PROMPT — App generadora de productos digitales low ticket (BR + LATAM)

> Pega este prompt completo en Claude Code. También puedes guardarlo en la raíz del repo como `SPEC.md` y pedirle a Claude que lo lea.

---

## 0. Rol y forma de trabajar

Actúa como **arquitecto de software senior y desarrollador full-stack**. Construirás una aplicación web llamada **ProductForge** (nombre provisional).

Reglas de trabajo:
1. **Antes de escribir código**, lee este documento completo y entra en modo plan. Devuélveme:
   - un plan por fases,
   - la estructura de carpetas,
   - el modelo de datos,
   - las dudas que bloqueen decisiones.
   No avances hasta que yo apruebe el plan.
2. Trabaja **por fases** (sección 11). Al cerrar cada fase:
   - ejecuta los tests,
   - haz commit con un mensaje claro,
   - dame un resumen corto de qué quedó listo y qué falta.
3. Prioriza **simplicidad**. Usa la solución más simple que cumpla el requisito. No agregues microservicios, colas complejas ni abstracciones que no se necesiten hoy. Deja el código preparado para escalar sin construir la escala de antemano.
4. Crea y mantén un `CLAUDE.md` en la raíz con:
   - stack,
   - comandos (dev, test, lint, deploy),
   - convenciones,
   - decisiones de arquitectura.
5. Nunca pongas claves ni secretos en el código. Todo va en variables de entorno y existe un `.env.example` documentado.

---

## 1. Objetivo del producto

La app genera **productos digitales low ticket de alto valor percibido**. Cada producto **resuelve un problema puntual y específico** dentro de un nicho.

El usuario entrega:
- **Nicho**: lo selecciona de una lista o lo escribe libremente.
- **Problema específico**: opcional. Si no lo da, la app propone 5 problemas puntuales del nicho para que elija uno.
- **Idioma / mercado**: Portugués (Brasil) por defecto, o Español (LATAM).
- **Formato principal**: ver sección 4.
- **Plantilla visual**: una de al menos 10, ver sección 5.

Con eso, la app genera un **paquete comercial completo**:

| Pieza | Cantidad | Descripción |
|---|---|---|
| Producto principal | 1 | Resuelve el problema central |
| Order bumps | mínimo 3 | Complementos de bajo precio que aceleran o profundizan el resultado del principal |
| Bonus | mínimo 2 | Regalos que aumentan el valor percibido y quitan objeciones |

Cada pieza es un archivo descargable, en el formato que mejor le sirva. No todas tienen que ser PDF.

**Principio rector:** cada pieza responde a "¿qué problema concreto resuelve y en cuánto tiempo?". Contenido genérico o de relleno = fallo.

---

## 2. Stack técnico

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind + shadcn/ui. Deploy en Netlify.
- **Backend:** FastAPI (Python 3.12) para generación de contenido y archivos. Deploy en Railway.
- **Base de datos y auth:** Supabase:
  - Postgres,
  - Auth,
  - Storage como respaldo de archivos,
  - RLS activado en todas las tablas.
- **IA:** API de Claude (Anthropic) llamada **solo desde el backend**. Pide salida estructurada (JSON validado con Pydantic) para todo el contenido.
- **Generación de archivos (backend):**
  - PDF y ebook PDF: HTML + CSS → PDF con **WeasyPrint** (o Playwright si se necesita JS). Las plantillas son HTML/Jinja2, así que agregar una nueva no requiere tocar lógica.
  - Si ya existe mi **PDF Agent (FastAPI + ReportLab)** en el repo, evalúa reutilizarlo o migrarlo. Explícame el trade-off antes de decidir.
  - EPUB: `ebooklib`.
  - Excel / Sheets: `openpyxl`, con fórmulas reales, formato y validaciones. También exporta `.csv` para importar en Google Sheets.
  - Word editable: `python-docx`.
  - PowerPoint editable: `python-pptx`.
  - Mapas mentales y conceptuales:
    - fuente en **Markdown/Markmap** y **Mermaid**,
    - export a SVG/PNG/PDF,
    - versión **editable**: `.xmind` u `.opml`/`.mm` (FreeMind), importable en XMind, MindMeister o Miro.
- **Almacenamiento externo:** **OneDrive** vía Microsoft Graph API como destino principal (sección 8).
- **Tareas largas:** una tabla `jobs` en Postgres más un worker simple (o `BackgroundTasks` de FastAPI al inicio). El frontend consulta el estado por polling. No introduzcas Celery/Redis salvo que sea necesario y me lo justifiques.

---

## 3. Flujo del usuario (UX simple, tipo wizard)

1. **Nicho**: selector con nichos sugeridos (sección 6) más un campo libre.
2. **Problema**:
   - la IA propone 5 problemas puntuales con su "dolor", su "resultado prometido" y un "público exacto";
   - el usuario elige uno o lo edita.
3. **Mercado**: `pt-BR` (por defecto) o `es-LATAM`.
4. **Formato principal**: cards con icono y una breve descripción.
5. **Plantilla visual**: galería con **preview en miniatura real** de cada plantilla.
6. **Revisión de la estructura**: antes de generar archivos, la app muestra un **outline editable** del paquete completo:
   - producto principal,
   - 3+ order bumps,
   - 2+ bonus,
   - para cada pieza: título, promesa, índice y formato.
   El usuario aprueba o ajusta. Esto ahorra tokens y tiempo.
7. **Generación**: barra de progreso por pieza.
8. **Resultado**:
   - descarga individual o ZIP,
   - link a la carpeta en OneDrive,
   - **ficha comercial** del paquete (sección 7).

Todo el wizard debe poder completarse en **menos de 2 minutos de interacción**, sin contar el tiempo de generación.

---

## 4. Formatos soportados

Arquitectura de **generadores enchufables**: cada formato es un módulo que implementa la misma interfaz, por ejemplo `generate(content: ProductContent, template: Template) -> list[FileArtifact]`. Agregar un formato nuevo = agregar un módulo, sin tocar el resto.

Formatos iniciales:

1. **PDF guía / ebook**: el principal, maquetado con la plantilla elegida.
2. **Ebook EPUB**: para lectores de ebooks.
3. **Mapa mental**: idea central con ramas.
4. **Mapa conceptual**: conceptos y relaciones etiquetadas.
5. **Planilla / Sheet**: calculadoras, trackers, planners y presupuestos en `.xlsx` funcional.
6. **Checklist / Workbook**: PDF con espacios para escribir (opcional: PDF rellenable).
7. **Blueprint**: plan paso a paso con fases, tiempos, entregables y errores comunes.
8. **Plantillas editables**: `.docx` o `.pptx` que el comprador personaliza (guiones, scripts, mensajes, documentos).
9. **Planner / Calendario**: 7, 21 o 30 días.
10. **Swipe file / Banco de textos**: scripts, mensajes o frases listas para copiar.

Cada formato define:
- qué estructura de contenido necesita (schema Pydantic propio),
- qué tipos de archivo exporta.

La IA genera **contenido estructurado** y el generador lo convierte en archivo. **Nunca pidas a la IA que escriba HTML final ni código de archivos.**

---

## 5. Plantillas visuales (mínimo 10)

Las plantillas se definen como **datos**, no como código:
- carpeta `templates/<id>/` con `template.json` (paleta, tipografías, espaciados, estilo de portada, estilo de cajas/callouts) y los HTML/Jinja2 base;
- un sistema de **design tokens** compartido;
- cada plantilla aplicable a PDF, ebook, checklist, blueprint y planner;
- en Sheets, Word y PPT, la plantilla solo aplica colores y tipografías.

Plantillas iniciales:

1. **Minimal Clean**: blanco, tipografía sans, mucho aire.
2. **Editorial Premium**: estilo revista, serif en títulos, columnas.
3. **Bold Moderno**: bloques de color fuerte, títulos grandes.
4. **Soft Pastel**: tonos suaves, ideal para maternidad, bienestar y relaciones.
5. **Corporativo Pro**: azul/gris, gráficos, ideal para finanzas y negocios.
6. **Natural / Orgánico**: tonos tierra y verdes, ideal para salud, nutrición y mascotas.
7. **Dark Elegante**: fondo oscuro, acentos dorados.
8. **Playful / Infantil**: colores vivos, formas redondeadas, ideal para educación infantil.
9. **Fitness Energía**: alto contraste, diagonales, ideal para fitness.
10. **Notebook / Cuaderno**: papel rayado, look manuscrito, ideal para workbooks y planners.
11. *(Opcional)* **Brasil Vibrante**: paleta cálida pensada para el mercado BR.
12. *(Opcional)* **Tech / Notion-like**: estilo app de productividad.

Requisitos visuales:
- portada profesional con título, subtítulo, promesa y mockup simple;
- índice automático;
- callouts tipo "Dica", "Atenção", "Exercício";
- numeración de páginas;
- tipografías embebidas (Google Fonts con licencia libre);
- cada plantilla con miniatura de preview generada automáticamente.

---

## 6. Nichos y motor de "problema específico"

Nichos sugeridos iniciales (editables desde la base de datos, no hardcodeados):
- salud,
- nutrición,
- fitness,
- maternidad y crianza,
- relaciones,
- finanzas personales,
- negocios y emprendimiento,
- mindset y productividad,
- educación,
- mascotas,
- belleza,
- espiritualidad,
- hogar y organización.

El **motor de problemas** convierte un nicho amplio en un problema puntual:
- ❌ "Finanzas personales"
- ✅ "Salir del cheque especial (cheque especial / sobregiro) en 60 días ganando un sueldo mínimo"

Para cada problema propuesto, la IA devuelve:
- público exacto,
- dolor principal,
- resultado prometido,
- plazo,
- por qué alguien pagaría por esto,
- nivel de urgencia (1-5).

---

## 7. Paquete comercial: principal + order bumps + bonus

Reglas de generación del paquete:

- **Producto principal**: resuelve el problema completo, de forma accionable. Lleva pasos, ejemplos y ejercicios.
- **Order bumps (mínimo 3)**:
  - cada uno resuelve un sub-problema o acelera el resultado del principal;
  - usan **formatos distintos** entre sí y respecto al principal (por ejemplo: planilla, checklist, plantillas editables);
  - se compran en 1 clic, por lo que la promesa debe ser obvia en una frase.
- **Bonus (mínimo 2)**:
  - quitan objeciones ("no tengo tiempo", "no sé por dónde empezar", "¿y si no funciona para mí?");
  - formato liviano: mapa mental, swipe file, mini guía, planner.
- **Coherencia**: el conjunto se lee como un ecosistema. Las piezas se citan entre sí cuando aplica.

Además, la app genera una **ficha comercial** (pantalla y archivo `.md`/`.docx`) con:
- nombre del producto y 3 alternativas de nombre,
- promesa principal (headline) y subheadline,
- precio sugerido:
  - principal: rango low ticket en BRL o en moneda LATAM según mercado,
  - cada order bump,
  - valor "percibido" de los bonus,
- descripción corta para Hotmart / Kiwify,
- bullets de beneficios,
- texto de cada order bump para el checkout,
- 3 hooks para anuncios.

---

## 8. Idiomas y mercados

- i18n desde el día 1:
  - interfaz de la app en **español**, con opción de portugués;
  - contenido generado en **pt-BR** o **es-LATAM**.
- El contenido **no se traduce**: se **genera nativo** en cada idioma, con prompts propios por mercado. Esto incluye:
  - ejemplos locales,
  - moneda (BRL vs. moneda neutra o configurable para LATAM),
  - modismos neutros,
  - referencias culturales.
- Opción **"Duplicar paquete al otro idioma"**: toma un producto existente y genera su versión adaptada (no traducción literal) al otro mercado, vinculada al original.
- Todos los prompts de IA viven en archivos versionados (`prompts/<mercado>/<pieza>.md`), no dentro del código.

---

## 9. Historial y modelado ("remodelar")

Cada generación queda registrada con todo lo necesario para reproducirla o modificarla.

Modelo de datos mínimo (ajústalo si ves algo mejor y justifícalo):

- `niches`: id, nombre, idioma, activo.
- `products`: id, user_id, niche, problem (JSON), market, main_format, template_id, status, parent_product_id (para versiones o duplicados), created_at.
- `product_items`: id, product_id, role (`main` | `order_bump` | `bonus`), format, title, outline (JSON), content (JSON estructurado), order.
- `files`: id, product_item_id, file_type, storage_path (Supabase), onedrive_item_id, onedrive_url, size, created_at.
- `jobs`: id, product_id, status, progress, error, logs.
- `templates`: id, nombre, config (JSON), preview_url, activo.

En la pantalla de **Historial** se puede:
- buscar y filtrar por nicho, mercado, formato y fecha;
- ver el detalle de un paquete y descargar sus archivos;
- **Remodelar**: crear una nueva versión a partir de un producto existente, cambiando cualquier cosa:
  - plantilla,
  - formato,
  - idioma,
  - una pieza específica,
  - el tono,
  - el público.
  Solo se regeneran las piezas afectadas, reutilizando el contenido estructurado guardado. La nueva versión apunta al original (`parent_product_id`).
- **Regenerar una sola pieza** (por ejemplo, solo el bonus 2) sin rehacer el paquete;
- ver el árbol de versiones.

Como el contenido se guarda estructurado (JSON), cambiar de plantilla o de formato **no requiere volver a llamar a la IA**.

---

## 10. Integración con OneDrive

- Autenticación OAuth 2.0 con Microsoft (MSAL) y permisos mínimos (`Files.ReadWrite` o `Files.ReadWrite.AppFolder` si alcanza; prefiere AppFolder).
- Tokens **cifrados** en base de datos, con refresh automático.
- Estructura de carpetas en OneDrive:
  ```
  /ProductForge/<mercado>/<nicho>/<YYYY-MM-DD>_<slug-producto>/
      principal/
      order-bumps/
      bonus/
      ficha-comercial.md
  ```
- Subida con *upload session* de Graph para archivos grandes.
- Si OneDrive falla, el archivo **igual queda en Supabase Storage** y la subida se reintenta. El usuario nunca pierde un producto por un fallo de OneDrive.
- Deja la capa de almacenamiento como **interfaz** (`StorageProvider`) para poder agregar Google Drive o Dropbox después sin reescribir nada.

---

## 11. Seguridad

- Auth con Supabase. Todas las tablas con **RLS**: cada usuario solo ve sus productos.
- La clave de Claude y los secretos de Microsoft viven **solo en el backend**. El frontend nunca llama a la IA directamente.
- El backend valida el JWT de Supabase en cada request.
- Validación estricta de inputs con Pydantic y Zod. Límite de longitud en campos libres.
- **Rate limiting** por usuario en endpoints de generación, y límite de costo diario configurable.
- Protección contra prompt injection: el input del usuario va como dato delimitado, nunca como instrucción. La salida de la IA se valida contra schema antes de usarse.
- Sanitizar todo lo que entra a las plantillas HTML (Jinja2 con autoescape).
- URLs de descarga firmadas y con expiración.
- CORS restringido a los dominios propios.
- Logs sin datos sensibles ni tokens.
- Dependencias fijadas y un `pip-audit` / `npm audit` en CI.

---

## 12. Fases de desarrollo

**Fase 1 — Base**
- Monorepo (`/frontend`, `/backend`, `/templates`, `/prompts`),
- Supabase (tablas + RLS + auth),
- `CLAUDE.md`, `.env.example`, CI básico con lint y tests.

**Fase 2 — Motor de contenido**
- Prompts por mercado,
- motor de problemas,
- generación del outline del paquete,
- generación de contenido estructurado con validación de schema.

**Fase 3 — Generadores**
- PDF/ebook con 3 plantillas primero,
- luego Sheets, mapas mentales y conceptuales, DOCX y checklist,
- después las 10 plantillas completas con previews.

**Fase 4 — Wizard UI**
- Flujo completo de la sección 3, con progreso de jobs y descargas en ZIP.

**Fase 5 — Historial y remodelado**
- Listado, filtros, versiones, regenerar pieza, duplicar a otro idioma.

**Fase 6 — OneDrive**
- OAuth, subida, carpetas, reintentos, interfaz `StorageProvider`.

**Fase 7 — Endurecimiento**
- Rate limits,
- límites de costo,
- tests end-to-end del flujo completo,
- deploy en Netlify + Railway,
- documentación final.

---

## 13. Criterios de aceptación

- [ ] Elijo nicho, problema, idioma, formato y plantilla, y obtengo un paquete con **1 principal + 3 order bumps + 2 bonus**, todos descargables y abribles sin errores.
- [ ] Las piezas usan al menos 3 formatos distintos entre sí.
- [ ] Hay 10 plantillas con preview, y cambiar de plantilla en el historial regenera los archivos **sin llamar a la IA**.
- [ ] El mismo producto puede generarse en pt-BR y en es-LATAM, con contenido nativo, no traducido.
- [ ] El historial permite remodelar, regenerar una pieza y ver versiones.
- [ ] Los archivos llegan a OneDrive en la estructura definida, con respaldo en Supabase si OneDrive falla.
- [ ] Los `.xlsx` tienen fórmulas funcionales; los mapas mentales se pueden abrir y editar en una herramienta externa; los `.docx` y `.pptx` son editables.
- [ ] Ningún secreto en el frontend ni en el repo; RLS verificado con un test de acceso cruzado entre dos usuarios.
- [ ] La ficha comercial se genera con precios sugeridos en la moneda del mercado.

---

## 14. Primera respuesta que espero de ti

No escribas código todavía. Respóndeme con:
1. Plan por fases con estimación de complejidad.
2. Estructura de carpetas propuesta.
3. Modelo de datos final (SQL de Supabase).
4. Interfaces clave (`ContentGenerator`, `FileGenerator`, `StorageProvider`, `Template`).
5. Lista de dudas o decisiones que necesitas que yo tome.
