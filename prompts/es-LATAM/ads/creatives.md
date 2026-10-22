Crea $count variaciones de creativo (imagen estática + copy del anuncio) para el ángulo `angle` y el avatar `avatar`, del producto de `brief`. Todo el copy va en español latinoamericano.

Cada variación tiene:
- template_id: una de `allowed_templates` (varía de plantilla entre variaciones cuando puedas).
- variant_note: en una frase, qué prueba esta variación frente a las demás.
- image (texto que irá dentro de la imagen):
  - headline: máximo $headline_words palabras. Es el hook: se lee en 2 segundos, sin signos de más.
  - subheadline: máximo $sub_words palabras (puede ir vacío).
  - kicker: máximo 4 palabras (etiqueta sobre el titular; puede ir vacío).
  - bullets: entre 3 y 5 ítems de máximo 7 palabras, solo si la plantilla usa lista (ver abajo); si no, lista vacía.
  - cta_text: máximo 4 palabras (por ejemplo «Quiero empezar hoy»).
  - price_text: solo si `brief.price_text` existe, tal cual; si no, vacío.
  - note: solo para la plantilla `note`, 1 a 3 frases cortas con voz cercana; si no, vacío.
  - mark: `check` (beneficios) o `cross` (errores o cosas que evitar) para la plantilla `checklist`.
- ad (texto del anuncio en Ads Manager):
  - primary_short: máximo 125 caracteres.
  - primary_long: entre 300 y 600 caracteres, con una mini historia o situación, los beneficios y una llamada a la acción.
  - headline: máximo 40 caracteres.
  - description: máximo 30 caracteres.
  - cta: uno de LEARN_MORE, SHOP_NOW, GET_OFFER, DOWNLOAD, SIGN_UP.
- scene: descripción breve de la imagen base ideal SIN texto y, en nichos sensibles, sin rostros reconocibles.
- stock_keywords: 2 o 3 palabras clave en inglés para buscar una foto de stock de esa escena.
- proof_id: el `id` de la prueba de `proofs` que uses (testimonio o dato real) o null. Si `angle.needs` es `proof`, usa solo pruebas de `proofs` y cítalas tal cual.

Uso de los campos de `image` según la plantilla (los que no se nombran se dejan vacíos):
- `headline_bold`, `question`, `photo_headline`: headline (en `question`, una pregunta real), subheadline, kicker y cta_text. `photo_headline` exige `scene` y 2 o 3 `stock_keywords`.
- `product_mockup`: headline, subheadline, 3 a 5 bullets, price_text (si hay precio) y cta_text.
- `checklist`: headline, 3 a 5 bullets y mark.
- `note`: note (obligatorio) y, si quieres, subheadline como firma.
- `text_post`: headline como texto de un post en primera persona, subheadline y cta_text.
- `notification`: kicker (título de la notificación, genérico, sin marcas), headline (el mensaje) y subheadline (una segunda notificación).
- `before_after` y `comparison`: headline y exactamente 2 o 4 bullets; la primera mitad es lo de antes o lo de siempre y la segunda mitad es lo de después o con el método. Sin cifras ni resultados que no estén en el brief.
- `offer_stack`: headline, 3 a 5 bullets con lo que incluye (solo cosas del brief), price_text tal cual y cta_text. Solo si hay precio.
- `testimonial`: proof_id obligatorio; note = cita TEXTUAL (o un fragmento textual) de esa prueba; subheadline = el autor de la prueba tal cual (o vacío); headline = una frase corta que introduce la cita.

Reglas:
- Respeta el formato del ángulo (`angle.hook`) y adáptalo al avatar y a su lenguaje (`avatar.language`).
- Cada variación debe tener un hook distinto, no la misma frase reescrita.
- Cumple las políticas del sistema: nada sobre atributos personales del espectador, nada inventado (cifras, testimonios, marcas), nada de urgencia salvo que `real_urgency` exista.
- Texto breve y legible en el celular: prefiere pocas palabras de alto impacto.
