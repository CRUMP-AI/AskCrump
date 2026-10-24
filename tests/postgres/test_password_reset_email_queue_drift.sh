#!/usr/bin/env bash
set -euo pipefail

migration='migrations/20261024163849_durable_password_reset_email_jobs.sql'
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
  --command='alter table public.password_reset_email_jobs alter column attempts drop default'
assert_refused column 'password_reset_email_jobs column shape drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.password_reset_email_jobs alter column attempts set default 0'

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.password_reset_email_jobs set unlogged'
assert_refused persistence 'password_reset_email_jobs drifted; refusing replacement.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.password_reset_email_jobs set logged'

psql -X --set=ON_ERROR_STOP=1 \
  --command='comment on table public.password_reset_email_jobs is null'
assert_refused table-marker 'password_reset_email_jobs drifted; refusing replacement.'
psql -X --set=ON_ERROR_STOP=1 \
  --command="comment on table public.password_reset_email_jobs is 'ASK_CRUMP_PASSWORD_RESET_EMAIL_JOBS_V1'"

psql -X --set=ON_ERROR_STOP=1 \
  --command='drop index public.users_email_lower_unique; create index users_email_lower_unique on public.users(lower(email))'
assert_refused account-index 'users lower-email unique index drifted; refusing queue migration.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop index public.users_email_lower_unique; create unique index users_email_lower_unique on public.users(lower(email))'

psql -X --set=ON_ERROR_STOP=1 \
  --command='drop index public.users_password_reset_token_hash_unique; create unique index users_password_reset_token_hash_unique on public.users(password_reset_token_hash) include(email) where password_reset_token_hash is not null'
assert_refused reset-index 'password-reset unique index drifted; refusing queue migration.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop index public.users_password_reset_token_hash_unique; create unique index users_password_reset_token_hash_unique on public.users(password_reset_token_hash) where password_reset_token_hash is not null'

psql -X --set=ON_ERROR_STOP=1 \
  --command='grant execute on function public.consume_password_reset_v1(text,text) to authenticated'
assert_refused consumer-acl 'atomic password-reset consumer drifted; refusing queue migration.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke execute on function public.consume_password_reset_v1(text,text) from authenticated'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create role reset_consumer_intruder nologin; grant execute on function public.consume_password_reset_v1(text,text) to reset_consumer_intruder'
assert_refused consumer-arbitrary-acl 'atomic password-reset consumer drifted; refusing queue migration.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke execute on function public.consume_password_reset_v1(text,text) from reset_consumer_intruder; drop role reset_consumer_intruder'

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.password_reset_email_jobs drop constraint password_reset_email_jobs_support_email_check'
assert_refused constraint 'password_reset_email_jobs constraint shape drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.password_reset_email_jobs add constraint password_reset_email_jobs_support_email_check check (length(support_email) between 3 and 320)'

psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.password_reset_email_jobs drop constraint password_reset_email_jobs_user_id_fkey, add constraint password_reset_email_jobs_user_id_fkey foreign key (user_id) references public.users(id) on delete set null'
assert_refused foreign-key 'password_reset_email_jobs constraint shape drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='alter table public.password_reset_email_jobs drop constraint password_reset_email_jobs_user_id_fkey, add constraint password_reset_email_jobs_user_id_fkey foreign key (user_id) references public.users(id) on delete cascade'

psql -X --set=ON_ERROR_STOP=1 --command='alter table public.users disable trigger all'
assert_refused foreign-key-trigger 'password_reset_email_jobs foreign-key triggers drifted.'
psql -X --set=ON_ERROR_STOP=1 --command='alter table public.users enable trigger all'

psql -X --set=ON_ERROR_STOP=1 \
  --command="create function public.password_reset_queue_intruder_trigger() returns trigger language plpgsql as 'begin return new; end'" \
  --command='create trigger password_reset_queue_intruder_trigger before insert on public.password_reset_email_jobs for each row execute function public.password_reset_queue_intruder_trigger()'
