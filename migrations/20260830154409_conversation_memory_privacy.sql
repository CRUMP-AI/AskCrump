-- Account-scoped conversation memory privacy.
--
-- A row means the conversation has opted out of long-term memory retrieval and
-- learning. The chat itself remains usable and synchronized. Keeping this as a
-- separate sparse table avoids creating blank conversations and makes privacy
-- independent of ordinary chat-sync conflict resolution.

create table if not exists public.chat_memory_opt_outs (
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, chat_id)
);

alter table public.chat_memory_opt_outs enable row level security;

-- Browsers use the authenticated Python API. Only the server-side service role
-- may access this table through PostgREST.
revoke all on table public.chat_memory_opt_outs from public, anon, authenticated;
grant select, insert, update, delete on table public.chat_memory_opt_outs to service_role;

comment on table public.chat_memory_opt_outs is
  'Sparse, account-scoped opt-outs that disable long-term memory retrieval and learning for one conversation.';
