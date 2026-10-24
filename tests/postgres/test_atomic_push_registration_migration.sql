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
    raise exception 'Atomic push-registration gate failed: %', failure_message;
  end if;
end;
$$;

select pg_temp.assert_true(
  (
    select function_row.prosecdef
      and function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
    from pg_catalog.pg_proc as function_row
    where function_row.oid =
      'public.mutate_push_registration_v1(uuid,uuid,text,text,text,text,boolean,timestamptz)'::regprocedure
  ),
  'RPC owner, definer, volatility, or search_path drifted'
);

select pg_temp.assert_true(
  has_function_privilege(
    'service_role',
    'public.mutate_push_registration_v1(uuid,uuid,text,text,text,text,boolean,timestamptz)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'anon',
    'public.mutate_push_registration_v1(uuid,uuid,text,text,text,text,boolean,timestamptz)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated',
    'public.mutate_push_registration_v1(uuid,uuid,text,text,text,text,boolean,timestamptz)',
    'EXECUTE'
  ),
  'RPC must be service-role-only'
);

select pg_temp.assert_true(
  (
    select not function_row.prosecdef
      and function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
      and not has_function_privilege(
        'service_role', 'public.disable_stale_installation_push_v1()', 'EXECUTE'
      )
      and not has_function_privilege(
        'anon', 'public.disable_stale_installation_push_v1()', 'EXECUTE'
      )
      and not has_function_privilege(
        'authenticated', 'public.disable_stale_installation_push_v1()', 'EXECUTE'
      )
    from pg_catalog.pg_proc as function_row
    where function_row.oid = 'public.disable_stale_installation_push_v1()'::regprocedure
  ),
  'session-rotation push scrub owner, invoker, volatility, search_path, or ACL drifted'
);

select pg_temp.assert_true(
  (
    select not function_row.prosecdef
      and function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
      and not has_function_privilege(
        'service_role', 'public.stamp_legacy_push_registration_v1()', 'EXECUTE'
      )
      and not has_function_privilege(
        'anon', 'public.stamp_legacy_push_registration_v1()', 'EXECUTE'
      )
      and not has_function_privilege(
        'authenticated', 'public.stamp_legacy_push_registration_v1()', 'EXECUTE'
      )
    from pg_catalog.pg_proc as function_row
    where function_row.oid = 'public.stamp_legacy_push_registration_v1()'::regprocedure
  ),
  'legacy push-stamp owner, invoker, volatility, search_path, or ACL drifted'
);

select pg_temp.assert_true(
  (
    select trigger_row.tgenabled = 'O'
      and not trigger_row.tgisinternal
      and trigger_row.tgfoid = 'public.disable_stale_installation_push_v1()'::regprocedure
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid = 'public.sessions'::regclass
      and trigger_row.tgname = 'disable_stale_installation_push'
  ),
  'session-rotation push scrub trigger is absent or drifted'
);

select pg_temp.assert_true(
  (
    select trigger_row.tgenabled = 'O'
      and not trigger_row.tgisinternal
      and trigger_row.tgfoid =
        'public.stamp_legacy_push_registration_v1()'::regprocedure
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid = 'public.push_tokens'::regclass
      and trigger_row.tgname = 'stamp_legacy_push_registration'
  ),
  'legacy push-stamp trigger is absent or drifted'
);

select pg_temp.assert_true(
  (
    select table_row.relrowsecurity
    from pg_catalog.pg_class as table_row
    where table_row.oid = 'public.push_tokens'::regclass
  ),
  'push_tokens RLS changed'
);

select pg_temp.assert_true(
  (
    select index_row.indisvalid
      and index_row.indisready
      and index_row.indrelid = 'public.push_tokens'::regclass
      and not index_row.indisunique
      and index_row.indnkeyatts = 1
      and index_row.indnatts = 1
      and index_row.indpred is null
      and index_row.indexprs is null
      and access_method.amname = 'btree'
      and pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true) =
        'installation_id'
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as index_class
      on index_class.oid = index_row.indexrelid
    join pg_catalog.pg_am as access_method
      on access_method.oid = index_class.relam
    where index_row.indexrelid =
      'public.push_tokens_installation_id_idx'::regclass
  ),
  'installation lookup index is absent or drifted'
);

