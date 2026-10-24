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
    raise exception 'PostgreSQL login migration gate failed: %', failure_message;
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
      'public.finalize_password_login_v1(uuid,text,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)'::regprocedure
  ),
  'atomic login RPC owner, definer, volatility, or search_path drifted'
);

select pg_temp.assert_true(
  not has_function_privilege(
    'anon',
    'public.finalize_password_login_v1(uuid,text,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated',
    'public.finalize_password_login_v1(uuid,text,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)',
    'EXECUTE'
  )
  and has_function_privilege(
    'service_role',
    'public.finalize_password_login_v1(uuid,text,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)',
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
      'public.finalize_password_login_v1(uuid,text,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)'::regprocedure
      and acl_row.privilege_type = 'EXECUTE'
  ),
  'atomic login RPC is not exactly service-role-only'
);

insert into public.users (
  id, email, password_hash, is_verified, is_guest, deleted_at,
  created_at, updated_at, registration_environment, registration_submitted_at
) values
  (
    '40000000-0000-4000-8000-000000000001', 'modern-login@example.test',
    '$argon2id$modern-current-password-hash', true, false, null,
    clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 hour',
    'production', clock_timestamp() - interval '1 day'
  ),
  (
    '40000000-0000-4000-8000-000000000002', 'legacy-login@example.test',
    '$2b$12$legacy-password-hash-for-test', true, false, null,
    clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 hour',
    'production', clock_timestamp() - interval '1 day'
  ),
  (
    '40000000-0000-4000-8000-000000000003', 'unverified-login@example.test',
    '$argon2id$unverified-password-hash', false, false, null,
    clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 hour',
    'production', clock_timestamp() - interval '1 day'
  ),
  (
    '40000000-0000-4000-8000-000000000004', 'guest-login@example.test',
    '$argon2id$guest-password-hash', true, true, null,
    clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 hour',
    'production', clock_timestamp() - interval '1 day'
  ),
  (
    '40000000-0000-4000-8000-000000000005', 'deleted-login@example.test',
    '$argon2id$deleted-password-hash', true, false, clock_timestamp() - interval '1 hour',
    clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 hour',
    'production', clock_timestamp() - interval '1 day'
  ),
  (
    '40000000-0000-4000-8000-000000000006', 'rollback-login@example.test',
    '$2b$12$rollback-legacy-password-hash', true, false, null,
    clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 hour',
    'production', clock_timestamp() - interval '1 day'
  ),
  (
    '40000000-0000-4000-8000-000000000007', 'prune-login@example.test',
    '$argon2id$prune-current-password-hash', true, false, null,
    clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 hour',
    'production', clock_timestamp() - interval '1 day'
  );

