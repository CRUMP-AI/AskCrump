\set ON_ERROR_STOP on

do $$
declare
  v_setup_signature regprocedure :=
    'public.complete_initial_password_setup_v1(uuid,uuid,text,text)'::regprocedure;
  v_signature regprocedure;
begin
  if not exists (
    select 1
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'users'
       and column_name = 'password_setup_required'
       and data_type = 'boolean'
       and is_nullable = 'NO'
       and column_default = 'false'
  ) then
    raise exception 'password_setup_required is missing or drifted.';
  end if;

  if not exists (
    select 1
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'users'
       and column_name = 'password_inbox_bound_at'
       and data_type = 'timestamp with time zone'
       and is_nullable = 'YES'
  ) then
    raise exception 'password_inbox_bound_at is missing or drifted.';
  end if;

  foreach v_signature in array array[
    'public.consume_password_reset_v1(text,text)'::regprocedure,
    'public.finalize_password_login_v1(uuid,text,text,uuid,text,timestamp with time zone,text,text,text,jsonb,text,text)'::regprocedure,
    'public.verify_registered_and_create_session_v1(uuid,text,uuid,text,timestamp with time zone,text,text,text,jsonb,text,text)'::regprocedure,
    'public.verify_guest_and_create_session_v1(uuid,text,uuid,text,timestamp with time zone,text,text,text,jsonb,text,text)'::regprocedure,
    v_setup_signature
  ]
  loop
    if not pg_catalog.has_function_privilege('service_role', v_signature, 'EXECUTE')
       or pg_catalog.has_function_privilege('anon', v_signature, 'EXECUTE')
       or pg_catalog.has_function_privilege('authenticated', v_signature, 'EXECUTE')
       or pg_catalog.strpos(pg_catalog.pg_get_functiondef(v_signature), 'SET search_path TO ''''') = 0 then
      raise exception 'Password-setup function security drift: %', v_signature;
    end if;
  end loop;
end;
$$;
-- First apply must sanitize rows and sessions that existed before rollout.
do $$
begin
  if exists (
    select 1
      from public.users as account
     where account.id in (
       '70000000-0000-4000-8000-000000000001',
       '70000000-0000-4000-8000-000000000002',
       '70000000-0000-4000-8000-000000000003'
     )
       and (
         account.password_hash <> '!pending-inbox-password-setup-v1!'
         or account.password_setup_required is not true
         or account.password_inbox_bound_at is not null
       )
  ) then
    raise exception 'Migration did not sanitize every pending or provenance-unknown credential.';
  end if;

  if exists (
    select 1
      from public.sessions as session
     where session.user_id in (
       '70000000-0000-4000-8000-000000000001',
       '70000000-0000-4000-8000-000000000002',
       '70000000-0000-4000-8000-000000000003'
     )
       and session.revoked_at is null
  ) then
    raise exception 'Migration did not revoke every unsafe historical session.';
  end if;
end;
$$;
-- Simulate an old application instance accepting a planted password after the
-- schema migration but before all instances have rolled. Verification itself
-- remains the fail-closed boundary.
insert into public.users (
  id, email, password_hash, password_setup_required, is_verified, is_guest,
  verification_token_hash, verification_token_expires,
  created_at, updated_at, registration_environment, registration_submitted_at
) values (
  '70000000-0000-4000-8000-000000000010',
  'rolling-registered@example.test',
  '$argon2id$rolling-attacker-planted-hash', false, false, false,
  repeat('a', 64), pg_catalog.clock_timestamp() + interval '1 day',
  pg_catalog.clock_timestamp() - interval '1 hour',
  pg_catalog.clock_timestamp() - interval '1 hour',
  'production', pg_catalog.clock_timestamp() - interval '1 hour'
);

set role service_role;

select verification_applied
  from public.verify_registered_and_create_session_v1(
    '70000000-0000-4000-8000-000000000010', repeat('a', 64),
    '71000000-0000-4000-8000-000000000010', repeat('b', 64),
    pg_catalog.clock_timestamp() + interval '1 day',
    'victim-verified-browser', 'Verified email link', 'web', '{}'::jsonb,
    '127.0.0.1', 'pytest'
  )
\gset registered_verify_

\if :registered_verify_verification_applied
\else
  \quit 1
\endif

select login_applied
  from public.finalize_password_login_v1(
    '70000000-0000-4000-8000-000000000010',
    '$argon2id$rolling-attacker-planted-hash', null,
    '71000000-0000-4000-8000-000000000011', repeat('c', 64),
    pg_catalog.clock_timestamp() + interval '1 day',
    'attacker-device', 'Attacker', 'web', '{}'::jsonb, '127.0.0.1', 'pytest'
  )
\gset planted_login_

\if :planted_login_login_applied
  \quit 1
\endif

-- Even another valid active session for the verified account is not inbox
-- proof. Only the session minted by the verification transaction carries the
-- server-owned proof marker.
reset role;
insert into public.sessions (
  id, user_id, token_hash, device_id, device_name, platform, device_info,
  created_at, last_activity, expires_at
) values (
  '71000000-0000-4000-8000-000000000013',
  '70000000-0000-4000-8000-000000000010', repeat('d', 64),
  'non-proof-session', 'Non-proof session', 'web', '{}'::jsonb,
  pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp(),
  pg_catalog.clock_timestamp() + interval '1 day'
);
set role service_role;

select password_setup_applied
  from public.complete_initial_password_setup_v1(
    '70000000-0000-4000-8000-000000000010',
    '71000000-0000-4000-8000-000000000013', repeat('d', 64),
    '$argon2id$victim-new-password-hash'
  )
\gset wrong_session_

\if :wrong_session_password_setup_applied
  \quit 1
\endif

select password_setup_applied
  from public.complete_initial_password_setup_v1(
    '70000000-0000-4000-8000-000000000010',
    '71000000-0000-4000-8000-000000000010', repeat('b', 64),
    '$argon2id$victim-new-password-hash'
  )
\gset victim_setup_

\if :victim_setup_password_setup_applied
\else
  \quit 1
\endif

select login_applied
  from public.finalize_password_login_v1(
    '70000000-0000-4000-8000-000000000010',
    '$argon2id$victim-new-password-hash', null,
    '71000000-0000-4000-8000-000000000012', repeat('e', 64),
    pg_catalog.clock_timestamp() + interval '1 day',
    'victim-login-device', 'Victim', 'web', '{}'::jsonb,
    '127.0.0.1', 'pytest'
  )
\gset victim_login_

\if :victim_login_login_applied
\else
  \quit 1
\endif

reset role;

do $$
begin
  if not exists (
    select 1
      from public.users as account
     where account.id = '70000000-0000-4000-8000-000000000010'
       and account.is_verified is true
       and account.is_guest is false
       and account.password_setup_required is false
       and account.password_hash = '$argon2id$victim-new-password-hash'
       and account.password_inbox_bound_at is not null
  ) then
    raise exception 'Victim password setup did not establish the sole usable hash.';
  end if;
end;
$$;
-- Guest conversion: the attacker-held guest session is revoked, the planted
-- password is disabled, and only the inbox-link successor remains active.
insert into public.users (
  id, email, password_hash, password_setup_required, is_verified, is_guest,
  verification_token_hash, verification_token_expires,
  created_at, updated_at, registration_environment, registration_submitted_at
) values (
  '70000000-0000-4000-8000-000000000020',
  'rolling-guest@example.test',
  '$argon2id$rolling-attacker-guest-hash', false, false, true,
  repeat('5', 64), pg_catalog.clock_timestamp() + interval '1 day',
  pg_catalog.clock_timestamp() - interval '1 hour',
  pg_catalog.clock_timestamp() - interval '1 hour',
  'production', pg_catalog.clock_timestamp() - interval '1 hour'
);

insert into public.sessions (
  id, user_id, token_hash, device_id, expires_at
) values (
  '71000000-0000-4000-8000-000000000020',
  '70000000-0000-4000-8000-000000000020', repeat('6', 64),
  'attacker-guest-device', pg_catalog.clock_timestamp() + interval '1 day'
);

set role service_role;
select converted
  from public.verify_guest_and_create_session_v1(
    '70000000-0000-4000-8000-000000000020', repeat('5', 64),
    '71000000-0000-4000-8000-000000000021', repeat('7', 64),
    pg_catalog.clock_timestamp() + interval '1 day',
    'victim-guest-verified-browser', 'Verified email link', 'web', '{}'::jsonb,
    '127.0.0.1', 'pytest'
  )
\gset guest_verify_
reset role;

\if :guest_verify_converted
\else
  \quit 1
\endif

set role service_role;
select password_setup_applied
  from public.complete_initial_password_setup_v1(
    '70000000-0000-4000-8000-000000000020',
    '71000000-0000-4000-8000-000000000021', repeat('7', 64),
    '$argon2id$guest-owner-selected-hash'
  )
\gset guest_setup_

\if :guest_setup_password_setup_applied
\else
  \quit 1
\endif

select login_applied
  from public.finalize_password_login_v1(
    '70000000-0000-4000-8000-000000000020',
    '$argon2id$guest-owner-selected-hash', null,
    '71000000-0000-4000-8000-000000000022', repeat('9', 64),
    pg_catalog.clock_timestamp() + interval '1 day',
    'victim-guest-login', 'Guest owner login', 'web', '{}'::jsonb,
    '127.0.0.1', 'pytest'
  )
\gset guest_login_
reset role;

\if :guest_login_login_applied
\else
  \quit 1
\endif

do $$
begin
  if not exists (
    select 1
      from public.users as account
     where account.id = '70000000-0000-4000-8000-000000000020'
       and account.is_verified is true
       and account.is_guest is false
       and account.password_setup_required is false
       and account.password_hash = '$argon2id$guest-owner-selected-hash'
       and account.password_inbox_bound_at is not null
  ) then
    raise exception 'Guest owner could not establish and use the inbox-bound password.';
  end if;

  if not exists (
    select 1
      from public.sessions as session
     where session.id = '71000000-0000-4000-8000-000000000020'
       and session.revoked_at is not null
  ) or exists (
    select 1
      from public.sessions as session
     where session.id = '71000000-0000-4000-8000-000000000021'
       and session.device_info ? 'passwordSetupProof'
  ) or not exists (
    select 1
      from public.sessions as session
     where session.id = '71000000-0000-4000-8000-000000000022'
       and session.revoked_at is null
  ) then
    raise exception 'Guest conversion did not isolate and consume inbox proof.';
  end if;
end;
$$;
-- Password reset is the recovery route for an account verified before the
-- repair, whose old password/session provenance cannot be proved. It must clear
-- the setup requirement and keep every old session revoked.
update public.users
   set password_reset_token_hash = repeat('8', 64),
       password_reset_expires = pg_catalog.clock_timestamp() + interval '1 hour'
 where id = '70000000-0000-4000-8000-000000000003';

set role service_role;
select reset_applied
  from public.consume_password_reset_v1(
    repeat('8', 64), '$argon2id$guest-owner-reset-hash'
  )
\gset guest_reset_
reset role;

\if :guest_reset_reset_applied
\else
  \quit 1
\endif

do $$
begin
  if not exists (
    select 1
      from public.users as account
     where account.id = '70000000-0000-4000-8000-000000000003'
       and account.password_setup_required is false
       and account.password_hash = '$argon2id$guest-owner-reset-hash'
       and account.password_inbox_bound_at is not null
       and account.is_verified is true
       and account.is_guest is false
       and account.password_reset_token_hash is null
  ) or exists (
    select 1
      from public.sessions as session
     where session.user_id = '70000000-0000-4000-8000-000000000003'
       and session.revoked_at is null
  ) then
    raise exception 'Password-reset recovery did not finish setup and revoke sessions.';
  end if;
end;
$$;
