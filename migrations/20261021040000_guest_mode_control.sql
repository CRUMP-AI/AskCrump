-- Database-authoritative guest-mode release and rollback control.
--
-- Guest mode starts disabled. The application may expose guest entry only
-- after the service-role setter enables it. Disabling the control and
-- revoking every active guest session happen in one database transaction.
-- Row locks on the singleton control serialize guest-user/session creation
-- against that disable-and-drain operation.
--
-- The migration runner owns the transaction. Do not embed BEGIN/COMMIT here.

set local lock_timeout = '5s';
set local statement_timeout = '30s';

create table if not exists public.guest_mode_control (
  singleton boolean primary key default true,
  enabled boolean not null default false,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint guest_mode_control_singleton check (singleton)
);

comment on table public.guest_mode_control is
  'Singleton, database-authoritative guest-mode release and rollback control.';
comment on column public.guest_mode_control.enabled is
  'False blocks guest identities and active guest sessions; true permits them.';

insert into public.guest_mode_control (singleton, enabled)
values (true, false)
on conflict (singleton) do nothing;

alter table public.guest_mode_control enable row level security;

revoke all on table public.guest_mode_control
  from public, anon, authenticated, service_role;

create or replace function public.get_guest_mode_control_v1()
returns table(enabled boolean, updated_at timestamptz)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  return query
  select control.enabled, control.updated_at
    from public.guest_mode_control as control
   where control.singleton is true;

  if not found then
    -- Missing control is an explicit fail-closed state, not an implicit on.
    return query select false, null::timestamptz;
  end if;
end;
$$;

comment on function public.get_guest_mode_control_v1() is
  'Reads guest-mode status for the service role; a missing singleton reads as disabled.';

create or replace function public.enforce_guest_mode_on_user_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_becoming_guest boolean := false;
  v_enabled boolean;
begin
  -- Registration/verification always wins over a stale caller-supplied guest
  -- flag, including legacy conversion code that updates only is_verified.
  if coalesce(new.is_verified, false) then
    new.is_guest := false;
  end if;

  if coalesce(new.is_guest, false) then
    if tg_op = 'INSERT' then
      v_becoming_guest := true;
    elsif tg_op = 'UPDATE' then
      v_becoming_guest := not coalesce(old.is_guest, false);
    end if;
  end if;

  if v_becoming_guest then
    select control.enabled
      into v_enabled
      from public.guest_mode_control as control
     where control.singleton is true
     for share;

    if not found or not coalesce(v_enabled, false) then
      raise exception using
        errcode = 'GX003',
        message = 'Guest mode is disabled.';
    end if;
  end if;

  return new;
end;
$$;

create or replace function public.enforce_guest_mode_on_session_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_enabled boolean;
  v_is_guest boolean := false;
begin
  -- A revoked row is inert. Any insert/reactivation with revoked_at NULL must
  -- cross the shared singleton lock before it can become an active session.
  if new.revoked_at is not null then
    return new;
  end if;

  -- Registered sessions are outside the guest kill-switch boundary. Resolve
  -- identity first so an ordinary registered-session touch cannot fail merely
  -- because an operator holds, disables, or repairs the guest control row.
  -- INSERT holds the account stable until the new session commits; UPDATE
  -- already owns the target session tuple and uses a non-locking identity read
  -- so the disable path never waits in a session -> account -> control cycle.
  if tg_op = 'INSERT' then
    select coalesce(account.is_guest, false)
      into v_is_guest
      from public.users as account
     where account.id = new.user_id
     for share;
  else
    select coalesce(account.is_guest, false)
      into v_is_guest
      from public.users as account
     where account.id = new.user_id;
  end if;

  if not coalesce(v_is_guest, false) then
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- PostgreSQL locks the target session tuple before a BEFORE UPDATE row
    -- trigger runs. Never wait here behind disablement, which locks control
    -- first and then needs that session tuple; reject immediately instead of
    -- creating a control -> session / session -> control deadlock.
    begin
      select control.enabled
        into v_enabled
        from public.guest_mode_control as control
       where control.singleton is true
       for share nowait;
    exception when lock_not_available then
      raise exception using
        errcode = 'GX003',
        message = 'Guest mode is disabled.';
    end;
  else
    select control.enabled
      into v_enabled
      from public.guest_mode_control as control
     where control.singleton is true
     for share;
  end if;

  if v_enabled is not true then
    raise exception using
      errcode = 'GX003',
      message = 'Guest mode is disabled.';
  end if;

  return new;
