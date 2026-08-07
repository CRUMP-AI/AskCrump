-- Ask Crump 5.1.0
-- Durable non-expiring Crump Credits wallet with an immutable, idempotent ledger.
-- Purchased credits are account-scoped and never expire.

begin;

create table if not exists public.credit_accounts (
  user_id uuid primary key references public.users(id) on delete cascade,
  balance bigint not null default 0 check (balance >= 0),
  lifetime_granted bigint not null default 0 check (lifetime_granted >= 0),
  lifetime_spent bigint not null default 0 check (lifetime_spent >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.credit_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  delta integer not null check (delta <> 0),
  balance_after bigint not null check (balance_after >= 0),
  reason text not null,
  provider text not null default 'internal',
  external_id text,
  product_id text,
  related_ledger_id uuid references public.credit_ledger(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists credit_ledger_user_created_idx
  on public.credit_ledger(user_id, created_at desc);

create unique index if not exists credit_ledger_provider_external_unique
  on public.credit_ledger(user_id, provider, external_id)
  where external_id is not null;

create unique index if not exists credit_ledger_refund_once_unique
  on public.credit_ledger(user_id, related_ledger_id)
  where related_ledger_id is not null and reason = 'refund';

alter table public.credit_accounts enable row level security;
alter table public.credit_ledger enable row level security;
revoke all on table public.credit_accounts from anon, authenticated;
revoke all on table public.credit_ledger from anon, authenticated;
grant all on table public.credit_accounts to service_role;
grant all on table public.credit_ledger to service_role;

insert into public.credit_accounts (user_id)
select id from public.users
where deleted_at is null
on conflict (user_id) do nothing;

create or replace function public.grant_credits(
  p_user_id uuid,
  p_amount integer,
  p_reason text,
  p_provider text default 'internal',
  p_external_id text default null,
  p_product_id text default null,
  p_metadata jsonb default '{}'::jsonb
)
returns table(ledger_id uuid, balance bigint, duplicate boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  existing public.credit_ledger%rowtype;
  new_balance bigint;
  inserted_id uuid;
begin
  if p_amount is null or p_amount <= 0 then
    raise exception 'Credit grant amount must be positive';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('credits:' || p_user_id::text, 0));

  insert into public.credit_accounts (user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  if p_external_id is not null then
    select * into existing
    from public.credit_ledger
    where user_id = p_user_id
      and provider = coalesce(nullif(p_provider, ''), 'internal')
      and external_id = p_external_id
    limit 1;

    if found then
      return query select existing.id, existing.balance_after, true;
      return;
    end if;
  end if;

  update public.credit_accounts as account
  set balance = account.balance + p_amount,
      lifetime_granted = account.lifetime_granted + p_amount,
      updated_at = now()
  where account.user_id = p_user_id
  returning account.balance into new_balance;

  insert into public.credit_ledger (
    user_id, delta, balance_after, reason, provider, external_id, product_id, metadata
  )
  values (
    p_user_id,
    p_amount,
    new_balance,
    coalesce(nullif(p_reason, ''), 'credit_grant'),
    coalesce(nullif(p_provider, ''), 'internal'),
    p_external_id,
    p_product_id,
    coalesce(p_metadata, '{}'::jsonb)
  )
  returning id into inserted_id;

  return query select inserted_id, new_balance, false;
end;
$$;

create or replace function public.spend_credits(
  p_user_id uuid,
  p_amount integer default 1,
  p_reason text default 'usage',
  p_metadata jsonb default '{}'::jsonb
)
returns table(ledger_id uuid, balance bigint, allowed boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_balance bigint;
  new_balance bigint;
  inserted_id uuid;
begin
  if p_amount is null or p_amount <= 0 then
    raise exception 'Credit spend amount must be positive';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('credits:' || p_user_id::text, 0));

  insert into public.credit_accounts (user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  select account.balance into current_balance
  from public.credit_accounts as account
  where account.user_id = p_user_id
  for update;

  if coalesce(current_balance, 0) < p_amount then
    return query select null::uuid, coalesce(current_balance, 0), false;
    return;
  end if;

  new_balance := current_balance - p_amount;

  update public.credit_accounts as account
  set balance = new_balance,
      lifetime_spent = account.lifetime_spent + p_amount,
      updated_at = now()
  where account.user_id = p_user_id;

  insert into public.credit_ledger (
    user_id, delta, balance_after, reason, provider, metadata
  )
  values (
    p_user_id,
    -p_amount,
    new_balance,
    coalesce(nullif(p_reason, ''), 'usage'),
    'internal',
    coalesce(p_metadata, '{}'::jsonb)
  )
  returning id into inserted_id;

  return query select inserted_id, new_balance, true;
end;
$$;

create or replace function public.refund_credit_spend(
  p_user_id uuid,
  p_ledger_id uuid,
  p_metadata jsonb default '{}'::jsonb
)
returns table(ledger_id uuid, balance bigint, duplicate boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  original public.credit_ledger%rowtype;
  existing public.credit_ledger%rowtype;
  refund_amount integer;
  new_balance bigint;
  inserted_id uuid;
begin
  perform pg_advisory_xact_lock(hashtextextended('credits:' || p_user_id::text, 0));

  select * into original
  from public.credit_ledger
  where id = p_ledger_id
    and user_id = p_user_id
    and delta < 0
  limit 1;

  if not found then
    raise exception 'Credit spend was not found';
  end if;

  select * into existing
  from public.credit_ledger
  where user_id = p_user_id
    and related_ledger_id = p_ledger_id
    and reason = 'refund'
  limit 1;

  if found then
    return query select existing.id, existing.balance_after, true;
    return;
  end if;

  refund_amount := abs(original.delta);

  update public.credit_accounts as account
  set balance = account.balance + refund_amount,
      lifetime_spent = greatest(0, account.lifetime_spent - refund_amount),
      updated_at = now()
  where account.user_id = p_user_id
  returning account.balance into new_balance;

  insert into public.credit_ledger (
    user_id, delta, balance_after, reason, provider, related_ledger_id, metadata
  )
  values (
    p_user_id,
    refund_amount,
    new_balance,
    'refund',
    'internal',
    p_ledger_id,
    coalesce(p_metadata, '{}'::jsonb)
  )
  returning id into inserted_id;

  return query select inserted_id, new_balance, false;
end;
$$;

revoke all on function public.grant_credits(uuid, integer, text, text, text, text, jsonb) from public, anon, authenticated;
revoke all on function public.spend_credits(uuid, integer, text, jsonb) from public, anon, authenticated;
revoke all on function public.refund_credit_spend(uuid, uuid, jsonb) from public, anon, authenticated;
grant execute on function public.grant_credits(uuid, integer, text, text, text, text, jsonb) to service_role;
grant execute on function public.spend_credits(uuid, integer, text, jsonb) to service_role;
grant execute on function public.refund_credit_spend(uuid, uuid, jsonb) to service_role;

-- Existing beta accounts receive a one-time, non-expiring QA balance so the
-- current product can be tested without a real-money purchase. Idempotency is
-- enforced per account by the provider/external-id unique index.
do $$
declare
  account record;
begin
  for account in
    select id from public.users where deleted_at is null
  loop
    perform *
    from public.grant_credits(
      account.id,
      100,
      'beta_qa_grant',
      'promo',
      'ask-crump-5.1-beta',
      null,
      jsonb_build_object('release', '5.1.0', 'purpose', 'founder QA')
    );
  end loop;
end $$;

commit;
