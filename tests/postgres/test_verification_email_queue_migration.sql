\set ON_ERROR_STOP on

create or replace function pg_temp.assert_true(condition boolean, failure_message text)
returns void language plpgsql as $$
begin
  if condition is not true then
    raise exception 'verification-email queue gate failed: %', failure_message;
  end if;
end;
$$;

select pg_temp.assert_true(
  (select relrowsecurity and relforcerowsecurity
   from pg_catalog.pg_class
   where oid = 'public.verification_email_jobs'::regclass),
  'queue RLS must be enabled and forced'
);
select pg_temp.assert_true(
  not pg_catalog.has_table_privilege('service_role', 'public.verification_email_jobs', 'SELECT')
  and not pg_catalog.has_table_privilege('service_role', 'public.verification_email_jobs', 'INSERT')
  and not pg_catalog.has_table_privilege('anon', 'public.verification_email_jobs', 'SELECT')
  and not pg_catalog.has_table_privilege('authenticated', 'public.verification_email_jobs', 'SELECT'),
  'queue table must remain RPC-only'
);
select pg_temp.assert_true(
  (select pg_catalog.count(*) = 0
   from information_schema.columns
   where table_schema = 'public'
     and table_name = 'verification_email_jobs'
     and column_name in ('email', 'recipient_email', 'name', 'token', 'alias', 'body', 'secret')),
  'queue must store no raw recipient, bearer, alias, body, name, or secret'
);

do $$
declare
  signature text;
  oid_value oid;
begin
  foreach signature in array array[
    'public.enqueue_verification_email_job_v1(uuid,text,text,text,timestamp with time zone,text,text,text,text,text,text,text,text,text)',
    'public.claim_verification_email_job_v1(uuid,integer)',
    'public.stage_verification_email_job_v1(uuid,uuid)',
    'public.complete_verification_email_job_v1(uuid,uuid,text)',
    'public.release_verification_email_job_v1(uuid,uuid,text,boolean,integer)'
  ] loop
    oid_value := pg_catalog.to_regprocedure(signature);
    perform pg_temp.assert_true(oid_value is not null, 'missing RPC ' || signature);
    perform pg_temp.assert_true(
      pg_catalog.has_function_privilege('service_role', oid_value, 'EXECUTE')
      and not pg_catalog.has_function_privilege('anon', oid_value, 'EXECUTE')
      and not pg_catalog.has_function_privilege('authenticated', oid_value, 'EXECUTE'),
      'unsafe RPC ACL ' || signature
    );
    perform pg_temp.assert_true(
      (select proc_row.prosecdef
         and proc_row.provolatile = 'v'
         and proc_row.proconfig = array['search_path=""']::text[]
       from pg_catalog.pg_proc as proc_row where proc_row.oid = oid_value),
      'unsafe RPC execution contract ' || signature
    );
  end loop;
end;
$$;

insert into public.users (
  id, email, is_verified, verification_token_hash, verification_token_expires
) values
  ('11111111-1111-4111-8111-111111111111', 'pending@example.com', false, repeat('a', 64), now() + interval '20 hours'),
  ('22222222-2222-4222-8222-222222222222', 'verified@example.com', true, repeat('b', 64), now() + interval '20 hours'),
  ('33333333-3333-4333-8333-333333333333', 'expired@example.com', false, repeat('c', 64), now() - interval '1 hour');

do $$
declare
  plan_line text;
  plan_text text := '';
begin
  perform pg_catalog.set_config('enable_seqscan', 'off', true);
  for plan_line in execute $explain$
    explain (costs off)
    select id
    from public.verification_email_jobs
    where status = 'queued' and next_attempt_at <= pg_catalog.clock_timestamp()
    order by next_attempt_at, created_at, id
    limit 1
  $explain$ loop
    plan_text := plan_text || plan_line;
  end loop;
  perform pg_temp.assert_true(
    pg_catalog.strpos(plan_text, 'verification_email_jobs_ready_idx') > 0,
    'ready-job claim plan must use the reviewed partial index'
  );

  plan_text := '';
  for plan_line in execute $explain$
    explain (costs off)
    select id
    from public.verification_email_jobs
    where claim_token_history @> array['eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'::uuid]
  $explain$ loop
    plan_text := plan_text || plan_line;
  end loop;
  perform pg_temp.assert_true(
    pg_catalog.strpos(plan_text, 'verification_email_jobs_claim_token_history_idx') > 0,
    'claim-token replay must use the reviewed GIN index'
  );

  plan_text := '';
  for plan_line in execute $explain$
    explain (costs off)
    select id
    from public.users
    where lower(email) = 'pending@example.com'
  $explain$ loop
    plan_text := plan_text || plan_line;
  end loop;
  perform pg_temp.assert_true(
    pg_catalog.strpos(plan_text, 'users_email_lower_unique') > 0,
    'account lookup plan must use the lower-email unique index'
  );
