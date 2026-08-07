-- Ask Crump 4.4.0
-- Intelligence foundation: user-controlled memory, orchestration preferences,
-- and privacy-safe request observability.
--
-- Raw prompts and model answers are intentionally NOT written to ai_request_traces.

create table if not exists public.user_ai_preferences (
  user_id uuid primary key references public.users(id) on delete cascade,
  intelligence_mode text not null default 'auto'
    check (intelligence_mode in ('auto', 'fast', 'deep')),
  memory_enabled boolean not null default true,
  auto_learn boolean not null default true,
  auto_tools boolean not null default true,
  verification_level text not null default 'auto'
    check (verification_level in ('off', 'auto', 'strict')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.user_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  memory_key text not null,
  kind text not null default 'note'
    check (kind in ('explicit', 'preference', 'goal', 'project', 'identity', 'note')),
  content text not null check (char_length(content) between 1 and 2000),
  importance smallint not null default 3 check (importance between 1 and 5),
  confidence double precision not null default 1
    check (confidence >= 0 and confidence <= 1),
  source_chat_id uuid,
  source_message_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_used_at timestamptz,
  deleted_at timestamptz,
  unique (user_id, memory_key)
);

create index if not exists user_memories_active_lookup_idx
  on public.user_memories(user_id, importance desc, updated_at desc)
  where deleted_at is null;

create table if not exists public.ai_request_traces (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  request_id text not null,
  chat_id uuid,
  message_id uuid,
  requested_mode text,
  effective_mode text,
  route text,
  planner_used boolean not null default false,
  verifier_used boolean not null default false,
  memory_count integer not null default 0 check (memory_count >= 0),
  tool_flags jsonb not null default '{}'::jsonb,
  model text,
  latency_ms integer not null default 0 check (latency_ms >= 0),
  status text not null,
  error_code text,
  created_at timestamptz not null default now()
);

create index if not exists ai_request_traces_user_created_idx
  on public.ai_request_traces(user_id, created_at desc);

create index if not exists ai_request_traces_status_created_idx
  on public.ai_request_traces(status, created_at desc);

alter table public.user_ai_preferences enable row level security;
alter table public.user_memories enable row level security;
alter table public.ai_request_traces enable row level security;

-- These tables are accessed only through the authenticated Python API using
-- the service role. Browsers never receive the service role key and do not
-- query these tables directly.
revoke all on table public.user_ai_preferences from anon, authenticated;
revoke all on table public.user_memories from anon, authenticated;
revoke all on table public.ai_request_traces from anon, authenticated;

grant all on table public.user_ai_preferences to service_role;
grant all on table public.user_memories to service_role;
grant all on table public.ai_request_traces to service_role;

-- Seed defaults for existing users so intelligence preferences are immediately
-- consistent across signed-in devices.
insert into public.user_ai_preferences (user_id)
select id from public.users
on conflict (user_id) do nothing;
