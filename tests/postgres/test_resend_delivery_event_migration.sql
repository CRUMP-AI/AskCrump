\set ON_ERROR_STOP on

create or replace function pg_temp.assert_true(
  condition boolean,
  failure_message text
)
returns void
language plpgsql
as $$
begin
  if condition is not true then
    raise exception 'PostgreSQL migration gate failed: %', failure_message;
  end if;
end;
$$;

create or replace function pg_temp.fixture_at(offset_from_start interval)
returns timestamptz
language sql
stable
as $$
  select pg_catalog.date_trunc('day', pg_catalog.now())
    - interval '2 days'
    + offset_from_start;
$$;

select pg_temp.assert_true(
  not has_schema_privilege('anon', 'private', 'USAGE')
    and not has_schema_privilege('authenticated', 'private', 'USAGE')
    and not has_schema_privilege('service_role', 'private', 'USAGE'),
  'private schema is reachable by a browser role'
);

select pg_temp.assert_true(
  not has_table_privilege(
    'service_role', 'private.resend_delivery_events', 'SELECT'
  )
    and not has_table_privilege(
      'service_role', 'private.resend_delivery_events', 'INSERT'
    )
    and not has_table_privilege(
      'anon', 'private.resend_delivery_events', 'SELECT'
    )
    and not has_table_privilege(
      'authenticated', 'private.resend_delivery_events', 'SELECT'
    ),
  'delivery-event table has a direct Data API grant'
);

select pg_temp.assert_true(
  has_function_privilege(
    'service_role',
    'public.record_resend_delivery_event(text,text,text,text,text,text,text,timestamptz)',
    'EXECUTE'
  )
    and not has_function_privilege(
      'anon',
      'public.record_resend_delivery_event(text,text,text,text,text,text,text,timestamptz)',
      'EXECUTE'
    )
    and not has_function_privilege(
      'authenticated',
      'public.record_resend_delivery_event(text,text,text,text,text,text,text,timestamptz)',
      'EXECUTE'
    )
    and has_function_privilege(
      'service_role',
      'public.resend_delivery_event_aggregate(timestamptz,timestamptz,text)',
      'EXECUTE'
    )
    and not has_function_privilege(
      'anon',
      'public.resend_delivery_event_aggregate(timestamptz,timestamptz,text)',
      'EXECUTE'
    )
    and not has_function_privilege(
      'authenticated',
      'public.resend_delivery_event_aggregate(timestamptz,timestamptz,text)',
      'EXECUTE'
    ),
  'delivery-event RPC privileges are not service-role only'
);

do $$
declare
  table_row record;
  function_row record;
begin
  select c.relrowsecurity, c.relforcerowsecurity
  into strict table_row
  from pg_catalog.pg_class as c
  join pg_catalog.pg_namespace as n on n.oid = c.relnamespace
  where n.nspname = 'private' and c.relname = 'resend_delivery_events';

  if not table_row.relrowsecurity or not table_row.relforcerowsecurity then
    raise exception 'private delivery-event table RLS drifted';
  end if;

  for function_row in
    select p.proname, p.prosecdef, p.provolatile, p.proconfig
    from pg_catalog.pg_proc as p
    join pg_catalog.pg_namespace as n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname in (
        'record_resend_delivery_event',
        'resend_delivery_event_aggregate'
      )
  loop
    if not function_row.prosecdef
       or function_row.proconfig <> array['search_path=""']::text[]
       or (
         function_row.proname = 'resend_delivery_event_aggregate'
         and function_row.provolatile <> 's'
       )
    then
      raise exception 'delivery-event function security or volatility drifted';
    end if;
  end loop;
end;
$$;

select pg_temp.assert_true(
  not exists (
    select 1
    from information_schema.columns
    where table_schema = 'private'
      and table_name = 'resend_delivery_events'
      and column_name in (
        'user_id', 'email', 'recipient', 'recipient_hash', 'subject', 'body',
        'html', 'url', 'token', 'headers', 'raw_payload', 'provider_event_id',
        'provider_email_id'
      )
  ),
  'delivery-event table stores a prohibited identifier or content field'
);

set role service_role;

select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('a', 64),
    repeat('1', 64),
    repeat('b', 64),
    'production',
    'verification',
    'email.sent',
    'accepted',
    pg_temp.fixture_at(interval '0')
  ),
  'first signed delivery event was not inserted'
);

select pg_temp.assert_true(
  not public.record_resend_delivery_event(
    repeat('a', 64),
    repeat('1', 64),
    repeat('b', 64),
    'production',
    'verification',
    'email.sent',
    'accepted',
    pg_temp.fixture_at(interval '0')
  ),
  'exact provider retry was not idempotent'
);

select pg_temp.assert_true(
  not public.record_resend_delivery_event(
    repeat('c', 64),
    repeat('1', 64),
    repeat('b', 64),
    'production',
    'verification',
    'email.sent',
    'accepted',
    pg_temp.fixture_at(interval '0')
  ),
  'manual replay with the same signed payload was not idempotent'
);

