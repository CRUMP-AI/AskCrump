#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
baseline="$repo_root/tests/postgres/sessions_user_fk_hardening_baseline.sql"
migration="$repo_root/migrations/20261027072857_sessions_user_fk_hardening.sql"
catalog_test="$repo_root/tests/postgres/test_sessions_user_fk_hardening_migration.sql"
drift_log="$(mktemp)"
other_fk_log="$(mktemp)"
orphan_log="$(mktemp)"
trigger_log="$(mktemp)"
index_log="$(mktemp)"

cleanup() {
  rm -f "$drift_log" "$other_fk_log" "$orphan_log" "$trigger_log" \
    "$index_log"
}
trap cleanup EXIT

psql_base=(psql -X --set=ON_ERROR_STOP=1)

reset_fixture() {
  "${psql_base[@]}" --file="$baseline"
}

expect_refusal() {
  local expected_state="$1"
  local expected_message="$2"
  local log_file="$3"

  set +e
  "${psql_base[@]}" --set=VERBOSITY=verbose --single-transaction \
    --file="$migration" >"$log_file" 2>&1
  local status=$?
  set -e

  cat "$log_file"
  if [[ "$status" -eq 0 ]]; then
    echo "Migration unexpectedly accepted a refusal fixture." >&2
    exit 1
  fi
  grep -F "$expected_state" "$log_file"
  grep -F "$expected_message" "$log_file"
}

# First apply installs and validates the exact constraint. A hostile-search-path
# reapply must retain the same catalog object rather than replace or duplicate it.
reset_fixture
"${psql_base[@]}" --single-transaction --file="$migration"
fk_oid_before="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select oid from pg_catalog.pg_constraint where conrelid='public.sessions'::regclass and conname='sessions_user_id_fkey'")"
test -n "$fk_oid_before"
support_index_oid_before="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select oid from pg_catalog.pg_class where oid='public.sessions_user_id_fk_idx'::regclass")"
test -n "$support_index_oid_before"
"${psql_base[@]}" --single-transaction \
  --command='set search_path=pg_catalog' \
  --file="$migration"
fk_oid_after="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select oid from pg_catalog.pg_constraint where conrelid='public.sessions'::regclass and conname='sessions_user_id_fkey'")"
test "$fk_oid_before" = "$fk_oid_after"
support_index_oid_after="$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select oid from pg_catalog.pg_class where oid='public.sessions_user_id_fk_idx'::regclass")"
test "$support_index_oid_before" = "$support_index_oid_after"
"${psql_base[@]}" --file="$catalog_test"

# A same-name partial index cannot support cascade lookup across revoked rows.
# Reapply must reject that drift without replacing the hostile object.
reset_fixture
"${psql_base[@]}" --command='create index sessions_user_id_fk_idx on public.sessions(user_id) where revoked_at is null'
expect_refusal \
  '55000' \
  'Sessions-user FK support index exists with conflicting semantics.' \
  "$index_log"
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_index where indexrelid='public.sessions_user_id_fk_idx'::regclass and indpred is not null and indisvalid and indisready")" = '1'
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_constraint where conrelid='public.sessions'::regclass and conname='sessions_user_id_fkey'")" = '0'

# A same-name constraint with weaker delete semantics is malicious drift. The
# migration must refuse it without replacing or validating the hostile object.
reset_fixture
"${psql_base[@]}" --command='alter table public.sessions add constraint sessions_user_id_fkey foreign key (user_id) references public.users(id) on delete restrict not valid'
expect_refusal \
  '55000' \
  'Named sessions-user FK exists with conflicting semantics.' \
  "$drift_log"
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_constraint where conrelid='public.sessions'::regclass and conname='sessions_user_id_fkey' and confdeltype='r' and convalidated is false")" = '1'

# An exact-semantic foreign key under an unexpected name is also conflicting
# drift; accepting it would leave the intended named contract ambiguous.
reset_fixture
"${psql_base[@]}" --command='alter table public.sessions add constraint unexpected_sessions_owner_fkey foreign key (user_id) references public.users(id) on delete cascade'
expect_refusal \
  '55000' \
  'A conflicting sessions.user_id foreign key already exists.' \
  "$other_fk_log"
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_constraint where conrelid='public.sessions'::regclass and conname='unexpected_sessions_owner_fkey' and convalidated")" = '1'
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_constraint where conrelid='public.sessions'::regclass and conname='sessions_user_id_fkey'")" = '0'

# A structurally correct constraint with disabled internal enforcement is drift,
# not a valid idempotent target. Reapply must refuse it without repairing or
# otherwise concealing the privileged catalog change.
reset_fixture
"${psql_base[@]}" --single-transaction --file="$migration"
"${psql_base[@]}" --command='alter table public.sessions disable trigger all'
expect_refusal \
  '55000' \
  'Sessions-user FK enforcement triggers are missing or disabled.' \
  "$trigger_log"
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_trigger as trigger_row join pg_catalog.pg_constraint as constraint_row on constraint_row.oid=trigger_row.tgconstraint where constraint_row.conrelid='public.sessions'::regclass and constraint_row.conname='sessions_user_id_fkey' and trigger_row.tgrelid='public.sessions'::regclass and trigger_row.tgenabled='D'")" = '2'
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_trigger as trigger_row join pg_catalog.pg_constraint as constraint_row on constraint_row.oid=trigger_row.tgconstraint where constraint_row.conrelid='public.sessions'::regclass and constraint_row.conname='sessions_user_id_fkey' and trigger_row.tgrelid='public.users'::regclass and trigger_row.tgenabled='O'")" = '2'

# Existing orphan data must stop the transaction before any catalog change.
# The orphan remains available for an explicit privacy/remediation decision.
reset_fixture
"${psql_base[@]}" --command="insert into public.sessions(id,user_id) values ('82000000-0000-4000-8000-000000000099','81000000-0000-4000-8000-000000000099')"
expect_refusal \
  '23503' \
  'Orphan sessions must be remediated before FK installation.' \
  "$orphan_log"
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from public.sessions where id='82000000-0000-4000-8000-000000000099'")" = '1'
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_constraint where conrelid='public.sessions'::regclass and conname='sessions_user_id_fkey'")" = '0'
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select count(*) from pg_catalog.pg_class where oid in ('public.users'::regclass,'public.sessions'::regclass) and relrowsecurity and pg_catalog.pg_get_userbyid(relowner)='postgres'")" = '2'
test "$(psql -X -qAt --set=ON_ERROR_STOP=1 --command="select (pg_catalog.has_table_privilege('sessions_fk_observer','public.users','SELECT') and pg_catalog.has_table_privilege('sessions_fk_observer','public.sessions','SELECT') and not pg_catalog.has_table_privilege('sessions_fk_observer','public.users','INSERT') and not pg_catalog.has_table_privilege('sessions_fk_observer','public.sessions','INSERT'))::text")" = 'true'
