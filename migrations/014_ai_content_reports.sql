-- Ask Crump 5.4.1
-- Private, account-scoped moderation intake for in-app AI output reports.

begin;

create table if not exists public.ai_content_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  message_id text not null default '',
  category text not null check (category in (
    'hate_or_harassment',
    'sexual_content',
    'violence_or_danger',
    'self_harm',
    'deception_or_fraud',
    'privacy',
    'copyright',
    'other'
  )),
  comment text not null default '' check (char_length(comment) <= 2000),
  reported_output text not null check (char_length(reported_output) between 1 and 30000),
  prompt_context text not null default '' check (char_length(prompt_context) <= 5000),
  client_platform text not null default 'web' check (char_length(client_platform) <= 40),
  status text not null default 'new'
    check (status in ('new', 'reviewing', 'resolved', 'dismissed')),
  resolution_notes text not null default '',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ai_content_reports_review_queue_idx
  on public.ai_content_reports(status, created_at asc);
create index if not exists ai_content_reports_user_idx
  on public.ai_content_reports(user_id, created_at desc);

alter table public.ai_content_reports enable row level security;
revoke all on table public.ai_content_reports from public, anon, authenticated;
grant all on table public.ai_content_reports to service_role;

comment on table public.ai_content_reports is
  'Server-only moderation queue created by the in-app Report response control. Deleted with the owning account.';

commit;
