-- Creativos, fase 5: copia de un lote a Google Drive.
-- El estado vive en el lote (`drive`): {status, total, uploaded, failed, folder}.

alter table ad_batches   add column drive jsonb not null default '{}';
alter table ad_creatives add column remote_id text, add column remote_url text;

alter table jobs drop constraint jobs_kind_check;
alter table jobs add constraint jobs_kind_check check (
  kind in ('generate', 'regenerate_item', 'remodel', 'duplicate_market', 'upload',
           'ad_plan', 'ad_render', 'ad_drive')
);
