-- A password submitted before inbox verification is not an authenticated
-- credential. Disable every pending password, revoke pre-verification sessions,
-- and require the inbox-proof session (or password reset) to establish the
-- first usable password.
--
-- The production migration runner owns the transaction boundary.

set local lock_timeout = '5s';
set local statement_timeout = '30s';

do $preflight$
declare
  v_signature regprocedure;
  v_owner name;
  v_existing_setup regprocedure := pg_catalog.to_regprocedure(
    'public.complete_initial_password_setup_v1(uuid,uuid,text,text)'
  );
begin
  if pg_catalog.to_regclass('public.users') is null
     or pg_catalog.to_regclass('public.sessions') is null then
    raise exception 'Password-setup prerequisites are missing.'
      using errcode = '55000';
  end if;

  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'service_role')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'anon')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated') then
    raise exception 'Password-setup database roles are missing.'
      using errcode = '55000';
  end if;

  if (
    select count(*)
      from information_schema.columns
     where table_schema = 'public'
       and (
         (
           table_name = 'users'
           and (
             (column_name = 'id' and data_type = 'uuid')
             or (column_name = 'password_hash' and data_type = 'text')
             or (column_name = 'is_verified' and data_type = 'boolean')
             or (column_name = 'is_guest' and data_type = 'boolean')
             or (column_name = 'verification_token_hash' and data_type = 'text')
             or (
               column_name = 'verification_token_expires'
               and data_type = 'timestamp with time zone'
             )
             or (column_name = 'password_reset_token_hash' and data_type = 'text')
             or (
               column_name = 'password_reset_expires'
               and data_type = 'timestamp with time zone'
             )
             or (column_name = 'updated_at' and data_type = 'timestamp with time zone')
             or (column_name = 'deleted_at' and data_type = 'timestamp with time zone')
           )
         )
         or (
           table_name = 'sessions'
           and (
             (column_name = 'id' and data_type = 'uuid')
             or (column_name = 'user_id' and data_type = 'uuid')
             or (column_name = 'token_hash' and data_type = 'text')
             or (column_name = 'device_id' and data_type = 'text')
             or (column_name = 'device_name' and data_type = 'text')
             or (column_name = 'platform' and data_type = 'text')
             or (column_name = 'device_info' and data_type = 'jsonb')
             or (column_name = 'ip_address' and data_type = 'text')
             or (column_name = 'user_agent' and data_type = 'text')
             or (
               column_name = 'created_at'
               and data_type = 'timestamp with time zone'
             )
             or (
               column_name = 'last_activity'
               and data_type = 'timestamp with time zone'
             )
             or (
               column_name = 'expires_at'
               and data_type = 'timestamp with time zone'
             )
             or (
               column_name = 'revoked_at'
               and data_type = 'timestamp with time zone'
             )
           )
         )
       )
  ) <> 23 then
    raise exception 'Unexpected password-setup table definitions; refusing migration.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'users'
       and column_name = 'password_setup_required'
       and (
         data_type <> 'boolean'
         or is_nullable <> 'NO'
         or column_default is distinct from 'false'
       )
  ) then
    raise exception 'Unexpected users.password_setup_required definition.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'users'
       and column_name = 'password_inbox_bound_at'
       and (
         data_type <> 'timestamp with time zone'
         or is_nullable <> 'YES'
       )
  ) then
    raise exception 'Unexpected users.password_inbox_bound_at definition.'
      using errcode = '55000';
  end if;

  foreach v_signature in array array[
    pg_catalog.to_regprocedure('public.consume_password_reset_v1(text,text)'),
    pg_catalog.to_regprocedure(
      'public.finalize_password_login_v1(uuid,text,text,uuid,text,timestamp with time zone,text,text,text,jsonb,text,text)'
    ),
    pg_catalog.to_regprocedure(
      'public.verify_registered_and_create_session_v1(uuid,text,uuid,text,timestamp with time zone,text,text,text,jsonb,text,text)'
    ),
    pg_catalog.to_regprocedure(
      'public.verify_guest_and_create_session_v1(uuid,text,uuid,text,timestamp with time zone,text,text,text,jsonb,text,text)'
    )
  ]
  loop
    if v_signature is null then
      raise exception 'A password-setup prerequisite function is missing.'
        using errcode = '55000';
    end if;

    select pg_catalog.pg_get_userbyid(function_row.proowner)
      into v_owner
      from pg_catalog.pg_proc as function_row
     where function_row.oid = v_signature;

    if v_owner <> 'postgres'
       or not pg_catalog.has_function_privilege(
         'service_role', v_signature, 'EXECUTE'
       )
       or pg_catalog.has_function_privilege('anon', v_signature, 'EXECUTE')
       or pg_catalog.has_function_privilege(
         'authenticated', v_signature, 'EXECUTE'
       )
       or (
         select count(*) <> 2
            or bool_or(
              acl_row.grantee not in (
                function_row.proowner,
                (select oid from pg_catalog.pg_roles where rolname = 'service_role')
              )
            )
            or bool_or(
              acl_row.grantee = (
                select oid from pg_catalog.pg_roles where rolname = 'service_role'
              )
              and acl_row.is_grantable
            )
           from pg_catalog.pg_proc as function_row
           cross join lateral pg_catalog.aclexplode(
             coalesce(
               function_row.proacl,
               pg_catalog.acldefault('f', function_row.proowner)
             )
           ) as acl_row
          where function_row.oid = v_signature
            and acl_row.privilege_type = 'EXECUTE'
       ) then
      raise exception 'Unexpected password-setup prerequisite function owner or ACL.'
        using errcode = '55000';
    end if;
  end loop;

  if v_existing_setup is not null
     and (
       (
         select pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
           from pg_catalog.pg_proc as function_row
          where function_row.oid = v_existing_setup
       )
       or not pg_catalog.has_function_privilege(
         'service_role', v_existing_setup, 'EXECUTE'
       )
       or pg_catalog.has_function_privilege('anon', v_existing_setup, 'EXECUTE')
       or pg_catalog.has_function_privilege(
         'authenticated', v_existing_setup, 'EXECUTE'
       )
     ) then
    raise exception 'Unexpected complete_initial_password_setup_v1 owner or ACL.'
      using errcode = '55000';
  end if;
