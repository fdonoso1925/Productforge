-- Hotmart: ventas leídas de la API (solo lectura) para el dashboard. Sin datos del comprador.

create table hotmart_sales (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  transaction     text not null,            -- código de transacción de Hotmart (HP...)
  product_id      bigint,
  product_name    text,
  status          text not null,            -- APPROVED, COMPLETE, REFUNDED, CHARGEBACK...
  order_date      timestamptz,
  approved_date   timestamptz,
  price           numeric(14, 2) not null default 0,   -- bruto, en `currency`
  currency        text not null default 'BRL',
  fee             numeric(14, 2) not null default 0,   -- tarifa de Hotmart
  commission_as   text,                     -- PRODUCER | COPRODUCER | AFFILIATE
  payment_type    text,
  is_subscription boolean not null default false,
  src             text,                     -- parámetros de seguimiento del enlace (utm/sck)
  sck             text,
  updated_at      timestamptz not null default now(),
  unique (user_id, transaction)
);
create index hotmart_sales_user_day_idx on hotmart_sales (user_id, order_date desc);

-- Qué producto de Hotmart es cuál de la app (para cruzar con el gasto en anuncios).
create table hotmart_product_links (
  user_id            uuid not null references auth.users(id) on delete cascade,
  hotmart_product_id bigint not null,
  product_id         uuid not null references products(id) on delete cascade,
  primary key (user_id, hotmart_product_id)
);

create table hotmart_sync (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  synced_at  timestamptz,
  last_error text,
  count      int not null default 0
);

alter table hotmart_sales         enable row level security;
alter table hotmart_product_links enable row level security;
alter table hotmart_sync          enable row level security;
create policy "own rows" on hotmart_sales         for select to authenticated using (user_id = (select auth.uid()));
create policy "own rows" on hotmart_product_links for select to authenticated using (user_id = (select auth.uid()));
create policy "own rows" on hotmart_sync          for select to authenticated using (user_id = (select auth.uid()));
