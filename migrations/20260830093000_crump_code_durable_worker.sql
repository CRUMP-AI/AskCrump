-- Make accepted Crump Code tasks durable across request and worker interruptions.
-- The browser records a metered dispatch once; a private, lease-owned cron worker
-- performs bounded Sandbox execution and can safely retry without charging again.

begin;

alter table public.code_tasks
  add column if not exists dispatch_token uuid,
  add column if not exists lease_token uuid,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists next_attempt_at timestamptz not null default now(),
  add column if not exists attempt_count integer not null default 0,
  add column if not exists max_attempts integer not null default 3;

alter table public.code_tasks
  drop constraint if exists code_tasks_attempt_count_check,
  add constraint code_tasks_attempt_count_check check (attempt_count >= 0),
  drop constraint if exists code_tasks_max_attempts_check,
  add constraint code_tasks_max_attempts_check check (max_attempts between 1 and 5);

create index if not exists code_tasks_worker_ready_idx
  on public.code_tasks(next_attempt_at asc, created_at asc)
  where status in ('provisioning', 'running', 'verifying');

create index if not exists code_tasks_refund_pending_idx
  on public.code_tasks(updated_at asc)
  where payment_source = 'refund_pending' and status in ('failed', 'cancelled');

create unique index if not exists code_tasks_dispatch_token_idx
  on public.code_tasks(dispatch_token)
  where dispatch_token is not null;

create or replace function public.dispatch_code_task(
  p_task_id uuid,
  p_user_id uuid,
  p_dispatch_token uuid,
  p_usage_receipt jsonb,
  p_payment_source text,
  p_credits_spent integer
)
returns setof public.code_tasks
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  dispatched public.code_tasks%rowtype;
begin
  if p_dispatch_token is null or p_usage_receipt is null then
    raise exception 'dispatch token and usage receipt are required' using errcode = '22023';
  end if;

  -- A retry after an uncertain response returns the same committed dispatch.
  select *
  into dispatched
  from public.code_tasks
  where id = p_task_id
    and user_id = p_user_id
    and dispatch_token = p_dispatch_token
  limit 1;

  if found then
    return next dispatched;
    return;
  end if;

  update public.code_tasks
  set status = 'provisioning',
      started_at = coalesce(started_at, now()),
      failure_code = null,
      next_attempt_at = now(),
      usage_receipt = p_usage_receipt,
      payment_source = p_payment_source,
      credits_spent = greatest(0, least(100000, coalesce(p_credits_spent, 0))),
      dispatch_token = p_dispatch_token,
      updated_at = now()
  where id = p_task_id
    and user_id = p_user_id
    and status = 'queued'
    and expires_at > now()
  returning * into dispatched;

  if not found then
    return;
  end if;

  insert into public.code_task_events (
    task_id,
    user_id,
    project_id,
    event_type,
    payload
  )
  values (
    dispatched.id,
    dispatched.user_id,
    dispatched.project_id,
    'task.claimed',
    '{"status":"provisioning"}'::jsonb
  );

  return next dispatched;
end;
$$;

revoke all on function public.dispatch_code_task(uuid, uuid, uuid, jsonb, text, integer)
  from public, anon, authenticated;
revoke all on function public.dispatch_code_task(uuid, uuid, uuid, jsonb, text, integer)
  from service_role;
grant execute on function public.dispatch_code_task(uuid, uuid, uuid, jsonb, text, integer)
  to service_role;

create or replace function public.claim_code_task(
  p_lease_seconds integer,
  p_claim_token uuid
)
returns setof public.code_tasks
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  claimed public.code_tasks%rowtype;
begin
  if p_claim_token is null then
    raise exception 'claim token is required' using errcode = '22023';
  end if;

  -- Replay the same committed claim if PostgREST lost the first response.
  select *
  into claimed
  from public.code_tasks
  where status in ('provisioning', 'running', 'verifying')
    and lease_token = p_claim_token
    and lease_expires_at > now()
  limit 1;

  if found then
    return next claimed;
    return;
  end if;

  select *
  into claimed
  from public.code_tasks
  where status in ('provisioning', 'running', 'verifying')
    and usage_receipt is not null
    and next_attempt_at <= now()
    and expires_at > now()
    and (lease_token is null or lease_expires_at is null or lease_expires_at < now())
  order by next_attempt_at asc, created_at asc
  for update skip locked
  limit 1;

  if not found then
    return;
  end if;

  update public.code_tasks
  set status = 'provisioning',
      lease_token = p_claim_token,
      lease_expires_at = now() + make_interval(secs => greatest(60, least(300, p_lease_seconds))),
      attempt_count = attempt_count + 1,
      failure_code = null,
      started_at = coalesce(started_at, now()),
      updated_at = now()
  where id = claimed.id
  returning * into claimed;

  return next claimed;
end;
$$;

revoke all on function public.claim_code_task(integer, uuid) from public, anon, authenticated;
revoke all on function public.claim_code_task(integer, uuid) from service_role;
grant execute on function public.claim_code_task(integer, uuid) to service_role;

comment on function public.dispatch_code_task(uuid, uuid, uuid, jsonb, text, integer) is
  'Private idempotent transition from a reviewed queued task to one metered worker dispatch.';

comment on function public.claim_code_task(integer, uuid) is
  'Private, replay-safe lease claim for one previously metered Crump Code task.';

commit;
