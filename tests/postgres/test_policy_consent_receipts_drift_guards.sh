#!/usr/bin/env bash
set -euo pipefail

migration="migrations/20261027075649_server_policy_consent_receipts.sql"
failure_log="${RUNNER_TEMP:-/tmp}/policy-consent-drift-$$.log"
: >"$failure_log"
trap 'rm -f "$failure_log"' EXIT

expect_refusal() {
  local expected="$1"
  if psql -X --set=ON_ERROR_STOP=1 --single-transaction \
    --file="$migration" >"$failure_log" 2>&1; then
    cat "$failure_log"
    echo "migration unexpectedly repaired hostile drift" >&2
    exit 1
  fi
  grep --fixed-strings "$expected" "$failure_log"
}

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
do $role$
begin
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'policy_drift_probe') then
    create role policy_drift_probe nologin;
  end if;
end;
$role$;
grant insert on table public.user_policy_acceptance_receipts to policy_drift_probe;
SQL
expect_refusal 'Policy table owner, RLS, policy, or ACL drift detected.'
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
revoke all on table public.user_policy_acceptance_receipts from policy_drift_probe;
drop role policy_drift_probe;
SQL

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
alter table public.user_policy_acceptance_receipts
  drop constraint user_policy_acceptance_receipts_attestations_check;
alter table public.user_policy_acceptance_receipts
  add constraint user_policy_acceptance_receipts_attestations_check check (
    age_17_plus_attested is true
    and terms_accepted is true
    and privacy_notice_acknowledged is true
    and (ai_provider_transmission_authorized is true or true)
  );
SQL
expect_refusal 'Policy CHECK-expression drift detected.'
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
alter table public.user_policy_acceptance_receipts
  drop constraint user_policy_acceptance_receipts_attestations_check;
alter table public.user_policy_acceptance_receipts
  add constraint user_policy_acceptance_receipts_attestations_check check (
    age_17_plus_attested is true
    and terms_accepted is true
    and privacy_notice_acknowledged is true
    and ai_provider_transmission_authorized is true
  );
SQL

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
drop trigger reject_policy_acceptance_receipt_delete
  on public.user_policy_acceptance_receipts;
SQL
expect_refusal 'Policy immutability-trigger drift detected.'
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
create trigger reject_policy_acceptance_receipt_delete
before delete on public.user_policy_acceptance_receipts
for each row execute function public.reject_policy_acceptance_receipt_mutation_v1();
SQL

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
create function public.read_current_policy_acceptance_v1(p_user_id text)
returns boolean
language sql
immutable
set search_path = ''
as 'select false';
revoke all on function public.read_current_policy_acceptance_v1(text)
  from public, anon, authenticated, service_role;
SQL
expect_refusal 'Unexpected policy function overload detected.'
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
drop function public.read_current_policy_acceptance_v1(text);
select public.assert_policy_consent_schema_v1();
SQL
