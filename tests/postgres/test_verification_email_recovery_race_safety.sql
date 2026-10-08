\set ON_ERROR_STOP on

create or replace function pg_temp.assert_true(condition boolean, message text)
returns void language plpgsql as $$
begin
  if condition is not true then
    raise exception 'Verification recovery race gate failed: %', message;
  end if;
end;
$$;

select pg_temp.assert_true(
  has_function_privilege(
    'service_role',
    'public.claim_verification_email_recovery(uuid,text)', 'EXECUTE'
  )
  and has_function_privilege(
    'service_role',
    'public.prepare_verification_email_recovery(text,uuid,text,timestamptz,text,timestamptz,text)',
    'EXECUTE'
  )
  and has_function_privilege(
    'service_role',
    'public.authorize_verification_email_recovery_dispatch(text,uuid,text,text,timestamptz,text)',
    'EXECUTE'
  )
  and has_function_privilege(
    'service_role',
    'public.complete_verification_email_recovery(text,uuid,text,text,text,timestamptz)',
    'EXECUTE'
  )
  and has_function_privilege(
    'service_role',
    'public.fail_verification_email_recovery(text,uuid,text,text)',
    'EXECUTE'
  )
  and has_function_privilege(
    'service_role',
    'public.consume_verification_email_recovery_token(text,text)',
    'EXECUTE'
  ),
  'service role cannot execute the race-safe RPC surface'
);

select pg_temp.assert_true(
  to_regprocedure('public.claim_verification_email_recovery(uuid)') is null
  and to_regprocedure(
    'public.prepare_verification_email_recovery(text,uuid,text,timestamptz,text,timestamptz)'
  ) is null,
  'an unscoped legacy transition remains callable'
);

select pg_temp.assert_true(
  not has_schema_privilege('service_role', 'private', 'USAGE')
  and not has_table_privilege(
    'service_role', 'private.verification_email_recovery_attempts', 'SELECT'
  ),
  'private recovery state is directly reachable'
);

insert into public.users (
  id, email, password_hash, is_verified,
  verification_token_hash, verification_token_expires
)
select
  ('10000000-0000-0000-0000-' || lpad(n::text, 12, '0'))::uuid,
  'recovery-' || n || '@test.invalid',
  'x', false, lpad(to_hex(n), 64, '0'),
  pg_catalog.clock_timestamp() + interval '24 hours'
from generate_series(1, 14) as series(n);

-- Webhook-before-registration and registration-before-webhook converge.
select pg_catalog.clock_timestamp() as event_first_at \gset
set role service_role;
select public.record_resend_delivery_event_and_recovery(
  repeat('01', 32), repeat('11', 32), repeat('21', 32), 'test',
  'verification', 'email.delivery_delayed', 'transient',
  :'event_first_at'::timestamptz
);
select public.register_verification_email_recovery_attempt(
  repeat('11', 32), '10000000-0000-0000-0000-000000000001', 'test',
  (select verification_token_expires from public.users
   where id = '10000000-0000-0000-0000-000000000001')
);
select public.register_verification_email_recovery_attempt(
  repeat('12', 32), '10000000-0000-0000-0000-000000000002', 'test',
  (select verification_token_expires from public.users
   where id = '10000000-0000-0000-0000-000000000002')
);
select public.record_resend_delivery_event_and_recovery(
  repeat('02', 32), repeat('12', 32), repeat('22', 32), 'test',
  'verification', 'email.delivery_delayed', 'transient',
  pg_catalog.clock_timestamp()
);
reset role;

select pg_temp.assert_true(
  (select state = 'eligible' and outcome_class = 'transient'
   from private.verification_email_recovery_attempts
   where provider_email_hash = repeat('11', 32))
  and
  (select state = 'eligible' and outcome_class = 'transient'
   from private.verification_email_recovery_attempts
   where provider_email_hash = repeat('12', 32)),
  'event-first and registration-first orderings did not converge'
);

