-- Minimal production-shaped baseline for the document-delivery migration.
-- This gate intentionally uses vanilla PostgreSQL 17 and no hosted service.

begin;

create extension if not exists pgcrypto;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin;
  end if;
end;
$$;

alter role service_role bypassrls;
grant usage on schema public to service_role;

create table public.users (
  id uuid primary key,
  deleted_at timestamptz
);

create table public.chat_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  message_id uuid not null,
  status text not null default 'processing',
  response_data jsonb,
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, message_id)
);

create table public.user_files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid,
  message_id uuid,
  storage_path text not null unique,
  file_name text not null,
  mime_type text not null,
  size_bytes bigint not null default 0,
  kind text not null default 'upload',
  status text not null default 'pending',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table public.usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  event_type text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.credit_accounts (
  user_id uuid primary key references public.users(id) on delete cascade,
  balance bigint not null default 0 check (balance >= 0),
  lifetime_granted bigint not null default 0 check (lifetime_granted >= 0),
  lifetime_spent bigint not null default 0 check (lifetime_spent >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.credit_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  delta integer not null check (delta <> 0),
  balance_after bigint not null check (balance_after >= 0),
  reason text not null,
  provider text not null default 'internal',
  external_id text,
  product_id text,
  related_ledger_id uuid references public.credit_ledger(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index credit_ledger_provider_external_unique
  on public.credit_ledger(user_id, provider, external_id)
  where external_id is not null;

create unique index credit_ledger_refund_once_unique
  on public.credit_ledger(user_id, related_ledger_id)
  where related_ledger_id is not null and reason = 'refund';

create table public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 100),
  description text not null default '',
  instructions text not null default '',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);

create table public.project_chats (
  project_id uuid not null references public.projects(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  created_at timestamptz not null default now(),
  primary key (project_id, chat_id)
);

create table public.manuscripts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  title text not null,
  subtitle text not null default '',
  author_name text not null default '',
  trim_code text not null default '6x9',
  trim_width numeric(6,3) not null default 6.0,
  trim_height numeric(6,3) not null default 9.0,
  bleed boolean not null default false,
  status text not null default 'draft',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);

create table public.manuscript_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  manuscript_id uuid not null references public.manuscripts(id) on delete cascade,
  chat_id uuid,
  status text not null default 'queued',
  stage text not null default 'blueprint',
  mode text not null default 'autopilot',
  brief text not null,
  target_words integer not null default 80000,
  chapter_count integer not null default 28,
  preferred_export_format text not null default 'docx',
  completed_sections integer not null default 0,
  total_sections integer not null default 0,
  attempt_count integer not null default 0,
  consecutive_failures integer not null default 0,
  not_before timestamptz not null default now(),
  lease_token uuid,
  lease_expires_at timestamptz,
  current_receipt jsonb not null default '{}'::jsonb,
  blueprint_receipt jsonb not null default '{}'::jsonb,
  provider_usage jsonb not null default '{}'::jsonb,
  last_error_code text,
  last_error_message text,
  metadata jsonb not null default '{}'::jsonb,
  approved_credit_limit integer not null default 0 check (approved_credit_limit >= 0),
  credits_spent integer not null default 0 check (credits_spent >= 0 and credits_spent <= approved_credit_limit),
  planned_steps integer not null default 0 check (planned_steps >= 0),
  planned_chargeable_steps integer not null default 0 check (planned_chargeable_steps >= 0 and planned_chargeable_steps <= planned_steps),
  credit_per_step integer not null default 8 check (credit_per_step > 0),
  credit_action_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz
);

create or replace function public.claim_chat_job(
  p_user_id uuid,
  p_chat_id uuid,
  p_message_id uuid
)
returns table(job_state text, response_data jsonb)
language plpgsql
security definer
set search_path = public
as $$
begin
  return query select 'legacy'::text, null::jsonb;
end;
$$;

revoke all on function public.claim_chat_job(uuid, uuid, uuid) from public;
grant execute on function public.claim_chat_job(uuid, uuid, uuid) to service_role;
grant select, insert, update, delete on all tables in schema public to service_role;

insert into public.users(id)
values
  ('10000000-0000-4000-8000-000000000001'),
  ('10000000-0000-4000-8000-000000000002');

insert into public.credit_accounts(user_id, balance, lifetime_granted)
values
  ('10000000-0000-4000-8000-000000000001', 100, 100),
  ('10000000-0000-4000-8000-000000000002', 100, 100);

commit;
