-- Code-only billing and provider admission. Generated with `supabase migration new`.
-- No prompts or provider credentials are stored. USD amounts are integer millionths.
-- Deploy with Code disabled. Older application dispatch fails closed after this
-- migration; deploy the atomic-dispatch application before any activation.
begin;

alter table public.code_tasks
  add column if not exists provider_started_at timestamptz,
  add column if not exists provider_execution_lease_token uuid,
  add column if not exists provider_budget_policy jsonb;

create or replace function public.code_budget_policy_valid(p jsonb)
returns boolean language plpgsql immutable set search_path = '' as $$
declare k text;
begin
  if p is null or pg_catalog.jsonb_typeof(p) <> 'object'
     or (select count(*) from pg_catalog.jsonb_object_keys(p)) <> 9
     or pg_catalog.jsonb_typeof(p->'model') <> 'string'
     or coalesce(p->>'model', '') !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{1,119}$' then
    return false;
  end if;
  foreach k in array array['input_rate','output_rate','max_input_bytes','max_output_tokens',
                          'call_limit','run_limit','account_daily_limit','global_daily_limit'] loop
    if pg_catalog.jsonb_typeof(p->k) <> 'number' or p->>k !~ '^[1-9][0-9]{0,12}$'
       or (p->>k)::numeric > 1000000000000 then return false; end if;
    if p->k is null then return false; end if;
  end loop;
  return (p->>'max_input_bytes')::bigint <= 2000000
     and (p->>'max_output_tokens')::bigint <= 16384
     and (p->>'call_limit')::bigint <= (p->>'run_limit')::bigint
     and (p->>'run_limit')::bigint <= (p->>'account_daily_limit')::bigint
     and (p->>'account_daily_limit')::bigint <= (p->>'global_daily_limit')::bigint;
end;
$$;
revoke all on function public.code_budget_policy_valid(jsonb) from public, anon, authenticated;

