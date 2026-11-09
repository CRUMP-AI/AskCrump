-- Google connections for agent capabilities (Slice 1).
--
-- The authenticated API is the only database gateway. Connection rows
-- hold OAuth tokens only as vault ciphertext, so a browser cannot read
-- a token, bypass ownership checks, or mutate connection state
-- directly. Scopes are stored per connection so the store declaration
-- and any later scope review can see exactly what was granted.

begin;

create table if not exists public.agent_connections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  provider text not null,
  account_email text not null,
  scopes jsonb not null default '[]'::jsonb,
  access_token_ciphertext text not null default '',
  refresh_token_ciphertext text not null default '',
  token_expires_at timestamptz,
  status text not null default 'connected',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_connections_provider_check
    check (provider in ('google')),
  constraint agent_connections_status_check
    check (status in ('connected', 'revoked', 'error')),
  constraint agent_connections_account_email_length_check
    check (char_length(account_email) between 1 and 320),
  constraint agent_connections_scopes_shape_check
    check (jsonb_typeof(scopes) = 'array'),
  constraint agent_connections_unique_user_provider_account
    unique (user_id, provider, account_email)
);

create index if not exists agent_connections_user_provider_idx
  on public.agent_connections(user_id, provider, status);

alter table public.agent_connections enable row level security;

revoke all privileges on public.agent_connections from anon, authenticated;

commit;
