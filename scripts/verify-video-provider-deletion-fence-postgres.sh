#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
  echo "video deletion-fence PostgreSQL verification failed: $*" >&2
  exit 1
}

[[ "${ASKCRUMP_DISPOSABLE_POSTGRES:-}" == "1" ]] ||
  fail "set ASKCRUMP_DISPOSABLE_POSTGRES=1 to acknowledge this destructive test database"

export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-postgres}"
export PGDATABASE="${PGDATABASE:-askcrump_video_fence_test}"

case "$PGHOST" in
  127.0.0.1|localhost) ;;
  *) fail "refusing non-local PostgreSQL host: $PGHOST" ;;
esac

[[ "$PGDATABASE" == "askcrump_video_fence_test" ]] ||
  fail "refusing database other than askcrump_video_fence_test"

command -v psql >/dev/null 2>&1 || fail "psql is required"

PSQL=(psql --no-psqlrc --set=ON_ERROR_STOP=1 --quiet --tuples-only --no-align)
TEMP_DIR="$(mktemp -d)"
AUXILIARY_DATABASE="askcrump_video_fence_invalid_preflight"
declare -A SESSION_PIDS=()
declare -A SESSION_OUTPUTS=()
WAIT_TIMEOUT_SECONDS=20

cleanup() {
  local pid
  set +e
  "${PSQL[@]}" --command "delete from deletion_fence_harness.race_gates" \
    >/dev/null 2>&1
  "${PSQL[@]}" --dbname postgres --command \
    "drop database if exists $AUXILIARY_DATABASE with (force);" \
    >/dev/null 2>&1
  for pid in $(jobs -pr); do
    kill "$pid" >/dev/null 2>&1 || true
  done
  for pid in $(jobs -pr); do
    wait "$pid" >/dev/null 2>&1 || true
  done
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

sql_scalar() {
  "${PSQL[@]}" --command "$1" | tr -d '[:space:]'
}

sql_exec() {
  "${PSQL[@]}" --command "$1" >/dev/null
}

assert_equal() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  [[ "$actual" == "$expected" ]] ||
    fail "$label (expected '$expected', got '$actual')"
}

assert_output_line() {
  local file="$1"
  local expected="$2"
  local label="$3"
  grep -Fqx "$expected" "$file" || {
    sed 's/^/  /' "$file" >&2
    fail "$label did not emit '$expected'"
  }
}

expect_permission_denied() {
  local label="$1"
  local statement="$2"
  local output
  if output=$("${PSQL[@]}" --set=VERBOSITY=verbose --command "$statement" 2>&1); then
    fail "$label unexpectedly succeeded"
  fi
  grep -qi "permission denied" <<<"$output" || {
    echo "$output" >&2
    fail "$label failed for an unexpected reason"
  }
}

expect_sql_failure() {
  local label="$1"
  local statement="$2"
  local expected_text="$3"
  local output
  if output=$("${PSQL[@]}" --set=VERBOSITY=verbose --command "$statement" 2>&1); then
    fail "$label unexpectedly succeeded"
  fi
  grep -qi "$expected_text" <<<"$output" || {
    echo "$output" >&2
    fail "$label failed for an unexpected reason"
  }
}

start_session() {
  local app_name="$1"
  local output_file="$2"
  local statement="$3"
  PGAPPNAME="$app_name" "${PSQL[@]}" --command "$statement" \
    >"$output_file" 2>&1 &
  STARTED_PID=$!
  SESSION_PIDS["$app_name"]=$STARTED_PID
  SESSION_OUTPUTS["$app_name"]=$output_file
}

fail_if_session_exited() {
  local app_name="$1"
  local label="$2"
  local pid="${SESSION_PIDS[$app_name]}"
  local output_file="${SESSION_OUTPUTS[$app_name]}"
  if ! kill -0 "$pid" 2>/dev/null; then
    wait "$pid" >/dev/null 2>&1 || true
    sed 's/^/  /' "$output_file" >&2 || true
    fail "$label completed before reaching the expected database wait"
  fi
}

wait_for_session_state() {
  local app_name="$1"
  local label="$2"
  local predicate="$3"
  local deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
  local matching_sessions
  while (( SECONDS < deadline )); do
    fail_if_session_exited "$app_name" "$label"
    matching_sessions="$(sql_scalar "
      select count(*)
      from pg_stat_activity
      where datname = current_database()
        and backend_type = 'client backend'
        and application_name = '$app_name'
        and ($predicate);
    ")"
    if [[ "$matching_sessions" == "1" ]]; then
      return 0
    fi
    sleep 0.05
  done
  "${PSQL[@]}" --command "
    select application_name, pid, state, wait_event_type, wait_event,
      pg_blocking_pids(pid) as blockers, left(query, 160) as query
    from pg_stat_activity
    where datname = current_database()
      and application_name = '$app_name';
  " >&2 || true
  sed 's/^/  /' "${SESSION_OUTPUTS[$app_name]}" >&2 || true
  fail "timed out waiting for $label"
}

