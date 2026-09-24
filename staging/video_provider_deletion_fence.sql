-- SOURCE-ONLY CANDIDATE. Generate a numbered migration with the Supabase CLI
-- before applying. Never run this directly against production from this branch.
-- A provider start must remain traceable after public.users cascades media_jobs.
begin;

create table if not exists public.video_account_deletion_fences (
  user_id uuid primary key,
  operation_token uuid not null,
  requested_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table if not exists public.video_provider_start_claims (
  job_id uuid primary key,
  user_id uuid not null, -- Deliberately no user FK: minimal claim survives account deletion.
  provider text not null check (provider in ('gemini', 'runway')),
  operation_type text not null check (operation_type in ('generate', 'extend')),
  state text not null default 'reserved'
    check (state in ('reserved', 'dispatching', 'accepted', 'rejected', 'unknown', 'abandoned', 'settled')),
  dispatch_token uuid,
  provider_job_id text,
  lease_expires_at timestamptz not null default (now() + interval '2 minutes'),
  deletion_requested_at timestamptz,
  reconcile_after timestamptz not null default now(),
  reconcile_lease_token uuid,
  reconcile_lease_expires_at timestamptz,
  reconcile_attempt_count integer not null default 0 check (reconcile_attempt_count >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint video_provider_claim_accepted_id_check
    check (state <> 'accepted' or nullif(btrim(provider_job_id), '') is not null)
);

create index if not exists video_provider_claims_owner_state_idx
  on public.video_provider_start_claims(user_id, state, lease_expires_at);
create index if not exists video_provider_claims_deletion_idx
  on public.video_provider_start_claims(reconcile_after, deletion_requested_at)
  where deletion_requested_at is not null and state in ('dispatching', 'accepted', 'unknown');

alter table public.video_account_deletion_fences enable row level security;
alter table public.video_provider_start_claims enable row level security;
revoke all on table public.video_account_deletion_fences from public, anon, authenticated, service_role;
revoke all on table public.video_provider_start_claims from public, anon, authenticated, service_role;
grant select, insert, update, delete on table public.video_account_deletion_fences to service_role;
grant select, insert, update, delete on table public.video_provider_start_claims to service_role;

-- Preserve existing in-flight work during the migration-first rollout. A
-- pre-migration pending:<id> row has an unknowable provider outcome.
do $$
begin
  if exists (
    select 1
    from public.media_jobs
    where kind = 'video'
      and status in ('queued', 'processing')
      and (
        provider not in ('gemini', 'runway')
        or coalesce(operation_type, 'generate') not in ('generate', 'extend')
        or nullif(btrim(provider_job_id), '') is null
      )
  ) then
    raise exception
      'video deletion-fence preflight failed: unsupported in-flight media_jobs require operator review'
      using errcode = '55000';
  end if;
end;
$$;

insert into public.video_provider_start_claims (
  job_id, user_id, provider, operation_type, state, provider_job_id, lease_expires_at
)
select id, user_id, provider, coalesce(operation_type, 'generate'),
  case
    when provider_job_id like 'pending:%' then 'unknown'
    else 'accepted'
  end,
  case when provider_job_id like 'pending:%' then null else provider_job_id end,
  now()
from public.media_jobs
where kind = 'video' and status in ('queued', 'processing')
on conflict (job_id) do nothing;

create or replace function public.reserve_video_provider_claim(
  p_user_id uuid, p_job_id uuid, p_provider text, p_operation_type text
)
returns jsonb
language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare
  unresolved_job uuid;
begin
  -- Both claim and deletion take the user lock first, then claim rows.
  perform 1 from public.users where id = p_user_id for update;
  if not found then return jsonb_build_object('status', 'account_deleting'); end if;
  if exists (
    select 1 from public.video_account_deletion_fences where user_id = p_user_id
  ) then
    update public.video_provider_start_claims
    set state = 'rejected', updated_at = now()
    where job_id = p_job_id and user_id = p_user_id and state = 'reserved';
    return jsonb_build_object('status', 'account_deleting');
  end if;
  select job_id into unresolved_job
  from public.video_provider_start_claims
    where user_id = p_user_id
      and state in ('dispatching', 'unknown') and provider_job_id is null
    order by created_at desc limit 1;
  if unresolved_job is not null then
    return jsonb_build_object('status', 'start_unknown', 'jobId', unresolved_job);
  end if;
  insert into public.video_provider_start_claims (
    job_id, user_id, provider, operation_type
  ) values (p_job_id, p_user_id, p_provider, p_operation_type)
  on conflict (job_id) do nothing;
  if found then return jsonb_build_object('status', 'reserved'); end if;
  if exists (
    select 1 from public.video_provider_start_claims
    where job_id = p_job_id
      and user_id = p_user_id
      and provider = p_provider
      and operation_type = p_operation_type
      and state = 'reserved'
  ) then return jsonb_build_object('status', 'reserved'); end if;
  return jsonb_build_object('status', 'claim_unavailable');
end;
$$;

create or replace function public.begin_video_provider_dispatch(
  p_user_id uuid, p_job_id uuid, p_dispatch_token uuid
)
returns boolean
language plpgsql security invoker
set search_path = public, pg_temp
as $$
begin
  if p_dispatch_token is null then
    raise exception 'dispatch token is required' using errcode = '22023';
  end if;
  perform 1 from public.users where id = p_user_id for update;
  if not found then return false; end if;
  if exists (
    select 1 from public.video_account_deletion_fences where user_id = p_user_id
  ) then
    update public.video_provider_start_claims
    set state = 'rejected', updated_at = now()
    where job_id = p_job_id and user_id = p_user_id and state = 'reserved';
    return false;
  end if;
  update public.video_provider_start_claims
  set state = 'dispatching', dispatch_token = p_dispatch_token, updated_at = now()
  where job_id = p_job_id and user_id = p_user_id and state = 'reserved'
    and exists (
      select 1 from public.media_jobs
      where id = p_job_id and user_id = p_user_id and status = 'queued'
    );
  if found then return true; end if;
  return exists (
    select 1 from public.video_provider_start_claims
    where job_id = p_job_id and user_id = p_user_id
      and state = 'dispatching' and dispatch_token = p_dispatch_token
  );
end;
$$;

create or replace function public.record_video_provider_acceptance(
  p_user_id uuid, p_job_id uuid, p_provider_job_id text
)
returns boolean
language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare
  media_updated boolean;
begin
  if nullif(btrim(p_provider_job_id), '') is null then
    raise exception 'provider job ID is required' using errcode = '22023';
  end if;
  update public.video_provider_start_claims
  set state = 'accepted',
      provider_job_id = left(p_provider_job_id, 500),
      reconcile_after = now(),
      updated_at = now()
  where job_id = p_job_id and user_id = p_user_id
    and state in ('dispatching', 'unknown', 'accepted')
    and (provider_job_id is null or provider_job_id = left(p_provider_job_id, 500));
  if not found then
    raise exception 'provider claim is unavailable or conflicts' using errcode = '55000';
  end if;

  -- The claim update commits even when account deletion already cascaded the
  -- media row. This function is idempotent for transient RPC response loss.
  update public.media_jobs
  set provider_job_id = left(p_provider_job_id, 500),
      status = 'processing',
      metadata = coalesce(metadata, '{}'::jsonb) || '{"providerAccepted":true}'::jsonb,
      updated_at = now()
  where id = p_job_id and user_id = p_user_id
    and status in ('queued', 'processing');
  media_updated := found;
  return media_updated;
end;
$$;

create or replace function public.finish_video_provider_claim(
  p_user_id uuid, p_job_id uuid, p_outcome text
)
returns void
language plpgsql security invoker
set search_path = public, pg_temp
as $$
begin
  if p_outcome not in ('rejected', 'unknown', 'abandoned') then
    raise exception 'invalid provider claim outcome' using errcode = '22023';
  end if;
  update public.video_provider_start_claims
  set state = p_outcome, updated_at = now()
  where job_id = p_job_id and user_id = p_user_id
    and (
      state in ('reserved', 'dispatching')
      or (state = 'unknown' and p_outcome = 'rejected' and provider_job_id is null)
    )
    and (p_outcome <> 'abandoned' or state = 'reserved');
end;
$$;

create or replace function public.begin_video_account_deletion(
  p_user_id uuid, p_operation_token uuid
)
returns boolean
language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare
  deletion_user public.users%rowtype;
  deletion_fence public.video_account_deletion_fences%rowtype;
  active_user boolean := false;
begin
  if p_operation_token is null then
    raise exception 'deletion operation token is required' using errcode = '22023';
  end if;
  select * into deletion_user
  from public.users
  where id = p_user_id
  for update;
  if not found then return false; end if;
  active_user := deletion_user.deleted_at is null
    and deletion_user.account_deletion_token is null;

  -- Every deletion path takes user -> optional durable job -> fence -> claims.
  -- The user lock already serializes reservation/dispatch, so a read-only live
  -- reservation check is sufficient before the fence row is owned.
  perform 1 from public.account_deletion_jobs
  where user_id = p_user_id
  for update;
  -- A conflict must have no lasting fence or billing side effect. The caller
  -- may safely retry deletion when the original video request settles.
  if exists (
    select 1 from public.video_provider_start_claims
    where user_id = p_user_id and state = 'reserved' and lease_expires_at > now()
  ) then return false; end if;
  if active_user then
    insert into public.video_account_deletion_fences(user_id, operation_token)
    values (p_user_id, p_operation_token) on conflict (user_id) do nothing;
  end if;
  select * into deletion_fence
  from public.video_account_deletion_fences
  where user_id = p_user_id
  for update;
  if not found
    or deletion_fence.operation_token <> p_operation_token
    or deletion_fence.deleted_at is not null then
    return false;
  end if;
  -- A non-active user may only replay the exact already-established token.
  if not active_user and not (
    deletion_user.deleted_at is not null
    and deletion_user.account_deletion_token = p_operation_token
  ) then
    return false;
  end if;

  update public.video_provider_start_claims
  set state = 'abandoned', updated_at = now()
  where user_id = p_user_id and state = 'reserved' and lease_expires_at <= now();

  -- Older app instances may have created media rows before claim support.
  insert into public.video_provider_start_claims (
    job_id, user_id, provider, operation_type, state, provider_job_id, lease_expires_at
  )
  select id, user_id, provider, coalesce(operation_type, 'generate'),
    case when provider_job_id like 'pending:%' then 'unknown' else 'accepted' end,
    case when provider_job_id like 'pending:%' then null else provider_job_id end,
    now()
  from public.media_jobs
  where user_id = p_user_id and kind = 'video' and status in ('queued', 'processing')
  on conflict (job_id) do nothing;

  update public.video_provider_start_claims
  set deletion_requested_at = coalesce(deletion_requested_at, now()), updated_at = now()
  where user_id = p_user_id and deletion_requested_at is null;

  return true;
end;
$$;

create or replace function public.release_video_account_deletion_fence(
  p_user_id uuid, p_operation_token uuid
)
returns text
language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare
  deletion_user public.users%rowtype;
begin
  select * into deletion_user
  from public.users
  where id = p_user_id
  for update;
  if not found then return 'user_deleted'; end if;
  if deletion_user.deleted_at is not null
    or deletion_user.account_deletion_token is not null then
    return 'account_deleting';
  end if;
  delete from public.video_account_deletion_fences
  where user_id = p_user_id and operation_token = p_operation_token
    and deleted_at is null;
  if not found then return 'not_owner'; end if;
  update public.video_provider_start_claims
  set deletion_requested_at = null, updated_at = now()
  where user_id = p_user_id and deletion_requested_at is not null;
  return 'released';
end;
$$;

-- Commit the users-row fence under the same locks used by orphan recovery.
-- A paused caller can therefore never write users.deleted_at after recovery
-- has abandoned its durable job and released the provider-start fence.
create or replace function public.establish_account_deletion_fence(
  p_user_id uuid, p_operation_token uuid, p_fenced_at timestamptz
)
returns text
language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare
  deletion_user public.users%rowtype;
  deletion_job public.account_deletion_jobs%rowtype;
  deletion_fence public.video_account_deletion_fences%rowtype;
begin
  if p_operation_token is null or p_fenced_at is null then
    raise exception 'deletion operation token and fence time are required'
      using errcode = '22023';
  end if;

  select * into deletion_user
  from public.users
  where id = p_user_id
  for update;
  if not found then
    return 'user_deleted';
  end if;

  select * into deletion_job
  from public.account_deletion_jobs
  where user_id = p_user_id
  for update;
  if not found
    or deletion_job.operation_token <> p_operation_token
    or deletion_job.completed_at is not null then
    return 'job_unavailable';
  end if;

  select * into deletion_fence
  from public.video_account_deletion_fences
  where user_id = p_user_id
  for update;
  if not found
    or deletion_fence.operation_token <> p_operation_token
    or deletion_fence.deleted_at is not null then
    return 'video_fence_unavailable';
  end if;

  -- Preserve one global lock order for every recovery-sensitive row family.
  perform 1
  from public.video_provider_start_claims
  where user_id = p_user_id
  order by job_id
  for update;

  if deletion_user.deleted_at is not null
    or deletion_user.account_deletion_token is not null then
    if deletion_user.deleted_at is not null
      and deletion_user.account_deletion_token = p_operation_token then
      return 'fenced';
    end if;
    return 'user_fence_conflict';
  end if;

  update public.users
  set deleted_at = p_fenced_at,
      account_deletion_token = p_operation_token,
      ai_data_sharing_consent_revoked_at = p_fenced_at,
      ai_data_sharing_consent_updated_at = p_fenced_at,
      updated_at = p_fenced_at
  where id = p_user_id;
  return 'fenced';
end;
$$;

-- Recover only a token-consistent provider fence after the users-row deletion
-- fence failed to become durable. Every authoritative row is inspected under
-- one transaction and the same user -> job -> fence -> claims lock order as
-- establishment, eliminating a Python read/check/release TOCTOU window.
--
-- A missing job row cannot be predicate-locked. Immediate compensation by the
-- creating caller passes false; a later takeover passes true and is gated by
-- the locked fence's database-authored requested_at. If a paused caller inserts
-- late, establishment still rechecks the exact unfinished job and fence while
-- holding the same user lock, so it cannot commit after a successful release.
drop function if exists public.recover_video_account_deletion_fence(uuid, uuid);
create or replace function public.recover_video_account_deletion_fence(
  p_user_id uuid, p_operation_token uuid, p_require_stale boolean default false
)
returns text
language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare
  deletion_user public.users%rowtype;
  deletion_job public.account_deletion_jobs%rowtype;
  deletion_fence public.video_account_deletion_fences%rowtype;
  job_found boolean := false;
  fence_found boolean := false;
  job_was_live boolean := false;
begin
  if p_operation_token is null then
    raise exception 'deletion operation token is required' using errcode = '22023';
  end if;

  select * into deletion_user
  from public.users
  where id = p_user_id
  for update;
  if not found then
    return 'user_deleted';
  end if;

  select * into deletion_job
  from public.account_deletion_jobs
  where user_id = p_user_id
  for update;
  job_found := found;

  select * into deletion_fence
  from public.video_account_deletion_fences
  where user_id = p_user_id
  for update;
  fence_found := found;

  perform 1
  from public.video_provider_start_claims
  where user_id = p_user_id
  order by job_id
  for update;

  -- Either users column means establishment won the shared lock. The caller
  -- must re-read and may continue only when this exact token owns that fence.
  if deletion_user.deleted_at is not null
    or deletion_user.account_deletion_token is not null then
    return 'account_deleting';
  end if;

  if job_found and deletion_job.operation_token <> p_operation_token then
    return 'job_conflict';
  end if;
  if fence_found and (
    deletion_fence.operation_token <> p_operation_token
    or deletion_fence.deleted_at is not null
  ) then
    return 'not_owner';
  end if;

  -- A takeover of an orphan with no durable job must use the database clock
  -- while this exact fence row is locked. Immediate compensation by the
  -- creating caller passes false and may release without waiting.
  if not job_found and fence_found and p_require_stale
    and deletion_fence.requested_at > now() - interval '15 minutes' then
    return 'still_reconciling';
  end if;

  if job_found and deletion_job.completed_at is null then
    job_was_live := true;
    -- Job reset timestamps may come from an application clock. The exact
    -- fence was created by Postgres, so it is the freshness authority. With no
    -- fence there is no database-authored operation time to prove staleness;
    -- keep that job fail-closed for a later exact-token request/operator.
    if not fence_found then
      return 'still_reconciling';
    end if;
    if deletion_fence.requested_at > now() - interval '15 minutes' then
      return 'still_reconciling';
    end if;
    update public.account_deletion_jobs
    set state = 'abandoned',
        completed_at = now(),
        next_attempt_at = null,
        last_error_code = 'DELETION_FENCE_NOT_ESTABLISHED',
        updated_at = now()
    where user_id = p_user_id
      and operation_token = p_operation_token
      and completed_at is null;
    if not found then
      raise exception 'deletion job recovery lost ownership' using errcode = '40001';
    end if;
  end if;

  if fence_found then
    delete from public.video_account_deletion_fences
    where user_id = p_user_id
      and operation_token = p_operation_token
      and deleted_at is null;
    if not found then
      raise exception 'video deletion fence recovery lost ownership' using errcode = '40001';
    end if;
    update public.video_provider_start_claims
    set deletion_requested_at = null, updated_at = now()
    where user_id = p_user_id and deletion_requested_at is not null;
  end if;

  if job_was_live then
    return 'abandoned';
  end if;
  if fence_found then
    return 'released';
  end if;
  return 'already_released';
end;
$$;

create or replace function public.claim_deleted_video_provider_reconciliation(
  p_lease_token uuid
)
returns setof public.video_provider_start_claims
language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare
  claimed public.video_provider_start_claims%rowtype;
begin
  if p_lease_token is null then
    raise exception 'reconciliation lease token is required' using errcode = '22023';
  end if;
  select * into claimed
  from public.video_provider_start_claims
  where reconcile_lease_token = p_lease_token
    and reconcile_lease_expires_at > now()
  limit 1;
  if found then
    return next claimed;
    return;
  end if;

  select * into claimed
  from public.video_provider_start_claims
  where deletion_requested_at is not null
    and exists (
      select 1 from public.video_account_deletion_fences
      where user_id = video_provider_start_claims.user_id and deleted_at is not null
    )
    and state in ('dispatching', 'accepted', 'unknown')
    and reconcile_after <= now()
    and (reconcile_lease_expires_at is null or reconcile_lease_expires_at < now())
  order by reconcile_after asc, created_at asc
  for update skip locked
  limit 1;
  if not found then return; end if;

  update public.video_provider_start_claims
  set reconcile_lease_token = p_lease_token,
      reconcile_lease_expires_at = now() + interval '4 minutes',
      reconcile_attempt_count = reconcile_attempt_count + 1,
      updated_at = now()
  where job_id = claimed.job_id
  returning * into claimed;
  return next claimed;
end;
$$;

create or replace function public.release_deleted_video_provider_reconciliation(
  p_job_id uuid, p_lease_token uuid, p_next_state text, p_delay_seconds integer
)
returns boolean
language plpgsql security invoker
set search_path = public, pg_temp
as $$
begin
  if p_next_state not in ('accepted', 'unknown', 'settled') then
    raise exception 'invalid reconciliation state' using errcode = '22023';
  end if;
  update public.video_provider_start_claims
  set state = p_next_state,
      reconcile_after = now() + make_interval(secs => greatest(60, least(86400, p_delay_seconds))),
      reconcile_lease_token = null,
      reconcile_lease_expires_at = null,
      updated_at = now()
  where job_id = p_job_id and reconcile_lease_token = p_lease_token
    and state in ('dispatching', 'accepted', 'unknown');
  return found;
end;
$$;

create or replace function public.require_video_account_deletion_fence()
returns trigger
language plpgsql security invoker
set search_path = public, pg_temp
as $$
begin
  if not exists (
    select 1 from public.video_account_deletion_fences where user_id = old.id
  ) then
    raise exception 'video deletion fence is required' using errcode = '55000';
  end if;
  if exists (
    select 1 from public.video_provider_start_claims
    where user_id = old.id and state = 'reserved'
  ) then
    raise exception 'video provider reservation is still settling' using errcode = '55000';
  end if;
  -- Snapshot one last time before media_jobs is removed by the user FK.
  insert into public.video_provider_start_claims (
    job_id, user_id, provider, operation_type, state, provider_job_id, lease_expires_at,
    deletion_requested_at
  )
  select id, user_id, provider, coalesce(operation_type, 'generate'),
    case when provider_job_id like 'pending:%' then 'unknown' else 'accepted' end,
    case when provider_job_id like 'pending:%' then null else provider_job_id end,
    now(), now()
  from public.media_jobs
  where user_id = old.id and kind = 'video' and status in ('queued', 'processing')
  on conflict (job_id) do nothing;
  update public.video_provider_start_claims
  set deletion_requested_at = coalesce(deletion_requested_at, now())
  where user_id = old.id and deletion_requested_at is null;
  update public.video_account_deletion_fences
  set deleted_at = now() where user_id = old.id;
  return old;
end;
$$;

drop trigger if exists require_video_account_deletion_fence on public.users;
create trigger require_video_account_deletion_fence
  before delete on public.users
  for each row execute function public.require_video_account_deletion_fence();

revoke all on function public.reserve_video_provider_claim(uuid, uuid, text, text)
  from public, anon, authenticated, service_role;
revoke all on function public.begin_video_provider_dispatch(uuid, uuid, uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.record_video_provider_acceptance(uuid, uuid, text)
  from public, anon, authenticated, service_role;
revoke all on function public.finish_video_provider_claim(uuid, uuid, text)
  from public, anon, authenticated, service_role;
revoke all on function public.begin_video_account_deletion(uuid, uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.release_video_account_deletion_fence(uuid, uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.establish_account_deletion_fence(uuid, uuid, timestamptz)
  from public, anon, authenticated, service_role;
revoke all on function public.recover_video_account_deletion_fence(uuid, uuid, boolean)
  from public, anon, authenticated, service_role;
revoke all on function public.claim_deleted_video_provider_reconciliation(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.release_deleted_video_provider_reconciliation(uuid, uuid, text, integer)
  from public, anon, authenticated, service_role;
revoke all on function public.require_video_account_deletion_fence()
  from public, anon, authenticated, service_role;
grant execute on function public.reserve_video_provider_claim(uuid, uuid, text, text) to service_role;
grant execute on function public.begin_video_provider_dispatch(uuid, uuid, uuid) to service_role;
grant execute on function public.record_video_provider_acceptance(uuid, uuid, text) to service_role;
grant execute on function public.finish_video_provider_claim(uuid, uuid, text) to service_role;
grant execute on function public.begin_video_account_deletion(uuid, uuid) to service_role;
grant execute on function public.release_video_account_deletion_fence(uuid, uuid) to service_role;
grant execute on function public.establish_account_deletion_fence(uuid, uuid, timestamptz) to service_role;
grant execute on function public.recover_video_account_deletion_fence(uuid, uuid, boolean) to service_role;
grant execute on function public.claim_deleted_video_provider_reconciliation(uuid) to service_role;
grant execute on function public.release_deleted_video_provider_reconciliation(uuid, uuid, text, integer) to service_role;

comment on table public.video_provider_start_claims is
  'Service-only, content-free provider-start journal; never store prompts, images, URLs, or credit receipts.';
comment on table public.video_account_deletion_fences is
  'Service-only deletion fence; prevents new provider dispatch while user deletion settles.';
commit;
