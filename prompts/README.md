# Prompts

Un directorio por mercado. El contenido se genera **nativo** en cada idioma: estos
archivos no son traducciones entre sí; cada uno está escrito para su público.

- `system.md`: rol y principios, común a todas las llamadas del mercado (se cachea).
- `problems.md`, `outline.md`, `item.md`, `commercial.md`: una tarea cada uno.
- `formats/<formato>.md`: guía específica que se agrega a `item.md` según el formato.

Variables `$nombre` (sintaxis `string.Template`): solo valores que pone el sistema
(cantidades, moneda, páginas). **Los datos del usuario nunca se interpolan aquí**: el
código los agrega al final del mensaje dentro de una etiqueta de datos.

Al cambiar cualquier prompt, sube `VERSION`. Cada producto guarda la versión con la
que se generó (`products.prompt_version`).

Un `$` literal en un prompt que pasa por `render` (todos menos `system.md` y
`formats/`) se escribe `$$`, por ejemplo `R$$ 19`.
