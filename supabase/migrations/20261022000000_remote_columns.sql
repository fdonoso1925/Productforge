-- Fase 6 (revisada): el destino de las copias pasa de OneDrive a Google Drive, y las columnas
-- dejan de llevar el nombre de un proveedor concreto. Solo renombra: no cambia datos, tipos
-- ni restricciones (el check y el índice parcial siguen a la columna renombrada).

alter table files rename column onedrive_item_id to remote_id;
alter table files rename column onedrive_url to remote_url;
alter table files rename column onedrive_status to remote_status;

alter index files_onedrive_pending_idx rename to files_remote_pending_idx;

comment on column files.remote_id is 'Id del archivo en el destino externo (Google Drive).';
comment on column files.remote_url is 'Enlace del archivo en el destino externo.';
comment on column files.remote_status is 'pending | uploaded | failed | skipped (el ZIP no se copia).';