end;
$$;

set role service_role;

do $$
declare
  null_completion_rejected boolean := false;
  null_failure_rejected boolean := false;
begin
  begin
    perform public.complete_verification_email_job_v1(
      '00000000-0000-4000-8000-000000000001',
      '00000000-0000-4000-8000-000000000002',
      null
    );
  exception when sqlstate '22023' then
    null_completion_rejected := true;
  end;
  begin
    perform public.release_verification_email_job_v1(
      '00000000-0000-4000-8000-000000000001',
      '00000000-0000-4000-8000-000000000002',
      null,
      true,
      0
    );
  exception when sqlstate '22023' then
    null_failure_rejected := true;
  end;
  if not null_completion_rejected or not null_failure_rejected then
    raise exception 'null completion or failure classification was not rejected';
  end if;
end;
$$;

select * from public.enqueue_verification_email_job_v1(
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'pending@example.com', repeat('1', 64),
  repeat('d', 64), now() + interval '24 hours', 'k1', 'pending_nonce_123456789',
  'presentation', 'professional', 'verification-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>'
);
select * from public.enqueue_verification_email_job_v1(
  'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'missing@example.com', repeat('2', 64),
  repeat('e', 64), now() + interval '24 hours', 'k1', 'missing_nonce_1234567890',
  null, null, 'verification-v1', 'Ask Crump', 'https://www.askcrump.com',
  'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>'
);
select * from public.enqueue_verification_email_job_v1(
  'cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'verified@example.com', repeat('3', 64),
  repeat('f', 64), now() + interval '24 hours', 'k1', 'verified_nonce_12345678',
  null, null, 'verification-v1', 'Ask Crump', 'https://www.askcrump.com',
  'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>'
);
select * from public.enqueue_verification_email_job_v1(
  'dddddddd-dddd-4ddd-8ddd-dddddddddddd', 'expired@example.com', repeat('4', 64),
  repeat('9', 64), now() + interval '24 hours', 'k1', 'expired_nonce_123456789',
  null, null, 'verification-v1', 'Ask Crump', 'https://www.askcrump.com',
  'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>'
);

-- A database-client retry may replay the same immutable envelope. A UUID
-- collision with changed immutable inputs must fail closed instead of silently
-- adopting another job's recipient or renderer contract.
select * from public.enqueue_verification_email_job_v1(
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'pending@example.com', repeat('1', 64),
  repeat('d', 64), now() + interval '24 hours', 'k1', 'pending_nonce_123456789',
  'presentation', 'professional', 'verification-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>'
);
do $$
declare
  mismatch_rejected boolean := false;
begin
  begin
    perform * from public.enqueue_verification_email_job_v1(
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'pending@example.com', repeat('1', 64),
      repeat('d', 64), now() + interval '24 hours', 'k1', 'different_nonce_12345678',
      'presentation', 'professional', 'verification-v1', 'Ask Crump',
      'https://www.askcrump.com', 'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>'
    );
  exception when unique_violation then
    mismatch_rejected := true;
  end;
  if not mismatch_rejected then
    raise exception 'job-id replay mismatch was not rejected';
  end if;
end;
$$;

reset role;