wait_for_gate_session() {
  local app_name="$1"
  wait_for_session_state "$app_name" "$app_name to reach its race gate" \
    "wait_event = 'PgSleep'"
}

wait_for_block() {
  local waiter="$1"
  local holder="$2"
  wait_for_session_state "$waiter" \
    "$waiter to enter a PostgreSQL lock wait behind $holder" \
    "wait_event_type = 'Lock' and wait_event in ('transactionid', 'tuple')"
  # The disposable database has no unrelated workload. Prove the named holder
  # still owns the fixture gate while the waiter reports PostgreSQL's Lock state;
  # keep pg_blocking_pids in timeout diagnostics rather than the polling key.
  wait_for_session_state "$holder" "$holder to remain at its race gate" \
    "wait_event = 'PgSleep'"
}

open_gate() {
  sql_exec "delete from deletion_fence_harness.race_gates where name = '$1';"
}

wait_for_session() {
  local pid="$1"
  local output_file="$2"
  local label="$3"
  if ! wait "$pid"; then
    sed 's/^/  /' "$output_file" >&2
    fail "$label session failed"
  fi
}

reset_fixtures() {
  sql_exec "
    truncate table
      public.video_provider_start_claims,
      public.video_account_deletion_fences,
      public.account_deletion_jobs,
      public.media_jobs,
      public.users,
      deletion_fence_harness.race_gates;
  "
}

verify_invalid_legacy_preflight() {
  local apply_output
  local remaining_tables

  "${PSQL[@]}" --dbname postgres --command \
    "drop database if exists $AUXILIARY_DATABASE with (force);" >/dev/null
  "${PSQL[@]}" --dbname postgres --command \
    "create database $AUXILIARY_DATABASE;" >/dev/null
  "${PSQL[@]}" --dbname "$AUXILIARY_DATABASE" \
    --file tests/postgres/video_provider_deletion_fence_bootstrap.sql
  "${PSQL[@]}" --dbname "$AUXILIARY_DATABASE" --command "
    insert into public.users(id)
    values ('09300000-0000-0000-0000-000000000001');
    insert into public.media_jobs(
      id, user_id, kind, status, provider, operation_type, provider_job_id
    ) values
      (
        '09310000-0000-0000-0000-000000000001',
        '09300000-0000-0000-0000-000000000001',
        'video', 'queued', 'unsupported-provider', 'generate', 'provider-job'
      ),
      (
        '09310000-0000-0000-0000-000000000002',
        '09300000-0000-0000-0000-000000000001',
        'video', 'processing', 'runway', 'unsupported-operation', 'provider-job'
      ),
      (
        '09310000-0000-0000-0000-000000000003',
        '09300000-0000-0000-0000-000000000001',
        'video', 'queued', 'gemini', 'generate', '   '
      );
  " >/dev/null

  if apply_output=$("${PSQL[@]}" --dbname "$AUXILIARY_DATABASE" \
      --file staging/video_provider_deletion_fence.sql 2>&1); then
    fail "invalid legacy provider rows unexpectedly passed migration preflight"
  fi
  grep -qi "video deletion-fence preflight failed" <<<"$apply_output" || {
    echo "$apply_output" >&2
    fail "invalid legacy provider rows did not produce the explicit preflight error"
  }

  remaining_tables="$("${PSQL[@]}" --dbname "$AUXILIARY_DATABASE" --command "
    select coalesce(to_regclass('public.video_account_deletion_fences')::text, 'null')
      || ':'
      || coalesce(to_regclass('public.video_provider_start_claims')::text, 'null');
  " | tr -d '[:space:]')"
  assert_equal "$remaining_tables" "null:null" \
    "failed preflight transaction rollback"

  "${PSQL[@]}" --dbname postgres --command \
    "drop database $AUXILIARY_DATABASE with (force);" >/dev/null
}

cd "$ROOT_DIR"

actual_database="$(sql_scalar 'select current_database();')"
assert_equal "$actual_database" "askcrump_video_fence_test" "database safety check"

"${PSQL[@]}" --file tests/postgres/video_provider_deletion_fence_bootstrap.sql
"${PSQL[@]}" --file staging/video_provider_deletion_fence.sql
"${PSQL[@]}" --file staging/video_provider_deletion_fence.sql
"${PSQL[@]}" --file tests/postgres/video_provider_deletion_fence_verify.sql
verify_invalid_legacy_preflight