end;
$preflight$;

-- The migration must run in one transaction. Block registration, verification,
-- password reset, and session writes until both the historical credential drain
-- and the replacement RPCs are committed; otherwise an old application
-- instance could verify a newly inserted planted credential between statements.
lock table public.users in exclusive mode;
lock table public.sessions in exclusive mode;

alter table public.users
  add column if not exists password_setup_required boolean not null default false;

alter table public.users
  add column if not exists password_inbox_bound_at timestamptz;

comment on column public.users.password_setup_required is
  'True until an inbox-proof session or password-reset bearer establishes the first usable password.';

comment on column public.users.password_inbox_bound_at is
  'Database time when an inbox-proof session or password-reset bearer established the current password; null means provenance is unavailable.';

-- Backfill every live pending registration, including a guest row in the
-- registration-conversion window. Plain guest placeholders have no verification
-- anchor and remain outside this update.
update public.users as account
   set password_hash = '!pending-inbox-password-setup-v1!',
       password_setup_required = true,
       password_inbox_bound_at = null
 where account.is_verified is false
   and account.deleted_at is null
   and account.verification_token_hash is not null;

-- Password provenance was not recorded before this repair. Fail closed for
-- every existing verified password account: disable the old hash and require a
-- fresh password-reset link delivered to the verified inbox. This deliberately
-- includes legitimate passwords because they cannot be distinguished from a
-- pre-registration planted password with defensible evidence.
update public.users as account
   set password_hash = '!pending-inbox-password-setup-v1!',
       password_setup_required = true,
       updated_at = pg_catalog.clock_timestamp()
 where account.is_verified is true
   and account.is_guest is false
   and account.deleted_at is null
   and account.password_inbox_bound_at is null;

