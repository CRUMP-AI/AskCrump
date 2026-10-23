\set ON_ERROR_STOP on

create extension if not exists dblink;

create or replace function pg_temp.assert_true(
  condition boolean,
  failure_message text
)
returns void
language plpgsql
as $$
begin
  if condition is not true then
    raise exception 'PostgreSQL guest-mode control gate failed: %', failure_message;
  end if;
end;
$$;

-- The singleton starts disabled, is unreadable as a table to API roles, and
-- exposes only its two explicit backend RPC capabilities to service_role.
select pg_temp.assert_true(
  (select count(*) = 1
     from public.guest_mode_control
    where singleton is true
      and enabled is false),
  'the singleton control did not default to disabled'
);
select pg_temp.assert_true(
  (select candidate.relrowsecurity
     from pg_catalog.pg_class as candidate
    where candidate.oid = 'public.guest_mode_control'::regclass),
  'row-level security is not enabled on the exposed control table'
);
select pg_temp.assert_true(
  pg_catalog.has_function_privilege(
    'service_role', 'public.get_guest_mode_control_v1()', 'EXECUTE'
  )
  and pg_catalog.has_function_privilege(
    'service_role', 'public.set_guest_mode_enabled_v1(boolean)', 'EXECUTE'
  )
  and pg_catalog.has_function_privilege(
    'service_role',
    'public.verify_guest_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)',
    'EXECUTE'
  )
  and pg_catalog.has_function_privilege(
    'service_role',
    'public.apply_guest_user_settings_v1(uuid,jsonb,timestamptz)',
    'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'anon', 'public.get_guest_mode_control_v1()', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated', 'public.get_guest_mode_control_v1()', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'anon', 'public.set_guest_mode_enabled_v1(boolean)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated', 'public.set_guest_mode_enabled_v1(boolean)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'anon',
    'public.verify_guest_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)',
    'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated',
    'public.verify_guest_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)',
    'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'anon',
    'public.apply_guest_user_settings_v1(uuid,jsonb,timestamptz)',
    'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated',
    'public.apply_guest_user_settings_v1(uuid,jsonb,timestamptz)',
    'EXECUTE'
  ),
  'guest-mode RPC execution is not service-role-only'
);
select pg_temp.assert_true(
  not pg_catalog.has_function_privilege(
    'service_role', 'public.enforce_guest_mode_on_user_v1()', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'service_role', 'public.enforce_guest_mode_on_session_v1()', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'service_role', 'public.enforce_guest_mode_on_user_settings_v1()', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'service_role', 'public.lock_guest_mode_control_v1()', 'EXECUTE'
  ),
  'a trigger or private lock function remained directly executable by service_role'
);
select pg_temp.assert_true(
  not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_mode_control', 'SELECT'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_mode_control', 'INSERT'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_mode_control', 'UPDATE'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_mode_control', 'DELETE'
  )
  and not pg_catalog.has_table_privilege(
    'anon', 'public.guest_mode_control', 'SELECT'
  )
  and not pg_catalog.has_table_privilege(
    'authenticated', 'public.guest_mode_control', 'SELECT'
  ),
  'an API role retained direct control-table access'
);

set role service_role;
create temporary table initial_guest_mode_status as
select * from public.get_guest_mode_control_v1();
reset role;
select pg_temp.assert_true(
  (select enabled is false and updated_at is not null
     from initial_guest_mode_status),
  'the service-role read RPC did not report the default-off state'
);

do $default_off$
begin
  begin
    insert into public.users (id, is_guest)
    values ('a1000000-0000-4000-8000-000000000001', true);
    raise exception 'a guest identity was inserted while guest mode was off';
  exception when sqlstate 'GX003' then
    null;
  end;
end;
$default_off$;
select pg_temp.assert_true(
  not exists (
    select 1 from public.users
     where id = 'a1000000-0000-4000-8000-000000000001'
  ),
  'the rejected default-off guest identity was persisted'
);

set role service_role;
create temporary table initial_enable_result as
select * from public.set_guest_mode_enabled_v1(true);
reset role;
select pg_temp.assert_true(
  (select enabled is true and revoked_sessions = 0
     from initial_enable_result),
  'the service-role setter did not enable guest mode cleanly'
);

-- Guest verification is a single locked cutover. Both pre-verification
-- sessions are revoked in the same transaction that removes guest authority,
-- and the verifying installation receives exactly one replacement session.
insert into public.users (
  id,
  is_guest,
  is_verified,
  verification_token_hash,
  verification_token_expires
) values (
  'a1000000-0000-4000-8000-000000000005',
  true,
  false,
  'guest-verification-hash',
  pg_catalog.clock_timestamp() + interval '1 day'
);
insert into public.sessions (
  id, user_id, token_hash, device_id, expires_at, revoked_at
) values
  (
    'a3000000-0000-4000-8000-000000000101',
    'a1000000-0000-4000-8000-000000000005',
    'guest-preverify-primary',
    'verification-browser',
    pg_catalog.clock_timestamp() + interval '1 day',
    null
  ),
  (
    'a3000000-0000-4000-8000-000000000102',
    'a1000000-0000-4000-8000-000000000005',
    'guest-preverify-secondary',
    'verification-other-device',
    pg_catalog.clock_timestamp() + interval '1 day',
    null
  );

