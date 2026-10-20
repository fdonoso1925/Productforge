-- ProductForge — esquema inicial (Fase 1)
-- Modelo de datos de PLAN.md §3. RLS activado en todas las tablas.
-- El frontend solo LEE sus filas; todas las escrituras pasan por el backend (service role).

create extension if not exists pgcrypto;

-- ─────────────────────────── Tipos ───────────────────────────

create type market_t as enum ('pt-BR', 'es-LATAM');
create type item_role_t as enum ('main', 'order_bump', 'bonus');
create type product_status_t as enum ('draft', 'outline_ready', 'generating', 'ready', 'error');
create type job_status_t as enum ('queued', 'running', 'done', 'error', 'cancelled');
create type format_t as enum (
  'pdf_guide', 'epub', 'mind_map', 'concept_map', 'sheet',
  'checklist', 'blueprint', 'editable_template', 'planner', 'swipe_file'
);

create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ──────────────── Acceso: solo emails permitidos (D1/D2) ────────────────
-- Google deja entrar a cualquier cuenta. Este trigger impide que se cree un
-- usuario cuyo email no esté en la lista, así nadie más obtiene sesión.

create table app_allowed_emails (
  email text primary key check (email = lower(email))
);
alter table app_allowed_emails enable row level security;
-- Sin policies: invisible para anon/authenticated.

create or replace function enforce_allowed_email() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if not exists (select 1 from public.app_allowed_emails where email = lower(new.email)) then
    raise exception 'email no autorizado' using errcode = '42501';
  end if;
  return new;
end;
$$;

create trigger enforce_allowed_email
  before insert on auth.users
  for each row execute function enforce_allowed_email();

-- ─────────────────────────── Catálogos ───────────────────────────

create table niches (
  id         uuid primary key default gen_random_uuid(),
  slug       text not null,
  name       text not null,
  market     market_t not null,
  active     boolean not null default true,
  sort_order int not null default 0,
  unique (slug, market)
);

create table templates (
  id          text primary key,
  name        text not null,
  config      jsonb not null default '{}',
  preview_url text,
  active      boolean not null default true,
  sort_order  int not null default 0
);

-- ─────────────────────────── Datos del usuario ───────────────────────────

create table products (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users(id) on delete cascade,
  parent_product_id uuid references products(id) on delete set null,
  root_product_id   uuid references products(id) on delete set null,
  title             text,
  slug              text,
  niche             text not null check (char_length(niche) <= 120),
  problem           jsonb not null,
  market            market_t not null default 'pt-BR',
  main_format       format_t not null,
  template_id       text not null references templates(id),
  tone              text check (char_length(tone) <= 200),
  audience_override text check (char_length(audience_override) <= 300),
  outline           jsonb,
  commercial        jsonb,
  prompt_version    text not null,
  status            product_status_t not null default 'draft',
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index products_user_created_idx on products (user_id, created_at desc);
create index products_root_idx on products (root_product_id);
create trigger products_updated_at before update on products
  for each row execute function set_updated_at();

create table product_items (
  id           uuid primary key default gen_random_uuid(),
  product_id   uuid not null references products(id) on delete cascade,
  user_id      uuid not null references auth.users(id) on delete cascade,
  role         item_role_t not null,
  format       format_t not null,
  title        text not null,
  outline      jsonb not null,
  content      jsonb,
  content_hash text,
  status       text not null default 'pending'
               check (status in ('pending', 'generating', 'ready', 'error')),
  "order"      int not null,
  created_at   timestamptz not null default now(),
  unique (product_id, role, "order")
);
create index product_items_product_idx on product_items (product_id);

create table files (
  id               uuid primary key default gen_random_uuid(),
  product_item_id  uuid references product_items(id) on delete cascade, -- null = ficha comercial / ZIP
  product_id       uuid not null references products(id) on delete cascade,
  user_id          uuid not null references auth.users(id) on delete cascade,
  file_type        text not null,
  storage_path     text not null,
  size             bigint not null,
  onedrive_item_id text,
  onedrive_url     text,
  onedrive_status  text not null default 'pending'
                   check (onedrive_status in ('pending', 'uploaded', 'failed', 'skipped')),
  upload_attempts  int not null default 0,
  created_at       timestamptz not null default now()
);
create index files_product_idx on files (product_id);
create index files_onedrive_pending_idx on files (onedrive_status)
  where onedrive_status in ('pending', 'failed');

create table jobs (
  id         uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  user_id    uuid not null references auth.users(id) on delete cascade,
  kind       text not null
             check (kind in ('generate', 'regenerate_item', 'remodel', 'duplicate_market', 'upload')),
  payload    jsonb not null default '{}',
  status     job_status_t not null default 'queued',
  progress   jsonb not null default '{}',
  error      text,
  logs       jsonb not null default '[]',
  attempts   int not null default 0,
  locked_at  timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index jobs_queued_idx on jobs (status, created_at) where status = 'queued';
create trigger jobs_updated_at before update on jobs
  for each row execute function set_updated_at();

-- Solo para visibilidad de costo por paquete (D6: sin tope).
create table ai_usage (
  id            bigint generated always as identity primary key,
  user_id       uuid not null references auth.users(id) on delete cascade,
  product_id    uuid references products(id) on delete set null,
  model         text not null,
  input_tokens  int not null,
  output_tokens int not null,
  cost_usd      numeric(10, 5) not null,
  created_at    timestamptz not null default now()
);
create index ai_usage_user_created_idx on ai_usage (user_id, created_at);

create table storage_connections (
  user_id           uuid not null references auth.users(id) on delete cascade,
  provider          text not null,
  account_label     text,
  access_token_enc  bytea not null,
  refresh_token_enc bytea not null,
  expires_at        timestamptz not null,
  created_at        timestamptz not null default now(),
  primary key (user_id, provider)
);

-- ─────────────────────────── RLS ───────────────────────────

alter table niches              enable row level security;
alter table templates           enable row level security;
alter table products            enable row level security;
alter table product_items       enable row level security;
alter table files               enable row level security;
alter table jobs                enable row level security;
alter table ai_usage            enable row level security;
alter table storage_connections enable row level security;

create policy "catalog read" on niches    for select to authenticated using (active);
create policy "catalog read" on templates for select to authenticated using (active);

create policy "own rows" on products      for select to authenticated using (user_id = (select auth.uid()));
create policy "own rows" on product_items for select to authenticated using (user_id = (select auth.uid()));
create policy "own rows" on files         for select to authenticated using (user_id = (select auth.uid()));
create policy "own rows" on jobs          for select to authenticated using (user_id = (select auth.uid()));
create policy "own rows" on ai_usage      for select to authenticated using (user_id = (select auth.uid()));
-- storage_connections: sin policy → invisible desde el frontend (contiene tokens cifrados).

-- ─────────────────────────── Storage ───────────────────────────
-- Bucket privado. Ruta: <user_id>/<product_id>/<archivo>. Las descargas usan
-- URLs firmadas que emite el backend, así que no hay policies de lectura.

insert into storage.buckets (id, name, public)
values ('products', 'products', false)
on conflict (id) do nothing;
