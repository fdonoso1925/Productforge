-- Portada de cada producto: estilo de arte generativo y/o imagen propia.
-- Forma: {"art": "auto|topo|waves|circles|bauhaus|facets|none", "image_id": "<uuid>|null"}.
-- Vacío ('{}') = producto anterior a esta función: se queda sin arte, como se veía antes.
-- La imagen vive en Storage como <user_id>/covers/<image_id>.jpg (solo la toca el backend).
alter table products add column cover jsonb not null default '{}'::jsonb;

comment on column products.cover is
  'Portada: {art, image_id}. {} = sin arte (productos anteriores). Ver backend/app/generators/cover.py';
