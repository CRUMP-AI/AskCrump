#!/usr/bin/env bash
set -euo pipefail

migration='migrations/20261024144202_durable_verification_email_jobs.sql'
result_dir="$(mktemp -d)"

cleanup() {
  set +e
  psql -X --set=ON_ERROR_STOP=0 \
    --command='alter table if exists public.users alter column is_verified drop not null' \
    --command='alter table if exists public.users alter column is_verified set default false' \
    --command='alter table if exists public.users alter column updated_at drop not null' \
    --command='alter table if exists public.users alter column updated_at set default now()' \
    --command='alter default privileges for role postgres in schema public revoke execute on functions from queue_default_intruder' \
    --command='revoke service_role from anon' \
    --command='drop index if exists public.verification_email_jobs_ready_idx' \
    --command='drop table if exists public.verification_email_index_collision_source' \
    --command='drop schema if exists queue_hostile cascade' \
    --command='drop role if exists queue_default_intruder' >/dev/null 2>&1
  rm -rf -- "$result_dir"
}
trap cleanup EXIT

assert_absent() {
  psql -X --set=ON_ERROR_STOP=1 --tuples-only --no-align \
    --command="select to_regclass('public.verification_email_jobs') is null and to_regprocedure('public.enqueue_verification_email_job_v1(uuid,text,text,text,timestamp with time zone,text,text,text,text,text,text,text,text,text)') is null" \
    | grep -Fx 't'
}

assert_users_contract_rejected() {
  local case_name="$1"
  local mutation_sql="$2"
  local restore_sql="$3"
  local log_file="$result_dir/${case_name}.log"
  local status

  psql -X --set=ON_ERROR_STOP=1 --command="$mutation_sql"

  set +e
  psql -X --set=ON_ERROR_STOP=1 --set=VERBOSITY=verbose \
    --single-transaction --file="$migration" >"$log_file" 2>&1
  status=$?
  set -e
  cat "$log_file"
  if [ "$status" -eq 0 ]; then
    echo "Migration unexpectedly accepted users schema drift: $case_name." >&2
    exit 1
  fi
  grep -F '55000' "$log_file"
  grep -F 'unexpected users verification columns.' "$log_file"
  assert_absent

  psql -X --set=ON_ERROR_STOP=1 --command="$restore_sql"
}

# Fresh/bootstrap databases may already enforce the two verification columns as
# NOT NULL. Prove that exact-default variant applies, then rolls back cleanly.
psql -X --set=ON_ERROR_STOP=1 \
  --command='begin' \
  --command='alter table public.users alter column is_verified set not null' \
  --command='alter table public.users alter column updated_at set not null' \
  --file="$migration" \
  --command='rollback'
assert_absent

assert_users_contract_rejected \
  'is-verified-default-true' \
  'alter table public.users alter column is_verified set default true' \
  'alter table public.users alter column is_verified set default false'
assert_users_contract_rejected \
  'is-verified-default-absent' \
  'alter table public.users alter column is_verified drop default' \
  'alter table public.users alter column is_verified set default false'
assert_users_contract_rejected \
  'updated-at-default-clock-timestamp' \
  'alter table public.users alter column updated_at set default pg_catalog.clock_timestamp()' \
  'alter table public.users alter column updated_at set default now()'
assert_users_contract_rejected \
  'updated-at-default-absent' \
  'alter table public.users alter column updated_at drop default' \
  'alter table public.users alter column updated_at set default now()'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create schema queue_hostile' \
  --command='create domain queue_hostile.text as integer' \
  --command='create domain queue_hostile.uuid as integer' \
  --command='create domain queue_hostile.timestamptz as integer'
psql -X --set=ON_ERROR_STOP=1 \
  --command='begin' \
  --command='set search_path=queue_hostile,pg_catalog,public' \
  --file="$migration" \
  --command='rollback'
assert_absent
psql -X --set=ON_ERROR_STOP=1 --command='drop schema queue_hostile cascade'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create table public.verification_email_index_collision_source(id timestamptz)' \
  --command='create index verification_email_jobs_ready_idx on public.verification_email_index_collision_source(id)'

set +e
psql -X --set=ON_ERROR_STOP=1 --set=VERBOSITY=verbose \
  --single-transaction --file="$migration" >"$result_dir/index-collision.log" 2>&1
status=$?
set -e
cat "$result_dir/index-collision.log"
if [ "$status" -eq 0 ]; then
  echo 'Migration unexpectedly accepted a first-apply index-name collision.' >&2
  exit 1
fi
grep -F '55000' "$result_dir/index-collision.log"
grep -F 'verification-email queue index contract is incomplete.' "$result_dir/index-collision.log"
assert_absent

psql -X --set=ON_ERROR_STOP=1 \
  --command='drop index public.verification_email_jobs_ready_idx' \
  --command='drop table public.verification_email_index_collision_source'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create role queue_default_intruder nologin' \
  --command='alter default privileges for role postgres in schema public grant execute on functions to queue_default_intruder'

set +e
psql -X --set=ON_ERROR_STOP=1 --set=VERBOSITY=verbose \
  --single-transaction --file="$migration" >"$result_dir/default-acl.log" 2>&1
status=$?
set -e
cat "$result_dir/default-acl.log"
if [ "$status" -eq 0 ]; then
  echo 'Migration unexpectedly accepted a first-apply default function ACL.' >&2
  exit 1
fi
grep -F '55000' "$result_dir/default-acl.log"
grep -F 'verification-email queue RPC postflight failed:' "$result_dir/default-acl.log"
assert_absent

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter default privileges for role postgres in schema public revoke execute on functions from queue_default_intruder' \
  --command='drop role queue_default_intruder'

psql -X --set=ON_ERROR_STOP=1 --command='grant service_role to anon'

set +e
psql -X --set=ON_ERROR_STOP=1 --set=VERBOSITY=verbose \
  --single-transaction --file="$migration" >"$result_dir/inherited-execute.log" 2>&1
status=$?
set -e
cat "$result_dir/inherited-execute.log"
if [ "$status" -eq 0 ]; then
  echo 'Migration unexpectedly accepted inherited anonymous RPC execution.' >&2
  exit 1
fi
grep -F '55000' "$result_dir/inherited-execute.log"
grep -F 'verification-email queue RPC postflight failed:' "$result_dir/inherited-execute.log"
assert_absent

psql -X --set=ON_ERROR_STOP=1 --command='revoke service_role from anon'

echo 'Verification-email queue first-apply guards passed.'
