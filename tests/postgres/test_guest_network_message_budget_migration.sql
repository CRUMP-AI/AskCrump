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
    raise exception 'PostgreSQL guest network message-budget gate failed: %',
      failure_message;
  end if;
end;
$$;

-- The child ledger is private, minimal, indexed for both quota reads and the
-- global retention sweep. Account deletion severs the optional usage link but
-- preserves the de-identified network receipt until the 25-hour purge.
select pg_temp.assert_true(
  (
    select count(*) = 4
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'guest_network_message_events'
       and (
         (
           column_name = 'receipt_id'
           and data_type = 'uuid'
           and is_nullable = 'NO'
           and column_default = 'gen_random_uuid()'
         )
         or (column_name = 'usage_event_id' and data_type = 'uuid' and is_nullable = 'YES')
         or (column_name = 'network_key_hash' and data_type = 'text' and is_nullable = 'NO')
         or (
           column_name = 'created_at'
           and data_type = 'timestamp with time zone'
           and is_nullable = 'NO'
         )
       )
  ),
  'the network receipt table columns drifted'
);
select pg_temp.assert_true(
  (
    select candidate.relrowsecurity
      from pg_catalog.pg_class as candidate
     where candidate.oid = 'public.guest_network_message_events'::regclass
  ),
  'row-level security is not enabled on the network receipt table'
);
select pg_temp.assert_true(
  exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid =
           'public.guest_network_message_events'::regclass
       and constraint_row.contype = 'p'
  )
  and exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid =
           'public.guest_network_message_events'::regclass
       and constraint_row.contype = 'f'
       and constraint_row.confrelid = 'public.usage_events'::regclass
       and constraint_row.confdeltype = 'n'
  )
  and exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid =
           'public.guest_network_message_events'::regclass
       and constraint_row.conname =
           'guest_network_message_events_network_key_hash_check'
       and constraint_row.contype = 'c'
       and pg_catalog.pg_get_constraintdef(constraint_row.oid)
           like '%^[0-9a-f]{64}$%'
  )
  and exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid =
           'public.guest_network_message_events'::regclass
       and constraint_row.contype = 'u'
       and pg_catalog.pg_get_constraintdef(constraint_row.oid) =
           'UNIQUE (usage_event_id)'
  ),
  'a primary-key, hash-check, unique link, or SET NULL foreign-key constraint is missing'
);
select pg_temp.assert_true(
  (
    select pg_catalog.array_agg(
      constraint_row.conname || ':' || constraint_row.contype::text || ':' ||
        pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
      order by constraint_row.conname
    ) = array[
      'guest_network_message_events_network_key_hash_check:c:CHECK (network_key_hash ~ ''^[0-9a-f]{64}$''::text)',
      'guest_network_message_events_pkey:p:PRIMARY KEY (receipt_id)',
      'guest_network_message_events_usage_event_id_fkey:f:FOREIGN KEY (usage_event_id) REFERENCES usage_events(id) ON DELETE SET NULL',
      'guest_network_message_events_usage_event_id_key:u:UNIQUE (usage_event_id)'
    ]::text[]
       and pg_catalog.bool_and(constraint_row.convalidated)
       and pg_catalog.bool_and(not constraint_row.condeferrable)
       and pg_catalog.bool_and(not constraint_row.condeferred)
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid =
           'public.guest_network_message_events'::regclass
  ),
  'the network receipt table constraint set is not exact and validated'
);
select pg_temp.assert_true(
  (
    select count(*) = 2
       and bool_and(index_row.indisvalid)
       and bool_and(index_row.indisready)
       and bool_and(not index_row.indisunique)
       and bool_and(index_row.indpred is null)
       and bool_and(index_row.indexprs is null)
      from pg_catalog.pg_index as index_row
      join pg_catalog.pg_class as index_relation
        on index_relation.oid = index_row.indexrelid
      join pg_catalog.pg_am as access_method
        on access_method.oid = index_relation.relam
     where index_row.indrelid =
           'public.guest_network_message_events'::regclass
       and access_method.amname = 'btree'
       and (
         (
           index_relation.relname =
             'guest_network_message_events_network_window_idx'
           and index_row.indnkeyatts = 3
           and index_row.indnatts = 3
           and pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true) =
             'network_key_hash'
           and pg_catalog.pg_get_indexdef(index_row.indexrelid, 2, true) =
             'created_at'
           and pg_catalog.pg_get_indexdef(index_row.indexrelid, 3, true) =
             'receipt_id'
         )
         or (
           index_relation.relname =
             'guest_network_message_events_retention_idx'
           and index_row.indnkeyatts = 2
           and index_row.indnatts = 2
           and pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true) =
             'created_at'
           and pg_catalog.pg_get_indexdef(index_row.indexrelid, 2, true) =
             'receipt_id'
         )
       )
  ),
  'a quota or retention index is missing or drifted'
);
select pg_temp.assert_true(
  (
    select pg_catalog.pg_get_userbyid(table_row.relowner) = 'postgres'
       and table_row.relkind = 'r'
       and table_row.relpersistence = 'p'
       and table_row.relrowsecurity
       and not table_row.relforcerowsecurity
      from pg_catalog.pg_class as table_row
     where table_row.oid = 'public.guest_network_message_events'::regclass
  ),
  'the network receipt table kind, owner, or RLS contract drifted'
);
select pg_temp.assert_true(
  not exists (
    select 1
      from pg_catalog.pg_attribute as attribute_row
     where attribute_row.attrelid =
           'public.guest_network_message_events'::regclass
       and attribute_row.attnum > 0
       and not attribute_row.attisdropped
       and attribute_row.attacl is not null
  )
  and not exists (
    select 1
      from pg_catalog.pg_policy as policy_row
     where policy_row.polrelid =
           'public.guest_network_message_events'::regclass
  )
  and not exists (
    select 1
      from pg_catalog.pg_rewrite as rewrite_row
     where rewrite_row.ev_class =
           'public.guest_network_message_events'::regclass
  ),
  'the network receipt table retained a column ACL, policy, or rule'
);
select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 4
       and pg_catalog.count(*) filter (
         where trigger_row.tgenabled <> 'O'
            or not trigger_row.tgisinternal
       ) = 0
      from pg_catalog.pg_trigger as trigger_row
      join pg_catalog.pg_constraint as constraint_row
        on constraint_row.oid = trigger_row.tgconstraint
     where constraint_row.conrelid =
           'public.guest_network_message_events'::regclass
       and constraint_row.conname =
           'guest_network_message_events_usage_event_id_fkey'
       and constraint_row.contype = 'f'
  )
  and (
    select pg_catalog.count(*) = 2
       and pg_catalog.count(*) filter (
         where trigger_row.tgenabled <> 'O'
            or not trigger_row.tgisinternal
            or constraint_row.conname <>
               'guest_network_message_events_usage_event_id_fkey'
            or constraint_row.contype <> 'f'
       ) = 0
      from pg_catalog.pg_trigger as trigger_row
      left join pg_catalog.pg_constraint as constraint_row
        on constraint_row.oid = trigger_row.tgconstraint
     where trigger_row.tgrelid =
           'public.guest_network_message_events'::regclass
  ),
  'the network receipt foreign-key trigger contract drifted'
);
select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 8
       and pg_catalog.bool_and(
         grantee_role.rolname = 'postgres'
         and grantor_role.rolname = 'postgres'
         and not acl_row.is_grantable
       )
      from pg_catalog.pg_class as table_row
      cross join lateral pg_catalog.aclexplode(
        coalesce(
          table_row.relacl,
          pg_catalog.acldefault('r', table_row.relowner)
        )
      ) as acl_row
      left join pg_catalog.pg_roles as grantee_role
        on grantee_role.oid = acl_row.grantee
      left join pg_catalog.pg_roles as grantor_role
        on grantor_role.oid = acl_row.grantor
     where table_row.oid =
           'public.guest_network_message_events'::regclass
  ),
  'the network receipt table ACL is not postgres-only'
);
select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 3
       and pg_catalog.bool_and(
         pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
         and language_row.lanname = 'plpgsql'
         and function_row.prokind = 'f'
         and function_row.prosecdef
         and not function_row.proleakproof
         and function_row.provolatile = 'v'
         and function_row.proparallel = 'u'
         and function_row.proconfig = array['search_path=""']::text[]
         and acl_contract.is_exact
       )
      from (
        values
          ('public.reserve_free_message_v2(uuid,uuid,text,text)'),
          ('public.refund_usage_event_v2(uuid,uuid)'),
          ('public.purge_guest_network_message_events_v1()')
      ) as expected(signature)
      join pg_catalog.pg_proc as function_row
        on function_row.oid = pg_catalog.to_regprocedure(expected.signature)
      join pg_catalog.pg_language as language_row
        on language_row.oid = function_row.prolang
      cross join lateral (
        select pg_catalog.count(*) = 2
          and pg_catalog.count(*) filter (
            where grantee_role.rolname = 'postgres'
              and grantor_role.rolname = 'postgres'
              and acl_row.privilege_type = 'EXECUTE'
              and not acl_row.is_grantable
          ) = 1
          and pg_catalog.count(*) filter (
            where grantee_role.rolname = 'service_role'
              and grantor_role.rolname = 'postgres'
              and acl_row.privilege_type = 'EXECUTE'
              and not acl_row.is_grantable
          ) = 1 as is_exact
          from pg_catalog.aclexplode(
            coalesce(
              function_row.proacl,
              pg_catalog.acldefault('f', function_row.proowner)
            )
          ) as acl_row
          left join pg_catalog.pg_roles as grantee_role
            on grantee_role.oid = acl_row.grantee
          left join pg_catalog.pg_roles as grantor_role
            on grantor_role.oid = acl_row.grantor
      ) as acl_contract
  ),
  'the reservation or purge RPC owner, execution, search-path, or ACL drifted'
);
select pg_temp.assert_true(
  (
    select count(*) = 1
      from cron.job
     where jobname = 'askcrump_guest_network_retention_v1'
       and schedule = '*/15 * * * *'
       and command =
         'select * from public.purge_guest_network_message_events_v1();'
       and database = current_database()
       and username = current_user
       and nodename = 'localhost'
       and nodeport = pg_catalog.inet_server_port()
       and active is true
  ),
  'the database-native retention job is absent, duplicated, or changed'
);

