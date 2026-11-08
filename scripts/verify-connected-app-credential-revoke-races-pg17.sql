\set ON_ERROR_STOP on

create extension if not exists dblink;

insert into public.users(id) values
  ('00000000-0000-4000-8000-000000009301'),
  ('00000000-0000-4000-8000-000000009302'),
  ('00000000-0000-4000-8000-000000009303');

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256,
  authorization_expires_at, created_at, updated_at
) values
  (
    '00000000-0000-4000-8000-000000009311',
    '00000000-0000-4000-8000-000000009301',
    'google', 'mail', 'personal',
    '00000000-0000-4000-8000-000000009321', 1, 'active',
    repeat('1', 64), array['mail.send'], repeat('2', 64),
    repeat('3', 64), repeat('4', 64),
    '00000000-0000-4000-8000-000000009331', repeat('a', 64),
    '2026-12-01T00:00:00Z', '2026-11-07T20:00:00Z',
    '2026-11-07T20:00:00Z'
  ),
  (
    '00000000-0000-4000-8000-000000009312',
    '00000000-0000-4000-8000-000000009302',
    'google', 'mail', 'personal',
    '00000000-0000-4000-8000-000000009322', 1, 'active',
    repeat('1', 64), array['mail.send'], repeat('2', 64),
    repeat('3', 64), repeat('5', 64),
    '00000000-0000-4000-8000-000000009332', repeat('b', 64),
    '2026-12-01T00:00:00Z', '2026-11-07T20:00:00Z',
    '2026-11-07T20:00:00Z'
  ),
  (
    '00000000-0000-4000-8000-000000009313',
    '00000000-0000-4000-8000-000000009303',
    'google', 'mail', 'personal',
    '00000000-0000-4000-8000-000000009323', 1, 'active',
    repeat('1', 64), array['mail.send'], repeat('2', 64),
    repeat('3', 64), repeat('6', 64),
    '00000000-0000-4000-8000-000000009333', repeat('c', 64),
    '2026-12-01T00:00:00Z', '2026-11-07T20:00:00Z',
    '2026-11-07T20:00:00Z'
  );

select public.connected_app_credential_create_v1(
  '00000000-0000-4000-8000-000000009301',
  '00000000-0000-4000-8000-000000009311', 'google', repeat('a', 64),
  '00000000-0000-4000-8000-000000009321', repeat('0', 64), 'personal',
  1, repeat('1', 64), repeat('2', 64), repeat('3', 64), repeat('4', 64),
  '2026-12-01T00:00:00Z', 1,
  '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z',
  repeat('7', 64), repeat('8', 64), 'credential-key',
  repeat('A', 16), repeat('B', 64), repeat('C', 16), repeat('D', 32),
  repeat('9', 64)
);
select public.connected_app_credential_create_v1(
  '00000000-0000-4000-8000-000000009302',
  '00000000-0000-4000-8000-000000009312', 'google', repeat('b', 64),
  '00000000-0000-4000-8000-000000009322', repeat('0', 64), 'personal',
  1, repeat('1', 64), repeat('2', 64), repeat('3', 64), repeat('5', 64),
  '2026-12-01T00:00:00Z', 1,
  '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z',
  repeat('7', 64), repeat('8', 64), 'credential-key',
  repeat('A', 16), repeat('B', 64), repeat('C', 16), repeat('D', 32),
  repeat('9', 64)
);
select public.connected_app_credential_create_v1(
  '00000000-0000-4000-8000-000000009303',
  '00000000-0000-4000-8000-000000009313', 'google', repeat('c', 64),
  '00000000-0000-4000-8000-000000009323', repeat('0', 64), 'personal',
  1, repeat('1', 64), repeat('2', 64), repeat('3', 64), repeat('6', 64),
  '2026-12-01T00:00:00Z', 1,
  '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z',
  repeat('7', 64), repeat('8', 64), 'credential-key',
  repeat('A', 16), repeat('B', 64), repeat('C', 16), repeat('D', 32),
  repeat('9', 64)
);

