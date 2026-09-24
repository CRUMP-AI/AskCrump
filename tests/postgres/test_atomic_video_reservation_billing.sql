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
    raise exception 'PostgreSQL migration gate failed: %', failure_message;
  end if;
end;
$$;

-- The real migration must have compiled, installed its compatibility trigger,
-- and backfilled the pre-atomic row without leaving the legacy phase behind.
select pg_temp.assert_true(
  (
    select video_phase = 'launching'
      and status = 'queued'
      and lease_token is not null
      and lease_expires_at is not null
      and request_fingerprint ~ '^[0-9a-f]{64}$'
      and metadata ->> 'compatibilityOrigin' = 'pre-atomic'
    from public.media_jobs
    where id = '11000000-0000-4000-8000-000000000001'
  ),
  'the pre-atomic row was not classified and fenced'
);

-- Capacity decisions are globally serialized. Both reservations are visible
-- before either RPC starts, so one caller must release itself at the limit and
-- the other must authorize; two successful callers would be oversubscription.
insert into public.users (id)
values ('20000000-0000-4000-8000-000000000001');

insert into public.credit_accounts (user_id)
values ('20000000-0000-4000-8000-000000000001');

insert into public.media_jobs (
  id,
  user_id,
  kind,
  provider,
  provider_job_id,
  idempotency_key,
  status,
  prompt,
  model,
  request_fingerprint,
  video_phase,
  lease_token,
  lease_expires_at,
  estimated_provider_cost_cents,
  metadata
)
values
  (
    '21000000-0000-4000-8000-000000000001',
    '20000000-0000-4000-8000-000000000001',
    'video',
    'gemini',
    'pending:capacity-a',
    'capacity-a',
    'queued',
    'Capacity fixture A.',
    'veo-test',
    repeat('a', 64),
    'reserved_unbilled',
    '22000000-0000-4000-8000-000000000001',
    now() + interval '10 minutes',
    10,
    '{}'::jsonb
  ),
  (
    '21000000-0000-4000-8000-000000000002',
    '20000000-0000-4000-8000-000000000001',
    'video',
    'gemini',
    'pending:capacity-b',
    'capacity-b',
    'queued',
    'Capacity fixture B.',
    'veo-test',
    repeat('b', 64),
    'reserved_unbilled',
    '22000000-0000-4000-8000-000000000002',
    now() + interval '10 minutes',
    10,
    '{}'::jsonb
  );

select dblink_connect(
  'capacity_gate',
  format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'atomic-capacity-gate'
  )
);
select dblink_connect(
  'capacity_a',
  format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'atomic-capacity-a'
  )
);
select dblink_connect(
  'capacity_b',
  format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'atomic-capacity-b'
  )
);

select dblink_exec('capacity_a', 'set role service_role');
select dblink_exec('capacity_b', 'set role service_role');

select dblink_exec('capacity_gate', 'begin');
select *
from dblink(
  'capacity_gate',
  $query$
    select true
    from (
      select pg_advisory_xact_lock(
        hashtextextended('askcrump-video-capacity-v1', 0)
      )
    ) as acquired
  $query$
) as capacity_gate_lock(acquired boolean);

select dblink_send_query(
  'capacity_a',
  $query$
    select outcome, active_jobs
    from public.authorize_video_reservation_capacity(
      '20000000-0000-4000-8000-000000000001',
      '21000000-0000-4000-8000-000000000001',
      'capacity-a',
      repeat('a', 64),
      '22000000-0000-4000-8000-000000000001',
      1,
      1000,
      1000,
      1000,
      false
    )
  $query$
);
select dblink_send_query(
  'capacity_b',
  $query$
    select outcome, active_jobs
    from public.authorize_video_reservation_capacity(
      '20000000-0000-4000-8000-000000000001',
      '21000000-0000-4000-8000-000000000002',
      'capacity-b',
      repeat('b', 64),
      '22000000-0000-4000-8000-000000000002',
      1,
      1000,
      1000,
      1000,
      false
    )
  $query$
);

