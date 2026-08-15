-- Ask Crump 5.4.1
-- Durable, leased full-manuscript generation jobs for the Python/Vercel runtime.

begin;

create table if not exists public.manuscript_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  manuscript_id uuid not null references public.manuscripts(id) on delete cascade,
  chat_id uuid,
  status text not null default 'queued'
    check (status in (
      'queued','running','paused','awaiting_credits','completed','failed','cancelled'
    )),
  stage text not null default 'blueprint'
    check (stage in ('blueprint','drafting','export','complete')),
  mode text not null default 'autopilot'
    check (mode in ('outline','autopilot')),
  brief text not null,
  target_words integer not null default 80000
    check (target_words between 20000 and 150000),
  chapter_count integer not null default 28
    check (chapter_count between 8 and 80),
  preferred_export_format text not null default 'docx'
    check (preferred_export_format in ('docx','pdf','epub')),
  completed_sections integer not null default 0 check (completed_sections >= 0),
  total_sections integer not null default 0 check (total_sections >= 0),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  consecutive_failures integer not null default 0 check (consecutive_failures >= 0),
  not_before timestamptz not null default now(),
  lease_token uuid,
  lease_expires_at timestamptz,
  current_section_id uuid references public.manuscript_sections(id) on delete set null,
  current_receipt jsonb not null default '{}'::jsonb,
  blueprint_receipt jsonb not null default '{}'::jsonb,
  provider_usage jsonb not null default '{}'::jsonb,
  output_file_id uuid references public.user_files(id) on delete set null,
  last_error_code text,
  last_error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz
);

create unique index if not exists manuscript_runs_one_active_idx
  on public.manuscript_runs(manuscript_id)
  where status in ('queued','running','paused','awaiting_credits');

create index if not exists manuscript_runs_queue_idx
  on public.manuscript_runs(status, not_before, created_at)
  where status in ('queued','running');

create index if not exists manuscript_runs_user_idx
  on public.manuscript_runs(user_id, created_at desc);

create index if not exists manuscript_runs_project_id_idx
  on public.manuscript_runs(project_id);

create index if not exists manuscript_runs_current_section_id_idx
  on public.manuscript_runs(current_section_id);

create index if not exists manuscript_runs_output_file_id_idx
  on public.manuscript_runs(output_file_id);

alter table public.manuscript_runs enable row level security;
revoke all on table public.manuscript_runs from anon, authenticated;
grant all on table public.manuscript_runs to service_role;

create or replace function public.claim_manuscript_run(p_lease_seconds integer default 420)
returns setof public.manuscript_runs
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  claimed public.manuscript_runs%rowtype;
begin
  select *
  into claimed
  from public.manuscript_runs
  where not_before <= now()
    and (
      status = 'queued'
      or (status = 'running' and lease_expires_at < now())
    )
  order by created_at asc
  for update skip locked
  limit 1;

  if not found then
    return;
  end if;

  update public.manuscript_runs
  set status = 'running',
      lease_token = gen_random_uuid(),
      lease_expires_at = now() + make_interval(secs => greatest(60, least(900, p_lease_seconds))),
      attempt_count = attempt_count + 1,
      started_at = coalesce(started_at, now()),
      updated_at = now()
  where id = claimed.id
  returning * into claimed;

  return next claimed;
end;
$$;

revoke all on function public.claim_manuscript_run(integer) from public, anon, authenticated;
grant execute on function public.claim_manuscript_run(integer) to service_role;

comment on table public.manuscript_runs is
  'Server-only durable manuscript generation runs. Leases make each step recoverable after function timeout or restart.';

commit;
