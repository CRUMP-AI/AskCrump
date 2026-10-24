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
  id uuid primary key
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

create table public.push_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  installation_id text not null,
  platform text not null check (platform in ('ios', 'android')),
  token text not null,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_used_at timestamptz,
  unique(user_id, installation_id),
  unique(token)
);

alter table public.push_tokens enable row level security;

revoke all on public.sessions, public.push_tokens from public, anon, authenticated;
grant select, insert, update, delete on public.sessions, public.push_tokens to service_role;

insert into public.users(id) values
  ('70000000-0000-4000-8000-000000000001'),
  ('70000000-0000-4000-8000-000000000002');

insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values (
  '71000000-0000-4000-8000-000000000099',
  '70000000-0000-4000-8000-000000000001',
  repeat('9', 64),
  'installation-legacy-current',
  clock_timestamp() - interval '1 minute',
  clock_timestamp(),
  clock_timestamp() + interval '30 days'
);

insert into public.push_tokens (
  id, user_id, installation_id, platform, token, enabled
) values
  (
    '73000000-0000-4000-8000-000000000099',
    '70000000-0000-4000-8000-000000000001',
    'installation-legacy-current',
    'ios',
    repeat('L', 24),
    true
  ),
  (
    '73000000-0000-4000-8000-000000000098',
    '70000000-0000-4000-8000-000000000002',
    'installation-legacy-unbound',
    'ios',
    repeat('M', 24),
    true
  );
