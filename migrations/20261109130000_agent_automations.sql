-- Agent automations (Slice 2 scheduling foundation).
--
-- An automation is a standing rule a user created: run one schedulable
-- capability on a simple daily schedule. The model is deliberately
-- small — a daily local time in a named timezone, no cron-expression
-- engine — and the authenticated API is the only database gateway, so
-- rows stay server-only and a browser cannot create or mutate another
-- user's schedule directly. The trigger endpoint computes due-ness
-- from next_run_at; this table only records the standing rule and when
-- it last ran.

begin;

create table if not exists public.agent_automations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  capability_id text not null,
  schedule_kind text not null default 'daily',
  local_time text not null,
  timezone text not null default 'UTC',
  payload jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  last_run_at timestamptz,
  next_run_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_automations_capability_length_check
    check (char_length(capability_id) between 1 and 80),
  constraint agent_automations_schedule_kind_check
    check (schedule_kind in ('daily')),
  constraint agent_automations_local_time_check
    check (local_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
  constraint agent_automations_timezone_length_check
    check (char_length(timezone) between 1 and 64),
  constraint agent_automations_payload_shape_check
    check (
      jsonb_typeof(payload) = 'object'
      and octet_length(payload::text) <= 16000
    )
);

create index if not exists agent_automations_user_created_idx
  on public.agent_automations(user_id, created_at desc);

create index if not exists agent_automations_due_idx
  on public.agent_automations(enabled, next_run_at);

alter table public.agent_automations enable row level security;

revoke all privileges on public.agent_automations from anon, authenticated;

commit;
