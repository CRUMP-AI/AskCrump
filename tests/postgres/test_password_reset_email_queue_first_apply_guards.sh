#!/usr/bin/env bash
set -euo pipefail

migration='migrations/20261024163849_durable_password_reset_email_jobs.sql'
result_dir="$(mktemp -d)"

cleanup() {
  set +e
  psql -X --set=ON_ERROR_STOP=0 \
    --command='alter table if exists public.users alter column is_guest set default false' \
    --command='alter table if exists public.users alter column password_reset_token_hash drop default' \
    --command='alter table if exists public.users alter column password_reset_expires drop default' \
    --command='alter table if exists public.users alter column updated_at drop not null' \
    --command='alter table if exists public.users alter column updated_at set default now()' \
    --command='alter default privileges for role postgres in schema public revoke execute on functions from reset_queue_default_intruder' \
    --command='revoke service_role from anon' \
    --command='revoke execute on function public.consume_password_reset_v1(text,text) from authenticated' \
    --command='revoke execute on function public.consume_password_reset_v1(text,text) from reset_consumer_intruder' \
    --command='drop index if exists public.password_reset_email_jobs_ready_idx' \
    --command='drop table if exists public.password_reset_index_collision_source' \
    --command='drop schema if exists reset_queue_hostile cascade' \
    --command='drop role if exists reset_consumer_intruder' \
    --command='drop role if exists reset_queue_default_intruder' >/dev/null 2>&1
  rm -rf -- "$result_dir"
}
trap cleanup EXIT

assert_absent() {
  psql -X --set=ON_ERROR_STOP=1 --tuples-only --no-align \
    --command="select to_regclass('public.password_reset_email_jobs') is null and to_regprocedure('public.enqueue_password_reset_email_job_v1(uuid,text,text,text,timestamp with time zone,text,text,text,text,text,text,text)') is null and to_regprocedure('public.claim_password_reset_email_job_v1(uuid,integer)') is null and to_regprocedure('public.stage_password_reset_email_job_v1(uuid,uuid)') is null and to_regprocedure('public.complete_password_reset_email_job_v1(uuid,uuid,text)') is null and to_regprocedure('public.release_password_reset_email_job_v1(uuid,uuid,text,boolean,integer)') is null" \
    | grep -Fx 't'
}

assert_rejected() {
  local case_name="$1"
  local mutation_sql="$2"
  local restore_sql="$3"
  local expected="$4"
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
    echo "Migration unexpectedly accepted first-apply drift: $case_name." >&2
    exit 1
  fi
  grep -F '55000' "$log_file"
  grep -F "$expected" "$log_file"
  assert_absent
  psql -X --set=ON_ERROR_STOP=1 --command="$restore_sql"
}

# Production permits updated_at to be nullable while clean bootstrap may make
# it NOT NULL. Both exact variants must apply and roll back cleanly.
psql -X --set=ON_ERROR_STOP=1 \
  --command='begin' \
  --command='alter table public.users alter column updated_at set not null' \
  --file="$migration" \
  --command='rollback'
assert_absent

assert_rejected \
  'is-guest-default-true' \
  'alter table public.users alter column is_guest set default true' \
  'alter table public.users alter column is_guest set default false' \
  'unexpected users password-reset columns.'
assert_rejected \
  'reset-token-default' \
  "alter table public.users alter column password_reset_token_hash set default 'unexpected'::text" \
  'alter table public.users alter column password_reset_token_hash drop default' \
  'unexpected users password-reset columns.'
assert_rejected \
  'reset-expiry-default' \
  'alter table public.users alter column password_reset_expires set default now()' \
  'alter table public.users alter column password_reset_expires drop default' \
  'unexpected users password-reset columns.'
assert_rejected \
  'updated-at-default' \
  'alter table public.users alter column updated_at set default pg_catalog.clock_timestamp()' \
  'alter table public.users alter column updated_at set default now()' \
  'unexpected users password-reset columns.'

assert_rejected \
  'reset-index-shape' \
  'drop index public.users_password_reset_token_hash_unique; create unique index users_password_reset_token_hash_unique on public.users(password_reset_token_hash)' \
  'drop index public.users_password_reset_token_hash_unique; create unique index users_password_reset_token_hash_unique on public.users(password_reset_token_hash) where password_reset_token_hash is not null' \
  'password-reset unique index drifted; refusing queue migration.'

assert_rejected \
  'atomic-consumer-acl' \
  'grant execute on function public.consume_password_reset_v1(text,text) to authenticated' \
  'revoke execute on function public.consume_password_reset_v1(text,text) from authenticated' \
  'atomic password-reset consumer drifted; refusing queue migration.'
assert_rejected \
  'atomic-consumer-arbitrary-acl' \
  'create role reset_consumer_intruder nologin; grant execute on function public.consume_password_reset_v1(text,text) to reset_consumer_intruder' \
  'revoke execute on function public.consume_password_reset_v1(text,text) from reset_consumer_intruder; drop role reset_consumer_intruder' \
  'atomic password-reset consumer drifted; refusing queue migration.'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create schema reset_queue_hostile' \
  --command='create domain reset_queue_hostile.text as integer' \
  --command='create domain reset_queue_hostile.uuid as integer' \
  --command='create domain reset_queue_hostile.timestamptz as integer'
psql -X --set=ON_ERROR_STOP=1 \
  --command='begin' \
  --command='set search_path=reset_queue_hostile,pg_catalog,public' \
  --file="$migration" \
  --command='rollback'
assert_absent
psql -X --set=ON_ERROR_STOP=1 --command='drop schema reset_queue_hostile cascade'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create table public.password_reset_index_collision_source(id timestamptz)' \
  --command='create index password_reset_email_jobs_ready_idx on public.password_reset_index_collision_source(id)'
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
grep -F 'password-reset-email queue index contract is incomplete.' "$result_dir/index-collision.log"
assert_absent
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop index public.password_reset_email_jobs_ready_idx' \
  --command='drop table public.password_reset_index_collision_source'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create role reset_queue_default_intruder nologin' \
  --command='alter default privileges for role postgres in schema public grant execute on functions to reset_queue_default_intruder'
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
grep -F 'password-reset-email queue RPC postflight failed:' "$result_dir/default-acl.log"
assert_absent
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter default privileges for role postgres in schema public revoke execute on functions from reset_queue_default_intruder' \
  --command='drop role reset_queue_default_intruder'

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
grep -F 'password-reset-email queue RPC postflight failed:' "$result_dir/inherited-execute.log"
assert_absent
psql -X --set=ON_ERROR_STOP=1 --command='revoke service_role from anon'

echo 'Password-reset-email queue first-apply guards passed.'