assert_refused trigger 'password_reset_email_jobs trigger or rewrite-rule drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop trigger password_reset_queue_intruder_trigger on public.password_reset_email_jobs' \
  --command='drop function public.password_reset_queue_intruder_trigger()'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create rule password_reset_queue_intruder_rule as on insert to public.password_reset_email_jobs do also nothing'
assert_refused rewrite-rule 'password_reset_email_jobs trigger or rewrite-rule drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop rule password_reset_queue_intruder_rule on public.password_reset_email_jobs'

psql -X --set=ON_ERROR_STOP=1 \
  --command="drop index public.password_reset_email_jobs_ready_idx; create index password_reset_email_jobs_ready_idx on public.password_reset_email_jobs(created_at, next_attempt_at, id) where status = 'queued'"
assert_refused index 'password_reset_email_jobs index shape drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command="drop index public.password_reset_email_jobs_ready_idx; create index password_reset_email_jobs_ready_idx on public.password_reset_email_jobs(next_attempt_at, created_at, id) where status = 'queued'"

psql -X --set=ON_ERROR_STOP=1 \
  --command='grant select on public.password_reset_email_jobs to service_role'
assert_refused table-acl 'password_reset_email_jobs drifted; refusing replacement.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke select on public.password_reset_email_jobs from service_role'

psql -X --set=ON_ERROR_STOP=1 \
  --command='create role password_reset_queue_column_intruder nologin' \
  --command='grant select (recipient_fingerprint) on public.password_reset_email_jobs to password_reset_queue_column_intruder'
assert_refused column-acl 'password_reset_email_jobs column ACL or policy drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke select (recipient_fingerprint) on public.password_reset_email_jobs from password_reset_queue_column_intruder' \
  --command='create policy password_reset_queue_intruder_read on public.password_reset_email_jobs for select to password_reset_queue_column_intruder using (true)'
assert_refused policy 'password_reset_email_jobs column ACL or policy drifted.'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop policy password_reset_queue_intruder_read on public.password_reset_email_jobs' \
  --command='drop role password_reset_queue_column_intruder'

psql -X --set=ON_ERROR_STOP=1 \
  --command="do \$\$ begin if not exists (select 1 from pg_roles where rolname = 'password_reset_queue_intruder') then create role password_reset_queue_intruder nologin; end if; end \$\$; grant execute on function public.stage_password_reset_email_job_v1(uuid,uuid) to password_reset_queue_intruder"
assert_refused rpc-acl 'password-reset-email queue RPC drifted:'
psql -X --set=ON_ERROR_STOP=1 \
  --command='revoke execute on function public.stage_password_reset_email_job_v1(uuid,uuid) from password_reset_queue_intruder; drop role password_reset_queue_intruder'

psql -X --set=ON_ERROR_STOP=1 \
  --file=tests/postgres/password_reset_email_queue_source_drift_fixture.sql
assert_refused rpc-source 'password-reset-email queue RPC drifted:'
psql -X --set=ON_ERROR_STOP=1 \
  --command='drop function public.claim_password_reset_email_job_v1(uuid,integer)'
psql -X --set=ON_ERROR_STOP=1 --single-transaction --file="$migration"

# The queue depends on the exact atomic reset consumer previously released.
# Prove a source-compatible-looking but semantically wrong replacement is
# refused even when ownership, comment, execution attributes, and ACLs remain.
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
create or replace function public.consume_password_reset_v1(
  p_token_hash text,
  p_password_hash text
)
returns table(reset_applied boolean)
language plpgsql
volatile
security definer
set search_path = ''
as $$
begin
  return query select false;
end;
$$;
alter function public.consume_password_reset_v1(text,text) owner to postgres;
revoke all on function public.consume_password_reset_v1(text,text)
  from public, anon, authenticated, service_role;
grant execute on function public.consume_password_reset_v1(text,text)
  to service_role;
comment on function public.consume_password_reset_v1(text,text) is
  'Atomically consumes one password-reset token, updates its account, and revokes every active session.';
SQL
assert_refused consumer-source 'atomic password-reset consumer drifted; refusing queue migration.'

echo 'Password-reset-email queue drift refusals passed.'
