-- Creativos, fase 4: imágenes base (stock o IA), caché por escena y consumo diario por proveedor.
-- Las dos tablas nuevas solo las toca el backend (sin policies, como storage_connections).

create table ad_image_cache (
  scene_hash   text primary key,   -- hash de usuario + escena + formato (ver ImageRequest.scene_hash)
  provider     text not null,
  storage_path text not null,      -- <user>/ads/_images/<hash>.jpg
  credit       jsonb,              -- id, autor, URL de la página y licencia
  created_at   timestamptz not null default now()
);

create table ad_provider_usage (
  provider  text not null,
  day       date not null,
  requests  int not null default 0,
  cost_usd  numeric(10, 5) not null default 0,
  exhausted boolean not null default false,   -- el proveedor respondió «sin cuota» hoy
  primary key (provider, day)
);

-- Qué imagen usó cada creativo (para atribución y para saber cuánto costó).
alter table ad_creatives
  add column image_provider text,
  add column image_credit   jsonb,
  add column base_image_path text,
  add column image_cost_usd numeric(10, 5) not null default 0;

alter table ad_image_cache   enable row level security;
alter table ad_provider_usage enable row level security;

-- Suma atómica del consumo diario (evita carreras entre dos jobs).
create or replace function ad_usage_add(p_provider text, p_day date, p_requests int, p_cost numeric)
returns void
language sql
security definer
set search_path = public
as $$
  insert into ad_provider_usage (provider, day, requests, cost_usd)
  values (p_provider, p_day, p_requests, p_cost)
  on conflict (provider, day) do update
    set requests = ad_provider_usage.requests + excluded.requests,
        cost_usd = ad_provider_usage.cost_usd + excluded.cost_usd;
$$;
revoke execute on function ad_usage_add(text, date, int, numeric) from public, anon, authenticated;
