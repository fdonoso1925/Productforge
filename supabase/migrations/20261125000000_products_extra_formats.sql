-- Formatos que el usuario pidió incluir sí o sí en el paquete (además del principal), como
-- order bump o bonus. Vacío = la IA elige los formatos, como hasta ahora.
alter table products add column extra_formats format_t[] not null default '{}';