select pg_temp.assert_true(
  pg_catalog.has_function_privilege(
    'service_role',
    'public.reserve_free_message_v1(uuid,uuid,text)',
    'EXECUTE'
  )
  and pg_catalog.has_function_privilege(
    'service_role',
    'public.reserve_free_message_v2(uuid,uuid,text,text)',
    'EXECUTE'
  )
  and pg_catalog.has_function_privilege(
    'service_role',
    'public.refund_usage_event_v2(uuid,uuid)',
    'EXECUTE'
  )
  and pg_catalog.has_function_privilege(
    'service_role',
    'public.purge_guest_network_message_events_v1()',
    'EXECUTE'
  ),
  'the service role is missing an intended reservation or purge RPC'
);
select pg_temp.assert_true(
  not pg_catalog.has_function_privilege(
    'anon', 'public.reserve_free_message_v2(uuid,uuid,text,text)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated', 'public.reserve_free_message_v2(uuid,uuid,text,text)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'anon', 'public.refund_usage_event_v2(uuid,uuid)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated', 'public.refund_usage_event_v2(uuid,uuid)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'anon', 'public.purge_guest_network_message_events_v1()', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated', 'public.purge_guest_network_message_events_v1()', 'EXECUTE'
  ),
  'a browser API role can execute the reservation or retention RPC'
);
select pg_temp.assert_true(
  not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_network_message_events', 'SELECT'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_network_message_events', 'INSERT'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_network_message_events', 'UPDATE'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_network_message_events', 'DELETE'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_network_message_events', 'TRUNCATE'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_network_message_events', 'REFERENCES'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_network_message_events', 'TRIGGER'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.guest_network_message_events', 'MAINTAIN'
  )
  and not pg_catalog.has_table_privilege(
    'anon', 'public.guest_network_message_events', 'SELECT'
  )
  and not pg_catalog.has_table_privilege(
    'anon', 'public.guest_network_message_events', 'INSERT'
  )
  and not pg_catalog.has_table_privilege(
    'anon', 'public.guest_network_message_events', 'UPDATE'
  )
  and not pg_catalog.has_table_privilege(
    'anon', 'public.guest_network_message_events', 'DELETE'
  )
  and not pg_catalog.has_table_privilege(
    'authenticated', 'public.guest_network_message_events', 'SELECT'
  )
  and not pg_catalog.has_table_privilege(
    'authenticated', 'public.guest_network_message_events', 'INSERT'
  )
  and not pg_catalog.has_table_privilege(
    'authenticated', 'public.guest_network_message_events', 'UPDATE'
  )
  and not pg_catalog.has_table_privilege(
    'authenticated', 'public.guest_network_message_events', 'DELETE'
  ),
  'the network receipt table is directly accessible'
);