-- No session attached to a pending or provenance-unknown password may survive
-- the repair. Pending verification issues a proof-marked successor; accounts
-- already verified recover through the normal inbox password-reset route.
update public.sessions as session
   set revoked_at = pg_catalog.clock_timestamp(),
       device_info = coalesce(session.device_info, '{}'::jsonb)
         || pg_catalog.jsonb_build_object(
              'preverificationPasswordRevokedAt',
              pg_catalog.clock_timestamp()
            )
  from public.users as account
 where account.id = session.user_id
   and account.deleted_at is null
   and account.password_setup_required is true
   and (
     account.verification_token_hash is not null
     or (account.is_verified is true and account.is_guest is false)
   )
   and session.revoked_at is null;

create or replace function public.consume_password_reset_v1(
  p_token_hash text,
  p_password_hash text
)
returns table(reset_applied boolean)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user_id uuid;
  v_reset_expires timestamptz;
  v_now timestamptz;
begin
  if p_token_hash is null
     or p_token_hash !~ '^[0-9a-f]{64}$'
     or p_password_hash is null
     or pg_catalog.length(p_password_hash) < 20
     or pg_catalog.length(p_password_hash) > 1024 then
    raise exception 'Invalid password-reset input.' using errcode = '22023';
  end if;

  select account.id, account.password_reset_expires
    into v_user_id, v_reset_expires
    from public.users as account
   where account.password_reset_token_hash = p_token_hash
   order by account.id
   limit 1
   for update;

  v_now := pg_catalog.clock_timestamp();
  if not found or v_reset_expires is null or v_reset_expires <= v_now then
    return query select false;
    return;
  end if;

  update public.users as account
     set password_hash = p_password_hash,
         password_setup_required = false,
         password_inbox_bound_at = v_now,
         is_verified = true,
         is_guest = false,
         verification_token_hash = null,
         verification_token_expires = null,
         password_reset_token_hash = null,
         password_reset_expires = null,
         updated_at = v_now
   where account.id = v_user_id
     and account.password_reset_token_hash = p_token_hash;

  if not found then
    raise exception 'Password-reset state changed while locked.'
      using errcode = '40001';
  end if;

  update public.sessions as session
     set revoked_at = v_now
   where session.user_id = v_user_id
     and session.revoked_at is null;

  return query select true;
end;
$function$;

