-- Autonomous Crump queue, budget, concurrency, and fairness guardrails.
--
-- This migration is intentionally dormant behind both existing release gates.
-- Every customer-visible acceptance decision and every worker compute claim is
-- made inside one short database transaction. Fixed, bounded limits live in a
-- private singleton row so future changes require a reviewed migration rather
-- than an environment-variable edit.

begin;

create table if not exists public.code_guardrail_limits (
  id smallint primary key default 1,
  user_queue_limit integer not null default 3,
  global_queue_limit integer not null default 100,
  global_active_lease_limit integer not null default 2,
  user_daily_accept_limit integer not null default 3,
  global_daily_accept_limit integer not null default 30,
  user_daily_model_start_limit integer not null default 4,
  global_daily_model_start_limit integer not null default 24,
  user_daily_sandbox_seconds integer not null default 720,
  global_daily_sandbox_seconds integer not null default 4320,
  updated_at timestamptz not null default now(),
  constraint code_guardrail_limits_singleton_check check (id = 1),
  constraint code_guardrail_limits_user_queue_check
    check (user_queue_limit between 1 and 5),
  constraint code_guardrail_limits_global_queue_check
    check (global_queue_limit between 10 and 500),
  constraint code_guardrail_limits_global_active_check
    check (global_active_lease_limit between 1 and 4),
  constraint code_guardrail_limits_user_accept_check
    check (user_daily_accept_limit between 1 and 10),
  constraint code_guardrail_limits_global_accept_check
    check (global_daily_accept_limit between 5 and 200),
  constraint code_guardrail_limits_user_model_start_check
    check (user_daily_model_start_limit between 1 and 12),
  constraint code_guardrail_limits_global_model_start_check
    check (global_daily_model_start_limit between 2 and 100),
  constraint code_guardrail_limits_user_sandbox_seconds_check
    check (user_daily_sandbox_seconds between 30 and 2880),
  constraint code_guardrail_limits_global_sandbox_seconds_check
    check (global_daily_sandbox_seconds between 60 and 24000)
);

insert into public.code_guardrail_limits (
  id,
  user_queue_limit,
  global_queue_limit,
  global_active_lease_limit,
  user_daily_accept_limit,
  global_daily_accept_limit,
  user_daily_model_start_limit,
  global_daily_model_start_limit,
  user_daily_sandbox_seconds,
  global_daily_sandbox_seconds
)
values (1, 3, 100, 2, 3, 30, 4, 24, 720, 4320)
on conflict (id) do nothing;