-- Enable the release control before creating disposable guest identities.
set role service_role;
select * from public.set_guest_mode_enabled_v1(true);
reset role;

insert into public.users (id, is_guest)
select
  ('a2000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  true
from pg_catalog.generate_series(1, 30) as series;
insert into public.users (id, is_guest)
values
  ('b2000000-0000-4000-8000-000000000001', false),
  ('c2000000-0000-4000-8000-000000000001', true),
  ('e2000000-0000-4000-8000-000000000001', true),
  ('e2000000-0000-4000-8000-000000000002', true);

-- Registered Free callers preserve v1 behavior: no network identifier, lock,
-- budget, or child receipt is required.
set role service_role;
create temporary table registered_result as
select * from public.reserve_free_message_v2(
  'b2000000-0000-4000-8000-000000000001',
  'b2100000-0000-4000-8000-000000000001',
  repeat('1', 64),
  null
);
create temporary table registered_replay_result as
select * from public.reserve_free_message_v2(
  'b2000000-0000-4000-8000-000000000001',
  'b2100000-0000-4000-8000-000000000001',
  repeat('1', 64),
  null
);
reset role;
select pg_temp.assert_true(
  (
    select outcome = 'reserved'
       and event_id is not null
       and used = 1
       and remaining = 4
       and network_used is null
       and network_remaining is null
       and network_next_available_at is null
      from registered_result
  )
  and (
    select outcome = 'reused'
       and event_id is null
       and used = 1
       and network_used is null
      from registered_replay_result
  )
  and not exists (
    select 1
      from public.guest_network_message_events as network_event
      join public.usage_events as usage
        on usage.id = network_event.usage_event_id
     where usage.user_id = 'b2000000-0000-4000-8000-000000000001'
  ),
  'a registered Free reservation entered the guest network budget'
);

-- A guest fails closed when the server does not supply a valid lowercase
-- digest. Neither validation failure may consume the account allowance.
set role service_role;
do $invalid_guest_hashes$
begin
  begin
    perform * from public.reserve_free_message_v2(
      'a2000000-0000-4000-8000-000000000029',
      'a2100000-0000-4000-8000-000000000001',
      repeat('2', 64),
      null
    );
    raise exception 'a missing guest network key was accepted';
  exception when sqlstate '22023' then
    null;
  end;

  begin
    perform * from public.reserve_free_message_v2(
      'a2000000-0000-4000-8000-000000000030',
      'a2100000-0000-4000-8000-000000000002',
      repeat('3', 64),
      repeat('G', 64)
    );
    raise exception 'an invalid guest network key was accepted';
  exception when sqlstate '22023' then
    null;
  end;
end;
$invalid_guest_hashes$;
reset role;
select pg_temp.assert_true(
  not exists (
    select 1 from public.usage_events
     where user_id in (
       'a2000000-0000-4000-8000-000000000029',
       'a2000000-0000-4000-8000-000000000030'
     )
  ),
  'invalid guest network keys consumed an account receipt'
);

-- Twenty-five different guest accounts share one privacy-minimized network
-- budget. The twenty-sixth account keeps all five account slots but is denied.
set role service_role;
create temporary table shared_network_results (
  sequence integer,
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz,
  network_used integer,
  network_remaining integer,
  network_next_available_at timestamptz
);
insert into shared_network_results
select series, result.*
from pg_catalog.generate_series(1, 25) as series
cross join lateral public.reserve_free_message_v2(
  ('a2000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  ('d2000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  pg_catalog.encode(digest('shared-network-' || series::text, 'sha256'), 'hex'),
  repeat('a', 64)
) as result;
create temporary table shared_network_denial as
select * from public.reserve_free_message_v2(
  'a2000000-0000-4000-8000-000000000026',
  'd2000000-0000-4000-8000-000000000026',
  pg_catalog.encode(digest('shared-network-26', 'sha256'), 'hex'),
  repeat('a', 64)
);
create temporary table shared_network_replay as
select * from public.reserve_free_message_v2(
  'a2000000-0000-4000-8000-000000000025',
  'd2000000-0000-4000-8000-000000000025',
  pg_catalog.encode(digest('shared-network-25', 'sha256'), 'hex'),
  repeat('a', 64)
);
create temporary table separate_network_result as
select * from public.reserve_free_message_v2(
  'a2000000-0000-4000-8000-000000000026',
  'd2000000-0000-4000-8000-000000000027',
  pg_catalog.encode(digest('separate-network-26', 'sha256'), 'hex'),
  repeat('b', 64)
);
reset role;

select pg_temp.assert_true(
  not exists (
    select 1 from shared_network_results
     where outcome <> 'reserved'
        or event_id is null
        or used <> 1
        or remaining <> 4
        or network_used <> sequence
        or network_remaining <> 25 - sequence
  ),
  'the first twenty-five shared-network messages were not reserved exactly once'
);
select pg_temp.assert_true(
  (
    select outcome = 'network_exhausted'
       and event_id is null
       and used = 0
       and remaining = 5
       and next_available_at is null
       and network_used = 25
       and network_remaining = 0
       and network_next_available_at is not null
      from shared_network_denial
  ),
  'the twenty-sixth shared-network message was not denied at the network cap'
);
select pg_temp.assert_true(
  (
    select outcome = 'reused'
       and event_id is null
       and used = 1
       and remaining = 4
       and network_used = 25
       and network_remaining = 0
       and network_next_available_at is not null
      from shared_network_replay
  )
  and (
    select outcome = 'reserved'
       and event_id is not null
       and used = 1
       and network_used = 1
       and network_remaining = 24
      from separate_network_result
  ),
  'replay at the cap or an independent network was incorrectly denied'
);
select pg_temp.assert_true(
  (
    select count(*) = 25
      from public.guest_network_message_events
     where network_key_hash = repeat('a', 64)
  )
  and (
    select count(*) = 1
      from public.guest_network_message_events
     where network_key_hash = repeat('b', 64)
  ),
  'a denial or replay inserted another network receipt'
);

-- The public account-deletion path removes identifiable account receipts but
-- must not replenish the short-lived network budget. This models the exact
-- register-in-place -> delete-account -> new-guest bypass: the first receipt
-- becomes an orphan containing only its opaque receipt id, keyed digest, and
-- timestamp, and the twenty-sixth guest remains denied.
insert into public.users (id, is_guest)
select
  ('92000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  true
from pg_catalog.generate_series(1, 26) as series;
set role service_role;
create temporary table deletion_invariance_seed as
select series, result.*
from pg_catalog.generate_series(1, 25) as series
cross join lateral public.reserve_free_message_v2(
  ('92000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  ('92100000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  pg_catalog.encode(
    public.digest('deletion-invariance-' || series::text, 'sha256'),
    'hex'
  ),
  repeat('8', 64)
) as result;
reset role;
-- These are the exact relevant statements in delete_user_account: usage rows
-- are removed before the owning user row.
delete from public.usage_events
 where user_id = '92000000-0000-4000-8000-000000000001';
delete from public.users
 where id = '92000000-0000-4000-8000-000000000001';
set role service_role;
create temporary table deletion_invariance_denial as
select * from public.reserve_free_message_v2(
  '92000000-0000-4000-8000-000000000026',
  '92100000-0000-4000-8000-000000000026',
  repeat('8', 64),
  repeat('8', 64)
);
reset role;
select pg_temp.assert_true(
  not exists (
    select 1 from deletion_invariance_seed where outcome <> 'reserved'
  )
  and not exists (
    select 1 from public.users
     where id = '92000000-0000-4000-8000-000000000001'
  )
  and not exists (
    select 1 from public.usage_events
     where user_id = '92000000-0000-4000-8000-000000000001'
  )
  and (
    select count(*) = 25
       and count(*) filter (where usage_event_id is null) = 1
      from public.guest_network_message_events
     where network_key_hash = repeat('8', 64)
  )
  and (
    select outcome = 'network_exhausted'
       and event_id is null
       and used = 0
       and remaining = 5
       and network_used = 25
       and network_remaining = 0
      from deletion_invariance_denial
  ),
  'account deletion restored network capacity or retained an account link'
);

-- If account deletion wins a real row-lock race, a waiting refund must return
-- false and leave the now-orphaned receipt in the network budget. This avoids
-- a narrow delete/refund interleaving becoming another capacity reset.
insert into public.users (id, is_guest)
values
  ('93000000-0000-4000-8000-000000000001', true),
  ('93000000-0000-4000-8000-000000000002', true);
set role service_role;
create temporary table deletion_race_reservation as
select * from public.reserve_free_message_v2(
  '93000000-0000-4000-8000-000000000001',
  '93100000-0000-4000-8000-000000000001',
  repeat('7', 64),
  repeat('7', 64)
);
reset role;
select public.dblink_connect(
  'guest_network_delete_winner',
  pg_catalog.format(
    'dbname=%L user=%L port=%L application_name=%L',
    current_database(),
    current_user,
    current_setting('port'),
    'guest-network-delete-winner'
  )
);
select public.dblink_connect(
  'guest_network_refund_waiter',
  pg_catalog.format(
    'dbname=%L user=%L port=%L application_name=%L',
    current_database(),
    current_user,
    current_setting('port'),
    'guest-network-refund-waiter'
  )
);
select public.dblink_exec('guest_network_delete_winner', 'begin');
select public.dblink_exec(
  'guest_network_delete_winner',
  $command$
    do $delete$
    begin
      delete from public.usage_events
       where user_id = '93000000-0000-4000-8000-000000000001';
      delete from public.users
       where id = '93000000-0000-4000-8000-000000000001';
    end;
    $delete$;
  $command$
);
select public.dblink_exec('guest_network_refund_waiter', 'set role service_role');
select public.dblink_send_query(
  'guest_network_refund_waiter',
  pg_catalog.format(
    'select * from public.refund_usage_event_v2(%L::uuid, %L::uuid)',
    '93000000-0000-4000-8000-000000000001',
    (select event_id::text from deletion_race_reservation)
  )
);
do $wait_for_delete_refund_race$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'guest-network-refund-waiter'
         and wait_event_type = 'Lock'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;

  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'guest-network-refund-waiter'
       and wait_event_type = 'Lock'
  ) then
    raise exception 'the refund did not wait behind account deletion';
  end if;
end;
$wait_for_delete_refund_race$;
select public.dblink_exec('guest_network_delete_winner', 'commit');
create temporary table deletion_race_refund as
select *
from public.dblink_get_result('guest_network_refund_waiter')
  as result(refunded boolean);
select public.dblink_disconnect('guest_network_delete_winner');
select public.dblink_disconnect('guest_network_refund_waiter');
set role service_role;
create temporary table deletion_race_followup as
select * from public.reserve_free_message_v2(
  '93000000-0000-4000-8000-000000000002',
  '93100000-0000-4000-8000-000000000002',
  repeat('6', 64),
  repeat('7', 64)
);
reset role;
select pg_temp.assert_true(
  (select refunded is false from deletion_race_refund)
  and (
    select count(*) = 2
       and count(*) filter (where usage_event_id is null) = 1
      from public.guest_network_message_events
     where network_key_hash = repeat('7', 64)
  )
  and (
    select outcome = 'reserved'
       and network_used = 2
       and network_remaining = 23
      from deletion_race_followup
  ),
  'a concurrent account deletion and refund released network capacity'
);

-- Two different guest accounts compete for the final shared-network slot.
-- Connection A owns the exact network advisory lock, B queues behind it, A
-- reserves slot 25 and commits, then B must observe the committed receipt and
-- exhaust. This proves the aggregate check and insert are one serialized
-- decision rather than two independent reads at the 25/26 boundary.
set role service_role;
create temporary table concurrent_network_seed_results (
  sequence integer,
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz,
  network_used integer,
  network_remaining integer,
  network_next_available_at timestamptz
);
insert into concurrent_network_seed_results
select series, result.*
from pg_catalog.generate_series(1, 24) as series
cross join lateral public.reserve_free_message_v2(
  ('a2000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  ('f2000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  pg_catalog.encode(
    public.digest('concurrent-network-' || series::text, 'sha256'),
    'hex'
  ),
  repeat('f', 64)
) as result;
reset role;
select pg_temp.assert_true(
  not exists (
    select 1
      from concurrent_network_seed_results
     where outcome <> 'reserved'
        or event_id is null
        or network_used <> sequence
        or network_remaining <> 25 - sequence
  )
  and (
    select count(*) = 24
      from public.guest_network_message_events
     where network_key_hash = repeat('f', 64)
  ),
  'the concurrent network fixture did not establish exactly 24 receipts'
);

select public.dblink_connect(
  'guest_network_a',
  pg_catalog.format(
    'dbname=%L user=%L port=%L application_name=%L',
    current_database(),
    current_user,
    current_setting('port'),
    'guest-network-a'
  )
);
select public.dblink_connect(
  'guest_network_b',
  pg_catalog.format(
    'dbname=%L user=%L port=%L application_name=%L',
    current_database(),
    current_user,
    current_setting('port'),
    'guest-network-b'
  )
);
select public.dblink_exec('guest_network_a', 'begin');
select public.dblink_exec(
  'guest_network_a',
  $command$
    do $lock$
    begin
      perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
          'usage:guest-network:' || repeat('f', 64) || ':messages',
          0
        )
      );
    end;
    $lock$;
  $command$
);
select public.dblink_exec('guest_network_a', 'set role service_role');
select public.dblink_exec('guest_network_b', 'set role service_role');
select public.dblink_send_query(
  'guest_network_b',
  $query$
    select * from public.reserve_free_message_v2(
      'a2000000-0000-4000-8000-000000000026',
      'f2100000-0000-4000-8000-000000000002',
      repeat('2', 64),
      repeat('f', 64)
    )
  $query$
);

do $wait_for_network_lock$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'guest-network-b'
         and wait_event_type = 'Lock'
         and wait_event = 'advisory'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;

  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'guest-network-b'
       and wait_event_type = 'Lock'
       and wait_event = 'advisory'
  ) then
    raise exception
      'the competing guest reservation did not reach the network advisory lock';
  end if;
end;
$wait_for_network_lock$;

create temporary table concurrent_network_results (
  caller text,
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz,
  network_used integer,
  network_remaining integer,
  network_next_available_at timestamptz
);
insert into concurrent_network_results
select 'a', result.*
from public.dblink(
  'guest_network_a',
  $query$
    select * from public.reserve_free_message_v2(
      'a2000000-0000-4000-8000-000000000025',
      'f2100000-0000-4000-8000-000000000001',
      repeat('1', 64),
      repeat('f', 64)
    )
  $query$
) as result(
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz,
  network_used integer,
  network_remaining integer,
  network_next_available_at timestamptz
);
select public.dblink_exec('guest_network_a', 'commit');
insert into concurrent_network_results
select 'b', result.*
from public.dblink_get_result('guest_network_b') as result(
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz,
  network_used integer,
  network_remaining integer,
  network_next_available_at timestamptz
);
select pg_temp.assert_true(
  (
    select count(*) = 1
      from concurrent_network_results
     where outcome = 'reserved'
       and event_id is not null
       and network_used = 25
       and network_remaining = 0
  )
  and (
    select count(*) = 1
      from concurrent_network_results
     where outcome = 'network_exhausted'
       and event_id is null
       and network_used = 25
       and network_remaining = 0
  )
  and (
    select count(*) = 25
      from public.guest_network_message_events
     where network_key_hash = repeat('f', 64)
  ),
  'concurrent accounts did not authorize exactly one twenty-fifth network receipt'
);
select public.dblink_disconnect('guest_network_a');
select public.dblink_disconnect('guest_network_b');

-- A network waiter that begins while all 25 receipts are current must sample
-- wall time only after it acquires the network lock. The oldest receipt is
-- pinned to expire one second after the waiter's statement starts; after the
-- lock is released, the waiter must own the newly opened twenty-fifth slot.
insert into public.usage_events (
  id, user_id, event_type, idempotency_key, created_at
)
select
  ('f3000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  ('a2000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  'messages',
  'network-boundary-seed-' || series::text,
  pg_catalog.clock_timestamp() - series * interval '1 second'
from pg_catalog.generate_series(1, 25) as series;
insert into public.guest_network_message_events (
  usage_event_id, network_key_hash, created_at
)
select
  ('f3000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  repeat('9', 64),
  pg_catalog.clock_timestamp() - series * interval '1 second'
from pg_catalog.generate_series(1, 25) as series;

select public.dblink_connect(
  'guest_network_boundary_lock',
  pg_catalog.format(
    'dbname=%L user=%L port=%L application_name=%L',
    current_database(),
    current_user,
    current_setting('port'),
    'guest-network-boundary-lock'
  )
);
select public.dblink_connect(
  'guest_network_boundary_waiter',
  pg_catalog.format(
    'dbname=%L user=%L port=%L application_name=%L',
    current_database(),
    current_user,
    current_setting('port'),
    'guest-network-boundary-waiter'
  )
);
select public.dblink_exec('guest_network_boundary_lock', 'begin');
select public.dblink_exec(
  'guest_network_boundary_lock',
  $command$
    do $lock$
    begin
      perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
          'usage:guest-network:' || repeat('9', 64) || ':messages',
          0
        )
      );
    end;
    $lock$;
  $command$
);
select public.dblink_exec(
  'guest_network_boundary_waiter',
  'set role service_role'
);
select public.dblink_send_query(
  'guest_network_boundary_waiter',
  $query$
    select * from public.reserve_free_message_v2(
      'a2000000-0000-4000-8000-000000000027',
      'f4100000-0000-4000-8000-000000000001',
      repeat('7', 64),
      repeat('9', 64)
    )
  $query$
);

do $wait_for_network_boundary_lock$
declare
  attempts integer;
begin
  for attempts in 1..100 loop
    exit when exists (
      select 1
        from pg_catalog.pg_stat_activity
       where application_name = 'guest-network-boundary-waiter'
         and wait_event_type = 'Lock'
         and wait_event = 'advisory'
    );
    perform pg_catalog.pg_sleep(0.05);
  end loop;

  if not exists (
    select 1
      from pg_catalog.pg_stat_activity
     where application_name = 'guest-network-boundary-waiter'
       and wait_event_type = 'Lock'
       and wait_event = 'advisory'
  ) then
    raise exception
      'the boundary guest reservation did not reach the network advisory lock';
  end if;
end;
$wait_for_network_boundary_lock$;

create temporary table network_boundary_waiter_start as
select activity.query_start
  from pg_catalog.pg_stat_activity as activity
 where activity.application_name = 'guest-network-boundary-waiter';
update public.guest_network_message_events as network_event
   set created_at = network_boundary_waiter_start.query_start
       - interval '24 hours'
       + interval '1 second'
  from network_boundary_waiter_start
 where network_event.usage_event_id =
       'f3000000-0000-4000-8000-000000000025';

select pg_temp.assert_true(
  exists (
    select 1
      from pg_catalog.pg_stat_activity as activity
      join public.guest_network_message_events as network_event
        on network_event.usage_event_id =
           'f3000000-0000-4000-8000-000000000025'
     where activity.application_name = 'guest-network-boundary-waiter'
       and activity.query_start < network_event.created_at + interval '24 hours'
  ),
  'the network boundary waiter did not begin before the oldest receipt expired'
);
select pg_catalog.pg_sleep(
  greatest(
    pg_catalog.date_part(
      'epoch',
      (
        (
          select query_start + interval '1.25 seconds'
            from network_boundary_waiter_start
        ) - pg_catalog.clock_timestamp()
      )
    ),
    0.25
  )
);
create temporary table network_boundary_release as
select pg_catalog.clock_timestamp() as released_at;
select public.dblink_exec('guest_network_boundary_lock', 'commit');

create temporary table network_boundary_result as
select result.*
from public.dblink_get_result('guest_network_boundary_waiter') as result(
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz,
  network_used integer,
  network_remaining integer,
  network_next_available_at timestamptz
);
select pg_temp.assert_true(
  (
    select outcome = 'reserved'
       and event_id is not null
       and used = 1
       and remaining = 4
       and network_used = 25
       and network_remaining = 0
      from network_boundary_result
  ),
  'a network waiter did not claim the slot that opened while it was blocked'
);
select pg_temp.assert_true(
  (
    select network_event.created_at >= network_boundary_release.released_at
      from network_boundary_result
      join public.guest_network_message_events as network_event
        on network_event.usage_event_id = network_boundary_result.event_id
      cross join network_boundary_release
  )
  and (
    select count(*) = 25
      from public.guest_network_message_events
     where network_key_hash = repeat('9', 64)
       and created_at > pg_catalog.clock_timestamp() - interval '24 hours'
  ),
  'the post-lock network receipt was backdated or overfilled the rolling window'
);
select public.dblink_disconnect('guest_network_boundary_lock');
select public.dblink_disconnect('guest_network_boundary_waiter');

-- The original five-message account cap still wins even when the network has
-- capacity, and its sixth call creates neither ledger row.
set role service_role;
create temporary table account_cap_results (
  sequence integer,
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz,
  network_used integer,
  network_remaining integer,
  network_next_available_at timestamptz
);
insert into account_cap_results
select series, result.*
from pg_catalog.generate_series(1, 6) as series
cross join lateral public.reserve_free_message_v2(
  'c2000000-0000-4000-8000-000000000001',
  ('d3000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  pg_catalog.encode(digest('account-cap-' || series::text, 'sha256'), 'hex'),
  repeat('c', 64)
) as result;
reset role;
select pg_temp.assert_true(
  (
    select count(*) = 5
      from account_cap_results
     where sequence <= 5
       and outcome = 'reserved'
       and event_id is not null
  )
  and (
    select outcome = 'exhausted'
       and event_id is null
       and used = 5
       and remaining = 0
       and next_available_at is not null
       and network_used = 5
       and network_remaining = 20
      from account_cap_results
     where sequence = 6
  )
  and (
    select count(*) = 5
      from public.guest_network_message_events
     where network_key_hash = repeat('c', 64)
  ),
  'v2 weakened the five-message account cap'
);

-- A confirmed service-only refund is distinct from account deletion: it row-
-- locks the exactly owned parent and optional child, deletes the parent first,
-- then removes the exact detached child in the same transaction and restores
-- precisely one network slot. A repeated refund is
-- explicitly unconfirmed and cannot remove an orphan account-deletion receipt.
set role service_role;
create temporary table refund_reservation as
select * from public.reserve_free_message_v2(
  'e2000000-0000-4000-8000-000000000001',
  'e2100000-0000-4000-8000-000000000001',
  repeat('4', 64),
  repeat('d', 64)
);
create temporary table confirmed_refund as
select * from public.refund_usage_event_v2(
  'e2000000-0000-4000-8000-000000000001',
  (select event_id from refund_reservation)
);
create temporary table repeated_refund as
select * from public.refund_usage_event_v2(
  'e2000000-0000-4000-8000-000000000001',
  (select event_id from refund_reservation)
);
create temporary table post_refund_reservation as
select * from public.reserve_free_message_v2(
  'e2000000-0000-4000-8000-000000000001',
  'e2100000-0000-4000-8000-000000000002',
  repeat('5', 64),
  repeat('d', 64)
);
reset role;
select pg_temp.assert_true(
  (select refunded is true from confirmed_refund)
  and (select refunded is false from repeated_refund)
  and not exists (
    select 1
      from public.guest_network_message_events
     where usage_event_id = (select event_id from refund_reservation)
  )
  and not exists (
    select 1
      from public.usage_events
     where id = (select event_id from refund_reservation)
  )
  and (
    select outcome = 'reserved'
       and event_id is not null
       and used = 1
       and network_used = 1
       and network_remaining = 24
      from post_refund_reservation
  ),
  'the explicit refund path did not restore exactly one owned network slot'
);

-- The privacy sweep drains more than one 10,000-row batch, skips a concurrently
-- locked expired receipt without blocking, reports that remainder, and removes
-- it on the next invocation. A current receipt and every durable account
-- receipt remain. The 25-hour cutoff is safely beyond the 24-hour quota window.
insert into public.usage_events (
  id, user_id, event_type, idempotency_key, created_at
)
select
  ('e2300000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  'e2000000-0000-4000-8000-000000000002'::uuid,
  'messages',
  'retention-expired-' || series::text,
  pg_catalog.clock_timestamp() - interval '26 hours'
from pg_catalog.generate_series(1, 10002) as series;
insert into public.usage_events (
  id, user_id, event_type, idempotency_key, created_at
) values (
  'e2400000-0000-4000-8000-000000000001',
  'e2000000-0000-4000-8000-000000000002',
  'messages',
  'retention-current',
  pg_catalog.clock_timestamp() - interval '24 hours 30 minutes'
);
insert into public.guest_network_message_events (
  usage_event_id, network_key_hash, created_at
) select
  ('e2300000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  repeat('e', 64),
  pg_catalog.clock_timestamp() - interval '26 hours'
from pg_catalog.generate_series(1, 10002) as series;
insert into public.guest_network_message_events (
  usage_event_id, network_key_hash, created_at
) values (
  'e2400000-0000-4000-8000-000000000001',
  repeat('e', 64),
  pg_catalog.clock_timestamp() - interval '24 hours 30 minutes'
);

select public.dblink_connect(
  'guest_network_retention_lock',
  pg_catalog.format(
    'dbname=%L user=%L port=%L application_name=%L',
    current_database(),
    current_user,
    current_setting('port'),
    'guest-network-retention-lock'
  )
);
select public.dblink_exec('guest_network_retention_lock', 'begin');
select * from public.dblink(
  'guest_network_retention_lock',
  $query$
    select usage_event_id::text
      from public.guest_network_message_events
     where usage_event_id = 'e2300000-0000-4000-8000-000000000001'
     for update
  $query$
) as locked(usage_event_id text);

set role service_role;
create temporary table first_purge as
select * from public.purge_guest_network_message_events_v1();
reset role;
select public.dblink_exec('guest_network_retention_lock', 'commit');
select public.dblink_disconnect('guest_network_retention_lock');
set role service_role;
create temporary table second_purge as
select * from public.purge_guest_network_message_events_v1();
create temporary table third_purge as
select * from public.purge_guest_network_message_events_v1();
reset role;
select pg_temp.assert_true(
  (select deleted_count = 10001 and has_more is true from first_purge)
  and (select deleted_count = 1 and has_more is false from second_purge)
  and (select deleted_count = 0 and has_more is false from third_purge)
  and not exists (
    select 1 from public.guest_network_message_events
     where usage_event_id::text like 'e2300000-%'
  )
  and exists (
    select 1 from public.guest_network_message_events
     where usage_event_id = 'e2400000-0000-4000-8000-000000000001'
  )
  and (
    select count(*) = 10003
      from public.usage_events
     where id::text like 'e2300000-%'
        or id = 'e2400000-0000-4000-8000-000000000001'
  ),
  'the 25-hour privacy sweep failed to drain, skip locks, or preserve account receipts'
);

-- Leave the shared disposable database in the state expected by the existing
-- guest-control fixture.
delete from public.users
 where id::text like 'a2000000-%'
    or id::text like 'b2000000-%'
    or id::text like 'c2000000-%'
    or id::text like 'e2000000-%'
    or id::text like '92000000-%'
    or id::text like '93000000-%';
set role service_role;
select * from public.set_guest_mode_enabled_v1(false);
reset role;
