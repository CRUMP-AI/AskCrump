\set ON_ERROR_STOP on

begin;

insert into public.users(id, created_at, registration_environment) values
  (
    '10000000-0000-4000-8000-000000006501',
    pg_catalog.clock_timestamp(), 'development'
  ),
  (
    '10000000-0000-4000-8000-000000006502',
    pg_catalog.clock_timestamp(), 'development'
  );

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256, authorization_expires_at
) values
  (
    '20000000-0000-4000-8000-000000006501',
    '10000000-0000-4000-8000-000000006501',
    'google', 'mail', 'personal',
    '20000000-0000-4000-8000-000000006511', 1, 'active',
    repeat('1',64), array['mail.get'], repeat('2',64), repeat('3',64),
    repeat('4',64), '20000000-0000-4000-8000-000000006521', repeat('5',64),
    pg_catalog.clock_timestamp() + interval '2 hours'
  ),
  (
    '20000000-0000-4000-8000-000000006502',
    '10000000-0000-4000-8000-000000006502',
    'microsoft', 'calendar', 'work_school',
    '20000000-0000-4000-8000-000000006512', 1, 'active',
    repeat('6',64), array['calendar.get'], repeat('7',64), repeat('8',64),
    repeat('9',64), '20000000-0000-4000-8000-000000006522', repeat('a',64),
    pg_catalog.clock_timestamp() + interval '2 hours'
  );

do $fixtures$
declare
  reference_at timestamptz := pg_catalog.clock_timestamp();
begin
  insert into connected_app_private.oauth_secret_custody (
    flow_id, nonce_id, owner_id, connection_id, connection_incarnation_id,
    expected_base_revision, current_flow_nonce_sha256, session_binding_sha256,
    provider, resource, account_kind, actions, actions_sha256,
    requested_scopes, requested_scopes_sha256, state_sha256, pkce_challenge,
    redirect_uri, created_at, expires_at, flow_binding_sha256,
    secret_key_id, secret_wrapped_key_nonce, secret_wrapped_key_ciphertext,
    secret_nonce, secret_ciphertext, secret_record_binding_sha256
  ) values
    (
      '30000000-0000-4000-8000-000000006501',
      '30000000-0000-4000-8000-000000006511',
      '10000000-0000-4000-8000-000000006501',
      '20000000-0000-4000-8000-000000006501',
      '20000000-0000-4000-8000-000000006511', 1,
      repeat('b',64), repeat('c',64), 'google', 'mail', 'personal',
      array['mail.get'], repeat('d',64), array['scope-a'], repeat('e',64),
      repeat('f',64), repeat('P',43), 'https://www.askcrump.com/oauth/callback',
      reference_at - interval '2 minutes', reference_at - interval '1 minute',
      repeat('0',64), 'oauth-key', repeat('A',16), repeat('B',64),
      repeat('C',16), repeat('D',32), repeat('1',64)
    ),
    (
      '30000000-0000-4000-8000-000000006502',
      '30000000-0000-4000-8000-000000006512',
      '10000000-0000-4000-8000-000000006502',
      '20000000-0000-4000-8000-000000006502',
      '20000000-0000-4000-8000-000000006512', 1,
      repeat('2',64), repeat('3',64), 'microsoft', 'calendar', 'work_school',
      array['calendar.get'], repeat('4',64), array['scope-b'], repeat('5',64),
      repeat('6',64), repeat('Q',43), 'https://www.askcrump.com/oauth/callback',
      reference_at - interval '2 minutes', reference_at - interval '1 minute',
      repeat('7',64), 'oauth-key', repeat('E',16), repeat('F',64),
      repeat('G',16), repeat('H',32), repeat('8',64)
    );

  insert into connected_app_private.oauth_provisional_credentials (
    provisional_id, owner_id, connection_id, connection_incarnation_id,
    flow_id, exchange_id, provider, account_kind, status,
    credential_handle_sha256, oauth_client_id_sha256,
    external_account_id_hash, granted_scopes, granted_scopes_sha256,
    exchange_binding_sha256, issued_at, expires_at, authority_binding_sha256,
    key_id, wrapped_key_nonce, wrapped_key_ciphertext, secret_nonce,
    secret_ciphertext, record_binding_sha256
  ) values
    (
      '40000000-0000-4000-8000-000000006501',
      '10000000-0000-4000-8000-000000006501',
      '20000000-0000-4000-8000-000000006501',
      '20000000-0000-4000-8000-000000006511',
      '40000000-0000-4000-8000-000000006511',
      '40000000-0000-4000-8000-000000006521',
      'google', 'personal', 'provisional', repeat('9',64), repeat('a',64),
      repeat('b',64), array['scope-a'], repeat('c',64), repeat('d',64),
      reference_at - interval '2 hours', reference_at - interval '1 hour',
      repeat('e',64), 'oauth-key', repeat('I',16), repeat('J',64),
      repeat('K',16), repeat('L',32), repeat('f',64)
    ),
    (
      '40000000-0000-4000-8000-000000006502',
      '10000000-0000-4000-8000-000000006502',
      '20000000-0000-4000-8000-000000006502',
      '20000000-0000-4000-8000-000000006512',
      '40000000-0000-4000-8000-000000006512',
      '40000000-0000-4000-8000-000000006522',
      'microsoft', 'work_school', 'quarantined', repeat('0',64), repeat('1',64),
      repeat('0',64), array['scope-b'], repeat('3',64), repeat('4',64),
      reference_at - interval '2 hours', reference_at - interval '1 hour',
      repeat('5',64), 'oauth-key', repeat('M',16), repeat('N',64),
      repeat('O',16), repeat('P',32), repeat('6',64)
    );
