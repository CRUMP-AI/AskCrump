\set ON_ERROR_STOP on

begin;

insert into public.users(id, registration_environment, created_at, updated_at) values
  (
    '00000000-0000-4000-8000-000000008501', 'development',
    pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()
  );

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  current_flow_nonce_sha256
) values (
  '00000000-0000-4000-8000-000000008511',
  '00000000-0000-4000-8000-000000008501',
  'google', 'mail', 'personal',
  '00000000-0000-4000-8000-000000008521', 0, 'pending', repeat('1', 64)
);

set local role service_role;

do $behavior$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  issued_at timestamptz := now_at + interval '2 seconds';
  permit_deadline timestamptz := now_at + interval '2 minutes';
  authorization_expires timestamptz := now_at + interval '1 hour';
  result jsonb;
begin
  begin
    perform 1 from connected_app_private.oauth_permit_capability_custody;
    raise exception 'service_role unexpectedly read private permit custody';
  exception when insufficient_privilege then
    null;
  end;

  perform public.connected_app_oauth_create_pending_v1(
    '00000000-0000-4000-8000-000000008531',
    '00000000-0000-4000-8000-000000008532',
    '00000000-0000-4000-8000-000000008501',
    '00000000-0000-4000-8000-000000008511',
    '00000000-0000-4000-8000-000000008521', 0,
    repeat('1',64), repeat('2',64), 'google', 'mail', 'personal',
    array['mail.get'], repeat('3',64), repeat('4',64), repeat('5',64),
    repeat('P',43), repeat('6',64), repeat('7',64), repeat('8',64),
    now_at, now_at + interval '5 minutes'
  );
  perform public.connected_app_oauth_consume_pending_v1(
    '00000000-0000-4000-8000-000000008531',
    '00000000-0000-4000-8000-000000008531',
    '00000000-0000-4000-8000-000000008501',
    '00000000-0000-4000-8000-000000008511',
    '00000000-0000-4000-8000-000000008521', 0,
    repeat('1',64), repeat('2',64), repeat('7',64), repeat('9',64)
  );

  result := public.connected_app_oauth_put_permit_capability_v2(
    '00000000-0000-4000-8000-000000008541',
    '00000000-0000-4000-8000-000000008531',
    '00000000-0000-4000-8000-000000008511',
    '00000000-0000-4000-8000-000000008541',
    repeat('a',64), repeat('b',64), repeat('c',64),
    issued_at, permit_deadline, 'oauth-key',
    repeat('A',16), repeat('B',64), repeat('C',16), repeat('D',32), repeat('e',64)
  );
  if result->'custody'->>'capability_sha256' <> repeat('a',64)
     or result->'custody' ? 'capability_secret' then
    raise exception 'encrypted permit custody projection drifted: %', result;
  end if;
  result := public.connected_app_oauth_read_permit_capability_v2(
    '00000000-0000-4000-8000-000000008541', repeat('c',64)
  );
  if result->>'permit_id' <> '00000000-0000-4000-8000-000000008541'
     or result->>'capability_sha256' <> repeat('a',64)
     or result ? 'capability_secret' then
    raise exception 'live-authority permit recovery drifted: %', result;
  end if;

  result := public.connected_app_oauth_consume_permit_v2(
    '00000000-0000-4000-8000-000000008541',
    '00000000-0000-4000-8000-000000008531',
    '00000000-0000-4000-8000-000000008511',
    '00000000-0000-4000-8000-000000008541',
    repeat('a',64), repeat('b',64), repeat('c',64),
    '00000000-0000-4000-8000-000000008541'
  );
  if result->>'claimed' <> 'true'
     or result->>'status' <> 'attempt_fenced'
     or result->>'consumed_at' is null then
    raise exception 'fresh permit claim failed: %', result;
  end if;
  if public.connected_app_oauth_read_permit_capability_v2(
       '00000000-0000-4000-8000-000000008541', repeat('c',64)
     ) is not null then
    raise exception 'consumed raw permit capability was retained';
  end if;
  result := public.connected_app_oauth_consume_permit_v2(
    '00000000-0000-4000-8000-000000008541',
    '00000000-0000-4000-8000-000000008531',
    '00000000-0000-4000-8000-000000008511',
    '00000000-0000-4000-8000-000000008541',
    repeat('a',64), repeat('b',64), repeat('c',64),
    '00000000-0000-4000-8000-000000008541'
  );
  if result->>'claimed' <> 'false'
     or result->>'status' <> 'attempt_fenced' then
    raise exception 'permit replay received a dispatch claim: %', result;
  end if;

  result := public.connected_app_oauth_finalize_v2(
    '00000000-0000-4000-8000-000000008531',
    '00000000-0000-4000-8000-000000008531',
    '00000000-0000-4000-8000-000000008541', repeat('c',64),
    '00000000-0000-4000-8000-000000008541',
    '00000000-0000-4000-8000-000000008501',
    '00000000-0000-4000-8000-000000008511',
    '00000000-0000-4000-8000-000000008521', 0, repeat('1',64),
    'google', 'mail', 'personal', repeat('d',64), repeat('4',64),
    '00000000-0000-4000-8000-000000008551', repeat('e',64),
    issued_at, authorization_expires, repeat('0',64),
    '00000000-0000-4000-8000-000000008531', repeat('f',64),
    '00000000-0000-4000-8000-000000008541', repeat('1',64)
  );
  if result->>'completed' <> 'true' or result->>'active' <> 'true'
     or result->>'completion_binding_sha256' <> repeat('f',64)
     or result->>'authorization_snapshot_sha256' <> repeat('0',64)
     or (result->>'authorization_issued_at')::timestamptz <> issued_at then
    raise exception 'separate completion/authorization finalize failed: %', result;
  end if;

  result := public.connected_app_get_binding_v2(
    '00000000-0000-4000-8000-000000008501',
    '00000000-0000-4000-8000-000000008511'
  );
  if result->>'authorization_snapshot_sha256' <> repeat('0',64)
     or (result->>'authorization_issued_at')::timestamptz <> issued_at
     or result->>'credential_ref_sha256' <> repeat('e',64) then
    raise exception 'restart binding projection failed: %', result;
  end if;

  -- The credential-vault create must accept the true authorization snapshot,
  -- not the unrelated OAuth completion replay hash.
  result := public.connected_app_credential_create_v1(
    '00000000-0000-4000-8000-000000008501',
    '00000000-0000-4000-8000-000000008511', 'google', repeat('e',64),
    '00000000-0000-4000-8000-000000008521', repeat('2',64), 'personal',
    1, repeat('0',64), repeat('3',64), repeat('4',64), repeat('d',64),
    authorization_expires, 1, now_at, now_at,
    repeat('5',64), repeat('6',64), 'credential-key',
    repeat('E',16), repeat('F',64), repeat('G',16), repeat('H',32), repeat('7',64)
  );
  if result->>'status' <> 'present'
     or result->'record'->>'authorization_snapshot_sha256' <> repeat('0',64) then
    raise exception 'credential-vault activation against true snapshot failed: %', result;
  end if;
  begin
    perform public.connected_app_credential_create_v1(
      '00000000-0000-4000-8000-000000008501',
      '00000000-0000-4000-8000-000000008511', 'google', repeat('e',64),
      '00000000-0000-4000-8000-000000008521', repeat('2',64), 'personal',
      1, repeat('f',64), repeat('3',64), repeat('4',64), repeat('d',64),
      authorization_expires, 1, now_at, now_at,
      repeat('5',64), repeat('6',64), 'credential-key',
      repeat('E',16), repeat('F',64), repeat('G',16), repeat('H',32), repeat('7',64)
    );
    raise exception 'credential vault accepted completion replay hash as authority';
  exception when sqlstate '55000' then
    null;
  end;

  -- A normal active-to-revoked transition must preserve the exact historical
  -- authorization issue instant without breaking the existing revocation RPC.
  result := public.connected_app_revoke_connection_v1(
    '00000000-0000-4000-8000-000000008501',
    '00000000-0000-4000-8000-000000008511',
    '00000000-0000-4000-8000-000000008561', repeat('e',64), repeat('8',64)
  );
  if result->>'authorization_state' <> 'revoked'
     or (result->>'authorization_issued_at')::timestamptz <> issued_at then
    raise exception 'revocation lost exact authorization issue time: %', result;
  end if;
  result := public.connected_app_read_credential_cleanup_v2(
    '00000000-0000-4000-8000-000000008561', repeat('8',64)
  );
  if result->>'cleanup_binding_sha256' <> repeat('8',64) then
    raise exception 'revocation cleanup replay was not durable: %', result;
  end if;
end;
$behavior$;

rollback;

select 'CONNECTED_OAUTH_RUNTIME_AUTHORITY_OK' as result;