select pg_temp.assert_true(
  exists (
    select 1
      from pg_catalog.pg_index as index_row
     where index_row.indrelid = 'public.push_tokens'::regclass
       and index_row.indisvalid
       and index_row.indisready
       and pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true) = 'token'
  ),
  'globally unique token lookup lost its existing token-led index'
);

select pg_temp.assert_true(
  (
    select constraint_row.contype = 'c'
      and constraint_row.convalidated
      and pg_catalog.strpos(
            pg_catalog.pg_get_constraintdef(constraint_row.oid),
            'registration_session_id IS NOT NULL'
          ) > 0
      and pg_catalog.strpos(
            pg_catalog.pg_get_constraintdef(constraint_row.oid),
            'registration_session_token_hash IS NOT NULL'
          ) > 0
      and pg_catalog.strpos(
            pg_catalog.pg_get_constraintdef(constraint_row.oid),
            'registration_generation IS NOT NULL'
          ) > 0
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = 'public.push_tokens'::regclass
       and constraint_row.conname = 'push_tokens_enabled_generation_check'
  ),
  'enabled destination generation constraint is absent, unvalidated, or drifted'
);

select pg_temp.assert_true(
  (
    select enabled
      and registration_session_id = '71000000-0000-4000-8000-000000000099'::uuid
      and registration_session_token_hash = repeat('9', 64)
      and registration_generation is not null
      from public.push_tokens
     where id = '73000000-0000-4000-8000-000000000099'::uuid
  ),
  'active legacy destination was not bound to its current server session'
);

select pg_temp.assert_true(
  (
    select not enabled
      and registration_session_id is null
      and registration_session_token_hash is null
      from public.push_tokens
     where id = '73000000-0000-4000-8000-000000000098'::uuid
  ),
  'unbound legacy destination remained enabled'
);

-- Migration-first rollout must remain compatible with the production version
-- immediately preceding the RPC caller.  That version deleted a matching
-- token, then directly upserted an enabled row without generation columns.
insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values (
  '71000000-0000-4000-8000-000000000097',
  '70000000-0000-4000-8000-000000000002',
  repeat('3', 64),
  'installation-mixed-version-current',
  clock_timestamp(),
  clock_timestamp(),
  clock_timestamp() + interval '30 days'
);

set role service_role;
insert into public.push_tokens (
  user_id, installation_id, platform, token, enabled
) values (
  '70000000-0000-4000-8000-000000000002',
  'installation-mixed-version-current',
  'ios',
  repeat('N', 24),
  false
);
delete from public.push_tokens
 where platform = 'ios'
   and token = repeat('N', 24);
insert into public.push_tokens (
  user_id, installation_id, platform, token, enabled, updated_at, last_used_at
) values (
  '70000000-0000-4000-8000-000000000002',
  'installation-mixed-version-current',
  'ios',
  repeat('N', 24),
  true,
  clock_timestamp(),
  clock_timestamp()
)
on conflict (user_id, installation_id) do update
   set platform = excluded.platform,
       token = excluded.token,
       enabled = excluded.enabled,
       updated_at = excluded.updated_at,
       last_used_at = excluded.last_used_at;
reset role;

select pg_temp.assert_true(
  (
    select destination.enabled
      and destination.registration_session_id =
        '71000000-0000-4000-8000-000000000097'::uuid
      and destination.registration_session_token_hash = repeat('3', 64)
      and destination.registration_generation = session_row.created_at
      from public.push_tokens as destination
      join public.sessions as session_row
        on session_row.id = destination.registration_session_id
     where destination.installation_id = 'installation-mixed-version-current'
       and destination.token = repeat('N', 24)
  ),
  'pre-RPC direct upsert did not receive the current locked session generation'
);

-- Exercise the UPDATE half of the legacy upsert after the same installation's
-- session generation rotates.  The session trigger disables the old row; the
-- compatibility trigger must then restamp and safely re-enable the conflict
-- update rather than retaining generation 3 or violating the CHECK.
update public.sessions
   set token_hash = repeat('4', 64),
       created_at = clock_timestamp(),
       last_activity = clock_timestamp(),
       expires_at = clock_timestamp() + interval '30 days'
 where id = '71000000-0000-4000-8000-000000000097';

