-- Resumen de la página de ventas que inspiró el paquete (SalesReference, ver
-- backend/app/content/schemas/reference.py). Es un resumen hecho por la IA, no la página:
-- guarda la URL de origen y los puntos clave (público, dolores, promesa, tono, ángulo).
-- Nulo = el paquete no partió de una página de referencia.
alter table products add column reference jsonb;

comment on column products.reference is
  'Resumen estructurado de una página de ventas usada como inspiración (nunca su texto). Nulo = sin referencia.';