do $races$
declare
  connection_string text := pg_catalog.format(
    'host=127.0.0.1 port=%s dbname=%s user=postgres',
    pg_catalog.current_setting('port'), pg_catalog.current_database()
  );
  result jsonb;
  response_text text;
  remote_error text;
begin
  perform public.dblink_connect('credential_revoke_a', connection_string);
  perform public.dblink_connect('credential_revoke_b', connection_string);

  -- READ wins: revoke must wait behind owner -> connection -> credential.
  perform public.dblink_exec('credential_revoke_a', 'begin');
  perform public.dblink_exec('credential_revoke_a', 'set local role service_role');
  select response::jsonb into result
  from public.dblink(
    'credential_revoke_a',
    $sql$select public.connected_app_credential_read_v1(repeat('a',64))::text$sql$
  ) as remote_result(response text);
  if result->>'status' <> 'present' then
    raise exception 'read-winner setup failed: %', result;
  end if;
  perform public.dblink_exec('credential_revoke_b', 'begin');
  perform public.dblink_exec('credential_revoke_b', 'set local role service_role');
  if public.dblink_send_query(
    'credential_revoke_b',
    $sql$select public.connected_app_revoke_connection_v1(
      '00000000-0000-4000-8000-000000009301',
      '00000000-0000-4000-8000-000000009311',
      '00000000-0000-4000-8000-000000009391', repeat('a',64), repeat('f',64)
    )::text$sql$
  ) <> 1 then
    raise exception 'read-winner revoke did not start';
  end if;
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('credential_revoke_b') <> 1 then
    raise exception 'revoke did not serialize behind read';
  end if;
  perform public.dblink_exec('credential_revoke_a', 'commit');
  select response::jsonb into result
  from public.dblink_get_result('credential_revoke_b') as remote_result(response text);
  perform response
  from public.dblink_get_result('credential_revoke_b') as remote_result(response text);
  if result->>'authorization_state' <> 'revoked' then
    raise exception 'read-winner revoke result drifted: %', result;
  end if;
  perform public.dblink_exec('credential_revoke_b', 'rollback');

  -- REVOKE wins: a blocked read may only observe the permanent tombstone.
  perform public.dblink_exec('credential_revoke_a', 'begin');
  perform public.dblink_exec('credential_revoke_a', 'set local role service_role');
  perform response
  from public.dblink(
    'credential_revoke_a',
    $sql$select public.connected_app_revoke_connection_v1(
      '00000000-0000-4000-8000-000000009301',
      '00000000-0000-4000-8000-000000009311',
      '00000000-0000-4000-8000-000000009391', repeat('a',64), repeat('f',64)
    )::text$sql$
  ) as remote_result(response text);
  perform public.dblink_exec('credential_revoke_b', 'begin');
  perform public.dblink_exec('credential_revoke_b', 'set local role service_role');
  if public.dblink_send_query(
    'credential_revoke_b',
    $sql$select public.connected_app_credential_read_v1(repeat('a',64))::text$sql$
  ) <> 1 then
    raise exception 'revoke-winner read did not start';
  end if;
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('credential_revoke_b') <> 1 then
    raise exception 'read did not serialize behind revoke';
  end if;
  perform public.dblink_exec('credential_revoke_a', 'commit');
  select response::jsonb into result
  from public.dblink_get_result('credential_revoke_b') as remote_result(response text);
  perform response
  from public.dblink_get_result('credential_revoke_b') as remote_result(response text);
  perform public.dblink_exec('credential_revoke_b', 'commit');
  if result <> '{"status":"erased","record":null}'::jsonb then
    raise exception 'revoke-winner read exposed custody: %', result;
  end if;

  -- CLAIM wins, then the competing revoke is rolled back for the reverse race.
  perform public.dblink_exec('credential_revoke_a', 'begin');
  perform public.dblink_exec('credential_revoke_a', 'set local role service_role');
  select response::jsonb into result
  from public.dblink(
    'credential_revoke_a',
    $sql$select public.connected_app_credential_claim_refresh_v1(
      repeat('b',64), repeat('9',64),
      '00000000-0000-4000-8000-000000009381', 30
    )::text$sql$
  ) as remote_result(response text);
  if result->>'status' <> 'claimed' then
    raise exception 'claim-winner setup failed: %', result;
  end if;
  perform public.dblink_exec('credential_revoke_b', 'begin');
  perform public.dblink_exec('credential_revoke_b', 'set local role service_role');
  perform public.dblink_send_query(
    'credential_revoke_b',
    $sql$select public.connected_app_revoke_connection_v1(
      '00000000-0000-4000-8000-000000009302',
      '00000000-0000-4000-8000-000000009312',
      '00000000-0000-4000-8000-000000009392', repeat('b',64), repeat('e',64)
    )::text$sql$
  );
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('credential_revoke_b') <> 1 then
    raise exception 'revoke did not serialize behind refresh claim';
  end if;
  perform public.dblink_exec('credential_revoke_a', 'commit');
  perform response
  from public.dblink_get_result('credential_revoke_b') as remote_result(response text);
  perform response
  from public.dblink_get_result('credential_revoke_b') as remote_result(response text);
  perform public.dblink_exec('credential_revoke_b', 'rollback');

  -- REVOKE wins: delayed refresh claim must fail current authority.
  perform public.dblink_exec('credential_revoke_a', 'begin');
  perform public.dblink_exec('credential_revoke_a', 'set local role service_role');
  perform response
  from public.dblink(
    'credential_revoke_a',
    $sql$select public.connected_app_revoke_connection_v1(
      '00000000-0000-4000-8000-000000009302',
      '00000000-0000-4000-8000-000000009312',
      '00000000-0000-4000-8000-000000009392', repeat('b',64), repeat('e',64)
    )::text$sql$
  ) as remote_result(response text);
  perform public.dblink_exec('credential_revoke_b', 'begin');
  perform public.dblink_exec('credential_revoke_b', 'set local role service_role');
  perform public.dblink_send_query(
    'credential_revoke_b',
    $sql$select public.connected_app_credential_claim_refresh_v1(
      repeat('b',64), repeat('9',64),
      '00000000-0000-4000-8000-000000009382', 30
    )::text$sql$
  );
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('credential_revoke_b') <> 1 then
    raise exception 'claim did not serialize behind revoke';
  end if;
  perform public.dblink_exec('credential_revoke_a', 'commit');
  response_text := null;
  select response into response_text
  from public.dblink_get_result('credential_revoke_b', false)
    as remote_result(response text);
  remote_error := public.dblink_error_message('credential_revoke_b');
  perform public.dblink_get_result('credential_revoke_b', false);
  perform public.dblink_exec('credential_revoke_b', 'rollback');
  if response_text is not null
     or remote_error not like '%credential refresh authority mismatch%' then
    raise exception 'revoke-winner claim was not fenced: %, %',
      response_text, remote_error;
  end if;

  -- REPLACE wins, then rollback the blocked revoke for the reverse order.
  perform public.dblink_exec('credential_revoke_a', 'begin');
  perform public.dblink_exec('credential_revoke_a', 'set local role service_role');
  select response::jsonb into result
  from public.dblink(
    'credential_revoke_a',
    $sql$select public.connected_app_credential_replace_v1(
      '00000000-0000-4000-8000-000000009303',
      '00000000-0000-4000-8000-000000009313', 'google', repeat('c',64),
      '00000000-0000-4000-8000-000000009323', repeat('0',64), 'personal',
      1, repeat('1',64), repeat('2',64), repeat('3',64), repeat('6',64),
      '2026-12-01T00:00:00Z', 2,
      '2026-11-07T20:00:00Z', '2026-11-07T20:01:00Z',
      repeat('7',64), repeat('8',64), 'credential-key',
      repeat('E',16), repeat('F',64), repeat('G',16), repeat('H',32),
      repeat('8',64), repeat('9',64)
    )::text$sql$
  ) as remote_result(response text);
  if result->'record'->>'secret_revision' <> '2' then
    raise exception 'replace-winner setup failed: %', result;
  end if;
  perform public.dblink_exec('credential_revoke_b', 'begin');
  perform public.dblink_exec('credential_revoke_b', 'set local role service_role');
  perform public.dblink_send_query(
    'credential_revoke_b',
    $sql$select public.connected_app_revoke_connection_v1(
      '00000000-0000-4000-8000-000000009303',
      '00000000-0000-4000-8000-000000009313',
      '00000000-0000-4000-8000-000000009393', repeat('c',64), repeat('d',64)
    )::text$sql$
  );
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('credential_revoke_b') <> 1 then
    raise exception 'revoke did not serialize behind credential replace';
  end if;
  perform public.dblink_exec('credential_revoke_a', 'commit');
  perform response
  from public.dblink_get_result('credential_revoke_b') as remote_result(response text);
  perform response
  from public.dblink_get_result('credential_revoke_b') as remote_result(response text);
  perform public.dblink_exec('credential_revoke_b', 'rollback');

  -- REVOKE wins: delayed replace must fail before touching ciphertext.
  perform public.dblink_exec('credential_revoke_a', 'begin');
  perform public.dblink_exec('credential_revoke_a', 'set local role service_role');
  perform response
  from public.dblink(
    'credential_revoke_a',
    $sql$select public.connected_app_revoke_connection_v1(
      '00000000-0000-4000-8000-000000009303',
      '00000000-0000-4000-8000-000000009313',
      '00000000-0000-4000-8000-000000009393', repeat('c',64), repeat('d',64)
    )::text$sql$
  ) as remote_result(response text);
  perform public.dblink_exec('credential_revoke_b', 'begin');
  perform public.dblink_exec('credential_revoke_b', 'set local role service_role');
  perform public.dblink_send_query(
    'credential_revoke_b',
    $sql$select public.connected_app_credential_replace_v1(
      '00000000-0000-4000-8000-000000009303',
      '00000000-0000-4000-8000-000000009313', 'google', repeat('c',64),
      '00000000-0000-4000-8000-000000009323', repeat('0',64), 'personal',
      1, repeat('1',64), repeat('2',64), repeat('3',64), repeat('6',64),
      '2026-12-01T00:00:00Z', 3,
      '2026-11-07T20:00:00Z', '2026-11-07T20:02:00Z',
      repeat('7',64), repeat('8',64), 'credential-key',
      repeat('I',16), repeat('J',64), repeat('K',16), repeat('L',32),
      repeat('7',64), repeat('8',64)
    )::text$sql$
  );
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('credential_revoke_b') <> 1 then
    raise exception 'replace did not serialize behind revoke';
  end if;
  perform public.dblink_exec('credential_revoke_a', 'commit');
  response_text := null;
  select response into response_text
  from public.dblink_get_result('credential_revoke_b', false)
    as remote_result(response text);
  remote_error := public.dblink_error_message('credential_revoke_b');
  perform public.dblink_get_result('credential_revoke_b', false);
  perform public.dblink_exec('credential_revoke_b', 'rollback');
  if response_text is not null
     or remote_error not like '%credential authority mismatch%' then
    raise exception 'revoke-winner replace was not fenced: %, %',
      response_text, remote_error;
  end if;

  if exists (
    select 1 from connected_app_private.credential_envelopes
    where credential_handle_sha256 in (repeat('a',64), repeat('b',64), repeat('c',64))
  ) or (
    select pg_catalog.count(*)
    from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 in (repeat('a',64), repeat('b',64), repeat('c',64))
  ) <> 3 then
    raise exception 'committed revoke did not permanently retire local custody';
  end if;

  perform public.dblink_disconnect('credential_revoke_a');
  perform public.dblink_disconnect('credential_revoke_b');
exception when others then
  begin perform public.dblink_disconnect('credential_revoke_a'); exception when others then null; end;
  begin perform public.dblink_disconnect('credential_revoke_b'); exception when others then null; end;
  raise;
end;
$races$;

select 'CONNECTED_APP_CREDENTIAL_REVOKE_RACES_OK' as result;
