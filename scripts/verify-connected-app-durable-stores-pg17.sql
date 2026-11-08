\set ON_ERROR_STOP on

insert into public.users(id) values
  ('00000000-0000-4000-8000-000000009001'),
  ('00000000-0000-4000-8000-000000009002');

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256,
  authorization_expires_at, created_at, updated_at
) values
  (
    '00000000-0000-4000-8000-000000009011',
    '00000000-0000-4000-8000-000000009001',
    'google', 'mail', 'personal',
    '00000000-0000-4000-8000-000000009021', 1, 'active',
    repeat('a', 64), array['mail.send'], repeat('b', 64),
    repeat('c', 64), repeat('d', 64),
    '00000000-0000-4000-8000-000000009031', repeat('e', 64),
    '2026-12-01T00:00:00Z', '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z'
  ),
  (
    '00000000-0000-4000-8000-000000009012',
    '00000000-0000-4000-8000-000000009002',
    'microsoft', 'calendar', 'work_school',
    '00000000-0000-4000-8000-000000009022', 1, 'active',
    repeat('1', 64), array['calendar.create'], repeat('2', 64),
    repeat('3', 64), repeat('4', 64),
    '00000000-0000-4000-8000-000000009032', repeat('5', 64),
    '2026-12-01T00:00:00Z', '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z'
  );

set role service_role;

do $behavior$
declare
  result jsonb;
