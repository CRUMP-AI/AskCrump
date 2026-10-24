create or replace function public.mutate_push_registration_v1(
  p_user_id uuid,
  p_session_id uuid,
  p_session_token_hash text,
  p_installation_id text,
  p_platform text,
  p_token text,
  p_enabled boolean,
  p_session_expires_at timestamptz
)
returns table (applied boolean, stale boolean, owner_id uuid, enabled boolean)
language sql
volatile
security definer
set search_path = ''
as $$ select false, true, null::uuid, false $$;
