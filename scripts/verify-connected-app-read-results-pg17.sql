\set ON_ERROR_STOP on

insert into public.users(id) values
  ('00000000-0000-4000-8000-00000000b001');

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256,
  authorization_expires_at, created_at, updated_at
) values (
  '00000000-0000-4000-8000-00000000b002',
  '00000000-0000-4000-8000-00000000b001',
  'google', 'mail', 'personal',
  '00000000-0000-4000-8000-00000000b003', 1, 'active',
  repeat('a', 64), array['mail.get'], repeat('b', 64),
  repeat('c', 64), repeat('d', 64),
  '00000000-0000-4000-8000-00000000b004', repeat('e', 64),
  pg_catalog.clock_timestamp() + interval '1 day',
  pg_catalog.clock_timestamp() - interval '1 minute',
  pg_catalog.clock_timestamp() - interval '1 minute'
);

insert into connected_app_private.task_grants (
  grant_id, owner_id, task_id, turn_id, connection_id, provider, resource,
  authorization_revision, authorization_snapshot_sha256, actions,
  actions_sha256, task_state_revision, expires_at
) values (
  '00000000-0000-4000-8000-00000000b005',
  '00000000-0000-4000-8000-00000000b001',
  '00000000-0000-4000-8000-00000000b006',
  '00000000-0000-4000-8000-00000000b007',
  '00000000-0000-4000-8000-00000000b002',
  'google', 'mail', 1, repeat('a', 64), array['mail.get'], repeat('b', 64),
  1, pg_catalog.clock_timestamp() + interval '1 day'
);

insert into connected_app_private.action_ledger (
  operation_id, action_id, owner_id, task_id, turn_id, connection_id,
  grant_id, provider, resource, action, authorization_revision,
  authorization_snapshot_sha256, granted_actions_sha256,
  granted_scopes_sha256, parameters_sha256, resource_version_sha256,
  authority_sha256, idempotency_key_sha256, task_state_revision,
  status, mutates_external_state, approval_class, claim_request_id,
  claim_id, fencing_token, lease_expires_at, execution_deadline,
  access_phase, read_use_nonce, read_credential_expires_at,
  read_consumed_at, access_started_at, created_at, updated_at
) values (
  '00000000-0000-4000-8000-00000000b008',
  '00000000-0000-4000-8000-00000000b008',
  '00000000-0000-4000-8000-00000000b001',
  '00000000-0000-4000-8000-00000000b006',
  '00000000-0000-4000-8000-00000000b007',
  '00000000-0000-4000-8000-00000000b002',
  '00000000-0000-4000-8000-00000000b005',
  'google', 'mail', 'mail.get', 1, repeat('a', 64), repeat('b', 64),
  repeat('c', 64), repeat('1', 64), null, repeat('2', 64), repeat('3', 64),
  1, 'access_granted', false, 'none',
  '00000000-0000-4000-8000-00000000b009',
  '00000000-0000-4000-8000-00000000b00a', 7,
  pg_catalog.clock_timestamp() + interval '1 minute',
  pg_catalog.clock_timestamp() + interval '5 minutes',
  'read', '00000000-0000-4000-8000-00000000b00b',
  pg_catalog.clock_timestamp() + interval '1 minute',
  pg_catalog.clock_timestamp() - interval '2 seconds',
  pg_catalog.clock_timestamp() - interval '4 seconds',
  pg_catalog.clock_timestamp() - interval '10 seconds',
  pg_catalog.clock_timestamp() - interval '2 seconds'
);

select public.connected_app_payload_put_v1(
  '00000000-0000-5000-8000-00000000b00c',
  '00000000-0000-4000-8000-00000000b001',
  '00000000-0000-4000-8000-00000000b002',
  '00000000-0000-4000-8000-00000000b008',
  'google', 'mail.get', 'commit-v1', repeat('4', 64),
  pg_catalog.clock_timestamp() - interval '1 second',
  pg_catalog.clock_timestamp() + interval '1 hour',
  repeat('5', 64), repeat('6', 64), 'wrap-v1',
  repeat('A', 16), repeat('B', 64), repeat('C', 16), repeat('D', 32),
  repeat('7', 64)
);

