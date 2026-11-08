\set ON_ERROR_STOP on

begin;

insert into public.users(id, created_at, registration_environment) values (
  '80000000-0000-4000-8000-000000000001',
  pg_catalog.clock_timestamp(),
  'development'
);

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256, authorization_expires_at
) values (
  '80000000-0000-4000-8000-000000000002',
  '80000000-0000-4000-8000-000000000001',
  'google', 'mail', 'personal',
  '80000000-0000-4000-8000-000000000003', 1, 'active',
  repeat('a', 64), array['mail.get'], repeat('b', 64), repeat('c', 64),
  repeat('d', 64), '80000000-0000-4000-8000-000000000004',
  repeat('e', 64), pg_catalog.clock_timestamp() + interval '1 day'
);

insert into connected_app_private.task_grants (
  grant_id, owner_id, task_id, turn_id, connection_id, provider, resource,
  authorization_revision, authorization_snapshot_sha256, actions,
  actions_sha256, task_state_revision, expires_at
) values (
  '80000000-0000-4000-8000-000000000005',
  '80000000-0000-4000-8000-000000000001',
  '80000000-0000-4000-8000-000000000006',
  '80000000-0000-4000-8000-000000000007',
  '80000000-0000-4000-8000-000000000002',
  'google', 'mail', 1, repeat('a', 64), array['mail.get'], repeat('b', 64),
  1, pg_catalog.clock_timestamp() + interval '1 day'
);

do $fixture$
declare
  observed timestamptz := pg_catalog.clock_timestamp() - interval '1 minute';
begin
  insert into connected_app_private.action_ledger (
    operation_id, action_id, owner_id, task_id, turn_id, connection_id,
    grant_id, provider, resource, action, authorization_revision,
    authorization_snapshot_sha256, granted_actions_sha256,
    granted_scopes_sha256, parameters_sha256, resource_version_sha256,
    authority_sha256, idempotency_key_sha256, task_state_revision,
    status, mutates_external_state, approval_class, claim_request_id,
    claim_id, fencing_token, lease_expires_at, execution_deadline,
    access_phase, read_use_nonce, read_credential_expires_at,
    read_consumed_at, access_started_at, terminal_outcome,
    terminal_binding_sha256, observed_at, terminal_at,
    invocation_binding_sha256, terminal_resource_version_sha256
  ) values (
    '80000000-0000-4000-8000-000000000008',
    '80000000-0000-4000-8000-000000000008',
    '80000000-0000-4000-8000-000000000001',
    '80000000-0000-4000-8000-000000000006',
    '80000000-0000-4000-8000-000000000007',
    '80000000-0000-4000-8000-000000000002',
    '80000000-0000-4000-8000-000000000005',
    'google', 'mail', 'mail.get', 1, repeat('a', 64), repeat('b', 64),
    repeat('c', 64), repeat('1', 64), null, repeat('2', 64), repeat('3', 64),
    1, 'terminal', false, 'none',
    '80000000-0000-4000-8000-000000000009',
    '80000000-0000-4000-8000-00000000000a', 7,
    pg_catalog.clock_timestamp() + interval '1 minute',
    pg_catalog.clock_timestamp() + interval '5 minutes',
    'read', '80000000-0000-4000-8000-00000000000b',
    pg_catalog.clock_timestamp() + interval '1 minute',
    observed - interval '2 seconds', observed - interval '4 seconds',
    'read', repeat('4', 64), observed, observed + interval '1 second',
    repeat('4', 64), repeat('9', 64)
  );

  perform public.connected_app_payload_put_v1(
    '80000000-0000-5000-8000-00000000000c',
    '80000000-0000-4000-8000-000000000001',
    '80000000-0000-4000-8000-000000000002',
    '80000000-0000-4000-8000-000000000008',
    'google', 'mail.get', 'commit-v1', repeat('5', 64),
    observed, observed + interval '7 days', repeat('7', 64), repeat('6', 64),
    'wrap-v1', repeat('A', 16), repeat('B', 64), repeat('C', 16),
    repeat('D', 32), repeat('8', 64)
  );

  insert into connected_app_private.read_results (
    completion_id, operation_id, action_id, owner_id, connection_id,
    provider, resource, action, result_payload_id,
    result_commitment_key_id, result_payload_sha256,
    result_reference_binding_sha256, terminal_binding_sha256,
    authority_sha256, idempotency_key_sha256, claim_id, fencing_token,
    read_use_nonce, observed_at, resource_version_sha256, completed_at
  ) values (
    '80000000-0000-5000-8000-00000000000d',
    '80000000-0000-4000-8000-000000000008',
    '80000000-0000-4000-8000-000000000008',
    '80000000-0000-4000-8000-000000000001',
    '80000000-0000-4000-8000-000000000002',
    'google', 'mail', 'mail.get',
    '80000000-0000-5000-8000-00000000000c',
    'commit-v1', repeat('5', 64), repeat('6', 64), repeat('4', 64),
    repeat('2', 64), repeat('3', 64),
    '80000000-0000-4000-8000-00000000000a', 7,
    '80000000-0000-4000-8000-00000000000b', observed, repeat('9', 64),
    observed + interval '1 second'
  );
end;
$fixture$;

set local role service_role;

do $behavior$
declare
  result jsonb;
begin
  result := public.connected_app_open_read_result_v1(
    '80000000-0000-4000-8000-000000000001',
    '80000000-0000-5000-8000-00000000000c'
  );
  if result is null
     or result->>'operation_id' <> '80000000-0000-4000-8000-000000000008'
     or result->>'result_payload_id' <> '80000000-0000-5000-8000-00000000000c'
     or result->>'terminal_binding_sha256' <> repeat('4', 64)
     or result->>'terminal_resource_version_sha256' <> repeat('9', 64)
     or result ?| array[
       'payload_ciphertext', 'payload_nonce', 'wrapped_key_ciphertext',
       'wrapped_key_nonce', 'body', 'subject', 'description'
     ] then
    raise exception 'owner read-result projection was not exact and content-free: %', result;
  end if;

  if public.connected_app_open_read_result_v1(
       '80000000-0000-4000-8000-00000000000e',
       '80000000-0000-5000-8000-00000000000c'
     ) is not null then
    raise exception 'cross-owner result lookup disclosed existence';
  end if;
end;
$behavior$;

reset role;

do $drift$
begin
  update connected_app_private.action_ledger
     set invocation_binding_sha256 = repeat('f', 64)
   where operation_id = '80000000-0000-4000-8000-000000000008';
  begin
    perform public.connected_app_open_read_result_v1(
      '80000000-0000-4000-8000-000000000001',
      '80000000-0000-5000-8000-00000000000c'
    );
    raise exception 'binding-drifted result was opened';
  exception when sqlstate '55000' then
    null;
  end;
end;
$drift$;

do $authority$
begin
  if pg_catalog.has_function_privilege(
       'anon', 'public.connected_app_open_read_result_v1(uuid,uuid)', 'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'authenticated', 'public.connected_app_open_read_result_v1(uuid,uuid)', 'EXECUTE'
     )
     or not pg_catalog.has_function_privilege(
       'service_role', 'public.connected_app_open_read_result_v1(uuid,uuid)', 'EXECUTE'
     ) then
    raise exception 'owner read-result authority surface drifted';
  end if;
end;
$authority$;

rollback;
