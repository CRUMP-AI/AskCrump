\set ON_ERROR_STOP on

-- The isolated registration baseline predates the production access boundary.
-- Reproduce the live server-only posture before applying guest-start facts.
alter table public.users enable row level security;
alter table public.sessions enable row level security;

revoke all on table public.users from public, anon, authenticated;
revoke all on table public.sessions from public, anon, authenticated;

-- Reproduce the exact enabled companion session guard installed by
-- 20261021040000_guest_mode_control.sql. The guest-start owner lock depends on
-- PostgreSQL's lexical ordering of these two BEFORE INSERT triggers.
create table public.guest_mode_control (
  singleton boolean primary key default true,
  enabled boolean not null default false,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint guest_mode_control_singleton check (singleton)
);

insert into public.guest_mode_control (singleton, enabled)
values (true, true);

alter table public.guest_mode_control enable row level security;
revoke all on table public.guest_mode_control
  from public, anon, authenticated, service_role;

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

create trigger enforce_guest_mode_on_session_v1
before insert or update on public.sessions
for each row execute function public.enforce_guest_mode_on_session_v1();

revoke all on function public.enforce_guest_mode_on_session_v1()
  from public, anon, authenticated, service_role;
