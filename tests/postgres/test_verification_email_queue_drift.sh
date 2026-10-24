#!/usr/bin/env bash
set -euo pipefail

migration='migrations/20261024144202_durable_verification_email_jobs.sql'
result_dir="$(mktemp -d)"
trap 'rm -rf -- "$result_dir"' EXIT

assert_refused() {
  local label="$1"
  local expected="$2"
  local output="$result_dir/${label}.log"
  set +e
  psql -X --set=ON_ERROR_STOP=1 --set=VERBOSITY=verbose \
    --single-transaction --file="$migration" >"$output" 2>&1
  local status=$?
  set -e
  cat "$output"
  if [ "$status" -eq 0 ]; then
    echo "Migration unexpectedly accepted ${label} drift." >&2
    exit 1
  fi
  grep -F '55000' "$output"
  grep -F "$expected" "$output"
}

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs alter column attempts drop default'
assert_refused column 'verification_email_jobs column shape drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs alter column attempts set default 0'

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs set unlogged'
assert_refused persistence 'verification_email_jobs drifted; refusing replacement.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs set logged'

psql -X --set=ON_ERROR_STOP=1 \
  --command='comment on table public.verification_email_jobs is null'
assert_refused table-marker 'verification_email_jobs drifted; refusing replacement.'
psql -X --set=ON_ERROR_STOP=1 \
  --command="comment on table public.verification_email_jobs is 'ASK_CRUMP_VERIFICATION_EMAIL_JOBS_V1'"

psql -X --set=ON_ERROR_STOP=1 \
  --command='drop index public.users_email_lower_unique; create index users_email_lower_unique on public.users(lower(email))'
assert_refused account-index 'users lower-email unique index drifted; refusing queue migration.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop index public.users_email_lower_unique; create unique index users_email_lower_unique on public.users(lower(email))'

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs drop constraint verification_email_jobs_support_email_check'
assert_refused constraint 'verification_email_jobs constraint shape drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.verification_email_jobs add constraint verification_email_jobs_support_email_check check (length(support_email) between 3 and 320)'

psql -X --set=ON_ERROR_STOP=1 --command='alter table public.verification_email_jobs drop constraint verification_email_jobs_user_id_fkey, add constraint verification_email_jobs_user_id_fkey foreign key (user_id) references public.users(id) on delete set null'
assert_refused foreign-key 'verification_email_jobs constraint shape drifted.'
psql -X --set=ON_ERROR_STOP=1 --command='alter table public.verification_email_jobs drop constraint verification_email_jobs_user_id_fkey, add constraint verification_email_jobs_user_id_fkey foreign key (user_id) references public.users(id) on delete cascade'

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.users disable trigger all'
assert_refused foreign-key-trigger 'verification_email_jobs foreign-key triggers drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.users enable trigger all'

psql -X --set=ON_ERROR_STOP=1 \
  --command="create function public.queue_intruder_trigger() returns trigger language plpgsql as 'begin return new; end'" \
  --command='create trigger queue_intruder_trigger before insert on public.verification_email_jobs for each row execute function public.queue_intruder_trigger()'
assert_refused trigger 'verification_email_jobs trigger or rewrite-rule drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop trigger queue_intruder_trigger on public.verification_email_jobs' \
  --command='drop function public.queue_intruder_trigger()'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create rule queue_intruder_rule as on insert to public.verification_email_jobs do also nothing'
assert_refused rewrite-rule 'verification_email_jobs trigger or rewrite-rule drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop rule queue_intruder_rule on public.verification_email_jobs'

psql -X --set=ON_ERROR_STOP=1 --command="drop index public.verification_email_jobs_ready_idx; create index verification_email_jobs_ready_idx on public.verification_email_jobs(created_at, next_attempt_at, id) where status = 'queued'"
assert_refused index 'verification_email_jobs index shape drifted.'
psql -X --set=ON_ERROR_STOP=1 --command="drop index public.verification_email_jobs_ready_idx; create index verification_email_jobs_ready_idx on public.verification_email_jobs(next_attempt_at, created_at, id) where status = 'queued'"

psql -X --set=ON_ERROR_STOP=1 \
  --command='grant select on public.verification_email_jobs to service_role'
assert_refused table-acl 'verification_email_jobs drifted; refusing replacement.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke select on public.verification_email_jobs from service_role'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create role queue_column_intruder nologin' \
  --command='grant select (recipient_fingerprint) on public.verification_email_jobs to queue_column_intruder'
assert_refused column-acl 'verification_email_jobs column ACL or policy drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke select (recipient_fingerprint) on public.verification_email_jobs from queue_column_intruder'
psql -X --set=ON_ERROR_STOP=1 \
  --command='create policy queue_intruder_read on public.verification_email_jobs for select to queue_column_intruder using (true)'
assert_refused policy 'verification_email_jobs column ACL or policy drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop policy queue_intruder_read on public.verification_email_jobs' \
  --command='drop role queue_column_intruder'

psql -X --set=ON_ERROR_STOP=1 \
  --command="do \$\$ begin if not exists (select 1 from pg_roles where rolname = 'queue_intruder') then create role queue_intruder nologin; end if; end \$\$; grant execute on function public.stage_verification_email_job_v1(uuid, uuid) to queue_intruder"
assert_refused rpc-acl 'verification-email queue RPC drifted:'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke execute on function public.stage_verification_email_job_v1(uuid, uuid) from queue_intruder; drop role queue_intruder'

psql -X --set=ON_ERROR_STOP=1 \
  --file=tests/postgres/verification_email_queue_source_drift_fixture.sql
assert_refused rpc-source 'verification-email queue RPC drifted:'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop function public.claim_verification_email_job_v1(uuid, integer)'
psql -X --set=ON_ERROR_STOP=1 --single-transaction --file="$migration"

echo 'Verification-email queue drift refusals passed.'