begin
  result := public.connected_app_payload_put_v1(
    '00000000-0000-4000-8000-000000009101',
    '00000000-0000-4000-8000-000000009001',
    '00000000-0000-4000-8000-000000009011',
    '00000000-0000-4000-8000-000000009111',
    'google', 'mail.send', 'commitment-key', repeat('6', 64),
    '2026-11-07T20:00:00Z', '2026-11-07T21:00:00Z',
    repeat('7', 64), repeat('8', 64), 'payload-key',
    repeat('A', 16), repeat('B', 64), repeat('C', 16), repeat('D', 32),
    repeat('9', 64)
  );
  if result->>'status' <> 'present'
     or result->'record'->>'owner_id' <>
       '00000000-0000-4000-8000-000000009001' then
    raise exception 'payload put contract failed';
  end if;

  result := public.connected_app_payload_reference_get_v1(
    '00000000-0000-4000-8000-000000009001',
    '00000000-0000-4000-8000-000000009101',
    '00000000-0000-4000-8000-000000009011',
    '00000000-0000-4000-8000-000000009111',
    'google', 'mail.send'
  );
  if result->>'status' <> 'present'
     or result->'reference'->>'identity_sha256' <> repeat('7', 64)
     or result->'reference' ? 'payload_ciphertext' then
    raise exception 'payload reference recovery contract failed: %', result;
  end if;
  begin
    perform public.connected_app_payload_reference_get_v1(
      '00000000-0000-4000-8000-000000009999',
      '00000000-0000-4000-8000-000000009101',
      '00000000-0000-4000-8000-000000009011',
      '00000000-0000-4000-8000-000000009111',
      'google', 'mail.send'
    );
    raise exception 'cross-owner payload reference lookup was accepted';
  exception when sqlstate '55000' then
    null;
  end;

  result := public.connected_app_payload_read_v1(
    '00000000-0000-4000-8000-000000009101', repeat('7', 64)
  );
  if result->>'status' <> 'present' then
    raise exception 'payload read contract failed';
  end if;

  begin
    perform public.connected_app_payload_read_v1(
      '00000000-0000-4000-8000-000000009101', repeat('f', 64)
    );
    raise exception 'cross-identity payload read was accepted';
  exception when sqlstate '55000' then
    null;
  end;

  result := public.connected_app_payload_delete_v1(
    '00000000-0000-4000-8000-000000009101', repeat('7', 64),
    '2026-11-07T20:01:00Z'
  );
  if result <> '{"status":"erased","record_existed":true}'::jsonb then
    raise exception 'payload erase contract failed: %', result;
  end if;
  result := public.connected_app_payload_reference_get_v1(
    '00000000-0000-4000-8000-000000009001',
    '00000000-0000-4000-8000-000000009101',
    '00000000-0000-4000-8000-000000009011',
    '00000000-0000-4000-8000-000000009111',
    'google', 'mail.send'
  );
  if result <> '{"status":"erased","reference":null}'::jsonb then
    raise exception 'payload reference tombstone contract failed: %', result;
  end if;
  result := public.connected_app_payload_put_v1(
    '00000000-0000-4000-8000-000000009101',
    '00000000-0000-4000-8000-000000009001',
    '00000000-0000-4000-8000-000000009011',
    '00000000-0000-4000-8000-000000009111',
    'google', 'mail.send', 'commitment-key', repeat('6', 64),
    '2026-11-07T20:00:00Z', '2026-11-07T21:00:00Z',
    repeat('7', 64), repeat('8', 64), 'payload-key',
    repeat('A', 16), repeat('B', 64), repeat('C', 16), repeat('D', 32),
    repeat('9', 64)
  );
  if result->>'status' <> 'erased' then
    raise exception 'payload tombstone resurrection refusal failed';
  end if;

  result := public.connected_app_credential_create_v1(
    '00000000-0000-4000-8000-000000009001',
    '00000000-0000-4000-8000-000000009011', 'google', repeat('e', 64),
    '00000000-0000-4000-8000-000000009021', repeat('0', 64), 'personal',
    1, repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('d', 64),
    '2026-12-01T00:00:00Z', 1,
    '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z',
    repeat('1', 64), repeat('2', 64), 'credential-key',
    repeat('E', 16), repeat('F', 64), repeat('G', 16), repeat('H', 32),
    repeat('3', 64)
  );
  if result->>'status' <> 'present' then
    raise exception 'credential create contract failed';
  end if;

  result := public.connected_app_credential_claim_refresh_v1(
    repeat('e', 64), repeat('3', 64),
    '00000000-0000-4000-8000-000000009201', 15
  );
  if result->>'status' <> 'claimed' then
    raise exception 'refresh lease claim failed';
  end if;
  result := public.connected_app_credential_claim_refresh_v1(
    repeat('e', 64), repeat('3', 64),
    '00000000-0000-4000-8000-000000009202', 15
  );
  if result->>'status' <> 'busy' then
    raise exception 'refresh lease exclusion failed';
  end if;
  result := public.connected_app_credential_finish_refresh_v1(
    repeat('e', 64), '00000000-0000-4000-8000-000000009201'
  );
  if result->>'status' <> 'finished' then
    raise exception 'refresh lease finish failed';
  end if;

  result := public.connected_app_credential_replace_v1(
    '00000000-0000-4000-8000-000000009001',
    '00000000-0000-4000-8000-000000009011', 'google', repeat('e', 64),
    '00000000-0000-4000-8000-000000009021', repeat('0', 64), 'personal',
    1, repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('d', 64),
    '2026-12-01T00:00:00Z', 2,
    '2026-11-07T20:00:00Z', '2026-11-07T20:03:00Z',
    repeat('1', 64), repeat('4', 64), 'credential-key',
    repeat('I', 16), repeat('J', 64), repeat('K', 16), repeat('L', 32),
    repeat('5', 64), repeat('3', 64)
  );
  if result->'record'->>'secret_revision' <> '2' then
    raise exception 'credential CAS rotation failed';
  end if;

  result := public.connected_app_credential_delete_v1(
    repeat('e', 64), repeat('5', 64), '2026-11-07T20:04:00Z'
  );
  if result <> '{"status":"erased","record_existed":true}'::jsonb then
    raise exception 'credential erase failed: %', result;
  end if;
  begin
    perform public.connected_app_credential_create_v1(
      '00000000-0000-4000-8000-000000009001',
      '00000000-0000-4000-8000-000000009011', 'google', repeat('e', 64),
      '00000000-0000-4000-8000-000000009021', repeat('0', 64), 'personal',
      1, repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('d', 64),
      '2026-12-01T00:00:00Z', 1,
      '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z',
      repeat('1', 64), repeat('2', 64), 'credential-key',
      repeat('E', 16), repeat('F', 64), repeat('G', 16), repeat('H', 32),
      repeat('3', 64)
    );
    raise exception 'retired credential was recreated';
  exception when sqlstate '55000' then
    null;
  end;

  -- Create one envelope of each kind for the second owner, then prove account
  -- cascade leaves only unlinked permanent tombstones.
  perform public.connected_app_payload_put_v1(
    '00000000-0000-4000-8000-000000009102',
    '00000000-0000-4000-8000-000000009002',
    '00000000-0000-4000-8000-000000009012',
    '00000000-0000-4000-8000-000000009112',
    'microsoft', 'calendar.create', 'commitment-key', repeat('6', 64),
    '2026-11-07T20:00:00Z', '2026-11-07T21:00:00Z',
    repeat('a', 64), repeat('b', 64), 'payload-key',
    repeat('M', 16), repeat('N', 64), repeat('O', 16), repeat('P', 32),
    repeat('c', 64)
  );
  perform public.connected_app_credential_create_v1(
    '00000000-0000-4000-8000-000000009002',
    '00000000-0000-4000-8000-000000009012', 'microsoft', repeat('5', 64),
    '00000000-0000-4000-8000-000000009022', repeat('6', 64), 'work_school',
    1, repeat('1', 64), repeat('2', 64), repeat('3', 64), repeat('4', 64),
    '2026-12-01T00:00:00Z', 1,
    '2026-11-07T20:00:00Z', '2026-11-07T20:00:00Z',
    repeat('7', 64), repeat('8', 64), 'credential-key',
    repeat('Q', 16), repeat('R', 64), repeat('S', 16), repeat('T', 32),
    repeat('9', 64)
  );
end;
$behavior$;

reset role;
delete from public.users where id = '00000000-0000-4000-8000-000000009002';

do $deletion$
begin
  if exists (
    select 1 from connected_app_private.payload_envelopes
    where owner_id = '00000000-0000-4000-8000-000000009002'
  ) or exists (
    select 1 from connected_app_private.credential_envelopes
    where owner_id = '00000000-0000-4000-8000-000000009002'
  ) or not exists (
    select 1 from connected_app_private.payload_tombstones
    where payload_id = '00000000-0000-4000-8000-000000009102'
      and identity_sha256 = repeat('a', 64)
  ) or not exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = repeat('5', 64)
  ) then
    raise exception 'account deletion encrypted-store cleanup failed';
  end if;
end;
$deletion$;

select 'CONNECTED_APP_DURABLE_STORE_BEHAVIOR_OK' as result;
