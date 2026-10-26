-- Páginas de ventas: generadas desde un paquete (o un brief manual), opcionalmente modeladas sobre
-- el análisis de otra página. De la página ajena NO se guarda el texto: solo el análisis y una
-- «huella» (hashes de grupos de palabras) para detectar parecidos con lo generado.

create table sales_pages (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references auth.users(id) on delete cascade,
  product_id            uuid references products(id) on delete set null,   -- nulo = brief manual
  market                market_t not null,
  template_id           text not null,          -- plantilla visual (paleta) de la página
  title                 text not null,
  status                text not null default 'planning'
                        check (status in ('planning', 'ready', 'error')),
  brief                 jsonb not null,         -- hechos del producto, precio, garantía y urgencia reales
  reference             jsonb,                  -- análisis de la página modelo (sin su texto)
  reference_fingerprint jsonb,                  -- hashes de 5 palabras de la página modelo
  content               jsonb,                  -- PageContent (textos de cada sección)
  proofs                jsonb not null default '[]',   -- pruebas reales elegidas (copia del momento)
  checkout_url          text,
  similarity            jsonb,                  -- {level: ok|warn|block, ratio, fields, brands}
  prompt_version        text not null,
  error                 text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create index sales_pages_user_idx on sales_pages (user_id, created_at desc);
create trigger sales_pages_updated before update on sales_pages
  for each row execute function set_updated_at();

alter table jobs add column page_id uuid references sales_pages(id) on delete cascade;
alter table jobs drop constraint jobs_target_check;
alter table jobs add constraint jobs_target_check check (
  product_id is not null or batch_id is not null or page_id is not null
);
alter table jobs drop constraint jobs_kind_check;
alter table jobs add constraint jobs_kind_check check (
  kind in ('generate', 'regenerate_item', 'remodel', 'duplicate_market', 'upload',
           'ad_plan', 'ad_render', 'ad_drive', 'ad_iterate', 'ad_meta_publish', 'ad_meta_sync',
           'page_generate')
);

alter table sales_pages enable row level security;
create policy "own rows" on sales_pages for select to authenticated using (user_id = (select auth.uid()));
