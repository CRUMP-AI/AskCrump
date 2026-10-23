\set ON_ERROR_STOP on

create extension if not exists dblink;

create or replace function pg_temp.assert_true(
  condition boolean,
  failure_message text
)
returns void
language plpgsql
as $$
begin
  if condition is not true then
    raise exception 'PostgreSQL free-message gate failed: %', failure_message;
  end if;
end;
$$;

select pg_temp.assert_true(
  pg_catalog.has_function_privilege(
    'service_role',
    'public.reserve_free_message_v1(uuid,uuid,text)',
    'EXECUTE'
  ),
  'service_role cannot execute the reservation RPC'
);
select pg_temp.assert_true(
  not pg_catalog.has_function_privilege(
    'anon',
    'public.reserve_free_message_v1(uuid,uuid,text)',
    'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated',
    'public.reserve_free_message_v1(uuid,uuid,text)',
    'EXECUTE'
  ),
  'the reservation RPC is exposed to a browser API role'
);
select pg_temp.assert_true(
  pg_catalog.has_table_privilege('service_role', 'public.usage_events', 'SELECT')
  and pg_catalog.has_table_privilege('service_role', 'public.usage_events', 'DELETE')
  and not pg_catalog.has_table_privilege('service_role', 'public.usage_events', 'INSERT')
  and not pg_catalog.has_table_privilege('service_role', 'public.usage_events', 'UPDATE')
  and not pg_catalog.has_table_privilege('service_role', 'public.usage_events', 'TRUNCATE')
  and not pg_catalog.has_table_privilege('service_role', 'public.usage_events', 'REFERENCES')
  and not pg_catalog.has_table_privilege('service_role', 'public.usage_events', 'TRIGGER')
  and not pg_catalog.has_table_privilege('service_role', 'public.usage_events', 'MAINTAIN'),
  'service_role usage_events privileges are broader or narrower than select/delete'
);
select pg_temp.assert_true(
  not pg_catalog.has_table_privilege('anon', 'public.usage_events', 'SELECT')
  and not pg_catalog.has_table_privilege('anon', 'public.usage_events', 'INSERT')
  and not pg_catalog.has_table_privilege('anon', 'public.usage_events', 'UPDATE')
  and not pg_catalog.has_table_privilege('anon', 'public.usage_events', 'DELETE')
  and not pg_catalog.has_table_privilege('authenticated', 'public.usage_events', 'SELECT')
  and not pg_catalog.has_table_privilege('authenticated', 'public.usage_events', 'INSERT')
  and not pg_catalog.has_table_privilege('authenticated', 'public.usage_events', 'UPDATE')
  and not pg_catalog.has_table_privilege('authenticated', 'public.usage_events', 'DELETE'),
  'a browser API role retained direct usage_events access'
);

-- The release singleton is intentionally installed disabled. This disposable
-- fixture enables it directly as the migration owner so guest write behavior
-- can be exercised before the later service-role operator RPC is installed.
update public.guest_mode_control
   set enabled = true,
       updated_at = pg_catalog.clock_timestamp()
 where singleton is true;

insert into public.users (id, is_guest)
values
  ('90000000-0000-4000-8000-000000000001', true),
  ('90000000-0000-4000-8000-000000000002', true),
  ('90000000-0000-4000-8000-000000000003', true),
  ('90000000-0000-4000-8000-000000000004', true),
  ('90000000-0000-4000-8000-000000000006', true),
  ('90000000-0000-4000-8000-000000000005', false);

set role service_role;
create temporary table reservation_results (
  sequence integer,
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz
);

insert into reservation_results
select 1, result.* from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000001',
  repeat('a', 64)
) as result;
insert into reservation_results
select 2, result.* from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000002',
  repeat('b', 64)
) as result;
insert into reservation_results
select 3, result.* from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000003',
  repeat('c', 64)
) as result;
insert into reservation_results
select 4, result.* from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000004',
  repeat('d', 64)
) as result;
insert into reservation_results
select 5, result.* from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000005',
  repeat('e', 64)
) as result;

