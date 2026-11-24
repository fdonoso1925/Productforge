-- Imágenes de la página de ventas: rutas en Storage de las fotos de stock del tema y de los
-- mockups del producto ({hero, problem, bundle, book}). Vacío = página solo con infografías.
alter table sales_pages add column assets jsonb not null default '{}';
