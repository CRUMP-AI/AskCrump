\set ON_ERROR_STOP on

-- The harness always supplies these values. Defaults are only for an explicit
-- local developer run against the disposable PostgreSQL 17 fixture.
\if :{?connected_test_host}
\else
\set connected_test_host 127.0.0.1
\endif
\if :{?connected_test_port}
\else
select pg_catalog.current_setting('port') as connected_test_port \gset
\endif
\if :{?connected_test_user}
\else
select pg_catalog.current_user as connected_test_user \gset
\endif
\if :{?connected_test_password}
\else
\set connected_test_password postgres
\endif
\if :{?connected_test_database}
\else
select pg_catalog.current_database() as connected_test_database \gset
\endif
select
  pg_catalog.set_config(
    'connected_operator_ci.host', :'connected_test_host', false
  ) as host,
  pg_catalog.set_config(
    'connected_operator_ci.port', :'connected_test_port', false
  ) as port,
  pg_catalog.set_config(
    'connected_operator_ci.user', :'connected_test_user', false
  ) as username,
  pg_catalog.set_config(
    'connected_operator_ci.password', :'connected_test_password', false
  ) as password,
  pg_catalog.set_config(
    'connected_operator_ci.database', :'connected_test_database', false
  ) as database
\gset connected_operator_ci_
\unset connected_operator_ci_host
\unset connected_operator_ci_port
\unset connected_operator_ci_username
\unset connected_operator_ci_password
\unset connected_operator_ci_database

do $connection_settings$
begin
  if pg_catalog.current_setting('connected_operator_ci.host')
       !~ '^[A-Za-z0-9.:-]+$'
     or pg_catalog.current_setting('connected_operator_ci.port')
       !~ '^[0-9]{1,5}$'
     or pg_catalog.current_setting('connected_operator_ci.port')::integer
       not between 1 and 65535
     or pg_catalog.current_setting('connected_operator_ci.user')
       !~ '^[A-Za-z_][A-Za-z0-9_$]*$'
     or pg_catalog.length(
       pg_catalog.current_setting('connected_operator_ci.password')
     ) > 512
     or pg_catalog.current_setting('connected_operator_ci.database')
       <> pg_catalog.current_database() then
    raise exception 'invalid connected operator test connection settings'
      using errcode = '22023';
  end if;
end;
$connection_settings$;

create extension if not exists dblink;

insert into public.users(id, created_at, registration_environment) values (
  '10000000-0000-4000-8000-000000006551',
  pg_catalog.clock_timestamp(), 'development'
);

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256, authorization_expires_at
) values (
  '20000000-0000-4000-8000-000000006551',
  '10000000-0000-4000-8000-000000006551',
  'google', 'mail', 'personal',
  '20000000-0000-4000-8000-000000006552', 1, 'active',
  repeat('1',64), array['mail.get'], repeat('2',64), repeat('3',64),
  repeat('4',64), '20000000-0000-4000-8000-000000006553', repeat('5',64),
  pg_catalog.clock_timestamp() + interval '2 hours'
);

