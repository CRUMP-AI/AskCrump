\set ON_ERROR_STOP on

insert into public.users(id) values
  ('00000000-0000-4000-8000-000000008001');

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  current_flow_nonce_sha256, created_at, updated_at
) values (
  '00000000-0000-4000-8000-000000008011',
  '00000000-0000-4000-8000-000000008001',
  'google', 'mail', 'personal',
  '00000000-0000-4000-8000-000000008021', 0, 'pending',
  repeat('1', 64), pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()
);

set role service_role;

do $behavior$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  flow_expires timestamptz := now_at + interval '5 minutes';
  result jsonb;
begin
  -- Current-flow nonce authority is not caller asserted. A mismatched start
  -- must fail before encrypted state/PKCE ciphertext becomes durable.
  begin
    perform public.connected_app_oauth_secret_begin_v1(
      '00000000-0000-4000-8000-000000008101',
      '00000000-0000-4000-8000-000000008102',
      '00000000-0000-4000-8000-000000008001',
      '00000000-0000-4000-8000-000000008011',
      '00000000-0000-4000-8000-000000008021', 0,
      repeat('0',64), repeat('2',64), 'google', 'mail', 'personal',
      array['mail.search'], repeat('3',64), array['scope-a'], repeat('4',64),
      repeat('5',64), repeat('P',43),
      'https://askcrump.com/oauth/callback', now_at, flow_expires,
      repeat('6',64), 'oauth-key', repeat('A',16), repeat('B',64),
      repeat('C',16), repeat('D',32), repeat('7',64)
    );
    raise exception 'OAuth custody accepted stale current-flow nonce';
  exception when sqlstate '55000' then
    null;
  end;

  result := public.connected_app_oauth_secret_begin_v1(
    '00000000-0000-4000-8000-000000008101',
    '00000000-0000-4000-8000-000000008102',
    '00000000-0000-4000-8000-000000008001',
    '00000000-0000-4000-8000-000000008011',
    '00000000-0000-4000-8000-000000008021', 0,
    repeat('1',64), repeat('2',64), 'google', 'mail', 'personal',
    array['mail.search'], repeat('3',64), array['scope-a'], repeat('4',64),
    repeat('5',64), repeat('P',43),
    'https://askcrump.com/oauth/callback', now_at, flow_expires,
    repeat('6',64), 'oauth-key', repeat('A',16), repeat('B',64),
    repeat('C',16), repeat('D',32), repeat('7',64)
  );
  if result->>'status' <> 'present'
     or result->'record'->>'status' <> 'pending'
     or result->'record' ? 'state'
     or result->'record' ? 'verifier' then
    raise exception 'OAuth secret begin shape drifted: %', result;
  end if;

  -- Exact begin replay is a readback, while changed ciphertext binding fails.
  result := public.connected_app_oauth_secret_begin_v1(
    '00000000-0000-4000-8000-000000008101',
    '00000000-0000-4000-8000-000000008102',
    '00000000-0000-4000-8000-000000008001',
    '00000000-0000-4000-8000-000000008011',
    '00000000-0000-4000-8000-000000008021', 0,
    repeat('1',64), repeat('2',64), 'google', 'mail', 'personal',
    array['mail.search'], repeat('3',64), array['scope-a'], repeat('4',64),
    repeat('5',64), repeat('P',43),
    'https://askcrump.com/oauth/callback', now_at, flow_expires,
    repeat('6',64), 'oauth-key', repeat('A',16), repeat('B',64),
    repeat('C',16), repeat('D',32), repeat('7',64)
  );
  if result->'record'->>'secret_record_binding_sha256' <> repeat('7',64) then
    raise exception 'OAuth secret begin replay readback drifted';
  end if;

  result := public.connected_app_oauth_secret_read_flow_v1(
    '00000000-0000-4000-8000-000000008101',
    '00000000-0000-4000-8000-000000008001',
    '00000000-0000-4000-8000-000000008011',
    '00000000-0000-4000-8000-000000008021', 0, repeat('1',64)
  );
  if result->>'status' <> 'present' then
    raise exception 'OAuth secret read failed: %', result;
  end if;

  result := public.connected_app_oauth_secret_fence_v1(
    '00000000-0000-4000-8000-000000008101',
    '00000000-0000-4000-8000-000000008111', repeat('8',64),
    repeat('6',64), '00000000-0000-4000-8000-000000008121',
    now_at + interval '2 minutes'
  );
  if result->>'status' <> 'claimed' or result->>'fresh' <> 'true' then
    raise exception 'OAuth exchange fence failed: %', result;
  end if;

  -- Same attempt recovers a lost fence response; a different attempt cannot
  -- dispatch a second provider exchange.
  result := public.connected_app_oauth_secret_fence_v1(
    '00000000-0000-4000-8000-000000008101',
    '00000000-0000-4000-8000-000000008111', repeat('8',64),
    repeat('6',64), '00000000-0000-4000-8000-000000008121',
    now_at + interval '2 minutes'
  );
  if result->>'status' <> 'fenced' or result->>'fresh' <> 'true' then
    raise exception 'OAuth same-attempt fence recovery failed: %', result;
  end if;
  result := public.connected_app_oauth_secret_fence_v1(
    '00000000-0000-4000-8000-000000008101',
    '00000000-0000-4000-8000-000000008111', repeat('8',64),
    repeat('6',64), '00000000-0000-4000-8000-000000008122',
    now_at + interval '2 minutes'
  );
  if result->>'fresh' <> 'false' then
    raise exception 'OAuth second attempt was not fenced: %', result;
  end if;

  result := public.connected_app_oauth_secret_grant_v1(
    p_flow_id => '00000000-0000-4000-8000-000000008101',
    p_exchange_id => '00000000-0000-4000-8000-000000008111',
    p_exchange_binding_sha256 => repeat('8',64),
    p_attempt_id => '00000000-0000-4000-8000-000000008121',
    p_credential_handle_sha256 => repeat('9',64),
    p_external_account_id_hash => repeat('a',64),
    p_actual_scopes => array['scope-a'],
    p_actual_scopes_sha256 => repeat('4',64),
    p_issued_at => now_at, p_expires_at => now_at + interval '1 hour',
    p_provisional_id => '00000000-0000-4000-8000-000000008131',
    p_oauth_client_id_sha256 => repeat('b',64),
    p_provisional_binding_sha256 => repeat('c',64),
    p_terminal_key_id => 'oauth-key',
    p_terminal_wrapped_key_nonce => repeat('E',16),
    p_terminal_wrapped_key_ciphertext => repeat('F',64),
    p_terminal_secret_nonce => repeat('G',16),
    p_terminal_secret_ciphertext => repeat('H',32),
    p_terminal_record_binding_sha256 => repeat('d',64),
    p_provisional_key_id => 'oauth-key',
    p_provisional_wrapped_key_nonce => repeat('I',16),
    p_provisional_wrapped_key_ciphertext => repeat('J',64),
    p_provisional_secret_nonce => repeat('K',16),
    p_provisional_secret_ciphertext => repeat('L',32),
    p_provisional_record_binding_sha256 => repeat('e',64)
  );
  if result->>'status' <> 'granted'
     or result->'record'->'provisional'->>'status' <> 'provisional'
     or result->'record'->'provisional' ? 'refresh_token'
     or result->'record'->'flow' ? 'credential_handle' then
    raise exception 'OAuth provisional grant shape drifted: %', result;
  end if;

  result := public.connected_app_oauth_secret_read_exchange_v1(
    '00000000-0000-4000-8000-000000008101',
    '00000000-0000-4000-8000-000000008111', repeat('8',64)
  );
  if result->>'status' <> 'granted'
     or result->'record'->>'credential_handle_sha256' <> repeat('9',64) then
    raise exception 'OAuth grant readback failed: %', result;
  end if;

  result := public.connected_app_oauth_provisional_read_v1(repeat('9',64));
  if result->>'status' <> 'provisional'
     or result->'record'->>'record_binding_sha256' <> repeat('e',64) then
    raise exception 'OAuth provisional read failed: %', result;
  end if;
  result := public.connected_app_oauth_provisional_erase_v1(
    repeat('9',64), repeat('e',64)
  );
  if result <> '{"status":"erased","record_existed":true}'::jsonb then
    raise exception 'OAuth provisional erase failed: %', result;
  end if;
  result := public.connected_app_oauth_secret_read_exchange_v1(
    '00000000-0000-4000-8000-000000008101',
    '00000000-0000-4000-8000-000000008111', repeat('8',64)
  );
  if result->>'status' <> 'granted'
     or result->'record'->'provisional' <> 'null'::jsonb then
    raise exception 'OAuth terminal recovery after activation drifted: %', result;
  end if;
  result := public.connected_app_oauth_secret_abort_v1(
    '00000000-0000-4000-8000-000000008101', repeat('6',64), 'aborted'
  );
  if result->>'status' <> 'erased' then
    raise exception 'OAuth terminal cleanup failed';
  end if;

  -- A post-exchange identity failure keeps the refresh token encrypted and
  -- quarantined, then abort atomically tombstones that provisional material.
  result := public.connected_app_oauth_secret_begin_v1(
    '00000000-0000-4000-8000-000000008201',
    '00000000-0000-4000-8000-000000008202',
    '00000000-0000-4000-8000-000000008001',
    '00000000-0000-4000-8000-000000008011',
    '00000000-0000-4000-8000-000000008021', 0,
    repeat('1',64), repeat('2',64), 'google', 'mail', 'personal',
    array['mail.search'], repeat('3',64), array['scope-a'], repeat('4',64),
    repeat('5',64), repeat('P',43),
    'https://askcrump.com/oauth/callback', now_at, flow_expires,
    repeat('f',64), 'oauth-key', repeat('A',16), repeat('B',64),
    repeat('C',16), repeat('D',32), repeat('0',64)
  );
  perform public.connected_app_oauth_secret_fence_v1(
    '00000000-0000-4000-8000-000000008201',
    '00000000-0000-4000-8000-000000008211', repeat('1',64),
    repeat('f',64), '00000000-0000-4000-8000-000000008221',
    now_at + interval '2 minutes'
  );
  result := public.connected_app_oauth_secret_ambiguous_v1(
    p_flow_id => '00000000-0000-4000-8000-000000008201',
    p_exchange_id => '00000000-0000-4000-8000-000000008211',
    p_exchange_binding_sha256 => repeat('1',64),
    p_attempt_id => '00000000-0000-4000-8000-000000008221',
    p_observed_at => now_at, p_quarantine => true,
    p_provisional_id => '00000000-0000-4000-8000-000000008231',
    p_credential_handle_sha256 => repeat('2',64),
    p_oauth_client_id_sha256 => repeat('3',64),
    p_external_account_id_hash => repeat('0',64),
    p_actual_scopes => array['scope-a'],
    p_actual_scopes_sha256 => repeat('4',64),
    p_issued_at => now_at, p_expires_at => now_at + interval '1 hour',
    p_provisional_binding_sha256 => repeat('5',64),
    p_provisional_key_id => 'oauth-key',
    p_provisional_wrapped_key_nonce => repeat('M',16),
    p_provisional_wrapped_key_ciphertext => repeat('N',64),
    p_provisional_secret_nonce => repeat('O',16),
    p_provisional_secret_ciphertext => repeat('Q',32),
    p_provisional_record_binding_sha256 => repeat('6',64)
  );
  if result->>'status' <> 'ambiguous' then
    raise exception 'OAuth quarantined ambiguity failed: %', result;
  end if;
  result := public.connected_app_oauth_provisional_read_v1(repeat('2',64));
  if result->>'status' <> 'quarantined' then
    raise exception 'OAuth quarantine readback failed: %', result;
  end if;
  perform public.connected_app_oauth_secret_abort_v1(
    '00000000-0000-4000-8000-000000008201', repeat('f',64), 'expired'
  );
  result := public.connected_app_oauth_provisional_read_v1(repeat('2',64));
  if result <> '{"status":"erased","record":null}'::jsonb then
    raise exception 'OAuth quarantine abort did not tombstone custody: %', result;
  end if;

end;
$behavior$;

reset role;

do $private_invariants$
begin
  if exists (
    select 1 from connected_app_private.oauth_secret_custody
    where flow_id in (
      '00000000-0000-4000-8000-000000008101',
      '00000000-0000-4000-8000-000000008201'
    )
  ) or not exists (
    select 1 from connected_app_private.oauth_provisional_tombstones
    where credential_handle_sha256 = repeat('2',64)
  ) then
    raise exception 'OAuth secret cleanup invariants failed';
  end if;
end;
$private_invariants$;

select 'CONNECTED_APP_OAUTH_SECRET_CUSTODY_BEHAVIOR_OK' as result;