select pg_temp.assert_true(
  (select verification_token_hash = repeat('a', 64)
   from public.users where email = 'pending@example.com'),
  'a live pending anchor must remain immutable'
);
select pg_temp.assert_true(
  (select verification_token_hash = repeat('9', 64)
   from public.users where email = 'expired@example.com'),
  'an expired generation must rotate atomically'
);
select pg_temp.assert_true(
  (select status = 'suppressed' and user_id is null
   from public.verification_email_jobs where id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),
  'an unknown account must create only a content-free suppression envelope'
);
select pg_temp.assert_true(
  (select status = 'suppressed' and user_id is null
   from public.verification_email_jobs where id = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'),
  'a verified account must create only a content-free suppression envelope'
);
select pg_temp.assert_true(
  (select count(*) = 1
   from public.verification_email_jobs where id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
  'an exact enqueue replay must not create a duplicate job'
);

set role service_role;
select * from public.claim_verification_email_job_v1(
  'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', 120
) \gset claimed_
select pg_temp.assert_true(:'claimed_job_id' <> '', 'a deliverable row must be claimed');
select * from public.stage_verification_email_job_v1(
  :'claimed_job_id'::uuid, :'claimed_lease_token'::uuid
) \gset staged_
select pg_temp.assert_true(:'staged_disposition' = 'deliver', 'pending account must stage for delivery');
select pg_temp.assert_true(:'staged_recipient_email' in ('pending@example.com', 'expired@example.com'), 'stage returns only the locked current recipient');
select pg_temp.assert_true(
  public.complete_verification_email_job_v1(
    :'claimed_job_id'::uuid, :'claimed_lease_token'::uuid, 'provider_accepted'
  ) = 'provider_accepted',
  'a live staged lease must complete as provider accepted'
);
reset role;

select pg_temp.assert_true(
  (select status = 'provider_accepted'
      and terminal_at is not null
      and claim_token_history = array[:'claimed_lease_token'::uuid]
      and pg_catalog.cardinality(claim_token_history) = attempts
   from public.verification_email_jobs where id = :'claimed_job_id'::uuid),
  'provider acceptance must be terminal and retain its one-shot claim token'
);

update public.verification_email_jobs
set next_attempt_at = pg_catalog.clock_timestamp() + interval '1 hour'
where status = 'queued';

insert into public.verification_email_jobs (
  id, delivery_mode, recipient_fingerprint, verification_token_hash,
  verification_token_expires, alias_key_id, alias_nonce, status,
  next_attempt_at, template_version, app_name, app_url, support_email,
  from_email
) values (
  '44444444-4444-4444-8444-444444444444', 'suppressed', repeat('4', 64),
  repeat('5', 64), pg_catalog.clock_timestamp() + interval '20 hours', 'k1',
  'retry_queue_nonce_123456', 'queued', pg_catalog.clock_timestamp() - interval '1 minute',
  'verification-v1', 'Ask Crump', 'https://www.askcrump.com',
  'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>'
);
set role service_role;
select * from public.claim_verification_email_job_v1(
  '44444444-4444-4444-8444-444444444445', 120
) \gset retry_
select pg_temp.assert_true(
  public.release_verification_email_job_v1(
    :'retry_job_id'::uuid, :'retry_lease_token'::uuid,
    'PROVIDER_UNAVAILABLE', true, 45
  ) = 'retry_scheduled',
  'retryable failure must schedule bounded backoff'
);
reset role;
select pg_temp.assert_true(
  (select status = 'queued'
      and attempts = 1
      and next_attempt_at >= pg_catalog.clock_timestamp() + interval '40 seconds'
      and lease_token is null
      and claim_token_history = array['44444444-4444-4444-8444-444444444445'::uuid]
      and last_failure_code = 'PROVIDER_UNAVAILABLE'
   from public.verification_email_jobs
   where id = '44444444-4444-4444-8444-444444444444'),
  'retry scheduling must retain history and clear the active lease'
);
update public.verification_email_jobs
set next_attempt_at = pg_catalog.clock_timestamp() - interval '1 second'
where id = '44444444-4444-4444-8444-444444444444';
set role service_role;
select * from public.claim_verification_email_job_v1(
  '44444444-4444-4444-8444-444444444446', 120
) \gset permanent_
select pg_temp.assert_true(
  public.release_verification_email_job_v1(
    :'permanent_job_id'::uuid, :'permanent_lease_token'::uuid,
    'PROVIDER_REJECTED', false, null
  ) = 'failed_permanent',
  'non-retryable failure must become terminal'
);
reset role;
select pg_temp.assert_true(
  (select status = 'failed_permanent'
      and terminal_at is not null
      and pg_catalog.cardinality(claim_token_history) = 2
   from public.verification_email_jobs
   where id = '44444444-4444-4444-8444-444444444444'),
  'non-retryable failure must preserve both claim tokens'
);

insert into public.verification_email_jobs (
  id, delivery_mode, recipient_fingerprint, verification_token_hash,
  verification_token_expires, alias_key_id, alias_nonce, status, attempts,
  next_attempt_at, template_version, app_name, app_url, support_email,
  from_email, claim_token_history
) values (
  '55555555-5555-4555-8555-555555555555', 'suppressed', repeat('5', 64),
  repeat('6', 64), pg_catalog.clock_timestamp() + interval '20 hours', 'k1',
  'attempt_queue_nonce_123456', 'queued', 5,
  pg_catalog.clock_timestamp() - interval '1 minute', 'verification-v1',
  'Ask Crump', 'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>', array[
    '55000000-0000-4000-8000-000000000001'::uuid,
    '55000000-0000-4000-8000-000000000002'::uuid,
    '55000000-0000-4000-8000-000000000003'::uuid,
    '55000000-0000-4000-8000-000000000004'::uuid,
    '55000000-0000-4000-8000-000000000005'::uuid
  ]
);
set role service_role;
select * from public.claim_verification_email_job_v1(
  '55555555-5555-4555-8555-555555555556', 120
) \gset exhausted_
select pg_temp.assert_true(
  public.release_verification_email_job_v1(
    :'exhausted_job_id'::uuid, :'exhausted_lease_token'::uuid,
    'PROVIDER_UNAVAILABLE', true, 30
  ) = 'failed_permanent',
  'sixth failed attempt must become terminal'
);
reset role;
select pg_temp.assert_true(
  (select status = 'failed_permanent'
      and attempts = 6
      and pg_catalog.cardinality(claim_token_history) = 6
   from public.verification_email_jobs
   where id = '55555555-5555-4555-8555-555555555555'),
  'attempt exhaustion must be terminal and retain fencing history'
);

insert into public.verification_email_jobs (
  id, delivery_mode, recipient_fingerprint, verification_token_hash,
  verification_token_expires, alias_key_id, alias_nonce, status,
  next_attempt_at, template_version, app_name, app_url, support_email,
  from_email
) values (
  '66666666-6666-4666-8666-666666666666', 'suppressed', repeat('6', 64),
  repeat('7', 64), pg_catalog.clock_timestamp() + interval '4 minutes', 'k1',
  'expiry_queue_nonce_123456', 'queued', pg_catalog.clock_timestamp() - interval '1 minute',
  'verification-v1', 'Ask Crump', 'https://www.askcrump.com',
  'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>'
);
set role service_role;
select pg_temp.assert_true(
  (select count(*) = 0 from public.claim_verification_email_job_v1(
    '66666666-6666-4666-8666-666666666667', 120
  )),
  'near-expiry work must not be claimed'
);
reset role;
select pg_temp.assert_true(
  (select status = 'failed_permanent'
      and last_failure_code = 'JOB_INTEGRITY_INVALID'
   from public.verification_email_jobs
   where id = '66666666-6666-4666-8666-666666666666'),
  'near-expiry work must be suppressed by cleanup'
);

insert into public.verification_email_jobs (
  id, delivery_mode, recipient_fingerprint, verification_token_hash,
  verification_token_expires, alias_key_id, alias_nonce, status,
  next_attempt_at, template_version, app_name, app_url, support_email,
  from_email, terminal_at, created_at, updated_at
) values (
  '77777777-7777-4777-8777-777777777777', 'suppressed', repeat('7', 64),
  repeat('8', 64), pg_catalog.clock_timestamp() + interval '20 hours', 'k1',
  'cleanup_queue_nonce_12345', 'failed_permanent', pg_catalog.clock_timestamp(),
  'verification-v1', 'Ask Crump', 'https://www.askcrump.com',
  'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>',
  pg_catalog.clock_timestamp() - interval '8 days',
  pg_catalog.clock_timestamp() - interval '8 days',
  pg_catalog.clock_timestamp() - interval '8 days'
);
set role service_role;
select pg_temp.assert_true(
  (select count(*) = 0 from public.claim_verification_email_job_v1(
    '77777777-7777-4777-8777-777777777778', 120
  )),
  'cleanup-only claim must remain empty'
);
reset role;
select pg_temp.assert_true(
  not exists (
    select 1 from public.verification_email_jobs
    where id = '77777777-7777-4777-8777-777777777777'
  ),
  'terminal rows older than seven days must be deleted'
);

delete from public.users where id = '33333333-3333-4333-8333-333333333333';
select pg_temp.assert_true(
  not exists (
    select 1 from public.verification_email_jobs
    where user_id = '33333333-3333-4333-8333-333333333333'
  ),
  'account deletion must cascade queued verification mail'
);

delete from public.verification_email_jobs;
insert into public.verification_email_jobs (
  id, delivery_mode, recipient_fingerprint, verification_token_hash,
  verification_token_expires, alias_key_id, alias_nonce, status, attempts,
  next_attempt_at, template_version, app_name, app_url, support_email,
  from_email, created_at, updated_at, claim_token_history
)
select (
    '80000000-0000-4000-8000-' || pg_catalog.lpad(series.value::text, 12, '0')
  )::uuid,
  'suppressed', repeat('8', 64), repeat('9', 64),
  pg_catalog.clock_timestamp() + interval '20 hours', 'k1',
  'stale_queue_nonce_123456', 'queued', 6,
  pg_catalog.clock_timestamp() - interval '1 hour', 'verification-v1',
  'Ask Crump', 'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>',
  pg_catalog.clock_timestamp() - interval '1 hour', pg_catalog.clock_timestamp(),
  pg_catalog.array_fill(
    '88000000-0000-4000-8000-000000000000'::uuid,
    array[6]
  )
from pg_catalog.generate_series(1, 101) as series(value);

set role service_role;
select pg_temp.assert_true(
  (select count(*) = 0
   from public.claim_verification_email_job_v1(
     '99999999-9999-4999-8999-999999999999', 120
   )),
  'a stale sweep capped at 100 must not reclaim the 101st exhausted job'
);
reset role;
select pg_temp.assert_true(
  not exists (
    select 1 from public.verification_email_jobs
    where status = 'processing' or attempts > 6
  ),
  'exhausted jobs must never return to processing'
);

select 'durable verification-email queue PostgreSQL gate passed' as result;
