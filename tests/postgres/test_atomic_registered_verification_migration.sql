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
    raise exception
      'PostgreSQL registered-verification gate failed: %',
      failure_message;
  end if;
end;
$$;

select pg_temp.assert_true(
  (
    select function_row.prosecdef is true
      and function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
    from pg_catalog.pg_proc as function_row
    where function_row.oid =
      'public.verify_registered_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)'::regprocedure
  ),
  'RPC owner, definer, volatility, or search_path drifted'
);

select pg_temp.assert_true(
  not has_function_privilege(
    'anon',
    'public.verify_registered_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated',
    'public.verify_registered_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)',
    'EXECUTE'
  )
  and has_function_privilege(
    'service_role',
    'public.verify_registered_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)',
    'EXECUTE'
  )
  and (
    select count(*) = 2
      and bool_and(
        acl_row.grantee in (
          function_row.proowner,
          (select oid from pg_catalog.pg_roles where rolname = 'service_role')
        )
      )
      and count(*) filter (
        where acl_row.grantee = (
          select oid from pg_catalog.pg_roles where rolname = 'service_role'
        )
          and not acl_row.is_grantable
      ) = 1
    from pg_catalog.pg_proc as function_row
    cross join lateral pg_catalog.aclexplode(function_row.proacl) as acl_row
    where function_row.oid =
      'public.verify_registered_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)'::regprocedure
      and acl_row.privilege_type = 'EXECUTE'
  )
  and (
    select count(*) = 1
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = function_row.pronamespace
    where namespace_row.nspname = 'public'
      and function_row.proname = 'verify_registered_and_create_session_v1'
  ),
  'RPC is not exactly service-role-only or has an unexpected overload'
);

insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  verification_token_hash, verification_token_expires,
  created_at, updated_at, registration_environment, registration_submitted_at,
  deleted_at
) values
  (
    '60000000-0000-4000-8000-000000000001', 'verify-valid@example.test',
    '$argon2id$verify-valid-password', false, false, repeat('a', 64),
    clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
    clock_timestamp() - interval '1 hour', 'production',
    clock_timestamp() - interval '1 day', null
  ),
  (
    '60000000-0000-4000-8000-000000000002', 'verify-expired@example.test',
    '$argon2id$verify-expired-password', false, false, repeat('b', 64),
    clock_timestamp() - interval '1 second', clock_timestamp() - interval '1 day',
    clock_timestamp() - interval '1 hour', 'production',
    clock_timestamp() - interval '1 day', null
  ),
  (
    '60000000-0000-4000-8000-000000000003', 'verify-already@example.test',
    '$argon2id$verify-already-password', true, false, repeat('c', 64),
    clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
    clock_timestamp() - interval '1 hour', 'production',
    clock_timestamp() - interval '1 day', null
  ),
  (
    '60000000-0000-4000-8000-000000000004', 'verify-guest@example.test',
    '$argon2id$verify-guest-password', false, true, repeat('d', 64),
    clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
    clock_timestamp() - interval '1 hour', 'production',
    clock_timestamp() - interval '1 day', null
  ),
  (
    '60000000-0000-4000-8000-000000000005', 'verify-deleted@example.test',
    '$argon2id$verify-deleted-password', false, false, repeat('e', 64),
    clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
    clock_timestamp() - interval '1 hour', 'production',
    clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 minute'
  ),
  (
    '60000000-0000-4000-8000-000000000006', 'verify-rollback@example.test',
    '$argon2id$verify-rollback-password', false, false, repeat('f', 64),
    clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
    clock_timestamp() - interval '1 hour', 'production',
    clock_timestamp() - interval '1 day', null
  ),
  (
    '60000000-0000-4000-8000-000000000007', 'verify-device@example.test',
    '$argon2id$verify-device-password', false, false, repeat('7', 64),
    clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
    clock_timestamp() - interval '1 hour', 'production',
    clock_timestamp() - interval '1 day', null
  ),
  (
    '60000000-0000-4000-8000-000000000008', 'verify-prune@example.test',
    '$argon2id$verify-prune-password', false, false, repeat('8', 64),
    clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
    clock_timestamp() - interval '1 hour', 'production',
    clock_timestamp() - interval '1 day', null
  );

insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values (
  '61000000-0000-4000-8000-000000000007',
  '60000000-0000-4000-8000-000000000007',
  encode(digest('registered-existing-device-token', 'sha256'), 'hex'),
  'verify-device', clock_timestamp() - interval '1 day',
  clock_timestamp() - interval '1 day', clock_timestamp() + interval '1 day'
);

insert into public.sessions (
  id, user_id, token_hash, created_at, last_activity, expires_at
)
select
  ('62000000-0000-4000-8000-' || lpad(series::text, 12, '0'))::uuid,
  '60000000-0000-4000-8000-000000000008'::uuid,
  encode(digest('verify-prune-' || series::text, 'sha256'), 'hex'),
  clock_timestamp() - (series || ' minutes')::interval,
  clock_timestamp() - (series || ' minutes')::interval,
  clock_timestamp() + interval '1 day'
from generate_series(1, 20) as series;