select pg_temp.assert_true(
  not exists (
    select 1 from reservation_results
     where outcome <> 'reserved'
        or used <> sequence
        or remaining <> 5 - sequence
        or event_id is null
  ),
  'calls one through five did not reserve exactly one sequential slot'
);
select pg_temp.assert_true(
  (
    select next_available_at = (
      select min(created_at) + interval '24 hours'
        from public.usage_events
       where user_id = '90000000-0000-4000-8000-000000000001'
         and event_type = 'messages'
    )
      from reservation_results
     where sequence = 5
  ),
  'the fifth reservation did not expose the oldest receipt expiry'
);

create temporary table sixth_result as
select * from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000006',
  repeat('f', 64)
);
select pg_temp.assert_true(
  (select outcome = 'exhausted' and event_id is null and used = 5 and remaining = 0
     from sixth_result),
  'the sixth distinct message was not rejected at the cap'
);
select pg_temp.assert_true(
  (select count(*) = 5 from public.usage_events
    where user_id = '90000000-0000-4000-8000-000000000001'
      and event_type = 'messages'),
  'an exhausted reservation inserted a receipt'
);

create temporary table replay_result as
select * from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000005',
  repeat('e', 64)
);
select pg_temp.assert_true(
  (select outcome = 'reused' and event_id is null and used = 5 and remaining = 0
     from replay_result),
  'an exact replay at the cap was not idempotently reused'
);

-- A registered Free account uses the same ledger, and an exact replay below
-- the cap does not insert or consume a second receipt.
create temporary table registered_free_result as
select * from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000005',
  '95000000-0000-4000-8000-000000000001',
  repeat('5', 64)
);
create temporary table registered_free_replay_result as
select * from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000005',
  '95000000-0000-4000-8000-000000000001',
  repeat('5', 64)
);
select pg_temp.assert_true(
  (select outcome = 'reserved' and event_id is not null and used = 1 and remaining = 4
     from registered_free_result)
  and
  (select outcome = 'reused' and event_id is null and used = 1 and remaining = 4
     from registered_free_replay_result)
  and
  (select count(*) = 1 from public.usage_events
    where user_id = '90000000-0000-4000-8000-000000000005'
      and event_type = 'messages'),
  'a registered Free replay below the cap consumed another receipt'
);
reset role;

-- Signup changes the same owner row; it must not mint a new allowance.
update public.users
   set is_guest = false
 where id = '90000000-0000-4000-8000-000000000001';
set role service_role;
create temporary table converted_result as
select * from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000007',
  repeat('1', 64)
);
select pg_temp.assert_true(
  (select outcome = 'exhausted' and used = 5 and remaining = 0 from converted_result),
  'guest-to-account conversion reset the shared allowance'
);
reset role;

-- Existing ledgers can exceed five recent rows after a downgrade. The exact
-- reset is the event at offset used-limit, not the oldest receipt.
insert into public.usage_events (
  user_id, event_type, idempotency_key, created_at
)
select
  '90000000-0000-4000-8000-000000000002',
  'messages',
  'seed-' || series::text,
  statement_timestamp() - (interval '7 hours' - series * interval '1 hour')
from pg_catalog.generate_series(1, 7) as series;

set role service_role;
create temporary table over_cap_result as
select * from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000002',
  '92000000-0000-4000-8000-000000000008',
  repeat('2', 64)
);
select pg_temp.assert_true(
  (
    select outcome = 'exhausted'
       and event_id is null
       and used = 7
       and remaining = 0
       and next_available_at = (
         select created_at + interval '24 hours'
           from public.usage_events
          where user_id = '90000000-0000-4000-8000-000000000002'
            and event_type = 'messages'
          order by created_at asc, id asc
          offset 2 limit 1
       )
      from over_cap_result
  ),
  'the over-cap reset was not based on the used-limit receipt'
);
reset role;

-- Only the receipt id owned by a new reservation is refundable.
set role service_role;
create temporary table refundable_result as
select * from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000003',
  '93000000-0000-4000-8000-000000000001',
  repeat('3', 64)
);
delete from public.usage_events
 where id = (select event_id from refundable_result);
