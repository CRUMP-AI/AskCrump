-- Durable private-Storage cleanup for account deletion.
--
-- Supabase Storage objects must be deleted through the Storage API, not by
-- deleting rows from storage.objects.  The account RPC therefore records an
-- independent cleanup obligation before removing the owning user.  A
-- service-role worker claims each obligation with a fenced, expiring lease.

create table if not exists public.account_storage_deletion_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique,
  bucket text not null default 'crump-files',
  owner_prefix text not null,
  status text not null default 'pending'
    check (status in ('pending', 'processing')),
  attempts integer not null default 0
    check (attempts >= 0),
  next_attempt_at timestamptz not null default now(),
  final_sweep_after timestamptz not null default (now() + interval '27 hours'),
  empty_observed_at timestamptz,
  lease_token uuid,
  lease_expires_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint account_storage_deletion_jobs_owner_prefix_check
    check (owner_prefix = user_id::text || '/'),
  constraint account_storage_deletion_jobs_bucket_check
    check (bucket ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$'),
  constraint account_storage_deletion_jobs_lease_state_check
    check (
      (status = 'pending' and lease_token is null and lease_expires_at is null)
      or
      (status = 'processing' and lease_token is not null and lease_expires_at is not null)
    )
);

create index if not exists account_storage_deletion_jobs_pending_idx
  on public.account_storage_deletion_jobs(next_attempt_at, created_at)
  where status = 'pending';

create index if not exists account_storage_deletion_jobs_expired_lease_idx
  on public.account_storage_deletion_jobs(lease_expires_at)
  where status = 'processing';

alter table public.account_storage_deletion_jobs enable row level security;
revoke all on table public.account_storage_deletion_jobs from public, anon, authenticated;
grant select, insert, update, delete on table public.account_storage_deletion_jobs to service_role;

comment on table public.account_storage_deletion_jobs is
  'Service-role-only durable obligations for deleting one former account UUID prefix through the Storage API.';
comment on column public.account_storage_deletion_jobs.owner_prefix is
  'Exact canonical UUID prefix, including the trailing slash; never a partial identifier.';

