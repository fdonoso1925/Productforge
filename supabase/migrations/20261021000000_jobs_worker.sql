-- Fase 4: el worker toma jobs de a uno con FOR UPDATE SKIP LOCKED.
-- Un job "running" cuyo worker murió (locked_at viejo) se reintenta hasta 3 veces.

create or replace function claim_job(stale_after interval default interval '15 minutes')
returns setof jobs
language sql
security definer
set search_path = public
as $$
  update jobs
     set status = 'running', locked_at = now(), attempts = attempts + 1
   where id = (
     select id from jobs
      where status = 'queued'
         or (status = 'running' and locked_at < now() - stale_after and attempts < 3)
      order by created_at
      for update skip locked
      limit 1
   )
  returning *;
$$;

-- Solo el backend (service role) puede tomar jobs.
revoke execute on function claim_job(interval) from public, anon, authenticated;