-- Simulate the exact historical lost-race final state without using the
-- reconciling wrapper: the signed event committed, but registration remained
-- `sent`. The next environment-scoped claim must repair it before claiming.
set role service_role;
select public.register_verification_email_recovery_attempt(
  repeat('2a', 32), '10000000-0000-0000-0000-000000000013', 'test',
  (select verification_token_expires from public.users
   where id = '10000000-0000-0000-0000-000000000013')
);
select public.record_resend_delivery_event(
  repeat('3a', 32), repeat('2a', 32), repeat('4a', 32), 'test',
  'verification', 'email.delivery_delayed', 'transient',
  pg_catalog.clock_timestamp()
);
reset role;
select pg_temp.assert_true(
  (select state = 'sent' and outcome_class = 'accepted'
   from private.verification_email_recovery_attempts
   where provider_email_hash = repeat('2a', 32)),
  'lost-race fixture did not preserve the missed sent state'
);
set role service_role;
do $$
begin
  perform * from public.claim_verification_email_recovery(
    '20000000-0000-0000-0000-000000000013', 'test'
  );
end;
$$;
reset role;
select pg_temp.assert_true(
  (select state = 'eligible' and outcome_class = 'transient'
   from private.verification_email_recovery_attempts
   where provider_email_hash = repeat('2a', 32)),
  'claim-time reconciliation did not repair the lost callback race'
);

-- Same signed payload under another event ID resolves by fingerprint and ACKs;
-- conflicting semantics under either uniqueness identity still fail closed.
set role service_role;
select pg_temp.assert_true(
  not public.record_resend_delivery_event_and_recovery(
    repeat('03', 32), repeat('11', 32), repeat('21', 32), 'test',
    'verification', 'email.delivery_delayed', 'transient',
    :'event_first_at'::timestamptz
  ),
  'same-payload replay under another event ID was not success-equivalent'
);
do $$
begin
  begin
    perform public.record_resend_delivery_event_and_recovery(
      repeat('04', 32), repeat('11', 32), repeat('21', 32), 'test',
      'verification', 'email.delivered', 'delivered',
      pg_catalog.clock_timestamp()
    );
    raise exception 'semantic replay conflict was accepted';
  exception when sqlstate '22023' then
    null;
  end;
end;
$$;
reset role;

-- Monotonic outcome: delivered -> complaint -> replay delivered remains terminal.
select pg_catalog.clock_timestamp() as delivered_at \gset
set role service_role;
select public.register_verification_email_recovery_attempt(
  repeat('13', 32), '10000000-0000-0000-0000-000000000003', 'test',
  (select verification_token_expires from public.users
   where id = '10000000-0000-0000-0000-000000000003')
);
select public.record_resend_delivery_event_and_recovery(
  repeat('05', 32), repeat('13', 32), repeat('23', 32), 'test',
  'verification', 'email.delivered', 'delivered', :'delivered_at'::timestamptz
);
select public.record_resend_delivery_event_and_recovery(
  repeat('06', 32), repeat('13', 32), repeat('24', 32), 'test',
  'verification', 'email.complained', 'complaint', pg_catalog.clock_timestamp()
);
select pg_temp.assert_true(
  not public.record_resend_delivery_event_and_recovery(
    repeat('05', 32), repeat('13', 32), repeat('23', 32), 'test',
    'verification', 'email.delivered', 'delivered',
    :'delivered_at'::timestamptz
  ),
  'exact delivered replay was not idempotent'
);
reset role;
select pg_temp.assert_true(
  (select state = 'terminal' and outcome_class = 'complaint'
   from private.verification_email_recovery_attempts
   where provider_email_hash = repeat('13', 32)),
  'terminal outcome was downgraded by delivered replay'
);

-- Ambiguous prepare response: exact replay succeeds, consumes one attempt, and
-- never changes the only already-delivered user token.
update private.verification_email_recovery_attempts
set retry_after = pg_catalog.clock_timestamp() - interval '1 second'
where provider_email_hash = repeat('11', 32);
set role service_role;
do $$
declare
  claimed record;
  fresh_expiry timestamptz := pg_catalog.clock_timestamp() + interval '24 hours';
