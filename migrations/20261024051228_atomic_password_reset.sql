-- Consume password-reset credentials, update the account, and revoke active
-- sessions in one database transaction. The production migration runner owns
-- the outer transaction boundary.

do $preflight$
declare
  reset_signature constant text :=
    'public.consume_password_reset_v1(text,text)';
  login_signature constant text :=
    'public.finalize_password_login_v1(uuid,text,text,uuid,text,timestamp with time zone,text,text,text,jsonb,text,text)';
  verification_signature constant text :=
    'public.verify_registered_and_create_session_v1(uuid,text,uuid,text,timestamp with time zone,text,text,text,jsonb,text,text)';
  existing_function oid := pg_catalog.to_regprocedure(reset_signature);
  existing_login_function oid := pg_catalog.to_regprocedure(login_signature);
  existing_verification_function oid :=
    pg_catalog.to_regprocedure(verification_signature);
  reset_index oid := pg_catalog.to_regclass(
    'public.users_password_reset_token_hash_unique'
  );
  device_index oid := pg_catalog.to_regclass('public.sessions_device_id_unique');
  token_index oid := pg_catalog.to_regclass('public.sessions_token_hash_unique');
begin
  if pg_catalog.to_regclass('public.users') is null
     or pg_catalog.to_regclass('public.sessions') is null then
    raise exception
      'Password-reset prerequisites are missing.'
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
             or (
               column_name = 'email_verified_at'
               and data_type = 'timestamp with time zone'
             )
             or (
               column_name = 'updated_at'
               and data_type = 'timestamp with time zone'
             )
             or (
               column_name = 'last_login'
               and data_type = 'timestamp with time zone'
             )
             or (
               column_name = 'deleted_at'
               and data_type = 'timestamp with time zone'
             )
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
  ) <> 25 then
    raise exception
      'Unexpected password-reset table definitions; refusing migration.'
      using errcode = '55000';
  end if;

  if pg_catalog.to_regprocedure(
       'public.enforce_email_verification_timestamp_v1()'
     ) is null
     or not exists (
       select 1
         from pg_catalog.pg_trigger as trigger_row
        where trigger_row.tgrelid = 'public.users'::regclass
          and trigger_row.tgname = 'users_email_verification_timestamp_v1'
          and trigger_row.tgenabled <> 'D'
     ) then
    raise exception
      'Immutable email-verification measurement is not installed.'
      using errcode = '55000';
  end if;

  if exists (
    select account.password_reset_token_hash
      from public.users as account
     where account.password_reset_token_hash is not null
     group by account.password_reset_token_hash
    having count(*) > 1
  ) then
    raise exception
      'Found duplicate password-reset token hashes; refusing migration.'
      using errcode = '55000';
  end if;

  if reset_index is not null
     and not exists (
       select 1
         from pg_catalog.pg_index as index_row
        where index_row.indexrelid = reset_index
          and index_row.indrelid = 'public.users'::regclass
          and index_row.indisunique
          and index_row.indisvalid
          and index_row.indisready
          and index_row.indnkeyatts = 1
          and pg_catalog.pg_get_indexdef(reset_index, 1, true) =
            'password_reset_token_hash'
          and pg_catalog.pg_get_expr(
                index_row.indpred,
                index_row.indrelid
              ) = '(password_reset_token_hash IS NOT NULL)'
     ) then
    raise exception
      'Unexpected users_password_reset_token_hash_unique definition.'
      using errcode = '55000';
  end if;

  if device_index is null
     or not exists (
       select 1
         from pg_catalog.pg_index as index_row
        where index_row.indexrelid = device_index
          and index_row.indrelid = 'public.sessions'::regclass
          and index_row.indisunique
          and index_row.indisvalid
          and index_row.indisready
          and index_row.indpred is null
          and index_row.indnkeyatts = 1
          and pg_catalog.pg_get_indexdef(device_index, 1, true) = 'device_id'
     ) then
    raise exception
      'Expected sessions_device_id_unique is missing or changed.'
      using errcode = '55000';
  end if;

  if token_index is null
     or not exists (
       select 1
         from pg_catalog.pg_index as index_row
        where index_row.indexrelid = token_index
          and index_row.indrelid = 'public.sessions'::regclass
          and index_row.indisunique
          and index_row.indisvalid
          and index_row.indisready
          and index_row.indpred is null
          and index_row.indnkeyatts = 1
          and pg_catalog.pg_get_indexdef(token_index, 1, true) = 'token_hash'
     ) then
    raise exception
      'Expected sessions_token_hash_unique is missing or changed.'
      using errcode = '55000';
  end if;

  if existing_function is not null
     and (
       (
         select pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
         from pg_catalog.pg_proc as function_row
         where function_row.oid = existing_function
       )
       or not pg_catalog.has_function_privilege(
         'service_role', existing_function, 'EXECUTE'
       )
       or pg_catalog.has_function_privilege(
         'anon', existing_function, 'EXECUTE'
       )
       or pg_catalog.has_function_privilege(
         'authenticated', existing_function, 'EXECUTE'
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
         where function_row.oid = existing_function
           and acl_row.privilege_type = 'EXECUTE'
       )
     ) then
    raise exception
      'Unexpected consume_password_reset_v1 owner or ACL; refusing replacement.'
      using errcode = '55000';
  end if;

  if existing_login_function is not null
     and (
       (
         select pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
         from pg_catalog.pg_proc as function_row
         where function_row.oid = existing_login_function
       )
       or not pg_catalog.has_function_privilege(
         'service_role', existing_login_function, 'EXECUTE'
       )
       or pg_catalog.has_function_privilege(
         'anon', existing_login_function, 'EXECUTE'
       )
       or pg_catalog.has_function_privilege(
         'authenticated', existing_login_function, 'EXECUTE'
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
         where function_row.oid = existing_login_function
           and acl_row.privilege_type = 'EXECUTE'
       )
     ) then
    raise exception
      'Unexpected finalize_password_login_v1 owner or ACL; refusing replacement.'
      using errcode = '55000';
  end if;

  if existing_verification_function is not null
     and (
       (
         select pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
         from pg_catalog.pg_proc as function_row
         where function_row.oid = existing_verification_function
       )
       or not pg_catalog.has_function_privilege(
         'service_role', existing_verification_function, 'EXECUTE'
       )
       or pg_catalog.has_function_privilege(
         'anon', existing_verification_function, 'EXECUTE'
       )
       or pg_catalog.has_function_privilege(
         'authenticated', existing_verification_function, 'EXECUTE'
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
         where function_row.oid = existing_verification_function
           and acl_row.privilege_type = 'EXECUTE'
       )
     ) then
    raise exception
      'Unexpected verify_registered_and_create_session_v1 owner or ACL; refusing replacement.'
      using errcode = '55000';
  end if;

  if not exists (
       select 1 from pg_catalog.pg_roles where rolname = 'service_role'
     )
     or not exists (
       select 1 from pg_catalog.pg_roles where rolname = 'anon'
     )
     or not exists (
       select 1 from pg_catalog.pg_roles where rolname = 'authenticated'
     ) then
    raise exception
      'Password-reset database roles are missing.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'consume_password_reset_v1'
       and function_row.oid <> coalesce(
         pg_catalog.to_regprocedure(reset_signature),
         0::oid
       )
  ) then
    raise exception
      'Unexpected consume_password_reset_v1 overload; refusing migration.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'finalize_password_login_v1'
       and function_row.oid <> coalesce(
         pg_catalog.to_regprocedure(login_signature),
         0::oid
       )
  ) then
    raise exception
      'Unexpected finalize_password_login_v1 overload; refusing migration.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'verify_registered_and_create_session_v1'
       and function_row.oid <> coalesce(
         pg_catalog.to_regprocedure(verification_signature),
         0::oid
       )
  ) then
    raise exception
      'Unexpected verify_registered_and_create_session_v1 overload; refusing migration.'
      using errcode = '55000';
  end if;