create table public.code_provider_call_reservations (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.code_tasks(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  call_key text not null check (call_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$'),
  request_sha256 text not null check (request_sha256 ~ '^[0-9a-f]{64}$'),
  lease_token uuid not null,
  policy jsonb not null check (public.code_budget_policy_valid(policy)),
  reserved_micros bigint not null check (reserved_micros between 1 and 1000000000000),
  input_ceiling integer not null check (input_ceiling between 4097 and 2004096),
  output_ceiling integer not null check (output_ceiling between 1 and 16384),
  status text not null default 'reserved' check (status in ('reserved','started','settled','uncertain','released')),
  actual_micros bigint check (actual_micros between 0 and 5000000000000000),
  budget_day date not null,
  created_at timestamptz not null default clock_timestamp(),
  expires_at timestamptz not null,
  started_at timestamptz,
  settled_at timestamptz,
  unique (task_id, call_key)
);
create index code_provider_budget_day_idx on public.code_provider_call_reservations(budget_day, user_id);
alter table public.code_provider_call_reservations enable row level security;
alter table public.code_provider_call_reservations force row level security;
revoke all on table public.code_provider_call_reservations from public, anon, authenticated, service_role;

-- Daily admission cannot depend on rows that privacy/account/project deletion
-- legitimately cascades away. Global totals contain NO account/task identity.
-- Account totals survive task deletion and disappear with the account itself.
create table public.code_provider_global_daily (
  budget_day date primary key,
  held_micros numeric(38,0) not null check (held_micros >= 0),
  strictest_cap_micros bigint not null check (strictest_cap_micros between 1 and 1000000000000),
  updated_at timestamptz not null default clock_timestamp()
);
create table public.code_provider_account_daily (
  user_id uuid not null references public.users(id) on delete cascade,
  budget_day date not null,
  held_micros numeric(38,0) not null check (held_micros >= 0),
  strictest_cap_micros bigint not null check (strictest_cap_micros between 1 and 1000000000000),
  updated_at timestamptz not null default clock_timestamp(),
  primary key (user_id,budget_day)
);
alter table public.code_provider_global_daily enable row level security;
alter table public.code_provider_global_daily force row level security;
alter table public.code_provider_account_daily enable row level security;
alter table public.code_provider_account_daily force row level security;
revoke all on table public.code_provider_global_daily,public.code_provider_account_daily
  from public,anon,authenticated,service_role;

create or replace function public.code_provider_held_micros(p_status text,p_reserved bigint,p_actual bigint)
returns numeric language sql immutable set search_path = '' as $$
  select case when p_status='released' then 0::numeric when p_status='settled' then p_actual::numeric
    else greatest(p_reserved,coalesce(p_actual,0))::numeric end
$$;
revoke all on function public.code_provider_held_micros(text,bigint,bigint) from public,anon,authenticated,service_role;

create or replace function public.guard_code_provider_admission_identity()
returns trigger language plpgsql set search_path = '' as $$
begin
  if row(new.id,new.task_id,new.user_id,new.call_key,new.request_sha256,new.policy,new.reserved_micros,
         new.input_ceiling,new.output_ceiling,new.budget_day)
     is distinct from row(old.id,old.task_id,old.user_id,old.call_key,old.request_sha256,old.policy,old.reserved_micros,
                          old.input_ceiling,old.output_ceiling,old.budget_day) then
    raise exception 'Code provider admission identity is immutable' using errcode='22023';
  end if;
  return new;
end;
$$;
revoke all on function public.guard_code_provider_admission_identity() from public,anon,authenticated,service_role;
create trigger guard_code_provider_admission_identity before update on public.code_provider_call_reservations
  for each row execute function public.guard_code_provider_admission_identity();

create or replace function public.account_code_provider_daily()
returns trigger language plpgsql security definer set search_path = '' as $$
declare held numeric; delta numeric;
begin
  held := public.code_provider_held_micros(new.status,new.reserved_micros,new.actual_micros);
  if tg_op='INSERT' then
    insert into public.code_provider_global_daily as daily(budget_day,held_micros,strictest_cap_micros)
      values(new.budget_day,held,(new.policy->>'global_daily_limit')::bigint)
      on conflict(budget_day) do update set held_micros=daily.held_micros+excluded.held_micros,
        strictest_cap_micros=least(daily.strictest_cap_micros,excluded.strictest_cap_micros),updated_at=clock_timestamp();
    insert into public.code_provider_account_daily as daily(user_id,budget_day,held_micros,strictest_cap_micros)
      values(new.user_id,new.budget_day,held,(new.policy->>'account_daily_limit')::bigint)
      on conflict(user_id,budget_day) do update set held_micros=daily.held_micros+excluded.held_micros,
        strictest_cap_micros=least(daily.strictest_cap_micros,excluded.strictest_cap_micros),updated_at=clock_timestamp();
  else
    delta := held-public.code_provider_held_micros(old.status,old.reserved_micros,old.actual_micros);
    update public.code_provider_global_daily set held_micros=held_micros+delta,updated_at=clock_timestamp()
      where budget_day=new.budget_day;
    if not found then raise exception 'Code global accounting unavailable'; end if;
    update public.code_provider_account_daily set held_micros=held_micros+delta,updated_at=clock_timestamp()
      where user_id=new.user_id and budget_day=new.budget_day;
    if not found then raise exception 'Code account accounting unavailable'; end if;
  end if;
  -- No DELETE trigger: cascades retain the global hold/spend and cap minimum.
  -- Do not acquire global locks from a row trigger after cascade/task locks;
  -- the admitted INSERT/UPDATE RPCs already hold global -> account -> task.
  return new;
end;
$$;
revoke all on function public.account_code_provider_daily() from public,anon,authenticated,service_role;
create trigger account_code_provider_daily after insert or update on public.code_provider_call_reservations
  for each row execute function public.account_code_provider_daily();

-- All provider accounting mutations use one fixed global -> account -> user -> task ->
-- reservation order. The deliberately conservative global lock crosses UTC-day
-- boundaries; there is no midnight race or floating-point admission arithmetic.
create or replace function public.code_provider_budget_lock(p_user_id uuid)
returns void language plpgsql set search_path = '' as $$
begin
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('code-provider-global:v1', 0));
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('code-provider-account:' || p_user_id::text, 0));
end;
$$;
revoke all on function public.code_provider_budget_lock(uuid) from public, anon, authenticated, service_role;

