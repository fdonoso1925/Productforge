-- Datos iniciales: nichos sugeridos (§6) y catálogo de plantillas (§5).
-- Los nichos se editan desde la base, no desde el código.
-- La config completa de cada plantilla vive en templates/<id>/template.json y se
-- sincroniza en la Fase 3; aquí solo se registra el catálogo.

insert into niches (slug, market, name, sort_order) values
  ('saude',          'pt-BR', 'Saúde', 1),
  ('nutricao',       'pt-BR', 'Nutrição', 2),
  ('fitness',        'pt-BR', 'Fitness', 3),
  ('maternidade',    'pt-BR', 'Maternidade e criação de filhos', 4),
  ('relacionamentos','pt-BR', 'Relacionamentos', 5),
  ('financas',       'pt-BR', 'Finanças pessoais', 6),
  ('negocios',       'pt-BR', 'Negócios e empreendedorismo', 7),
  ('produtividade',  'pt-BR', 'Mindset e produtividade', 8),
  ('educacao',       'pt-BR', 'Educação', 9),
  ('pets',           'pt-BR', 'Pets', 10),
  ('beleza',         'pt-BR', 'Beleza', 11),
  ('espiritualidade','pt-BR', 'Espiritualidade', 12),
  ('casa',           'pt-BR', 'Casa e organização', 13),
  ('salud',          'es-LATAM', 'Salud', 1),
  ('nutricion',      'es-LATAM', 'Nutrición', 2),
  ('fitness',        'es-LATAM', 'Fitness', 3),
  ('maternidad',     'es-LATAM', 'Maternidad y crianza', 4),
  ('relaciones',     'es-LATAM', 'Relaciones', 5),
  ('finanzas',       'es-LATAM', 'Finanzas personales', 6),
  ('negocios',       'es-LATAM', 'Negocios y emprendimiento', 7),
  ('productividad',  'es-LATAM', 'Mindset y productividad', 8),
  ('educacion',      'es-LATAM', 'Educación', 9),
  ('mascotas',       'es-LATAM', 'Mascotas', 10),
  ('belleza',        'es-LATAM', 'Belleza', 11),
  ('espiritualidad', 'es-LATAM', 'Espiritualidad', 12),
  ('hogar',          'es-LATAM', 'Hogar y organización', 13)
on conflict (slug, market) do nothing;

insert into templates (id, name, sort_order) values
  ('minimal-clean',     'Minimal Clean', 1),
  ('editorial-premium', 'Editorial Premium', 2),
  ('bold-moderno',      'Bold Moderno', 3),
  ('soft-pastel',       'Soft Pastel', 4),
  ('corporativo-pro',   'Corporativo Pro', 5),
  ('natural-organico',  'Natural / Orgánico', 6),
  ('dark-elegante',     'Dark Elegante', 7),
  ('playful-infantil',  'Playful / Infantil', 8),
  ('fitness-energia',   'Fitness Energía', 9),
  ('notebook-cuaderno', 'Notebook / Cuaderno', 10)
on conflict (id) do nothing;