create temporary table after_refund_result as
select * from public.reserve_free_message_v1(
  '90000000-0000-4000-8000-000000000003',
  '93000000-0000-4000-8000-000000000002',
  repeat('4', 64)
);
select pg_temp.assert_true(
  (select outcome = 'reserved' and used = 1 and remaining = 4 from after_refund_result),
  'deleting the owned receipt did not restore exactly one slot'
);
reset role;

-- Two callers compete for the fifth slot. Connection A holds the same
-- advisory namespace, B queues, A reserves and commits, then B must exhaust.
insert into public.usage_events (user_id, event_type, idempotency_key, created_at)
select
  '90000000-0000-4000-8000-000000000004',
  'messages',
  'concurrent-seed-' || series::text,
  statement_timestamp() - series * interval '1 minute'
from pg_catalog.generate_series(1, 4) as series;

select public.dblink_connect(
  'free_message_a',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'free-message-a'
  )
);
select public.dblink_connect(
  'free_message_b',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'free-message-b'
  )
);
select public.dblink_exec('free_message_a', 'begin');
select public.dblink_exec(
  'free_message_a',
  $command$
    do $lock$
    begin
      perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
          'usage:90000000-0000-4000-8000-000000000004:messages', 0
        )
      );
    end;
    $lock$;
  $command$
);
select public.dblink_exec('free_message_a', 'set role service_role');
select public.dblink_exec('free_message_b', 'set role service_role');
select public.dblink_send_query(
  'free_message_b',
  $query$
    select * from public.reserve_free_message_v1(
      '90000000-0000-4000-8000-000000000004',
      '94000000-0000-4000-8000-000000000002',
      repeat('b', 64)
    )
  $query$
);

do $wait_for_allowance_lock$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'free-message-b'
         and wait_event_type = 'Lock'
         and wait_event = 'advisory'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;

  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'free-message-b'
       and wait_event_type = 'Lock'
       and wait_event = 'advisory'
  ) then
    raise exception 'the competing Free reservation did not reach the allowance advisory lock';
  end if;
end;
$wait_for_allowance_lock$;

create temporary table concurrent_results (
  caller text,
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz
);
insert into concurrent_results
select 'a', result.*
from public.dblink(
  'free_message_a',
  $query$
    select * from public.reserve_free_message_v1(
      '90000000-0000-4000-8000-000000000004',
      '94000000-0000-4000-8000-000000000001',
      repeat('a', 64)
    )
  $query$
) as result(
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz
);
select public.dblink_exec('free_message_a', 'commit');
insert into concurrent_results
select 'b', result.*
from public.dblink_get_result('free_message_b') as result(
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz
);
select pg_temp.assert_true(
  (select count(*) = 1 from concurrent_results where outcome = 'reserved')
  and (select count(*) = 1 from concurrent_results where outcome = 'exhausted')
  and (
    select count(*) = 5 from public.usage_events
     where user_id = '90000000-0000-4000-8000-000000000004'
       and event_type = 'messages'
  ),
  'concurrent callers did not authorize exactly one fifth receipt'
);
select public.dblink_disconnect('free_message_a');
select public.dblink_disconnect('free_message_b');

-- A waiter that begins while the fifth receipt is current must re-sample
-- database wall time after the advisory lock. Once that receipt expires, the
-- waiting call owns the newly opened slot and timestamps it after release.
insert into public.usage_events (
  user_id, event_type, idempotency_key, created_at
) values (
  '90000000-0000-4000-8000-000000000006',
  'messages',
  'boundary-seed-oldest',
  pg_catalog.clock_timestamp() - interval '23 hours'
);
insert into public.usage_events (
  user_id, event_type, idempotency_key, created_at
)
select
  '90000000-0000-4000-8000-000000000006',
  'messages',
  'boundary-seed-' || series::text,
  pg_catalog.clock_timestamp() - series * interval '1 hour'
from pg_catalog.generate_series(1, 4) as series;