set role service_role;
create temporary table guest_verification_result as
select * from public.verify_guest_and_create_session_v1(
  'a1000000-0000-4000-8000-000000000005',
  'guest-verification-hash',
  'a3000000-0000-4000-8000-000000000103',
  'verified-fresh-session',
  pg_catalog.clock_timestamp() + interval '365 days',
  'verification-browser',
  'Verified email link',
  'web',
  '{"client":"web","platform":"web"}'::jsonb,
  '127.0.0.1',
  'PostgreSQL verification gate'
);
reset role;
select pg_temp.assert_true(
  (select converted is true and revoked_sessions = 2
     from guest_verification_result)
  and (select is_verified is true and is_guest is false
         from public.users
        where id = 'a1000000-0000-4000-8000-000000000005')
  and not exists (
    select 1
      from public.sessions
     where token_hash in (
       'guest-preverify-primary',
       'guest-preverify-secondary'
     )
       and revoked_at is null
       and expires_at > pg_catalog.clock_timestamp()
  )
  and (select count(*) = 1
         from public.sessions
        where user_id = 'a1000000-0000-4000-8000-000000000005'
          and revoked_at is null
          and token_hash = 'verified-fresh-session'),
  'guest verification did not revoke every old token and leave one fresh session'
);

set role service_role;
create temporary table guest_verification_replay_result as
select * from public.verify_guest_and_create_session_v1(
  'a1000000-0000-4000-8000-000000000005',
  'guest-verification-hash',
  'a3000000-0000-4000-8000-000000000104',
  'verified-replay-must-not-persist',
  pg_catalog.clock_timestamp() + interval '365 days',
  'verification-replay-browser',
  'Replayed verification link',
  'web',
  '{"client":"web","platform":"web"}'::jsonb,
  '127.0.0.2',
  'PostgreSQL replay gate'
);
reset role;
select pg_temp.assert_true(
  not exists (select 1 from guest_verification_replay_result)
  and not exists (
    select 1 from public.sessions
     where token_hash = 'verified-replay-must-not-persist'
  ),
  'a guest verification replay created or rotated a session'
);

-- A settings-only request retains the guest authority it had when admitted.
-- If verification owns the user row first, the stale request waits, observes
-- the registered identity after commit, and cannot mutate registered settings.
insert into public.users (
  id, is_guest, is_verified, verification_token_hash,
  verification_token_expires
) values (
  'a1000000-0000-4000-8000-000000000006',
  true,
  false,
  'settings-verification-first-hash',
  pg_catalog.clock_timestamp() + interval '1 day'
);
insert into public.user_settings (user_id, assistant_name)
values (
  'a1000000-0000-4000-8000-000000000006',
  'Before verification-first race'
);

select public.dblink_connect(
  'settings_verification_first',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'settings-verification-first'
  )
);
select public.dblink_connect(
  'stale_guest_settings_waiter',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'stale-guest-settings-waiter'
  )
);
select public.dblink_exec('settings_verification_first', 'begin');
select public.dblink_exec('settings_verification_first', 'set role service_role');
create temporary table settings_verification_first_result as
select result.*
  from public.dblink(
    'settings_verification_first',
    $query$
      select * from public.verify_guest_and_create_session_v1(
        'a1000000-0000-4000-8000-000000000006',
        'settings-verification-first-hash',
        'a3000000-0000-4000-8000-000000000106',
        'settings-verification-first-session',
        pg_catalog.clock_timestamp() + interval '365 days',
        'settings-verification-first-device',
        'Verification first',
        'web',
        '{}'::jsonb,
        '127.0.0.6',
        'PostgreSQL settings verification-first gate'
      )
    $query$
  ) as result(
    converted boolean,
    user_data jsonb,
    session_data jsonb,
    revoked_sessions bigint
  );
select public.dblink_exec('stale_guest_settings_waiter', 'set role service_role');
select public.dblink_send_query(
  'stale_guest_settings_waiter',
  $query$
    select * from public.apply_guest_user_settings_v1(
      'a1000000-0000-4000-8000-000000000006',
      '{"assistant_name":"Stale guest request must not persist"}'::jsonb,
      pg_catalog.clock_timestamp()
    )
  $query$
);
do $wait_for_stale_settings_after_verification$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'stale-guest-settings-waiter'
         and wait_event_type = 'Lock'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;
  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'stale-guest-settings-waiter'
       and wait_event_type = 'Lock'
  ) then
    raise exception 'stale guest settings did not wait for verification';
  end if;
end;
$wait_for_stale_settings_after_verification$;
select public.dblink_exec('settings_verification_first', 'commit');
create temporary table stale_guest_settings_result as
select result.*
  from public.dblink_get_result('stale_guest_settings_waiter') as result(
    accepted boolean,
    outcome text,
    settings_data jsonb
  );
select pg_temp.assert_true(
  (select converted is true from settings_verification_first_result)
  and (select not accepted and outcome = 'not_guest'
         from stale_guest_settings_result)
  and (select is_verified is true and is_guest is false
         from public.users
        where id = 'a1000000-0000-4000-8000-000000000006')
  and (select assistant_name = 'Before verification-first race'
         from public.user_settings
        where user_id = 'a1000000-0000-4000-8000-000000000006'),
  'a stale guest settings request wrote after verification committed'
);
select public.dblink_disconnect('settings_verification_first');
select public.dblink_disconnect('stale_guest_settings_waiter');

