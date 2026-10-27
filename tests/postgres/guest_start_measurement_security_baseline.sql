\set ON_ERROR_STOP on

-- The isolated registration baseline predates the production access boundary.
-- Reproduce the live server-only posture before applying guest-start facts.
alter table public.users enable row level security;
alter table public.sessions enable row level security;

revoke all on table public.users from public, anon, authenticated;
revoke all on table public.sessions from public, anon, authenticated;