end;
$$;

create or replace function public.enforce_guest_mode_on_user_settings_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_is_guest boolean := false;
  v_guest_mode_enabled boolean := false;
begin
  -- Keep the identity stable for the complete settings write. Registered
  -- accounts return before touching the guest-only control lock.
  select coalesce(account.is_guest, false)
    into v_is_guest
    from public.users as account
   where account.id = new.user_id
   for share;

  if not found then
    -- The table's foreign key remains the authority for an unknown user.
    return new;
  end if;

  if not v_is_guest then
    return new;
  end if;

  -- This shared transaction lock serializes guest settings persistence with
  -- disable-and-drain. Missing and disabled controls both fail closed.
  v_guest_mode_enabled := public.lock_guest_mode_control_v1();
  if not coalesce(v_guest_mode_enabled, false) then
    raise exception using
      errcode = 'GX003',
      message = 'Guest mode is disabled.';
  end if;

  return new;
end;
$$;

create or replace function public.apply_guest_user_settings_v1(
  p_user_id uuid,
  p_settings jsonb,
  p_updated_at timestamptz
)
returns table(
  accepted boolean,
  outcome text,
  settings_data jsonb
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_guest_mode_enabled boolean := false;
  v_is_guest boolean := false;
  v_settings jsonb := coalesce(p_settings, '{}'::jsonb);
  v_persisted public.user_settings%rowtype;
begin
  -- This RPC is the authority carried by a request that authenticated while
  -- the account was still a guest. Acquire locks in the same global-control
  -- -> owner order as every other guest write, then keep both through the
  -- settings upsert. Verification takes the owner row exclusively, so either
  -- this write commits before conversion or it observes the registered
  -- identity and persists nothing.
  v_guest_mode_enabled := public.lock_guest_mode_control_v1();

  select coalesce(account.is_guest, false)
    into v_is_guest
    from public.users as account
   where account.id = p_user_id
   for share;

  if not found then
    return query select false, 'user_not_found'::text, null::jsonb;
    return;
  end if;

  if not v_is_guest then
    return query select false, 'not_guest'::text, null::jsonb;
    return;
  end if;

  if v_guest_mode_enabled is not true then
    return query select false, 'guest_mode_disabled'::text, null::jsonb;
    return;
  end if;

  -- The backend sanitizes this object before calling the RPC. Keep the
  -- database boundary closed as well so this privileged function cannot be
  -- repurposed into a generic column-write capability.
  if p_user_id is null
     or pg_catalog.jsonb_typeof(v_settings) is distinct from 'object'
     or v_settings = '{}'::jsonb
     or v_settings - array[
          'assistant_name', 'work_mode', 'work_start', 'work_end', 'preferences'
        ]::text[] <> '{}'::jsonb then
    return query select false, 'invalid_settings'::text, null::jsonb;
    return;
  end if;

  if v_settings ? 'assistant_name'
     and (
       pg_catalog.jsonb_typeof(v_settings -> 'assistant_name') is distinct from 'string'
       or pg_catalog.btrim(v_settings ->> 'assistant_name') = ''
       or pg_catalog.char_length(v_settings ->> 'assistant_name') > 80
     ) then
    return query select false, 'invalid_settings'::text, null::jsonb;
    return;
  end if;

  if v_settings ? 'work_mode'
     and pg_catalog.jsonb_typeof(v_settings -> 'work_mode') is distinct from 'boolean' then
    return query select false, 'invalid_settings'::text, null::jsonb;
    return;
  end if;

  if v_settings ? 'work_start' then
    if pg_catalog.jsonb_typeof(v_settings -> 'work_start') is distinct from 'number'
       or (v_settings ->> 'work_start') !~ '^(0|[1-9][0-9]*)$' then
      return query select false, 'invalid_settings'::text, null::jsonb;
      return;
    end if;
    if (v_settings ->> 'work_start')::numeric not between 0 and 23 then
      return query select false, 'invalid_settings'::text, null::jsonb;
      return;
    end if;
  end if;

  if v_settings ? 'work_end' then
    if pg_catalog.jsonb_typeof(v_settings -> 'work_end') is distinct from 'number'
       or (v_settings ->> 'work_end') !~ '^(0|[1-9][0-9]*)$' then
      return query select false, 'invalid_settings'::text, null::jsonb;
      return;
    end if;
    if (v_settings ->> 'work_end')::numeric not between 0 and 23 then
      return query select false, 'invalid_settings'::text, null::jsonb;
      return;
    end if;
  end if;

  if v_settings ? 'preferences'
     and (
       pg_catalog.jsonb_typeof(v_settings -> 'preferences') is distinct from 'object'
       or pg_catalog.octet_length((v_settings -> 'preferences')::text) > 32000
     ) then
    return query select false, 'invalid_settings'::text, null::jsonb;
    return;
  end if;

  insert into public.user_settings as current_settings (
    user_id,
    assistant_name,
    work_mode,
    work_start,
    work_end,
    preferences,
    updated_at
  ) values (
    p_user_id,
    case when v_settings ? 'assistant_name'
      then v_settings ->> 'assistant_name' else 'Crump' end,
    case when v_settings ? 'work_mode'
      then (v_settings ->> 'work_mode')::boolean else false end,
    case when v_settings ? 'work_start'
      then (v_settings ->> 'work_start')::integer else 9 end,
    case when v_settings ? 'work_end'
      then (v_settings ->> 'work_end')::integer else 17 end,
    case when v_settings ? 'preferences'
      then v_settings -> 'preferences' else '{}'::jsonb end,
    coalesce(p_updated_at, pg_catalog.clock_timestamp())
  )
  on conflict (user_id) do update
     set assistant_name = case when v_settings ? 'assistant_name'
           then excluded.assistant_name else current_settings.assistant_name end,
         work_mode = case when v_settings ? 'work_mode'
           then excluded.work_mode else current_settings.work_mode end,
         work_start = case when v_settings ? 'work_start'
           then excluded.work_start else current_settings.work_start end,
         work_end = case when v_settings ? 'work_end'
           then excluded.work_end else current_settings.work_end end,
         preferences = case when v_settings ? 'preferences'
           then excluded.preferences else current_settings.preferences end,
         updated_at = excluded.updated_at
  returning current_settings.* into v_persisted;

  return query
  select true, 'accepted'::text, pg_catalog.to_jsonb(v_persisted);
end;
$$;

comment on function public.apply_guest_user_settings_v1(
  uuid, jsonb, timestamptz
) is
  'Applies sanitized settings only while the request owner still has guest authority, serialized with verification and guest-mode disablement.';

-- Install the user invariant before normalizing any already-verified rows.
drop trigger if exists enforce_guest_mode_on_user_v1 on public.users;
create trigger enforce_guest_mode_on_user_v1
before insert or update of is_guest, is_verified on public.users
for each row execute function public.enforce_guest_mode_on_user_v1();

drop trigger if exists enforce_guest_mode_on_session_v1 on public.sessions;
create trigger enforce_guest_mode_on_session_v1
before insert or update on public.sessions
for each row execute function public.enforce_guest_mode_on_session_v1();

drop trigger if exists enforce_guest_mode_on_user_settings_v1
  on public.user_settings;
create trigger enforce_guest_mode_on_user_settings_v1
before insert or update on public.user_settings
for each row execute function public.enforce_guest_mode_on_user_settings_v1();

-- Repair the only invalid identity combination without deleting the account or
-- any customer data. This update does not transition a row into guest mode.
update public.users
   set is_guest = false
 where is_verified is true
   and is_guest is true;

create or replace function public.set_guest_mode_enabled_v1(p_enabled boolean)
returns table(
  enabled boolean,
  revoked_sessions bigint,
  updated_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_current boolean;
  v_updated_at timestamptz;
  v_revoked_sessions bigint := 0;
begin
  if p_enabled is null then
    raise exception using
      errcode = '22004',
      message = 'Guest mode state is required.';
  end if;

  -- FOR UPDATE is the exclusive side of the lock protocol used by both
  -- identity and session triggers. Once acquired, no guest can be minted or
  -- reactivated until this transaction commits.
  select control.enabled
    into v_current
    from public.guest_mode_control as control
   where control.singleton is true
   for update;

  if not found then
    raise exception using
      errcode = 'GX004',
      message = 'Guest mode control is missing.';
  end if;

  v_updated_at := pg_catalog.clock_timestamp();
  update public.guest_mode_control as control
     set enabled = p_enabled,
         updated_at = v_updated_at
   where control.singleton is true;

  if not p_enabled then
    update public.sessions as session
       set revoked_at = v_updated_at,
           device_info = coalesce(session.device_info, '{}'::jsonb)
             || pg_catalog.jsonb_build_object(
                  'guestControlRevokedAt', v_updated_at
                )
      from public.users as account
     where session.user_id = account.id
       and account.is_guest is true
       and session.revoked_at is null;
    get diagnostics v_revoked_sessions = row_count;
  end if;

  return query
  select p_enabled, v_revoked_sessions, v_updated_at;
end;
$$;

comment on function public.set_guest_mode_enabled_v1(boolean) is
  'Atomically enables guest mode or disables it and revokes every active guest session.';

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
as $$
declare
  v_user public.users%rowtype;
  v_session public.sessions%rowtype;
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_revoked_sessions bigint := 0;
begin
  if p_user_id is null
     or p_verification_token_hash is null
     or pg_catalog.btrim(p_verification_token_hash) = ''
     or p_session_id is null
     or p_session_token_hash is null
     or pg_catalog.btrim(p_session_token_hash) = ''
     or p_session_expires_at is null
     or p_session_expires_at <= v_now then
    raise exception using
      errcode = '22023',
      message = 'Guest verification session values are invalid.';
  end if;

  -- The user tuple is the serialization point. Exactly one transaction can
  -- own the guest -> verified transition, and it keeps that lock through the
  -- complete session drain and replacement-session insert.
  select account.*
    into v_user
    from public.users as account
   where account.id = p_user_id
   for update;

  if not found
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
         verification_token_expires = v_now + interval '15 minutes',
         updated_at = v_now
   where account.id = p_user_id
   returning account.* into v_user;

  update public.sessions as session
     set revoked_at = v_now,
         device_info = coalesce(session.device_info, '{}'::jsonb)
           || pg_catalog.jsonb_build_object(
                'guestVerificationRevokedAt', v_now
              )
   where session.user_id = p_user_id
     and session.revoked_at is null;
  get diagnostics v_revoked_sessions = row_count;

  -- Match ordinary session rotation: a stable installation owns one row; an
  -- email link opened without an installation header receives one new row.
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

  return query
  select
    true,
    pg_catalog.to_jsonb(v_user),
    pg_catalog.to_jsonb(v_session),
    v_revoked_sessions;
end;
$$;

comment on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) is
  'Atomically converts a verified guest, revokes every pre-verification session, and issues one replacement session.';

-- SECURITY DEFINER functions receive PUBLIC execution by default. Trigger
-- functions are not callable APIs, and the control RPCs are backend-only.
revoke all on function public.get_guest_mode_control_v1()
  from public, anon, authenticated, service_role;
revoke all on function public.set_guest_mode_enabled_v1(boolean)
  from public, anon, authenticated, service_role;
revoke all on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
)
  from public, anon, authenticated, service_role;
revoke all on function public.enforce_guest_mode_on_user_v1()
  from public, anon, authenticated, service_role;
revoke all on function public.enforce_guest_mode_on_session_v1()
  from public, anon, authenticated, service_role;
revoke all on function public.enforce_guest_mode_on_user_settings_v1()
  from public, anon, authenticated, service_role;
revoke all on function public.apply_guest_user_settings_v1(
  uuid, jsonb, timestamptz
)
  from public, anon, authenticated, service_role;
revoke all on function public.lock_guest_mode_control_v1()
  from public, anon, authenticated, service_role;

grant execute on function public.get_guest_mode_control_v1()
  to service_role;
grant execute on function public.set_guest_mode_enabled_v1(boolean)
  to service_role;
grant execute on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
)
  to service_role;
grant execute on function public.apply_guest_user_settings_v1(
  uuid, jsonb, timestamptz
)
  to service_role;

-- Every install/reinstall starts fail closed and drains any guest sessions
-- that predate this control. The caller may enable guest mode only after the
-- matching application release is ready.
select * from public.set_guest_mode_enabled_v1(false);
