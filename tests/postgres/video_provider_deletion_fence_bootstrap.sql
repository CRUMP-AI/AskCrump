\set ON_ERROR_STOP on

-- This schema exists only inside the disposable CI database. It supplies the
-- minimum Supabase-shaped roles and application tables required to compile and
-- exercise staging/video_provider_deletion_fence.sql against real PostgreSQL.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin nobypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin nobypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end;
$$;

alter role anon nologin nobypassrls;
alter role authenticated nologin nobypassrls;
alter role service_role nologin bypassrls;

grant usage on schema public to anon, authenticated, service_role;

create table public.users (
  id uuid primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  account_deletion_token uuid,
  ai_data_sharing_consent_revoked_at timestamptz,
  ai_data_sharing_consent_updated_at timestamptz
);

create table public.account_deletion_jobs (
  user_id uuid primary key,
  operation_token uuid not null unique,
  state text not null check (
    state in ('fencing', 'fenced', 'retry_pending', 'late_upload_sweep', 'complete', 'abandoned')
  ),
  fenced_at timestamptz not null,
  account_deleted_at timestamptz,
  finalize_after timestamptz not null,
  next_attempt_at timestamptz,
  attempts integer not null default 0,
  last_error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  native_billing_identity_possible boolean not null default false
);

create table public.media_jobs (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  kind text not null,
  status text not null,
  provider text not null,
  operation_type text,
  provider_job_id text,
  metadata jsonb,
  updated_at timestamptz not null default now()
);

alter table public.users enable row level security;
alter table public.account_deletion_jobs enable row level security;
alter table public.media_jobs enable row level security;

revoke all on table public.users from public, anon, authenticated, service_role;
revoke all on table public.account_deletion_jobs from public, anon, authenticated, service_role;
revoke all on table public.media_jobs from public, anon, authenticated, service_role;

-- The production Supabase service role bypasses RLS. These grants model only
-- the base-table capabilities the candidate RPCs and deletion caller need.
grant select, update, delete on table public.users to service_role;
grant select, insert, update, delete on table public.account_deletion_jobs to service_role;
grant select, insert, update, delete on table public.media_jobs to service_role;

-- Seed the four legacy statuses before the candidate is applied so its
-- migration-time backfill is exercised, not merely its steady-state RPCs.
insert into public.users(id)
values ('09000000-0000-0000-0000-000000000001');

insert into public.media_jobs(
  id, user_id, kind, status, provider, operation_type, provider_job_id
) values
  (
    '09100000-0000-0000-0000-000000000001',
    '09000000-0000-0000-0000-000000000001',
    'video', 'queued', 'runway', 'extend', 'legacy-provider-job'
  ),
  (
    '09100000-0000-0000-0000-000000000002',
    '09000000-0000-0000-0000-000000000001',
    'video', 'processing', 'gemini', null,
    'pending:09100000-0000-0000-0000-000000000002'
  ),
  (
    '09100000-0000-0000-0000-000000000003',
    '09000000-0000-0000-0000-000000000001',
    'video', 'ready', 'runway', 'generate', 'legacy-ready-job'
  ),
  (
    '09100000-0000-0000-0000-000000000004',
    '09000000-0000-0000-0000-000000000001',
    'video', 'failed', 'gemini', 'generate',
    'pending:09100000-0000-0000-0000-000000000004'
  );
