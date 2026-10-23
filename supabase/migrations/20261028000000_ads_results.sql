-- Creativos, fase 6: resultados de Ads Manager, iteración de creativos y duplicado de lotes.
-- CTR, CPC, CPA y ROAS NO se guardan: se calculan de los totales (así nunca se contradicen).

create table ad_results (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  creative_id uuid not null references ad_creatives(id) on delete cascade,
  day         date not null,
  spend       numeric(12, 2) not null default 0 check (spend >= 0),
  impressions int not null default 0 check (impressions >= 0),
  clicks      int not null default 0 check (clicks >= 0),
  purchases   int not null default 0 check (purchases >= 0),
  revenue     numeric(12, 2) not null default 0 check (revenue >= 0),  -- valor de conversión de compras
  source      text not null default 'manual' check (source in ('manual', 'csv')),
  created_at  timestamptz not null default now(),
  unique (creative_id, day)
);
create index ad_results_user_idx on ad_results (user_id, creative_id);

-- Iteraciones: un creativo nuevo apunta al que mejoró (o del que salió la variante).
alter table ad_creatives
  add column parent_creative_id uuid references ad_creatives(id) on delete set null;

alter table jobs drop constraint jobs_kind_check;
alter table jobs add constraint jobs_kind_check check (
  kind in ('generate', 'regenerate_item', 'remodel', 'duplicate_market', 'upload',
           'ad_plan', 'ad_render', 'ad_drive', 'ad_iterate')
);

alter table ad_results enable row level security;
create policy "own rows" on ad_results for select to authenticated using (user_id = (select auth.uid()));
