Corrige los creativos de `creatives` para que pasen la revisión de políticas de Meta SIN que haya que tocarlos después. Cada uno trae su `draft` actual, las observaciones de políticas (`policy_notes`, con la regla, el motivo y la severidad) y una reescritura sugerida (`suggested_rewrite`). El objetivo es entregar anuncios que queden en verde: sin observaciones.

Checklist de políticas (`strict` indica un nicho sensible: sé más estricto):

$checklist

Cómo corregir:
- Resuelve TODAS las observaciones de cada creativo, en cualquier parte del texto: la imagen (titular, subtítulo, kicker, bullets, botón, nota), el texto del anuncio (`primary_short`, `primary_long`, `headline`, `description`) y la `scene`.
- Conserva la idea, el ángulo, el avatar y la `template_id` (no la cambies). Conserva `scene`, `stock_keywords`, `proof_id` y `variant_note` salvo que sean la causa de la observación.
- Quita el problema de raíz: no afirmes ni insinúes características personales de quien ve el anuncio (salud, peso, deudas, embarazo, religión, orientación…); habla de la situación o del público en general. Elimina promesas garantizadas, dinero rápido, antes/después, cifras o pruebas que no estén en `proofs`, urgencia que no esté en `real_urgency` y cualquier mención de plataformas o marcas.
- Reescribe con naturalidad: que siga siendo un anuncio atractivo, específico y con un hook claro, no una versión tímida y genérica.
- Respeta los límites de largo: titulares de hasta $headline_words palabras y subtítulos de hasta $sub_words palabras en la imagen; los textos del anuncio con sus límites habituales. Mantén la misma cantidad de bullets.
- No inventes datos, testimonios, cifras ni precios: solo lo que está en `brief` y `proofs`.

Devuelve exactamente un creativo corregido por cada elemento de `creatives`, en el mismo orden.
