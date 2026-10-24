\set ON_ERROR_STOP on

create or replace function pg_temp.assert_true(condition boolean, failure_message text)
returns void language plpgsql as $$
begin
  if condition is not true then
    raise exception 'password-reset-email queue gate failed: %', failure_message;
  end if;
end;
$$;

select pg_temp.assert_true(
  (select relrowsecurity and relforcerowsecurity
   from pg_catalog.pg_class
   where oid = 'public.password_reset_email_jobs'::regclass),
  'queue RLS must be enabled and forced'
);
select pg_temp.assert_true(
  not pg_catalog.has_table_privilege('service_role', 'public.password_reset_email_jobs', 'SELECT')
  and not pg_catalog.has_table_privilege('service_role', 'public.password_reset_email_jobs', 'INSERT')
  and not pg_catalog.has_table_privilege('anon', 'public.password_reset_email_jobs', 'SELECT')
  and not pg_catalog.has_table_privilege('authenticated', 'public.password_reset_email_jobs', 'SELECT'),
  'queue table must remain RPC-only'
);
select pg_temp.assert_true(
  (select pg_catalog.count(*) = 0
   from information_schema.columns
   where table_schema = 'public'
     and table_name = 'password_reset_email_jobs'
     and column_name in (
       'email', 'recipient_email', 'name', 'token', 'alias', 'body', 'secret',
       'intent', 'plan'
     )),
  'queue must store no raw recipient, bearer, alias, body, name, secret, or routing intent'
);

do $$
declare
  signature text;
  oid_value oid;
begin
  foreach signature in array array[
    'public.enqueue_password_reset_email_job_v1(uuid,text,text,text,timestamp with time zone,text,text,text,text,text,text,text)',
    'public.claim_password_reset_email_job_v1(uuid,integer)',
    'public.stage_password_reset_email_job_v1(uuid,uuid)',
    'public.complete_password_reset_email_job_v1(uuid,uuid,text)',
    'public.release_password_reset_email_job_v1(uuid,uuid,text,boolean,integer)'
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
  id, email, is_guest, deleted_at, password_reset_token_hash,
  password_reset_expires, updated_at
) values
  ('11111111-1111-4111-8111-111111111111', 'live@example.com', false, null,
   repeat('a', 64), pg_catalog.clock_timestamp() + interval '4 minutes', now()),
  ('22222222-2222-4222-8222-222222222222', 'expired@example.com', false, null,
   repeat('b', 64), pg_catalog.clock_timestamp() - interval '1 minute', now()),
  ('33333333-3333-4333-8333-333333333333', 'guest@example.com', true, null,
   null, null, now()),
  ('44444444-4444-4444-8444-444444444444', 'deleted@example.com', false, now(),
   null, null, now()),
  ('55555555-5555-4555-8555-555555555555', 'race@example.com', false, null,
   repeat('e', 64), pg_catalog.clock_timestamp() + interval '45 minutes', now());

set role service_role;
select * from public.enqueue_password_reset_email_job_v1(
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'live@example.com', repeat('1', 64),
  repeat('c', 64), pg_catalog.clock_timestamp() + interval '1 hour',
  'k1', 'live_reset_nonce_1234567', 'password-reset-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>'
);
select * from public.enqueue_password_reset_email_job_v1(
  'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'expired@example.com', repeat('2', 64),
  repeat('d', 64), pg_catalog.clock_timestamp() + interval '1 hour',
  'k1', 'expired_reset_nonce_12345', 'password-reset-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>'
);
select * from public.enqueue_password_reset_email_job_v1(
  'cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'missing@example.com', repeat('3', 64),
  repeat('f', 64), pg_catalog.clock_timestamp() + interval '1 hour',
  'k1', 'missing_reset_nonce_12345', 'password-reset-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>'
);
select * from public.enqueue_password_reset_email_job_v1(
  'dddddddd-dddd-4ddd-8ddd-dddddddddddd', 'guest@example.com', repeat('4', 64),
  repeat('7', 64), pg_catalog.clock_timestamp() + interval '1 hour',
  'k1', 'guest_reset_nonce_1234567', 'password-reset-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>'
);
select * from public.enqueue_password_reset_email_job_v1(
  'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', 'deleted@example.com', repeat('5', 64),
  repeat('8', 64), pg_catalog.clock_timestamp() + interval '1 hour',
  'k1', 'deleted_reset_nonce_12345', 'password-reset-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>'
);

-- A committed-response retry must adopt the preserved live generation rather
-- than compare it to the unused replacement candidate.
select * from public.enqueue_password_reset_email_job_v1(
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'live@example.com', repeat('1', 64),
  repeat('c', 64), pg_catalog.clock_timestamp() + interval '1 hour',
  'k1', 'live_reset_nonce_1234567', 'password-reset-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>'
);
reset role;