create or replace function public.finalize_password_login_v1(
  p_user_id uuid,
  p_expected_password_hash text,
  p_upgraded_password_hash text,
  p_session_id uuid,
  p_session_token_hash text,
  p_session_expires_at timestamptz,
  p_device_id text,
  p_device_name text,
  p_platform text,
  p_device_info jsonb,
  p_ip_address text,
  p_user_agent text
)
returns table(
  login_applied boolean,
  user_data jsonb,
  session_data jsonb,
  pruned_sessions bigint
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_session public.sessions%rowtype;
  v_now timestamptz;
  v_pruned_sessions bigint := 0;
begin
  if p_user_id is null
     or p_expected_password_hash is null
     or pg_catalog.length(p_expected_password_hash) < 20
     or pg_catalog.length(p_expected_password_hash) > 1024
     or (
       p_upgraded_password_hash is not null
       and (
         pg_catalog.length(p_upgraded_password_hash) < 20
         or pg_catalog.length(p_upgraded_password_hash) > 1024
       )
     )
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_expires_at is null then
    raise exception 'Invalid password-login input.' using errcode = '22023';
  end if;

  select account.*
    into v_user
    from public.users as account
   where account.id = p_user_id
   for update;

  v_now := pg_catalog.clock_timestamp();
  if not found
     or v_user.deleted_at is not null
     or v_user.is_verified is not true
     or v_user.is_guest is true
     or v_user.password_setup_required is not false
     or v_user.password_inbox_bound_at is null
     or v_user.password_hash is distinct from p_expected_password_hash
     or p_session_expires_at <= v_now then
    return query select false, null::jsonb, null::jsonb, 0::bigint;
    return;
  end if;

  update public.users as account
     set password_hash = coalesce(p_upgraded_password_hash, account.password_hash),
         last_login = v_now,
         updated_at = v_now
   where account.id = p_user_id
     and account.password_setup_required is false
     and account.password_inbox_bound_at is not null
     and account.password_hash is not distinct from p_expected_password_hash
   returning account.* into v_user;

  if not found then
    raise exception 'Password-login state changed while locked.'
      using errcode = '40001';
  end if;

  insert into public.sessions as persisted (
    id, user_id, token_hash, device_id, device_name, platform, device_info,
    ip_address, user_agent, created_at, last_activity, expires_at, revoked_at
  ) values (
    p_session_id, p_user_id, p_session_token_hash, p_device_id, p_device_name,
    p_platform, coalesce(p_device_info, '{}'::jsonb), p_ip_address, p_user_agent,
    v_now, v_now, p_session_expires_at, null
  )
  on conflict (device_id) do update
     set user_id = excluded.user_id,
         token_hash = excluded.token_hash,
         device_name = excluded.device_name,
         platform = excluded.platform,
         device_info = excluded.device_info,
         ip_address = excluded.ip_address,
         user_agent = excluded.user_agent,
         created_at = excluded.created_at,
         last_activity = excluded.last_activity,
         expires_at = excluded.expires_at,
         revoked_at = null
  returning persisted.* into v_session;

  update public.sessions as session
     set revoked_at = v_now
   where session.id in (
     select active_session.id
       from public.sessions as active_session
      where active_session.user_id = p_user_id
        and active_session.revoked_at is null
        and active_session.id <> v_session.id
      order by active_session.created_at desc, active_session.id desc
      offset 19
   );
  get diagnostics v_pruned_sessions = row_count;

  return query select true, pg_catalog.to_jsonb(v_user),
    pg_catalog.to_jsonb(v_session), v_pruned_sessions;
end;
$function$;

create or replace function public.verify_registered_and_create_session_v1(
  p_user_id uuid,
  p_verification_token_hash text,
  p_session_id uuid,
  p_session_token_hash text,
  p_session_expires_at timestamptz,
  p_device_id text,
  p_device_name text,
  p_platform text,
  p_device_info jsonb,
  p_ip_address text,
  p_user_agent text
)
returns table(
  verification_applied boolean,
  user_data jsonb,
  session_data jsonb,
  pruned_sessions bigint
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_session public.sessions%rowtype;
  v_now timestamptz;
  v_revoked_sessions bigint := 0;
begin
  if p_user_id is null
     or p_verification_token_hash is null
     or p_verification_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_expires_at is null then
    raise exception 'Invalid registered-verification input.' using errcode = '22023';
  end if;

  select account.* into v_user
    from public.users as account
   where account.id = p_user_id
   for update;

  v_now := pg_catalog.clock_timestamp();
  if not found
     or v_user.deleted_at is not null
     or v_user.is_guest is true
     or v_user.is_verified is not false
     or v_user.verification_token_hash is distinct from p_verification_token_hash
     or v_user.verification_token_expires is null
     or v_user.verification_token_expires <= v_now
     or p_session_expires_at <= v_now then
    return query select false, null::jsonb, null::jsonb, 0::bigint;
    return;
  end if;

  update public.users as account
     set is_verified = true,
         password_hash = '!pending-inbox-password-setup-v1!',
         password_setup_required = true,
         password_inbox_bound_at = null,
         verification_token_expires = v_now + interval '15 minutes',
         updated_at = v_now
   where account.id = p_user_id
     and account.is_verified is false
     and account.is_guest is false
     and account.verification_token_hash = p_verification_token_hash
   returning account.* into v_user;

  if not found then
    raise exception 'Registered verification state changed while locked.'
      using errcode = '40001';
  end if;

  update public.sessions as session
     set revoked_at = v_now
   where session.user_id = p_user_id
     and session.revoked_at is null;
  get diagnostics v_revoked_sessions = row_count;

  insert into public.sessions as persisted (
    id, user_id, token_hash, device_id, device_name, platform, device_info,
    ip_address, user_agent, created_at, last_activity, expires_at, revoked_at
  ) values (
    p_session_id, p_user_id, p_session_token_hash, p_device_id, p_device_name,
    p_platform, coalesce(p_device_info, '{}'::jsonb)
      || pg_catalog.jsonb_build_object(
           'passwordSetupProof', 'inbox-verification-v1'
         ),
    p_ip_address, p_user_agent,
    v_now, v_now, p_session_expires_at, null
  )
  on conflict (device_id) do update
     set user_id = excluded.user_id,
         token_hash = excluded.token_hash,
         device_name = excluded.device_name,
         platform = excluded.platform,
         device_info = excluded.device_info,
         ip_address = excluded.ip_address,
         user_agent = excluded.user_agent,
         created_at = excluded.created_at,
         last_activity = excluded.last_activity,
         expires_at = excluded.expires_at,
         revoked_at = null
  returning persisted.* into v_session;

  return query select true, pg_catalog.to_jsonb(v_user),
    pg_catalog.to_jsonb(v_session), v_revoked_sessions;
end;
$function$;

create or replace function public.verify_guest_and_create_session_v1(
  p_user_id uuid,
  p_verification_token_hash text,
  p_session_id uuid,
  p_session_token_hash text,
  p_session_expires_at timestamptz,
  p_device_id text,
  p_device_name text,
  p_platform text,
  p_device_info jsonb,
  p_ip_address text,
  p_user_agent text
)
returns table(
  converted boolean,
  user_data jsonb,
  session_data jsonb,
  revoked_sessions bigint
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_session public.sessions%rowtype;
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_revoked_sessions bigint := 0;
begin
  if p_user_id is null
     or p_verification_token_hash is null
     or p_verification_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_expires_at is null
     or p_session_expires_at <= v_now then
    raise exception 'Guest verification session values are invalid.'
      using errcode = '22023';
  end if;

  select account.* into v_user
    from public.users as account
   where account.id = p_user_id
   for update;

  if not found
     or v_user.deleted_at is not null
     or v_user.is_verified is true
     or v_user.is_guest is not true
     or v_user.verification_token_hash is distinct from p_verification_token_hash
     or v_user.verification_token_expires is null
     or v_user.verification_token_expires <= v_now then
    return;
  end if;

  update public.users as account
     set is_verified = true,
         is_guest = false,
         password_hash = '!pending-inbox-password-setup-v1!',
         password_setup_required = true,
         password_inbox_bound_at = null,
         verification_token_expires = v_now + interval '15 minutes',
         updated_at = v_now
   where account.id = p_user_id
   returning account.* into v_user;

  update public.sessions as session
     set revoked_at = v_now,
         device_info = coalesce(session.device_info, '{}'::jsonb)
           || pg_catalog.jsonb_build_object('guestVerificationRevokedAt', v_now)
   where session.user_id = p_user_id
     and session.revoked_at is null;
  get diagnostics v_revoked_sessions = row_count;

  insert into public.sessions as persisted (
    id, user_id, token_hash, device_id, device_name, platform, device_info,
    ip_address, user_agent, created_at, last_activity, expires_at, revoked_at
  ) values (
    p_session_id, p_user_id, p_session_token_hash, p_device_id, p_device_name,
    p_platform, coalesce(p_device_info, '{}'::jsonb)
      || pg_catalog.jsonb_build_object(
           'passwordSetupProof', 'inbox-verification-v1'
         ),
    p_ip_address, p_user_agent,
    v_now, v_now, p_session_expires_at, null
  )
  on conflict (device_id) do update
     set user_id = excluded.user_id,
         token_hash = excluded.token_hash,
         device_name = excluded.device_name,
         platform = excluded.platform,
         device_info = excluded.device_info,
         ip_address = excluded.ip_address,
         user_agent = excluded.user_agent,
         created_at = excluded.created_at,
         last_activity = excluded.last_activity,
         expires_at = excluded.expires_at,
         revoked_at = null
  returning persisted.* into v_session;

  return query select true, pg_catalog.to_jsonb(v_user),
    pg_catalog.to_jsonb(v_session), v_revoked_sessions;
end;
$function$;

create or replace function public.complete_initial_password_setup_v1(
  p_user_id uuid,
  p_session_id uuid,
  p_session_token_hash text,
  p_password_hash text
)
returns table(
  password_setup_applied boolean,
  user_data jsonb,
  revoked_sessions bigint
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_session public.sessions%rowtype;
  v_now timestamptz;
  v_revoked_sessions bigint := 0;
begin
  if p_user_id is null
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_password_hash is null
     or pg_catalog.length(p_password_hash) < 20
     or pg_catalog.length(p_password_hash) > 1024 then
    raise exception 'Invalid initial-password input.' using errcode = '22023';
  end if;

  select account.* into v_user
    from public.users as account
   where account.id = p_user_id
   for update;

  v_now := pg_catalog.clock_timestamp();
  if not found
     or v_user.deleted_at is not null
     or v_user.is_verified is not true
     or v_user.is_guest is true
     or v_user.password_setup_required is not true then
    return query select false, null::jsonb, 0::bigint;
    return;
  end if;

  select session.* into v_session
    from public.sessions as session
   where session.id = p_session_id
     and session.user_id = p_user_id
     and session.token_hash = p_session_token_hash
     and session.revoked_at is null
     and session.expires_at > v_now
     and session.device_info ->> 'passwordSetupProof'
       = 'inbox-verification-v1'
   for update;

  if not found then
    return query select false, null::jsonb, 0::bigint;
    return;
  end if;

  update public.users as account
     set password_hash = p_password_hash,
         password_setup_required = false,
         password_inbox_bound_at = v_now,
         password_reset_token_hash = null,
         password_reset_expires = null,
         updated_at = v_now
   where account.id = p_user_id
     and account.password_setup_required is true
   returning account.* into v_user;

  if not found then
    raise exception 'Initial-password state changed while locked.'
      using errcode = '40001';
  end if;

  update public.sessions as session
     set device_info = coalesce(session.device_info, '{}'::jsonb)
       - 'passwordSetupProof'
   where session.id = p_session_id
     and session.user_id = p_user_id
     and session.token_hash = p_session_token_hash;

  update public.sessions as session
     set revoked_at = v_now
   where session.user_id = p_user_id
     and session.id <> p_session_id
     and session.revoked_at is null;
  get diagnostics v_revoked_sessions = row_count;

  return query select true, pg_catalog.to_jsonb(v_user), v_revoked_sessions;
end;
$function$;

revoke all on function public.consume_password_reset_v1(text, text)
  from public, anon, authenticated, service_role;
grant execute on function public.consume_password_reset_v1(text, text)
  to service_role;

revoke all on function public.finalize_password_login_v1(
  uuid, text, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.finalize_password_login_v1(
  uuid, text, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) to service_role;

revoke all on function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) to service_role;

revoke all on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) to service_role;

revoke all on function public.complete_initial_password_setup_v1(
  uuid, uuid, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.complete_initial_password_setup_v1(
  uuid, uuid, text, text
) to service_role;

comment on function public.complete_initial_password_setup_v1(
  uuid, uuid, text, text
) is
  'Establishes the first usable password only through the exact active inbox-verification session and revokes every other session.';

comment on function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) is
  'Atomically verifies a registered account, disables its pending password, revokes old sessions, and issues one password-setup session.';

comment on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) is
  'Atomically converts a verified guest, disables its pending password, revokes every old session, and issues one password-setup session.';