set role service_role;
delete from public.push_tokens
 where platform = 'ios'
   and token = repeat('P', 24);
insert into public.push_tokens (
  user_id, installation_id, platform, token, enabled, updated_at, last_used_at
) values (
  '70000000-0000-4000-8000-000000000002',
  'installation-mixed-version-current',
  'ios',
  repeat('P', 24),
  true,
  clock_timestamp(),
  clock_timestamp()
)
on conflict (user_id, installation_id) do update
   set platform = excluded.platform,
       token = excluded.token,
       enabled = excluded.enabled,
       updated_at = excluded.updated_at,
       last_used_at = excluded.last_used_at;
reset role;

select pg_temp.assert_true(
  (
    select destination.enabled
      and destination.token = repeat('P', 24)
      and destination.registration_session_id =
        '71000000-0000-4000-8000-000000000097'::uuid
      and destination.registration_session_token_hash = repeat('4', 64)
      and destination.registration_generation = session_row.created_at
      from public.push_tokens as destination
      join public.sessions as session_row
        on session_row.id = destination.registration_session_id
     where destination.installation_id = 'installation-mixed-version-current'
  ),
  'pre-RPC conflict update retained a stale generation or failed to re-enable'
);

-- The same old write after its session has disappeared must not fail the
-- request or create a deliverable token.  The compatibility trigger rewrites
-- it disabled so the already-validated CHECK remains safe during rollout.
set role service_role;
insert into public.push_tokens (
  user_id, installation_id, platform, token, enabled, updated_at, last_used_at
) values (
  '70000000-0000-4000-8000-000000000002',
  'installation-mixed-version-stale',
  'ios',
  repeat('O', 24),
  true,
  clock_timestamp(),
  clock_timestamp()
);
reset role;

select pg_temp.assert_true(
  (
    select not destination.enabled
      and destination.registration_session_id is null
      and destination.registration_session_token_hash is null
      and destination.registration_generation is null
      from public.push_tokens as destination
     where destination.installation_id = 'installation-mixed-version-stale'
  ),
  'stale pre-RPC direct upsert did not complete fail-closed'
);

-- Give the planner a production-shaped relation size.  With only the handful
-- of functional fixtures above, scanning the primary key in id order is
-- legitimately cheaper and would not demonstrate the selective hot-path
-- indexes used as this table grows.
insert into public.push_tokens (
  user_id, installation_id, platform, token, enabled
)
select '70000000-0000-4000-8000-000000000001'::uuid,
       'installation-plan-fixture-' || fixture_id::text,
       'ios',
       'plan-token-fixture-' || fixture_id::text,
       false
  from pg_catalog.generate_series(1, 2048) as fixture_id;

analyze public.push_tokens;

do $index_plan_gate$
declare
  installation_plan json;
  transfer_plan json;
begin
  set local enable_seqscan = off;
  execute $plan$
    explain (format json, costs off)
    select id
      from public.push_tokens
     where installation_id = 'installation-plan-probe'
     order by id
     for update
  $plan$ into installation_plan;
  if pg_catalog.strpos(
       installation_plan::text,
       'push_tokens_installation_id_idx'
     ) = 0 then
    raise exception 'Installation-only lock path did not use its dedicated index: %',
      installation_plan;
  end if;

  execute $plan$
    explain (format json, costs off)
    select id
      from public.push_tokens
     where installation_id = 'installation-plan-probe'
        or token = 'token-plan-probe'
     order by id
     for update
  $plan$ into transfer_plan;
  if pg_catalog.strpos(
       transfer_plan::text,
       'push_tokens_installation_id_idx'
     ) = 0
     or pg_catalog.strpos(transfer_plan::text, 'push_tokens_token_key') = 0 then
    raise exception 'Installation-or-token lock path did not use both lookup indexes: %',
      transfer_plan;
  end if;
end;
$index_plan_gate$;

delete from public.push_tokens
 where installation_id like 'installation-plan-fixture-%';

insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values (
  '71000000-0000-4000-8000-000000000001',
  '70000000-0000-4000-8000-000000000001',
  repeat('a', 64),
  'installation-native-fixture',
  clock_timestamp() - interval '2 minutes',
  clock_timestamp(),
  clock_timestamp() + interval '30 days'
);