select pg_temp.assert_true(
  (select password_reset_token_hash = repeat('a', 64)
   from public.users where email = 'live@example.com'),
  'every still-valid reset generation must be preserved'
);
select pg_temp.assert_true(
  (select password_reset_token_hash = repeat('d', 64)
     and password_reset_expires > pg_catalog.clock_timestamp()
   from public.users where email = 'expired@example.com'),
  'expired reset generation must rotate atomically'
);
select pg_temp.assert_true(
  (select pg_catalog.count(*) = 3
   from public.password_reset_email_jobs
   where status = 'suppressed' and user_id is null),
  'missing, guest, and deleted accounts must create only suppressed envelopes'
);
select pg_temp.assert_true(
  (select pg_catalog.count(*) = 1
   from public.password_reset_email_jobs
   where id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
  'exact replay must not duplicate a job'
);

do $$
declare
  mismatch_rejected boolean := false;
begin
  set local role service_role;
  begin
    perform * from public.enqueue_password_reset_email_job_v1(
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'live@example.com', repeat('1', 64),
      repeat('c', 64), pg_catalog.clock_timestamp() + interval '1 hour',
      'k1', 'different_reset_nonce_1234', 'password-reset-v1', 'Ask Crump',
      'https://www.askcrump.com', 'askcrump@gmail.com',
      'Ask Crump <noreply@askcrump.com>'
    );
  exception when unique_violation then
    mismatch_rejected := true;
  end;
  if not mismatch_rejected then
    raise exception 'job-id replay mismatch was not rejected';
  end if;
end;
$$;

-- Claim and stage the live job. It has less than five minutes left but is
-- still valid long enough for the bounded two-minute lease.
update public.password_reset_email_jobs
set next_attempt_at = pg_catalog.clock_timestamp() + interval '1 hour'
where id <> 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' and status = 'queued';
set role service_role;
select * from public.claim_password_reset_email_job_v1(
  '99999999-9999-4999-8999-999999999999', 120
) \gset live_claim_
select pg_temp.assert_true(
  :'live_claim_job_id' = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  'live reset job must be claimed'
);
select * from public.stage_password_reset_email_job_v1(
  :'live_claim_job_id'::uuid, :'live_claim_lease_token'::uuid
) \gset live_stage_
select pg_temp.assert_true(
  :'live_stage_disposition' = 'deliver'
    and :'live_stage_recipient_email' = 'live@example.com'
    and :'live_stage_password_reset_token_hash' = repeat('a', 64),
  'stage must return only the locked current generation'
);
select pg_temp.assert_true(
  public.complete_password_reset_email_job_v1(
    :'live_claim_job_id'::uuid,
    :'live_claim_lease_token'::uuid,
    'provider_accepted'
  ) = 'provider_accepted',
  'staged provider acceptance must complete terminally'
);
reset role;

-- A generation changed after enqueue must suppress before recipient release.
set role service_role;
select * from public.enqueue_password_reset_email_job_v1(
  'ffffffff-ffff-4fff-8fff-ffffffffffff', 'race@example.com', repeat('6', 64),
  repeat('9', 64), pg_catalog.clock_timestamp() + interval '1 hour',
  'k1', 'race_reset_nonce_1234567', 'password-reset-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>'
);
reset role;
update public.password_reset_email_jobs
set next_attempt_at = pg_catalog.clock_timestamp() - interval '1 second'
where id = 'ffffffff-ffff-4fff-8fff-ffffffffffff';
update public.users
set password_reset_token_hash = repeat('0', 64)
where email = 'race@example.com';
set role service_role;
select * from public.claim_password_reset_email_job_v1(
  '77777777-7777-4777-8777-777777777777', 120
) \gset race_claim_
select disposition, recipient_email is null as recipient_is_null
from public.stage_password_reset_email_job_v1(
  :'race_claim_job_id'::uuid, :'race_claim_lease_token'::uuid
) \gset race_stage_
select pg_temp.assert_true(
  :'race_stage_disposition' = 'suppress' and :'race_stage_recipient_is_null' = 't',
  'stale reset generation must suppress before provider delivery'
);
select pg_temp.assert_true(
  public.complete_password_reset_email_job_v1(
    :'race_claim_job_id'::uuid, :'race_claim_lease_token'::uuid, 'suppressed'
  ) = 'suppressed',
  'stale job suppression must complete terminally'
);
reset role;

-- Deleting the account cascades every linked queue envelope.
delete from public.users where email = 'expired@example.com';
select pg_temp.assert_true(
  not exists (
    select 1 from public.password_reset_email_jobs
    where id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
  ),
  'account deletion must cascade queued reset envelopes'
);

-- Retry release must clear the lease, apply bounded backoff, and fence the old
-- lease. A retry that no longer fits before reset expiry must fail terminally.
insert into public.users (
  id, email, is_guest, deleted_at, password_reset_token_hash,
  password_reset_expires, updated_at
) values (
  '66666666-6666-4666-8666-666666666666', 'retry@example.com', false, null,
  repeat('6', 64), pg_catalog.clock_timestamp() + interval '45 minutes', now()
);
set role service_role;
select * from public.enqueue_password_reset_email_job_v1(
  '12121212-1212-4212-8212-121212121212', 'retry@example.com', repeat('7', 64),
  repeat('8', 64), pg_catalog.clock_timestamp() + interval '1 hour',
  'k1', 'retry_reset_nonce_1234567', 'password-reset-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>'
);
select * from public.claim_password_reset_email_job_v1(
  '13131313-1313-4313-8313-131313131313', 60
) \gset retry_claim_
select pg_temp.assert_true(
  public.release_password_reset_email_job_v1(
    :'retry_claim_job_id'::uuid, :'retry_claim_lease_token'::uuid,
    'PROVIDER_UNAVAILABLE', true, 7
  ) = 'retry_scheduled',
  'retryable provider failure must schedule bounded retry'
);
reset role;
select pg_temp.assert_true(
  (select status = 'queued'
      and lease_token is null
      and lease_expires_at is null
      and next_attempt_at > pg_catalog.clock_timestamp()
      and last_failure_code = 'PROVIDER_UNAVAILABLE'
   from public.password_reset_email_jobs
   where id = '12121212-1212-4212-8212-121212121212'),
  'retry release must clear lease and retain classified failure'
);
set role service_role;
select pg_temp.assert_true(
  public.complete_password_reset_email_job_v1(
    :'retry_claim_job_id'::uuid, :'retry_claim_lease_token'::uuid,
    'provider_accepted'
  ) = 'lease_lost',
  'released lease must remain fenced'
);
reset role;

update public.password_reset_email_jobs
set next_attempt_at = pg_catalog.clock_timestamp() - interval '1 second'
where id = '12121212-1212-4212-8212-121212121212';
set role service_role;
select * from public.claim_password_reset_email_job_v1(
  '14141414-1414-4414-8414-141414141414', 60
) \gset expiry_claim_
reset role;
update public.password_reset_email_jobs
set password_reset_expires = pg_catalog.clock_timestamp() + interval '90 seconds'
where id = '12121212-1212-4212-8212-121212121212';
set role service_role;
select pg_temp.assert_true(
  public.release_password_reset_email_job_v1(
    :'expiry_claim_job_id'::uuid, :'expiry_claim_lease_token'::uuid,
    'PROVIDER_THROTTLED', true, 0
  ) = 'failed_permanent',
  'retry that cannot fit before reset expiry must fail terminally'
);
reset role;
select pg_temp.assert_true(
  (select status = 'failed_permanent'
      and terminal_at is not null
      and lease_token is null
      and last_failure_code = 'PROVIDER_THROTTLED'
   from public.password_reset_email_jobs
   where id = '12121212-1212-4212-8212-121212121212'),
  'near-expiry release must persist terminal failure state'
);

-- A still-valid generation inside the worker lease horizon is preserved so a
-- previously emailed link is not invalidated, but it is never newly sent. The
-- generic route tells the caller to check email rather than promising a send.
insert into public.users (
  id, email, is_guest, deleted_at, password_reset_token_hash,
  password_reset_expires, updated_at
) values (
  '77777777-7777-4777-8777-777777777778', 'near-expiry@example.com', false,
  null, repeat('1', 64), pg_catalog.clock_timestamp() + interval '90 seconds',
  now()
);
set role service_role;
select * from public.enqueue_password_reset_email_job_v1(
  '15151515-1515-4515-8515-151515151515', 'near-expiry@example.com',
  repeat('b', 64), repeat('c', 64),
  pg_catalog.clock_timestamp() + interval '1 hour', 'k1',
  'near_expiry_nonce_12345', 'password-reset-v1', 'Ask Crump',
  'https://www.askcrump.com', 'askcrump@gmail.com',
  'Ask Crump <noreply@askcrump.com>'
);
select pg_temp.assert_true(
  not exists (
    select 1 from public.claim_password_reset_email_job_v1(
      '16161616-1616-4616-8616-161616161616', 120
    )
  ),
  'near-expiry preserved generation must not be delivered inside lease horizon'
);
reset role;
select pg_temp.assert_true(
  (select status = 'failed_permanent'
      and last_failure_code = 'JOB_INTEGRITY_INVALID'
   from public.password_reset_email_jobs
   where id = '15151515-1515-4515-8515-151515151515'),
  'near-expiry preserved generation must fail closed without provider access'
);
