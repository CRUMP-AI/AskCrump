#!/usr/bin/env bash
set -euo pipefail

psql_base=(psql -X --set=ON_ERROR_STOP=1)

"${psql_base[@]}" <<'SQL'
insert into public.users (
  id, email, is_guest, is_verified, created_at,
  registration_environment, subscription_tier, subscription_status
) values
  (
    '40000000-0000-4000-8000-000000000001',
    'guest-40000000-0000-4000-8000-000000000001@guest.askcrump.local',
    true, false, pg_catalog.statement_timestamp() - interval '1 minute',
    'production', 'free', 'inactive'
  ),
  (
    '40000000-0000-4000-8000-000000000002',
    'guest-40000000-0000-4000-8000-000000000002@guest.askcrump.local',
    true, false, pg_catalog.statement_timestamp() - interval '1 minute',
    'production', 'free', 'inactive'
  );
SQL

first_sql="$(mktemp)"
second_sql="$(mktemp)"
ready_file="$(mktemp)"
cleanup() {
  rm -f "$first_sql" "$second_sql" "$ready_file"
}
trap cleanup EXIT

wait_for_ready() {
  local scenario="$1"
  local attempt
  for attempt in $(seq 1 500); do
    if grep -qx 'ready' "$ready_file"; then
      return 0
    fi
    if ! kill -0 "$first_pid" 2>/dev/null; then
      wait "$first_pid" || true
      echo "First connection exited before $scenario readiness."
      exit 1
    fi
    # This is only a bounded sentinel poll. The contender is never launched
    # until the first connection explicitly signals after acquiring its lock.
    sleep 0.02
  done

  echo "Timed out waiting for $scenario readiness."
  kill "$first_pid" 2>/dev/null || true
  wait "$first_pid" || true
  exit 1
}

cat >"$first_sql" <<'SQL'
begin;
set local lock_timeout = '5s';
set local statement_timeout = '10s';
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '40000000-0000-4000-8000-000000000001',
  'guest-race-first-token',
  'guest-race-device',
  pg_catalog.statement_timestamp() + interval '1 day'
)
on conflict (device_id) do update
set user_id = excluded.user_id,
    token_hash = excluded.token_hash,
    expires_at = excluded.expires_at,
    revoked_at = null;
\! printf 'ready\n' > "$READY_FILE"
select pg_catalog.pg_sleep(1);
commit;
SQL

cat >"$second_sql" <<'SQL'
begin;
set local lock_timeout = '5s';
set local statement_timeout = '10s';
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '40000000-0000-4000-8000-000000000002',
  'guest-race-second-token',
  'guest-race-device',
  pg_catalog.statement_timestamp() + interval '1 day'
)
on conflict (device_id) do update
set user_id = excluded.user_id,
    token_hash = excluded.token_hash,
    expires_at = excluded.expires_at,
    revoked_at = null;
commit;
SQL

: >"$ready_file"
READY_FILE="$ready_file" timeout 15s "${psql_base[@]}" --file="$first_sql" &
first_pid=$!
wait_for_ready "different-owner same-device"
timeout 15s "${psql_base[@]}" --file="$second_sql" &
second_pid=$!

wait "$first_pid"
wait "$second_pid"

"${psql_base[@]}" <<'SQL'
insert into public.users (
  id, email, is_guest, is_verified, created_at,
  registration_environment, subscription_tier, subscription_status
) values
  (
    '40000000-0000-4000-8000-000000000003',
    'guest-40000000-0000-4000-8000-000000000003@guest.askcrump.local',
    true, false, pg_catalog.statement_timestamp() - interval '1 minute',
    'production', 'free', 'inactive'
  ),
  (
    '40000000-0000-4000-8000-000000000004',
    'guest-40000000-0000-4000-8000-000000000004@guest.askcrump.local',
    true, false, pg_catalog.statement_timestamp() - interval '1 minute',
    'production', 'free', 'inactive'
  ),
  (
    '40000000-0000-4000-8000-000000000005',
    'guest-40000000-0000-4000-8000-000000000005@guest.askcrump.local',
    true, false, pg_catalog.statement_timestamp() - interval '1 minute',
    'production', 'free', 'inactive'
  );
SQL

# Same guest and same device: the owner lock must serialize before either
# transaction reaches the unique conflict row. Both writes succeed; one first
# stamp survives and the second same-owner update is a measurement no-op.
cat >"$first_sql" <<'SQL'
begin;
set local lock_timeout = '5s';
set local statement_timeout = '10s';
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '40000000-0000-4000-8000-000000000003',
  'same-owner-same-device-first',
  'same-owner-same-device',
  pg_catalog.statement_timestamp() + interval '1 day'
)
on conflict (device_id) do update
set user_id = excluded.user_id,
    token_hash = excluded.token_hash,
    expires_at = excluded.expires_at,
    revoked_at = null;
\! printf 'ready\n' > "$READY_FILE"
select pg_catalog.pg_sleep(1);
commit;
SQL

cat >"$second_sql" <<'SQL'
begin;
set local lock_timeout = '5s';
set local statement_timeout = '10s';
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '40000000-0000-4000-8000-000000000003',
  'same-owner-same-device-second',
  'same-owner-same-device',
  pg_catalog.statement_timestamp() + interval '1 day'
)
on conflict (device_id) do update
set user_id = excluded.user_id,
    token_hash = excluded.token_hash,
    expires_at = excluded.expires_at,
    revoked_at = null;
