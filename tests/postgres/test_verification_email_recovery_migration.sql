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

select pg_temp.assert_true(
  not has_schema_privilege('service_role', 'private', 'USAGE')
    and not has_schema_privilege('anon', 'private', 'USAGE')
    and not has_schema_privilege('authenticated', 'private', 'USAGE'),
  'private recovery schema is reachable directly'
);

select pg_temp.assert_true(
  not has_table_privilege(
    'service_role', 'private.verification_email_recovery_attempts', 'SELECT'
  )
    and not has_table_privilege(
      'service_role', 'private.verification_email_recovery_attempts', 'INSERT'
    )
    and not has_table_privilege(
      'anon', 'private.verification_email_recovery_attempts', 'SELECT'
    )
    and not has_table_privilege(
      'authenticated', 'private.verification_email_recovery_attempts', 'SELECT'
    ),
  'attempt ledger has a direct Data API grant'
);

select pg_temp.assert_true(
  has_function_privilege(
    'service_role',
    'public.register_verification_email_recovery_attempt(text,uuid,text,timestamptz)',
    'EXECUTE'
  )
    and has_function_privilege(
      'service_role',
      'public.record_resend_delivery_event_and_recovery(text,text,text,text,text,text,text,timestamptz)',
      'EXECUTE'
    )
    and has_function_privilege(
      'service_role',
      'public.claim_verification_email_recovery(uuid)',
      'EXECUTE'
    )
    and has_function_privilege(
      'service_role',
      'public.prepare_verification_email_recovery(text,uuid,text,timestamptz,text,timestamptz)',
      'EXECUTE'
    )
    and has_function_privilege(
      'service_role',
      'public.complete_verification_email_recovery(text,uuid,text,timestamptz)',
      'EXECUTE'
    )
    and has_function_privilege(
      'service_role',
      'public.fail_verification_email_recovery(text,uuid,text,text,timestamptz)',
      'EXECUTE'
    ),
  'service role cannot execute the bounded recovery RPC surface'
);

