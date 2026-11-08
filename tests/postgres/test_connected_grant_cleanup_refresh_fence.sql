\set ON_ERROR_STOP on

begin;

insert into public.users(id, created_at, registration_environment) values
  ('10000000-0000-4000-8000-000000006101', pg_catalog.clock_timestamp(), 'development'),
  ('10000000-0000-4000-8000-000000006102', pg_catalog.clock_timestamp(), 'development');

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256, authorization_expires_at
) values
  (
    '20000000-0000-4000-8000-000000006101',
    '10000000-0000-4000-8000-000000006101',
    'google', 'mail', 'personal',
    '20000000-0000-4000-8000-000000006111', 1, 'active',
    repeat('a',64), array['mail.get'], repeat('b',64), repeat('c',64),
    repeat('d',64), '20000000-0000-4000-8000-000000006121', repeat('e',64),
    pg_catalog.clock_timestamp() + interval '2 hours'
  ),
  (
    '20000000-0000-4000-8000-000000006102',
    '10000000-0000-4000-8000-000000006102',
    'microsoft', 'mail', 'work_school',
    '20000000-0000-4000-8000-000000006112', 1, 'active',
    repeat('1',64), array['mail.get'], repeat('2',64), repeat('3',64),
    repeat('4',64), '20000000-0000-4000-8000-000000006122', repeat('5',64),
    pg_catalog.clock_timestamp() + interval '2 hours'
  );

do $behavior$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  expiry timestamptz;
  result jsonb;
  encrypted_record jsonb;
