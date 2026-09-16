-- Autonomous Crump atomic acceptance boundary.
--
-- A run is not claimable until one short database transaction has locked the
-- owner-scoped task, verified its immutable source revision, consumed either
-- the included allowance or the exact confirmed credit spend, persisted the
-- private dispatch owner and billing receipt, and appended one claimed event.

begin;

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

  select *
  into candidate
  from public.code_tasks
  where id = p_task_id
    and user_id = p_user_id
  for update;

  if not found then
    return jsonb_build_object('accepted', false, 'reason', 'task_not_ready');
  end if;

  select lower(coalesce(account.internal_tier, '')) in ('professional', 'enterprise')
  into internal_access
  from public.users as account
  where account.id = p_user_id
    and account.deleted_at is null;

  if not found then
    return jsonb_build_object('accepted', false, 'reason', 'task_not_ready');
  end if;

  -- PostgREST may lose a committed response. The exact private owner token
  -- replays the retained result without another allowance event or deduction.
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
      credits_spent = greatest(0, least(100000, coalesce((receipt ->> 'creditsSpent')::integer, 0))),
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
    jsonb_build_object(
      'status', 'provisioning',
      'mode', dispatched.mode
    )
  );

  return jsonb_build_object(
    'accepted', true,
    'replayed', false,
    'task', to_jsonb(dispatched)
  );
end;
$$;

revoke all on function public.accept_code_task_run(
  uuid, uuid, uuid, text, integer, integer, text, integer
) from public, anon, authenticated, service_role;
grant execute on function public.accept_code_task_run(
  uuid, uuid, uuid, text, integer, integer, text, integer
) to service_role;

-- The preceding two-step application boundary must fail closed after this
-- migration. Only the atomic acceptance function may make a task claimable.
revoke all on function public.dispatch_code_task(uuid, uuid, uuid, jsonb, text, integer)
  from service_role;

comment on function public.accept_code_task_run(
  uuid, uuid, uuid, text, integer, integer, text, integer
) is
  'Service-role-only replay-safe Autonomous Crump allowance/credit consumption and worker dispatch transaction.';

comment on function public.dispatch_code_task(uuid, uuid, uuid, jsonb, text, integer) is
  'Legacy non-atomic Autonomous Crump dispatch boundary; execution revoked after atomic acceptance shipped.';

commit;
