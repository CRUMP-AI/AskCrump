-- Ask Crump guest mode.
--
-- A guest is a real users row that can later be upgraded in place. Message
-- allowance is deliberately NOT stored on users: usage_events is the single
-- ledger for both guests and registered Free accounts, so signup preserves the
-- conversation and remaining rolling-24-hour allowance without a copy/reset.
--
-- The migration runner owns the transaction. Do not embed BEGIN/COMMIT here;
-- an embedded commit can leave schema changes without migration-history proof.

set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.users
  add column if not exists is_guest boolean not null default false;

comment on column public.users.is_guest is
  'True only for an anonymous try-first account that has not completed registration.';

-- Install the fail-closed singleton before any guest write RPC is created.
-- The later guest-control migration adds the operator APIs and triggers, but
-- every reservation/sync/reply function can already share this lock so there
-- is never a rollout window with an unguarded database write capability.
create table if not exists public.guest_mode_control (
  singleton boolean primary key default true,
  enabled boolean not null default false,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint guest_mode_control_singleton check (singleton)
);

insert into public.guest_mode_control (singleton, enabled)
values (true, false)
on conflict (singleton) do nothing;

alter table public.guest_mode_control enable row level security;

revoke all on table public.guest_mode_control
  from public, anon, authenticated, service_role;

create or replace function public.lock_guest_mode_control_v1()
returns boolean
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_enabled boolean := false;
begin
  -- FOR SHARE is the write-side barrier. The lock is held until the caller's
  -- transaction ends, so disable-and-drain cannot commit in the middle of a
  -- guest reservation, sync, or reply persistence operation.
  select control.enabled
    into v_enabled
    from public.guest_mode_control as control
   where control.singleton is true
   for share;

  -- A missing singleton is an explicit fail-closed state.
  return coalesce(v_enabled, false);
end;
$$;

comment on function public.lock_guest_mode_control_v1() is
  'Private transaction-scoped guest-write barrier; a missing singleton returns false.';

revoke all on function public.lock_guest_mode_control_v1()
  from public, anon, authenticated, service_role;
