Escribe el guion de un video corto de motion graphics (texto e íconos animados, sin voz ni personas) para Reels y el feed de Meta, del producto de `brief`, para el ángulo `angle` y el avatar `avatar`. Todo en español latinoamericano.

El video dura unos 17 segundos y tiene 5 escenas fijas. Cada texto aparece grande en pantalla: pocas palabras, de alto impacto, que se lean en el celular sin pausar.

1. Gancho (0–3 s): debe estar completo antes de los 2 segundos.
   - hook_tag: etiqueta corta en 2 a 4 palabras que llame a quien es el público (por ejemplo «Atención, tutor», «Si emprendes en casa»). Sin señalar atributos personales sensibles.
   - hook_lines: el gancho repartido en 2 o 3 líneas de 1 a 4 palabras cada una, siguiendo el formato del ángulo (`angle.hook`) y el lenguaje del avatar (`avatar.language`).
   - hook_highlight: el índice (0, 1 o 2) de la línea que carga la emoción; esa línea va grande sobre un bloque de color.
2. Problema: problem_title (3 a 8 palabras) y exactamente 3 problems, frustraciones reales del avatar en máximo 7 palabras cada una. Usa formulaciones prudentes («puede», «muchas veces»), sin afirmaciones absolutas sobre otros productos ni marcas.
3. Solución: solution_title (2 a 5 palabras, abre la solución), solution_big (1 a 3 palabras clave, la idea central del producto) y solution_caption (6 a 14 palabras sobre lo que logra, sin prometer resultados garantizados).
4. Qué recibes: benefits_title (2 a 5 palabras) y exactamente 3 benefits con title (2 a 4 palabras) y detail (3 a 8 palabras). Solo entregables que existen en `brief` (el producto, su promesa y sus bonuses): no inventes módulos, bonos ni extras.
5. Cierre: cta_button en imperativo y primera persona, 2 a 4 palabras («Quiero la guía», «Quiero empezar hoy»), y cta_sub, una línea de confianza VERDADERA de 2 a 8 palabras («Acceso inmediato al comprar», «Material digital para descargar»). Si `brief.price_text` existe puedes usarlo tal cual; si no, no menciones precios.

Si existe `winning_hook`, es el titular de un anuncio que ya funcionó: inspírate en su enfoque para el gancho, con palabras nuevas.

Reglas:
- Nada inventado: ninguna cifra, plazo, porcentaje, cantidad de personas, testimonio, estudio ni marca que no esté en `brief`. Si un número no aparece en `brief`, no lo uses.
- Nada de urgencia o escasez salvo que `brief.real_urgency` exista.
- Cumple las políticas de Meta: sin promesas de salud, peso, belleza o ingresos; sin señalar atributos personales («¿Tienes deudas?», «¿Sufres de ansiedad?»).
- Sin asteriscos, emojis ni símbolos decorativos: el diseño ya resalta lo importante.
