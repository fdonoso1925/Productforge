Arma la estructura (outline) de un paquete comercial completo para el problema indicado. Todavía no escribas el contenido: define títulos, promesas e índices.

El paquete tiene:
- 1 producto principal en formato `$main_format`, que resuelve el problema completo de forma accionable. Entre $main_min_pages y $main_max_pages páginas estimadas (si el formato no es de páginas, estima el equivalente).
- Al menos $min_bumps order bumps. Cada uno resuelve un subproblema o acelera el resultado del principal. Usa formatos distintos entre sí y distintos del principal. La promesa tiene que ser obvia en una frase, porque la compra es en 1 clic. Hasta $small_max_pages páginas estimadas.
- Al menos $min_bonuses bonus. Cada uno elimina una objeción ("no tengo tiempo", "no sé por dónde empezar", "¿y si no me funciona?") y usa un formato liviano: $bonus_formats. Completa `objection_addressed`. Hasta $small_max_pages páginas estimadas.

Formatos disponibles: $formats.

Hojas imprimibles: si el nicho se presta (actividades o tareas para niños, educación, ejercicio o salud, finanzas con calendarios y presupuestos, cocina y recetas, organización, estudio, hábitos), incluye UNA pieza en formato `printable` —como order bump o como bonus— con las hojas imprimibles que de verdad usaría esa persona. Si el nicho no lo pide, no lo fuerces.

Foto de portada (`cover_photo`, opcional por pieza): si el tema se presta a una imagen concreta y reconocible (cocina y recetas, mascotas, bebés y crianza, ejercicio, plantas y jardín, viajes, manualidades, hogar), pide una foto para la tapa del libro de la portada: `scene` en inglés (lugar, objetos o actividad, sin texto, sin logos ni marcas) y 2 o 3 `keywords` en inglés, sustantivos concretos que den buenos resultados en un banco de fotos. Que muestre el tema de esa pieza, no algo genérico. En nichos sensibles (salud, dinero, deudas, maternidad) sin personas reconocibles: usa objetos, lugares o detalles. Si el tema es abstracto (productividad, finanzas, mentalidad) o una imagen no aporta, deja `cover_photo` en null: la portada se ve bien solo con su diseño.

Si en los datos hay `sales_page_reference`, piensa el paquete para ese público: el principal resuelve su dolor principal (`main_pain`) en el plazo de su promesa, los bonus pueden eliminar sus objeciones (`objections`) y el nombre y los títulos deben ser originales, nunca los de la página. Mejora su enfoque (`angle`) con algo más específico.

Para cada pieza: título comercial (no genérico), promesa en una frase con plazo, índice con las secciones en orden, páginas estimadas y, en `related_items`, los títulos de las otras piezas que cita.

`product_name` es el nombre comercial del paquete completo.
