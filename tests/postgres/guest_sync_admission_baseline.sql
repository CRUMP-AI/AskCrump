-- Minimal pre-migration schema for the isolated guest-sync PostgreSQL gate.
-- It intentionally has no dependency on a hosted Supabase project.

\set ON_ERROR_STOP on

create extension if not exists pgcrypto;

do $$
begin
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end;
$$;

grant usage on schema public to service_role;

create table public.users (
  id uuid primary key,
  is_verified boolean not null default false,
  verification_token_hash text,
  verification_token_expires timestamptz,
  updated_at timestamptz not null default now()
);

create table public.sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  token_hash text not null,
  device_id text,
  device_name text,
  platform text,
  device_info jsonb not null default '{}'::jsonb,
  ip_address text,
  user_agent text,
  created_at timestamptz not null default now(),
  last_activity timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);

create unique index sessions_token_hash_unique on public.sessions(token_hash);
create unique index sessions_device_id_unique on public.sessions(device_id);
create index sessions_user_active_idx
  on public.sessions(user_id, last_activity desc)
  where revoked_at is null;
create index sessions_expiry_idx on public.sessions(expires_at);

create table public.user_settings (
  user_id uuid primary key references public.users(id) on delete cascade,
  assistant_name text default 'Crump',
  work_mode boolean not null default false,
  work_start integer not null default 9,
  work_end integer not null default 17,
  preferences jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.user_chats (
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  title text not null default 'New conversation',
  messages jsonb not null default '[]'::jsonb,
  revision bigint not null default 1,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, chat_id)
);

-- Faithful allowance ledger prerequisites. The Guest/Free migration relies on
-- the later idempotency column and partial uniqueness contract, so the
-- disposable gate must model both instead of silently testing a weaker table.
create table public.usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  event_type text not null,
  idempotency_key text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index usage_events_daily_idx
  on public.usage_events(user_id, event_type, created_at desc);
create unique index usage_events_idempotency_unique
  on public.usage_events(user_id, event_type, idempotency_key)
  where idempotency_key is not null;

-- A small stand-in with the production compare-and-apply contract. The target
-- migration composes this existing RPC rather than duplicating sync semantics.
create or replace function public.apply_chat_sync(
  p_user_id uuid,
  p_chat_id uuid,
  p_title text,
  p_messages jsonb,
  p_created_at timestamptz,
  p_updated_at timestamptz,
  p_deleted_at timestamptz,
  p_revision bigint
)
returns table(accepted boolean, resulting_revision bigint)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_revision bigint;
begin
  insert into public.user_chats as current_chat(
    user_id, chat_id, title, messages, created_at, updated_at, deleted_at, revision
  )
  values (
    p_user_id,
    p_chat_id,
    coalesce(nullif(p_title, ''), 'New conversation'),
    coalesce(p_messages, '[]'::jsonb),
    coalesce(p_created_at, p_updated_at, now()),
    coalesce(p_updated_at, now()),
    p_deleted_at,
    greatest(1, coalesce(p_revision, 1))
  )
  on conflict (user_id, chat_id) do update set
    title = excluded.title,
    messages = case
      when excluded.deleted_at is not null then '[]'::jsonb
      else excluded.messages
    end,
    deleted_at = excluded.deleted_at,
    updated_at = greatest(current_chat.updated_at, excluded.updated_at),
    revision = greatest(excluded.revision, current_chat.revision + 1)
  where excluded.updated_at > current_chat.updated_at
     or (
       excluded.updated_at = current_chat.updated_at
       and excluded.revision > current_chat.revision
     )
  returning current_chat.revision into v_revision;

  if found then
    return query select true, v_revision;
  end if;

  select candidate.revision
    into v_revision
    from public.user_chats as candidate
   where candidate.user_id = p_user_id
     and candidate.chat_id = p_chat_id;
  return query select false, coalesce(v_revision, 1);
end;
$$;

-- Simulate a short-lived install of the retired two-step function so the
-- target migration must explicitly remove its service-role capability.
create or replace function public.admit_guest_sync_chats(
  p_user_id uuid,
  p_chat_ids uuid[],
  p_sizes integer[],
  p_max_chats integer,
  p_max_bytes bigint
)
returns uuid[]
language sql
as $$
  select coalesce(p_chat_ids, '{}'::uuid[])
$$;

grant select, insert, update, delete
  on public.users, public.sessions, public.user_settings,
     public.user_chats, public.usage_events
  to service_role;
-- Seed deliberately unsafe browser-table grants so the target allowance
-- migration must prove that it revokes them instead of merely inheriting a
-- clean disposable database.
grant all on table public.usage_events to anon, authenticated;
revoke all on function public.apply_chat_sync(
  uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint
) from public, anon, authenticated;
grant execute on function public.apply_chat_sync(
  uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint
) to service_role;
grant execute on function public.admit_guest_sync_chats(
  uuid, uuid[], integer[], integer, bigint
) to service_role;
