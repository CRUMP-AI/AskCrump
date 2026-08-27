-- Crump Code foundation.
--
-- The authenticated API is the only database gateway. Coding tasks, audit
-- events, approvals, generated patches, and Sandbox identifiers remain
-- server-only so a browser cannot bypass ownership checks or mutate lifecycle
-- state directly.

begin;

create table if not exists public.code_tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  objective text not null,
  mode text not null default 'plan',
  source_repo_url text not null,
  source_ref text,
  status text not null default 'queued',
  network_policy text not null default 'deny_all',
  max_duration_seconds integer not null default 180,
  sandbox_name text,
  sandbox_session_id text,
  base_snapshot_id text,
  final_snapshot_id text,
  base_revision text,
  result_summary text,
  result_patch text,
  verification jsonb not null default '[]'::jsonb,
  failure_code text,
  usage_receipt jsonb,
  payment_source text,
  credits_spent integer not null default 0,
  cancel_requested_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  expires_at timestamptz not null default (now() + interval '7 days'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint code_tasks_objective_length_check
    check (char_length(objective) between 1 and 12000),
  constraint code_tasks_mode_check
    check (mode in ('plan', 'implement')),
  constraint code_tasks_source_repo_url_length_check
    check (char_length(source_repo_url) between 1 and 500),
  constraint code_tasks_source_ref_length_check
    check (source_ref is null or char_length(source_ref) between 1 and 160),
  constraint code_tasks_status_check
    check (status in (
      'queued', 'provisioning', 'running', 'awaiting_approval',
      'verifying', 'completed', 'failed', 'cancelled'
    )),
  constraint code_tasks_network_policy_check
    check (network_policy = 'deny_all'),
  constraint code_tasks_duration_check
    check (max_duration_seconds between 30 and 240),
  constraint code_tasks_summary_length_check
    check (result_summary is null or char_length(result_summary) <= 20000),
  constraint code_tasks_patch_length_check
    check (result_patch is null or char_length(result_patch) <= 200000),
  constraint code_tasks_verification_shape_check
    check (jsonb_typeof(verification) = 'array' and octet_length(verification::text) <= 40000),
  constraint code_tasks_failure_code_length_check
    check (failure_code is null or char_length(failure_code) <= 80),
  constraint code_tasks_usage_receipt_shape_check
    check (
      usage_receipt is null
      or (jsonb_typeof(usage_receipt) = 'object' and octet_length(usage_receipt::text) <= 4000)
    ),
  constraint code_tasks_credits_spent_check
    check (credits_spent between 0 and 100000)
);

create index if not exists code_tasks_project_created_idx
  on public.code_tasks(project_id, created_at desc);

create index if not exists code_tasks_user_active_idx
  on public.code_tasks(user_id, updated_at desc)
  where status in ('queued', 'provisioning', 'running', 'awaiting_approval', 'verifying');

create index if not exists code_tasks_recovery_idx
  on public.code_tasks(status, updated_at asc)
  where status in ('provisioning', 'running', 'verifying');

create table if not exists public.code_task_events (
  id bigint generated always as identity primary key,
  task_id uuid not null references public.code_tasks(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint code_task_events_type_check
    check (event_type in (
      'task.created', 'task.claimed', 'sandbox.provisioned', 'agent.started',
      'tool.requested', 'tool.completed', 'verification.started',
      'verification.completed', 'approval.requested', 'approval.decided',
      'task.completed', 'task.failed', 'task.cancelled', 'task.requeued'
    )),
  constraint code_task_events_payload_shape_check
    check (jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 16000)
);

create index if not exists code_task_events_task_idx
  on public.code_task_events(task_id, id asc);

create table if not exists public.code_task_approvals (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.code_tasks(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  action_type text not null,
  status text not null default 'pending',
  title text not null,
  details text not null default '',
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '30 minutes'),
  decided_at timestamptz,
  constraint code_task_approvals_action_check
    check (action_type in (
      'network_access', 'credential_access', 'destructive_source_write',
      'publish', 'extended_runtime'
    )),
  constraint code_task_approvals_status_check
    check (status in ('pending', 'approved', 'denied', 'expired')),
  constraint code_task_approvals_title_length_check
    check (char_length(title) between 1 and 200),
  constraint code_task_approvals_details_length_check
    check (char_length(details) <= 2000)
);

create index if not exists code_task_approvals_task_idx
  on public.code_task_approvals(task_id, created_at desc);

create unique index if not exists code_task_approvals_one_pending_action_idx
  on public.code_task_approvals(task_id, action_type)
  where status = 'pending';

alter table public.code_tasks enable row level security;
alter table public.code_task_events enable row level security;
alter table public.code_task_approvals enable row level security;

revoke all on table public.code_tasks from public, anon, authenticated;
revoke all on table public.code_task_events from public, anon, authenticated;
revoke all on table public.code_task_approvals from public, anon, authenticated;
revoke all on sequence public.code_task_events_id_seq from public, anon, authenticated;
revoke all on table public.code_tasks from service_role;
revoke all on table public.code_task_events from service_role;
revoke all on table public.code_task_approvals from service_role;
revoke all on sequence public.code_task_events_id_seq from service_role;

grant all on table public.code_tasks to service_role;
grant select, insert on table public.code_task_events to service_role;
grant select, insert, update on table public.code_task_approvals to service_role;
grant usage, select on sequence public.code_task_events_id_seq to service_role;

comment on table public.code_tasks is
  'Server-only Crump Code tasks. Source is limited to public GitHub repositories; generated code executes only in short-lived deny-all-network Sandboxes and never writes to the source repository.';

comment on table public.code_task_events is
  'Append-only Crump Code lifecycle and tool audit events. Payloads are bounded and must not contain credentials, repository file contents, model prompts, or raw command output.';

comment on table public.code_task_approvals is
  'Server-only human approval ledger for future network, credential, destructive source write, publish, and extended-runtime capabilities.';

commit;
