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
  (
    select index_row.indisunique
      and index_row.indisvalid
      and index_row.indisready
      and index_row.indrelid = 'public.users'::regclass
      and index_row.indnkeyatts = 1
      and pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true) =
        'password_reset_token_hash'
      and pg_catalog.pg_get_expr(index_row.indpred, index_row.indrelid) =
        '(password_reset_token_hash IS NOT NULL)'
    from pg_catalog.pg_index as index_row
    where index_row.indexrelid =
      'public.users_password_reset_token_hash_unique'::regclass
  ),
  'password-reset token uniqueness boundary is missing or incorrect'
);

select pg_temp.assert_true(
  (
    select function_row.prosecdef is true
      and function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
    from pg_catalog.pg_proc as function_row
    where function_row.oid =
      'public.consume_password_reset_v1(text,text)'::regprocedure
  ),
  'atomic password-reset RPC owner, definer, volatility, or search_path drifted'
);

select pg_temp.assert_true(
  not has_function_privilege(
    'anon',
    'public.consume_password_reset_v1(text,text)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated',
    'public.consume_password_reset_v1(text,text)',
    'EXECUTE'
  )
  and has_function_privilege(
    'service_role',
    'public.consume_password_reset_v1(text,text)',
    'EXECUTE'
  )
  and not exists (
    select 1
      from pg_catalog.pg_proc as function_row
      cross join lateral pg_catalog.aclexplode(function_row.proacl) as acl_row
     where function_row.oid =
       'public.consume_password_reset_v1(text,text)'::regprocedure
       and acl_row.privilege_type = 'EXECUTE'
       and (
         acl_row.grantee in (
           0::oid,
           (select oid from pg_catalog.pg_roles where rolname = 'anon'),
           (select oid from pg_catalog.pg_roles where rolname = 'authenticated')
         )
         or (
           acl_row.grantee = (
             select oid from pg_catalog.pg_roles where rolname = 'service_role'
           )
           and acl_row.is_grantable
         )
       )
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
      'public.consume_password_reset_v1(text,text)'::regprocedure
      and acl_row.privilege_type = 'EXECUTE'
  ),
  'atomic password-reset RPC is not exactly service-role-only'
);

insert into public.users (
  id,
  email,
  password_hash,
  is_verified,
  is_guest,
  verification_token_hash,
  verification_token_expires,
  password_reset_token_hash,
  password_reset_expires,
  terms_accepted_at,
  terms_version,
  preferences,
  guest_message_count,
  subscription_tier,
  subscription_status,
  created_at,
  updated_at,
  registration_environment,
  registration_submitted_at
) values
  (
    '30000000-0000-4000-8000-000000000001',
    'guest-converted@example.test',
    '$argon2id$old-guest-password-hash',
    false,
    true,
    repeat('1', 64),
    pg_catalog.clock_timestamp() + interval '1 day',
    repeat('a', 64),
    pg_catalog.clock_timestamp() + interval '1 hour',
    pg_catalog.clock_timestamp() - interval '30 minutes',
    '2026-10-22',
    '{"history":"preserve"}'::jsonb,
    4,
    'professional',
    'active',
    pg_catalog.clock_timestamp() - interval '1 hour',
    pg_catalog.clock_timestamp() - interval '5 minutes',
    'production',
    pg_catalog.clock_timestamp() - interval '45 minutes'
  ),
  (
    '30000000-0000-4000-8000-000000000002',
    'unrelated@example.test',
    '$argon2id$unrelated-password-hash',
    true,
    false,
    null,
    null,
    repeat('b', 64),
    pg_catalog.clock_timestamp() + interval '1 hour',
    null,
    null,
    '{}'::jsonb,
    0,
    'free',
    'inactive',
    pg_catalog.clock_timestamp() - interval '2 hours',
    pg_catalog.clock_timestamp() - interval '1 hour',
    'production',
    pg_catalog.clock_timestamp() - interval '2 hours'
  ),
  (
    '30000000-0000-4000-8000-000000000003',
    'expired@example.test',
    '$argon2id$expired-password-hash',
    false,
    false,
    null,
    null,
    repeat('c', 64),
    pg_catalog.clock_timestamp() - interval '1 second',
    null,
    null,
    '{}'::jsonb,
    0,
    'free',
    'inactive',
    pg_catalog.clock_timestamp() - interval '2 hours',
    pg_catalog.clock_timestamp() - interval '1 hour',
    'production',
    pg_catalog.clock_timestamp() - interval '2 hours'
  );

insert into public.sessions (
  id, user_id, token_hash, expires_at, revoked_at
) values
  (
    '31000000-0000-4000-8000-000000000001',
    '30000000-0000-4000-8000-000000000001',
    repeat('1', 64),
    pg_catalog.clock_timestamp() + interval '1 day',
    null
  ),
  (
    '31000000-0000-4000-8000-000000000002',
    '30000000-0000-4000-8000-000000000001',
    repeat('2', 64),
    pg_catalog.clock_timestamp() + interval '1 day',
    pg_catalog.clock_timestamp() - interval '1 minute'
  ),
  (
    '31000000-0000-4000-8000-000000000003',
    '30000000-0000-4000-8000-000000000002',
    repeat('3', 64),
    pg_catalog.clock_timestamp() + interval '1 day',
    null
  );

-- Neither browser-facing role may invoke the definer RPC.
\set ON_ERROR_STOP off
set role anon;
select * from public.consume_password_reset_v1(
  repeat('a', 64),
  '$argon2id$anonymous-must-not-write'
);
\set anon_call_sqlstate :SQLSTATE
reset role;
set role authenticated;
select * from public.consume_password_reset_v1(
  repeat('a', 64),
  '$argon2id$authenticated-must-not-write'
);
\set authenticated_call_sqlstate :SQLSTATE
reset role;
\set ON_ERROR_STOP on

