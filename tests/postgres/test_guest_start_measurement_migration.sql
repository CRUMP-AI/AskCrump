\set ON_ERROR_STOP on

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

select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 3
      from information_schema.columns as column_row
     where column_row.table_schema = 'public'
       and column_row.table_name = 'users'
       and column_row.column_name in (
         'guest_start_tracking_version',
         'guest_started_at',
         'guest_start_environment'
       )
       and column_row.is_nullable = 'YES'
       and (
         (column_row.column_name = 'guest_start_tracking_version'
          and column_row.data_type = 'smallint')
         or (column_row.column_name = 'guest_started_at'
             and column_row.data_type = 'timestamp with time zone')
         or (column_row.column_name = 'guest_start_environment'
             and column_row.data_type = 'text')
       )
  ),
  'forward guest-start columns are missing or incompatible'
);

select pg_temp.assert_true(
  (
    select users_relation.relrowsecurity
      and sessions_relation.relrowsecurity
    from pg_catalog.pg_class as users_relation
    cross join pg_catalog.pg_class as sessions_relation
    where users_relation.oid = 'public.users'::regclass
      and sessions_relation.oid = 'public.sessions'::regclass
  )
  and not has_table_privilege('anon', 'public.users', 'SELECT')
  and not has_table_privilege('anon', 'public.sessions', 'SELECT')
  and not has_table_privilege('authenticated', 'public.users', 'SELECT')
  and not has_table_privilege('authenticated', 'public.sessions', 'SELECT')
  and not has_any_column_privilege('anon', 'public.users', 'SELECT')
  and not has_any_column_privilege('authenticated', 'public.users', 'UPDATE'),
  'users/sessions RLS or direct-role ACL prerequisites drifted'
);

select pg_temp.assert_true(
  exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = 'public.users'::regclass
       and constraint_row.conname = 'users_guest_start_boundary_check'
       and constraint_row.contype = 'c'
       and constraint_row.convalidated
  ),
  'guest-start boundary constraint is missing or unvalidated'
);

select pg_temp.assert_true(
  (
    select index_row.indrelid = 'public.users'::regclass
      and access_method.amname = 'btree'
      and index_row.indnkeyatts = 3
      and index_row.indnatts = 3
      and index_row.indexprs is null
      and index_row.indisvalid
      and index_row.indisready
      and index_row.indislive
      and not index_row.indisunique
      and not index_row.indisprimary
      and not index_row.indisexclusion
      and pg_catalog.pg_get_indexdef(index_row.indexrelid) =
        'CREATE INDEX users_guest_start_cohort_idx ON public.users USING btree (guest_start_environment, guest_started_at, id) WHERE (guest_started_at IS NOT NULL)'
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as index_relation
      on index_relation.oid = index_row.indexrelid
    join pg_catalog.pg_am as access_method
      on access_method.oid = index_relation.relam
    where index_row.indexrelid =
      'public.users_guest_start_cohort_idx'::regclass
  ),
  'guest-start cohort index shape drifted'
);

select pg_temp.assert_true(
  (
    select trigger_row.tgtype = 23
      and trigger_row.tgenabled = 'O'
      and trigger_row.tgqual is null
      and pg_catalog.cardinality(trigger_row.tgattr::smallint[]) = 3
      and trigger_row.tgattr[0] = (
        select attribute_row.attnum
          from pg_catalog.pg_attribute as attribute_row
         where attribute_row.attrelid = 'public.users'::regclass
           and attribute_row.attname = 'guest_start_tracking_version'
      )
      and trigger_row.tgattr[1] = (
        select attribute_row.attnum
          from pg_catalog.pg_attribute as attribute_row
         where attribute_row.attrelid = 'public.users'::regclass
           and attribute_row.attname = 'guest_started_at'
      )
      and trigger_row.tgattr[2] = (
        select attribute_row.attnum
          from pg_catalog.pg_attribute as attribute_row
         where attribute_row.attrelid = 'public.users'::regclass
           and attribute_row.attname = 'guest_start_environment'
      )
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid = 'public.users'::regclass
      and trigger_row.tgname = 'users_guest_start_immutability_v1'
      and not trigger_row.tgisinternal
  ),
  'user immutability trigger columns or predicate drifted'
);