-- Reverse ordering: when guest settings owns the shared control and user
-- locks first, verification waits. The write commits while the identity is
-- still a guest, then verification removes guest authority.
insert into public.users (
  id, is_guest, is_verified, verification_token_hash,
  verification_token_expires
) values (
  'a1000000-0000-4000-8000-000000000007',
  true,
  false,
  'settings-first-verification-hash',
  pg_catalog.clock_timestamp() + interval '1 day'
);
insert into public.user_settings (user_id, assistant_name)
values (
  'a1000000-0000-4000-8000-000000000007',
  'Before settings-first race'
);

select public.dblink_connect(
  'guest_settings_before_verification',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-settings-before-verification'
  )
);
select public.dblink_connect(
  'verification_after_guest_settings',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'verification-after-guest-settings'
  )
);
select public.dblink_exec('guest_settings_before_verification', 'begin');
select public.dblink_exec('guest_settings_before_verification', 'set role service_role');
create temporary table guest_settings_before_verification_result as
select result.*
  from public.dblink(
    'guest_settings_before_verification',
    $query$
      select * from public.apply_guest_user_settings_v1(
        'a1000000-0000-4000-8000-000000000007',
        '{"assistant_name":"Guest settings committed first"}'::jsonb,
        pg_catalog.clock_timestamp()
      )
    $query$
  ) as result(
    accepted boolean,
    outcome text,
    settings_data jsonb
  );
select public.dblink_exec('verification_after_guest_settings', 'set role service_role');
select public.dblink_send_query(
  'verification_after_guest_settings',
  $query$
    select * from public.verify_guest_and_create_session_v1(
      'a1000000-0000-4000-8000-000000000007',
      'settings-first-verification-hash',
      'a3000000-0000-4000-8000-000000000107',
      'settings-first-verification-session',
      pg_catalog.clock_timestamp() + interval '365 days',
      'settings-first-verification-device',
      'Settings first',
      'web',
      '{}'::jsonb,
      '127.0.0.7',
      'PostgreSQL settings-first verification gate'
    )
  $query$
);
do $wait_for_verification_after_guest_settings$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'verification-after-guest-settings'
         and wait_event_type = 'Lock'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;
  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'verification-after-guest-settings'
       and wait_event_type = 'Lock'
  ) then
    raise exception 'verification did not wait for in-flight guest settings';
  end if;
end;
$wait_for_verification_after_guest_settings$;
select public.dblink_exec('guest_settings_before_verification', 'commit');
create temporary table verification_after_guest_settings_result as
select result.*
  from public.dblink_get_result('verification_after_guest_settings') as result(
    converted boolean,
    user_data jsonb,
    session_data jsonb,
    revoked_sessions bigint
  );
select pg_temp.assert_true(
  (select accepted and outcome = 'accepted'
     from guest_settings_before_verification_result)
  and (select converted is true
         from verification_after_guest_settings_result)
  and (select assistant_name = 'Guest settings committed first'
         from public.user_settings
        where user_id = 'a1000000-0000-4000-8000-000000000007')
  and (select is_verified is true and is_guest is false
         from public.users
        where id = 'a1000000-0000-4000-8000-000000000007'),
  'guest settings and verification did not serialize by lock ownership'
);
select public.dblink_disconnect('guest_settings_before_verification');
select public.dblink_disconnect('verification_after_guest_settings');

insert into public.users (id, is_guest)
values
  ('a1000000-0000-4000-8000-000000000010', true),
  ('a1000000-0000-4000-8000-000000000011', true),
  ('a1000000-0000-4000-8000-000000000012', true),
  ('a1000000-0000-4000-8000-000000000020', false);

insert into public.user_settings (user_id, assistant_name)
values
  ('a1000000-0000-4000-8000-000000000011', 'Guest setting while enabled'),
  ('a1000000-0000-4000-8000-000000000020', 'Registered setting');

insert into public.user_chats (
  user_id, chat_id, title, messages, revision
) values (
  'a1000000-0000-4000-8000-000000000011',
  'a2000000-0000-4000-8000-000000000001',
  'Preserved guest work',
  '[{"role":"user","content":"keep me"}]'::jsonb,
  1
);

insert into public.sessions (
  id, user_id, token_hash, expires_at, revoked_at
) values
  (
    'a3000000-0000-4000-8000-000000000001',
    'a1000000-0000-4000-8000-000000000010',
    'guest-active-a',
    pg_catalog.clock_timestamp() + interval '1 day',
    null
  ),
  (
    'a3000000-0000-4000-8000-000000000002',
    'a1000000-0000-4000-8000-000000000011',
    'guest-active-b',
    pg_catalog.clock_timestamp() + interval '1 day',
    null
  ),
  (
    'a3000000-0000-4000-8000-000000000003',
    'a1000000-0000-4000-8000-000000000011',
    'guest-already-revoked',
    pg_catalog.clock_timestamp() + interval '1 day',
    '2020-01-01 00:00:00+00'::timestamptz
  ),
  (
    'a3000000-0000-4000-8000-000000000004',
    'a1000000-0000-4000-8000-000000000020',
    'registered-active',
    pg_catalog.clock_timestamp() + interval '1 day',
    null
  ),
  (
    'a3000000-0000-4000-8000-000000000005',
    'a1000000-0000-4000-8000-000000000020',
    'registered-already-revoked',
    pg_catalog.clock_timestamp() + interval '1 day',
    '2020-02-01 00:00:00+00'::timestamptz
  );