do $fixtures$
declare reference_at timestamptz := pg_catalog.clock_timestamp();
begin
  insert into connected_app_private.oauth_secret_custody (
    flow_id, nonce_id, owner_id, connection_id, connection_incarnation_id,
    expected_base_revision, current_flow_nonce_sha256, session_binding_sha256,
    provider, resource, account_kind, actions, actions_sha256,
    requested_scopes, requested_scopes_sha256, state_sha256, pkce_challenge,
    redirect_uri, created_at, expires_at, flow_binding_sha256,
    secret_key_id, secret_wrapped_key_nonce, secret_wrapped_key_ciphertext,
    secret_nonce, secret_ciphertext, secret_record_binding_sha256
  ) values (
    '30000000-0000-4000-8000-000000006551',
    '30000000-0000-4000-8000-000000006552',
    '10000000-0000-4000-8000-000000006551',
    '20000000-0000-4000-8000-000000006551',
    '20000000-0000-4000-8000-000000006552', 1,
    repeat('6',64), repeat('7',64), 'google', 'mail', 'personal',
    array['mail.get'], repeat('8',64), array['scope-a'], repeat('9',64),
    repeat('a',64), repeat('R',43), 'https://www.askcrump.com/oauth/callback',
    reference_at - interval '2 minutes', reference_at - interval '1 minute',
    repeat('b',64), 'oauth-key', repeat('A',16), repeat('B',64),
    repeat('C',16), repeat('D',32), repeat('c',64)
  );

  insert into connected_app_private.oauth_provisional_credentials (
    provisional_id, owner_id, connection_id, connection_incarnation_id,
    flow_id, exchange_id, provider, account_kind, status,
    credential_handle_sha256, oauth_client_id_sha256,
    external_account_id_hash, granted_scopes, granted_scopes_sha256,
    exchange_binding_sha256, issued_at, expires_at, authority_binding_sha256,
    key_id, wrapped_key_nonce, wrapped_key_ciphertext, secret_nonce,
    secret_ciphertext, record_binding_sha256
  ) values (
    '40000000-0000-4000-8000-000000006551',
    '10000000-0000-4000-8000-000000006551',
    '20000000-0000-4000-8000-000000006551',
    '20000000-0000-4000-8000-000000006552',
    '40000000-0000-4000-8000-000000006552',
    '40000000-0000-4000-8000-000000006553',
    'google', 'personal', 'provisional', repeat('d',64), repeat('e',64),
    repeat('f',64), array['scope-a'], repeat('0',64), repeat('1',64),
    reference_at - interval '2 hours', reference_at - interval '1 hour',
    repeat('2',64), 'oauth-key', repeat('E',16), repeat('F',64),
    repeat('G',16), repeat('H',32), repeat('3',64)
  );
end;
$fixtures$;

do $race$
declare
  connection_text text := pg_catalog.format(
    'dbname=%L host=%L port=%s user=%L password=%L',
    pg_catalog.current_setting('connected_operator_ci.database'),
    pg_catalog.current_setting('connected_operator_ci.host'),
    pg_catalog.current_setting('connected_operator_ci.port'),
    pg_catalog.current_setting('connected_operator_ci.user'),
    pg_catalog.current_setting('connected_operator_ci.password')
  );
  blocked_result jsonb;
  winner_result jsonb;
begin
  perform public.dblink_connect('reconcile_owner', connection_text);
  perform public.dblink_connect('reconcile_other', connection_text);
  perform public.dblink_exec('reconcile_owner', 'begin');
  perform response
  from public.dblink(
    'reconcile_owner',
    $sql$select connected_app_private.owner_lock_v1(
      '10000000-0000-4000-8000-000000006551'
    )::text$sql$
  ) as remote(response text);

  if public.dblink_send_query(
       'reconcile_other',
       'select public.connected_app_oauth_reconcile_expired_v1(100)::text'
     ) <> 1 then
    raise exception 'second reconciliation worker did not start';
  end if;
  select response::jsonb into blocked_result
  from public.dblink_get_result('reconcile_other') as remote(response text);
  if blocked_result <> '{"expired_flows":0,"expired_provisionals":0}'::jsonb then
    raise exception 'owner-busy worker did not skip bounded work: %', blocked_result;
  end if;

  select response::jsonb into winner_result
  from public.dblink(
    'reconcile_owner',
    'select public.connected_app_oauth_reconcile_expired_v1(100)::text'
  ) as remote(response text);
  if winner_result <> '{"expired_flows":1,"expired_provisionals":1}'::jsonb then
    raise exception 'owner-lock winner did not retire exact work: %', winner_result;
  end if;
  perform public.dblink_exec('reconcile_owner', 'commit');

  if public.connected_app_oauth_reconcile_expired_v1(100)
       <> '{"expired_flows":0,"expired_provisionals":0}'::jsonb then
    raise exception 'post-race replay found duplicate work';
  end if;
  perform public.dblink_disconnect('reconcile_owner');
  perform public.dblink_disconnect('reconcile_other');
end;
$race$;

select 'CONNECTED_EXTERNAL_RECONCILIATION_RACES_OK' as result;