create or replace function public.claim_account_storage_deletion_job()
returns table (
  job_id uuid,
  user_id uuid,
  bucket text,
  owner_prefix text,
  attempts integer,
  final_sweep_after timestamptz,
  empty_observed_at timestamptz,
  lease_token uuid
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_lease_token uuid := pg_catalog.gen_random_uuid();
begin
  return query
  with candidate as (
    select job.id
    from public.account_storage_deletion_jobs as job
    where (
      job.status = 'pending'
      and job.next_attempt_at <= pg_catalog.clock_timestamp()
    ) or (
      job.status = 'processing'
      and job.lease_expires_at <= pg_catalog.clock_timestamp()
    )
    order by job.next_attempt_at, job.created_at
    for update skip locked
    limit 1
  ), claimed as (
    update public.account_storage_deletion_jobs as job
    set status = 'processing',
        attempts = job.attempts + 1,
        lease_token = v_lease_token,
        lease_expires_at = pg_catalog.clock_timestamp() + interval '8 minutes',
        updated_at = pg_catalog.clock_timestamp()
    where job.id = (select candidate.id from candidate)
    returning job.*
  )
  select
    claimed.id,
    claimed.user_id,
    claimed.bucket,
    claimed.owner_prefix,
    claimed.attempts,
    claimed.final_sweep_after,
    claimed.empty_observed_at,
    claimed.lease_token
  from claimed;
end;
$$;

create or replace function public.release_account_storage_deletion_job(
  p_job_id uuid,
  p_lease_token uuid,
  p_objects_deleted integer default 0,
  p_error text default null
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.account_storage_deletion_jobs%rowtype;
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_backoff_seconds integer;
begin
  select job.*
  into v_job
  from public.account_storage_deletion_jobs as job
  where job.id = p_job_id
    and job.status = 'processing'
    and job.lease_token = p_lease_token
  for update;

  if not found then
    return 'lease_lost';
  end if;

  if p_error is not null then
    v_backoff_seconds := least(
      3600,
      (30 * power(2::numeric, least(greatest(v_job.attempts - 1, 0), 7)))::integer
    );
    update public.account_storage_deletion_jobs as job
    set status = 'pending',
        next_attempt_at = v_now + pg_catalog.make_interval(secs => v_backoff_seconds),
        empty_observed_at = null,
        lease_token = null,
        lease_expires_at = null,
        last_error = left(p_error, 300),
        updated_at = v_now
    where job.id = v_job.id
      and job.lease_token = p_lease_token;
    return 'retry_scheduled';
  end if;

  if v_now < v_job.final_sweep_after then
    update public.account_storage_deletion_jobs as job
    set status = 'pending',
        next_attempt_at = v_job.final_sweep_after,
        empty_observed_at = null,
        lease_token = null,
        lease_expires_at = null,
        last_error = null,
        updated_at = v_now
    where job.id = v_job.id
      and job.lease_token = p_lease_token;
    return 'awaiting_final_sweep';
  end if;

  if greatest(coalesce(p_objects_deleted, 0), 0) > 0
     or v_job.empty_observed_at is null then
    update public.account_storage_deletion_jobs as job
    set status = 'pending',
        next_attempt_at = v_now + interval '5 minutes',
        empty_observed_at = v_now,
        lease_token = null,
        lease_expires_at = null,
        last_error = null,
        updated_at = v_now
    where job.id = v_job.id
      and job.lease_token = p_lease_token;
    return 'verification_started';
  end if;

  update public.account_storage_deletion_jobs as job
  set status = 'pending',
      next_attempt_at = greatest(v_now + interval '15 seconds', v_job.empty_observed_at + interval '5 minutes'),
      lease_token = null,
      lease_expires_at = null,
      last_error = null,
      updated_at = v_now
  where job.id = v_job.id
    and job.lease_token = p_lease_token;
  return 'awaiting_second_empty_observation';
end;
$$;

create or replace function public.complete_account_storage_deletion_job(
  p_job_id uuid,
  p_lease_token uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_deleted boolean := false;
begin
  delete from public.account_storage_deletion_jobs as job
  where job.id = p_job_id
    and job.status = 'processing'
    and job.lease_token = p_lease_token
    and job.final_sweep_after <= pg_catalog.clock_timestamp()
    and job.empty_observed_at <= pg_catalog.clock_timestamp() - interval '5 minutes'
  returning true into v_deleted;

  return coalesce(v_deleted, false);
end;
$$;

-- Record the independent Storage cleanup obligation before any cascade can
-- erase the file inventory.  The queue intentionally has no foreign key to
-- users so it survives account deletion and can be retried to completion.
create or replace function public.delete_user_account(
  p_user_id uuid,
  p_storage_bucket text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_user_id is null then
    raise exception 'user id is required' using errcode = '22023';
  end if;
  if p_storage_bucket is null
     or p_storage_bucket !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$' then
    raise exception 'invalid storage bucket' using errcode = '22023';
  end if;

  insert into public.account_storage_deletion_jobs as job (
    user_id,
    bucket,
    owner_prefix,
    status,
    attempts,
    next_attempt_at,
    final_sweep_after,
    empty_observed_at,
    lease_token,
    lease_expires_at,
    last_error,
    updated_at
  ) values (
    p_user_id,
    p_storage_bucket,
    p_user_id::text || '/',
    'pending',
    0,
    pg_catalog.clock_timestamp(),
    pg_catalog.clock_timestamp() + interval '27 hours',
    null,
    null,
    null,
    null,
    pg_catalog.clock_timestamp()
  )
  on conflict (user_id) do update
  set status = 'pending',
      next_attempt_at = least(job.next_attempt_at, pg_catalog.clock_timestamp()),
      final_sweep_after = greatest(
        job.final_sweep_after,
        pg_catalog.clock_timestamp() + interval '27 hours'
      ),
      empty_observed_at = null,
      lease_token = null,
      lease_expires_at = null,
      last_error = null,
      updated_at = pg_catalog.clock_timestamp();

  if pg_catalog.to_regclass('public.crump_chats') is not null then
    execute 'delete from public.crump_chats where user_id = $1' using p_user_id;
  end if;
  if pg_catalog.to_regclass('public.devices') is not null then
    execute 'delete from public.devices where user_id = $1' using p_user_id;
  end if;
  delete from public.usage_events where user_id = p_user_id;
  delete from public.user_chats where user_id = p_user_id;
  delete from public.user_settings where user_id = p_user_id;
  delete from public.sessions where user_id = p_user_id;
  delete from public.users where id = p_user_id;
end;
$$;

-- Preserve the existing one-argument contract for service-side callers that
-- use the canonical default bucket.  The account route calls the overload
-- above with the application's configured private bucket.
create or replace function public.delete_user_account(p_user_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform public.delete_user_account(p_user_id, 'crump-files');
end;
$$;

revoke all on function public.claim_account_storage_deletion_job() from public, anon, authenticated;
revoke all on function public.release_account_storage_deletion_job(uuid, uuid, integer, text) from public, anon, authenticated;
revoke all on function public.complete_account_storage_deletion_job(uuid, uuid) from public, anon, authenticated;
revoke all on function public.delete_user_account(uuid, text) from public, anon, authenticated;
revoke all on function public.delete_user_account(uuid) from public, anon, authenticated;

grant execute on function public.claim_account_storage_deletion_job() to service_role;
grant execute on function public.release_account_storage_deletion_job(uuid, uuid, integer, text) to service_role;
grant execute on function public.complete_account_storage_deletion_job(uuid, uuid) to service_role;
grant execute on function public.delete_user_account(uuid, text) to service_role;
grant execute on function public.delete_user_account(uuid) to service_role;