select pg_temp.assert_true(
  (
    select trigger_row.tgtype & 2 = 2
      and trigger_row.tgtype & 4 = 4
      and trigger_row.tgtype & 16 = 0
      and trigger_row.tgtype & 8 = 0
      and trigger_row.tgtype & 1 = 1
      and trigger_row.tgqual is null
      and pg_catalog.cardinality(trigger_row.tgattr::smallint[]) = 0
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid = 'public.sessions'::regclass
      and trigger_row.tgname = 'a_guest_start_owner_lock_v1'
      and not trigger_row.tgisinternal
  ),
  'owner prelock is not a row-level BEFORE INSERT trigger'
);

select pg_temp.assert_true(
  (
    select trigger_row.tgtype & 2 = 0
      and trigger_row.tgtype & 4 = 4
      and trigger_row.tgtype & 16 = 16
      and trigger_row.tgtype & 1 = 1
      and trigger_row.tgqual is null
      and pg_catalog.cardinality(trigger_row.tgattr::smallint[]) = 1
      and trigger_row.tgattr[0] = (
        select attribute_row.attnum
          from pg_catalog.pg_attribute as attribute_row
         where attribute_row.attrelid = 'public.sessions'::regclass
           and attribute_row.attname = 'user_id'
      )
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid = 'public.sessions'::regclass
      and trigger_row.tgname = 'sessions_guest_start_stamp_v1'
      and not trigger_row.tgisinternal
  ),
  'stamp is not a row-level AFTER INSERT OR UPDATE OF user_id trigger'
);

select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 4
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_language as language_row
        on language_row.oid = function_row.prolang
     where function_row.oid in (
       'public.enforce_guest_start_immutability_v1()'::regprocedure,
       'public.lock_guest_start_owner_before_session_v1()'::regprocedure,
       'public.stamp_guest_start_from_session_v1()'::regprocedure,
       'public.product_guest_start_funnel_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure
     )
       and language_row.lanname = 'plpgsql'
       and function_row.prokind = 'f'
       and function_row.proisstrict is false
       and function_row.proleakproof is false
       and function_row.proparallel = 'u'
  ),
  'guest-start function language/kind/null/leak/parallel contract drifted'
);

select pg_temp.assert_true(
  (
    select function_row.prosecdef is false
      and function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.md5(function_row.prosrc) =
        '295ae12afaa71900aabde7d5502a14e2'
    from pg_catalog.pg_proc as function_row
    where function_row.oid =
      'public.enforce_guest_start_immutability_v1()'::regprocedure
  )
  and (
    select function_row.prosecdef is true
      and function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.md5(function_row.prosrc) =
        'ac2f6822a109add3b3189a4e0db8a606'
    from pg_catalog.pg_proc as function_row
    where function_row.oid =
      'public.lock_guest_start_owner_before_session_v1()'::regprocedure
  )
  and (
    select function_row.prosecdef is true
      and function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.md5(function_row.prosrc) =
        'f812b2e7d9828929a6267c894148b549'
    from pg_catalog.pg_proc as function_row
    where function_row.oid =
      'public.stamp_guest_start_from_session_v1()'::regprocedure
  ),
  'private guest-start trigger functions have unsafe security attributes'
);

select pg_temp.assert_true(
  'a_guest_start_owner_lock_v1' < 'enforce_guest_mode_on_session_v1',
  'owner lock trigger no longer sorts before the guest-mode session guard'
);

