Escribe la página de ventas completa del producto de `brief`, pensada para convertir visitas en compradores. Se verá en celular primero.

Datos disponibles en <datos_del_usuario>:
- `brief`: producto, público, problema, dolor, promesa, plazo, por qué pagarían y las piezas del paquete (`deliverables`: la principal, los bonus y los order bumps). `price_text`, `guarantee_text` y `real_urgency` existen solo si el usuario los dio.
- `angles`: los ángulos de venta posibles. Usa todos los que apliquen a lo largo de la página, cada uno donde mejor funciona: dolor y situación en el problema; mecanismo en la solución; transformación en el hero y el cierre; persona/identificación en «es para ti»; objeción en las preguntas frecuentes; error común y mito en la solución o los beneficios; lista de beneficios en los beneficios. Ignora los que piden datos que no hay (oferta sin precio, autoridad sin pruebas, urgencia sin urgencia real).
- `proofs`: pruebas reales con su id. Si hay, elige las que más ayuden en `proof.proof_ids` (no copies su texto: el sistema lo inserta tal cual) y escribe solo una frase de introducción en `proof.intro`. Si no hay, deja `proof.proof_ids` vacío y `proof.intro` vacío.
- `reference_teardown` (opcional): análisis de otra página. Conserva lo que funciona de su estructura, corrige sus debilidades (`weaknesses`), agrega lo que le falta (`missing`) y supera su claridad. Evita todos los `brand_terms`. Que tu texto no se parezca al suyo en palabras: debe sonar a este producto y a este público.
- `feedback` (opcional): problemas de un intento anterior; corrígelos.

Cómo escribirla, sección por sección:
- `hero`: `eyebrow` (para quién es, en pocas palabras), `headline` (promesa concreta; máximo 110 caracteres), `subheadline` (cómo y en cuánto tiempo, sin exagerar), exactamente 3 `bullets` de beneficio y `cta_text` (verbo + resultado, p. ej. «Quiero empezar ahora»). `microcopy`: solo hechos reales (p. ej. acceso inmediato si el producto es digital); si dudas, vacío.
- `problem`: la situación y el dolor con las palabras del público (`pains`: 3 a 6, concretos), y `agitation`: qué pasa si sigue igual, honesto y breve.
- `solution`: presenta el método. `mechanism_name`: un nombre corto y descriptivo (no una marca registrada ni un invento pretencioso). `mechanism`: cómo funciona y por qué es distinto a lo que ya intentó.
- `journey`: de 3 a 5 etapas del camino desde donde está hasta el resultado, cada una con título y qué hará en esa etapa.
- `benefits`: de 4 a 6, cada uno con título de resultado y un texto que explique el porqué.
- `deliverable_blurbs`: una frase de valor por cada pieza de `brief.deliverables`, en el mismo orden y en la misma cantidad. Para los bumps, preséntalos como complemento opcional.
- `for_you` (3 a 6) y `not_for_you` (2 a 4): honestos; no es para quien busque resultados sin aplicar lo aprendido.
- `about`: solo si `brief.about_author` trae datos; resúmelos sin agregar credenciales. Si no hay, vacío.
- `offer`: `title`, `intro` (resume qué se lleva y por qué es buena decisión, sin repetir el precio) y `cta_text`. Deja vacíos `price_text`, `guarantee` y `urgency`.
- `faq`: de 5 a 8 preguntas que eliminan las objeciones reales de este público (tiempo, nivel, formato, acceso, si sirve para su caso), con respuestas directas. No hables de garantía, devolución ni pagos si no hay `guarantee_text`.
- `final_cta`: cierre que retoma la transformación y pide la compra.
- `disclaimer`: aviso breve y honesto (los resultados dependen de aplicar el contenido; no se garantizan ingresos ni resultados concretos).
- `seo_title` (hasta 60 caracteres) y `seo_description` (hasta 160).

Reglas duras:
- Ninguna cifra (plazos, porcentajes, cantidades de personas o ventas) que no esté en `brief` o `proofs`.
- Nada de testimonios inventados, nombres, logos ni «miles de personas».
- Los textos son para leer rápido: frases cortas, sin relleno ni palabras vacías.