begin
  select authorization_expires_at into expiry
  from connected_app_private.connections
  where id = '20000000-0000-4000-8000-000000006101';

  perform public.connected_app_credential_create_v1(
    '10000000-0000-4000-8000-000000006101',
    '20000000-0000-4000-8000-000000006101', 'google', repeat('e',64),
    '20000000-0000-4000-8000-000000006111', repeat('0',64), 'personal',
    1, repeat('a',64), repeat('b',64), repeat('c',64), repeat('d',64),
    expiry, 1, now_at, now_at, repeat('6',64), repeat('7',64),
    'credential-key', repeat('A',16), repeat('B',64), repeat('C',16),
    repeat('D',32), repeat('8',64)
  );

  result := public.connected_app_credential_claim_refresh_v2(
    repeat('e',64), repeat('8',64),
    '30000000-0000-4000-8000-000000006101', 1
  );
  if result->>'status' <> 'claimed' then
    raise exception 'v2 refresh claim failed: %', result;
  end if;
  perform pg_catalog.pg_sleep(1.05);
  result := public.connected_app_credential_claim_refresh_v2(
    repeat('e',64), repeat('8',64),
    '30000000-0000-4000-8000-000000006101', 1
  );
  if result->>'status' <> 'stale' then
    raise exception 'expired same-ID refresh claim revived: %', result;
  end if;
  if public.connected_app_credential_claim_refresh_v2(
       repeat('e',64), repeat('8',64),
       '30000000-0000-4000-8000-000000006101', 1
     )->>'status' <> 'stale' then
    raise exception 'retired refresh ID replay was not permanently stale';
  end if;

  result := public.connected_app_credential_claim_refresh_v2(
    repeat('e',64), repeat('8',64),
    '30000000-0000-4000-8000-000000006102', 30
  );
  if result->>'status' <> 'claimed' then
    raise exception 'fresh v2 refresh claim failed: %', result;
  end if;
  result := public.connected_app_credential_commit_refresh_v2(
    p_owner_id => '10000000-0000-4000-8000-000000006101',
    p_connection_id => '20000000-0000-4000-8000-000000006101',
    p_provider => 'google', p_credential_handle_sha256 => repeat('e',64),
    p_connection_incarnation_id => '20000000-0000-4000-8000-000000006111',
    p_oauth_client_id_sha256 => repeat('0',64), p_account_kind => 'personal',
    p_authorization_revision => 1,
    p_authorization_snapshot_sha256 => repeat('a',64),
    p_granted_actions_sha256 => repeat('b',64),
    p_granted_scopes_sha256 => repeat('c',64),
    p_external_account_id_hash => repeat('d',64),
    p_authorization_expires_at => expiry, p_secret_revision => 2,
    p_created_at => now_at, p_updated_at => now_at + interval '2 seconds',
    p_authority_binding_sha256 => repeat('6',64),
    p_metadata_binding_sha256 => repeat('9',64), p_key_id => 'credential-key',
    p_wrapped_key_nonce => repeat('E',16),
    p_wrapped_key_ciphertext => repeat('F',64),
    p_secret_nonce => repeat('G',16), p_secret_ciphertext => repeat('H',32),
    p_record_binding_sha256 => repeat('f',64),
    p_expected_record_binding_sha256 => repeat('8',64),
    p_lease_id => '30000000-0000-4000-8000-000000006102'
  );
  if result->>'status' <> 'present'
     or result->'record'->>'record_binding_sha256' <> repeat('f',64) then
    raise exception 'v2 refresh atomic commit failed: %', result;
  end if;
  if public.connected_app_credential_commit_refresh_v2(
    p_owner_id => '10000000-0000-4000-8000-000000006101',
    p_connection_id => '20000000-0000-4000-8000-000000006101',
    p_provider => 'google', p_credential_handle_sha256 => repeat('e',64),
    p_connection_incarnation_id => '20000000-0000-4000-8000-000000006111',
    p_oauth_client_id_sha256 => repeat('0',64), p_account_kind => 'personal',
    p_authorization_revision => 1,
    p_authorization_snapshot_sha256 => repeat('a',64),
    p_granted_actions_sha256 => repeat('b',64),
    p_granted_scopes_sha256 => repeat('c',64),
    p_external_account_id_hash => repeat('d',64),
    p_authorization_expires_at => expiry, p_secret_revision => 2,
    p_created_at => now_at, p_updated_at => now_at + interval '2 seconds',
    p_authority_binding_sha256 => repeat('6',64),
    p_metadata_binding_sha256 => repeat('9',64), p_key_id => 'credential-key',
    p_wrapped_key_nonce => repeat('E',16),
    p_wrapped_key_ciphertext => repeat('F',64),
    p_secret_nonce => repeat('G',16), p_secret_ciphertext => repeat('H',32),
    p_record_binding_sha256 => repeat('f',64),
    p_expected_record_binding_sha256 => repeat('8',64),
    p_lease_id => '30000000-0000-4000-8000-000000006102'
  )->'record'->>'record_binding_sha256' <> repeat('f',64) then
    raise exception 'v2 refresh lost-response replay drifted';
  end if;

  insert into connected_app_private.oauth_provisional_credentials (
    provisional_id, owner_id, connection_id, connection_incarnation_id,
    flow_id, exchange_id, provider, account_kind, status,
    credential_handle_sha256, oauth_client_id_sha256,
    external_account_id_hash, granted_scopes, granted_scopes_sha256,
    exchange_binding_sha256, issued_at, expires_at, authority_binding_sha256,
    key_id, wrapped_key_nonce, wrapped_key_ciphertext, secret_nonce,
    secret_ciphertext, record_binding_sha256
  ) values (
    '40000000-0000-4000-8000-000000006101',
    '10000000-0000-4000-8000-000000006101',
    '20000000-0000-4000-8000-000000006101',
    '20000000-0000-4000-8000-000000006111',
    '40000000-0000-4000-8000-000000006102',
    '40000000-0000-4000-8000-000000006103', 'google', 'personal',
    'provisional', repeat('e',64), repeat('0',64), repeat('d',64),
    array['scope-a'], repeat('c',64), repeat('a',64), now_at,
    now_at + interval '1 hour', repeat('7',64), 'oauth-key',
    repeat('I',16), repeat('J',64), repeat('K',16), repeat('L',32),
    repeat('4',64)
  );
  select pg_catalog.to_jsonb(provisional.*) into encrypted_record
  from connected_app_private.oauth_provisional_credentials as provisional
  where provisional_id = '40000000-0000-4000-8000-000000006101';

  perform public.connected_app_provider_cleanup_begin_v1(
    '40000000-0000-4000-8000-000000006103',
    '10000000-0000-4000-8000-000000006101',
    '20000000-0000-4000-8000-000000006101',
    '40000000-0000-4000-8000-000000006103',
    'google', repeat('a',64), pg_catalog.clock_timestamp() + interval '5 minutes'
  );
  perform public.connected_app_provider_cleanup_attach_v1(
    '40000000-0000-4000-8000-000000006103', repeat('a',64),
    'provisional', repeat('4',64), encrypted_record
  );
  begin
    perform public.connected_app_provider_cleanup_release_v1(
      '40000000-0000-4000-8000-000000006103', repeat('4',64)
    );
    raise exception 'cleanup released before source ciphertext erasure';
  exception when sqlstate '55000' then
    null;
  end;
end;
$behavior$;

delete from connected_app_private.oauth_provisional_credentials
where provisional_id = '40000000-0000-4000-8000-000000006101';

do $release_and_deletion$
declare
  expiry timestamptz;
  now_at timestamptz := pg_catalog.clock_timestamp();
  result jsonb;