select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('d', 64), repeat('1', 64), repeat('e', 64), 'production',
    'verification', 'email.delivered', 'delivered',
    pg_temp.fixture_at(interval '1 minute')
  ),
  'delivered event was not inserted'
);
select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('f', 64), repeat('2', 64), repeat('3', 64), 'production',
    'verification', 'email.sent', 'accepted',
    pg_temp.fixture_at(interval '2 minutes')
  ),
  'second message send was not inserted'
);
select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('4', 64), repeat('2', 64), repeat('5', 64), 'production',
    'verification', 'email.delivery_delayed', 'transient',
    pg_temp.fixture_at(interval '3 minutes')
  ),
  'delivery-delay event was not inserted'
);
select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('6', 64), repeat('2', 64), repeat('7', 64), 'production',
    'verification', 'email.bounced', 'permanent',
    pg_temp.fixture_at(interval '4 minutes')
  ),
  'bounce event was not inserted'
);
select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('b1', 32), repeat('2', 64), repeat('b2', 32), 'production',
    'verification', 'email.bounced', 'transient',
    pg_temp.fixture_at(interval '4 minutes 30 seconds')
  ),
  'transient bounce event was not inserted'
);
select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('b3', 32), repeat('2', 64), repeat('b4', 32), 'production',
    'verification', 'email.bounced', 'failed',
    pg_temp.fixture_at(interval '4 minutes 45 seconds')
  ),
  'undetermined bounce event was not inserted'
);
select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('8', 64), repeat('9', 64), repeat('0', 64), 'production',
    'password_reset', 'email.failed', 'failed',
    pg_temp.fixture_at(interval '5 minutes')
  ),
  'password-reset failure was not inserted'
);
select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('a1', 32), repeat('a2', 32), repeat('a3', 32), 'preview',
    'verification', 'email.suppressed', 'suppressed',
    pg_temp.fixture_at(interval '6 minutes')
  ),
  'preview fixture was not inserted'
);
select pg_temp.assert_true(
  public.record_resend_delivery_event(
    repeat('a4', 32), repeat('a5', 32), repeat('a6', 32), 'production',
    'verification', 'email.complained', 'complaint',
    pg_temp.fixture_at(interval '1 day')
  ),
  'half-open upper-bound fixture was not inserted'
);

do $$
declare
  rejected boolean := false;
begin
  begin
    perform public.record_resend_delivery_event(
      repeat('a', 64), repeat('1', 64), repeat('c', 64), 'production',
      'verification', 'email.sent', 'accepted',
      pg_temp.fixture_at(interval '0')
    );
  exception when sqlstate '22023' then
    rejected := true;
  end;
  if not rejected then
    raise exception 'same event ID with changed payload was accepted';
  end if;
end;
$$;

do $$
declare
  rejected boolean := false;
begin
  begin
    perform public.record_resend_delivery_event(
      upper(repeat('b', 64)), repeat('3', 64), repeat('c', 64), 'production',
      'verification', 'email.sent', 'accepted',
      pg_temp.fixture_at(interval '7 minutes')
    );
  exception when sqlstate '22023' then
    rejected := true;
  end;
  if not rejected then
    raise exception 'uppercase provider hash was accepted';
  end if;
end;
$$;

do $$
declare
  rejected boolean := false;
begin
  begin
    perform public.record_resend_delivery_event(
      repeat('b5', 32), repeat('b6', 32), repeat('b7', 32), 'production',
      'verification', 'email.opened', 'delivered',
      pg_temp.fixture_at(interval '8 minutes')
    );
  exception when sqlstate '22023' then
    rejected := true;
  end;
  if not rejected then
    raise exception 'privacy-excluded engagement event was accepted';
  end if;
end;
$$;

do $$
declare
  rejected boolean := false;
begin
  begin
    perform public.record_resend_delivery_event(
      repeat('c1', 32), repeat('c2', 32), repeat('c3', 32), 'production',
      'verification', 'email.delivered', 'transient',
      pg_temp.fixture_at(interval '9 minutes')
    );
  exception when sqlstate '22023' then
    rejected := true;
  end;
  if not rejected then
    raise exception 'invalid event/outcome pair was accepted';
  end if;
end;
$$;

do $$
declare
  verification_row record;
  password_row record;
begin
  select * into strict verification_row
  from public.resend_delivery_event_aggregate(
    pg_temp.fixture_at(interval '0'),
    pg_temp.fixture_at(interval '1 day'),
    'production'
  )
  where message_kind = 'verification';

  if verification_row.provider_events <> 7
     or verification_row.provider_messages <> 2
     or verification_row.sent_messages <> 2
     or verification_row.delivered_messages <> 1
     or verification_row.delivery_delayed_messages <> 1
     or verification_row.bounced_messages <> 1
     or verification_row.failed_messages <> 0
     or verification_row.suppressed_messages <> 0
     or verification_row.complained_messages <> 0
  then
    raise exception 'verification aggregate drifted: %', row_to_json(verification_row);
  end if;

  select * into strict password_row
  from public.resend_delivery_event_aggregate(
    pg_temp.fixture_at(interval '0'),
    pg_temp.fixture_at(interval '1 day'),
    'production'
  )
  where message_kind = 'password_reset';

  if password_row.provider_events <> 1
     or password_row.provider_messages <> 1
     or password_row.failed_messages <> 1
     or password_row.sent_messages <> 0
     or password_row.delivered_messages <> 0
  then
    raise exception 'password-reset aggregate drifted: %', row_to_json(password_row);
  end if;
end;
$$;

reset role;

select pg_temp.assert_true(
  (select count(*) from private.resend_delivery_events) = 10,
  'replays, excluded environments, or half-open fixtures changed stored row count'
);
