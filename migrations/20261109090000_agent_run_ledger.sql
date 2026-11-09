-- Agent run ledger, steps, and pending approvals (Slice 1 foundation).
--
-- The authenticated API is the only database gateway. Runs, their
-- append-only steps, and the exact payloads awaiting a user's decision
-- remain server-only so a browser cannot bypass ownership checks,
-- rewrite an approved payload, or mutate lifecycle state directly.
-- Capability risk, approval, and cost rules live in the backend
-- capability registry; these tables only record what happened.

begin;

create table if not exists public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid references public.projects(id) on delete set null,
  conversation_id text,
  capability_id text not null,
  status text not null default 'queued',
  input_summary jsonb not null default '{}'::jsonb,
  result_summary text,
  credit_cost integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_runs_capability_length_check
    check (char_length(capability_id) between 1 and 80),
  constraint agent_runs_status_check
    check (status in (
      'queued', 'planning', 'running', 'waiting_approval',
      'waiting_user', 'succeeded', 'failed', 'cancelled'
    )),
  constraint agent_runs_conversation_length_check
    check (conversation_id is null or char_length(conversation_id) <= 160),
  constraint agent_runs_input_summary_shape_check
    check (
      jsonb_typeof(input_summary) = 'object'
      and octet_length(input_summary::text) <= 16000
    ),
  constraint agent_runs_result_summary_length_check
    check (result_summary is null or char_length(result_summary) <= 20000),
  constraint agent_runs_credit_cost_check
    check (credit_cost is null or credit_cost between 0 and 100000)
);

create index if not exists agent_runs_user_created_idx
  on public.agent_runs(user_id, created_at desc);

create index if not exists agent_runs_user_status_idx
  on public.agent_runs(user_id, status, updated_at desc);

create table if not exists public.agent_run_steps (
  id bigint generated always as identity primary key,
  run_id uuid not null references public.agent_runs(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  capability_id text not null,
  step_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint agent_run_steps_capability_length_check
    check (char_length(capability_id) between 1 and 80),
  constraint agent_run_steps_type_check
    check (step_type in (
      'run.created', 'run.queued', 'run.started',
      'step.started', 'step.completed', 'step.failed',
      'approval.requested', 'approval.decided',
      'run.completed', 'run.failed', 'run.cancelled'
    )),
  constraint agent_run_steps_payload_shape_check
    check (
      jsonb_typeof(payload) = 'object'
      and octet_length(payload::text) <= 16000
    )
);

create index if not exists agent_run_steps_run_idx
  on public.agent_run_steps(run_id, id asc);

create table if not exists public.agent_pending_actions (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.agent_runs(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  capability_id text not null,
  exact_payload jsonb not null default '{}'::jsonb,
  rendered_summary text not null,
  credit_cost integer,
  status text not null default 'pending',
  expires_at timestamptz not null,
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_pending_actions_capability_length_check
    check (char_length(capability_id) between 1 and 80),
  constraint agent_pending_actions_status_check
    check (status in ('pending', 'approved', 'denied', 'expired', 'cancelled')),
  constraint agent_pending_actions_payload_shape_check
    check (
      jsonb_typeof(exact_payload) = 'object'
      and octet_length(exact_payload::text) <= 16000
    ),
  constraint agent_pending_actions_summary_length_check
    check (char_length(rendered_summary) between 1 and 500),
  constraint agent_pending_actions_credit_cost_check
    check (credit_cost is null or credit_cost between 0 and 100000)
);

create index if not exists agent_pending_actions_user_status_idx
  on public.agent_pending_actions(user_id, status, created_at desc);

create index if not exists agent_pending_actions_run_idx
  on public.agent_pending_actions(run_id, created_at desc);

alter table public.agent_runs enable row level security;
alter table public.agent_run_steps enable row level security;
alter table public.agent_pending_actions enable row level security;

revoke all privileges on public.agent_runs from anon, authenticated;
revoke all privileges on public.agent_run_steps from anon, authenticated;
revoke all privileges on public.agent_pending_actions from anon, authenticated;

commit;