select pg_temp.assert_true(
  :'anon_call_sqlstate' = '42501'
  and :'authenticated_call_sqlstate' = '42501',
  'a browser-facing role invoked the atomic password-reset RPC'
);

set role service_role;
select reset_applied as wrong_token_applied
  from public.consume_password_reset_v1(
    repeat('f', 64),
    '$argon2id$wrong-token-must-not-write'
  ) \gset
select reset_applied as expired_token_applied
  from public.consume_password_reset_v1(
    repeat('c', 64),
    '$argon2id$expired-token-must-not-write'
  ) \gset
reset role;

select pg_temp.assert_true(
  :'wrong_token_applied' = 'f'
  and :'expired_token_applied' = 'f'
  and (
    select account.password_hash = '$argon2id$expired-password-hash'
      and account.password_reset_token_hash = repeat('c', 64)
      and account.is_verified is false
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000003'
  ),
  'a wrong or expired token mutated account state'
);

create temporary table password_reset_before as
select
  account.id,
  account.registration_submitted_at,
  account.registration_environment,
  account.terms_accepted_at,
  account.terms_version,
  account.preferences,
  account.guest_message_count,
  account.subscription_tier,
  account.subscription_status
from public.users as account
where account.id = '30000000-0000-4000-8000-000000000001';

set role service_role;
select reset_applied as valid_token_applied
  from public.consume_password_reset_v1(
    repeat('a', 64),
    '$argon2id$new-guest-password-hash'
  ) \gset
select reset_applied as replay_token_applied
  from public.consume_password_reset_v1(
    repeat('a', 64),
    '$argon2id$replay-must-not-overwrite'
  ) \gset
reset role;

select pg_temp.assert_true(
  :'valid_token_applied' = 't'
  and :'replay_token_applied' = 'f',
  'valid token did not win exactly once'
);

select pg_temp.assert_true(
  (
    select account.password_hash = '$argon2id$new-guest-password-hash'
      and account.is_verified is true
      and account.is_guest is false
      and account.verification_token_hash is null
      and account.verification_token_expires is null
      and account.password_reset_token_hash is null
      and account.password_reset_expires is null
      and account.email_verified_at is not null
      and account.email_verified_at >= account.created_at
      and account.registration_submitted_at = before_state.registration_submitted_at
      and account.registration_environment = before_state.registration_environment
      and account.terms_accepted_at = before_state.terms_accepted_at
      and account.terms_version = before_state.terms_version
      and account.preferences = before_state.preferences
      and account.guest_message_count = before_state.guest_message_count
      and account.subscription_tier = before_state.subscription_tier
      and account.subscription_status = before_state.subscription_status
    from public.users as account
    join password_reset_before as before_state using (id)
  ),
  'guest conversion or preserved account state is incorrect'
);

select pg_temp.assert_true(
  (
    select session.revoked_at is not null
    from public.sessions as session
    where session.id = '31000000-0000-4000-8000-000000000001'
  )
  and (
    select session.revoked_at is not null
    from public.sessions as session
    where session.id = '31000000-0000-4000-8000-000000000002'
  )
  and (
    select session.revoked_at is null
    from public.sessions as session
    where session.id = '31000000-0000-4000-8000-000000000003'
  ),
  'session revocation was incomplete or crossed accounts'
);

-- A session-write failure must roll back the password change, token consume,
-- guest conversion, and verification timestamp as one statement.
insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  password_reset_token_hash, password_reset_expires,
  created_at, updated_at, registration_environment,
  registration_submitted_at
) values (
  '30000000-0000-4000-8000-000000000004',
  'rollback@example.test',
  '$argon2id$rollback-old-password-hash',
  false,
  true,
  repeat('d', 64),
  pg_catalog.clock_timestamp() + interval '1 hour',
  pg_catalog.clock_timestamp() - interval '1 hour',
  pg_catalog.clock_timestamp() - interval '5 minutes',
  'production',
  pg_catalog.clock_timestamp() - interval '30 minutes'
);

insert into public.sessions (id, user_id, token_hash, expires_at)
values (
  '31000000-0000-4000-8000-000000000004',
  '30000000-0000-4000-8000-000000000004',
  repeat('4', 64),
  pg_catalog.clock_timestamp() + interval '1 day'
);

create or replace function public.reject_test_session_revocation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.user_id = '30000000-0000-4000-8000-000000000004'::uuid
     and old.revoked_at is null
     and new.revoked_at is not null then
    raise exception 'synthetic session revocation failure';
  end if;
  return new;
end;
$$;

create trigger reject_test_session_revocation
before update of revoked_at on public.sessions
for each row
execute function public.reject_test_session_revocation();

\set ON_ERROR_STOP off
set role service_role;
select * from public.consume_password_reset_v1(
  repeat('d', 64),
  '$argon2id$rollback-new-password-must-not-stick'
);
\set rollback_call_sqlstate :SQLSTATE
reset role;
\set ON_ERROR_STOP on

drop trigger reject_test_session_revocation on public.sessions;
drop function public.reject_test_session_revocation();

select pg_temp.assert_true(
  :'rollback_call_sqlstate' = 'P0001'
  and (
    select account.password_hash = '$argon2id$rollback-old-password-hash'
      and account.password_reset_token_hash = repeat('d', 64)
      and account.password_reset_expires > pg_catalog.clock_timestamp()
      and account.is_verified is false
      and account.is_guest is true
      and account.email_verified_at is null
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000004'
  )
  and (
    select session.revoked_at is null
    from public.sessions as session
    where session.id = '31000000-0000-4000-8000-000000000004'
  ),
  'session failure did not roll the reset transaction back'
);