do $$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when (
      select count(*) = 2
      from pg_stat_activity
      where application_name in ('atomic-capacity-a', 'atomic-capacity-b')
        and wait_event_type = 'Lock'
        and wait_event = 'advisory'
    );
    perform pg_sleep(0.05);
  end loop;

  if not (
    select count(*) = 2
    from pg_stat_activity
    where application_name in ('atomic-capacity-a', 'atomic-capacity-b')
      and wait_event_type = 'Lock'
      and wait_event = 'advisory'
  ) then
    raise exception 'Both capacity calls did not reach the serialization lock';
  end if;
end;
$$;

select dblink_exec('capacity_gate', 'commit');

create temporary table capacity_results (
  caller text not null,
  outcome text not null,
  active_jobs integer not null
);

insert into capacity_results
select 'a', result.outcome, result.active_jobs
from dblink_get_result('capacity_a') as result(
  outcome text,
  active_jobs integer
);

insert into capacity_results
select 'b', result.outcome, result.active_jobs
from dblink_get_result('capacity_b') as result(
  outcome text,
  active_jobs integer
);

select pg_temp.assert_true(
  (select count(*) = 1 from capacity_results where outcome = 'authorized'),
  'concurrent capacity calls did not authorize exactly one reservation'
);
select pg_temp.assert_true(
  (select count(*) = 1 from capacity_results where outcome = 'concurrency_limit'),
  'concurrent capacity calls did not reject exactly one reservation'
);
select pg_temp.assert_true(
  (
    select count(*) = 1
    from public.media_jobs
    where user_id = '20000000-0000-4000-8000-000000000001'
      and metadata ->> 'capacityAuthorized' = 'true'
  ),
  'capacity serialization left an unexpected number of authorized rows'
);

-- Exercise the successful atomic receipt bind and idempotent replay with the
-- same restricted invoker role used by the backend in Supabase.
set role service_role;
do $$
declare
  reservation public.media_jobs%rowtype;
  first_call record;
  replay_call record;
begin
  select *
  into reservation
  from public.media_jobs
  where user_id = '20000000-0000-4000-8000-000000000001'
    and metadata ->> 'capacityAuthorized' = 'true';

  select *
  into first_call
  from public.consume_video_reservation(
    reservation.user_id,
    reservation.id,
    reservation.idempotency_key,
    reservation.request_fingerprint,
    reservation.lease_token::text,
    'video',
    'internal',
    'video_generation',
    1,
    10,
    'video_generation',
    'capacity-action',
    'video',
    10,
    10,
    '{}'::jsonb
  );

  if first_call.outcome <> 'bound'
     or first_call.receipt ->> 'paymentSource' <> 'internal'
  then
    raise exception 'The authorized reservation was not atomically billed';
  end if;

  select *
  into replay_call
  from public.consume_video_reservation(
    reservation.user_id,
    reservation.id,
    reservation.idempotency_key,
    reservation.request_fingerprint,
    reservation.lease_token::text,
    'video',
    'internal',
    'video_generation',
    1,
    10,
    'video_generation',
    'capacity-action',
    'video',
    10,
    10,
    '{}'::jsonb
  );

  if replay_call.outcome <> 'existing' or not replay_call.duplicate then
    raise exception 'The atomic billing replay was not idempotent';
  end if;
end;
$$;
reset role;

select dblink_disconnect('capacity_gate');
select dblink_disconnect('capacity_a');
select dblink_disconnect('capacity_b');

-- Reconciliation is oldest-first but uses SKIP LOCKED. A locked oldest row
-- must not block younger work, and it must become eligible immediately after
-- the lock clears instead of being starved by the claimed rows' backoff.
insert into public.users (id)
values ('30000000-0000-4000-8000-000000000001');

