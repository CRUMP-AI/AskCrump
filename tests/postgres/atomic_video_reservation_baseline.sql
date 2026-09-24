-- Minimal pre-atomic production contract for the isolated PostgreSQL gate.
-- Keep this focused on objects referenced by migrations/015, migrations/016,
-- and 20260924224459_atomic_video_reservation_billing.sql. It intentionally
-- does not emulate Supabase services or connect to any hosted project.

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

create table public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade
);

create table public.user_files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid,
  message_id uuid,
  storage_path text not null unique,
  file_name text not null,
  mime_type text not null,
  size_bytes bigint not null default 0
    check (size_bytes >= 0 and size_bytes <= 104857600),
  kind text not null default 'upload'
    check (kind in (
      'upload', 'generated_image', 'generated_document', 'generated_video',
      'manuscript', 'data_export'
    )),
  status text not null default 'pending'
    check (status in ('pending', 'ready', 'failed')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table public.media_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid references public.projects(id) on delete set null,
  kind text not null check (kind in ('video')),
  provider text not null,
  provider_job_id text not null,
  idempotency_key text,
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'ready', 'failed')),
  prompt text not null,
  model text not null,
  aspect_ratio text not null default '16:9'
    check (aspect_ratio in ('16:9', '9:16')),
  resolution text not null default '720p'
    check (resolution in ('720p', '1080p')),
  file_id uuid references public.user_files(id) on delete set null,
  error_message text,
  billing_receipt jsonb not null default '{}'::jsonb,
  billing_refunded boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index media_jobs_user_idempotency_idx
  on public.media_jobs(user_id, idempotency_key)
  where idempotency_key is not null;

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

grant select, insert, update, delete
  on all tables in schema public
  to service_role;

-- This row represents a provider launch written by the pre-atomic release.
-- The target migration must classify and fence it during its backfill.
insert into public.users (id)
values ('10000000-0000-4000-8000-000000000001');

insert into public.media_jobs (
  id,
  user_id,
  kind,
  provider,
  provider_job_id,
  idempotency_key,
  status,
  prompt,
  model,
  billing_receipt,
  created_at,
  updated_at
)
values (
  '11000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000001',
  'video',
  'gemini',
  'pending:pre-atomic-lock-order',
  'pre-atomic-lock-order',
  'queued',
  'Pre-atomic compatibility fixture.',
  'veo-test',
  '{"paymentSource":"subscription","eventId":null}'::jsonb,
  now() - interval '1 hour',
  now() - interval '1 hour'
);

commit;