begin
  select * into strict claimed from public.claim_verification_email_recovery(
    '20000000-0000-0000-0000-000000000001', 'test'
  );
  if not public.prepare_verification_email_recovery(
    claimed.provider_email_hash, claimed.claim_token,
    claimed.previous_token_hash, claimed.previous_token_expires_at,
    repeat('91', 32), fresh_expiry, 'test'
  ) then
    raise exception 'first prepare failed';
  end if;
  -- Simulates first commit succeeding while its response is lost.
  if not public.prepare_verification_email_recovery(
    claimed.provider_email_hash, claimed.claim_token,
    claimed.previous_token_hash, claimed.previous_token_expires_at,
    repeat('91', 32), fresh_expiry, 'test'
  ) then
    raise exception 'ambiguous prepare replay was not success-equivalent';
  end if;
end;
$$;
reset role;
select pg_temp.assert_true(
  (select state = 'prepared' and attempt_count = 1
     and recovery_token_hash = repeat('91', 32)
   from private.verification_email_recovery_attempts
   where provider_email_hash = repeat('11', 32))
  and
  (select verification_token_hash = lpad(to_hex(1), 64, '0')
   from public.users where id = '10000000-0000-0000-0000-000000000001'),
  'prepare replay changed the original token or consumed two attempts'
);

-- Prepare all four pre-authorization terminal races plus verified-account race.
set role service_role;
select public.register_verification_email_recovery_attempt(
  repeat('14', 32), '10000000-0000-0000-0000-000000000004', 'test',
  (select verification_token_expires from public.users where id='10000000-0000-0000-0000-000000000004'));
select public.register_verification_email_recovery_attempt(
  repeat('15', 32), '10000000-0000-0000-0000-000000000005', 'test',
  (select verification_token_expires from public.users where id='10000000-0000-0000-0000-000000000005'));
select public.register_verification_email_recovery_attempt(
  repeat('16', 32), '10000000-0000-0000-0000-000000000006', 'test',
  (select verification_token_expires from public.users where id='10000000-0000-0000-0000-000000000006'));
select public.register_verification_email_recovery_attempt(
  repeat('17', 32), '10000000-0000-0000-0000-000000000007', 'test',
  (select verification_token_expires from public.users where id='10000000-0000-0000-0000-000000000007'));
select public.register_verification_email_recovery_attempt(
  repeat('18', 32), '10000000-0000-0000-0000-000000000008', 'test',
  (select verification_token_expires from public.users where id='10000000-0000-0000-0000-000000000008'));
select public.record_resend_delivery_event_and_recovery(repeat('34',32),repeat('14',32),repeat('44',32),'test','verification','email.delivery_delayed','transient',pg_catalog.clock_timestamp());
select public.record_resend_delivery_event_and_recovery(repeat('35',32),repeat('15',32),repeat('45',32),'test','verification','email.delivery_delayed','transient',pg_catalog.clock_timestamp());
select public.record_resend_delivery_event_and_recovery(repeat('36',32),repeat('16',32),repeat('46',32),'test','verification','email.delivery_delayed','transient',pg_catalog.clock_timestamp());
select public.record_resend_delivery_event_and_recovery(repeat('37',32),repeat('17',32),repeat('47',32),'test','verification','email.delivery_delayed','transient',pg_catalog.clock_timestamp());
select public.record_resend_delivery_event_and_recovery(repeat('38',32),repeat('18',32),repeat('48',32),'test','verification','email.delivery_delayed','transient',pg_catalog.clock_timestamp());
reset role;
update private.verification_email_recovery_attempts
set retry_after = pg_catalog.clock_timestamp() - interval '1 second'
where provider_email_hash in (
  repeat('14',32), repeat('15',32), repeat('16',32), repeat('17',32), repeat('18',32)
);

set role service_role;
do $$
declare
  hashes text[] := array[repeat('14',32),repeat('15',32),repeat('16',32),repeat('17',32),repeat('18',32)];
  claim_ids uuid[] := array[
    '20000000-0000-0000-0000-000000000004'::uuid,
    '20000000-0000-0000-0000-000000000005'::uuid,
    '20000000-0000-0000-0000-000000000006'::uuid,
    '20000000-0000-0000-0000-000000000007'::uuid,
    '20000000-0000-0000-0000-000000000008'::uuid
  ];
  claimed record;
  i integer;
