#!/usr/bin/env bash
set -euo pipefail

migration="migrations/20261027184134_guest_start_measurement.sql"
fixture_sql="$(mktemp)"
refusal_log="$(mktemp)"
cleanup() {
  rm -f "$fixture_sql" "$refusal_log"
}
trap cleanup EXIT

run_refusal() {
  local scenario="$1"
  local expected="$2"
  set +e
  psql -X --set=ON_ERROR_STOP=1 --set=VERBOSITY=verbose \
    --command=begin \
    --file="$fixture_sql" \
    --file="$migration" \
    >"$refusal_log" 2>&1
  local migration_status=$?
  set -e

  cat "$refusal_log"
  if [ "$migration_status" -eq 0 ]; then
    echo "Migration unexpectedly accepted $scenario drift."
    exit 1
  fi
  grep -F "55000" "$refusal_log"
  grep -F "$expected" "$refusal_log"
}

cat >"$fixture_sql" <<'SQL'
create or replace function public.stamp_guest_start_from_session_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  -- guest-start-contract:stamp-v1 retained deliberately.
  return new;
end;
$$;
SQL
run_refusal \
  "same-marker function source" \
  "Guest-start function contract drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
alter function public.product_guest_start_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) strict parallel safe;
SQL
run_refusal \
  "function STRICT/parallel attributes" \
  "Guest-start function contract drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
drop trigger users_guest_start_immutability_v1 on public.users;
create trigger users_guest_start_immutability_v1
before insert or update of guest_started_at
on public.users
for each row
when (new.guest_started_at is not null)
execute function public.enforce_guest_start_immutability_v1();
SQL
run_refusal \
  "user trigger columns/WHEN" \
  "Guest-start trigger contract drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
drop index public.users_guest_start_cohort_idx;
create index users_guest_start_cohort_idx
  on public.users(guest_started_at, id)
  include (guest_start_environment)
  where guest_started_at is not null;
SQL
run_refusal \
  "index parent/key/include/opclass" \
  "Guest-start cohort index drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
drop trigger users_guest_start_immutability_v1 on public.users;
alter table public.users
  alter column guest_start_environment
  type text collate pg_catalog."C";
create trigger users_guest_start_immutability_v1
before insert or update of
  guest_start_tracking_version, guest_started_at, guest_start_environment
on public.users
for each row
execute function public.enforce_guest_start_immutability_v1();
SQL
run_refusal \
  "guest-start environment collation" \
  "Guest-start column/default drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
create or replace function public.enforce_guest_mode_on_session_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  return new;
end;
$$;
SQL
run_refusal \
  "companion guard function source" \
  "Guest-start session guard prerequisite drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
alter trigger enforce_guest_mode_on_session_v1 on public.sessions
  rename to renamed_guest_mode_session_guard;
SQL
run_refusal \
  "renamed companion guard" \
  "Guest-start session guard prerequisite drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
alter table public.sessions
  disable trigger enforce_guest_mode_on_session_v1;
SQL
run_refusal \
  "disabled companion guard" \
  "Guest-start session guard prerequisite drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
drop trigger enforce_guest_mode_on_session_v1 on public.sessions;
SQL
run_refusal \
  "missing companion guard" \
  "Guest-start session guard prerequisite drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
drop trigger enforce_guest_mode_on_session_v1 on public.sessions;
create trigger enforce_guest_mode_on_session_v1
before update of user_id on public.sessions
for each row
when (new.revoked_at is null)
execute function public.enforce_guest_mode_on_session_v1();
SQL
run_refusal \
  "companion guard event/columns/WHEN shape" \
  "Guest-start session guard prerequisite drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
create trigger "0_duplicate_guest_mode_session_guard"
before insert or update on public.sessions
for each row
execute function public.enforce_guest_mode_on_session_v1();
SQL
run_refusal \
  "lexically earlier duplicate companion guard" \
  "Guest-start session guard prerequisite drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
grant execute on function public.stamp_guest_start_from_session_v1()
  to anon;
SQL
run_refusal \
  "private function ACL" \
  "Guest-start function ACL drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
grant select on table public.users to anon;
SQL
run_refusal \
  "users table ACL" \
  "Guest-start users/sessions ACL prerequisite drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
grant update(guest_started_at) on table public.users to authenticated;
SQL
run_refusal \
  "users column ACL" \
  "Guest-start users/sessions ACL prerequisite drift exists; refusing migration."

cat >"$fixture_sql" <<'SQL'
alter table public.users disable row level security;
SQL
run_refusal \
  "users RLS" \
  "Guest-start users/sessions RLS prerequisite drift exists; refusing migration."

# Every planted drift lived only in the failed transaction. A final exact
# reapply proves rollback retained the reviewed contract.
psql -X --set=ON_ERROR_STOP=1 \
  --command='set search_path=pg_catalog' \
  --file="$migration"