end;
$fixtures$;

do $authority$
begin
  if not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_oauth_reconcile_expired_v1(integer)',
       'EXECUTE'
     ) or pg_catalog.has_function_privilege(
       'anon',
       'public.connected_app_oauth_reconcile_expired_v1(integer)',
       'EXECUTE'
     ) or pg_catalog.has_function_privilege(
       'authenticated',
       'public.connected_app_oauth_reconcile_expired_v1(integer)',
       'EXECUTE'
     ) then
    raise exception 'reconciliation RPC authority drifted';
  end if;
end;
$authority$;

set local role anon;
do $anon_refusal$
begin
  begin
    perform public.connected_app_oauth_reconcile_expired_v1(1);
    raise exception 'anon unexpectedly invoked reconciliation';
  exception when insufficient_privilege then
    null;
  end;
end;
$anon_refusal$;
reset role;

set local role authenticated;
do $authenticated_refusal$
begin
  begin
    perform public.connected_app_oauth_reconcile_expired_v1(1);
    raise exception 'authenticated unexpectedly invoked reconciliation';
  exception when insufficient_privilege then
    null;
  end;
end;
$authenticated_refusal$;
reset role;

set local role service_role;
do $behavior$
declare
  result jsonb;
begin
  begin
    perform public.connected_app_oauth_reconcile_expired_v1(0);
    raise exception 'invalid reconciliation limit was accepted';
  exception when sqlstate '22023' then
    null;
  end;

  result := public.connected_app_oauth_reconcile_expired_v1(1);
  if result <> '{"expired_flows":1,"expired_provisionals":1}'::jsonb
     or (select pg_catalog.array_agg(key order by key)
         from pg_catalog.jsonb_object_keys(result) as key)
       <> array['expired_flows','expired_provisionals'] then
    raise exception 'first bounded reconciliation drifted: %', result;
  end if;

  result := public.connected_app_oauth_reconcile_expired_v1(1);
  if result <> '{"expired_flows":1,"expired_provisionals":1}'::jsonb then
    raise exception 'second bounded reconciliation drifted: %', result;
  end if;

  -- This models a caller that lost either successful response and invokes a
  -- later authenticated wake.  Database-owned tombstones/outbox rows make the
  -- replay content-free and exactly idempotent.
  result := public.connected_app_oauth_reconcile_expired_v1(100);
  if result <> '{"expired_flows":0,"expired_provisionals":0}'::jsonb
     or public.connected_app_oauth_reconcile_expired_v1(100) <> result then
    raise exception 'reconciliation replay was not exactly idempotent: %', result;
  end if;
end;
$behavior$;
reset role;

do $durability$
begin
  if exists (select 1 from connected_app_private.oauth_secret_custody)
     or exists (select 1 from connected_app_private.oauth_provisional_credentials)
     or (select pg_catalog.count(*)
         from connected_app_private.oauth_secret_tombstones
         where reason = 'expired') <> 2
     or (select pg_catalog.count(*)
         from connected_app_private.oauth_provisional_tombstones) <> 2 then
    raise exception 'expired OAuth custody was not durably retired';
  end if;

  if (select pg_catalog.count(*)
      from connected_app_private.provider_grant_cleanup_jobs
      where source_kind = 'provisional'
        and status = 'cleanup_pending'
        and encrypted_record is not null
        and owner_id is null and connection_id is null
        and owner_id_sha256 ~ '^[0-9a-f]{64}$'
        and connection_id_sha256 ~ '^[0-9a-f]{64}$') <> 2 then
    raise exception 'expired provisional grants did not enter durable cleanup';
  end if;

  if not exists (
       select 1
       from connected_app_private.provider_grant_cleanup_jobs
       where provider = 'google' and source_kind = 'provisional'
     ) or not exists (
       select 1
       from connected_app_private.provider_grant_cleanup_jobs
       where provider = 'microsoft' and source_kind = 'provisional'
     ) then
    raise exception 'provider cleanup semantics were not preserved';
  end if;
end;
$durability$;

rollback;

select 'CONNECTED_EXTERNAL_RECONCILIATION_WORKER_OK' as result;