begin
  begin
    perform public.connected_app_provider_cleanup_release_recover_v1(
      '40000000-0000-4000-8000-000000006103', repeat('0',64)
    );
    raise exception 'cleanup release recovery accepted a wrong credential handle';
  exception when sqlstate '55000' then
    null;
  end;
  result := public.connected_app_provider_cleanup_release_recover_v1(
    '40000000-0000-4000-8000-000000006103', repeat('e',64)
  );
  if result->>'status' <> 'released' then
    raise exception 'cleanup release recovery after exact custody transfer failed: %', result;
  end if;

  select authorization_expires_at into expiry
  from connected_app_private.connections
  where id = '20000000-0000-4000-8000-000000006102';
  perform public.connected_app_credential_create_v1(
    '10000000-0000-4000-8000-000000006102',
    '20000000-0000-4000-8000-000000006102', 'microsoft', repeat('5',64),
    '20000000-0000-4000-8000-000000006112', repeat('6',64), 'work_school',
    1, repeat('1',64), repeat('2',64), repeat('3',64), repeat('4',64),
    expiry, 1, now_at, now_at, repeat('7',64), repeat('8',64),
    'credential-key', repeat('M',16), repeat('N',64), repeat('O',16),
    repeat('P',32), repeat('9',64)
  );
  perform public.connected_app_provider_cleanup_begin_v1(
    '40000000-0000-4000-8000-000000006104',
    '10000000-0000-4000-8000-000000006102',
    '20000000-0000-4000-8000-000000006102',
    '40000000-0000-4000-8000-000000006104',
    'microsoft', repeat('6',64), pg_catalog.clock_timestamp() + interval '5 minutes'
  );
end;
$release_and_deletion$;

delete from public.users where id = '10000000-0000-4000-8000-000000006102';

do $assertions$
declare result jsonb;
begin
  if not exists (
    select 1 from connected_app_private.provider_grant_cleanup_jobs
    where provider = 'microsoft' and source_kind = 'credential'
      and source_binding_sha256 = repeat('9',64)
      and status = 'cleanup_pending' and encrypted_record is not null
      and owner_id is null and connection_id is null
      and owner_id_sha256 ~ '^[0-9a-f]{64}$'
      and connection_id_sha256 ~ '^[0-9a-f]{64}$'
  ) then
    raise exception 'account cascade discarded or linked an external grant cleanup';
  end if;
  if not exists (
    select 1 from connected_app_private.provider_grant_cleanup_jobs
    where cleanup_id = '40000000-0000-4000-8000-000000006104'
      and status = 'user_action_required' and encrypted_record is null
      and owner_id is null and connection_id is null
  ) then
    raise exception 'exchange-unknown account deletion was not preserved honestly';
  end if;

  result := public.connected_app_provider_cleanup_claim_v1(
    '50000000-0000-4000-8000-000000006101', 30
  );
  if result->>'status' <> 'claimed' or result->'record'->>'provider' <> 'microsoft' then
    raise exception 'durable cleanup claim failed: %', result;
  end if;
  if public.connected_app_provider_cleanup_recover_v1(
       '50000000-0000-4000-8000-000000006101'
     ) is distinct from result then
    raise exception 'cleanup lost-response recovery drifted';
  end if;
  result := public.connected_app_provider_cleanup_finish_v1(
    (result->'record'->>'cleanup_id')::uuid,
    '50000000-0000-4000-8000-000000006101',
    'user_action_required', null
  );
  if result->>'status' <> 'user_action_required' then
    raise exception 'Microsoft honest action-required settlement failed: %', result;
  end if;
  if exists (
    select 1 from connected_app_private.provider_grant_cleanup_jobs
    where cleanup_id = (result->>'cleanup_id')::uuid and encrypted_record is not null
  ) then
    raise exception 'terminal cleanup retained encrypted credential material';
  end if;

  if pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_credential_claim_refresh_v1(text,text,uuid,integer)',
       'EXECUTE'
     ) or pg_catalog.has_function_privilege(
       'service_role', 'public.connected_app_credential_finish_refresh_v1(text,uuid)',
       'EXECUTE'
     ) or not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_credential_commit_refresh_v2(uuid,uuid,text,text,uuid,text,text,bigint,text,text,text,text,timestamp with time zone,bigint,timestamp with time zone,timestamp with time zone,text,text,text,text,text,text,text,text,text,uuid)',
       'EXECUTE'
     ) then
    raise exception 'refresh v1 fallback or v2 authority ACL drifted';
  end if;
end;
$assertions$;

rollback;

select 'CONNECTED_GRANT_CLEANUP_REFRESH_FENCE_OK' as result;