select public.dblink_connect(
  'free_message_boundary_lock',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'free-message-boundary-lock'
  )
);
select public.dblink_connect(
  'free_message_boundary_waiter',
  pg_catalog.format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'free-message-boundary-waiter'
  )
);
select public.dblink_exec('free_message_boundary_lock', 'begin');
select public.dblink_exec(
  'free_message_boundary_lock',
  $command$
    do $lock$
    begin
      perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
          'usage:90000000-0000-4000-8000-000000000006:messages', 0
        )
      );
    end;
    $lock$;
  $command$
);
select public.dblink_exec('free_message_boundary_waiter', 'set role service_role');
select public.dblink_send_query(
  'free_message_boundary_waiter',
  $query$
    select * from public.reserve_free_message_v1(
      '90000000-0000-4000-8000-000000000006',
      '96000000-0000-4000-8000-000000000001',
      repeat('6', 64)
    )
  $query$
);

do $wait_for_boundary_lock$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'free-message-boundary-waiter'
         and wait_event_type = 'Lock'
         and wait_event = 'advisory'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;

  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'free-message-boundary-waiter'
       and wait_event_type = 'Lock'
       and wait_event = 'advisory'
  ) then
    raise exception 'the boundary reservation did not reach the allowance advisory lock';
  end if;
end;
$wait_for_boundary_lock$;

-- Pin the expiry to the waiter's actual statement start after the lock wait
-- is observed. This keeps the regression deterministic even on a slow CI
-- runner: statement_timestamp() sees the row as current, while the post-lock
-- wall clock sees it as expired.
create temporary table boundary_waiter_start as
select activity.query_start
  from pg_catalog.pg_stat_activity as activity
 where activity.application_name = 'free-message-boundary-waiter';
update public.usage_events as event
   set created_at = boundary_waiter_start.query_start
       - interval '24 hours'
       + interval '1 second'
  from boundary_waiter_start
 where event.user_id = '90000000-0000-4000-8000-000000000006'
   and event.idempotency_key = 'boundary-seed-oldest';

select pg_temp.assert_true(
  exists (
    select 1
      from pg_catalog.pg_stat_activity as activity
      join public.usage_events as event
        on event.user_id = '90000000-0000-4000-8000-000000000006'
       and event.idempotency_key = 'boundary-seed-oldest'
     where activity.application_name = 'free-message-boundary-waiter'
       and activity.query_start < event.created_at + interval '24 hours'
  ),
  'the boundary waiter did not begin before the oldest receipt expired'
);
select pg_catalog.pg_sleep(
  greatest(
    pg_catalog.date_part(
      'epoch',
      (
        (
          select query_start + interval '1.25 seconds'
            from boundary_waiter_start
        ) - pg_catalog.clock_timestamp()
      )
    ),
    0.25
  )
);
create temporary table boundary_release as
select pg_catalog.clock_timestamp() as released_at;
select public.dblink_exec('free_message_boundary_lock', 'commit');

create temporary table boundary_result as
select result.*
from public.dblink_get_result('free_message_boundary_waiter') as result(
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz
);
select pg_temp.assert_true(
  (
    select outcome = 'reserved'
       and event_id is not null
       and used = 5
       and remaining = 0
      from boundary_result
  ),
  'a lock waiter did not claim the slot that opened while it was blocked'
);
select pg_temp.assert_true(
  (
    select event.created_at >= boundary_release.released_at
      from boundary_result
      join public.usage_events as event on event.id = boundary_result.event_id
      cross join boundary_release
  ),
  'the post-lock reservation receipt was backdated before lock release'
);
select public.dblink_disconnect('free_message_boundary_lock');
select public.dblink_disconnect('free_message_boundary_waiter');

-- Validation failures must retain their stable SQLSTATEs.
do $validation$
begin
  begin
    perform * from public.reserve_free_message_v1(
      '90000000-0000-4000-8000-000000000003',
      '93000000-0000-4000-8000-000000000003',
      'not-a-fingerprint'
    );
    raise exception 'invalid fingerprint unexpectedly succeeded';
  exception when sqlstate '22023' then
    null;
  end;

  begin
    perform * from public.reserve_free_message_v1(
      '99000000-0000-4000-8000-000000000099',
      '99000000-0000-4000-8000-000000000001',
      repeat('9', 64)
    );
    raise exception 'unknown user unexpectedly succeeded';
  exception when foreign_key_violation then
    null;
  end;
end;
$validation$;