set role service_role;

do $behavior$
declare
  result jsonb;
  observed_at timestamptz := pg_catalog.clock_timestamp();
begin
  result := public.connected_app_read_read_result_v1(
    '00000000-0000-4000-8000-00000000b001',
    '00000000-0000-4000-8000-00000000b008',
    '00000000-0000-5000-8000-00000000b00d', repeat('3', 64)
  );
  if result <> '{"status":"consumed_unknown","record":null}'::jsonb then
    raise exception 'consumed-unknown readback contract failed: %', result;
  end if;

  result := public.connected_app_settle_read_result_v1(
    '00000000-0000-5000-8000-00000000b00d',
    '00000000-0000-4000-8000-00000000b008',
    '00000000-0000-4000-8000-00000000b008',
    '00000000-0000-4000-8000-00000000b001',
    '00000000-0000-4000-8000-00000000b002',
    'google', 'mail', 'mail.get',
    '00000000-0000-5000-8000-00000000b00c',
    'commit-v1', repeat('4', 64), repeat('6', 64), repeat('8', 64),
    repeat('2', 64), repeat('3', 64),
    '00000000-0000-4000-8000-00000000b00a', 7,
    '00000000-0000-4000-8000-00000000b00b', observed_at, repeat('9', 64)
  );
  if result->>'status' <> 'terminal'
     or result->'record'->>'result_payload_id' <>
       '00000000-0000-5000-8000-00000000b00c'
     or result->'record' ? 'payload_ciphertext'
     or result::text like '%private body%' then
    raise exception 'atomic read-result settlement contract failed';
  end if;

  -- Exact replay returns the same opaque reference and never mutates the row.
  if public.connected_app_settle_read_result_v1(
    '00000000-0000-5000-8000-00000000b00d',
    '00000000-0000-4000-8000-00000000b008',
    '00000000-0000-4000-8000-00000000b008',
    '00000000-0000-4000-8000-00000000b001',
    '00000000-0000-4000-8000-00000000b002',
    'google', 'mail', 'mail.get',
    '00000000-0000-5000-8000-00000000b00c',
    'commit-v1', repeat('4', 64), repeat('6', 64), repeat('8', 64),
    repeat('2', 64), repeat('3', 64),
    '00000000-0000-4000-8000-00000000b00a', 7,
    '00000000-0000-4000-8000-00000000b00b', observed_at, repeat('9', 64)
  )->'record' is distinct from result->'record' then
    raise exception 'exact read-result settlement replay drifted';
  end if;

  result := public.connected_app_read_read_result_v1(
    '00000000-0000-4000-8000-00000000b001',
    '00000000-0000-4000-8000-00000000b008',
    '00000000-0000-5000-8000-00000000b00d', repeat('3', 64)
  );
  if result->>'status' <> 'terminal'
     or result->'record'->>'completion_id' <>
       '00000000-0000-5000-8000-00000000b00d' then
    raise exception 'terminal read-result readback failed';
  end if;

  begin
    perform public.connected_app_settle_read_result_v1(
      '00000000-0000-5000-8000-00000000b00d',
      '00000000-0000-4000-8000-00000000b008',
      '00000000-0000-4000-8000-00000000b008',
      '00000000-0000-4000-8000-00000000b001',
      '00000000-0000-4000-8000-00000000b002',
      'microsoft', 'mail', 'mail.get',
      '00000000-0000-5000-8000-00000000b00c',
      'commit-v1', repeat('4', 64), repeat('6', 64), repeat('8', 64),
      repeat('2', 64), repeat('3', 64),
      '00000000-0000-4000-8000-00000000b00a', 7,
      '00000000-0000-4000-8000-00000000b00b', observed_at, repeat('9', 64)
    );
    raise exception 'provider-drifted read-result replay was accepted';
  exception when sqlstate '55000' then
    null;
  end;
end;
$behavior$;

reset role;

