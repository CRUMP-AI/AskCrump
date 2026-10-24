#!/usr/bin/env bash
set -euo pipefail

migration='migrations/20261024210302_queue_backlog_observability.sql'
result_dir="$(mktemp -d)"

cleanup() {
  set +e
  psql -X --set=ON_ERROR_STOP=0 \
    --command='revoke service_role from anon' \
    --command='alter default privileges for role postgres in schema public revoke execute on functions from queue_backlog_default_intruder' \
    --command='drop function if exists public.read_email_queue_backlog_v1(integer)' \
    --command='drop function if exists public.read_email_queue_backlog_v1()' \
    --command='drop table if exists public.read_email_queue_backlog_v1' \
    --command='drop schema if exists queue_backlog_apply_hostile cascade' \
    --command='drop role if exists queue_backlog_default_intruder' >/dev/null 2>&1
  rm -rf -- "$result_dir"
}
trap cleanup EXIT

assert_absent() {
  psql -X -qAt --set=ON_ERROR_STOP=1 \
    --command="select to_regprocedure('public.read_email_queue_backlog_v1()') is null" \
    | grep -Fx 't'
}

assert_refused() {
  local label="$1"
  local expected="$2"
  local output="$result_dir/${label}.log"
  local status
  set +e
  psql -X --set=ON_ERROR_STOP=1 --set=VERBOSITY=verbose \
    --single-transaction --file="$migration" >"$output" 2>&1
  status=$?
  set -e
  cat "$output"
  if [ "$status" -eq 0 ]; then
    echo "Migration unexpectedly accepted first-apply case ${label}." >&2
    exit 1
  fi
  grep -F '55000' "$output"
  grep -F "$expected" "$output"
}

psql -X --set=ON_ERROR_STOP=1 \
  --command='begin' --file="$migration" --command='rollback'
assert_absent

psql -X --set=ON_ERROR_STOP=1 \
  --command='create table public.read_email_queue_backlog_v1(id integer)'
assert_refused relation-collision 'email queue backlog relation-name collision.'
assert_absent
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop table public.read_email_queue_backlog_v1'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create function public.read_email_queue_backlog_v1(integer) returns bigint language sql stable as $$ select 0::bigint $$'
assert_refused overload 'unexpected email queue backlog RPC overload.'
assert_absent
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop function public.read_email_queue_backlog_v1(integer)'

psql -X --set=ON_ERROR_STOP=1 \
  --command="create function public.read_email_queue_backlog_v1() returns bigint language sql stable security definer set search_path = '' as \$\$ select 0::bigint \$\$"
assert_refused wrong-result 'existing email queue backlog RPC drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop function public.read_email_queue_backlog_v1()'
assert_absent

psql -X --set=ON_ERROR_STOP=1 --command='grant service_role to anon'
assert_refused inherited-execute 'email queue backlog claim prerequisite drifted:'
assert_absent
psql -X --set=ON_ERROR_STOP=1 --command='revoke service_role from anon'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create role queue_backlog_default_intruder nologin' \
  --command='alter default privileges for role postgres in schema public grant execute on functions to queue_backlog_default_intruder'
assert_refused default-acl 'email queue backlog RPC postflight failed.'
assert_absent
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter default privileges for role postgres in schema public revoke execute on functions from queue_backlog_default_intruder' \
  --command='drop role queue_backlog_default_intruder'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create schema queue_backlog_apply_hostile' \
  --command='create domain queue_backlog_apply_hostile.text as integer' \
  --command='create domain queue_backlog_apply_hostile.uuid as integer' \
  --command='create domain queue_backlog_apply_hostile.timestamptz as integer'
psql -X --set=ON_ERROR_STOP=1 \
  --command='begin' \
  --command='set local search_path=queue_backlog_apply_hostile,pg_catalog,public' \
  --file="$migration" \
  --command='rollback'
assert_absent
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop schema queue_backlog_apply_hostile cascade'

echo 'Queue backlog observability first-apply guards passed.'
