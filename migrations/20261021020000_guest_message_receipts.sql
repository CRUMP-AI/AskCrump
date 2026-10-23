-- Shared guest + registered-Free rolling message allowance.
--
-- usage_events is the one durable ledger. Because guest registration updates
-- the same users row, its recent receipts remain attached and signup cannot
-- mint another five messages. The function hard-codes the commercial rule;
-- no caller-controlled limit or raw request content enters the database.
--
-- The migration runner owns the transaction. Creation and ACL lockdown must
-- execute in the same runner transaction.

create or replace function public.reserve_free_message_v1(
  p_user_id uuid,
  p_message_id uuid,
  p_fingerprint text
)
returns table(
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_limit constant integer := 5;
  v_now timestamptz;
  v_key text;
  v_existing uuid;
  v_used integer;
  v_oldest timestamptz;
  v_next_available timestamptz;
  v_inserted uuid;
  v_is_guest boolean := false;
  v_guest_mode_enabled boolean := false;
begin
  if p_user_id is null or p_message_id is null then
    raise exception using
      errcode = '22023',
      message = 'Free message identity is required.';
  end if;
  if coalesce(p_fingerprint, '') !~ '^[0-9a-f]{64}$' then
    raise exception using
      errcode = '22023',
      message = 'Free message fingerprint is invalid.';
  end if;

  v_key := p_message_id::text || ':' || p_fingerprint;

  -- Lock order is global control -> account -> per-account usage advisory.
  -- A disable transaction takes the exclusive side of the first lock, so it
  -- cannot commit while a guest reservation is still in flight. Registered
  -- Free accounts read the same lock but remain eligible when guest mode is
  -- disabled or the singleton is missing.
  v_guest_mode_enabled := public.lock_guest_mode_control_v1();

  select coalesce(account.is_guest, false)
    into v_is_guest
    from public.users as account
   where account.id = p_user_id
   for share;

  if not found then
    raise exception using
      errcode = '23503',
      message = 'Free message account does not exist.';
  end if;

  if v_is_guest and v_guest_mode_enabled is not true then
    return query select
      'guest_mode_disabled'::text,
      null::uuid,
      0,
      0,
      null::timestamptz;
    return;
  end if;

  -- Match consume_usage_event_v2's lock namespace so a Free reservation and
  -- any legacy message consumer cannot race each other for the same account.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'usage:' || p_user_id::text || ':messages',
      0
    )
  );

  -- Sample authoritative wall time only after the per-account lock wait. A
  -- statement timestamp is fixed before the wait and can make an expired
  -- rolling-window receipt look current or backdate a new reservation.
  v_now := pg_catalog.clock_timestamp();

  -- Replay precedes the cap. Return no event_id: only a newly owned receipt
  -- may be refunded by a pre-persistence failure.
  select event.id into v_existing
  from public.usage_events as event
  where event.user_id = p_user_id
    and event.event_type = 'messages'
    and event.idempotency_key = v_key;

  select count(*)::integer, min(event.created_at)
  into v_used, v_oldest
  from public.usage_events as event
  where event.user_id = p_user_id
    and event.event_type = 'messages'
    and event.created_at > v_now - interval '24 hours';

  if v_used >= v_limit then
    -- Existing ledgers can contain more than five recent rows (for example,
    -- after a paid account downgrades). Expiring only the oldest row would
    -- still leave the account at or above the cap. Select the first event
    -- whose expiry actually leaves fewer than five rows in the window.
    select event.created_at + interval '24 hours'
    into v_next_available
    from public.usage_events as event
    where event.user_id = p_user_id
      and event.event_type = 'messages'
      and event.created_at > v_now - interval '24 hours'
    order by event.created_at asc, event.id asc
    offset greatest(v_used - v_limit, 0)
    limit 1;
  end if;

  if v_existing is not null then
    return query select
      'reused'::text,
      null::uuid,
      v_used,
      greatest(v_limit - v_used, 0),
      case when v_used >= v_limit then v_next_available else null end;
    return;
  end if;

  if v_used >= v_limit then
    return query select
      'exhausted'::text,
      null::uuid,
      v_used,
      0,
      v_next_available;
    return;
  end if;

  insert into public.usage_events (
    user_id,
    event_type,
    idempotency_key,
    metadata,
    created_at
  ) values (
    p_user_id,
    'messages',
    v_key,
    pg_catalog.jsonb_build_object(
      'source', 'free_message_allowance',
      'messageId', p_message_id::text
    ),
    v_now
  )
  returning id into v_inserted;

  v_used := v_used + 1;
  if v_oldest is null then
    v_oldest := v_now;
  end if;
  if v_used >= v_limit then
    v_next_available := v_oldest + interval '24 hours';
  end if;
  return query select
    'reserved'::text,
    v_inserted,
    v_used,
    greatest(v_limit - v_used, 0),
    case when v_used >= v_limit then v_next_available else null end;
end;
$$;

revoke all on function public.reserve_free_message_v1(uuid, uuid, text)
  from public, anon, authenticated, service_role;
grant execute on function public.reserve_free_message_v1(uuid, uuid, text)
  to service_role;

-- The backend reads allowance status and deletes only the event id it owns on
-- an explicitly safe pre-persistence refund. Inserts remain RPC-only.
revoke all on table public.usage_events from public, anon, authenticated, service_role;
grant select, delete on table public.usage_events to service_role;

comment on function public.reserve_free_message_v1(uuid, uuid, text) is
  'Atomically reserves one of five rolling-24-hour Free text messages; service role only.';