select pg_temp.assert_true(
  (
    select result.applied and not result.stale and result.owner_id =
      '70000000-0000-4000-8000-000000000001'::uuid
    from public.mutate_push_registration_v1(
      '70000000-0000-4000-8000-000000000001',
      '71000000-0000-4000-8000-000000000001',
      repeat('a', 64),
      'installation-native-fixture',
      'ios',
      repeat('A', 24),
      true,
      clock_timestamp() + interval '30 days'
    ) as result
  ),
  'current A registration did not apply'
);

-- Rotate the one installation session to B exactly as login does.  Both a
-- delayed A register and delayed A unregister must now fail before changing B.
update public.sessions
   set user_id = '70000000-0000-4000-8000-000000000002',
       token_hash = repeat('b', 64),
       created_at = clock_timestamp(),
       last_activity = clock_timestamp(),
       expires_at = clock_timestamp() + interval '30 days',
       revoked_at = null
 where id = '71000000-0000-4000-8000-000000000001';

select pg_temp.assert_true(
  not exists (
    select 1
      from public.push_tokens
     where installation_id = 'installation-native-fixture'
       and user_id = '70000000-0000-4000-8000-000000000001'::uuid
       and enabled
  ),
  'expired A destination remained enabled after the installation session rotated to B'
);

select pg_temp.assert_true(
  (
    select not result.applied and result.stale
    from public.mutate_push_registration_v1(
      '70000000-0000-4000-8000-000000000001',
      '71000000-0000-4000-8000-000000000001',
      repeat('a', 64),
      'installation-native-fixture',
      'ios',
      repeat('A', 24),
      true,
      clock_timestamp() + interval '30 days'
    ) as result
  ),
  'delayed A registration was not rejected after B rotation'
);

select pg_temp.assert_true(
  (
    select result.applied and not result.stale
    from public.mutate_push_registration_v1(
      '70000000-0000-4000-8000-000000000002',
      '71000000-0000-4000-8000-000000000001',
      repeat('b', 64),
      'installation-native-fixture',
      'ios',
      repeat('B', 24),
      true,
      clock_timestamp() + interval '30 days'
    ) as result
  ),
  'current B registration did not apply'
);

select pg_temp.assert_true(
  (
    select not result.applied and result.stale
    from public.mutate_push_registration_v1(
      '70000000-0000-4000-8000-000000000001',
      '71000000-0000-4000-8000-000000000001',
      repeat('a', 64),
      'installation-native-fixture',
      '',
      '',
      false,
      clock_timestamp() + interval '30 days'
    ) as result
  ),
  'delayed A unregister was not rejected after B rotation'
);

select pg_temp.assert_true(
  (
    select count(*) = 1
      and bool_and(user_id = '70000000-0000-4000-8000-000000000002'::uuid)
      and bool_and(token = repeat('B', 24))
      and bool_and(enabled)
      and bool_and(registration_session_token_hash = repeat('b', 64))
    from public.push_tokens
    where installation_id = 'installation-native-fixture'
      and enabled
  ),
  'stale A completion changed B push ownership'
);

select pg_temp.assert_true(
  (
    select result.applied and not result.stale and not result.enabled
    from public.mutate_push_registration_v1(
      '70000000-0000-4000-8000-000000000002',
      '71000000-0000-4000-8000-000000000001',
      repeat('b', 64),
      'installation-native-fixture',
      '',
      '',
      false,
      clock_timestamp() + interval '30 days'
    ) as result
  ),
  'current B unregister did not apply'
);

select pg_temp.assert_true(
  not exists (
    select 1 from public.push_tokens
    where installation_id = 'installation-native-fixture' and enabled
  ),
  'unregister left an enabled destination'
);