set role service_role;
create temporary table initial_disable_result as
select * from public.set_guest_mode_enabled_v1(false);
reset role;
select pg_temp.assert_true(
  (select enabled is false and revoked_sessions = 2
     from initial_disable_result),
  'disable did not revoke exactly the two active guest sessions'
);
select pg_temp.assert_true(
  not exists (
    select 1
      from public.sessions as session
      join public.users as account on account.id = session.user_id
     where account.is_guest is true
       and session.revoked_at is null
  ),
  'an active guest session survived disablement'
);
select pg_temp.assert_true(
  not exists (
    select 1
      from public.sessions as session
      join public.users as account on account.id = session.user_id
     where account.is_guest is true
       and session.token_hash in ('guest-active-a', 'guest-active-b')
       and (
         session.device_info ->> 'guestControlRevokedAt' is null
         or (
           session.device_info ->> 'guestControlRevokedAt'
         )::timestamptz <> session.revoked_at
       )
  ),
  'disablement did not mark the exact control-owned guest revocation timestamp'
);
select pg_temp.assert_true(
  (select revoked_at is null
     from public.sessions
    where token_hash = 'registered-active')
  and
  (select revoked_at = '2020-02-01 00:00:00+00'::timestamptz
     from public.sessions
    where token_hash = 'registered-already-revoked')
  and
  (select revoked_at = '2020-01-01 00:00:00+00'::timestamptz
     from public.sessions
    where token_hash = 'guest-already-revoked'),
  'disablement modified a registered or already-revoked session'
);

set role service_role;
create temporary table repeated_disable_result as
select * from public.set_guest_mode_enabled_v1(false);
reset role;
select pg_temp.assert_true(
  (select enabled is false and revoked_sessions = 0
     from repeated_disable_result),
  'a repeated disable was not idempotent'
);

set role service_role;
create temporary table non_resurrecting_enable_result as
select * from public.set_guest_mode_enabled_v1(true);
reset role;
select pg_temp.assert_true(
  (select enabled is true and revoked_sessions = 0
     from non_resurrecting_enable_result)
  and not exists (
    select 1
      from public.sessions as session
      join public.users as account on account.id = session.user_id
     where account.is_guest is true
       and session.revoked_at is null
  ),
  're-enable resurrected a previously revoked guest session'
);

set role service_role;
create temporary table restore_disabled_result as
select * from public.set_guest_mode_enabled_v1(false);
reset role;
select pg_temp.assert_true(
  (select enabled is false and revoked_sessions = 0
     from restore_disabled_result),
  'restoring the disabled state unexpectedly revoked another session'
);

-- This is the active-session predicate used by the pre-guest parent. A raw
-- rollback must not be able to authenticate a drained guest token.
select pg_temp.assert_true(
  not exists (
    select 1
      from public.sessions
     where token_hash = 'guest-active-a'
       and revoked_at is null
       and expires_at > pg_catalog.clock_timestamp()
  ),
  'the parent-shaped active-session lookup still found a guest token'
);

do $no_reactivation_while_off$
begin
  begin
    update public.sessions
       set revoked_at = null
     where token_hash = 'guest-active-b';
    raise exception 'a guest session was reactivated while guest mode was off';
  exception when sqlstate 'GX003' then
    null;
  end;

  begin
    insert into public.sessions (user_id, token_hash, expires_at)
    values (
      'a1000000-0000-4000-8000-000000000011',
      'guest-new-while-off',
      pg_catalog.clock_timestamp() + interval '1 day'
    );
    raise exception 'an active guest session was inserted while guest mode was off';
  exception when sqlstate 'GX003' then
    null;
  end;
end;
$no_reactivation_while_off$;
select pg_temp.assert_true(
  not exists (
    select 1 from public.sessions
     where token_hash = 'guest-new-while-off'
  ),
  'a rejected off-state guest session was persisted'
);

do $no_guest_settings_write_while_off$
begin
  begin
    update public.user_settings
       set assistant_name = 'Must not persist'
     where user_id = 'a1000000-0000-4000-8000-000000000011';
    raise exception 'guest settings changed while guest mode was off';
  exception when sqlstate 'GX003' then
    null;
  end;

  begin
    insert into public.user_settings (user_id, assistant_name)
    values (
      'a1000000-0000-4000-8000-000000000012',
      'Must not insert'
    );
    raise exception 'guest settings were inserted while guest mode was off';
  exception when sqlstate 'GX003' then
    null;
  end;
end;
$no_guest_settings_write_while_off$;
update public.user_settings
   set assistant_name = 'Registered setting while guest mode is off'
 where user_id = 'a1000000-0000-4000-8000-000000000020';
select pg_temp.assert_true(
  (select assistant_name = 'Guest setting while enabled'
     from public.user_settings
    where user_id = 'a1000000-0000-4000-8000-000000000011')
  and not exists (
    select 1 from public.user_settings
     where user_id = 'a1000000-0000-4000-8000-000000000012'
  )
  and
  (select assistant_name = 'Registered setting while guest mode is off'
     from public.user_settings
    where user_id = 'a1000000-0000-4000-8000-000000000020'),
  'the settings trigger did not reject guests while preserving registered writes'
);

-- Registered sessions remain usable while the guest-only path is disabled.
insert into public.sessions (user_id, token_hash, expires_at)
values (
  'a1000000-0000-4000-8000-000000000020',
  'registered-created-while-off',
  pg_catalog.clock_timestamp() + interval '1 day'
);
select pg_temp.assert_true(
  exists (
    select 1 from public.sessions
     where token_hash = 'registered-created-while-off'
       and revoked_at is null
  ),
  'guest disablement blocked a registered session'
);

-- Legacy conversion code may update only is_verified. The user trigger must
-- remove guest status even while new guest identities are disabled.
update public.users
   set is_verified = true
 where id = 'a1000000-0000-4000-8000-000000000010';