end;
$preflight$;

create unique index if not exists users_password_reset_token_hash_unique
  on public.users(password_reset_token_hash)
  where password_reset_token_hash is not null;

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
    raise exception 'Invalid password-reset input.'
      using errcode = '22023';
  end if;

  select account.id, account.password_reset_expires
    into v_user_id, v_reset_expires
    from public.users as account
   where account.password_reset_token_hash = p_token_hash
   order by account.id
   limit 1
   for update;

  -- The partial unique index makes the locked row the sole account for this
  -- bearer token. Sample the security clock only after acquiring its row lock;
  -- an unrelated writer cannot extend a token by making this reset wait.
  v_now := pg_catalog.clock_timestamp();

  if not found or v_reset_expires is null or v_reset_expires <= v_now then
    return query select false;
    return;
  end if;

  update public.users as account
     set password_hash = p_password_hash,
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

  -- A trigger failure or any other error here rolls the user update and token
  -- consumption back with this statement, leaving a safe retry path.
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
    raise exception 'Invalid password-login input.'
      using errcode = '22023';
  end if;

  -- This user tuple is the serialization point shared with password reset.
  -- Compare the exact hash Python verified while retaining that lock through
  -- any hash upgrade and the complete session write.
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
     and account.password_hash is not distinct from p_expected_password_hash
   returning account.* into v_user;

  if not found then
    raise exception 'Password-login state changed while locked.'
      using errcode = '40001';
  end if;

  insert into public.sessions as persisted (
    id,
    user_id,
    token_hash,
    device_id,
    device_name,
    platform,
    device_info,
    ip_address,
    user_agent,
    created_at,
    last_activity,
    expires_at,
    revoked_at
  ) values (
    p_session_id,
    p_user_id,
    p_session_token_hash,
    p_device_id,
    p_device_name,
    p_platform,
    coalesce(p_device_info, '{}'::jsonb),
    p_ip_address,
    p_user_agent,
    v_now,
    v_now,
    p_session_expires_at,
    null
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

  -- Preserve the existing bounded active-session behavior within this same
  -- transaction. The freshly written session sorts first on this DB timestamp.
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

  return query
  select
    true,
    pg_catalog.to_jsonb(v_user),
    pg_catalog.to_jsonb(v_session),
    v_pruned_sessions;
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
  v_pruned_sessions bigint := 0;
begin
  if p_user_id is null
     or p_verification_token_hash is null
     or p_verification_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_expires_at is null then
    raise exception 'Invalid registered-verification input.'
      using errcode = '22023';
  end if;

  -- This is the same serialization tuple used by password reset and password
  -- login. Keep it locked through both inbox-proof consumption and session mint.
  select account.*
    into v_user
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

  insert into public.sessions as persisted (
    id,
    user_id,
    token_hash,
    device_id,
    device_name,
    platform,
    device_info,
    ip_address,
    user_agent,
    created_at,
    last_activity,
    expires_at,
    revoked_at
  ) values (
    p_session_id,
    p_user_id,
    p_session_token_hash,
    p_device_id,
    p_device_name,
    p_platform,
    coalesce(p_device_info, '{}'::jsonb),
    p_ip_address,
    p_user_agent,
    v_now,
    v_now,
    p_session_expires_at,
    null
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

  return query
  select
    true,
    pg_catalog.to_jsonb(v_user),
    pg_catalog.to_jsonb(v_session),
    v_pruned_sessions;
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

comment on function public.consume_password_reset_v1(text, text) is
  'Atomically consumes one password-reset token, updates its account, and revokes every active session.';

comment on function public.finalize_password_login_v1(
  uuid, text, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) is
  'Atomically compares the password hash verified by the backend, applies an optional hash upgrade, and issues one bounded device session.';

comment on function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) is
  'Atomically verifies one registered account from its current email token and issues one bounded device session.';