-- Re-create the exact fresh settlement state and prove two service workers
-- cannot create two completions or overwrite the opaque result binding.
create extension if not exists dblink;
delete from connected_app_private.read_results
where operation_id = '00000000-0000-4000-8000-00000000b008';
update connected_app_private.action_ledger
set status = 'access_granted', terminal_outcome = null,
    terminal_binding_sha256 = null, provider_request_id_sha256 = null,
    provider_resource_id_sha256 = null, observed_at = null,
    terminal_at = null, updated_at = pg_catalog.clock_timestamp()
where operation_id = '00000000-0000-4000-8000-00000000b008';

do $race$
declare
  connection_string text := pg_catalog.format(
    'host=127.0.0.1 port=%s dbname=%s user=postgres',
    pg_catalog.current_setting('port'), pg_catalog.current_database()
  );
  observed_at timestamptz := pg_catalog.clock_timestamp();
  settle_sql text;
  result_a jsonb;
  result_b jsonb;
begin
  settle_sql := pg_catalog.format($sql$
    select public.connected_app_settle_read_result_v1(
      '00000000-0000-5000-8000-00000000b00d',
      '00000000-0000-4000-8000-00000000b008',
      '00000000-0000-4000-8000-00000000b008',
      '00000000-0000-4000-8000-00000000b001',
      '00000000-0000-4000-8000-00000000b002',
      'google', 'mail', 'mail.get',
      '00000000-0000-5000-8000-00000000b00c',
      'commit-v1', repeat('4', 64), repeat('6', 64), repeat('8', 64),
      repeat('2', 64), repeat('3', 64),
      '00000000-0000-4000-8000-00000000b00a', 7,
      '00000000-0000-4000-8000-00000000b00b', %L::timestamptz,
      repeat('9', 64)
    )::text
  $sql$, observed_at);

  perform public.dblink_connect('read_result_race_a', connection_string);
  perform public.dblink_connect('read_result_race_b', connection_string);
  perform public.dblink_exec('read_result_race_a', 'begin');
  perform public.dblink_exec('read_result_race_a', 'set local role service_role');
  select response::jsonb into result_a
  from public.dblink('read_result_race_a', settle_sql)
    as remote_result(response text);

  perform public.dblink_exec('read_result_race_b', 'begin');
  perform public.dblink_exec('read_result_race_b', 'set local role service_role');
  if public.dblink_send_query('read_result_race_b', settle_sql) <> 1 then
    raise exception 'second read-result settlement was not dispatched';
  end if;
  perform public.dblink_exec('read_result_race_a', 'commit');
  select response::jsonb into result_b
  from public.dblink_get_result('read_result_race_b')
    as remote_result(response text);
  perform response
  from public.dblink_get_result('read_result_race_b')
    as remote_result(response text);
  perform public.dblink_exec('read_result_race_b', 'commit');
  perform public.dblink_disconnect('read_result_race_a');
  perform public.dblink_disconnect('read_result_race_b');

  if result_a->>'status' <> 'terminal'
     or result_b->>'status' <> 'terminal'
     or result_a->'record' is distinct from result_b->'record' then
    raise exception 'concurrent exact read-result settlement did not converge';
  end if;
end;
$race$;

do $race_result$
begin
  if (select pg_catalog.count(*) from connected_app_private.read_results
      where operation_id = '00000000-0000-4000-8000-00000000b008') <> 1 then
    raise exception 'concurrent read-result settlement duplicated completion';
  end if;
end;
$race_result$;

delete from public.users
where id = '00000000-0000-4000-8000-00000000b001';

do $deletion$
begin
  if exists (
    select 1 from connected_app_private.read_results
    where owner_id = '00000000-0000-4000-8000-00000000b001'
  ) or exists (
    select 1 from connected_app_private.payload_envelopes
    where payload_id = '00000000-0000-5000-8000-00000000b00c'
  ) or not exists (
    select 1 from connected_app_private.payload_tombstones
    where payload_id = '00000000-0000-5000-8000-00000000b00c'
      and identity_sha256 = repeat('5', 64)
  ) then
    raise exception 'account-deletion read-result cascade/tombstone failed';
  end if;
end;
$deletion$;

select 'CONNECTED_APP_ENCRYPTED_READ_RESULTS_BEHAVIOR_OK' as result;