create table if not exists public.code_guardrail_receipts (
  id bigint generated always as identity primary key,
  task_id uuid not null references public.code_tasks(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  budget_day date not null,
  receipt_kind text not null,
  attempt_number integer not null default 0,
  declared_sandbox_seconds integer not null default 0,
  created_at timestamptz not null default now(),
  constraint code_guardrail_receipts_kind_check
    check (receipt_kind in ('accepted', 'model_start')),
  constraint code_guardrail_receipts_attempt_check
    check (
      (receipt_kind = 'accepted' and attempt_number = 0)
      or (receipt_kind = 'model_start' and attempt_number between 1 and 5)
    ),
  constraint code_guardrail_receipts_seconds_check
    check (
      (receipt_kind = 'accepted' and declared_sandbox_seconds = 0)
      or (receipt_kind = 'model_start' and declared_sandbox_seconds between 30 and 240)
    ),
  constraint code_guardrail_receipts_unique_attempt
    unique (task_id, receipt_kind, attempt_number)
);

create index if not exists code_guardrail_receipts_global_day_idx
  on public.code_guardrail_receipts(budget_day, receipt_kind, created_at asc);

create index if not exists code_guardrail_receipts_user_day_idx
  on public.code_guardrail_receipts(user_id, budget_day, receipt_kind, created_at desc);

create index if not exists code_guardrail_receipts_fairness_idx
  on public.code_guardrail_receipts(user_id, created_at desc)
  where receipt_kind = 'model_start';

create unique index if not exists code_tasks_one_accepted_active_per_user_idx
  on public.code_tasks(user_id)
  where dispatch_token is not null
    and usage_receipt is not null
    and status in ('queued', 'provisioning', 'running', 'awaiting_approval', 'verifying');

create index if not exists code_tasks_unaccepted_queue_idx
  on public.code_tasks(user_id, created_at asc)
  where status = 'queued'
    and dispatch_token is null
    and usage_receipt is null;

create index if not exists code_tasks_active_lease_idx
  on public.code_tasks(lease_expires_at asc, user_id)
  where status in ('provisioning', 'running', 'verifying')
    and lease_token is not null;

alter table public.code_guardrail_limits enable row level security;
alter table public.code_guardrail_receipts enable row level security;

revoke all on table public.code_guardrail_limits from public, anon, authenticated, service_role;
revoke all on table public.code_guardrail_receipts from public, anon, authenticated, service_role;
revoke all on sequence public.code_guardrail_receipts_id_seq
  from public, anon, authenticated, service_role;

grant select on table public.code_guardrail_limits to service_role;
grant select, insert on table public.code_guardrail_receipts to service_role;
grant usage, select on sequence public.code_guardrail_receipts_id_seq to service_role;

create or replace function public.enforce_code_task_queue_guardrail()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  guardrails public.code_guardrail_limits%rowtype;
  user_queued integer;
  global_queued integer;
begin
  if new.status <> 'queued'
     or new.dispatch_token is not null
     or new.usage_receipt is not null then
    raise exception 'New Autonomous Crump tasks must enter the guarded queue'
      using errcode = '23514';
  end if;

  -- Every guarded operation locks the global namespace before the user
  -- namespace. UUID hash collisions only serialize unrelated users; they can
  -- never weaken a limit.
  perform pg_catalog.pg_advisory_xact_lock(8274, 0);
  perform pg_catalog.pg_advisory_xact_lock(8274, pg_catalog.hashtext(new.user_id::text));

  select *
  into guardrails
  from public.code_guardrail_limits
  where id = 1;

  if not found then
    raise exception 'Autonomous Crump guardrail configuration is unavailable';
  end if;

  select count(*)::integer
  into user_queued
  from public.code_tasks
  where user_id = new.user_id
    and status = 'queued'
    and dispatch_token is null
    and usage_receipt is null
    and expires_at > now();

  if user_queued >= guardrails.user_queue_limit then
    raise exception 'Autonomous Crump user queue limit reached'
      using errcode = 'P0001', detail = 'user_queue_limit';
  end if;

  select count(*)::integer
  into global_queued
  from public.code_tasks
  where status = 'queued'
    and dispatch_token is null
    and usage_receipt is null
    and expires_at > now();

  if global_queued >= guardrails.global_queue_limit then
    raise exception 'Autonomous Crump global queue limit reached'
      using errcode = 'P0001', detail = 'global_queue_limit';
  end if;

  return new;
end;
$$;

revoke all on function public.enforce_code_task_queue_guardrail()
  from public, anon, authenticated, service_role;

drop trigger if exists code_tasks_guarded_insert on public.code_tasks;
create trigger code_tasks_guarded_insert
before insert on public.code_tasks
for each row execute function public.enforce_code_task_queue_guardrail();

create or replace function public.create_code_task_guarded(
  p_user_id uuid,
  p_project_id uuid,
  p_objective text,
  p_mode text,
  p_source_repo_url text,
  p_source_ref text,
  p_max_duration_seconds integer
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  guardrails public.code_guardrail_limits%rowtype;
  created public.code_tasks%rowtype;
  user_queued integer;
  global_queued integer;
begin
  if p_user_id is null or p_project_id is null then
    raise exception 'Autonomous Crump task ownership is required' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(8274, 0);
  perform pg_catalog.pg_advisory_xact_lock(8274, pg_catalog.hashtext(p_user_id::text));

  select *
  into guardrails
  from public.code_guardrail_limits
  where id = 1;

  if not found then
    return jsonb_build_object(
      'created', false,
      'deferred', true,
      'reason', 'guardrail_unavailable',
      'retryAfterSeconds', 60
    );
  end if;

  select count(*)::integer
  into user_queued
  from public.code_tasks
  where user_id = p_user_id
    and status = 'queued'
    and dispatch_token is null
    and usage_receipt is null
    and expires_at > now();

  if user_queued >= guardrails.user_queue_limit then
    return jsonb_build_object(
      'created', false,
      'deferred', true,
      'reason', 'user_queue_limit',
      'retryAfterSeconds', 30
    );
  end if;

  select count(*)::integer
  into global_queued
  from public.code_tasks
  where status = 'queued'
    and dispatch_token is null
    and usage_receipt is null
    and expires_at > now();

  if global_queued >= guardrails.global_queue_limit then
    return jsonb_build_object(
      'created', false,
      'deferred', true,
      'reason', 'global_queue_limit',
      'retryAfterSeconds', 900
    );
  end if;

  insert into public.code_tasks (
    user_id,
    project_id,
    objective,
    mode,
    source_repo_url,
    source_ref,
    status,
    network_policy,
    max_duration_seconds,
    updated_at
  )
  select
    p_user_id,
    project.id,
    p_objective,
    p_mode,
    p_source_repo_url,
    nullif(p_source_ref, ''),
    'queued',
    'deny_all',
    p_max_duration_seconds,
    now()
  from public.projects as project
  where project.id = p_project_id
    and project.user_id = p_user_id
  returning * into created;

  if not found then
    return jsonb_build_object('created', false, 'reason', 'project_not_found');
  end if;

  insert into public.code_task_events (
    task_id,
    user_id,
    project_id,
    event_type,
    payload
  )
  values (
    created.id,
    created.user_id,
    created.project_id,
    'task.created',
    jsonb_build_object('mode', created.mode)
  );

  return jsonb_build_object(
    'created', true,
    'deferred', false,
    'task', to_jsonb(created),
    'guardrailReceipt', jsonb_build_object(
      'kind', 'queued',
      'userQueueLimit', guardrails.user_queue_limit,
      'globalQueueLimit', guardrails.global_queue_limit
    )
  );
end;
$$;

revoke all on function public.create_code_task_guarded(
  uuid, uuid, text, text, text, text, integer
) from public, anon, authenticated, service_role;
grant execute on function public.create_code_task_guarded(
  uuid, uuid, text, text, text, text, integer
) to service_role;

create or replace function public.accept_code_task_run(
  p_task_id uuid,
  p_user_id uuid,
  p_dispatch_token uuid,
  p_source_revision text,
  p_included_limit integer,
  p_credit_cost integer,
  p_credit_action_key text,
  p_confirmed_max integer
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  candidate public.code_tasks%rowtype;
  dispatched public.code_tasks%rowtype;
  guardrails public.code_guardrail_limits%rowtype;
  usage_event_id uuid;
  usage_used integer;
  usage_allowed boolean;
  credit_ledger_id uuid;
  credit_balance bigint;
  credit_allowed boolean;
  credit_duplicate boolean;
  credit_limit_exceeded boolean;
  receipt jsonb;
  normalized_revision text := lower(trim(coalesce(p_source_revision, '')));
  normalized_action text := left(trim(coalesce(p_credit_action_key, '')), 160);
  usage_metadata jsonb;
  internal_access boolean := false;
  current_budget_day date := (current_timestamp at time zone 'UTC')::date;
  user_accepted integer;
  global_accepted integer;
  retry_after_midnight integer := greatest(
    1,
    extract(epoch from (
      date_trunc('day', current_timestamp at time zone 'UTC') + interval '1 day'
      - (current_timestamp at time zone 'UTC')
    ))::integer
  );
begin
  if p_task_id is null or p_user_id is null or p_dispatch_token is null then
    raise exception 'Atomic code dispatch identifiers are required' using errcode = '22023';
  end if;
  if normalized_revision !~ '^[0-9a-f]{40}$' then
    raise exception 'Atomic code dispatch requires an immutable source revision'
      using errcode = '22023';
  end if;
  if p_included_limit is null or p_included_limit not in (3, 10) then
    raise exception 'Atomic code dispatch included limit is invalid' using errcode = '22023';
  end if;
  if p_credit_cost is null or p_credit_cost <> 12 then
    raise exception 'Atomic code dispatch credit cost is invalid' using errcode = '22023';
  end if;
  if p_confirmed_max is null or p_confirmed_max < 0 or p_confirmed_max > 100000 then
    raise exception 'Atomic code dispatch confirmed maximum is invalid' using errcode = '22023';
  end if;

  -- Consistent lock order: global namespace, user namespace, task row.
  perform pg_catalog.pg_advisory_xact_lock(8274, 0);
  perform pg_catalog.pg_advisory_xact_lock(8274, pg_catalog.hashtext(p_user_id::text));

  select *
  into guardrails
  from public.code_guardrail_limits
  where id = 1;

  if not found then
    return jsonb_build_object(
      'accepted', false,
      'deferred', true,
      'reason', 'guardrail_unavailable',
      'retryAfterSeconds', 60
    );
  end if;

  select *
  into candidate
  from public.code_tasks
  where id = p_task_id
    and user_id = p_user_id
  for update skip locked;

  if not found then
    return jsonb_build_object('accepted', false, 'reason', 'task_not_ready');
  end if;

  -- An uncertain HTTP response replays the committed owner token without
  -- charging, consuming budget, or creating another receipt.
  if candidate.dispatch_token = p_dispatch_token then
    if candidate.usage_receipt is null or candidate.status = 'queued' then
      raise exception 'Atomic code dispatch replay state is incomplete';
    end if;
    return jsonb_build_object(
      'accepted', true,
      'replayed', true,
      'task', to_jsonb(candidate)
    );
  end if;

  if candidate.status <> 'queued'
     or candidate.dispatch_token is not null
     or candidate.usage_receipt is not null
     or candidate.expires_at <= now()
     or lower(coalesce(candidate.source_ref, '')) <> normalized_revision
     or lower(coalesce(candidate.base_revision, '')) <> normalized_revision then
    return jsonb_build_object('accepted', false, 'reason', 'task_not_ready');
  end if;

  if exists (
    select 1
    from public.code_tasks as active
    where active.user_id = p_user_id
      and active.id <> candidate.id
      and active.dispatch_token is not null
      and active.usage_receipt is not null
      and active.status in (
        'queued', 'provisioning', 'running', 'awaiting_approval', 'verifying'
      )
  ) then
    return jsonb_build_object(
      'accepted', false,
      'deferred', true,
      'reason', 'user_active_task',
      'retryAfterSeconds', 30
    );
  end if;

  select
    count(*) filter (where user_id = p_user_id)::integer,
    count(*)::integer
  into user_accepted, global_accepted
  from public.code_guardrail_receipts
  where code_guardrail_receipts.budget_day = current_budget_day
    and receipt_kind = 'accepted';

  if user_accepted >= guardrails.user_daily_accept_limit then
    return jsonb_build_object(
      'accepted', false,
      'deferred', true,
      'reason', 'user_daily_accept_limit',
      'retryAfterSeconds', retry_after_midnight
    );
  end if;

  if global_accepted >= guardrails.global_daily_accept_limit then
    return jsonb_build_object(
      'accepted', false,
      'deferred', true,
      'reason', 'global_daily_accept_limit',
      'retryAfterSeconds', retry_after_midnight
    );
  end if;

  select lower(coalesce(account.internal_tier, '')) in ('professional', 'enterprise')
  into internal_access
  from public.users as account
  where account.id = p_user_id
    and account.deleted_at is null;

  if not found then
    return jsonb_build_object('accepted', false, 'reason', 'task_not_ready');
  end if;

  usage_metadata := jsonb_build_object(
    'feature', 'code_workspace',
    'route', 'code_task',
    'taskId', candidate.id,
    'mode', candidate.mode,
    'creditActionKey', normalized_action
  );

  if internal_access then
    select coalesce(account.balance, 0)
    into credit_balance
    from public.credit_accounts as account
    where account.user_id = p_user_id;

    receipt := jsonb_build_object(
      'feature', 'code_workspace',
      'paymentSource', 'internal',
      'eventId', null,
      'creditBalance', coalesce(credit_balance, 0),
      'creditsSpent', 0,
      'internalAccess', true
    );
  else
    select event_id, used, allowed
    into usage_event_id, usage_used, usage_allowed
    from public.consume_usage_event(
      p_user_id,
      'feature:code_workspace',
      p_included_limit,
      usage_metadata
    );

    if usage_allowed then
      select coalesce(account.balance, 0)
      into credit_balance
      from public.credit_accounts as account
      where account.user_id = p_user_id;

      receipt := jsonb_build_object(
        'feature', 'code_workspace',
        'paymentSource', 'included',
        'eventId', usage_event_id,
        'creditBalance', coalesce(credit_balance, 0),
        'creditsSpent', 0,
        'used', usage_used,
        'limit', p_included_limit
      );
    else
      select coalesce(account.balance, 0)
      into credit_balance
      from public.credit_accounts as account
      where account.user_id = p_user_id;

      if p_credit_cost <= 0
         or normalized_action = ''
         or p_confirmed_max < p_credit_cost then
        return jsonb_build_object(
          'accepted', false,
          'reason', 'credit_confirmation_required',
          'creditBalance', coalesce(credit_balance, 0),
          'creditsRequired', greatest(0, p_credit_cost)
        );
      end if;

      select ledger_id, balance, allowed, duplicate, limit_exceeded
      into credit_ledger_id, credit_balance, credit_allowed,
           credit_duplicate, credit_limit_exceeded
      from public.spend_credits_confirmed(
        p_user_id,
        p_credit_cost,
        'feature_code_workspace',
        normalized_action,
        candidate.id::text,
        p_confirmed_max,
        usage_metadata
      );

      if credit_limit_exceeded then
        return jsonb_build_object(
          'accepted', false,
          'reason', 'credit_confirmation_required',
          'creditBalance', coalesce(credit_balance, 0),
          'creditsRequired', p_credit_cost
        );
      end if;
      if not coalesce(credit_allowed, false) then
        return jsonb_build_object(
          'accepted', false,
          'reason', 'credits_required',
          'creditBalance', coalesce(credit_balance, 0),
          'creditsRequired', p_credit_cost
        );
      end if;

      receipt := jsonb_build_object(
        'feature', 'code_workspace',
        'paymentSource', 'credits',
        'eventId', 'credit:' || credit_ledger_id::text,
        'creditBalance', coalesce(credit_balance, 0),
        'creditsSpent', p_credit_cost,
        'idempotentReplay', coalesce(credit_duplicate, false)
      );
    end if;
  end if;

  update public.code_tasks
  set status = 'provisioning',
      started_at = coalesce(started_at, now()),
      failure_code = null,
      next_attempt_at = now(),
      usage_receipt = receipt,
      payment_source = receipt ->> 'paymentSource',
      credits_spent = greatest(
        0,
        least(100000, coalesce((receipt ->> 'creditsSpent')::integer, 0))
      ),
      dispatch_token = p_dispatch_token,
      updated_at = now()
  where id = candidate.id
    and user_id = candidate.user_id
    and status = 'queued'
    and dispatch_token is null
    and usage_receipt is null
  returning * into dispatched;

  if not found then
    raise exception 'Atomic code dispatch lost its locked task';
  end if;

  insert into public.code_guardrail_receipts (
    task_id,
    user_id,
    budget_day,
    receipt_kind,
    attempt_number,
    declared_sandbox_seconds
  )
  values (
    dispatched.id,
    dispatched.user_id,
    current_budget_day,
    'accepted',
    0,
    0
  );

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
    jsonb_build_object('status', 'provisioning', 'mode', dispatched.mode)
  );

  return jsonb_build_object(
    'accepted', true,
    'replayed', false,
    'task', to_jsonb(dispatched),
    'guardrailReceipt', jsonb_build_object(
      'kind', 'accepted',
      'budgetDay', current_budget_day,
      'declaredSandboxSeconds', 0
    )
  );
end;
$$;

revoke all on function public.accept_code_task_run(
  uuid, uuid, uuid, text, integer, integer, text, integer
) from public, anon, authenticated, service_role;
grant execute on function public.accept_code_task_run(
  uuid, uuid, uuid, text, integer, integer, text, integer
) to service_role;

create or replace function public.claim_code_task_guarded(
  p_lease_seconds integer,
  p_claim_token uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  guardrails public.code_guardrail_limits%rowtype;
  candidate public.code_tasks%rowtype;
  claimed public.code_tasks%rowtype;
  candidate_id uuid;
  candidate_user_id uuid;
  current_budget_day date := (current_timestamp at time zone 'UTC')::date;
  global_active integer;
  global_starts integer;
  global_seconds integer;
  user_starts integer;
  user_seconds integer;
  declared_seconds integer;
  next_attempt integer;
  retry_after_midnight integer := greatest(
    1,
    extract(epoch from (
      date_trunc('day', current_timestamp at time zone 'UTC') + interval '1 day'
      - (current_timestamp at time zone 'UTC')
    ))::integer
  );
begin
  if p_claim_token is null then
    raise exception 'claim token is required' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(8274, 0);

  select *
  into guardrails
  from public.code_guardrail_limits
  where id = 1;

  if not found then
    return jsonb_build_object(
      'claimed', false,
      'deferred', true,
      'reason', 'guardrail_unavailable',
      'retryAfterSeconds', 60
    );
  end if;

  -- Replay a committed lease without another model-start or Sandbox reservation.
  select *
  into claimed
  from public.code_tasks
  where status in ('provisioning', 'running', 'verifying')
    and lease_token = p_claim_token
    and lease_expires_at > now()
  limit 1;

  if found then
    return jsonb_build_object(
      'claimed', true,
      'replayed', true,
      'task', to_jsonb(claimed)
    );
  end if;

  select count(*)::integer
  into global_active
  from public.code_tasks
  where status in ('provisioning', 'running', 'verifying')
    and lease_token is not null
    and lease_expires_at > now();

  if global_active >= guardrails.global_active_lease_limit then
    return jsonb_build_object(
      'claimed', false,
      'deferred', true,
      'reason', 'global_active_lease_limit',
      'retryAfterSeconds', 30
    );
  end if;

  select
    count(*)::integer,
    coalesce(sum(declared_sandbox_seconds), 0)::integer
  into global_starts, global_seconds
  from public.code_guardrail_receipts
  where code_guardrail_receipts.budget_day = current_budget_day
    and receipt_kind = 'model_start';

  if global_starts >= guardrails.global_daily_model_start_limit then
    return jsonb_build_object(
      'claimed', false,
      'deferred', true,
      'reason', 'global_daily_model_start_limit',
      'retryAfterSeconds', retry_after_midnight
    );
  end if;

  -- Pick the least-recently-served eligible account first. A user with an
  -- active lease or exhausted daily budget is skipped so another account can
  -- make progress instead of sitting behind it.
  select task.id, task.user_id
  into candidate_id, candidate_user_id
  from public.code_tasks as task
  where task.status in ('queued', 'provisioning', 'running', 'verifying')
    and task.usage_receipt is not null
    and task.next_attempt_at <= now()
    and task.expires_at > now()
    and (
      task.lease_token is null
      or task.lease_expires_at is null
      or task.lease_expires_at < now()
    )
    and not exists (
      select 1
      from public.code_tasks as active
      where active.user_id = task.user_id
        and active.id <> task.id
        and active.status in ('provisioning', 'running', 'verifying')
        and active.lease_token is not null
        and active.lease_expires_at > now()
    )
    and (
      select count(*)
      from public.code_guardrail_receipts as user_receipt
      where user_receipt.user_id = task.user_id
        and user_receipt.budget_day = current_budget_day
        and user_receipt.receipt_kind = 'model_start'
    ) < guardrails.user_daily_model_start_limit
    and (
      select coalesce(sum(user_receipt.declared_sandbox_seconds), 0)
      from public.code_guardrail_receipts as user_receipt
      where user_receipt.user_id = task.user_id
        and user_receipt.budget_day = current_budget_day
        and user_receipt.receipt_kind = 'model_start'
    ) + task.max_duration_seconds <= guardrails.user_daily_sandbox_seconds
  order by
    (
      select max(served.created_at)
      from public.code_guardrail_receipts as served
      where served.user_id = task.user_id
        and served.receipt_kind = 'model_start'
    ) asc nulls first,
    task.next_attempt_at asc,
    task.created_at asc,
    task.id asc
  limit 1;

  if not found then
    if exists (
      select 1
      from public.code_tasks as waiting
      where waiting.status in ('queued', 'provisioning', 'running', 'verifying')
        and waiting.usage_receipt is not null
        and waiting.next_attempt_at <= now()
        and waiting.expires_at > now()
        and (
          waiting.lease_token is null
          or waiting.lease_expires_at is null
          or waiting.lease_expires_at < now()
        )
    ) then
      return jsonb_build_object(
        'claimed', false,
        'deferred', true,
        'reason', 'user_daily_compute_limit',
        'retryAfterSeconds', retry_after_midnight
      );
    end if;
    return jsonb_build_object('claimed', false, 'deferred', false, 'reason', 'no_work');
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    8274,
    pg_catalog.hashtext(candidate_user_id::text)
  );

  select *
  into candidate
  from public.code_tasks
  where id = candidate_id
    and user_id = candidate_user_id
    and status in ('queued', 'provisioning', 'running', 'verifying')
    and usage_receipt is not null
    and next_attempt_at <= now()
    and expires_at > now()
    and (
      lease_token is null
      or lease_expires_at is null
      or lease_expires_at < now()
    )
  for update skip locked;

  if not found then
    return jsonb_build_object(
      'claimed', false,
      'deferred', true,
      'reason', 'candidate_changed',
      'retryAfterSeconds', 1
    );
  end if;

  if exists (
    select 1
    from public.code_tasks as active
    where active.user_id = candidate.user_id
      and active.id <> candidate.id
      and active.status in ('provisioning', 'running', 'verifying')
      and active.lease_token is not null
      and active.lease_expires_at > now()
  ) then
    return jsonb_build_object(
      'claimed', false,
      'deferred', true,
      'reason', 'user_active_lease_limit',
      'retryAfterSeconds', 30
    );
  end if;

  select
    count(*)::integer,
    coalesce(sum(declared_sandbox_seconds), 0)::integer
  into user_starts, user_seconds
  from public.code_guardrail_receipts
  where user_id = candidate.user_id
    and code_guardrail_receipts.budget_day = current_budget_day
    and receipt_kind = 'model_start';

  declared_seconds := candidate.max_duration_seconds;
  next_attempt := candidate.attempt_count + 1;

  if user_starts >= guardrails.user_daily_model_start_limit
     or user_seconds + declared_seconds > guardrails.user_daily_sandbox_seconds then
    return jsonb_build_object(
      'claimed', false,
      'deferred', true,
      'reason', 'user_daily_compute_limit',
      'retryAfterSeconds', retry_after_midnight
    );
  end if;

  if global_seconds + declared_seconds > guardrails.global_daily_sandbox_seconds then
    return jsonb_build_object(
      'claimed', false,
      'deferred', true,
      'reason', 'global_daily_sandbox_seconds',
      'retryAfterSeconds', retry_after_midnight
    );
  end if;

  update public.code_tasks
  set status = 'provisioning',
      lease_token = p_claim_token,
      lease_expires_at = now() + make_interval(
        secs => greatest(60, least(300, p_lease_seconds))
      ),
      attempt_count = next_attempt,
      failure_code = null,
      started_at = coalesce(started_at, now()),
      updated_at = now()
  where id = candidate.id
  returning * into claimed;

  insert into public.code_guardrail_receipts (
    task_id,
    user_id,
    budget_day,
    receipt_kind,
    attempt_number,
    declared_sandbox_seconds
  )
  values (
    claimed.id,
    claimed.user_id,
    current_budget_day,
    'model_start',
    next_attempt,
    declared_seconds
  );

  return jsonb_build_object(
    'claimed', true,
    'replayed', false,
    'task', to_jsonb(claimed),
    'guardrailReceipt', jsonb_build_object(
      'kind', 'model_start',
      'budgetDay', current_budget_day,
      'attempt', next_attempt,
      'declaredSandboxSeconds', declared_seconds
    )
  );
end;
$$;

revoke all on function public.claim_code_task_guarded(integer, uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.claim_code_task_guarded(integer, uuid)
  to service_role;

-- The unguarded claim boundary must fail closed after this migration.
revoke all on function public.claim_code_task(integer, uuid) from service_role;

comment on table public.code_guardrail_limits is
  'Private fixed Autonomous Crump queue, concurrency, and UTC-day compute limits. Changes require a reviewed database migration.';

comment on table public.code_guardrail_receipts is
  'Content-free private Autonomous Crump acceptance and model-start budget receipts. No prompts, source URLs, paths, output, provider tokens, or customer content.';

comment on function public.create_code_task_guarded(
  uuid, uuid, text, text, text, text, integer
) is
  'Service-role-only atomic queue admission for one owner-scoped Autonomous Crump task.';

comment on function public.accept_code_task_run(
  uuid, uuid, uuid, text, integer, integer, text, integer
) is
  'Service-role-only replay-safe Autonomous Crump guardrail, allowance or credit, and dispatch transaction.';

comment on function public.claim_code_task_guarded(integer, uuid) is
  'Service-role-only fair lease claim with global and per-user active, UTC-day model-start, and declared Sandbox-second budgets.';

commit;
