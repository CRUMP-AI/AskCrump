\set ON_ERROR_STOP on

create extension if not exists dblink;

insert into public.users(id) values
  ('00000000-0000-4000-8000-000000009201');

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256,
  authorization_expires_at, created_at, updated_at
) values (
  '00000000-0000-4000-8000-000000009211',
  '00000000-0000-4000-8000-000000009201',
  'google', 'mail', 'personal',
  '00000000-0000-4000-8000-000000009221', 1, 'active',
  repeat('a', 64), array['mail.send'], repeat('b', 64),
  repeat('c', 64), repeat('d', 64),
  '00000000-0000-4000-8000-000000009231', repeat('f', 64),
  '2026-12-01T00:00:00Z', '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z'
);

select public.connected_app_credential_create_v1(
  '00000000-0000-4000-8000-000000009201',
  '00000000-0000-4000-8000-000000009211', 'google', repeat('f', 64),
  '00000000-0000-4000-8000-000000009221', repeat('0', 64), 'personal',
  1, repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('d', 64),
  '2026-12-01T00:00:00Z', 1,
  '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z',
  repeat('1', 64), repeat('2', 64), 'credential-key',
  repeat('A', 16), repeat('B', 64), repeat('C', 16), repeat('D', 32),
  repeat('3', 64)
);

do $races$
declare
  connection_string text := pg_catalog.format(
    'host=127.0.0.1 port=%s dbname=%s user=postgres',
    pg_catalog.current_setting('port'),
    pg_catalog.current_database()
  );
  result jsonb;
