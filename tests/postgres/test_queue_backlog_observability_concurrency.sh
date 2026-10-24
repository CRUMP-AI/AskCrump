#!/usr/bin/env bash
set -euo pipefail

result_dir="$(mktemp -d)"
reader_pid=''
cleanup() {
  if [ -n "$reader_pid" ]; then
    kill "$reader_pid" 2>/dev/null || true
    wait "$reader_pid" 2>/dev/null || true
  fi
  rm -rf -- "$result_dir"
}
trap cleanup EXIT

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
truncate table public.verification_email_jobs, public.password_reset_email_jobs;
insert into public.verification_email_jobs (
  id, delivery_mode, recipient_fingerprint, verification_token_hash,
  verification_token_expires, alias_key_id, alias_nonce, status,
  template_version, app_name, app_url, support_email, from_email,
  next_attempt_at, created_at, updated_at
) values (
  '85000000-0000-4000-8000-000000000001', 'suppressed', repeat('1',64),
  repeat('a',64), clock_timestamp() + interval '1 hour', 'k1',
  'concurrent_read_nonce_1', 'queued', 'verification-v1', 'Ask Crump',
  'https://askcrump.com', 'support@example.test', 'from@example.test',
  clock_timestamp() - interval '1 second',
  clock_timestamp() - interval '10 seconds', clock_timestamp()
);
SQL

psql -X -qAt --set=ON_ERROR_STOP=1 >"$result_dir/reader.log" <<'SQL' &
begin isolation level repeatable read;
set local role service_role;
set local application_name = 'queue_backlog_snapshot_reader';
select verification_eligible_depth
from public.read_email_queue_backlog_v1();
select pg_sleep(5);
select verification_eligible_depth
from public.read_email_queue_backlog_v1();
commit;
SQL
reader_pid=$!

i=0
while [ "$i" -lt 200 ]; do
  sleeping="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_stat_activity where datname = pg_catalog.current_database() and application_name = 'queue_backlog_snapshot_reader' and state = 'active' and wait_event_type = 'Timeout' and wait_event = 'PgSleep';")"
  if [ "$sleeping" -eq 1 ]; then
    break
  fi
  psql -X -qAt --set=ON_ERROR_STOP=1 \
    --command='select pg_sleep(0.05)' >/dev/null
  i=$((i + 1))
done
if [ "${sleeping:-0}" -ne 1 ]; then
  echo 'Timed out waiting for the repeatable-read backlog reader.' >&2
  exit 1
fi

psql -X -qAt --set=ON_ERROR_STOP=1 >"$result_dir/claim.log" <<'SQL'
set statement_timeout = '3s';
set role service_role;
select job_id::text
from public.claim_verification_email_job_v1(
  '85100000-0000-4000-8000-000000000001', 120
);
SQL
grep -Fx '85000000-0000-4000-8000-000000000001' "$result_dir/claim.log"

wait "$reader_pid"
reader_pid=''
numeric_reads="$(grep -E '^[0-9]+$' "$result_dir/reader.log")"
test "$numeric_reads" = "$(printf '1\n1')"

post_metrics="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="set role service_role; select verification_active_depth::text || '|' || verification_eligible_depth::text from public.read_email_queue_backlog_v1();")"
test "$post_metrics" = '1|0'

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
select case
  when status = 'processing'
   and lease_token is not null
   and lease_expires_at > clock_timestamp()
  then true else false
end as claimed_without_reader_block
from public.verification_email_jobs
where id = '85000000-0000-4000-8000-000000000001';
SQL
