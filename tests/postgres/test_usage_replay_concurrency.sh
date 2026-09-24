#!/usr/bin/env bash
set -euo pipefail

task_dir="$(mktemp -d)"
export ASKCRUMP_USAGE_REPLAY_MARKER="$task_dir/first-lock-held"
owner_id='10000000-0000-4000-8000-000000000002'
event_type='feature:concurrent-replay-fixture'
usage_key='concurrent-message-component'

(
  psql -X --set=ON_ERROR_STOP=1 --quiet --no-align --tuples-only >"$task_dir/first.out" <<SQL
begin;
select pg_advisory_xact_lock(
  hashtextextended('usage:${owner_id}:${event_type}', 0)
);
\! touch "$ASKCRUMP_USAGE_REPLAY_MARKER"
select duplicate
from public.consume_usage_event_v2(
  '${owner_id}'::uuid,
  '${event_type}',
  1,
  '{"usageIdempotencyKey":"${usage_key}"}'::jsonb
);
select pg_sleep(2);
commit;
SQL
) &
first_pid=$!

for _attempt in $(seq 1 100); do
  if [[ -f "$ASKCRUMP_USAGE_REPLAY_MARKER" ]]; then
    break
  fi
  sleep 0.05
done
if [[ ! -f "$ASKCRUMP_USAGE_REPLAY_MARKER" ]]; then
  echo 'first keyed usage transaction did not acquire its lock' >&2
  exit 1
fi

second_duplicate="$({
  psql -X --set=ON_ERROR_STOP=1 --quiet --no-align --tuples-only <<SQL
select duplicate
from public.consume_usage_event_v2(
  '${owner_id}'::uuid,
  '${event_type}',
  1,
  '{"usageIdempotencyKey":"${usage_key}"}'::jsonb
);
SQL
} | tr -d '[:space:]')"
wait "$first_pid"

first_duplicate="$(grep -E '^[ft]$' "$task_dir/first.out" | head -n 1 | tr -d '[:space:]')"
row_count="$(psql -X --set=ON_ERROR_STOP=1 --quiet --no-align --tuples-only <<SQL | tr -d '[:space:]'
select count(*)
from public.usage_events
where user_id = '${owner_id}'::uuid
  and event_type = '${event_type}'
  and idempotency_key = '${usage_key}';
SQL
)"

if [[ "$first_duplicate" != 'f' || "$second_duplicate" != 't' || "$row_count" != '1' ]]; then
  echo "concurrent replay contract failed: first=$first_duplicate second=$second_duplicate rows=$row_count" >&2
  exit 1
fi

echo 'Concurrent keyed usage replay converged on one owned event.'

paid_marker="$task_dir/first-paid-lock-held"
paid_event_type='feature:image_edit'
paid_usage_key='concurrent-paid-message:image-edit'

(
  psql -X --set=ON_ERROR_STOP=1 --quiet --no-align --tuples-only >"$task_dir/first-paid.out" <<SQL
begin;
select pg_advisory_xact_lock(
  hashtextextended('credits:${owner_id}', 0)
);
\! touch "$paid_marker"
select duplicate
from public.spend_credits_confirmed_v2(
  '${owner_id}'::uuid,
  10,
  'feature_image_edit',
  'concurrent-paid-quote-one',
  '${paid_usage_key}',
  10,
  '${paid_event_type}',
  '${paid_usage_key}',
  '{"route":"chat"}'::jsonb
);
select pg_sleep(2);
commit;
SQL
) &
first_paid_pid=$!

for _attempt in $(seq 1 100); do
  if [[ -f "$paid_marker" ]]; then
    break
  fi
  sleep 0.05
done
if [[ ! -f "$paid_marker" ]]; then
  echo 'first keyed paid transaction did not acquire its lock' >&2
  exit 1
fi

second_paid_duplicate="$({
  psql -X --set=ON_ERROR_STOP=1 --quiet --no-align --tuples-only <<SQL
select duplicate
from public.spend_credits_confirmed_v2(
  '${owner_id}'::uuid,
  10,
  'feature_image_edit',
  'concurrent-paid-quote-two',
  '${paid_usage_key}',
  10,
  '${paid_event_type}',
  '${paid_usage_key}',
  '{"route":"chat"}'::jsonb
);
SQL
} | tr -d '[:space:]')"
wait "$first_paid_pid"

first_paid_duplicate="$(grep -E '^[ft]$' "$task_dir/first-paid.out" | head -n 1 | tr -d '[:space:]')"
paid_spend_count="$(psql -X --set=ON_ERROR_STOP=1 --quiet --no-align --tuples-only <<SQL | tr -d '[:space:]'
select count(*)
from public.credit_ledger
where user_id = '${owner_id}'::uuid
  and provider = 'feature-spend'
  and metadata ->> 'usageEventType' = '${paid_event_type}'
  and metadata ->> 'usageIdempotencyKey' = '${paid_usage_key}';
SQL
)"
paid_balance="$(psql -X --set=ON_ERROR_STOP=1 --quiet --no-align --tuples-only <<SQL | tr -d '[:space:]'
select balance
from public.credit_accounts
where user_id = '${owner_id}'::uuid;
SQL
)"

if [[ "$first_paid_duplicate" != 'f' || "$second_paid_duplicate" != 't' \
   || "$paid_spend_count" != '1' || "$paid_balance" != '90' ]]; then
  echo "concurrent paid replay contract failed: first=$first_paid_duplicate second=$second_paid_duplicate spends=$paid_spend_count balance=$paid_balance" >&2
  exit 1
fi

echo 'Concurrent keyed paid replay converged on one confirmed deduction.'