select pg_temp.assert_true(
  not has_function_privilege(
    'anon', 'public.enforce_guest_start_immutability_v1()', 'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated', 'public.enforce_guest_start_immutability_v1()', 'EXECUTE'
  )
  and not has_function_privilege(
    'service_role', 'public.enforce_guest_start_immutability_v1()', 'EXECUTE'
  )
  and not has_function_privilege(
    'anon', 'public.lock_guest_start_owner_before_session_v1()', 'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated',
    'public.lock_guest_start_owner_before_session_v1()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'service_role',
    'public.lock_guest_start_owner_before_session_v1()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'anon', 'public.stamp_guest_start_from_session_v1()', 'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated', 'public.stamp_guest_start_from_session_v1()', 'EXECUTE'
  )
  and not has_function_privilege(
    'service_role', 'public.stamp_guest_start_from_session_v1()', 'EXECUTE'
  ),
  'private guest-start trigger function ACLs drifted'
);

-- Every pre-migration account stays in the unknown legacy cohort. A later
-- new-device session for an old guest must not fabricate a first-start time.
select pg_temp.assert_true(
  (
    select account.guest_start_tracking_version is null
      and account.guest_started_at is null
      and account.guest_start_environment is null
    from public.users as account
    where account.id = '10000000-0000-4000-8000-000000000002'
  ),
  'migration backfilled a legacy guest'
);

insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '10000000-0000-4000-8000-000000000002',
  'legacy-new-device-token',
  'legacy-new-device',
  pg_catalog.statement_timestamp() + interval '1 day'
);

select pg_temp.assert_true(
  (
    select account.guest_started_at is null
      and account.guest_start_environment is null
    from public.users as account
    where account.id = '10000000-0000-4000-8000-000000000002'
  ),
  'a post-cutover session fabricated legacy guest timing'
);

-- A direct registration is forward-eligible but is not a guest start.
insert into public.users (
  id, email, is_guest, is_verified, created_at,
  registration_environment, subscription_tier, subscription_status
) values (
  '30000000-0000-4000-8000-000000000001',
  'direct-registration@example.test',
  false,
  false,
  pg_catalog.statement_timestamp() - interval '10 minutes',
  'production',
  'free',
  'inactive'
);

select pg_temp.assert_true(
  (
    select account.guest_start_tracking_version = 1
      and account.guest_started_at is null
      and account.guest_start_environment is null
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000001'
  ),
  'direct registration was counted as a guest start'
);

-- Fresh guest identities are eligible, but creation alone is not a start.
insert into public.users (
  id, email, is_guest, is_verified, created_at,
  registration_environment, subscription_tier, subscription_status
) values
  (
    '30000000-0000-4000-8000-000000000002',
    'guest-30000000-0000-4000-8000-000000000002@guest.askcrump.local',
    true,
    false,
    pg_catalog.statement_timestamp() - interval '9 minutes',
    'production',
    'free',
    'inactive'
  ),
  (
    '30000000-0000-4000-8000-000000000003',
    'guest-30000000-0000-4000-8000-000000000003@guest.askcrump.local',
    true,
    false,
    pg_catalog.statement_timestamp() - interval '8 minutes',
    'production',
    'free',
    'inactive'
  ),
  (
    '30000000-0000-4000-8000-000000000004',
    'guest-30000000-0000-4000-8000-000000000004@guest.askcrump.local',
    true,
    false,
    pg_catalog.statement_timestamp() - interval '7 minutes',
    'production',
    'free',
    'inactive'
  ),
  (
    '30000000-0000-4000-8000-000000000005',
    'guest-30000000-0000-4000-8000-000000000005@guest.askcrump.local',
    true,
    false,
    pg_catalog.statement_timestamp() - interval '6 minutes',
    'preview',
    'free',
    'inactive'
  ),
  (
    '30000000-0000-4000-8000-000000000007',
    'guest-30000000-0000-4000-8000-000000000007@guest.askcrump.local',
    true,
    false,
    pg_catalog.statement_timestamp() - interval '5 minutes',
    'production',
    'free',
    'inactive'
  ),
  (
    '30000000-0000-4000-8000-000000000008',
    'guest-30000000-0000-4000-8000-000000000008@guest.askcrump.local',
    true,
    false,
    pg_catalog.statement_timestamp() - interval '5 minutes',
    'production',
    'free',
    'inactive'
  ),
  (
    '30000000-0000-4000-8000-000000000009',
    'guest-30000000-0000-4000-8000-000000000009@guest.askcrump.local',
    true,
    false,
    pg_catalog.statement_timestamp() + interval '1 hour',
    'development',
    'free',
    'inactive'
  );

