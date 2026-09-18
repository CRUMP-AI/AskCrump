-- Durable, service-role-only account deletion state.
--
-- Supabase Storage objects are not removed by database cascades. This record
-- intentionally survives public.users so the worker can sweep uploads that
-- finish after the account row is deleted. It stores identifiers and state
-- only; no customer content, paths, filenames, URLs, or credentials.
-- This migration is intentionally ordered after
-- 20260918041136_ai_data_sharing_consent.sql; the deletion fence atomically
-- revokes the consent columns introduced there.

begin;

set local lock_timeout = '5s';

alter table public.users
  add column if not exists account_deletion_token uuid;

do $constraint$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'users_account_deletion_token_requires_deleted_at'
      and conrelid = 'public.users'::regclass
  ) then
    alter table public.users
      add constraint users_account_deletion_token_requires_deleted_at
      check (account_deletion_token is null or deleted_at is not null);
  end if;
end;
$constraint$;

create table if not exists public.account_deletion_jobs (
  user_id uuid primary key,
  operation_token uuid not null unique,
  state text not null
    check (state in (
      'fencing',
      'fenced',
      'retry_pending',
      'late_upload_sweep',
      'complete',
      'abandoned'
    )),
  fenced_at timestamptz not null,
  account_deleted_at timestamptz,
  finalize_after timestamptz not null,
  next_attempt_at timestamptz,
  attempts integer not null default 0 check (attempts >= 0),
  last_error_code text
    check (last_error_code is null or last_error_code ~ '^[A-Z0-9_]{1,80}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  constraint account_deletion_jobs_completion_check check (
    (state in ('complete', 'abandoned')) = (completed_at is not null)
  ),
  constraint account_deletion_jobs_window_check check (
    finalize_after > fenced_at
  )
);

create index if not exists account_deletion_jobs_due_idx
  on public.account_deletion_jobs(next_attempt_at)
  where completed_at is null and next_attempt_at is not null;

alter table public.account_deletion_jobs enable row level security;

revoke all on table public.account_deletion_jobs
  from public, anon, authenticated, service_role;
grant select, insert, update, delete on table public.account_deletion_jobs
  to service_role;

comment on table public.account_deletion_jobs is
  'Content-free durable tombstones for account deletion and late private Storage sweeps.';
comment on column public.users.account_deletion_token is
  'Server-only operation token fencing writes while durable account deletion runs.';

commit;
