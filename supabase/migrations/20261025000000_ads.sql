-- Módulo Creativos para Meta Ads (fases 2 y 3): lotes de anuncios, creativos y pruebas reales.
-- Ángulos, políticas y plantillas viven en archivos versionados (prompts/<mercado>/ads/,
-- ad_templates/); aquí va solo lo que es dato del usuario. Escrituras solo por el backend.

create table ad_batches (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  product_id      uuid references products(id) on delete set null,   -- nulo = brief manual
  parent_batch_id uuid references ad_batches(id) on delete set null,
  niche           text not null,
  market          market_t not null,
  template_id     text not null,   -- plantilla visual del producto (paleta y fuentes) para componer
  brief           jsonb not null,  -- copia del momento: producto, problema, público, promesa, precio...
  avatars         jsonb not null default '[]',
  picks           jsonb not null default '[]',   -- [{angle_id, avatar, count}]
  ratios          jsonb not null default '["4x5"]',
  status          text not null default 'planning'
                  check (status in ('planning', 'review', 'rendering', 'ready', 'error')),
  prompt_version  text not null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index ad_batches_user_idx on ad_batches (user_id, created_at desc);
create trigger ad_batches_updated_at before update on ad_batches
  for each row execute function set_updated_at();

create table ad_creatives (
  id             uuid primary key default gen_random_uuid(),
  batch_id       uuid not null references ad_batches(id) on delete cascade,
  user_id        uuid not null references auth.users(id) on delete cascade,
  group_id       uuid not null,   -- un mismo borrador en sus distintos formatos comparte grupo
  angle          text not null,
  avatar         text not null,
  template_id    text not null,
  ratio          text not null check (ratio in ('4x5', '9x16', '1x1')),
  copy           jsonb not null,  -- CreativeDraft: textos de la imagen y del anuncio
  policy_status  text check (policy_status in ('green', 'yellow', 'red')),
  policy_notes   jsonb,
  pre_score      int check (pre_score between 1 and 10),
  score_notes    jsonb,
  status         text not null default 'planned'
                 check (status in ('planned', 'rendered', 'error', 'discarded')),
  version        int not null default 1,
  filename       text not null,   -- <producto>_<mercado>_<angulo>_<plantilla>_<ratio>_v<n>.png
  storage_path   text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (batch_id, filename)
);
create index ad_creatives_batch_idx on ad_creatives (batch_id, group_id);
create trigger ad_creatives_updated_at before update on ad_creatives
  for each row execute function set_updated_at();

-- Testimonios y datos REALES cargados por el usuario (la IA nunca los inventa).
create table ad_proofs (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  product_id uuid references products(id) on delete cascade,   -- nulo = vale para todos
  kind       text not null check (kind in ('testimonial', 'stat', 'authority')),
  text       text not null check (char_length(text) <= 500),
  author     text check (char_length(author) <= 80),
  created_at timestamptz not null default now()
);
create index ad_proofs_user_idx on ad_proofs (user_id, product_id);

-- Los jobs de anuncios cuelgan de un lote, no de un producto.
alter table jobs alter column product_id drop not null;
alter table jobs add column batch_id uuid references ad_batches(id) on delete cascade;
alter table jobs drop constraint jobs_kind_check;
alter table jobs add constraint jobs_kind_check check (
  kind in ('generate', 'regenerate_item', 'remodel', 'duplicate_market', 'upload',
           'ad_plan', 'ad_render')
);
alter table jobs add constraint jobs_target_check check (product_id is not null or batch_id is not null);
create index jobs_batch_idx on jobs (batch_id) where batch_id is not null;

alter table ad_batches   enable row level security;
alter table ad_creatives enable row level security;
alter table ad_proofs    enable row level security;

create policy "own rows" on ad_batches   for select to authenticated using (user_id = (select auth.uid()));
create policy "own rows" on ad_creatives for select to authenticated using (user_id = (select auth.uid()));
create policy "own rows" on ad_proofs    for select to authenticated using (user_id = (select auth.uid()));
