\set ON_ERROR_STOP on

-- The registration-cohort gate installs the live registered verification,
-- login, and reset RPCs. Supply the exact live guest-verification signature so
-- this focused gate can exercise its secure replacement without installing the
-- unrelated guest-mode control surface.
create or replace function public.verify_guest_and_create_session_v1(
  p_user_id uuid,
  p_verification_token_hash text,
  p_session_id uuid,
  p_session_token_hash text,
  p_session_expires_at timestamptz,
  p_device_id text,
  p_device_name text,
  p_platform text,
  p_device_info jsonb,
  p_ip_address text,
  p_user_agent text
)
returns table(
  converted boolean,
  user_data jsonb,
  session_data jsonb,
  revoked_sessions bigint
)
language plpgsql
security definer
set search_path = ''
as $$
begin
  return;
end;
$$;

revoke all on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) to service_role;

insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  verification_token_hash, verification_token_expires,
  created_at, updated_at, registration_environment, registration_submitted_at
) values
  (
    '70000000-0000-4000-8000-000000000001',
    'planted-registered@example.test',
    '$argon2id$attacker-planted-registered-hash', false, false,
    repeat('1', 64), pg_catalog.clock_timestamp() + interval '1 day',
    pg_catalog.clock_timestamp() - interval '1 hour',
    pg_catalog.clock_timestamp() - interval '1 hour',
    'production', pg_catalog.clock_timestamp() - interval '1 hour'
  ),
  (
    '70000000-0000-4000-8000-000000000002',
    'planted-guest-conversion@example.test',
    '$argon2id$attacker-planted-guest-hash', false, true,
    repeat('2', 64), pg_catalog.clock_timestamp() + interval '1 day',
    pg_catalog.clock_timestamp() - interval '1 hour',
    pg_catalog.clock_timestamp() - interval '1 hour',
    'production', pg_catalog.clock_timestamp() - interval '1 hour'
  ),
  (
    '70000000-0000-4000-8000-000000000003',
    'already-verified-planted@example.test',
    '$argon2id$attacker-planted-already-verified-hash', true, false,
    null, null,
    pg_catalog.clock_timestamp() - interval '2 hours',
    pg_catalog.clock_timestamp() - interval '1 hour',
    'production', pg_catalog.clock_timestamp() - interval '2 hours'
  );
insert into public.sessions (
  id, user_id, token_hash, device_id, expires_at
) values
  (
    '71000000-0000-4000-8000-000000000001',
    '70000000-0000-4000-8000-000000000001',
    encode(digest(
      'askcrump:preverification-takeover:planted-registered-session:v1',
      'sha256'
    ), 'hex'), 'planted-registered-session',
    pg_catalog.clock_timestamp() + interval '1 day'
  ),
  (
    '71000000-0000-4000-8000-000000000002',
    '70000000-0000-4000-8000-000000000002',
    encode(digest(
      'askcrump:preverification-takeover:planted-guest-session:v1',
      'sha256'
    ), 'hex'), 'planted-guest-session',
    pg_catalog.clock_timestamp() + interval '1 day'
  ),
  (
    '71000000-0000-4000-8000-000000000003',
    '70000000-0000-4000-8000-000000000003',
    encode(digest(
      'askcrump:preverification-takeover:already-verified-attacker-session:v1',
      'sha256'
    ), 'hex'), 'already-verified-attacker-session',
    pg_catalog.clock_timestamp() + interval '1 day'
  );