begin
  for i in 1..5 loop
    select * into strict claimed from public.claim_verification_email_recovery(
      claim_ids[i], 'test'
    );
    if claimed.provider_email_hash <> hashes[i] then
      raise exception 'claim order drifted in pre-authorization fixture';
    end if;
    if not public.prepare_verification_email_recovery(
      hashes[i], claim_ids[i], claimed.previous_token_hash,
      claimed.previous_token_expires_at, lpad(to_hex(160+i),64,'0'),
      pg_catalog.clock_timestamp()+interval '24 hours', 'test'
    ) then
      raise exception 'pre-authorization fixture did not prepare';
    end if;
  end loop;
end;
$$;
select public.record_resend_delivery_event_and_recovery(repeat('54',32),repeat('14',32),repeat('64',32),'test','verification','email.delivered','delivered',pg_catalog.clock_timestamp());
select public.record_resend_delivery_event_and_recovery(repeat('55',32),repeat('15',32),repeat('65',32),'test','verification','email.bounced','permanent',pg_catalog.clock_timestamp());
select public.record_resend_delivery_event_and_recovery(repeat('56',32),repeat('16',32),repeat('66',32),'test','verification','email.suppressed','suppressed',pg_catalog.clock_timestamp());
select public.record_resend_delivery_event_and_recovery(repeat('57',32),repeat('17',32),repeat('67',32),'test','verification','email.complained','complaint',pg_catalog.clock_timestamp());
reset role;
update public.users set is_verified = true
where id = '10000000-0000-0000-0000-000000000008';
set role service_role;
do $$
declare
  hashes text[] := array[repeat('14',32),repeat('15',32),repeat('16',32),repeat('17',32),repeat('18',32)];
  claim_ids uuid[] := array[
    '20000000-0000-0000-0000-000000000004'::uuid,
    '20000000-0000-0000-0000-000000000005'::uuid,
    '20000000-0000-0000-0000-000000000006'::uuid,
    '20000000-0000-0000-0000-000000000007'::uuid,
    '20000000-0000-0000-0000-000000000008'::uuid
  ];
  i integer;
begin
  for i in 1..5 loop
    if public.authorize_verification_email_recovery_dispatch(
      hashes[i], claim_ids[i], 'test', lpad(to_hex(i+3),64,'0'),
      (select verification_token_expires from public.users
       where id=('10000000-0000-0000-0000-'||lpad((i+3)::text,12,'0'))::uuid),
      lpad(to_hex(160+i),64,'0')
    ) then
      raise exception 'pre-authorization terminal/verified race authorized I/O';
    end if;
  end loop;
end;
$$;
reset role;
select pg_temp.assert_true(
  not exists (
    select 1 from private.verification_email_recovery_attempts
    where provider_email_hash in (
      repeat('14',32),repeat('15',32),repeat('16',32),repeat('17',32),repeat('18',32)
    ) and state in ('prepared','dispatch_authorized')
  ),
  'a delivered/permanent/suppressed/complaint/verified pre-auth race can send'
);
select pg_temp.assert_true(
  (select verification_token_hash=lpad(to_hex(4),64,'0') from public.users where id='10000000-0000-0000-0000-000000000004')
  and (select verification_token_hash=lpad(to_hex(5),64,'0') from public.users where id='10000000-0000-0000-0000-000000000005')
  and (select verification_token_hash=lpad(to_hex(6),64,'0') from public.users where id='10000000-0000-0000-0000-000000000006')
  and (select verification_token_hash=lpad(to_hex(7),64,'0') from public.users where id='10000000-0000-0000-0000-000000000007'),
  'pre-authorization race invalidated an original token'
);