# Exercise actual permission errors, not only ACL catalog predicates.
expect_permission_denied \
  "anonymous journal read" \
  "set role anon; select * from public.video_provider_start_claims;"
expect_permission_denied \
  "authenticated journal write" \
  "set role authenticated; insert into public.video_account_deletion_fences(user_id, operation_token) values ('90000000-0000-0000-0000-000000000001', '90000000-0000-0000-0000-000000000002');"
expect_permission_denied \
  "anonymous reservation RPC" \
  "set role anon; select public.reserve_video_provider_claim('90000000-0000-0000-0000-000000000001', '90000000-0000-0000-0000-000000000002', 'runway', 'generate');"
expect_permission_denied \
  "authenticated deletion RPC" \
  "set role authenticated; select public.begin_video_account_deletion('90000000-0000-0000-0000-000000000001', '90000000-0000-0000-0000-000000000003');"
expect_permission_denied \
  "authenticated establish deletion RPC" \
  "set role authenticated; select public.establish_account_deletion_fence('90000000-0000-0000-0000-000000000001', '90000000-0000-0000-0000-000000000003', now());"
expect_permission_denied \
  "authenticated recover deletion RPC" \
  "set role authenticated; select public.recover_video_account_deletion_fence('90000000-0000-0000-0000-000000000001', '90000000-0000-0000-0000-000000000003');"
expect_permission_denied \
  "post-migration role reservation RPC" \
  "set role deletion_fence_rls_probe; select public.reserve_video_provider_claim('90000000-0000-0000-0000-000000000001', '90000000-0000-0000-0000-000000000002', 'runway', 'generate');"

sql_exec "
  insert into public.video_account_deletion_fences(user_id, operation_token)
  values (
    '90000000-0000-0000-0000-000000000010',
    '90000000-0000-0000-0000-000000000011'
  );
"
assert_equal "$(sql_scalar "
  set role deletion_fence_rls_probe;
  select count(*) from public.video_account_deletion_fences;
")" "0" "RLS-hidden fence row"
expect_sql_failure \
  "RLS probe fence insert" \
  "set role deletion_fence_rls_probe; insert into public.video_account_deletion_fences(user_id, operation_token) values ('90000000-0000-0000-0000-000000000012', '90000000-0000-0000-0000-000000000013');" \
  "row-level security"

service_smoke="$(sql_scalar "
  set role service_role;
  select public.reserve_video_provider_claim(
    '90000000-0000-0000-0000-000000000001',
    '90000000-0000-0000-0000-000000000002',
    'runway',
    'generate'
  ) ->> 'status';
")"
assert_equal "$service_smoke" "account_deleting" "service-role RPC smoke test"

# Reservation wins the user-row lock: deletion waits, then observes the live
# reservation and returns false without leaving a fence.
reset_fixtures
sql_exec "insert into public.users(id) values ('11000000-0000-0000-0000-000000000001');"
sql_exec "insert into deletion_fence_harness.race_gates(name) values ('reservation-first');"

start_session "reservation_holder" "$TEMP_DIR/reservation-holder.out" "
  begin;
  set role service_role;
  select public.reserve_video_provider_claim(
    '11000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    'runway',
    'generate'
  ) ->> 'status';
  reset role;
  select deletion_fence_harness.wait_for_gate('reservation-first');
  commit;
"
reservation_holder_pid=$STARTED_PID
wait_for_gate_session "reservation_holder"

start_session "deletion_waiter" "$TEMP_DIR/deletion-waiter.out" "
  set statement_timeout = '45s';
  set role service_role;
  select public.begin_video_account_deletion(
    '11000000-0000-0000-0000-000000000001',
    '31000000-0000-0000-0000-000000000001'
  );
"
deletion_waiter_pid=$STARTED_PID
wait_for_block "deletion_waiter" "reservation_holder"
open_gate "reservation-first"
wait_for_session "$reservation_holder_pid" "$TEMP_DIR/reservation-holder.out" "reservation holder"
wait_for_session "$deletion_waiter_pid" "$TEMP_DIR/deletion-waiter.out" "deletion waiter"
assert_output_line "$TEMP_DIR/reservation-holder.out" "reserved" "reservation holder"
assert_output_line "$TEMP_DIR/deletion-waiter.out" "f" "deletion waiter"
assert_equal "$(sql_scalar "select count(*) from public.video_account_deletion_fences;")" "0" \
  "reservation-first fence count"