select pg_temp.assert_true(
  (
    select account.guest_start_tracking_version = 1
      and account.guest_started_at is null
      and account.guest_start_environment is null
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000002'
  ),
  'guest creation without a session was counted as a start'
);

-- created_at is supplied by an application clock and may be ahead of the
-- database. A valid persisted session must still keep the exact database
-- guest-start stamp rather than fail or clamp it to the app timestamp.
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '30000000-0000-4000-8000-000000000009',
  'guest-start-future-created-token',
  'future-created-guest-device',
  pg_catalog.statement_timestamp() + interval '1 day'
);

select pg_temp.assert_true(
  (
    select account.guest_started_at is not null
      and account.guest_started_at < account.created_at
      and account.guest_start_environment = 'development'
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000009'
  ),
  'future app created_at rejected or rewrote the database guest-start stamp'
);

-- A failed session write does not stamp because the measurement trigger is
-- AFTER the successful row event.
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '30000000-0000-4000-8000-000000000001',
  'guest-start-duplicate-token',
  'registered-device',
  pg_catalog.statement_timestamp() + interval '1 day'
);

do $$
begin
  begin
    insert into public.sessions (
      user_id, token_hash, device_id, expires_at
    ) values (
      '30000000-0000-4000-8000-000000000005',
      'guest-start-duplicate-token',
      'failed-guest-device',
      pg_catalog.statement_timestamp() + interval '1 day'
    );
    raise exception 'duplicate session unexpectedly succeeded';
  exception when unique_violation then
    null;
  end;
end;
$$;

select pg_temp.assert_true(
  (
    select account.guest_started_at is null
      and account.guest_start_environment is null
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000005'
  ),
  'failed session persistence stamped a guest start'
);

insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '30000000-0000-4000-8000-000000000007',
  'guest-start-do-nothing-token',
  'registered-device',
  pg_catalog.statement_timestamp() + interval '1 day'
)
on conflict (device_id) do nothing;

select pg_temp.assert_true(
  (
    select account.guest_started_at is null
      and account.guest_start_environment is null
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000007'
  ),
  'conflict DO NOTHING was counted as a successful guest session'
);

insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '30000000-0000-4000-8000-000000000005',
  'guest-start-expired-token',
  'expired-guest-device',
  pg_catalog.statement_timestamp() - interval '1 second'
);

select pg_temp.assert_true(
  (
    select account.guest_started_at is null
      and account.guest_start_environment is null
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000005'
  ),
  'expired session was counted as an active guest start'
);

update public.users
   set deleted_at = pg_catalog.statement_timestamp()
 where id = '30000000-0000-4000-8000-000000000008';

insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '30000000-0000-4000-8000-000000000008',
  'guest-start-deleted-token',
  'deleted-guest-device',
  pg_catalog.statement_timestamp() + interval '1 day'
);

select pg_temp.assert_true(
  (
    select account.guest_started_at is null
      and account.guest_start_environment is null
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000008'
  ),
  'soft-deleted guest session was counted as a guest start'
);

insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '30000000-0000-4000-8000-000000000002',
  'guest-start-first-token',
  'shared-device',
  pg_catalog.statement_timestamp() + interval '1 day'
);

create temporary table guest_start_test_clock as
select
  account.id as user_id,
  account.guest_started_at,
  account.guest_start_environment