-- Authorize the ambiguous-prepare row. A later terminal callback cannot revoke
-- authorization; send wins, completion is durable, and the digest is usable.
set role service_role;
select pg_temp.assert_true(
  public.authorize_verification_email_recovery_dispatch(
    repeat('11',32), '20000000-0000-0000-0000-000000000001', 'test',
    lpad(to_hex(1),64,'0'),
    (select verification_token_expires from public.users where id='10000000-0000-0000-0000-000000000001'),
    repeat('91',32)
  ), 'dispatch authorization failed'
);
select pg_temp.assert_true(
  public.authorize_verification_email_recovery_dispatch(
    repeat('11',32), '20000000-0000-0000-0000-000000000001', 'test',
    lpad(to_hex(1),64,'0'),
    (select verification_token_expires from public.users where id='10000000-0000-0000-0000-000000000001'),
    repeat('91',32)
  ), 'dispatch authorization replay failed'
);
select public.record_resend_delivery_event_and_recovery(
  repeat('71',32), repeat('11',32), repeat('81',32), 'test',
  'verification', 'email.complained', 'complaint', pg_catalog.clock_timestamp()
);
reset role;
select recovery_token_expires_at as authorized_recovery_expiry
from private.verification_email_recovery_attempts
where provider_email_hash=repeat('11',32) \gset
set role service_role;
select pg_temp.assert_true(
  public.complete_verification_email_recovery(
    repeat('11',32), '20000000-0000-0000-0000-000000000001',
    repeat('92',32), 'test', repeat('91',32),
    :'authorized_recovery_expiry'::timestamptz
  ), 'authorized send did not win after terminal callback'
);
select pg_temp.assert_true(
  public.consume_verification_email_recovery_token(repeat('91',32),'test')
    = '10000000-0000-0000-0000-000000000001'::uuid,
  'authorized durable recovery digest was not consumable'
);
select pg_temp.assert_true(
  (select is_verified
      and verification_token_hash = lpad(to_hex(1),64,'0')
      and verification_token_expires > pg_catalog.clock_timestamp()
   from public.users
   where id = '10000000-0000-0000-0000-000000000001'),
  'recovery-first verification invalidated the usable original link'
);
select pg_temp.assert_true(
  public.consume_verification_email_recovery_token(repeat('91',32),'test')
    = '10000000-0000-0000-0000-000000000001'::uuid,
  'ambiguous recovery-token consumption replay was not success-equivalent'
);
reset role;

-- Original-first then recovery, followed by both replay paths, is also
-- success-equivalent. The original digest remains the user's only public hash.
set role service_role;
select public.register_verification_email_recovery_attempt(
  repeat('2b',32), '10000000-0000-0000-0000-000000000014', 'test',
  (select verification_token_expires from public.users
   where id='10000000-0000-0000-0000-000000000014')
);
select public.record_resend_delivery_event_and_recovery(
  repeat('3b',32), repeat('2b',32), repeat('4b',32), 'test',
  'verification', 'email.delivery_delayed', 'transient',
  pg_catalog.clock_timestamp()
);
reset role;
update private.verification_email_recovery_attempts
set retry_after = pg_catalog.clock_timestamp() - interval '1 second'
where provider_email_hash = repeat('2b',32);
set role service_role;
do $$
declare
  claimed record;
  recovery_expiry timestamptz := pg_catalog.clock_timestamp() + interval '24 hours';
begin
  select * into strict claimed from public.claim_verification_email_recovery(
    '20000000-0000-0000-0000-000000000014', 'test'
  );
  if claimed.provider_email_hash <> repeat('2b',32) then
    raise exception 'original-first fixture claimed the wrong attempt';
  end if;
  if not public.prepare_verification_email_recovery(
    repeat('2b',32), claimed.claim_token, claimed.previous_token_hash,
    claimed.previous_token_expires_at, repeat('5b',32), recovery_expiry,
    'test'
  ) then
    raise exception 'original-first fixture did not prepare';
  end if;
  if not public.authorize_verification_email_recovery_dispatch(
    repeat('2b',32), claimed.claim_token, 'test',
    claimed.previous_token_hash, claimed.previous_token_expires_at,
    repeat('5b',32)
  ) then
    raise exception 'original-first fixture did not authorize';
  end if;
  if not public.complete_verification_email_recovery(
    repeat('2b',32), claimed.claim_token, repeat('6b',32), 'test',
    repeat('5b',32), recovery_expiry
  ) then
    raise exception 'original-first fixture did not complete';
  end if;
