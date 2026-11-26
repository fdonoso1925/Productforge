Crea $count variaciones de creativo (imagen estática + copy del anuncio) para el ángulo `angle` y el avatar `avatar`, del producto de `brief`. Todo el copy va en español latinoamericano.

Cada variación tiene:
- template_id: una de `allowed_templates` (varía de plantilla entre variaciones cuando puedas).
- variant_note: en una frase, qué prueba esta variación frente a las demás.
- image (texto que irá dentro de la imagen):
  - headline: máximo $headline_words palabras. Es el hook: se lee en 2 segundos, sin signos de más. Marca entre asteriscos las 1 a 3 palabras que cargan la emoción (máximo 3 tramos de hasta 3 palabras), por ejemplo «Cocina *natural* para tu perro»: la plantilla las pone sobre un bloque de color. Solo el headline lleva asteriscos; ningún otro campo.
  - subheadline: máximo $sub_words palabras (puede ir vacío).
  - kicker: máximo 4 palabras (etiqueta sobre el titular; puede ir vacío).
  - bullets: entre 3 y 5 ítems de máximo 7 palabras, solo si la plantilla usa lista (ver abajo); si no, lista vacía.
  - cta_text: máximo 4 palabras (por ejemplo «Quiero empezar hoy»).
  - price_text: solo si `brief.price_text` existe, tal cual; si no, vacío.
  - base_price_text: déjalo vacío (el sistema pone el precio normal tachado). Si `brief.base_price_text` existe, en el texto del anuncio puedes contrastarlo con el precio («de X por Y») usando esas dos cifras tal cual; nunca otra cifra ni un descuento calculado por ti.
  - note: solo para la plantilla `note`, 1 a 3 frases cortas con voz cercana; si no, vacío.
  - mark: `check` (beneficios) o `cross` (errores o cosas que evitar) para la plantilla `checklist`.
- ad (texto del anuncio en Ads Manager):
  - primary_short: máximo 125 caracteres.
  - primary_long: entre 300 y 600 caracteres, con una mini historia o situación, los beneficios y una llamada a la acción.
  - headline: máximo 40 caracteres.
  - description: máximo 30 caracteres.
  - cta: uno de LEARN_MORE, SHOP_NOW, GET_OFFER, DOWNLOAD, SIGN_UP.
- scene (obligatorio): la FOTO DE FONDO del anuncio, en una frase. Todos los anuncios llevan foto de fondo, nunca un color plano: elige una escena concreta, atractiva y emocional que haga detener el scroll (una persona en una situación reconocible, un lugar, un espacio de trabajo o del hogar, naturaleza…). Sin texto, logos ni marcas visibles. En nichos sensibles (salud, dinero, deudas, maternidad…) sin personas reconocibles: usa lugares, objetos o paisajes. Cada variación usa una escena distinta.
- stock_keywords (obligatorio): 2 o 3 palabras clave EN INGLÉS, sustantivos concretos que den buenos resultados en un banco de fotos (por ejemplo «home office», «sunrise mountain», «coffee desk»). La foto va detrás del texto, así que busca escenas con espacio despejado.
- proof_id: el `id` de la prueba de `proofs` que uses (testimonio o dato real) o null. Si `angle.needs` es `proof`, usa solo pruebas de `proofs` y cítalas tal cual.

Uso de los campos de `image` según la plantilla (los que no se nombran se dejan vacíos):
- `headline_bold`, `question`, `photo_headline`: headline (en `question`, una pregunta real), subheadline, kicker y cta_text.
- `product_mockup`: headline, subheadline, 3 a 5 bullets, price_text (si hay precio) y cta_text.
- `checklist`: headline, 3 a 5 bullets y mark.
- `note`: note (obligatorio) y, si quieres, subheadline como firma.
- `text_post`: headline como texto de un post en primera persona, subheadline y cta_text.
- `notification`: kicker (título de la notificación, genérico, sin marcas), headline (el mensaje) y subheadline (una segunda notificación).
- `before_after` y `comparison`: headline y exactamente 2 o 4 bullets; la primera mitad es lo de antes o lo de siempre y la segunda mitad es lo de después o con el método. Sin cifras ni resultados que no estén en el brief.
- `offer_stack`: headline, 3 a 5 bullets con lo que incluye (solo cosas del brief), price_text tal cual y cta_text. Solo si hay precio.
- `how` («cómo lograr X sin Y»): headline con la promesa y la objeción que elimina, kicker opcional y 3 o 4 bullets que son pasos cortos y en orden (lo que la persona hace de verdad con el producto). Rinde cuando la objeción es la dificultad o el tiempo.
- `myth` (mito vs. verdad): headline que plantea la creencia, kicker opcional y exactamente 2 bullets: el primero es el mito (una creencia común que frena la compra, dicha de forma prudente: «muchos creen…») y el segundo la verdad que lo desmiente con lo que el producto enseña. Sin estudios ni cifras.
- `objection` (objeción respondida): headline que nombra la objeción n.º 1 del avatar y exactamente 2 bullets: el primero es la duda típica, como pregunta corta, y el segundo la respuesta concreta basada en el brief. No es un testimonio: no inventes quién lo dijo.
- `testimonial`: proof_id obligatorio; note = cita TEXTUAL (o un fragmento textual) de esa prueba; subheadline = el autor de la prueba tal cual (o vacío); headline = una frase corta que introduce la cita.

Iteración: si `iterate_from` existe, es un creativo que ya se probó (con sus métricas, si las hay). Mantén el ángulo y el avatar, y propón hooks NUEVOS que prueben otro enfoque (otro dolor concreto, otro formato de gancho, otro plazo real); no reutilices sus frases ni cambies solo unas palabras. Si tuvo buen CTR, conserva lo que funcionó (claridad, especificidad) y varía el resto.

Reglas:
- Respeta el formato del ángulo (`angle.hook`) y adáptalo al avatar y a su lenguaje (`avatar.language`).
- Cada variación debe tener un hook distinto, no la misma frase reescrita.
- Cumple las políticas del sistema: nada sobre atributos personales del espectador, nada inventado (cifras, testimonios, marcas), nada de urgencia salvo que `real_urgency` exista.
- Texto breve y legible en el celular: prefiere pocas palabras de alto impacto.
