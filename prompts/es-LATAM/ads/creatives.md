Crea $count variaciones de creativo (imagen estática + copy del anuncio) para el ángulo `angle` y el avatar `avatar`, del producto de `brief`. Todo el copy va en español latinoamericano.

Cada variación tiene:
- template_id: una de `allowed_templates` (varía de plantilla entre variaciones cuando puedas).
- variant_note: en una frase, qué prueba esta variación frente a las demás.
- image (texto que irá dentro de la imagen):
  - headline: máximo $headline_words palabras. Es el hook: se lee en 2 segundos, sin signos de más.
  - subheadline: máximo $sub_words palabras (puede ir vacío).
  - kicker: máximo 4 palabras (etiqueta sobre el titular; puede ir vacío).
  - bullets: entre 3 y 5 ítems de máximo 7 palabras, solo si la plantilla es `checklist` o `product_mockup`; si no, lista vacía.
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

Reglas:
- Respeta el formato del ángulo (`angle.hook`) y adáptalo al avatar y a su lenguaje (`avatar.language`).
- Cada variación debe tener un hook distinto, no la misma frase reescrita.
- Cumple las políticas del sistema: nada sobre atributos personales del espectador, nada inventado (cifras, testimonios, marcas), nada de urgencia salvo que `real_urgency` exista.
- Texto breve y legible en el celular: prefiere pocas palabras de alto impacto.
