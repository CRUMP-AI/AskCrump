-- Make the atomic manuscript lease claim safely replayable after an uncertain
-- PostgREST response. The original one-argument function remains available
-- during deployment overlap; the application calls this two-argument form.

begin;

create or replace function public.claim_manuscript_run(
  p_lease_seconds integer,
  p_claim_token uuid
)
returns setof public.manuscript_runs
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  claimed public.manuscript_runs%rowtype;
begin
  if p_claim_token is null then
    raise exception 'claim token is required' using errcode = '22023';
  end if;

  -- If the first response was lost after commit, return the exact same lease
  -- instead of claiming another run or making the caller wait for expiry.
  select *
  into claimed
  from public.manuscript_runs
  where status = 'running'
    and lease_token = p_claim_token
    and lease_expires_at > now()
  limit 1;

  if found then
    return next claimed;
    return;
  end if;

  select *
  into claimed
  from public.manuscript_runs
  where not_before <= now()
    and (
      status = 'queued'
      or (status = 'running' and lease_expires_at < now())
    )
  order by created_at asc
  for update skip locked
  limit 1;

  if not found then
    return;
  end if;

  update public.manuscript_runs
  set status = 'running',
      lease_token = p_claim_token,
      lease_expires_at = now() + make_interval(secs => greatest(60, least(900, p_lease_seconds))),
      attempt_count = attempt_count + 1,
      started_at = coalesce(started_at, now()),
      updated_at = now()
  where id = claimed.id
  returning * into claimed;

  return next claimed;
end;
$$;

revoke all on function public.claim_manuscript_run(integer, uuid) from public, anon, authenticated;
grant execute on function public.claim_manuscript_run(integer, uuid) to service_role;

commit;