insert into public.media_jobs (
  id,
  user_id,
  kind,
  provider,
  provider_job_id,
  idempotency_key,
  status,
  prompt,
  model,
  request_fingerprint,
  video_phase,
  provider_started_at,
  sweep_retry_after,
  billing_receipt,
  metadata,
  created_at,
  updated_at
)
values
  (
    '31000000-0000-4000-8000-000000000001',
    '30000000-0000-4000-8000-000000000001',
    'video',
    'gemini',
    'provider-fairness-1',
    'fairness-1',
    'processing',
    'Fairness fixture 1.',
    'veo-test',
    repeat('1', 64),
    'processing',
    now() - interval '1 hour',
    now() - interval '30 minutes',
    '{"paymentSource":"subscription","eventId":null}'::jsonb,
    '{}'::jsonb,
    now() - interval '3 hours',
    now() - interval '10 minutes'
  ),
  (
    '31000000-0000-4000-8000-000000000002',
    '30000000-0000-4000-8000-000000000001',
    'video',
    'gemini',
    'provider-fairness-2',
    'fairness-2',
    'processing',
    'Fairness fixture 2.',
    'veo-test',
    repeat('2', 64),
    'processing',
    now() - interval '1 hour',
    now() - interval '20 minutes',
    '{"paymentSource":"subscription","eventId":null}'::jsonb,
    '{}'::jsonb,
    now() - interval '2 hours',
    now() - interval '10 minutes'
  ),
  (
    '31000000-0000-4000-8000-000000000003',
    '30000000-0000-4000-8000-000000000001',
    'video',
    'gemini',
    'provider-fairness-3',
    'fairness-3',
    'processing',
    'Fairness fixture 3.',
    'veo-test',
    repeat('3', 64),
    'processing',
    now() - interval '1 hour',
    now() - interval '10 minutes',
    '{"paymentSource":"subscription","eventId":null}'::jsonb,
    '{}'::jsonb,
    now() - interval '1 hour',
    now() - interval '10 minutes'
  );

select dblink_connect(
  'fairness_locker',
  format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'atomic-fairness-locker'
  )
);
select dblink_exec('fairness_locker', 'set role service_role');
select dblink_exec('fairness_locker', 'begin');
select *
from dblink(
  'fairness_locker',
  $query$
    select id
    from public.media_jobs
    where id = '31000000-0000-4000-8000-000000000001'
    for update
  $query$
) as fairness_lock(id uuid);

set role service_role;
create temporary table fairness_first as
select *
from public.claim_video_reconciliation_batch(2, 60, 300);
reset role;

select pg_temp.assert_true(
  (
    select array_agg(id order by id) = array[
      '31000000-0000-4000-8000-000000000002'::uuid,
      '31000000-0000-4000-8000-000000000003'::uuid
    ]
    from fairness_first
  ),
  'the batch did not skip the locked oldest row and claim the next two'
);

select dblink_exec('fairness_locker', 'commit');

set role service_role;
create temporary table fairness_second as
select *
from public.claim_video_reconciliation_batch(1, 60, 300);
reset role;

select pg_temp.assert_true(
  (
    select count(*) = 1
      and min(id) = '31000000-0000-4000-8000-000000000001'::uuid
    from fairness_second
  ),
  'the formerly locked oldest row was starved after its lock cleared'
);

select dblink_disconnect('fairness_locker');

-- Reproduce the dangerous lock order from a rolling deploy: an old UPDATE
-- owns the row lock and waits in the compatibility trigger for the owner lock.
-- The modern billing path already owns the owner lock, must SKIP LOCKED, fail
-- closed, and release without deadlocking the old writer.
update public.media_jobs
set lease_expires_at = now() - interval '1 minute'
where id = '11000000-0000-4000-8000-000000000001';

insert into public.credit_accounts (user_id)
values ('10000000-0000-4000-8000-000000000001');

