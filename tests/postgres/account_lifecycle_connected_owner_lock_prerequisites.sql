-- Disposable-only compatibility surface for the account lifecycle lock gate.
-- The registration-growth fixture intentionally omits these production tables,
-- but delete_user_account must be compiled and exercised against all of them.

\set ON_ERROR_STOP on

create extension if not exists dblink;

create table if not exists public.usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  event_type text not null,
  idempotency_key text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists usage_events_daily_idx
  on public.usage_events(user_id, event_type, created_at desc);
create unique index if not exists usage_events_idempotency_unique
  on public.usage_events(user_id, event_type, idempotency_key)
  where idempotency_key is not null;

create table if not exists public.user_chats (
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

create table if not exists public.user_settings (
  user_id uuid primary key references public.users(id) on delete cascade,
  assistant_name text default 'Crump',
  work_mode boolean not null default false,
  work_start integer not null default 9,
  work_end integer not null default 17,
  preferences jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.crump_chats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  created_at timestamptz not null default now()
);

create table if not exists public.devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  created_at timestamptz not null default now()
);

grant select, insert, update, delete
  on public.usage_events, public.user_chats, public.user_settings,
     public.crump_chats, public.devices
  to service_role;