# Deletion wins the same user-row lock: reservation waits, then sees the
# committed fence and cannot create a provider claim.
reset_fixtures
sql_exec "insert into public.users(id) values ('11000000-0000-0000-0000-000000000002');"
sql_exec "insert into deletion_fence_harness.race_gates(name) values ('deletion-first');"

start_session "deletion_holder" "$TEMP_DIR/deletion-holder.out" "
  begin;
  set role service_role;
  select public.begin_video_account_deletion(
    '11000000-0000-0000-0000-000000000002',
    '31000000-0000-0000-0000-000000000002'
  );
  reset role;
  select deletion_fence_harness.wait_for_gate('deletion-first');
  commit;
"
deletion_holder_pid=$STARTED_PID
wait_for_gate_session "deletion_holder"

start_session "reservation_waiter" "$TEMP_DIR/reservation-waiter.out" "
  set statement_timeout = '45s';
  set role service_role;
  select public.reserve_video_provider_claim(
    '11000000-0000-0000-0000-000000000002',
    '21000000-0000-0000-0000-000000000002',
    'gemini',
    'extend'
  ) ->> 'status';
"
reservation_waiter_pid=$STARTED_PID
wait_for_block "reservation_waiter" "deletion_holder"
open_gate "deletion-first"
wait_for_session "$deletion_holder_pid" "$TEMP_DIR/deletion-holder.out" "deletion holder"
wait_for_session "$reservation_waiter_pid" "$TEMP_DIR/reservation-waiter.out" "reservation waiter"
assert_output_line "$TEMP_DIR/deletion-holder.out" "t" "deletion holder"
assert_output_line "$TEMP_DIR/reservation-waiter.out" "account_deleting" "reservation waiter"
assert_equal "$(sql_scalar "select count(*) from public.video_provider_start_claims;")" "0" \
  "deletion-first claim count"

# Establishment wins the shared lock order. Recovery waits, then observes the
# same token on users and must preserve both the live job and video fence.
reset_fixtures
sql_exec "
  insert into public.users(id)
  values ('11000000-0000-0000-0000-000000000008');
  set role service_role;
  select public.begin_video_account_deletion(
    '11000000-0000-0000-0000-000000000008',
    '31000000-0000-0000-0000-000000000008'
  );
  insert into public.account_deletion_jobs(
    user_id, operation_token, state, fenced_at, finalize_after,
    next_attempt_at, created_at
  ) values (
    '11000000-0000-0000-0000-000000000008',
    '31000000-0000-0000-0000-000000000008',
    'fencing', now() - interval '16 minutes', now() + interval '30 hours',
    now(), now() - interval '16 minutes'
  );
  reset role;
  insert into deletion_fence_harness.race_gates(name)
  values ('establish-before-recovery');
"

start_session "establish_holder" "$TEMP_DIR/establish-holder.out" "
  begin;
  set role service_role;
  select public.establish_account_deletion_fence(
    '11000000-0000-0000-0000-000000000008',
    '31000000-0000-0000-0000-000000000008',
    now()
  );
  reset role;
  select deletion_fence_harness.wait_for_gate('establish-before-recovery');
  commit;
"
establish_holder_pid=$STARTED_PID
wait_for_gate_session "establish_holder"

start_session "recovery_after_establish" "$TEMP_DIR/recovery-after-establish.out" "
  set statement_timeout = '45s';
  set role service_role;
  select public.recover_video_account_deletion_fence(
    '11000000-0000-0000-0000-000000000008',
    '31000000-0000-0000-0000-000000000008'
  );
"
recovery_after_establish_pid=$STARTED_PID
wait_for_block "recovery_after_establish" "establish_holder"

# The begin path takes the same user-first order. Even with a durable fence and
# claim locks held by establishment, it waits on users rather than taking a
# claim lock that could deadlock against the fence lock.
start_session "begin_after_establish" "$TEMP_DIR/begin-after-establish.out" "
  set statement_timeout = '45s';
  set role service_role;
  select public.begin_video_account_deletion(
    '11000000-0000-0000-0000-000000000008',
    '31000000-0000-0000-0000-000000000008'
  );
"
begin_after_establish_pid=$STARTED_PID
wait_for_block "begin_after_establish" "establish_holder"
open_gate "establish-before-recovery"
wait_for_session "$establish_holder_pid" "$TEMP_DIR/establish-holder.out" "establish holder"
wait_for_session "$recovery_after_establish_pid" "$TEMP_DIR/recovery-after-establish.out" \
  "recovery after establish"
wait_for_session "$begin_after_establish_pid" "$TEMP_DIR/begin-after-establish.out" \
  "begin after establish"
