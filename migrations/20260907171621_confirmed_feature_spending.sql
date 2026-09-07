-- Ask Crump credit-charge disclosure trust gate.
-- Adds an idempotent, explicitly confirmed feature-spend boundary and a
-- durable maximum for asynchronous manuscript generation. This migration is
-- staged separately from the Word/PDF guide release.

begin;

alter table public.manuscript_runs
  add column if not exists approved_credit_limit integer not null default 0
    check (approved_credit_limit >= 0),
  add column if not exists credits_spent integer not null default 0
    check (credits_spent >= 0),
  add column if not exists planned_steps integer not null default 0
    check (planned_steps >= 0),
  add column if not exists planned_chargeable_steps integer not null default 0
    check (planned_chargeable_steps >= 0),
  add column if not exists credit_per_step integer not null default 8
    check (credit_per_step > 0),
  add column if not exists credit_action_key text;

alter table public.manuscript_runs
  drop constraint if exists manuscript_runs_credit_budget_check,
  add constraint manuscript_runs_credit_budget_check
    check (credits_spent <= approved_credit_limit),
  drop constraint if exists manuscript_runs_chargeable_steps_check,
  add constraint manuscript_runs_chargeable_steps_check
    check (planned_chargeable_steps <= planned_steps);

-- Runs created before this disclosure boundary have no explicit maximum.
-- Pause them without charging; the owner can review a fresh quote to resume.
update public.manuscript_runs
set status = 'paused',
    lease_token = null,
    lease_expires_at = null,
    last_error_code = 'CREDIT_BUDGET_CONFIRMATION_REQUIRED',
    last_error_message = 'Review and approve the remaining manuscript credit maximum before this run continues.',
    updated_at = now()
where mode = 'autopilot'
  and status in ('queued', 'running', 'paused', 'awaiting_credits')
  and approved_credit_limit = 0;

create or replace function public.spend_credits_confirmed(
  p_user_id uuid,
  p_amount integer,
  p_reason text,
  p_action_key text,
  p_component text,
  p_confirmed_max integer,
  p_metadata jsonb default '{}'::jsonb
)
returns table(
  ledger_id uuid,
  balance bigint,
  allowed boolean,
  duplicate boolean,
  limit_exceeded boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  normalized_action text;
  normalized_component text;
  external_key text;
  existing public.credit_ledger%rowtype;
  current_balance bigint;
  new_balance bigint;
  inserted_id uuid;
  action_spent bigint;
begin
  if p_user_id is null then
    raise exception 'Credit spend user is required' using errcode = '22023';
  end if;
  if p_amount is null or p_amount <= 0 then
    raise exception 'Credit spend amount must be positive' using errcode = '22023';
  end if;
  if p_confirmed_max is null or p_confirmed_max <= 0
     or p_amount > p_confirmed_max then
    raise exception 'Confirmed credit maximum is invalid' using errcode = '22023';
  end if;

  normalized_action := left(trim(coalesce(p_action_key, '')), 160);
  normalized_component := left(trim(coalesce(p_component, '')), 120);
  if normalized_action = '' or normalized_component = '' then
    raise exception 'Confirmed credit action and component are required'
      using errcode = '22023';
  end if;
  external_key := normalized_action || ':' || normalized_component;

  perform pg_advisory_xact_lock(
    hashtextextended('credits:' || p_user_id::text, 0)
  );

  insert into public.credit_accounts (user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  select *
  into existing
  from public.credit_ledger
  where user_id = p_user_id
    and provider = 'feature-spend'
    and external_id = external_key
  limit 1;

  if found then
    select account.balance
    into current_balance
    from public.credit_accounts as account
    where account.user_id = p_user_id;

    -- A refunded provider attempt must not make its old approval reusable.
    -- The refund RPC takes the same per-account advisory lock, so this check
    -- is serialized with both deductions and refunds.
    if exists (
      select 1
      from public.credit_ledger as refund
      where refund.user_id = p_user_id
        and refund.related_ledger_id = existing.id
        and refund.reason = 'refund'
    ) then
      return query
        select null::uuid, coalesce(current_balance, 0), false, false, true;
      return;
    end if;

    return query
      select existing.id, coalesce(current_balance, 0), true, true, false;
    return;
  end if;

  select coalesce(sum(-ledger.delta), 0)
  into action_spent
  from public.credit_ledger as ledger
  where ledger.user_id = p_user_id
    and ledger.provider = 'feature-spend'
    and ledger.delta < 0
    and ledger.metadata ->> 'creditActionKey' = normalized_action;

  if action_spent + p_amount > p_confirmed_max then
    select account.balance
    into current_balance
    from public.credit_accounts as account
    where account.user_id = p_user_id;

    return query
      select null::uuid, coalesce(current_balance, 0), false, false, true;
    return;
  end if;

  select account.balance
  into current_balance
  from public.credit_accounts as account
  where account.user_id = p_user_id
  for update;

  if coalesce(current_balance, 0) < p_amount then
    return query
      select null::uuid, coalesce(current_balance, 0), false, false, false;
    return;
  end if;

  new_balance := current_balance - p_amount;

  update public.credit_accounts as account
  set balance = new_balance,
      lifetime_spent = account.lifetime_spent + p_amount,
      updated_at = now()
  where account.user_id = p_user_id;

  insert into public.credit_ledger (
    user_id,
    delta,
    balance_after,
    reason,
    provider,
    external_id,
    metadata
  )
  values (
    p_user_id,
    -p_amount,
    new_balance,
    coalesce(nullif(trim(p_reason), ''), 'confirmed_feature_spend'),
    'feature-spend',
    external_key,
    coalesce(p_metadata, '{}'::jsonb)
      || jsonb_build_object(
        'creditActionKey', normalized_action,
        'creditComponent', normalized_component,
        'confirmedMaximum', p_confirmed_max,
        'confirmedBoundary', true
      )
  )
  returning id into inserted_id;

  return query select inserted_id, new_balance, true, false, false;
end;
$$;

revoke all on function public.spend_credits_confirmed(
  uuid, integer, text, text, text, integer, jsonb
) from public, anon, authenticated;
grant execute on function public.spend_credits_confirmed(
  uuid, integer, text, text, text, integer, jsonb
) to service_role;

-- The application has no remaining caller for the legacy unconfirmed spend
-- RPC. Revoking it makes the migration-to-deploy window and any code rollback
-- fail closed instead of restoring silent credit deductions.
revoke all on function public.spend_credits(
  uuid, integer, text, jsonb
) from service_role;

comment on function public.spend_credits_confirmed(
  uuid, integer, text, text, text, integer, jsonb
) is
  'Service-role-only idempotent deduction bounded by an exact user-confirmed action maximum.';
comment on function public.spend_credits(
  uuid, integer, text, jsonb
) is
  'Legacy unconfirmed spend boundary; execution revoked after exact action-time confirmation shipped.';

comment on column public.manuscript_runs.approved_credit_limit is
  'Maximum paid credits explicitly approved for this durable run.';
comment on column public.manuscript_runs.credits_spent is
  'Paid credits deducted inside the run; included allowance is not counted.';

commit;