end;
$$;
reset role;
-- Mirror the ordinary original-link route: mark verified and shorten only its
-- expiry, while retaining the original digest for scanner-safe replay.
update public.users
set is_verified = true,
    verification_token_expires = pg_catalog.clock_timestamp() + interval '15 minutes'
where id = '10000000-0000-0000-0000-000000000014'
  and verification_token_hash = lpad(to_hex(14),64,'0');
set role service_role;
select pg_temp.assert_true(
  public.consume_verification_email_recovery_token(repeat('5b',32),'test')
    = '10000000-0000-0000-0000-000000000014'::uuid,
  'original-first recovery link was not success-equivalent'
);
select pg_temp.assert_true(
  public.consume_verification_email_recovery_token(repeat('5b',32),'test')
    = '10000000-0000-0000-0000-000000000014'::uuid,
  'original-first recovery replay failed'
);
reset role;
select pg_temp.assert_true(
  (select is_verified
      and verification_token_hash = lpad(to_hex(14),64,'0')
      and verification_token_expires > pg_catalog.clock_timestamp()
   from public.users
   where id='10000000-0000-0000-0000-000000000014'),
  'original-first flow lost its original replay digest'
);
select pg_temp.assert_true(
  (select not is_verified
      and verification_token_hash = lpad(to_hex(13),64,'0')
   from public.users
   where id='10000000-0000-0000-0000-000000000013'),
  'recovery consumption crossed into a foreign user'
);
update public.users
set verification_token_expires = pg_catalog.clock_timestamp() - interval '1 second'
where id='10000000-0000-0000-0000-000000000014';
update private.verification_email_recovery_attempts
set recovery_token_expires_at = pg_catalog.clock_timestamp() - interval '1 second'
where provider_email_hash=repeat('2b',32);
set role service_role;
select pg_temp.assert_true(
  public.consume_verification_email_recovery_token(repeat('5b',32),'test') is null
  and public.consume_verification_email_recovery_token(repeat('5b',32),'preview') is null,
  'expired or cross-environment recovery token was accepted'
);
reset role;

-- Mixed-environment claim/cleanup is strictly scoped.
set role service_role;
select public.register_verification_email_recovery_attempt(
  repeat('19',32), '10000000-0000-0000-0000-000000000009', 'preview',
  (select verification_token_expires from public.users where id='10000000-0000-0000-0000-000000000009'));
select public.register_verification_email_recovery_attempt(
  repeat('20',32), '10000000-0000-0000-0000-000000000010', 'test',
  (select verification_token_expires from public.users where id='10000000-0000-0000-0000-000000000010'));
select public.record_resend_delivery_event_and_recovery(repeat('79',32),repeat('19',32),repeat('89',32),'preview','verification','email.delivery_delayed','transient',pg_catalog.clock_timestamp());
select public.record_resend_delivery_event_and_recovery(repeat('80',32),repeat('20',32),repeat('90',32),'test','verification','email.delivery_delayed','transient',pg_catalog.clock_timestamp());
reset role;
update private.verification_email_recovery_attempts set retry_after=pg_catalog.clock_timestamp()-interval '1 second'
where provider_email_hash in (repeat('19',32),repeat('20',32));
set role service_role;
do $$
declare claimed record;
begin
  select * into strict claimed from public.claim_verification_email_recovery(
    '20000000-0000-0000-0000-000000000010','test'
  );
  if claimed.provider_email_hash <> repeat('20',32) then
    raise exception 'test worker crossed into preview';
  end if;
end;
$$;
reset role;
select pg_temp.assert_true(
  (select state='eligible' from private.verification_email_recovery_attempts
   where provider_email_hash=repeat('19',32) and environment='preview')
  and
  (select state='claimed' from private.verification_email_recovery_attempts
   where provider_email_hash=repeat('20',32) and environment='test'),
  'claim or cleanup crossed environment scope'
);

select pg_temp.assert_true(
  not exists (
    select 1 from private.verification_email_recovery_attempts
    where attempt_count > 1
  ),
  'one-shot attempt ceiling was exceeded'
);