assert_output_line "$TEMP_DIR/establish-holder.out" "fenced" "establish-first holder"
assert_output_line "$TEMP_DIR/recovery-after-establish.out" "account_deleting" \
  "establish-first recovery"
assert_output_line "$TEMP_DIR/begin-after-establish.out" "t" \
  "same-token begin after establish"
assert_equal "$(sql_scalar "
  select count(*) from public.users
  where id = '11000000-0000-0000-0000-000000000008'
    and deleted_at is not null
    and account_deletion_token = '31000000-0000-0000-0000-000000000008';
")" "1" "establish-first users fence"
assert_equal "$(sql_scalar "
  select count(*) from public.video_account_deletion_fences
  where user_id = '11000000-0000-0000-0000-000000000008'
    and operation_token = '31000000-0000-0000-0000-000000000008'
    and deleted_at is null;
")" "1" "establish-first video fence"

# Recovery wins the same lock order. A paused establishment waits, then sees
# completed_at and cannot commit users.deleted_at after the video fence is gone.
reset_fixtures
sql_exec "
  insert into public.users(id)
  values ('11000000-0000-0000-0000-000000000009');
  set role service_role;
  select public.begin_video_account_deletion(
    '11000000-0000-0000-0000-000000000009',
    '31000000-0000-0000-0000-000000000009'
  );
  insert into public.account_deletion_jobs(
    user_id, operation_token, state, fenced_at, finalize_after,
    next_attempt_at, created_at
  ) values (
    '11000000-0000-0000-0000-000000000009',
    '31000000-0000-0000-0000-000000000009',
    'fencing', now() - interval '16 minutes', now() + interval '30 hours',
    now(), now() - interval '16 minutes'
  );
  update public.video_account_deletion_fences
  set requested_at = now() - interval '16 minutes'
  where user_id = '11000000-0000-0000-0000-000000000009';
  reset role;
  insert into deletion_fence_harness.race_gates(name)
  values ('recovery-before-establish');
"

start_session "recovery_holder" "$TEMP_DIR/recovery-holder.out" "
  begin;
  set role service_role;
  select public.recover_video_account_deletion_fence(
    '11000000-0000-0000-0000-000000000009',
    '31000000-0000-0000-0000-000000000009'
  );
  reset role;
  select deletion_fence_harness.wait_for_gate('recovery-before-establish');
  commit;
"
recovery_holder_pid=$STARTED_PID
wait_for_gate_session "recovery_holder"

start_session "establish_after_recovery" "$TEMP_DIR/establish-after-recovery.out" "
  set statement_timeout = '45s';
  set role service_role;
  select public.establish_account_deletion_fence(
    '11000000-0000-0000-0000-000000000009',
    '31000000-0000-0000-0000-000000000009',
    now()
  );
"
establish_after_recovery_pid=$STARTED_PID
wait_for_block "establish_after_recovery" "recovery_holder"
open_gate "recovery-before-establish"
wait_for_session "$recovery_holder_pid" "$TEMP_DIR/recovery-holder.out" "recovery holder"
wait_for_session "$establish_after_recovery_pid" "$TEMP_DIR/establish-after-recovery.out" \
  "establish after recovery"
assert_output_line "$TEMP_DIR/recovery-holder.out" "abandoned" "recovery-first holder"
assert_output_line "$TEMP_DIR/establish-after-recovery.out" "job_unavailable" \
  "recovery-first establish"
assert_equal "$(sql_scalar "
  select count(*) from public.users
  where id = '11000000-0000-0000-0000-000000000009'
    and deleted_at is null and account_deletion_token is null;
")" "1" "recovery-first active user"
assert_equal "$(sql_scalar "
  select count(*) from public.video_account_deletion_fences
  where user_id = '11000000-0000-0000-0000-000000000009';
")" "0" "recovery-first released fence"
assert_equal "$(sql_scalar "
  select count(*) from public.account_deletion_jobs
  where user_id = '11000000-0000-0000-0000-000000000009'
    and state = 'abandoned' and completed_at is not null;
")" "1" "recovery-first abandoned job"

# Acceptance commits first. Deletion waits on the durable claim, then cascades
# the media row while retaining the accepted provider handle.
reset_fixtures
sql_exec "
  insert into public.users(id)
  values ('11000000-0000-0000-0000-000000000003');
  insert into public.media_jobs(
    id, user_id, kind, status, provider, operation_type, provider_job_id, metadata
  ) values (
    '21000000-0000-0000-0000-000000000003',
    '11000000-0000-0000-0000-000000000003',
    'video', 'queued', 'runway', 'generate',
    'pending:21000000-0000-0000-0000-000000000003', '{}'::jsonb
  );
