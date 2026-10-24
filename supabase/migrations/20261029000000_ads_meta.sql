-- Creativos, fase 8: subida a Meta (Marketing API) y lectura automática de métricas.
-- Todo lo que la app crea en Meta queda en PAUSA: activarlo es decisión del usuario en Ads Manager.

-- Estado de Meta del lote: {status, campaign_id, adset_id, link_url, objective, daily_budget, ...}
alter table ad_batches add column meta jsonb not null default '{}';
-- Ids de Meta de cada creativo: {image_hash, creative_id, ad_id}
alter table ad_creatives add column meta jsonb not null default '{}';

alter table ad_results drop constraint ad_results_source_check;
alter table ad_results add constraint ad_results_source_check check (source in ('manual', 'csv', 'meta'));

alter table jobs drop constraint jobs_kind_check;
alter table jobs add constraint jobs_kind_check check (
  kind in ('generate', 'regenerate_item', 'remodel', 'duplicate_market', 'upload',
           'ad_plan', 'ad_render', 'ad_drive', 'ad_iterate', 'ad_meta_publish', 'ad_meta_sync')
);
