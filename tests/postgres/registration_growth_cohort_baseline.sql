-- Minimal pre-migration schema for the isolated registration-cohort gate.
-- It intentionally uses synthetic rows and no hosted Supabase dependency.

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
  email text,
  is_verified boolean not null default false,
  is_guest boolean not null default false,
  subscription_tier text not null default 'free',
  subscription_status text not null default 'inactive',
  subscription_provider text,
  created_at timestamptz not null,
  updated_at timestamptz not null default now(),
  registration_environment text,
  deleted_at timestamptz,
  internal_tier text,
  constraint users_registration_environment_check check (
    registration_environment is null
    or registration_environment in ('production', 'preview', 'development')
  )
);

create table public.product_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  environment text not null,
  event_name text not null,
  event_key text not null,
  source text,
  plan text,
  artifact_type text,
  placement text,
  campaign text,
  creative text,
  intent text,
  created_at timestamptz not null default now()
);

create table public.chat_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  status text not null,
  updated_at timestamptz not null
);

create table public.projects (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  archived_at timestamptz,
  created_at timestamptz not null
);

create table public.project_chats (
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  created_at timestamptz not null
);

create table public.user_files (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  kind text not null,
  status text not null,
  size_bytes bigint not null default 0,
  deleted_at timestamptz,
  created_at timestamptz not null
);

create table public.project_files (
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  file_id uuid not null references public.user_files(id) on delete cascade,
  created_at timestamptz not null
);

create table public.credit_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  reason text not null,
  provider text,
  delta bigint not null,
  created_at timestamptz not null
);

grant select on all tables in schema public to service_role;

-- Historical positive evidence for conservative backfill. One event predates
-- the user and is invalid; another is later and preview-scoped. The earliest
-- valid event wins deterministically.
insert into public.users (
  id, email, is_guest, created_at, registration_environment
) values
  (
    '10000000-0000-4000-8000-000000000001',
    'submitted@example.test',
    true,
    '2026-09-20 00:00:00+00',
    'production'
  ),
  (
    '10000000-0000-4000-8000-000000000002',
    'guest-preview@guest.askcrump.local',
    true,
    '2026-10-02 00:00:00+00',
    'production'
  );

-- Pre-migration legacy rows prove the reports keep their historical
-- created_at fallback. They must exist before the live INSERT guard is added.
insert into public.users (
  id, email, is_guest, is_verified, created_at, registration_environment
) values
  (
    '10000000-0000-4000-8000-000000000004',
    'legacy@example.test',
    false,
    true,
    '2026-10-04 00:00:00+00',
    'production'
  ),
  (
    '10000000-0000-4000-8000-000000000009',
    'legacy-null-environment@example.test',
    false,
    true,
    '2026-10-05 00:00:00+00',
    null
  );

insert into public.product_events (
  id, user_id, environment, event_name, event_key, source, created_at
) values
  (
    '20000000-0000-4000-8000-000000000000',
    '10000000-0000-4000-8000-000000000001',
    'preview',
    'AccountCreated',
    'account-created',
    'invalid-before-user-existed',
    '2026-09-19 00:00:00+00'
  ),
  (
    '20000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    'production',
    'AccountCreated',
    'account-created',
    'organic',
    '2026-10-06 00:00:00+00'
  ),
  (
    '20000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000001',
    'preview',
    'AccountCreated',
    'account-created',
    'later-duplicate',
    '2026-10-07 00:00:00+00'
  );
