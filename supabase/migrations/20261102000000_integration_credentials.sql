-- Credenciales de Meta Ads y Hotmart que el usuario ingresa en Ajustes.
-- Van cifradas (Fernet, clave TOKEN_ENCRYPTION_KEY del backend) en un solo blob JSON por proveedor.
-- Sin policies: el navegador nunca las lee, solo el backend (service role), como storage_connections.
create table integration_credentials (
  user_id    uuid not null references auth.users(id) on delete cascade,
  provider   text not null check (provider in ('meta', 'hotmart')),
  data_enc   bytea not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, provider)
);

alter table integration_credentials enable row level security;
-- integration_credentials: sin policy → invisible desde el frontend (contiene claves cifradas).
