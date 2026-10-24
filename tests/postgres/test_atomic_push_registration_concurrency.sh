#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(mktemp -d)"
trap 'rm -rf "$fixture_dir"' EXIT

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values (
  '72000000-0000-4000-8000-000000000001',
  '70000000-0000-4000-8000-000000000001',
  repeat('a1', 32),
  'installation-race-same',
  clock_timestamp() - interval '10 minutes',
  clock_timestamp(),
  clock_timestamp() + interval '30 days'
);

select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000001',
  '72000000-0000-4000-8000-000000000001',
  repeat('a1', 32),
  'installation-race-same',
  'ios',
  repeat('S', 24),
  true,
  clock_timestamp() + interval '30 days'
);
SQL

# New-owner rotation wins the session-row lock.  The delayed A unregister must
# re-read the rotated session and fail stale rather than disabling B's token.
psql -X --set=ON_ERROR_STOP=1 >"$fixture_dir/new-owner-first.log" <<'SQL' &
begin;
update public.sessions
   set user_id = '70000000-0000-4000-8000-000000000002',
       token_hash = repeat('b2', 32),
       created_at = clock_timestamp(),
       last_activity = clock_timestamp(),
       expires_at = clock_timestamp() + interval '30 days',
       revoked_at = null
 where id = '72000000-0000-4000-8000-000000000001';
select pg_sleep(1);
select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000002',
  '72000000-0000-4000-8000-000000000001',
  repeat('b2', 32),
  'installation-race-same',
  'ios',
  repeat('T', 24),
  true,
  clock_timestamp() + interval '30 days'
);
commit;
SQL
new_owner_pid=$!
sleep 0.2
psql -X --set=ON_ERROR_STOP=1 >"$fixture_dir/stale-unregister.log" <<'SQL' &
select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000001',
  '72000000-0000-4000-8000-000000000001',
  repeat('a1', 32),
  'installation-race-same',
  '',
  '',
  false,
  clock_timestamp() + interval '30 days'
);
SQL
stale_unregister_pid=$!
wait "$new_owner_pid"
wait "$stale_unregister_pid"

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
do $$
begin
  if not exists (
    select 1
      from public.push_tokens
     where installation_id = 'installation-race-same'
       and user_id = '70000000-0000-4000-8000-000000000002'
       and token = repeat('T', 24)
       and enabled
  ) then
    raise exception 'New-owner-first race did not preserve B registration.';
  end if;
end;
$$;

-- Reset the same installation to A for the reverse commit order.
update public.sessions
   set user_id = '70000000-0000-4000-8000-000000000001',
       token_hash = repeat('c3', 32),
       created_at = clock_timestamp() - interval '10 minutes',
       last_activity = clock_timestamp(),
       expires_at = clock_timestamp() + interval '30 days',
       revoked_at = null
 where id = '72000000-0000-4000-8000-000000000001';
delete from public.push_tokens where installation_id = 'installation-race-same';
select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000001',
  '72000000-0000-4000-8000-000000000001',
  repeat('c3', 32),
  'installation-race-same',
  'ios',
  repeat('U', 24),
  true,
  clock_timestamp() + interval '30 days'
);
SQL

# A unregister commits first.  B's login-style rotation and registration must
# wait, then become the final owner instead of being lost to A's completion.
psql -X --set=ON_ERROR_STOP=1 >"$fixture_dir/old-owner-first.log" <<'SQL' &
begin;
select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000001',
  '72000000-0000-4000-8000-000000000001',
  repeat('c3', 32),
  'installation-race-same',
  '',
  '',
  false,
  clock_timestamp() + interval '30 days'
);
select pg_sleep(1);
commit;
SQL
old_owner_pid=$!
sleep 0.2
psql -X --set=ON_ERROR_STOP=1 >"$fixture_dir/new-owner-after.log" <<'SQL' &
begin;
update public.sessions
   set user_id = '70000000-0000-4000-8000-000000000002',
       token_hash = repeat('d4', 32),
       created_at = clock_timestamp(),
       last_activity = clock_timestamp(),
       expires_at = clock_timestamp() + interval '30 days',
       revoked_at = null
 where id = '72000000-0000-4000-8000-000000000001';
select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000002',
  '72000000-0000-4000-8000-000000000001',
  repeat('d4', 32),
  'installation-race-same',
  'ios',
  repeat('V', 24),
  true,
  clock_timestamp() + interval '30 days'
);
commit;
SQL
new_owner_after_pid=$!
wait "$old_owner_pid"
wait "$new_owner_after_pid"

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
do $$
begin
  if not exists (
    select 1
      from public.push_tokens
     where installation_id = 'installation-race-same'
       and user_id = '70000000-0000-4000-8000-000000000002'
       and token = repeat('V', 24)
       and enabled
  ) then
    raise exception 'Old-owner-first race did not finish with B registration.';
  end if;
end;
$$;

insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values
  (
    '72000000-0000-4000-8000-000000000011',
    '70000000-0000-4000-8000-000000000001',
    repeat('e5', 32),
    'installation-token-race-old',
    clock_timestamp() - interval '10 minutes',
    clock_timestamp(),
    clock_timestamp() + interval '30 days'
  ),
  (
    '72000000-0000-4000-8000-000000000012',
    '70000000-0000-4000-8000-000000000002',
    repeat('f6', 32),
    'installation-token-race-new',
    clock_timestamp(),
    clock_timestamp(),
    clock_timestamp() + interval '30 days'
  );
delete from public.push_tokens where token = repeat('W', 24);
SQL

# Hold the token advisory lock so both absent-row claimants queue together.
psql -X --set=ON_ERROR_STOP=1 >"$fixture_dir/token-gate.log" <<'SQL' &
select pg_advisory_lock(pg_catalog.hashtextextended('askcrump.push.token:' || repeat('W', 24), 0));
select pg_sleep(1);
select pg_advisory_unlock(pg_catalog.hashtextextended('askcrump.push.token:' || repeat('W', 24), 0));
SQL
gate_pid=$!
sleep 0.2
psql -X --set=ON_ERROR_STOP=1 >"$fixture_dir/token-old.log" <<'SQL' &
select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000001',
  '72000000-0000-4000-8000-000000000011',
  repeat('e5', 32),
  'installation-token-race-old',
  'ios',
  repeat('W', 24),
  true,
  clock_timestamp() + interval '30 days'
);
SQL
token_old_pid=$!
psql -X --set=ON_ERROR_STOP=1 >"$fixture_dir/token-new.log" <<'SQL' &
select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000002',
  '72000000-0000-4000-8000-000000000012',
  repeat('f6', 32),
  'installation-token-race-new',
  'ios',
  repeat('W', 24),
  true,
  clock_timestamp() + interval '30 days'
);
SQL
token_new_pid=$!
wait "$gate_pid"
wait "$token_old_pid"
wait "$token_new_pid"

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
do $$
begin
  if (
    select count(*) <> 1
        or not bool_and(user_id = '70000000-0000-4000-8000-000000000002'::uuid)
        or not bool_and(installation_id = 'installation-token-race-new')
        or not bool_and(enabled)
      from public.push_tokens
     where token = repeat('W', 24)
  ) then
    raise exception 'Concurrent absent-token claims did not preserve the newer B generation.';
  end if;
end;
$$;
SQL
