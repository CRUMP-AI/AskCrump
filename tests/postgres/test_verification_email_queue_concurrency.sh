#!/usr/bin/env bash
set -euo pipefail

result_dir="$(mktemp -d)"
trap 'rm -rf -- "$result_dir"' EXIT

wait_for_advisory_count() {
  local class_id="$1"
  local granted="$2"
  local minimum="$3"
  local count
  for _ in $(seq 1 200); do
    count="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_locks where locktype = 'advisory' and database = (select oid from pg_catalog.pg_database where datname = pg_catalog.current_database()) and classid = '${class_id}'::oid and granted is ${granted};")"
    if [ "$count" -ge "$minimum" ]; then
      return 0
    fi
    sleep 0.05
  done
  echo "Timed out waiting for advisory class ${class_id} granted=${granted} count >= ${minimum}." >&2
  return 1
}

terminate_advisory_holder() {
  local class_id="$1"
  local backend_pid
  backend_pid="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select pid from pg_catalog.pg_locks where locktype = 'advisory' and database = (select oid from pg_catalog.pg_database where datname = pg_catalog.current_database()) and classid = '${class_id}'::oid and granted is true order by pid limit 1;")"
  if [ -z "$backend_pid" ]; then
    echo "No advisory holder found for class ${class_id}." >&2
    return 1
  fi
  psql -X -qAt --set=ON_ERROR_STOP=1 \
    --command="select pg_catalog.pg_terminate_backend(${backend_pid});" | grep -Fx 't'
}

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
truncate table public.verification_email_jobs;
delete from public.users;
insert into public.users (
  id, email, is_verified, verification_token_hash, verification_token_expires
) values
  ('71000000-0000-4000-8000-000000000001', 'queue-race-a@example.test', false, repeat('a', 64), clock_timestamp() + interval '20 hours'),
  ('71000000-0000-4000-8000-000000000002', 'queue-race-b@example.test', false, repeat('b', 64), clock_timestamp() + interval '20 hours');
SQL

# Hold the same advisory key so both identical enqueue attempts wait together.
psql -X --set=ON_ERROR_STOP=1 >"$result_dir/enqueue-gate.log" <<'SQL' &
select pg_advisory_lock(1179014991, hashtext('72000000-0000-4000-8000-000000000001'));
select pg_sleep(30);
SQL
gate_pid=$!
wait_for_advisory_count 1179014991 true 1

enqueue_sql="set role service_role; select accepted::text || '|' || job_id::text from public.enqueue_verification_email_job_v1('72000000-0000-4000-8000-000000000001', 'queue-race-a@example.test', repeat('1', 64), repeat('c', 64), clock_timestamp() + interval '24 hours', 'k1', 'queue_race_nonce_123456', null, null, 'verification-v1', 'Ask Crump', 'https://www.askcrump.com', 'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>');"
psql -X -qAt --set=ON_ERROR_STOP=1 --command="$enqueue_sql" >"$result_dir/enqueue-a" &
enqueue_a_pid=$!
psql -X -qAt --set=ON_ERROR_STOP=1 --command="$enqueue_sql" >"$result_dir/enqueue-b" &
enqueue_b_pid=$!
wait_for_advisory_count 1179014991 false 2
terminate_advisory_holder 1179014991
wait "$gate_pid" || true
wait "$enqueue_a_pid"
wait "$enqueue_b_pid"

expected_enqueue='true|72000000-0000-4000-8000-000000000001'
for output in "$result_dir/enqueue-a" "$result_dir/enqueue-b"; do
  if [ "$(tr -d '\r\n[:space:]' <"$output")" != "$expected_enqueue" ]; then
    echo "Concurrent enqueue did not return the one stable job." >&2
    cat "$output" >&2
    exit 1
  fi
done

psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select * from public.enqueue_verification_email_job_v1('72000000-0000-4000-8000-000000000002', 'queue-race-b@example.test', repeat('2', 64), repeat('d', 64), clock_timestamp() + interval '24 hours', 'k1', 'queue_race_nonce_234567', null, null, 'verification-v1', 'Ask Crump', 'https://www.askcrump.com', 'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>');" >/dev/null

# Retrying one claim token concurrently must converge on one lease instead of
# raising a unique-index conflict or consuming two jobs.
psql -X --set=ON_ERROR_STOP=1 >"$result_dir/claim-gate.log" <<'SQL' &
select pg_advisory_lock(1179014992, hashtext('73000000-0000-4000-8000-000000000000'));
select pg_sleep(30);
SQL
claim_gate_pid=$!
wait_for_advisory_count 1179014992 true 1

same_claim_sql="set role service_role; select job_id::text || '|' || lease_token::text from public.claim_verification_email_job_v1('73000000-0000-4000-8000-000000000000', 60);"
psql -X -qAt --set=ON_ERROR_STOP=1 --command="$same_claim_sql" >"$result_dir/claim-same-a" &
claim_same_a_pid=$!
psql -X -qAt --set=ON_ERROR_STOP=1 --command="$same_claim_sql" >"$result_dir/claim-same-b" &
claim_same_b_pid=$!
wait_for_advisory_count 1179014992 false 2
terminate_advisory_holder 1179014992
wait "$claim_gate_pid" || true
wait "$claim_same_a_pid"
wait "$claim_same_b_pid"