select pg_temp.assert_true(
  (select is_verified is true and is_guest is false
     from public.users
    where id = 'a1000000-0000-4000-8000-000000000010'),
  'verification did not clear the guest identity flag'
);
insert into public.sessions (user_id, token_hash, expires_at)
values (
  'a1000000-0000-4000-8000-000000000010',
  'converted-registered-active',
  pg_catalog.clock_timestamp() + interval '1 day'
);

select pg_temp.assert_true(
  exists (
    select 1 from public.user_chats
     where user_id = 'a1000000-0000-4000-8000-000000000011'
       and chat_id = 'a2000000-0000-4000-8000-000000000001'
       and messages = '[{"role":"user","content":"keep me"}]'::jsonb
  ),
  'disablement deleted or changed preserved guest conversation data'
);

-- Race order one: mint obtains the shared control lock first. Disable waits,
-- then drains the just-committed guest session before it can remain active.
set role service_role;
select * from public.set_guest_mode_enabled_v1(true);
reset role;
insert into public.users (id, is_guest)
values
  ('a1000000-0000-4000-8000-000000000030', true),
  ('a1000000-0000-4000-8000-000000000031', true);

insert into public.user_settings (user_id, assistant_name)
values (
  'a1000000-0000-4000-8000-000000000030',
  'Guest setting before disable race'
);

-- A guest settings writer owns the same shared control lock as other guest
-- writes. Disable must wait for that transaction, then all later settings
-- mutations observe the disabled state and fail closed.
select public.dblink_connect(
  'guest_settings_first',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-settings-first'
  )
);
select public.dblink_connect(
  'guest_disable_after_settings',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-disable-after-settings'
  )
);
select public.dblink_exec('guest_settings_first', 'begin');
select public.dblink_exec('guest_settings_first', 'set role service_role');
create temporary table guest_settings_first_result as
select result.*
  from public.dblink(
    'guest_settings_first',
    $query$
      select * from public.apply_guest_user_settings_v1(
        'a1000000-0000-4000-8000-000000000030',
        '{"assistant_name":"Guest setting committed before disable"}'::jsonb,
        pg_catalog.clock_timestamp()
      )
    $query$
  ) as result(
    accepted boolean,
    outcome text,
    settings_data jsonb
  );
select public.dblink_exec('guest_disable_after_settings', 'set role service_role');
select public.dblink_send_query(
  'guest_disable_after_settings',
  'select * from public.set_guest_mode_enabled_v1(false)'
);
do $wait_for_disable_after_settings$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'guest-disable-after-settings'
         and wait_event_type = 'Lock'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;
  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'guest-disable-after-settings'
       and wait_event_type = 'Lock'
  ) then
    raise exception 'disable did not wait for the guest-settings shared lock';
  end if;
end;
$wait_for_disable_after_settings$;
select public.dblink_exec('guest_settings_first', 'commit');
create temporary table settings_first_disable_result as
select result.*
  from public.dblink_get_result('guest_disable_after_settings') as result(
    enabled boolean,
    revoked_sessions bigint,
    updated_at timestamptz
  );
select pg_temp.assert_true(
  (select accepted and outcome = 'accepted'
     from guest_settings_first_result)
  and (select enabled is false from settings_first_disable_result)
  and
  (select assistant_name = 'Guest setting committed before disable'
     from public.user_settings
    where user_id = 'a1000000-0000-4000-8000-000000000030'),
  'guest settings and disable did not serialize at the shared control lock'
);
select public.dblink_disconnect('guest_settings_first');
select public.dblink_disconnect('guest_disable_after_settings');

set role service_role;
select * from public.set_guest_mode_enabled_v1(true);
reset role;

select public.dblink_connect(
  'guest_mint_first',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-mint-first'
  )
);
select public.dblink_connect(
  'guest_disable_waiter',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-disable-waiter'
  )
);
select public.dblink_exec('guest_mint_first', 'begin');
select public.dblink_exec('guest_mint_first', 'set role service_role');
select public.dblink_exec(
  'guest_mint_first',
  $command$
    insert into public.sessions (user_id, token_hash, expires_at)
    values (
      'a1000000-0000-4000-8000-000000000030',
      'guest-mint-before-disable',
      pg_catalog.clock_timestamp() + interval '1 day'
    )
  $command$
);
select public.dblink_exec('guest_disable_waiter', 'set role service_role');
select public.dblink_send_query(
  'guest_disable_waiter',
  'select * from public.set_guest_mode_enabled_v1(false)'
);

do $wait_for_disable$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'guest-disable-waiter'
         and wait_event_type = 'Lock'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;

  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'guest-disable-waiter'
       and wait_event_type = 'Lock'
  ) then
    raise exception 'disable did not wait for the mint-first shared control lock';
  end if;
end;
$wait_for_disable$;

select public.dblink_exec('guest_mint_first', 'commit');
create temporary table mint_first_disable_result as
select result.*
  from public.dblink_get_result('guest_disable_waiter') as result(
    enabled boolean,
    revoked_sessions bigint,
    updated_at timestamptz
  );
select pg_temp.assert_true(
  (select enabled is false and revoked_sessions = 1
     from mint_first_disable_result)
  and not exists (
    select 1 from public.sessions
     where token_hash = 'guest-mint-before-disable'
       and revoked_at is null
  ),
  'mint-before-disable left an active guest session'
);
select public.dblink_disconnect('guest_mint_first');
select public.dblink_disconnect('guest_disable_waiter');