select pg_temp.assert_true(
  not has_function_privilege(
    'anon', 'public.claim_verification_email_recovery(uuid)', 'EXECUTE'
  )
    and not has_function_privilege(
      'authenticated',
      'public.claim_verification_email_recovery(uuid)',
      'EXECUTE'
    )
    and not has_function_privilege(
      'anon',
      'public.prepare_verification_email_recovery(text,uuid,text,timestamptz,text,timestamptz)',
      'EXECUTE'
    ),
  'browser roles can execute a recovery RPC'
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
  where n.nspname = 'private'
    and c.relname = 'verification_email_recovery_attempts';

  if not table_row.relrowsecurity or not table_row.relforcerowsecurity then
    raise exception 'private recovery ledger RLS drifted';
  end if;

  for function_row in
    select p.proname, p.prosecdef, p.proconfig
    from pg_catalog.pg_proc as p
    join pg_catalog.pg_namespace as n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname in (
        'register_verification_email_recovery_attempt',
        'record_resend_delivery_event_and_recovery',
        'claim_verification_email_recovery',
        'prepare_verification_email_recovery',
        'complete_verification_email_recovery',
        'fail_verification_email_recovery'
      )
  loop
    if not function_row.prosecdef
       or function_row.proconfig <> array['search_path=""']::text[]
    then
      raise exception 'recovery function security or search path drifted';
    end if;
  end loop;
end;
$$;

select pg_temp.assert_true(
  not exists (
    select 1
    from information_schema.columns
    where table_schema = 'private'
      and table_name = 'verification_email_recovery_attempts'
      and column_name in (
        'email', 'email_address', 'recipient', 'recipient_hash', 'subject',
        'body', 'html', 'url', 'token', 'token_hash', 'headers',
        'raw_payload', 'provider_email_id', 'provider_event_id'
      )
  ),
  'attempt ledger stores a prohibited address, content, token, or raw ID'
);

insert into public.users (
  id, email, password_hash, is_verified,
  verification_token_hash, verification_token_expires
) values
  ('10000000-0000-0000-0000-000000000001', 'transient@test.invalid', 'x', false, repeat('1', 64), pg_catalog.clock_timestamp() + interval '24 hours'),
  ('10000000-0000-0000-0000-000000000002', 'permanent@test.invalid', 'x', false, repeat('2', 64), pg_catalog.clock_timestamp() + interval '24 hours'),
  ('10000000-0000-0000-0000-000000000003', 'complaint@test.invalid', 'x', false, repeat('3', 64), pg_catalog.clock_timestamp() + interval '24 hours'),
  ('10000000-0000-0000-0000-000000000004', 'verified@test.invalid', 'x', false, repeat('4', 64), pg_catalog.clock_timestamp() + interval '24 hours'),
  ('10000000-0000-0000-0000-000000000005', 'expired@test.invalid', 'x', false, repeat('5', 64), pg_catalog.clock_timestamp() + interval '24 hours'),
  ('10000000-0000-0000-0000-000000000006', 'rollback@test.invalid', 'x', false, repeat('6', 64), pg_catalog.clock_timestamp() + interval '24 hours'),
  ('10000000-0000-0000-0000-000000000007', 'race@test.invalid', 'x', false, repeat('7', 64), pg_catalog.clock_timestamp() + interval '24 hours');

select pg_catalog.clock_timestamp() as transient_event_at \gset

set role service_role;

select pg_temp.assert_true(
  public.register_verification_email_recovery_attempt(
    repeat('a1', 32), '10000000-0000-0000-0000-000000000001', 'test',
    (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000001')
  ),
  'transient fixture was not registered'
);
select pg_temp.assert_true(
  not public.register_verification_email_recovery_attempt(
    repeat('a1', 32), '10000000-0000-0000-0000-000000000001', 'test',
    (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000001')
  ),
  'exact attempt registration replay was not idempotent'
);

select pg_temp.assert_true(
  public.record_resend_delivery_event_and_recovery(
    repeat('e1', 32), repeat('a1', 32), repeat('f1', 32), 'test',
    'verification', 'email.delivery_delayed', 'transient',
    :'transient_event_at'::timestamptz
  ),
  'signed transient event was not recorded'
);
select pg_temp.assert_true(
  not public.record_resend_delivery_event_and_recovery(
    repeat('e1', 32), repeat('a1', 32), repeat('f1', 32), 'test',
    'verification', 'email.delivery_delayed', 'transient',
    :'transient_event_at'::timestamptz
  ),
  'signed event replay was not idempotent'
);

reset role;

select pg_temp.assert_true(
  (
    select state = 'eligible'
      and attempt_count = 0
      and retry_after > pg_catalog.clock_timestamp()
    from private.verification_email_recovery_attempts
    where provider_email_hash = repeat('a1', 32)
  ),
  'verified transient event did not schedule one delayed retry'
);

update private.verification_email_recovery_attempts
set retry_after = pg_catalog.clock_timestamp() - interval '1 second'
where provider_email_hash = repeat('a1', 32);

set role service_role;

do $$
declare
  first_claim record;
  competing_claim record;
begin
  select * into strict first_claim
  from public.claim_verification_email_recovery(
    '20000000-0000-0000-0000-000000000001'
  );
  if first_claim.provider_email_hash <> repeat('a1', 32)
     or first_claim.previous_token_hash <> repeat('1', 64)
  then
    raise exception 'first recovery claim returned the wrong bounded identity';
  end if;

  select * into competing_claim
  from public.claim_verification_email_recovery(
    '20000000-0000-0000-0000-000000000002'
  );
  if found then
    raise exception 'race competitor claimed the same recovery attempt';
  end if;

  if not public.prepare_verification_email_recovery(
    repeat('a1', 32),
    '20000000-0000-0000-0000-000000000001',
    repeat('1', 64),
    first_claim.previous_token_expires_at,
    repeat('9', 64),
    pg_catalog.clock_timestamp() + interval '24 hours'
  ) then
    raise exception 'claimed recovery could not rotate to a fresh token hash';
  end if;
end;
$$;

reset role;

select pg_temp.assert_true(
  (
    select state = 'sending' and attempt_count = 1
    from private.verification_email_recovery_attempts
    where provider_email_hash = repeat('a1', 32)
  ),
  'prepare did not consume the sole retry before provider I/O'
);

set role service_role;

select pg_temp.assert_true(
  public.complete_verification_email_recovery(
    repeat('a1', 32),
    '20000000-0000-0000-0000-000000000001',
    repeat('a2', 32),
    (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000001')
  ),
  'sole recovery retry did not complete'
);
select pg_temp.assert_true(
  not public.complete_verification_email_recovery(
    repeat('a1', 32),
    '20000000-0000-0000-0000-000000000001',
    repeat('a2', 32),
    (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000001')
  ),
  'completion replay was not idempotent'
);

reset role;

select pg_temp.assert_true(
  (
    select state = 'retry_sent'
      and attempt_count = 1
      and retry_provider_email_hash = repeat('a2', 32)
    from private.verification_email_recovery_attempts
    where provider_email_hash = repeat('a1', 32)
  ),
  'completed retry did not retain only the hashed provider correlation'
);

-- Permanent bounce and complaint are terminal and can never enter the queue.
set role service_role;
select public.register_verification_email_recovery_attempt(
  repeat('b1', 32), '10000000-0000-0000-0000-000000000002', 'test',
  (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000002')
);
select public.record_resend_delivery_event_and_recovery(
  repeat('e2', 32), repeat('b1', 32), repeat('f2', 32), 'test',
  'verification', 'email.bounced', 'permanent', pg_catalog.clock_timestamp()
);
select public.register_verification_email_recovery_attempt(
  repeat('c1', 32), '10000000-0000-0000-0000-000000000003', 'test',
  (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000003')
);
select public.record_resend_delivery_event_and_recovery(
  repeat('e3', 32), repeat('c1', 32), repeat('f3', 32), 'test',
  'verification', 'email.complained', 'complaint', pg_catalog.clock_timestamp()
);
reset role;

select pg_temp.assert_true(
  (select state = 'terminal' from private.verification_email_recovery_attempts where provider_email_hash = repeat('b1', 32))
    and (select state = 'terminal' from private.verification_email_recovery_attempts where provider_email_hash = repeat('c1', 32)),
  'permanent bounce or complaint was made retryable'
);

-- Already-verified and expired accounts are cancelled by the authoritative DB state.
set role service_role;
select public.register_verification_email_recovery_attempt(
  repeat('d1', 32), '10000000-0000-0000-0000-000000000004', 'test',
  (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000004')
);
select public.register_verification_email_recovery_attempt(
  repeat('d2', 32), '10000000-0000-0000-0000-000000000005', 'test',
  (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000005')
);
reset role;
update public.users set is_verified = true where id = '10000000-0000-0000-0000-000000000004';
update public.users set verification_token_expires = pg_catalog.clock_timestamp() - interval '1 second' where id = '10000000-0000-0000-0000-000000000005';
update private.verification_email_recovery_attempts set token_expires_at = pg_catalog.clock_timestamp() - interval '1 second' where provider_email_hash = repeat('d2', 32);
set role service_role;
select public.record_resend_delivery_event_and_recovery(
  repeat('e4', 32), repeat('d1', 32), repeat('f4', 32), 'test',
  'verification', 'email.delivery_delayed', 'transient', pg_catalog.clock_timestamp()
);
select public.record_resend_delivery_event_and_recovery(
  repeat('e5', 32), repeat('d2', 32), repeat('f5', 32), 'test',
  'verification', 'email.delivery_delayed', 'transient', pg_catalog.clock_timestamp()
);
reset role;

select pg_temp.assert_true(
  (select state = 'cancelled' from private.verification_email_recovery_attempts where provider_email_hash = repeat('d1', 32))
    and (select state = 'cancelled' from private.verification_email_recovery_attempts where provider_email_hash = repeat('d2', 32)),
  'verified or expired account remained retryable'
);

-- A provider send failure restores the prior token and permanently consumes the retry.
set role service_role;
select public.register_verification_email_recovery_attempt(
  repeat('d3', 32), '10000000-0000-0000-0000-000000000006', 'test',
  (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000006')
);
select public.record_resend_delivery_event_and_recovery(
  repeat('e6', 32), repeat('d3', 32), repeat('f6', 32), 'test',
  'verification', 'email.bounced', 'transient', pg_catalog.clock_timestamp()
);
reset role;
update private.verification_email_recovery_attempts set retry_after = pg_catalog.clock_timestamp() - interval '1 second' where provider_email_hash = repeat('d3', 32);
set role service_role;
do $$
declare
  claimed record;
  fresh_expiry timestamptz := pg_catalog.clock_timestamp() + interval '24 hours';
begin
  select * into strict claimed
  from public.claim_verification_email_recovery('20000000-0000-0000-0000-000000000006');
  if not public.prepare_verification_email_recovery(
    repeat('d3', 32), claimed.claim_token,
    claimed.previous_token_hash, claimed.previous_token_expires_at,
    repeat('8', 64), fresh_expiry
  ) then
    raise exception 'rollback fixture did not prepare';
  end if;
  if not public.fail_verification_email_recovery(
    repeat('d3', 32), claimed.claim_token, repeat('8', 64),
    claimed.previous_token_hash, claimed.previous_token_expires_at
  ) then
    raise exception 'send failure did not roll back';
  end if;
  if public.fail_verification_email_recovery(
    repeat('d3', 32), claimed.claim_token, repeat('8', 64),
    claimed.previous_token_hash, claimed.previous_token_expires_at
  ) then
    raise exception 'send-failure replay was not idempotent';
  end if;
end;
$$;
reset role;

select pg_temp.assert_true(
  (
    select verification_token_hash = repeat('6', 64)
    from public.users
    where id = '10000000-0000-0000-0000-000000000006'
  )
    and (
      select state = 'send_failed' and attempt_count = 1
      from private.verification_email_recovery_attempts
      where provider_email_hash = repeat('d3', 32)
    ),
  'provider send failure did not restore the previous token exactly once'
);

-- A terminal event winning after claim prevents token rotation and provider I/O.
set role service_role;
select public.register_verification_email_recovery_attempt(
  repeat('d4', 32), '10000000-0000-0000-0000-000000000007', 'test',
  (select verification_token_expires from public.users where id = '10000000-0000-0000-0000-000000000007')
);
select public.record_resend_delivery_event_and_recovery(
  repeat('e7', 32), repeat('d4', 32), repeat('f7', 32), 'test',
  'verification', 'email.delivery_delayed', 'transient', pg_catalog.clock_timestamp()
);
reset role;
update private.verification_email_recovery_attempts set retry_after = pg_catalog.clock_timestamp() - interval '1 second' where provider_email_hash = repeat('d4', 32);
set role service_role;
do $$
declare
  claimed record;
begin
  select * into strict claimed
  from public.claim_verification_email_recovery('20000000-0000-0000-0000-000000000007');
  perform public.record_resend_delivery_event_and_recovery(
    repeat('e8', 32), repeat('d4', 32), repeat('f8', 32), 'test',
    'verification', 'email.delivered', 'delivered', pg_catalog.clock_timestamp()
  );
  if public.prepare_verification_email_recovery(
    repeat('d4', 32), claimed.claim_token,
    claimed.previous_token_hash, claimed.previous_token_expires_at,
    repeat('7a', 32), pg_catalog.clock_timestamp() + interval '24 hours'
  ) then
    raise exception 'delivered-vs-claim race still rotated a token';
  end if;
end;
$$;
reset role;

select pg_temp.assert_true(
  (select state = 'delivered' from private.verification_email_recovery_attempts where provider_email_hash = repeat('d4', 32))
    and (select verification_token_hash = repeat('7', 64) from public.users where id = '10000000-0000-0000-0000-000000000007'),
  'delivered event did not win the claim race without changing the token'
);

select pg_temp.assert_true(
  not exists (
    select 1
    from private.verification_email_recovery_attempts
    where attempt_count > 1
  ),
  'a recovery path exceeded its one-retry ceiling'
);