from public.users as account
where account.id = '30000000-0000-4000-8000-000000000002';

select pg_temp.assert_true(
  (
    select clock.guest_started_at is not null
      and clock.guest_start_environment = 'production'
    from guest_start_test_clock as clock
  ),
  'successful guest session did not stamp exact environment and time'
);

update public.sessions
   set last_activity = pg_catalog.statement_timestamp()
 where device_id = 'shared-device';

select pg_temp.assert_true(
  (
    select account.guest_started_at = clock.guest_started_at
      and account.guest_start_environment = clock.guest_start_environment
    from public.users as account
    join guest_start_test_clock as clock on clock.user_id = account.id
  ),
  'ordinary session update rewrote the first guest start'
);

-- The supported device upsert executes BEFORE INSERT owner locking followed by
-- an AFTER UPDATE stamp when ownership changes.
insert into public.sessions (
  user_id, token_hash, device_id, expires_at
) values (
  '30000000-0000-4000-8000-000000000003',
  'guest-start-reassigned-token',
  'shared-device',
  pg_catalog.statement_timestamp() + interval '1 day'
)
on conflict (device_id) do update
set user_id = excluded.user_id,
    token_hash = excluded.token_hash,
    expires_at = excluded.expires_at,
    revoked_at = null;

select pg_temp.assert_true(
  (
    select account.guest_started_at is not null
      and account.guest_start_environment = 'production'
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000003'
  ),
  'device-session reassignment did not stamp the new guest'
);

-- A direct owner UPDATE is also supported when uncontended; its NOWAIT owner
-- lock makes concurrency fail fast rather than forming a tuple/user deadlock.
insert into public.users (
  id, email, is_guest, is_verified, created_at,
  registration_environment, subscription_tier, subscription_status
) values (
  '30000000-0000-4000-8000-000000000006',
  'guest-30000000-0000-4000-8000-000000000006@guest.askcrump.local',
  true,
  false,
  pg_catalog.statement_timestamp() - interval '5 minutes',
  'production',
  'free',
  'inactive'
);

update public.sessions
   set user_id = '30000000-0000-4000-8000-000000000006',
       token_hash = 'guest-start-direct-update-token'
 where device_id = 'shared-device';

select pg_temp.assert_true(
  (
    select account.guest_started_at is not null
      and account.guest_start_environment = 'production'
    from public.users as account
    where account.id = '30000000-0000-4000-8000-000000000006'
  ),
  'direct session owner change did not stamp the current guest'
);

-- Conversion cannot reclassify or rewrite the immutable guest-start
-- environment or time. The acquisition cohort follows this account through a
-- later preview registration and preview activation without relabeling its
-- original production start.
update public.users
   set email = 'converted-guest@example.test',
       is_verified = true,
       is_guest = false,
       registration_environment = 'preview',
       registration_submitted_at = (
         select clock.guest_started_at - interval '1 millisecond'
           from guest_start_test_clock as clock
       ),
       guest_started_at = timestamptz '2000-01-01 00:00:00+00',
       guest_start_environment = 'preview',
       guest_start_tracking_version = null
 where id = '30000000-0000-4000-8000-000000000002';

select pg_temp.assert_true(
  (
    select account.guest_start_tracking_version = 1
      and account.guest_started_at = clock.guest_started_at
      and account.guest_start_environment = 'production'
      and account.registration_environment = 'preview'
      and account.registration_submitted_at < clock.guest_started_at
      and account.email_verified_at >= account.registration_submitted_at
    from public.users as account
    join guest_start_test_clock as clock on clock.user_id = account.id
  ),
  'verification or conversion rewrote the immutable guest-start boundary'
);

insert into public.product_events (
  user_id, environment, event_name, event_key, source, created_at
)
select
  account.id,
  'preview',
  'ActivationReached',
  'guest-start-measurement-activation',
  'postgres-gate',
  account.email_verified_at + interval '1 second'