"
assert_equal "$(sql_scalar "
  set role service_role;
  select public.reserve_video_provider_claim(
    '11000000-0000-0000-0000-000000000003',
    '21000000-0000-0000-0000-000000000003',
    'runway', 'generate'
  ) ->> 'status';
")" "reserved" "acceptance-first reservation"
assert_equal "$(sql_scalar "
  set role service_role;
  select public.begin_video_provider_dispatch(
    '11000000-0000-0000-0000-000000000003',
    '21000000-0000-0000-0000-000000000003',
    '41000000-0000-0000-0000-000000000003'
  );
")" "t" "acceptance-first dispatch"
sql_exec "insert into deletion_fence_harness.race_gates(name) values ('acceptance-first');"

start_session "acceptance_holder" "$TEMP_DIR/acceptance-holder.out" "
  begin;
  set role service_role;
  select public.record_video_provider_acceptance(
    '11000000-0000-0000-0000-000000000003',
    '21000000-0000-0000-0000-000000000003',
    'provider-accepts-first'
  );
  reset role;
  select deletion_fence_harness.wait_for_gate('acceptance-first');
  commit;
"
acceptance_holder_pid=$STARTED_PID
wait_for_gate_session "acceptance_holder"

start_session "acceptance_delete_waiter" "$TEMP_DIR/acceptance-delete-waiter.out" "
  begin;
  set statement_timeout = '45s';
  set role service_role;
  select public.begin_video_account_deletion(
    '11000000-0000-0000-0000-000000000003',
    '31000000-0000-0000-0000-000000000003'
  );
  delete from public.users
  where id = '11000000-0000-0000-0000-000000000003';
  commit;
"
acceptance_delete_waiter_pid=$STARTED_PID
wait_for_block "acceptance_delete_waiter" "acceptance_holder"
open_gate "acceptance-first"
wait_for_session "$acceptance_holder_pid" "$TEMP_DIR/acceptance-holder.out" "acceptance holder"
wait_for_session "$acceptance_delete_waiter_pid" "$TEMP_DIR/acceptance-delete-waiter.out" \
  "acceptance delete waiter"
assert_output_line "$TEMP_DIR/acceptance-holder.out" "t" "acceptance holder"
assert_output_line "$TEMP_DIR/acceptance-delete-waiter.out" "t" "acceptance delete waiter"
assert_equal "$(sql_scalar "
  select state || ':' || provider_job_id
  from public.video_provider_start_claims
  where job_id = '21000000-0000-0000-0000-000000000003';
")" "accepted:provider-accepts-first" "acceptance-first durable claim"
assert_equal "$(sql_scalar "
  select count(*) from public.users
  where id = '11000000-0000-0000-0000-000000000003';
")" "0" "acceptance-first user deletion"
assert_equal "$(sql_scalar "
  select count(*) from public.media_jobs
  where id = '21000000-0000-0000-0000-000000000003';
")" "0" "acceptance-first media cascade"

# Deletion commits first. A concurrent provider response waits for the claim,
# then records the external handle and reports false because media was removed.
reset_fixtures
sql_exec "
  insert into public.users(id)
  values ('11000000-0000-0000-0000-000000000004');
  insert into public.media_jobs(
    id, user_id, kind, status, provider, operation_type, provider_job_id, metadata
  ) values (
    '21000000-0000-0000-0000-000000000004',
    '11000000-0000-0000-0000-000000000004',
    'video', 'queued', 'gemini', 'extend',
    'pending:21000000-0000-0000-0000-000000000004', '{}'::jsonb
  );
"
assert_equal "$(sql_scalar "
  set role service_role;
  select public.reserve_video_provider_claim(
    '11000000-0000-0000-0000-000000000004',
    '21000000-0000-0000-0000-000000000004',
    'gemini', 'extend'
  ) ->> 'status';
")" "reserved" "deletion-first acceptance reservation"
assert_equal "$(sql_scalar "
  set role service_role;
  select public.begin_video_provider_dispatch(
    '11000000-0000-0000-0000-000000000004',
    '21000000-0000-0000-0000-000000000004',
    '41000000-0000-0000-0000-000000000004'
  );
")" "t" "deletion-first acceptance dispatch"
sql_exec "insert into deletion_fence_harness.race_gates(name) values ('delete-before-acceptance');"