create or replace function public.reserve_and_dispatch_code_task(
  p_task_id uuid, p_user_id uuid, p_dispatch_token uuid, p_included_limit integer,
  p_credit_cost integer, p_confirmed_max integer, p_action_key text,
  p_bypass_source text, p_budget_policy jsonb
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  t public.code_tasks%rowtype;
  u record; c record;
  receipt jsonb; source text; credit_amount integer := 0;
  usage_key text := 'code-task:' || p_task_id::text;
begin
  -- Lock the user before its child task, matching account-deletion FK ordering.
  -- This avoids parent DELETE waiting for a task while INSERT waits for its user.
  perform 1 from public.users where id=p_user_id for key share;
  select * into t from public.code_tasks where id=p_task_id and user_id=p_user_id for update;
  if not found then return jsonb_build_object('outcome','denied','code','CODE_TASK_NOT_FOUND'); end if;
  if t.dispatch_token is not null then
    return jsonb_build_object('outcome','replay','task',to_jsonb(t));
  end if;
  if t.status <> 'queued' or t.expires_at <= clock_timestamp() or p_dispatch_token is null
     or not public.code_budget_policy_valid(p_budget_policy)
     or p_included_limit is null or p_included_limit < -1
     or p_credit_cost is null or p_credit_cost not between 0 and 100000
     or p_confirmed_max is null or p_confirmed_max not between 0 and 100000
     or coalesce(length(trim(p_action_key)),0) not between 1 and 160 then
    return jsonb_build_object('outcome','denied','code','CODE_TASK_CONFLICT');
  end if;
  if p_bypass_source is not null then
    if p_bypass_source not in ('internal','subscription') or p_included_limit <> -1 then
      return jsonb_build_object('outcome','denied','code','CODE_TASK_CONFLICT');
    end if;
    source := p_bypass_source;
    receipt := jsonb_build_object('feature','code_workspace','eventId',null,'paymentSource',source,'creditsSpent',0);
  else
    if p_included_limit < 0 then return jsonb_build_object('outcome','denied','code','CODE_TASK_CONFLICT'); end if;
    select * into u from public.consume_usage_event_v2(p_user_id,'feature:code_workspace',p_included_limit,
      jsonb_build_object('usageIdempotencyKey',usage_key,'route','code_task','mode',t.mode,'taskId',t.id));
    if u.allowed then
      source := 'included';
      receipt := jsonb_build_object('feature','code_workspace','eventId',u.event_id::text,
        'paymentSource',source,'creditsSpent',0);
    else
      if p_credit_cost <= 0 or p_confirmed_max < p_credit_cost then
        return jsonb_build_object('outcome','denied','code','CREDIT_CONFIRMATION_REQUIRED');
      end if;
      select * into c from public.spend_credits_confirmed_v2(p_user_id,p_credit_cost,
        'feature:code_workspace',p_action_key,'code_workspace',p_confirmed_max,
        'feature:code_workspace',usage_key,jsonb_build_object('route','code_task','mode',t.mode,'taskId',t.id));
      if not c.allowed then
        return jsonb_build_object('outcome','denied','code',case when c.limit_exceeded then 'CREDIT_CONFIRMATION_REQUIRED' else 'CREDITS_REQUIRED' end);
      end if;
      source := 'credits';
      -- Use the original ledger amount even on an idempotent v2 reconciliation.
      select (-delta)::integer into credit_amount from public.credit_ledger where id=c.ledger_id and user_id=p_user_id;
      if credit_amount is null or credit_amount <= 0 then raise exception 'Code spend receipt unavailable'; end if;
      receipt := jsonb_build_object('feature','code_workspace','eventId','credit:' || c.ledger_id::text,
        'paymentSource',source,'creditsSpent',credit_amount);
    end if;
  end if;
  update public.code_tasks set status='provisioning',dispatch_token=p_dispatch_token,
    usage_receipt=receipt,payment_source=source,credits_spent=credit_amount,
    provider_budget_policy=p_budget_policy,started_at=coalesce(started_at,clock_timestamp()),
    next_attempt_at=clock_timestamp(),updated_at=clock_timestamp(),failure_code=null
    where id=t.id returning * into t;
  insert into public.code_task_events(task_id,user_id,project_id,event_type,payload)
    values(t.id,t.user_id,t.project_id,'task.claimed','{"status":"provisioning"}');
  return jsonb_build_object('outcome','dispatched','task',to_jsonb(t));
end;
$$;

create or replace function public.reserve_code_provider_call(
  p_task_id uuid, p_user_id uuid, p_lease_token uuid, p_call_key text,
  p_request_sha256 text, p_reserved_micros bigint, p_input_ceiling integer,
  p_output_ceiling integer, p_policy jsonb
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  t public.code_tasks%rowtype; r public.code_provider_call_reservations%rowtype;
  n timestamptz; d date; estimated numeric;
  run_used numeric; account_used numeric; global_used numeric;
  account_cap bigint; global_cap bigint;
begin
  perform public.code_provider_budget_lock(p_user_id);
  perform 1 from public.users where id=p_user_id for key share;
  select * into t from public.code_tasks where id=p_task_id and user_id=p_user_id for update;
  n := clock_timestamp(); d := (n at time zone 'UTC')::date;
  if t.id is null or p_lease_token is null or t.lease_token is distinct from p_lease_token
     or t.lease_expires_at is null or t.lease_expires_at <= n or t.expires_at <= n
     or t.status <> 'running' or t.cancel_requested_at is not null or t.dispatch_token is null
     or (t.provider_execution_lease_token is not null and t.provider_execution_lease_token <> p_lease_token) then
    return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_LEASE_CONFLICT');
  end if;
  if not public.code_budget_policy_valid(p_policy) or p_policy is distinct from t.provider_budget_policy
     or coalesce(p_call_key,'') !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$'
     or coalesce(p_request_sha256,'') !~ '^[0-9a-f]{64}$'
     or p_input_ceiling is null or p_input_ceiling < 4097 or p_input_ceiling > (p_policy->>'max_input_bytes')::int+4096
     or p_output_ceiling is null or p_output_ceiling < 1 or p_output_ceiling > (p_policy->>'max_output_tokens')::int then
    return jsonb_build_object('outcome','denied','code','CODE_BUDGET_POLICY_CONFLICT');
  end if;
  estimated := ceil((p_input_ceiling::numeric*(p_policy->>'input_rate')::numeric+
                         p_output_ceiling::numeric*(p_policy->>'output_rate')::numeric)/1000000);
  if p_reserved_micros is null or p_reserved_micros <> estimated or estimated <= 0
     or estimated > (p_policy->>'call_limit')::bigint then
    return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_BUDGET_EXHAUSTED');
  end if;
  select * into r from public.code_provider_call_reservations where task_id=t.id and call_key=p_call_key for update;
  if found then
    if r.request_sha256 <> p_request_sha256 or r.policy <> p_policy
       or r.reserved_micros <> p_reserved_micros or r.input_ceiling <> p_input_ceiling
       or r.output_ceiling <> p_output_ceiling then
      return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_CALL_CONFLICT');
    end if;
    if r.status <> 'reserved' then
      return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_OUTCOME_UNCERTAIN');
    end if;
    if r.budget_day <> d then
      return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_DAY_CONFLICT');
    end if;
    -- Before the first provider begin, an expired worker may safely hand an
    -- identical unused reservation to its replacement lease. No POST occurred.
    update public.code_provider_call_reservations set lease_token=p_lease_token,expires_at=t.lease_expires_at
      where id=r.id returning * into r;
    return jsonb_build_object('outcome','reserved_replay','reservation',to_jsonb(r));
  end if;
  if exists(select 1 from public.code_provider_call_reservations where task_id=t.id and status in ('started','uncertain')) then
    return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_OUTCOME_UNCERTAIN');
  end if;
  select coalesce(sum(case when status='released' then 0 when status='settled' then actual_micros
    else greatest(reserved_micros,coalesce(actual_micros,0)) end),0)
    into run_used from public.code_provider_call_reservations where task_id=t.id;
  select held_micros,least((p_policy->>'account_daily_limit')::bigint,strictest_cap_micros)
    into account_used,account_cap from public.code_provider_account_daily where user_id=p_user_id and budget_day=d;
  account_used := coalesce(account_used,0);
  account_cap := coalesce(account_cap,(p_policy->>'account_daily_limit')::bigint);
  select held_micros,least((p_policy->>'global_daily_limit')::bigint,strictest_cap_micros)
    into global_used,global_cap from public.code_provider_global_daily where budget_day=d;
  global_used := coalesce(global_used,0);
  global_cap := coalesce(global_cap,(p_policy->>'global_daily_limit')::bigint);
  if run_used+estimated > (p_policy->>'run_limit')::bigint
     or account_used+estimated > account_cap or global_used+estimated > global_cap then
    return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_BUDGET_EXHAUSTED');
  end if;
  insert into public.code_provider_call_reservations(task_id,user_id,call_key,request_sha256,lease_token,
    policy,reserved_micros,input_ceiling,output_ceiling,budget_day,expires_at)
    values(t.id,p_user_id,p_call_key,p_request_sha256,p_lease_token,p_policy,p_reserved_micros,
      p_input_ceiling,p_output_ceiling,d,t.lease_expires_at) returning * into r;
  return jsonb_build_object('outcome','reserved','reservation',to_jsonb(r));
end;
$$;

create or replace function public.begin_code_provider_call(
  p_task_id uuid, p_user_id uuid, p_lease_token uuid, p_reservation_id uuid
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare t public.code_tasks%rowtype; r public.code_provider_call_reservations%rowtype; n timestamptz;
begin
  perform public.code_provider_budget_lock(p_user_id);
  perform 1 from public.users where id=p_user_id for key share;
  select * into t from public.code_tasks where id=p_task_id and user_id=p_user_id for update;
  select * into r from public.code_provider_call_reservations where id=p_reservation_id and task_id=p_task_id and user_id=p_user_id for update;
  n := clock_timestamp();
  if t.id is null or r.id is null or p_lease_token is null or t.lease_token is distinct from p_lease_token
     or r.lease_token <> p_lease_token or t.status <> 'running' or t.cancel_requested_at is not null
     or t.lease_expires_at is null or t.lease_expires_at <= n or t.expires_at <= n
     or r.expires_at <= n or r.budget_day <> (n at time zone 'UTC')::date
     or r.policy is distinct from t.provider_budget_policy
     or (t.provider_execution_lease_token is not null and t.provider_execution_lease_token <> p_lease_token) then
    return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_LEASE_CONFLICT');
  end if;
  if r.status <> 'reserved' then return jsonb_build_object('outcome','already_started','reservation',to_jsonb(r)); end if;
  update public.code_provider_call_reservations set status='started',started_at=n where id=r.id returning * into r;
  update public.code_tasks set provider_started_at=coalesce(provider_started_at,n),
    provider_execution_lease_token=coalesce(provider_execution_lease_token,p_lease_token),updated_at=n where id=t.id;
  return jsonb_build_object('outcome','started','reservation',to_jsonb(r));
end;
$$;

create or replace function public.settle_code_provider_call(
  p_task_id uuid, p_user_id uuid, p_lease_token uuid, p_reservation_id uuid,
  p_actual_micros bigint, p_uncertain boolean
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare t public.code_tasks%rowtype; r public.code_provider_call_reservations%rowtype; target text;
begin
  perform public.code_provider_budget_lock(p_user_id);
  perform 1 from public.users where id=p_user_id for key share;
  select * into t from public.code_tasks where id=p_task_id and user_id=p_user_id for update;
  select * into r from public.code_provider_call_reservations where id=p_reservation_id and task_id=p_task_id and user_id=p_user_id for update;
  if t.id is null or r.id is null or p_lease_token is null or r.lease_token <> p_lease_token then
    return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_LEASE_CONFLICT');
  end if;
  if p_actual_micros is not null and (p_actual_micros < 0 or p_actual_micros > 5000000000000000) then
    return jsonb_build_object('outcome','denied','code','CODE_BUDGET_REQUEST_INVALID');
  end if;
  target := case when coalesce(p_uncertain,true) or p_actual_micros is null or p_actual_micros > r.reserved_micros then 'uncertain' else 'settled' end;
  -- A late usage response may follow lease reconciliation. Record additional
  -- known cost monotonically, but never downgrade uncertainty or free its hold.
  if r.status='uncertain' and p_actual_micros is not null
     and (r.actual_micros is null or p_actual_micros>r.actual_micros) then
    update public.code_provider_call_reservations set actual_micros=p_actual_micros
      where id=r.id returning * into r;
    return jsonb_build_object('outcome','uncertain','reservation',to_jsonb(r));
  end if;
  if r.status in ('settled','uncertain') then
    if (r.status=target or r.status='uncertain') and r.actual_micros is not distinct from p_actual_micros then
      return jsonb_build_object('outcome','settled_replay','reservation',to_jsonb(r));
    end if;
    return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_CALL_CONFLICT');
  end if;
  if r.status <> 'started' then return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_CALL_CONFLICT'); end if;
  update public.code_provider_call_reservations set status=target,actual_micros=p_actual_micros,settled_at=clock_timestamp()
    where id=r.id returning * into r;
  -- Settlement is allowed after cancellation/lease expiry for the ORIGINAL
  -- reservation owner. Already-incurred cost must remain accountable.
  return jsonb_build_object('outcome',target,'reservation',to_jsonb(r));
end;
$$;

create or replace function public.release_code_provider_call(
  p_task_id uuid, p_user_id uuid, p_lease_token uuid, p_reservation_id uuid
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare t public.code_tasks%rowtype; r public.code_provider_call_reservations%rowtype;
begin
  perform public.code_provider_budget_lock(p_user_id);
  perform 1 from public.users where id=p_user_id for key share;
  select * into t from public.code_tasks where id=p_task_id and user_id=p_user_id for update;
  select * into r from public.code_provider_call_reservations where id=p_reservation_id and task_id=p_task_id and user_id=p_user_id for update;
  if t.id is null or r.id is null or p_lease_token is null or r.lease_token <> p_lease_token then
    return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_LEASE_CONFLICT');
  end if;
  if r.status not in ('reserved','released') then
    return jsonb_build_object('outcome','denied','code','CODE_PROVIDER_OUTCOME_UNCERTAIN');
  end if;
  update public.code_provider_call_reservations set status='released',settled_at=coalesce(settled_at,clock_timestamp())
    where id=r.id returning * into r;
  return jsonb_build_object('outcome','released','reservation',to_jsonb(r));
end;
$$;

create or replace function public.refund_code_task_if_unstarted(p_task_id uuid,p_user_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare t public.code_tasks%rowtype; event_key text;
begin
  perform public.code_provider_budget_lock(p_user_id);
  perform 1 from public.users where id=p_user_id for key share;
  select * into t from public.code_tasks where id=p_task_id and user_id=p_user_id for update;
  if not found then return jsonb_build_object('outcome','denied','code','CODE_TASK_NOT_FOUND'); end if;
  if t.status not in ('cancelled','failed') then
    return jsonb_build_object('outcome','not_terminal','task',to_jsonb(t));
  end if;
  -- Unused calls can be released even if an earlier call started; started or
  -- uncertain calls retain their full holds. No provider POST is replayed.
  update public.code_provider_call_reservations set status='released',settled_at=clock_timestamp()
    where task_id=t.id and status='reserved';
  if t.provider_started_at is not null then
    if t.payment_source='refund_pending' then
      update public.code_tasks set payment_source=coalesce(usage_receipt->>'paymentSource','provider_started'),updated_at=clock_timestamp()
        where id=t.id returning * into t;
    end if;
    return jsonb_build_object('outcome','provider_started','task',to_jsonb(t));
  end if;
  if t.payment_source='refunded' or t.usage_receipt is null then
    return jsonb_build_object('outcome','no_receipt','task',to_jsonb(t));
  end if;
  event_key := t.usage_receipt->>'eventId';
  if event_key like 'credit:%' then
    perform public.refund_credit_spend(t.user_id,substring(event_key from 8)::uuid,
      jsonb_build_object('reason','code_provider_not_started','taskId',t.id));
  elsif event_key is not null then
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('usage:' || p_user_id::text || ':feature:code_workspace',0));
    delete from public.usage_events where id=event_key::uuid and user_id=t.user_id
      and event_type='feature:code_workspace' and (
        idempotency_key='code-task:' || t.id::text
        or (t.provider_budget_policy is null and idempotency_key is null and metadata->>'feature'='code_workspace')
      );
    if not found then raise exception 'Code allowance receipt unavailable'; end if;
  elsif coalesce(t.usage_receipt->>'paymentSource','') not in ('internal','subscription') then
    raise exception 'Code refund receipt unavailable';
  end if;
  update public.code_tasks set usage_receipt=null,payment_source='refunded',credits_spent=0,updated_at=clock_timestamp()
    where id=t.id returning * into t;
  return jsonb_build_object('outcome','refunded','task',to_jsonb(t));
end;
$$;

-- A monotonic provider-begin marker must survive generic terminal transitions
-- and stale callers. A refund may only be written by the locked RPC above.
create or replace function public.guard_code_provider_begin()
returns trigger language plpgsql set search_path = '' as $$
begin
  if old.dispatch_token is not null then new.dispatch_token := old.dispatch_token; end if;
  if old.provider_started_at is not null then
    new.provider_started_at := old.provider_started_at;
    new.provider_execution_lease_token := old.provider_execution_lease_token;
    new.provider_budget_policy := old.provider_budget_policy;
    if new.payment_source in ('refunded','refund_pending') then
      new.payment_source := coalesce(old.usage_receipt->>'paymentSource',old.payment_source,'provider_started');
      new.usage_receipt := old.usage_receipt;
      new.credits_spent := old.credits_spent;
    end if;
  elsif old.dispatch_token is not null then
    new.provider_budget_policy := old.provider_budget_policy;
  end if;
  return new;
end;
$$;
revoke all on function public.guard_code_provider_begin() from public, anon, authenticated, service_role;
create trigger guard_code_provider_begin before update on public.code_tasks
  for each row execute function public.guard_code_provider_begin();

create or replace function public.reconcile_code_provider_lease(p_task_id uuid,p_user_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare t public.code_tasks%rowtype; n timestamptz;
begin
  perform public.code_provider_budget_lock(p_user_id);
  perform 1 from public.users where id=p_user_id for key share;
  select * into t from public.code_tasks where id=p_task_id and user_id=p_user_id for update;
  if not found then return jsonb_build_object('outcome','denied','code','CODE_TASK_NOT_FOUND'); end if;
  n := clock_timestamp();
  if t.provider_started_at is null or t.status not in ('provisioning','running','verifying')
     or (t.lease_expires_at is not null and t.lease_expires_at>n) then
    return jsonb_build_object('outcome','unchanged','task',to_jsonb(t));
  end if;
  update public.code_provider_call_reservations set status=case when status='reserved' then 'released' else 'uncertain' end,
    settled_at=coalesce(settled_at,n) where task_id=t.id and status in ('reserved','started');
  update public.code_tasks set status='failed',failure_code='CODE_PROVIDER_OUTCOME_UNCERTAIN',
    lease_token=null,lease_expires_at=null,completed_at=n,updated_at=n,
    payment_source=coalesce(usage_receipt->>'paymentSource',payment_source,'provider_started')
    where id=t.id returning * into t;
  insert into public.code_task_events(task_id,user_id,project_id,event_type,payload)
    values(t.id,t.user_id,t.project_id,'task.failed',
      '{"status":"failed","failureCode":"CODE_PROVIDER_OUTCOME_UNCERTAIN"}');
  return jsonb_build_object('outcome','failed_uncertain','task',to_jsonb(t));
end;
$$;

revoke all on function public.reserve_and_dispatch_code_task(uuid,uuid,uuid,integer,integer,integer,text,text,jsonb) from public,anon,authenticated;
revoke all on function public.reserve_code_provider_call(uuid,uuid,uuid,text,text,bigint,integer,integer,jsonb) from public,anon,authenticated;
revoke all on function public.begin_code_provider_call(uuid,uuid,uuid,uuid) from public,anon,authenticated;
revoke all on function public.settle_code_provider_call(uuid,uuid,uuid,uuid,bigint,boolean) from public,anon,authenticated;
revoke all on function public.release_code_provider_call(uuid,uuid,uuid,uuid) from public,anon,authenticated;
revoke all on function public.refund_code_task_if_unstarted(uuid,uuid) from public,anon,authenticated;
revoke all on function public.reconcile_code_provider_lease(uuid,uuid) from public,anon,authenticated;
grant execute on function public.reserve_and_dispatch_code_task(uuid,uuid,uuid,integer,integer,integer,text,text,jsonb) to service_role;
grant execute on function public.reserve_code_provider_call(uuid,uuid,uuid,text,text,bigint,integer,integer,jsonb) to service_role;
grant execute on function public.begin_code_provider_call(uuid,uuid,uuid,uuid) to service_role;
grant execute on function public.settle_code_provider_call(uuid,uuid,uuid,uuid,bigint,boolean) to service_role;
grant execute on function public.release_code_provider_call(uuid,uuid,uuid,uuid) to service_role;
grant execute on function public.refund_code_task_if_unstarted(uuid,uuid) to service_role;
grant execute on function public.reconcile_code_provider_lease(uuid,uuid) to service_role;
-- No legacy charge-then-dispatch bypass during a rolling application update.
revoke all on function public.dispatch_code_task(uuid,uuid,uuid,jsonb,text,integer) from service_role;

-- A new worker may recover unused work, never restart a model conversation
-- after its first provider begin. The reconciler handles expired started work.
create or replace function public.claim_code_task(p_lease_seconds integer,p_claim_token uuid)
returns setof public.code_tasks language plpgsql security invoker set search_path = '' as $$
declare claimed public.code_tasks%rowtype;
begin
  if p_claim_token is null then raise exception 'claim token is required' using errcode='22023'; end if;
  select * into claimed from public.code_tasks
    where status in ('provisioning','running','verifying') and lease_token=p_claim_token
      and lease_expires_at>clock_timestamp() and expires_at>clock_timestamp() limit 1;
  if found then return next claimed; return; end if;
  select * into claimed from public.code_tasks
    where status in ('provisioning','running','verifying') and usage_receipt is not null
      and provider_budget_policy is not null and provider_started_at is null
      and next_attempt_at<=clock_timestamp() and expires_at>clock_timestamp()
      and (lease_token is null or lease_expires_at is null or lease_expires_at<clock_timestamp())
    order by next_attempt_at,created_at for update skip locked limit 1;
  if not found then return; end if;
  update public.code_tasks set status='provisioning',lease_token=p_claim_token,
    lease_expires_at=clock_timestamp()+pg_catalog.make_interval(secs=>greatest(60,least(300,p_lease_seconds))),
    attempt_count=attempt_count+1,failure_code=null,started_at=coalesce(started_at,clock_timestamp()),updated_at=clock_timestamp()
    where id=claimed.id returning * into claimed;
  return next claimed;
end;
$$;
revoke all on function public.claim_code_task(integer,uuid) from public,anon,authenticated;
grant execute on function public.claim_code_task(integer,uuid) to service_role;

-- Preserve the latest durable Storage-deletion contract introduced by
-- 20260924210000_durable_account_storage_deletion.sql. Only lock ordering changes:
-- parent user first, before Storage obligation or any child deletes. This
-- matches Code's user KEY SHARE -> task -> usage/credit order. Retrying a deleted
-- account still refreshes its independent Storage cleanup obligation as before.
create or replace function public.delete_user_account(p_user_id uuid,p_storage_bucket text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if p_user_id is null then
    raise exception 'user id is required' using errcode='22023';
  end if;
  if p_storage_bucket is null or p_storage_bucket !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$' then
    raise exception 'invalid storage bucket' using errcode='22023';
  end if;
  perform 1 from public.users where id=p_user_id for update;
  insert into public.account_storage_deletion_jobs as job (
    user_id,bucket,owner_prefix,status,attempts,next_attempt_at,final_sweep_after,
    empty_observed_at,lease_token,lease_expires_at,last_error,updated_at
  ) values (
    p_user_id,p_storage_bucket,p_user_id::text || '/','pending',0,pg_catalog.clock_timestamp(),
    pg_catalog.clock_timestamp()+interval '27 hours',null,null,null,null,pg_catalog.clock_timestamp()
  ) on conflict(user_id) do update
  set status='pending',next_attempt_at=least(job.next_attempt_at,pg_catalog.clock_timestamp()),
      final_sweep_after=greatest(job.final_sweep_after,pg_catalog.clock_timestamp()+interval '27 hours'),
      empty_observed_at=null,lease_token=null,lease_expires_at=null,last_error=null,updated_at=pg_catalog.clock_timestamp();
  if pg_catalog.to_regclass('public.crump_chats') is not null then
    execute 'delete from public.crump_chats where user_id = $1' using p_user_id;
  end if;
  if pg_catalog.to_regclass('public.devices') is not null then
    execute 'delete from public.devices where user_id = $1' using p_user_id;
  end if;
  delete from public.usage_events where user_id=p_user_id;
  delete from public.user_chats where user_id=p_user_id;
  delete from public.user_settings where user_id=p_user_id;
  delete from public.sessions where user_id=p_user_id;
  delete from public.users where id=p_user_id;
end;
$$;
revoke all on function public.delete_user_account(uuid,text) from public,anon,authenticated;
grant execute on function public.delete_user_account(uuid,text) to service_role;

comment on table public.code_provider_call_reservations is
  'Code-only content-free provider admission. Unknown outcomes retain reserved cost; only pre-dispatch holds can be released. UTC day caps use the strictest configured limit observed that day.';
comment on table public.code_provider_global_daily is
  'Deletion-independent Code provider daily admission total and cap minimum. Contains no account, task, reservation, model, prompt, or credential identity; cascade deletion never releases retained cost.';
comment on table public.code_provider_account_daily is
  'Code account daily admission totals survive task/project deletion; identifiers and rows cascade away with the account. Global accounting is retained separately without identifiers.';
commit;
