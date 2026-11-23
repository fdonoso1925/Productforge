-- Videos: motor elegido por video. «motion» = el motor propio de motion graphics (como hasta ahora);
-- «lemo» = el renderizador de Lemo-Opuscar con uno de sus estilos (kinetic, swiss, neon, paper).
-- Los videos existentes quedan en «motion».
alter table ad_videos
  add column engine text not null default 'motion' check (engine in ('motion', 'lemo')),
  add column style  text check (style is null or style in ('kinetic', 'swiss', 'neon', 'paper')),
  add constraint ad_videos_lemo_style check (engine <> 'lemo' or style is not null);