-- A reinstall may rotate the opaque installation ID while APNs/FCM keeps the
-- same token.  The newer session generation must own that globally unique
-- destination regardless of arrival order.
insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values
  (
    '71000000-0000-4000-8000-000000000011',
    '70000000-0000-4000-8000-000000000001',
    repeat('c', 64),
    'installation-reinstall-old',
    clock_timestamp() - interval '5 minutes',
    clock_timestamp(),
    clock_timestamp() + interval '30 days'
  ),
  (
    '71000000-0000-4000-8000-000000000012',
    '70000000-0000-4000-8000-000000000002',
    repeat('d', 64),
    'installation-reinstall-new',
    clock_timestamp(),
    clock_timestamp(),
    clock_timestamp() + interval '30 days'
  );

select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000001',
  '71000000-0000-4000-8000-000000000011',
  repeat('c', 64),
  'installation-reinstall-old',
  'ios',
  repeat('R', 24),
  true,
  clock_timestamp() + interval '30 days'
);
select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000002',
  '71000000-0000-4000-8000-000000000012',
  repeat('d', 64),
  'installation-reinstall-new',
  'ios',
  repeat('R', 24),
  true,
  clock_timestamp() + interval '30 days'
);

select pg_temp.assert_true(
  (
    select count(*) = 1
      and bool_and(user_id = '70000000-0000-4000-8000-000000000002'::uuid)
      and bool_and(installation_id = 'installation-reinstall-new')
      and bool_and(enabled)
    from public.push_tokens
    where token = repeat('R', 24)
  ),
  'newer reinstalled session did not take the globally unique token'
);

select pg_temp.assert_true(
  (
    select not result.applied and result.stale
    from public.mutate_push_registration_v1(
      '70000000-0000-4000-8000-000000000001',
      '71000000-0000-4000-8000-000000000011',
      repeat('c', 64),
      'installation-reinstall-old',
      'ios',
      repeat('R', 24),
      true,
      clock_timestamp() + interval '30 days'
    ) as result
  ),
  'older reinstalled session reclaimed the newer token'
);

-- PostgreSQL timestamps are not unique. When two sessions have the exact same
-- created_at, the larger immutable session UUID deterministically wins so
-- arrival order cannot decide which installation owns the destination.
insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values
  (
    '71000000-0000-4000-8000-000000000013',
    '70000000-0000-4000-8000-000000000001',
    repeat('e', 64),
    'installation-equal-generation-old',
    '2026-10-24T06:30:00Z',
    clock_timestamp(),
    clock_timestamp() + interval '30 days'
  ),
  (
    '71000000-0000-4000-8000-000000000014',
    '70000000-0000-4000-8000-000000000002',
    repeat('f', 64),
    'installation-equal-generation-new',
    '2026-10-24T06:30:00Z',
    clock_timestamp(),
    clock_timestamp() + interval '30 days'
  );

select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000002',
  '71000000-0000-4000-8000-000000000014',
  repeat('f', 64),
  'installation-equal-generation-new',
  'ios',
  repeat('E', 24),
  true,
  clock_timestamp() + interval '30 days'
);

select pg_temp.assert_true(
  (
    select not result.applied and result.stale
    from public.mutate_push_registration_v1(
      '70000000-0000-4000-8000-000000000001',
      '71000000-0000-4000-8000-000000000013',
      repeat('e', 64),
      'installation-equal-generation-old',
      'ios',
      repeat('E', 24),
      true,
      clock_timestamp() + interval '30 days'
    ) as result
  ),
  'equal-time lower session UUID reclaimed the deterministic winner'
);

select pg_temp.assert_true(
  (
    select count(*) = 1
      and bool_and(user_id = '70000000-0000-4000-8000-000000000002'::uuid)
      and bool_and(registration_session_id = '71000000-0000-4000-8000-000000000014'::uuid)
    from public.push_tokens
    where token = repeat('E', 24)
  ),
  'equal-time session UUID tie-breaker did not preserve one deterministic owner'
);

-- Revoking a session disables exactly the destination generation established
-- by that session.  A fresh generation can subsequently register normally.
insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values (
  '71000000-0000-4000-8000-000000000021',
  '70000000-0000-4000-8000-000000000001',
  repeat('7', 64),
  'installation-revocation-fixture',
  clock_timestamp(),
  clock_timestamp(),
  clock_timestamp() + interval '30 days'
);

select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000001',
  '71000000-0000-4000-8000-000000000021',
  repeat('7', 64),
  'installation-revocation-fixture',
  'ios',
  repeat('Q', 24),
  true,
  clock_timestamp() + interval '30 days'
);