start_session "delete_acceptance_holder" "$TEMP_DIR/delete-acceptance-holder.out" "
  begin;
  set role service_role;
  select public.begin_video_account_deletion(
    '11000000-0000-0000-0000-000000000004',
    '31000000-0000-0000-0000-000000000004'
  );
  delete from public.users
  where id = '11000000-0000-0000-0000-000000000004';
  reset role;
  select deletion_fence_harness.wait_for_gate('delete-before-acceptance');
  commit;
"
delete_acceptance_holder_pid=$STARTED_PID
wait_for_gate_session "delete_acceptance_holder"

start_session "acceptance_waiter" "$TEMP_DIR/acceptance-waiter.out" "
  set statement_timeout = '45s';
  set role service_role;
  select public.record_video_provider_acceptance(
    '11000000-0000-0000-0000-000000000004',
    '21000000-0000-0000-0000-000000000004',
    'provider-arrives-after-delete'
  );
"
acceptance_waiter_pid=$STARTED_PID
wait_for_block "acceptance_waiter" "delete_acceptance_holder"
open_gate "delete-before-acceptance"
wait_for_session "$delete_acceptance_holder_pid" "$TEMP_DIR/delete-acceptance-holder.out" \
  "delete acceptance holder"
wait_for_session "$acceptance_waiter_pid" "$TEMP_DIR/acceptance-waiter.out" "acceptance waiter"
assert_output_line "$TEMP_DIR/delete-acceptance-holder.out" "t" "delete acceptance holder"
assert_output_line "$TEMP_DIR/acceptance-waiter.out" "f" "post-delete acceptance waiter"
assert_equal "$(sql_scalar "
  select state || ':' || provider_job_id
  from public.video_provider_start_claims
  where job_id = '21000000-0000-0000-0000-000000000004';
")" "accepted:provider-arrives-after-delete" "post-delete durable acceptance"

# A locked oldest row is skipped rather than blocking a reconciliation worker.
# Lease-token replay returns the same job, and only the owning token can release.
reset_fixtures
sql_exec "
  insert into public.video_account_deletion_fences(
    user_id, operation_token, requested_at, deleted_at
  ) values
    ('11000000-0000-0000-0000-000000000005', '31000000-0000-0000-0000-000000000005', now() - interval '5 minutes', now()),
    ('11000000-0000-0000-0000-000000000006', '31000000-0000-0000-0000-000000000006', now() - interval '4 minutes', now()),
    ('11000000-0000-0000-0000-000000000007', '31000000-0000-0000-0000-000000000007', now() - interval '3 minutes', null);
  insert into public.video_provider_start_claims(
    job_id, user_id, provider, operation_type, state, provider_job_id,
    lease_expires_at, deletion_requested_at, reconcile_after, created_at
  ) values
    ('21000000-0000-0000-0000-000000000005', '11000000-0000-0000-0000-000000000005', 'runway', 'generate', 'accepted', 'provider-job-5', now(), now(), now() - interval '5 minutes', now() - interval '5 minutes'),
    ('21000000-0000-0000-0000-000000000006', '11000000-0000-0000-0000-000000000006', 'gemini', 'extend', 'accepted', 'provider-job-6', now(), now(), now() - interval '4 minutes', now() - interval '4 minutes'),
    ('21000000-0000-0000-0000-000000000007', '11000000-0000-0000-0000-000000000007', 'runway', 'generate', 'accepted', 'provider-job-7', now(), now(), now() - interval '3 minutes', now() - interval '3 minutes');
  insert into deletion_fence_harness.race_gates(name) values ('skip-locked');
"

start_session "reconciliation_row_holder" "$TEMP_DIR/reconciliation-row-holder.out" "
  begin;
  set role service_role;
  select job_id
  from public.video_provider_start_claims
  where job_id = '21000000-0000-0000-0000-000000000005'
  for update;
  reset role;
  select deletion_fence_harness.wait_for_gate('skip-locked');
  commit;
"
reconciliation_row_holder_pid=$STARTED_PID
wait_for_gate_session "reconciliation_row_holder"

skip_locked_job="$(sql_scalar "
  set statement_timeout = '3s';
  set role service_role;
  select job_id
  from public.claim_deleted_video_provider_reconciliation(
    '51000000-0000-0000-0000-000000000006'
  );
")"
assert_equal "$skip_locked_job" "21000000-0000-0000-0000-000000000006" \
  "SKIP LOCKED second lease"

lease_replay_job="$(sql_scalar "
  set role service_role;
  select job_id
  from public.claim_deleted_video_provider_reconciliation(
    '51000000-0000-0000-0000-000000000006'
  );
")"
assert_equal "$lease_replay_job" "21000000-0000-0000-0000-000000000006" \
  "lease-token replay"