-- Race order two: disable obtains the exclusive control lock first. A guest
-- mint waits, observes disabled after commit, and fails without a session row.
set role service_role;
select * from public.set_guest_mode_enabled_v1(true);
reset role;
select public.dblink_connect(
  'guest_disable_first',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-disable-first'
  )
);
select public.dblink_connect(
  'guest_mint_waiter',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-mint-waiter'
  )
);
select public.dblink_exec('guest_disable_first', 'begin');
select public.dblink_exec('guest_disable_first', 'set role service_role');
create temporary table disable_first_result as
select result.*
  from public.dblink(
    'guest_disable_first',
    'select * from public.set_guest_mode_enabled_v1(false)'
  ) as result(
    enabled boolean,
    revoked_sessions bigint,
    updated_at timestamptz
  );
select public.dblink_exec('guest_mint_waiter', 'set role service_role');
select public.dblink_send_query(
  'guest_mint_waiter',
  $query$
    insert into public.sessions (user_id, token_hash, expires_at)
    values (
      'a1000000-0000-4000-8000-000000000031',
      'guest-mint-after-disable',
      pg_catalog.clock_timestamp() + interval '1 day'
    )
    returning id
  $query$
);

do $wait_for_mint$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'guest-mint-waiter'
         and wait_event_type = 'Lock'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;

  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'guest-mint-waiter'
       and wait_event_type = 'Lock'
  ) then
    raise exception 'mint did not wait for the disable-first exclusive control lock';
  end if;
end;
$wait_for_mint$;

select public.dblink_exec('guest_disable_first', 'commit');
create temporary table disable_first_mint_result as
select result.*
  from public.dblink_get_result('guest_mint_waiter', false) as result(id uuid);
select pg_temp.assert_true(
  not exists (select 1 from disable_first_mint_result)
  and public.dblink_error_message('guest_mint_waiter')
      ilike '%Guest mode is disabled%'
  and not exists (
    select 1 from public.sessions
     where token_hash = 'guest-mint-after-disable'
  ),
  'disable-before-mint did not reject the waiting guest session'
);
select public.dblink_disconnect('guest_disable_first');
select public.dblink_disconnect('guest_mint_waiter');

-- UPDATE race order one: reactivation takes the shared control lock and the
-- session tuple first. Disable waits, then drains that newly active row after
-- reactivation commits.
set role service_role;
select * from public.set_guest_mode_enabled_v1(true);
reset role;
insert into public.sessions (
  id, user_id, token_hash, expires_at, revoked_at
) values (
  'a3000000-0000-4000-8000-000000000030',
  'a1000000-0000-4000-8000-000000000030',
  'guest-reactivation-before-disable',
  pg_catalog.clock_timestamp() + interval '1 day',
  pg_catalog.clock_timestamp()
);

select public.dblink_connect(
  'guest_reactivation_first',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-reactivation-first'
  )
);
select public.dblink_connect(
  'guest_disable_after_reactivation',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-disable-after-reactivation'
  )
);
select public.dblink_exec('guest_reactivation_first', 'begin');
select public.dblink_exec('guest_reactivation_first', 'set role service_role');
select public.dblink_exec(
  'guest_reactivation_first',
  $command$
    update public.sessions
       set revoked_at = null
     where token_hash = 'guest-reactivation-before-disable'
  $command$
);
select public.dblink_exec(
  'guest_disable_after_reactivation', 'set role service_role'
);
select public.dblink_send_query(
  'guest_disable_after_reactivation',
  'select * from public.set_guest_mode_enabled_v1(false)'
);

do $wait_for_disable_after_reactivation$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'guest-disable-after-reactivation'
         and wait_event_type = 'Lock'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;

  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'guest-disable-after-reactivation'
       and wait_event_type = 'Lock'
  ) then
    raise exception 'disable did not wait for the reactivation-first shared lock';
  end if;
end;
$wait_for_disable_after_reactivation$;

select public.dblink_exec('guest_reactivation_first', 'commit');
create temporary table reactivation_first_disable_result as
select result.*
  from public.dblink_get_result(
    'guest_disable_after_reactivation'
  ) as result(
    enabled boolean,
    revoked_sessions bigint,
    updated_at timestamptz
  );
select pg_temp.assert_true(
  (select enabled is false and revoked_sessions = 1
     from reactivation_first_disable_result)
  and
  (select revoked_at is not null
     from public.sessions
    where token_hash = 'guest-reactivation-before-disable'),
  'reactivation-before-disable left its guest session active'
);
select public.dblink_disconnect('guest_reactivation_first');
select public.dblink_disconnect('guest_disable_after_reactivation');

-- UPDATE race order two: disable owns the exclusive control lock while an
-- update already has an active session tuple. The trigger's NOWAIT path must
-- fail closed promptly, release the tuple, and let disable drain the session.
set role service_role;
select * from public.set_guest_mode_enabled_v1(true);
reset role;
insert into public.sessions (
  id, user_id, token_hash, expires_at, revoked_at
) values (
  'a3000000-0000-4000-8000-000000000031',
  'a1000000-0000-4000-8000-000000000031',
  'guest-reactivation-after-disable',
  pg_catalog.clock_timestamp() + interval '1 day',
  null
);

