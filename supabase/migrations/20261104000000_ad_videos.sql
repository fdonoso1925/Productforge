-- Videos de motion graphics para Meta Ads/Reels (texto e íconos animados con música, 100 % con
-- código). Un video por ángulo y avatar dentro de un lote de anuncios; se compone con un job
-- `ad_video` y, como los creativos, se puede subir a Meta siempre en pausa.

create table ad_videos (
  id             uuid primary key default gen_random_uuid(),
  batch_id       uuid not null references ad_batches(id) on delete cascade,
  user_id        uuid not null references auth.users(id) on delete cascade,
  angle          text not null,
  avatar         text not null,
  ratio          text not null default '9x16' check (ratio in ('9x16', '4x5')),
  script         jsonb,           -- VideoScript: los textos de las 5 escenas (nulo hasta que la IA lo escribe)
  ad_copy        jsonb,           -- texto del anuncio en Ads Manager (primary, headline, description, cta)
  policy_status  text check (policy_status in ('green', 'yellow', 'red')),
  policy_notes   jsonb,
  status         text not null default 'planned'
                 check (status in ('planned', 'rendering', 'ready', 'error')),
  error          text,
  filename       text not null,   -- <producto>_<mercado>_<angulo>_video_<ratio>_v<n>.mp4
  storage_path   text,
  thumb_path     text,            -- PNG del gancho completo: miniatura del anuncio de video
  duration       numeric(6, 2),
  meta           jsonb not null default '{}',  -- ids en Meta (video, creativo, anuncio) al subirlo
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (batch_id, filename)
);
create index ad_videos_batch_idx on ad_videos (batch_id, created_at);

alter table jobs drop constraint jobs_kind_check;
alter table jobs add constraint jobs_kind_check check (
  kind in ('generate', 'regenerate_item', 'remodel', 'duplicate_market', 'upload',
           'ad_plan', 'ad_render', 'ad_drive', 'ad_iterate', 'ad_meta_publish', 'ad_meta_sync',
           'page_generate', 'ad_video')
);

-- Como el resto de tablas de usuario: solo lectura de lo propio; las escrituras van por el backend.
alter table ad_videos enable row level security;
create policy "own rows" on ad_videos for select to authenticated using (user_id = (select auth.uid()));