unavailable_job="$(sql_scalar "
  set statement_timeout = '3s';
  set role service_role;
  select job_id
  from public.claim_deleted_video_provider_reconciliation(
    '51000000-0000-0000-0000-000000000007'
  );
")"
assert_equal "$unavailable_job" "" \
  "live leases and a non-deleted fence must leave no claimable row"

open_gate "skip-locked"
wait_for_session "$reconciliation_row_holder_pid" "$TEMP_DIR/reconciliation-row-holder.out" \
  "reconciliation row holder"

oldest_job="$(sql_scalar "
  set role service_role;
  select job_id
  from public.claim_deleted_video_provider_reconciliation(
    '51000000-0000-0000-0000-000000000005'
  );
")"
assert_equal "$oldest_job" "21000000-0000-0000-0000-000000000005" \
  "oldest row after lock release"
assert_equal "$(sql_scalar "
  select count(*)
  from public.video_provider_start_claims
  where job_id in (
      '21000000-0000-0000-0000-000000000005',
      '21000000-0000-0000-0000-000000000006'
    )
    and reconcile_attempt_count = 1
    and reconcile_lease_expires_at >= now() + interval '3 minutes 45 seconds'
    and reconcile_lease_expires_at <= now() + interval '4 minutes 5 seconds';
")" "2" "initial reconciliation lease duration and attempts"

sql_exec "
  update public.video_provider_start_claims
  set reconcile_lease_expires_at = now() - interval '1 second'
  where job_id = '21000000-0000-0000-0000-000000000005';
"
reclaimed_job="$(sql_scalar "
  set role service_role;
  select job_id
  from public.claim_deleted_video_provider_reconciliation(
    '51000000-0000-0000-0000-000000000008'
  );
")"
assert_equal "$reclaimed_job" "21000000-0000-0000-0000-000000000005" \
  "expired reconciliation lease reclaim"

stale_release="$(sql_scalar "
  set role service_role;
  select public.release_deleted_video_provider_reconciliation(
    '21000000-0000-0000-0000-000000000005',
    '51000000-0000-0000-0000-000000000005',
    'settled',
    0
  );
")"
assert_equal "$stale_release" "f" "stale reconciliation lease release"

reclaimed_release="$(sql_scalar "
  set role service_role;
  select public.release_deleted_video_provider_reconciliation(
    '21000000-0000-0000-0000-000000000005',
    '51000000-0000-0000-0000-000000000008',
    'settled',
    0
  );
")"
assert_equal "$reclaimed_release" "t" "reclaimed reconciliation lease release"

wrong_release="$(sql_scalar "
  set role service_role;
  select public.release_deleted_video_provider_reconciliation(
    '21000000-0000-0000-0000-000000000006',
    '51000000-0000-0000-0000-000000000005',
    'settled',
    0
  );
")"
assert_equal "$wrong_release" "f" "wrong reconciliation lease release"

right_release="$(sql_scalar "
  set role service_role;
  select public.release_deleted_video_provider_reconciliation(
    '21000000-0000-0000-0000-000000000006',
    '51000000-0000-0000-0000-000000000006',
    'settled',
    0
  );
")"
assert_equal "$right_release" "t" "owned reconciliation lease release"
assert_equal "$(sql_scalar "
  select count(*) filter (
      where job_id = '21000000-0000-0000-0000-000000000005'
        and reconcile_attempt_count = 2
    )
    || ':'
    || count(*) filter (
      where job_id = '21000000-0000-0000-0000-000000000006'
        and reconcile_attempt_count = 1
    )
    || ':'
    || count(*) filter (
      where job_id = '21000000-0000-0000-0000-000000000007'
        and reconcile_attempt_count = 0
    )
  from public.video_provider_start_claims
  where job_id in (
    '21000000-0000-0000-0000-000000000005',
    '21000000-0000-0000-0000-000000000006',
    '21000000-0000-0000-0000-000000000007'
  );
")" "1:1:1" "reconciliation attempt counts"
assert_equal "$(sql_scalar "
  select count(*)
  from public.video_provider_start_claims
  where job_id = '21000000-0000-0000-0000-000000000006'
    and state = 'settled'
    and reconcile_lease_token is null
    and reconcile_after >= now() + interval '55 seconds';
")" "1" "released lease delay floor"

final_unavailable_job="$(sql_scalar "
  set role service_role;
  select job_id
  from public.claim_deleted_video_provider_reconciliation(
    '51000000-0000-0000-0000-000000000009'
  );
")"
assert_equal "$final_unavailable_job" "" \
  "settled rows and a non-deleted fence must remain ineligible"

echo "Real PostgreSQL deletion-fence verification passed."