-- Browser-facing roles must not invoke the definer RPC.
\set ON_ERROR_STOP off
set role anon;
select * from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000001',
  '$argon2id$modern-current-password-hash', null,
  gen_random_uuid(), encode(digest('browser-anon', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day',
  null, 'browser', 'web', '{}'::jsonb, '127.0.0.1', 'pytest'
);
\set anon_login_sqlstate :SQLSTATE
reset role;
set role authenticated;
select * from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000001',
  '$argon2id$modern-current-password-hash', null,
  gen_random_uuid(), encode(digest('browser-authenticated', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day',
  null, 'browser', 'web', '{}'::jsonb, '127.0.0.1', 'pytest'
);
\set authenticated_login_sqlstate :SQLSTATE
reset role;
\set ON_ERROR_STOP on

select pg_temp.assert_true(
  :'anon_login_sqlstate' = '42501'
  and :'authenticated_login_sqlstate' = '42501',
  'a browser-facing role invoked the atomic login RPC'
);

set role service_role;
select login_applied as modern_login_applied
from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000001',
  '$argon2id$modern-current-password-hash', null,
  '41000000-0000-4000-8000-000000000001',
  encode(digest('login-modern-1', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', 'stable-device', 'Phone', 'web',
  '{"client":"web"}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select login_applied as rotated_login_applied
from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000001',
  '$argon2id$modern-current-password-hash', null,
  '41000000-0000-4000-8000-000000000002',
  encode(digest('login-modern-2', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', 'stable-device', 'Phone', 'web',
  '{"client":"web"}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select login_applied as legacy_login_applied
from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000002',
  '$2b$12$legacy-password-hash-for-test', '$argon2id$upgraded-password-hash',
  '41000000-0000-4000-8000-000000000003',
  encode(digest('login-legacy', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select login_applied as wrong_hash_login_applied
from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000001',
  '$argon2id$stale-or-wrong-password-hash', null,
  '41000000-0000-4000-8000-000000000004',
  encode(digest('login-wrong-hash', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select login_applied as unverified_login_applied
from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000003',
  '$argon2id$unverified-password-hash', null,
  '41000000-0000-4000-8000-000000000005',
  encode(digest('login-unverified', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select login_applied as guest_login_applied
from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000004',
  '$argon2id$guest-password-hash', null,
  '41000000-0000-4000-8000-000000000006',
  encode(digest('login-guest', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
select login_applied as deleted_login_applied
from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000005',
  '$argon2id$deleted-password-hash', null,
  '41000000-0000-4000-8000-000000000007',
  encode(digest('login-deleted', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
reset role;

select pg_temp.assert_true(
  :'modern_login_applied' = 't'
  and :'rotated_login_applied' = 't'
  and :'legacy_login_applied' = 't'
  and :'wrong_hash_login_applied' = 'f'
  and :'unverified_login_applied' = 'f'
  and :'guest_login_applied' = 'f'
  and :'deleted_login_applied' = 'f',
  'login acceptance did not match account and password state'
);

select pg_temp.assert_true(
  (
    select account.password_hash = '$argon2id$modern-current-password-hash'
      and account.last_login is not null
    from public.users as account
    where account.id = '40000000-0000-4000-8000-000000000001'
  )
  and (
    select count(*) = 1
      and bool_and(session.id = '41000000-0000-4000-8000-000000000001')
      and bool_and(
        session.token_hash = encode(digest('login-modern-2', 'sha256'), 'hex')
      )
      and bool_and(session.revoked_at is null)
    from public.sessions as session
    where session.device_id = 'stable-device'
  )
  and (
    select account.password_hash = '$argon2id$upgraded-password-hash'
      and account.last_login is not null
    from public.users as account
    where account.id = '40000000-0000-4000-8000-000000000002'
  )
  and exists (
    select 1 from public.sessions as session
    where session.id = '41000000-0000-4000-8000-000000000003'
      and session.device_id is null
      and session.revoked_at is null
  ),
  'modern login, legacy upgrade, or device rotation did not persist atomically'
);

select pg_temp.assert_true(
  not exists (
    select 1 from public.sessions as session
    where session.id in (
      '41000000-0000-4000-8000-000000000004',
      '41000000-0000-4000-8000-000000000005',
      '41000000-0000-4000-8000-000000000006',
      '41000000-0000-4000-8000-000000000007'
    )
  )
  and (
    select account.last_login is null
    from public.users as account
    where account.id = '40000000-0000-4000-8000-000000000003'
  )
  and (
    select account.last_login is null
    from public.users as account
    where account.id = '40000000-0000-4000-8000-000000000004'
  )
  and (
    select account.last_login is null
    from public.users as account
    where account.id = '40000000-0000-4000-8000-000000000005'
  ),
  'a rejected login wrote a session or login timestamp'
);

-- A session insert failure must roll back the optional password upgrade and
-- login timestamps from the same statement.
create or replace function public.reject_test_login_session_write()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.user_id = '40000000-0000-4000-8000-000000000006'::uuid then
    raise exception 'synthetic login session failure';
  end if;
  return new;
end;
$$;

create trigger reject_test_login_session_write
before insert or update on public.sessions
for each row execute function public.reject_test_login_session_write();

\set ON_ERROR_STOP off
set role service_role;
select * from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000006',
  '$2b$12$rollback-legacy-password-hash', '$argon2id$rollback-upgrade-must-not-stick',
  '41000000-0000-4000-8000-000000000008',
  encode(digest('login-rollback', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);
\set login_rollback_sqlstate :SQLSTATE
reset role;
\set ON_ERROR_STOP on

drop trigger reject_test_login_session_write on public.sessions;
drop function public.reject_test_login_session_write();

select pg_temp.assert_true(
  :'login_rollback_sqlstate' = 'P0001'
  and (
    select account.password_hash = '$2b$12$rollback-legacy-password-hash'
      and account.last_login is null
    from public.users as account
    where account.id = '40000000-0000-4000-8000-000000000006'
  )
  and not exists (
    select 1 from public.sessions as session
    where session.user_id = '40000000-0000-4000-8000-000000000006'
  ),
  'session failure did not roll the complete login transaction back'
);

insert into public.sessions (
  id, user_id, token_hash, created_at, last_activity, expires_at
)
select
  gen_random_uuid(),
  '40000000-0000-4000-8000-000000000007'::uuid,
  encode(digest('prune-' || sequence::text, 'sha256'), 'hex'),
  clock_timestamp() - (sequence || ' minutes')::interval,
  clock_timestamp() - (sequence || ' minutes')::interval,
  clock_timestamp() + interval '1 day'
from generate_series(1, 21) as sequence;

set role service_role;
select login_applied as prune_login_applied
from public.finalize_password_login_v1(
  '40000000-0000-4000-8000-000000000007',
  '$argon2id$prune-current-password-hash', null,
  '41000000-0000-4000-8000-000000000009',
  encode(digest('login-prune', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
) \gset
reset role;

select pg_temp.assert_true(
  :'prune_login_applied' = 't'
  and (
    select count(*) = 20
    from public.sessions as session
    where session.user_id = '40000000-0000-4000-8000-000000000007'
      and session.revoked_at is null
  )
  and (
    select session.revoked_at is null
    from public.sessions as session
    where session.id = '41000000-0000-4000-8000-000000000009'
  ),
  'login session pruning did not preserve exactly twenty active sessions including the new one'
);