insert into public.media_jobs (
  id,
  user_id,
  kind,
  provider,
  provider_job_id,
  idempotency_key,
  status,
  prompt,
  model,
  request_fingerprint,
  video_phase,
  lease_token,
  lease_expires_at,
  estimated_provider_cost_cents,
  metadata
)
values (
  '12000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000001',
  'video',
  'gemini',
  'pending:lock-order-reservation',
  'lock-order-reservation',
  'queued',
  'Lock-order reservation fixture.',
  'veo-test',
  repeat('c', 64),
  'reserved_unbilled',
  '13000000-0000-4000-8000-000000000001',
  now() + interval '10 minutes',
  10,
  '{"capacityAuthorized":true}'::jsonb
);

select dblink_connect(
  'modern_billing',
  format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'atomic-modern-billing'
  )
);
select dblink_connect(
  'legacy_writer',
  format(
    'dbname=%L user=%L application_name=%L',
    current_database(),
    current_user,
    'atomic-legacy-writer'
  )
);

select dblink_exec('modern_billing', 'set role service_role');
select dblink_exec('legacy_writer', 'set role service_role');

select dblink_exec('modern_billing', 'begin');
select dblink_exec(
  'modern_billing',
  'set local statement_timeout = ''5 seconds'''
);
select *
from dblink(
  'modern_billing',
  $query$
    select true
    from (
      select pg_advisory_xact_lock(
        hashtextextended(
          'askcrump-video-owner-billing-v1:'
          || '10000000-0000-4000-8000-000000000001',
          0
        )
      )
    ) as acquired
  $query$
) as modern_owner_lock(acquired boolean);

select dblink_send_query(
  'legacy_writer',
  $query$
    update public.media_jobs
    set metadata = metadata || '{"legacyPatch":true}'::jsonb
    where id = '11000000-0000-4000-8000-000000000001'
    returning id
  $query$
);

do $$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
      from pg_stat_activity
      where application_name = 'atomic-legacy-writer'
        and wait_event_type = 'Lock'
        and wait_event = 'advisory'
    );
    perform pg_sleep(0.05);
  end loop;

  if not exists (
    select 1
    from pg_stat_activity
    where application_name = 'atomic-legacy-writer'
      and wait_event_type = 'Lock'
      and wait_event = 'advisory'
  ) then
    raise exception 'The legacy writer did not reach the owner advisory lock';
  end if;
end;
$$;

create temporary table lock_order_result as
select *
from dblink(
  'modern_billing',
  $query$
    select outcome
    from public.consume_video_reservation(
      '10000000-0000-4000-8000-000000000001',
      '12000000-0000-4000-8000-000000000001',
      'lock-order-reservation',
      repeat('c', 64),
      '13000000-0000-4000-8000-000000000001',
      'video',
      'internal',
      'video_generation',
      1,
      10,
      'video_generation',
      'lock-order-action',
      'video',
      10,
      10,
      '{}'::jsonb
    )
  $query$
) as result(outcome text);

select pg_temp.assert_true(
  (select outcome = 'settlement_pending' from lock_order_result),
  'the owner-scoped billing path did not fail closed on the locked legacy row'
);

select dblink_exec('modern_billing', 'commit');

create temporary table legacy_update_result as
select *
from dblink_get_result('legacy_writer') as result(id uuid);

select pg_temp.assert_true(
  (
    select count(*) = 1
    from legacy_update_result
    where id = '11000000-0000-4000-8000-000000000001'
  ),
  'the legacy writer did not finish after the owner lock was released'
);
select pg_temp.assert_true(
  (
    select billing_receipt = '{}'::jsonb
      and video_phase = 'reserved_unbilled'
    from public.media_jobs
    where id = '12000000-0000-4000-8000-000000000001'
  ),
  'the failed-closed billing attempt mutated the reservation'
);

select dblink_disconnect('modern_billing');
select dblink_disconnect('legacy_writer');

select 'atomic video reservation PostgreSQL gate passed' as result;