update public.sessions
   set revoked_at = clock_timestamp()
 where id = '71000000-0000-4000-8000-000000000021';

select pg_temp.assert_true(
  not exists (
    select 1
      from public.push_tokens
     where installation_id = 'installation-revocation-fixture'
       and registration_session_id = '71000000-0000-4000-8000-000000000021'::uuid
       and registration_session_token_hash = repeat('7', 64)
       and enabled
  ),
  'revoked session generation retained an enabled destination'
);

update public.sessions
   set token_hash = repeat('8', 64),
       created_at = clock_timestamp(),
       last_activity = clock_timestamp(),
       expires_at = clock_timestamp() + interval '30 days',
       revoked_at = null
 where id = '71000000-0000-4000-8000-000000000021';

select pg_temp.assert_true(
  (
    select result.applied and not result.stale and result.enabled
      from public.mutate_push_registration_v1(
        '70000000-0000-4000-8000-000000000001',
        '71000000-0000-4000-8000-000000000021',
        repeat('8', 64),
        'installation-revocation-fixture',
        'ios',
        repeat('Z', 24),
        true,
        clock_timestamp() + interval '30 days'
      ) as result
  ),
  'fresh session generation could not re-register after revocation'
);

update public.sessions
   set token_hash = repeat('0', 64)
 where id = '71000000-0000-4000-8000-000000000021';

select pg_temp.assert_true(
  not exists (
    select 1
      from public.push_tokens
     where installation_id = 'installation-revocation-fixture'
       and registration_session_token_hash = repeat('8', 64)
       and enabled
  ),
  'same-owner session token rotation retained the older push generation'
);

-- A logout/revoke request authenticated with generation A may complete after
-- the same sessions row has rotated to B.  The route's generation CAS must be
-- a no-op, preserving B's session and freshly registered destination.
insert into public.sessions (
  id, user_id, token_hash, device_id, created_at, last_activity, expires_at
) values (
  '71000000-0000-4000-8000-000000000031',
  '70000000-0000-4000-8000-000000000001',
  repeat('1', 64),
  'installation-delayed-logout',
  clock_timestamp() - interval '1 minute',
  clock_timestamp(),
  clock_timestamp() + interval '30 days'
);

select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000001',
  '71000000-0000-4000-8000-000000000031',
  repeat('1', 64),
  'installation-delayed-logout',
  'ios',
  repeat('X', 24),
  true,
  clock_timestamp() + interval '30 days'
);

update public.sessions
   set user_id = '70000000-0000-4000-8000-000000000002',
       token_hash = repeat('2', 64),
       created_at = clock_timestamp(),
       last_activity = clock_timestamp(),
       expires_at = clock_timestamp() + interval '30 days',
       revoked_at = null
 where id = '71000000-0000-4000-8000-000000000031';

select * from public.mutate_push_registration_v1(
  '70000000-0000-4000-8000-000000000002',
  '71000000-0000-4000-8000-000000000031',
  repeat('2', 64),
  'installation-delayed-logout',
  'ios',
  repeat('Y', 24),
  true,
  clock_timestamp() + interval '30 days'
);

update public.sessions
   set revoked_at = clock_timestamp()
 where id = '71000000-0000-4000-8000-000000000031'
   and user_id = '70000000-0000-4000-8000-000000000001'
   and token_hash = repeat('1', 64)
   and revoked_at is null;

select pg_temp.assert_true(
  (
    select session_row.user_id = '70000000-0000-4000-8000-000000000002'::uuid
      and session_row.token_hash = repeat('2', 64)
      and session_row.revoked_at is null
      from public.sessions as session_row
     where session_row.id = '71000000-0000-4000-8000-000000000031'::uuid
  ),
  'delayed A logout/revoke changed B session generation'
);

select pg_temp.assert_true(
  (
    select count(*) = 1
      and bool_and(user_id = '70000000-0000-4000-8000-000000000002'::uuid)
      and bool_and(token = repeat('Y', 24))
      and bool_and(enabled)
      from public.push_tokens
     where installation_id = 'installation-delayed-logout'
       and enabled
  ),
  'delayed A logout/revoke disabled B push generation'
);