select public.dblink_connect(
  'guest_disable_control_holder',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-disable-control-holder'
  )
);
select public.dblink_connect(
  'guest_reactivation_waiter',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-reactivation-waiter'
  )
);
select public.dblink_exec('guest_disable_control_holder', 'begin');
select public.dblink_exec(
  'guest_disable_control_holder',
  $command$
    do $hold_control$
    declare
      control_enabled boolean;
    begin
      select control.enabled
        into control_enabled
        from public.guest_mode_control as control
       where control.singleton is true
       for update;
    end;
    $hold_control$
  $command$
);
select public.dblink_exec('guest_reactivation_waiter', 'set role service_role');
select public.dblink_send_query(
  'guest_reactivation_waiter',
  $query$
    update public.sessions
       set last_activity = pg_catalog.clock_timestamp()
     where token_hash = 'guest-reactivation-after-disable'
    returning id
  $query$
);

do $wait_for_nowait_rejection$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when public.dblink_is_busy('guest_reactivation_waiter') = 0;
    perform pg_catalog.pg_sleep(0.05);
  end loop;

  if public.dblink_is_busy('guest_reactivation_waiter') <> 0 then
    raise exception 'the active-session UPDATE deadlocked behind guest disablement';
  end if;
end;
$wait_for_nowait_rejection$;

create temporary table disable_first_reactivation_result as
select result.*
  from public.dblink_get_result(
    'guest_reactivation_waiter', false
  ) as result(id uuid);
select pg_temp.assert_true(
  not exists (select 1 from disable_first_reactivation_result)
  and public.dblink_error_message('guest_reactivation_waiter')
      ilike '%Guest mode is disabled%',
  'disable-first did not promptly reject an active guest-session UPDATE'
);

create temporary table disable_after_nowait_result as
select result.*
  from public.dblink(
    'guest_disable_control_holder',
    'select * from public.set_guest_mode_enabled_v1(false)'
  ) as result(
    enabled boolean,
    revoked_sessions bigint,
    updated_at timestamptz
  );
select public.dblink_exec('guest_disable_control_holder', 'commit');
select pg_temp.assert_true(
  (select enabled is false and revoked_sessions = 1
     from disable_after_nowait_result)
  and
  (select revoked_at is not null
     from public.sessions
    where token_hash = 'guest-reactivation-after-disable'),
  'disable-first did not drain the guest session after NOWAIT rejection'
);
select public.dblink_disconnect('guest_disable_control_holder');
select public.dblink_disconnect('guest_reactivation_waiter');

-- A registered-session touch never enters the guest-control lock path. It
-- must succeed even while an operator transaction owns the control row.
select public.dblink_connect(
  'registered_control_holder',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'registered-control-holder'
  )
);
select public.dblink_connect(
  'registered_session_update',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'registered-session-update'
  )
);
select public.dblink_exec('registered_control_holder', 'begin');
select public.dblink_exec(
  'registered_control_holder',
  $command$
    do $hold_registered_control$
    declare
      control_enabled boolean;
    begin
      select control.enabled
        into control_enabled
        from public.guest_mode_control as control
       where control.singleton is true
       for update;
    end;
    $hold_registered_control$
  $command$
);
select public.dblink_exec('registered_session_update', 'set role service_role');
select public.dblink_send_query(
  'registered_session_update',
  $query$
    update public.sessions
       set last_activity = pg_catalog.clock_timestamp()
     where token_hash = 'registered-active'
    returning id
  $query$
);
do $wait_for_registered_update$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when public.dblink_is_busy('registered_session_update') = 0;
    perform pg_catalog.pg_sleep(0.05);
  end loop;
  if public.dblink_is_busy('registered_session_update') <> 0 then
    raise exception 'registered-session UPDATE waited on guest control';
  end if;
end;
$wait_for_registered_update$;
create temporary table registered_update_result as
select result.*
  from public.dblink_get_result('registered_session_update', false)
    as result(id uuid);
select pg_temp.assert_true(
  exists (select 1 from registered_update_result),
  'guest control blocked or rejected a registered-session UPDATE'
);
select public.dblink_exec('registered_control_holder', 'commit');
select public.dblink_disconnect('registered_control_holder');
select public.dblink_disconnect('registered_session_update');

-- Guest write barrier race: a reservation that already owns the shared
-- control lock may finish first, then disable commits. Every reservation,
-- browser sync, and reply persistence started after that commit is rejected
-- without creating another receipt or conversation.
set role service_role;
select * from public.set_guest_mode_enabled_v1(true);
reset role;
select public.dblink_connect(
  'guest_write_first',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-write-first'
  )
);
select public.dblink_connect(
  'guest_disable_after_write',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(), current_user, 'guest-disable-after-write'
  )
);
select public.dblink_exec('guest_write_first', 'begin');
select public.dblink_exec('guest_write_first', 'set role service_role');
create temporary table in_flight_reservation_result as
select result.*
  from public.dblink(
    'guest_write_first',
    $query$
      select * from public.reserve_free_message_v1(
        'a1000000-0000-4000-8000-000000000031',
        'a4000000-0000-4000-8000-000000000001',
        repeat('a', 64)
      )
    $query$
  ) as result(
    outcome text,
    event_id uuid,
    used integer,
    remaining integer,
    next_available_at timestamptz
  );
select public.dblink_exec('guest_disable_after_write', 'set role service_role');
select public.dblink_send_query(
  'guest_disable_after_write',
  'select * from public.set_guest_mode_enabled_v1(false)'
);
do $wait_for_disable_after_write$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'guest-disable-after-write'
         and wait_event_type = 'Lock'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;
  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'guest-disable-after-write'
       and wait_event_type = 'Lock'
  ) then
    raise exception 'disable did not wait for the in-flight guest write barrier';
  end if;