same_claim_a="$(tr -d '\r\n[:space:]' <"$result_dir/claim-same-a")"
same_claim_b="$(tr -d '\r\n[:space:]' <"$result_dir/claim-same-b")"
if [ -z "$same_claim_a" ] || [ "$same_claim_a" != "$same_claim_b" ]; then
  echo 'Concurrent retries of one claim token did not converge.' >&2
  cat "$result_dir/claim-same-a" "$result_dir/claim-same-b" >&2
  exit 1
fi
same_job="${same_claim_a%%|*}"
same_lease="${same_claim_a##*|}"
if [ "$same_lease" != '73000000-0000-4000-8000-000000000000' ]; then
  echo 'Same-token claim returned an unexpected lease token.' >&2
  exit 1
fi
psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select disposition from public.stage_verification_email_job_v1('$same_job', '$same_lease');" | grep -Fx 'deliver'
psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select public.complete_verification_email_job_v1('$same_job', '$same_lease', 'provider_accepted');" | grep -Fx 'provider_accepted'

psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select * from public.enqueue_verification_email_job_v1('72000000-0000-4000-8000-000000000003', 'queue-race-a@example.test', repeat('3', 64), repeat('e', 64), clock_timestamp() + interval '24 hours', 'k1', 'queue_race_nonce_345678', null, null, 'verification-v1', 'Ask Crump', 'https://www.askcrump.com', 'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>');" >/dev/null

# Two workers must claim distinct ready rows via SKIP LOCKED.
psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select job_id::text || '|' || lease_token::text from public.claim_verification_email_job_v1('73000000-0000-4000-8000-000000000001', 60);" >"$result_dir/claim-a" &
claim_a_pid=$!
psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select job_id::text || '|' || lease_token::text from public.claim_verification_email_job_v1('73000000-0000-4000-8000-000000000002', 60);" >"$result_dir/claim-b" &
claim_b_pid=$!
wait "$claim_a_pid"
wait "$claim_b_pid"

if [ "$(cut -d'|' -f1 "$result_dir/claim-a" "$result_dir/claim-b" | sort -u | wc -l | tr -d ' ')" != '2' ]; then
  echo 'Concurrent workers did not claim distinct jobs.' >&2
  cat "$result_dir/claim-a" "$result_dir/claim-b" >&2
  exit 1
fi

old_job="$(cut -d'|' -f1 "$result_dir/claim-a" | tr -d '\r\n')"
old_lease="$(cut -d'|' -f2 "$result_dir/claim-a" | tr -d '\r\n')"
psql -X --set=ON_ERROR_STOP=1 --command="update public.verification_email_jobs set lease_expires_at = clock_timestamp() - interval '1 second' where id = '$old_job'::uuid and lease_token = '$old_lease'::uuid"
expired_retry="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select job_id::text from public.claim_verification_email_job_v1('$old_lease', 60);" | tr -d '\r\n[:space:]')"
if [ -n "$expired_retry" ]; then
  echo 'Expired claim token was incorrectly renewed.' >&2
  exit 1
fi
new_claim="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select job_id::text || '|' || lease_token::text from public.claim_verification_email_job_v1('73000000-0000-4000-8000-000000000003', 60);")"
new_job="$(printf '%s' "$new_claim" | cut -d'|' -f1 | tr -d '\r\n')"
new_lease="$(printf '%s' "$new_claim" | cut -d'|' -f2 | tr -d '\r\n')"

if [ "$new_job" != "$old_job" ]; then
  echo 'Expired lease was not reclaimed.' >&2
  exit 1
fi
psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select * from public.enqueue_verification_email_job_v1('72000000-0000-4000-8000-000000000004', 'queue-race-a@example.test', repeat('4', 64), repeat('f', 64), clock_timestamp() + interval '24 hours', 'k1', 'queue_race_nonce_456789', null, null, 'verification-v1', 'Ask Crump', 'https://www.askcrump.com', 'askcrump@gmail.com', 'Ask Crump <noreply@askcrump.com>');" >/dev/null
expired_retry_after_reclaim="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select job_id::text from public.claim_verification_email_job_v1('$old_lease', 60);" | tr -d '\r\n[:space:]')"
if [ -n "$expired_retry_after_reclaim" ]; then
  echo 'Expired claim token consumed another job after fresh reclaim.' >&2
  exit 1
fi
old_outcome="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select public.complete_verification_email_job_v1('$old_job', '$old_lease', 'provider_accepted');" | tr -d '\r\n[:space:]')"
if [ "$old_outcome" != 'lease_lost' ]; then
  echo "Stale lease was not fenced: $old_outcome" >&2
  exit 1
fi
psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select disposition from public.stage_verification_email_job_v1('$new_job', '$new_lease');" | grep -Fx 'deliver'
psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select public.complete_verification_email_job_v1('$new_job', '$new_lease', 'provider_accepted');" | grep -Fx 'provider_accepted'
completed_retry="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select job_id::text from public.claim_verification_email_job_v1('$new_lease', 60);" | tr -d '\r\n[:space:]')"
if [ -n "$completed_retry" ]; then
  echo 'Completed claim token consumed another job.' >&2
  exit 1
fi

echo 'Verification-email queue concurrency and lease fencing passed.'