commit;
SQL

: >"$ready_file"
READY_FILE="$ready_file" timeout 15s "${psql_base[@]}" --file="$first_sql" &
first_pid=$!
wait_for_ready "same-owner same-device"
timeout 15s "${psql_base[@]}" --file="$second_sql" &
second_pid=$!
wait "$first_pid"
wait "$second_pid"

# Same guest and different devices: concurrent first inserts also serialize on
# the owner and create two sessions without competing timestamp upgrades.
cat >"$first_sql" <<'SQL'
begin;
set local lock_timeout = '5s';
set local statement_timeout = '10s';
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '40000000-0000-4000-8000-000000000004',
  'same-owner-different-device-first',
  'same-owner-device-a',
  pg_catalog.statement_timestamp() + interval '1 day'
);
\! printf 'ready\n' > "$READY_FILE"
select pg_catalog.pg_sleep(1);
commit;
SQL

cat >"$second_sql" <<'SQL'
begin;
set local lock_timeout = '5s';
set local statement_timeout = '10s';
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '40000000-0000-4000-8000-000000000004',
  'same-owner-different-device-second',
  'same-owner-device-b',
  pg_catalog.statement_timestamp() + interval '1 day'
);
commit;
SQL

: >"$ready_file"
READY_FILE="$ready_file" timeout 15s "${psql_base[@]}" --file="$first_sql" &
first_pid=$!
wait_for_ready "same-owner different-device"
timeout 15s "${psql_base[@]}" --file="$second_sql" &
second_pid=$!
wait "$first_pid"
wait "$second_pid"

# A session may be active when its statement begins and expire while waiting
# for the owner. The post-lock clock recheck must keep that persisted but stale
# session out of the guest-start cohort.
cat >"$first_sql" <<'SQL'
begin;
set local statement_timeout = '10s';
select account.id
  from public.users as account
 where account.id = '40000000-0000-4000-8000-000000000005'
 for update;
\! printf 'ready\n' > "$READY_FILE"
select pg_catalog.pg_sleep(1);
commit;
SQL

cat >"$second_sql" <<'SQL'
begin;
set local lock_timeout = '5s';
set local statement_timeout = '10s';
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '40000000-0000-4000-8000-000000000005',
  'near-expiry-owner-wait',
  'near-expiry-owner-wait',
  pg_catalog.clock_timestamp() + interval '400 milliseconds'
);
commit;
SQL

: >"$ready_file"
READY_FILE="$ready_file" timeout 15s "${psql_base[@]}" --file="$first_sql" &
first_pid=$!
wait_for_ready "near-expiry owner-lock"
timeout 15s "${psql_base[@]}" --file="$second_sql" &
second_pid=$!
wait "$first_pid"
wait "$second_pid"

"${psql_base[@]}" <<'SQL'
do $$
declare
  v_stamped bigint;
  v_owner uuid;
  v_same_device_sessions bigint;
  v_different_device_sessions bigint;
begin
  select pg_catalog.count(*)
    into v_stamped
    from public.users as account
   where account.id in (
     '40000000-0000-4000-8000-000000000001'::uuid,
     '40000000-0000-4000-8000-000000000002'::uuid
   )
     and account.guest_started_at is not null
     and account.guest_start_environment = 'production';

  select session_row.user_id
    into strict v_owner
    from public.sessions as session_row
   where session_row.device_id = 'guest-race-device';

  select pg_catalog.count(*)
    into v_same_device_sessions
    from public.sessions as session_row
   where session_row.user_id =
     '40000000-0000-4000-8000-000000000003'::uuid
     and session_row.device_id = 'same-owner-same-device';

  select pg_catalog.count(*)
    into v_different_device_sessions
    from public.sessions as session_row
   where session_row.user_id =
     '40000000-0000-4000-8000-000000000004'::uuid
     and session_row.device_id in ('same-owner-device-a', 'same-owner-device-b');

  if v_stamped <> 2 then
    raise exception 'same-device upserts stamped % guests, expected 2', v_stamped;
  end if;

  if v_owner <> '40000000-0000-4000-8000-000000000002'::uuid then
    raise exception 'same-device upsert finished with unexpected owner %', v_owner;
  end if;

  if v_same_device_sessions <> 1
     or v_different_device_sessions <> 2 then
    raise exception
      'same-owner races produced wrong session counts: same-device=% different-device=%',
      v_same_device_sessions,
      v_different_device_sessions;
  end if;

  if exists (
    select 1
      from public.users as account
     where account.id in (
       '40000000-0000-4000-8000-000000000003'::uuid,
       '40000000-0000-4000-8000-000000000004'::uuid
     )
       and (
         account.guest_started_at is null
         or account.guest_start_environment <> 'production'
       )
  ) then
    raise exception 'same-owner first-session race lost its immutable stamp';
  end if;

  if not exists (
    select 1
      from public.users as account
      join public.sessions as session_row on session_row.user_id = account.id
     where account.id = '40000000-0000-4000-8000-000000000005'::uuid
       and account.guest_started_at is null
       and account.guest_start_environment is null
       and session_row.device_id = 'near-expiry-owner-wait'
       and session_row.expires_at <= pg_catalog.clock_timestamp()
  ) then
    raise exception 'owner-lock wait stamped a session that expired while blocked';
  end if;
end;
$$;
SQL