from public.users as account
where account.id = '30000000-0000-4000-8000-000000000002';

do $$
declare
  v_since timestamptz := pg_catalog.statement_timestamp() - interval '1 hour';
  v_until timestamptz := pg_catalog.statement_timestamp() + interval '1 hour';
  v_guest_started bigint;
  v_registered bigint;
  v_verified bigint;
  v_activated bigint;
begin
  select
    max(report.accounts) filter (where report.metric = 'guest_started'),
    max(report.accounts) filter (where report.metric = 'registration_submitted'),
    max(report.accounts) filter (where report.metric = 'email_verified'),
    max(report.accounts) filter (where report.metric = 'activation_reached')
    into strict v_guest_started, v_registered, v_verified, v_activated
  from public.product_guest_start_funnel_snapshot(
    v_since, v_until, 'production', false
  ) as report;

  if v_guest_started <> 3
     or v_registered <> 1
     or v_verified <> 1
     or v_activated <> 1 then
    raise exception
      'unexpected forward guest funnel: starts=% registrations=% verified=% activation=%',
      v_guest_started, v_registered, v_verified, v_activated;
  end if;
end;
$$;

select pg_temp.assert_true(
  (
    select pg_catalog.array_agg(distinct key_row.key order by key_row.key) =
      array['accounts', 'eligible', 'metric', 'rate_pct', 'stage_order']::text[]
    from public.product_guest_start_funnel_snapshot(
      pg_catalog.statement_timestamp() - interval '1 hour',
      pg_catalog.statement_timestamp() + interval '1 hour',
      'production',
      false
    ) as report
    cross join lateral pg_catalog.jsonb_object_keys(
      pg_catalog.to_jsonb(report)
    ) as key_row(key)
  ),
  'guest-start aggregate exposes identifiers or content-bearing fields'
);

select pg_temp.assert_true(
  (
    select function_row.prosecdef is false
      and function_row.provolatile = 's'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.md5(function_row.prosrc) =
        'a7965f41c9413af126455e9f3c24a160'
    from pg_catalog.pg_proc as function_row
    where function_row.oid =
      'public.product_guest_start_funnel_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure
  )
  and has_function_privilege(
    'service_role',
    'public.product_guest_start_funnel_snapshot(timestamptz,timestamptz,text,boolean)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'anon',
    'public.product_guest_start_funnel_snapshot(timestamptz,timestamptz,text,boolean)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated',
    'public.product_guest_start_funnel_snapshot(timestamptz,timestamptz,text,boolean)',
    'EXECUTE'
  ),
  'guest-start aggregate security or ACL drifted'
);

set role service_role;
select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 4
      from public.product_guest_start_funnel_snapshot(
        pg_catalog.statement_timestamp() - interval '1 hour',
        pg_catalog.statement_timestamp() + interval '1 hour',
        'production',
        false
      )
  ),
  'service role cannot execute the content-free guest-start aggregate'
);
reset role;

do $$
begin
  begin
    perform *
      from public.product_guest_start_funnel_snapshot(
        pg_catalog.statement_timestamp(),
        pg_catalog.statement_timestamp(),
        'production',
        false
      );
    raise exception 'empty interval unexpectedly succeeded';
  exception when invalid_parameter_value then
    null;
  end;

  begin
    perform *
      from public.product_guest_start_funnel_snapshot(
        pg_catalog.statement_timestamp() - interval '1 hour',
        pg_catalog.statement_timestamp(),
        'unknown',
        false
      );
    raise exception 'invalid environment unexpectedly succeeded';
  exception when invalid_parameter_value then
    null;
  end;

  begin
    perform *
      from public.product_guest_start_funnel_snapshot(
        pg_catalog.statement_timestamp() - interval '1 hour',
        pg_catalog.statement_timestamp(),
        null::text,
        false
      );
    raise exception 'null environment unexpectedly succeeded';
  exception when invalid_parameter_value then
    null;
  end;
end;
$$;
