#!/usr/bin/env bash
set -euo pipefail

migration='migrations/20261024210302_queue_backlog_observability.sql'
verification_migration='migrations/20261024144202_durable_verification_email_jobs.sql'
result_dir="$(mktemp -d)"
trap 'rm -rf -- "$result_dir"' EXIT

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
    echo "Migration unexpectedly accepted ${label} drift." >&2
    exit 1
  fi
  grep -F '55000' "$output"
  grep -F "$expected" "$output"
}

reapply() {
  psql -X --set=ON_ERROR_STOP=1 --single-transaction --file="$migration"
}

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs alter column attempts drop default'
assert_refused verification-column 'verification_email_jobs backlog column drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs alter column attempts set default 0'
reapply

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.password_reset_email_jobs drop constraint password_reset_email_jobs_support_email_check'
assert_refused password-constraint 'password_reset_email_jobs backlog constraint drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.password_reset_email_jobs add constraint password_reset_email_jobs_support_email_check check (length(support_email) between 3 and 320)'
reapply

psql -X --set=ON_ERROR_STOP=1 \
  --command="drop index public.verification_email_jobs_ready_idx; create index verification_email_jobs_ready_idx on public.verification_email_jobs(created_at, next_attempt_at, id) where status = 'queued'"
assert_refused verification-index 'verification_email_jobs backlog index drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command="drop index public.verification_email_jobs_ready_idx; create index verification_email_jobs_ready_idx on public.verification_email_jobs(next_attempt_at, created_at, id) where status = 'queued'"
reapply

psql -X --set=ON_ERROR_STOP=1 \
  --command='grant select on public.password_reset_email_jobs to service_role'
assert_refused table-acl 'password_reset_email_jobs backlog prerequisite drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke select on public.password_reset_email_jobs from service_role'
reapply

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs no force row level security'
assert_refused forced-rls 'verification_email_jobs backlog prerequisite drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs force row level security'
reapply

psql -X --set=ON_ERROR_STOP=1 \
  --command='create policy queue_backlog_intruder on public.password_reset_email_jobs for select to service_role using (true)'
assert_refused policy 'password_reset_email_jobs backlog ACL, policy, trigger, or rule drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop policy queue_backlog_intruder on public.password_reset_email_jobs'
reapply

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
select pg_catalog.replace(
  pg_catalog.pg_get_functiondef(
    'public.claim_password_reset_email_job_v1(uuid,integer)'::regprocedure
  ),
  'DEFAULT 120',
  'DEFAULT 121'
) \gexec
SQL
assert_refused claim-default 'email queue backlog claim prerequisite drifted:'
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
select pg_catalog.replace(
  pg_catalog.pg_get_functiondef(
    'public.claim_password_reset_email_job_v1(uuid,integer)'::regprocedure
  ),
  'DEFAULT 121',
  'DEFAULT 120'
) \gexec
SQL
reapply

psql -X --set=ON_ERROR_STOP=1 \
  --file=tests/postgres/verification_email_queue_source_drift_fixture.sql
assert_refused claim-source 'email queue backlog claim prerequisite drifted:'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop function public.claim_verification_email_job_v1(uuid,integer)'
psql -X --set=ON_ERROR_STOP=1 --single-transaction \
  --file="$verification_migration"
reapply

psql -X --set=ON_ERROR_STOP=1 \
  --command='create role queue_backlog_rpc_intruder nologin' \
  --command='grant execute on function public.read_email_queue_backlog_v1() to queue_backlog_rpc_intruder'
assert_refused rpc-acl 'existing email queue backlog RPC drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke execute on function public.read_email_queue_backlog_v1() from queue_backlog_rpc_intruder' \
  --command='drop role queue_backlog_rpc_intruder'
reapply

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
create or replace function public.read_email_queue_backlog_v1()
returns table (
  verification_active_depth bigint,
  verification_eligible_depth bigint,
  verification_oldest_eligible_job_age_seconds bigint,
  password_reset_active_depth bigint,
  password_reset_eligible_depth bigint,
  password_reset_oldest_eligible_job_age_seconds bigint
)
language sql stable security definer set search_path = ''
as $$
  -- ASK_CRUMP_EMAIL_QUEUE_BACKLOG_V1
  select 0::bigint, 0::bigint, null::bigint,
         0::bigint, 0::bigint, null::bigint;
$$;
SQL
assert_refused rpc-source 'existing email queue backlog RPC drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop function public.read_email_queue_backlog_v1()'
reapply

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
drop function public.read_email_queue_backlog_v1();
create function public.read_email_queue_backlog_v1()
returns bigint language sql stable security definer set search_path = ''
as $$ select 0::bigint $$;
SQL
assert_refused rpc-result 'existing email queue backlog RPC drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop function public.read_email_queue_backlog_v1()'
reapply

psql -X --set=ON_ERROR_STOP=1 \
  --command='create function public.read_email_queue_backlog_v1(integer) returns bigint language sql stable as $$ select 0::bigint $$'
assert_refused rpc-overload 'unexpected email queue backlog RPC overload.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop function public.read_email_queue_backlog_v1(integer)'
reapply

psql -X --set=ON_ERROR_STOP=1 \
  --command='create table public.read_email_queue_backlog_v1(id integer)'
assert_refused relation-collision 'email queue backlog relation-name collision.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop table public.read_email_queue_backlog_v1'
reapply

echo 'Queue backlog observability drift refusals passed.'