\set ON_ERROR_STOP off
set role anon;
select * from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000001', repeat('a', 64),
  '61000000-0000-4000-8000-000000000001',
  encode(digest('registered-denied-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Browser', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);
\set anon_call_sqlstate :SQLSTATE
reset role;
set role authenticated;
select * from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000001', repeat('a', 64),
  '61000000-0000-4000-8000-000000000001',
  encode(digest('registered-denied-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Browser', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);
\set authenticated_call_sqlstate :SQLSTATE
reset role;
\set ON_ERROR_STOP on

select pg_temp.assert_true(
  :'anon_call_sqlstate' = '42501'
  and :'authenticated_call_sqlstate' = '42501',
  'a browser-facing role invoked the definer RPC'
);

set role service_role;
select verification_applied as wrong_hash_applied
from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000001', repeat('9', 64),
  '61000000-0000-4000-8000-000000000001',
  encode(digest('registered-wrong-hash-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Browser', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select verification_applied as expired_applied
from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000002', repeat('b', 64),
  '61000000-0000-4000-8000-000000000002',
  encode(digest('registered-expired-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Browser', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select verification_applied as already_applied
from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000003', repeat('c', 64),
  '61000000-0000-4000-8000-000000000003',
  encode(digest('registered-already-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Browser', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select verification_applied as guest_applied
from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000004', repeat('d', 64),
  '61000000-0000-4000-8000-000000000004',
  encode(digest('registered-guest-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Browser', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select verification_applied as deleted_applied
from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000005', repeat('e', 64),
  '61000000-0000-4000-8000-000000000005',
  encode(digest('registered-deleted-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Browser', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
reset role;

select pg_temp.assert_true(
  :'wrong_hash_applied' = 'f'
  and :'expired_applied' = 'f'
  and :'already_applied' = 'f'
  and :'guest_applied' = 'f'
  and :'deleted_applied' = 'f'
  and not exists (
    select 1 from public.sessions
    where id in (
      '61000000-0000-4000-8000-000000000001'::uuid,
      '61000000-0000-4000-8000-000000000002'::uuid,
      '61000000-0000-4000-8000-000000000003'::uuid,
      '61000000-0000-4000-8000-000000000004'::uuid,
      '61000000-0000-4000-8000-000000000005'::uuid
    )
  ),
  'an ineligible verification mutated a session'
);

set role service_role;
select verification_applied as valid_applied
from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000001', repeat('a', 64),
  '61000000-0000-4000-8000-000000000001',
  encode(digest('registered-valid-session-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Verified link', 'web',
  '{"client":"web"}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select verification_applied as replay_applied
from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000001', repeat('a', 64),
  '61000000-0000-4000-8000-000000000009',
  encode(digest('registered-replay-session-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Verified link', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
reset role;

select pg_temp.assert_true(
  :'valid_applied' = 't'
  and :'replay_applied' = 'f'
  and (
    select account.is_verified is true
      and account.is_guest is false
      and account.email_verified_at is not null
      and account.verification_token_hash = repeat('a', 64)
      and account.verification_token_expires > clock_timestamp()
      and account.verification_token_expires < clock_timestamp() + interval '16 minutes'
    from public.users as account
    where account.id = '60000000-0000-4000-8000-000000000001'
  )
  and (
    select count(*) = 1
      and bool_and(
        token_hash = encode(
          digest('registered-valid-session-token', 'sha256'), 'hex'
        )
      )
      and bool_and(device_id is null)
      and bool_and(revoked_at is null)
    from public.sessions
    where user_id = '60000000-0000-4000-8000-000000000001'
  ),
  'valid verification did not commit exactly one user/session transition'
);

set role service_role;
select verification_applied as device_applied
from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000007', repeat('7', 64),
  '61000000-0000-4000-8000-000000000099',
  encode(digest('registered-rotated-device-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', 'verify-device', 'Verified link', 'web',
  '{"client":"web"}'::jsonb, '127.0.0.2', 'pytest-rotate'
) \gset
select verification_applied as prune_applied, pruned_sessions as prune_count
from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000008', repeat('8', 64),
  '61000000-0000-4000-8000-000000000008',
  encode(digest('registered-prune-new-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Verified link', 'web',
  '{}'::jsonb, '127.0.0.3', 'pytest-prune'
) \gset
reset role;

select pg_temp.assert_true(
  :'device_applied' = 't'
  and (
    select count(*) = 1
      and bool_and(id = '61000000-0000-4000-8000-000000000007'::uuid)
      and bool_and(
        token_hash = encode(
          digest('registered-rotated-device-token', 'sha256'), 'hex'
        )
      )
      and bool_and(revoked_at is null)
    from public.sessions
    where device_id = 'verify-device'
  )
  and :'prune_applied' = 't'
  and :'prune_count' = '1'
  and (
    select count(*) = 20
    from public.sessions
    where user_id = '60000000-0000-4000-8000-000000000008'
      and revoked_at is null
  ),
  'device rotation or bounded-session pruning changed'
);

create or replace function public.reject_test_verification_session()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.user_id = '60000000-0000-4000-8000-000000000006'::uuid then
    raise exception 'synthetic verification session failure';
  end if;
  return new;
end;
$$;
create trigger reject_test_verification_session
before insert or update on public.sessions
for each row execute function public.reject_test_verification_session();

\set ON_ERROR_STOP off
set role service_role;
select * from public.verify_registered_and_create_session_v1(
  '60000000-0000-4000-8000-000000000006', repeat('f', 64),
  '61000000-0000-4000-8000-000000000006',
  encode(digest('registered-rollback-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Verified link', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);
\set rollback_sqlstate :SQLSTATE
reset role;
\set ON_ERROR_STOP on

drop trigger reject_test_verification_session on public.sessions;
drop function public.reject_test_verification_session();

select pg_temp.assert_true(
  :'rollback_sqlstate' = 'P0001'
  and (
    select account.is_verified is false
      and account.email_verified_at is null
      and account.verification_token_hash = repeat('f', 64)
    from public.users as account
    where account.id = '60000000-0000-4000-8000-000000000006'
  )
  and not exists (
    select 1 from public.sessions
    where user_id = '60000000-0000-4000-8000-000000000006'
  ),
  'session failure did not roll back registered verification'
);