begin
  perform public.dblink_connect('connected_store_race_a', connection_string);
  perform public.dblink_connect('connected_store_race_b', connection_string);

  -- Put wins the first payload race.  The blocked erase must observe that
  -- committed row, report record_existed=true, and leave only a tombstone.
  perform public.dblink_exec('connected_store_race_a', 'begin');
  perform public.dblink_exec('connected_store_race_a', 'set local role service_role');
  select response::jsonb into result
  from public.dblink(
    'connected_store_race_a',
    $sql$
      select public.connected_app_payload_put_v1(
        '00000000-0000-4000-8000-000000009301',
        '00000000-0000-4000-8000-000000009201',
        '00000000-0000-4000-8000-000000009211',
        '00000000-0000-4000-8000-000000009311',
        'google', 'mail.send', 'commitment-key', repeat('4', 64),
        '2026-11-07T20:00:00Z', '2026-11-07T21:00:00Z',
        repeat('5', 64), repeat('6', 64), 'payload-key',
        repeat('E', 16), repeat('F', 64), repeat('G', 16), repeat('H', 32),
        repeat('7', 64)
      )::text
    $sql$
  ) as remote_result(response text);
  if result->>'status' <> 'present' then
    raise exception 'payload put race setup failed';
  end if;

  perform public.dblink_exec('connected_store_race_b', 'begin');
  perform public.dblink_exec('connected_store_race_b', 'set local role service_role');
  if public.dblink_send_query(
    'connected_store_race_b',
    $sql$
      select public.connected_app_payload_delete_v1(
        '00000000-0000-4000-8000-000000009301', repeat('5', 64),
        '2026-11-07T20:01:00Z'
      )::text
    $sql$
  ) <> 1 then
    raise exception 'payload erase race did not start';
  end if;
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('connected_store_race_b') <> 1 then
    raise exception 'payload erase did not serialize behind put';
  end if;
  perform public.dblink_exec('connected_store_race_a', 'commit');
  select response::jsonb into result
  from public.dblink_get_result('connected_store_race_b') as remote_result(response text);
  perform response
  from public.dblink_get_result('connected_store_race_b') as remote_result(response text);
  perform public.dblink_exec('connected_store_race_b', 'commit');
  if result <> '{"status":"erased","record_existed":true}'::jsonb then
    raise exception 'payload put-winner result drifted: %', result;
  end if;

  -- Erase wins the reverse order.  A delayed put can never resurrect it.
  perform public.dblink_exec('connected_store_race_a', 'begin');
  perform public.dblink_exec('connected_store_race_a', 'set local role service_role');
  select response::jsonb into result
  from public.dblink(
    'connected_store_race_a',
    $sql$
      select public.connected_app_payload_delete_v1(
        '00000000-0000-4000-8000-000000009302', repeat('8', 64),
        '2026-11-07T20:01:00Z'
      )::text
    $sql$
  ) as remote_result(response text);
  if result <> '{"status":"erased","record_existed":false}'::jsonb then
    raise exception 'payload erase-winner setup drifted: %', result;
  end if;

  perform public.dblink_exec('connected_store_race_b', 'begin');
  perform public.dblink_exec('connected_store_race_b', 'set local role service_role');
  if public.dblink_send_query(
    'connected_store_race_b',
    $sql$
      select public.connected_app_payload_put_v1(
        '00000000-0000-4000-8000-000000009302',
        '00000000-0000-4000-8000-000000009201',
        '00000000-0000-4000-8000-000000009211',
        '00000000-0000-4000-8000-000000009312',
        'google', 'mail.send', 'commitment-key', repeat('9', 64),
        '2026-11-07T20:00:00Z', '2026-11-07T21:00:00Z',
        repeat('8', 64), repeat('a', 64), 'payload-key',
        repeat('I', 16), repeat('J', 64), repeat('K', 16), repeat('L', 32),
        repeat('b', 64)
      )::text
    $sql$
  ) <> 1 then
    raise exception 'payload put race did not start';
  end if;
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('connected_store_race_b') <> 1 then
    raise exception 'payload put did not serialize behind erase';
  end if;
  perform public.dblink_exec('connected_store_race_a', 'commit');
  select response::jsonb into result
  from public.dblink_get_result('connected_store_race_b') as remote_result(response text);
  perform response
  from public.dblink_get_result('connected_store_race_b') as remote_result(response text);
  perform public.dblink_exec('connected_store_race_b', 'commit');
  if result->>'status' <> 'erased' or result->>'record' is not null then
    raise exception 'delayed payload put resurrected erased record: %', result;
  end if;

  -- Exactly one refresh lease wins while the first transaction is open.
  perform public.dblink_exec('connected_store_race_a', 'begin');
  perform public.dblink_exec('connected_store_race_a', 'set local role service_role');
  select response::jsonb into result
  from public.dblink(
    'connected_store_race_a',
    $sql$
      select public.connected_app_credential_claim_refresh_v1(
        repeat('f', 64), repeat('3', 64),
        '00000000-0000-4000-8000-000000009321', 30
      )::text
    $sql$
  ) as remote_result(response text);
  if result->>'status' <> 'claimed' then
    raise exception 'first refresh lease was not claimed';
  end if;

  perform public.dblink_exec('connected_store_race_b', 'begin');
  perform public.dblink_exec('connected_store_race_b', 'set local role service_role');
  if public.dblink_send_query(
    'connected_store_race_b',
    $sql$
      select public.connected_app_credential_claim_refresh_v1(
        repeat('f', 64), repeat('3', 64),
        '00000000-0000-4000-8000-000000009322', 30
      )::text
    $sql$
  ) <> 1 then
    raise exception 'second refresh lease race did not start';
  end if;
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('connected_store_race_b') <> 1 then
    raise exception 'second refresh claim did not serialize';
  end if;
  perform public.dblink_exec('connected_store_race_a', 'commit');
  select response::jsonb into result
  from public.dblink_get_result('connected_store_race_b') as remote_result(response text);
  perform response
  from public.dblink_get_result('connected_store_race_b') as remote_result(response text);
  perform public.dblink_exec('connected_store_race_b', 'commit');
  if result->>'status' <> 'busy' then
    raise exception 'refresh lease race had two winners: %', result;
  end if;

  perform public.dblink_disconnect('connected_store_race_a');
  perform public.dblink_disconnect('connected_store_race_b');
exception when others then
  begin perform public.dblink_disconnect('connected_store_race_a'); exception when others then null; end;
  begin perform public.dblink_disconnect('connected_store_race_b'); exception when others then null; end;
  raise;
end;
$races$;

select 'CONNECTED_APP_DURABLE_STORE_RACES_OK' as result;