end;
$wait_for_disable_after_write$;
select public.dblink_exec('guest_write_first', 'commit');
create temporary table disable_after_write_result as
select result.*
  from public.dblink_get_result('guest_disable_after_write') as result(
    enabled boolean,
    revoked_sessions bigint,
    updated_at timestamptz
  );
select pg_temp.assert_true(
  (select outcome = 'reserved' and event_id is not null
     from in_flight_reservation_result)
  and (select enabled is false from disable_after_write_result),
  'the in-flight write/disable serialization result was incorrect'
);
select public.dblink_disconnect('guest_write_first');
select public.dblink_disconnect('guest_disable_after_write');

set role service_role;
create temporary table disabled_reservation_result as
select * from public.reserve_free_message_v1(
  'a1000000-0000-4000-8000-000000000031',
  'a4000000-0000-4000-8000-000000000002',
  repeat('b', 64)
);
create temporary table disabled_sync_result as
select * from public.apply_guest_chat_sync_v2(
  'a1000000-0000-4000-8000-000000000031',
  'a5000000-0000-4000-8000-000000000001',
  'Disabled sync',
  '[]'::jsonb,
  pg_catalog.clock_timestamp(),
  pg_catalog.clock_timestamp(),
  null,
  1
);
create temporary table disabled_reply_result as
select * from public.persist_guest_chat_reply_v1(
  'a1000000-0000-4000-8000-000000000031',
  'a5000000-0000-4000-8000-000000000002',
  'Disabled reply',
  pg_catalog.jsonb_build_object(
    'id', 'disabled-user', 'role', 'user', 'content', 'Hello'
  ),
  pg_catalog.jsonb_build_object(
    'id', 'disabled-assistant', 'role', 'assistant',
    'inReplyTo', 'disabled-user', 'content', 'Hi'
  )
);
create temporary table disabled_settings_result as
select * from public.apply_guest_user_settings_v1(
  'a1000000-0000-4000-8000-000000000030',
  '{"assistant_name":"Disabled settings must not persist"}'::jsonb,
  pg_catalog.clock_timestamp()
);
reset role;
select pg_temp.assert_true(
  (select outcome = 'guest_mode_disabled' and event_id is null
     from disabled_reservation_result)
  and (select not accepted and outcome = 'guest_mode_disabled'
         from disabled_sync_result)
  and (select not accepted and outcome = 'guest_mode_disabled'
         from disabled_reply_result)
  and (select not accepted and outcome = 'guest_mode_disabled'
         from disabled_settings_result)
  and not exists (
    select 1 from public.usage_events
     where user_id = 'a1000000-0000-4000-8000-000000000031'
       and idempotency_key like 'a4000000-0000-4000-8000-000000000002:%'
  )
  and not exists (
    select 1 from public.user_chats
     where user_id = 'a1000000-0000-4000-8000-000000000031'
       and chat_id in (
         'a5000000-0000-4000-8000-000000000001',
         'a5000000-0000-4000-8000-000000000002'
       )
  )
  and (select assistant_name = 'Guest setting committed before disable'
         from public.user_settings
        where user_id = 'a1000000-0000-4000-8000-000000000030'
  ),
  'a guest write persisted after disable committed'
);

-- Deleting the row simulates a damaged or partial control state. Every guest
-- path must remain closed; registered session creation remains independent.
delete from public.guest_mode_control where singleton is true;
set role service_role;
create temporary table missing_guest_mode_status as
select * from public.get_guest_mode_control_v1();
reset role;
select pg_temp.assert_true(
  (select enabled is false and updated_at is null
     from missing_guest_mode_status),
  'a missing control row did not read as fail-closed'
);

do $missing_control_fails_closed$
begin
  begin
    update public.sessions
       set revoked_at = null
     where token_hash = 'guest-active-b';
    raise exception 'a guest session reactivated with no control row';
  exception when sqlstate 'GX003' then
    null;
  end;

  begin
    update public.users
       set is_guest = true
     where id = 'a1000000-0000-4000-8000-000000000020';
    raise exception 'a user became a guest with no control row';
  exception when sqlstate 'GX003' then
    null;
  end;

  begin
    update public.user_settings
       set assistant_name = 'Must not persist without control'
     where user_id = 'a1000000-0000-4000-8000-000000000030';
    raise exception 'guest settings changed with no control row';
  exception when sqlstate 'GX003' then
    null;
  end;

  begin
    perform * from public.set_guest_mode_enabled_v1(true);
    raise exception 'the setter recreated or enabled a missing control row';
  exception when sqlstate 'GX004' then
    null;
  end;
end;
$missing_control_fails_closed$;

insert into public.sessions (user_id, token_hash, expires_at)
values (
  'a1000000-0000-4000-8000-000000000020',
  'registered-with-missing-control',
  pg_catalog.clock_timestamp() + interval '1 day'
);
select pg_temp.assert_true(
  exists (
    select 1 from public.sessions
     where token_hash = 'registered-with-missing-control'
       and revoked_at is null
  ),
  'a missing guest control row blocked a registered session'
);

update public.user_settings
   set assistant_name = 'Registered setting with missing control'
 where user_id = 'a1000000-0000-4000-8000-000000000020';
select pg_temp.assert_true(
  (select assistant_name = 'Registered setting with missing control'
     from public.user_settings
    where user_id = 'a1000000-0000-4000-8000-000000000020'),
  'a missing guest control row blocked registered settings'
);
