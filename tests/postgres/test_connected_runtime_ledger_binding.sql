\set ON_ERROR_STOP on

begin;

insert into public.users(id, created_at, registration_environment) values (
  '10000000-0000-4000-8000-000000000001',
  pg_catalog.clock_timestamp(),
  'development'
) on conflict (id) do nothing;

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256, authorization_expires_at
) values (
  '20000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000001',
  'google', 'mail', 'personal',
  '20000000-0000-4000-8000-000000000002',
  1, 'active', repeat('a', 64), array['mail.get', 'mail.send'],
  repeat('b', 64), repeat('c', 64), repeat('d', 64),
  '20000000-0000-4000-8000-000000000003', repeat('e', 64),
  pg_catalog.clock_timestamp() + interval '2 hours'
);

insert into connected_app_private.task_grants (
  grant_id, owner_id, task_id, turn_id, connection_id,
  provider, resource, authorization_revision,
  authorization_snapshot_sha256, actions, actions_sha256,
  task_state_revision, expires_at
) values (
  '30000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000001',
  '30000000-0000-4000-8000-000000000002',
  '30000000-0000-4000-8000-000000000003',
  '20000000-0000-4000-8000-000000000001',
  'google', 'mail', 1, repeat('a', 64),
  array['mail.get', 'mail.send'], repeat('b', 64), 1,
  pg_catalog.clock_timestamp() + interval '1 hour'
);

insert into connected_app_private.approvals (
  approval_id, action_id, owner_id, task_id, turn_id, connection_id,
  provider, resource, action, authorization_revision,
  authorization_snapshot_sha256, approval_class, parameters_sha256,
  resource_version_sha256, approval_binding_sha256,
  approved_at, expires_at, consumed_at, consumed_by_operation_id
) values (
  '40000000-0000-4000-8000-000000000001',
  '50000000-0000-4000-8000-000000000002',
  '10000000-0000-4000-8000-000000000001',
  '30000000-0000-4000-8000-000000000002',
  '30000000-0000-4000-8000-000000000003',
  '20000000-0000-4000-8000-000000000001',
  'google', 'mail', 'mail.send', 1, repeat('a', 64),
  'external_communication', repeat('4', 64), null, repeat('5', 64),
  pg_catalog.clock_timestamp() - interval '1 minute',
  pg_catalog.clock_timestamp() + interval '10 minutes',
  pg_catalog.clock_timestamp(),
  '50000000-0000-4000-8000-000000000002'
);

set local role service_role;

do $test$
declare
  owner_id constant uuid := '10000000-0000-4000-8000-000000000001';
  connection_id constant uuid := '20000000-0000-4000-8000-000000000001';
  grant_id constant uuid := '30000000-0000-4000-8000-000000000001';
  task_id constant uuid := '30000000-0000-4000-8000-000000000002';
  turn_id constant uuid := '30000000-0000-4000-8000-000000000003';
  read_operation constant uuid := '50000000-0000-4000-8000-000000000001';
  write_operation constant uuid := '50000000-0000-4000-8000-000000000002';
  approval_id constant uuid := '40000000-0000-4000-8000-000000000001';
  read_request constant uuid := '60000000-0000-4000-8000-000000000001';
  read_claim constant uuid := '60000000-0000-4000-8000-000000000002';
  read_nonce constant uuid := '60000000-0000-4000-8000-000000000003';
  expired_read_nonce constant uuid := '60000000-0000-4000-8000-000000000004';
  recovery_request constant uuid := '60000000-0000-4000-8000-000000000005';
  recovered_claim constant uuid := '60000000-0000-4000-8000-000000000006';
  write_request constant uuid := '70000000-0000-4000-8000-000000000001';
  write_claim constant uuid := '70000000-0000-4000-8000-000000000002';
  preobserve_nonce constant uuid := '70000000-0000-4000-8000-000000000003';
  effect_nonce constant uuid := '70000000-0000-4000-8000-000000000004';
  read_deadline timestamptz := pg_catalog.clock_timestamp() + interval '5 minutes';
  recovered_deadline timestamptz :=
    pg_catalog.clock_timestamp() + interval '6 minutes';
  write_deadline timestamptz := pg_catalog.clock_timestamp() + interval '5 minutes';
  read_expiry timestamptz := pg_catalog.clock_timestamp() + interval '80 seconds';
  preobserve_expiry timestamptz := pg_catalog.clock_timestamp() + interval '80 seconds';
  effect_expiry timestamptz := pg_catalog.clock_timestamp() + interval '70 seconds';
  observed_at timestamptz := pg_catalog.clock_timestamp();
  result jsonb;
  first_terminal jsonb;
  first_recovery jsonb;
begin
  result := public.connected_app_claim_action_v2(
    read_operation, read_operation, owner_id, task_id, turn_id,
    connection_id, grant_id, 'google', 'mail', 'mail.get', 1,
    repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('1', 64),
    null, repeat('2', 64), repeat('3', 64), repeat('4', 64), 1,
    read_request, read_claim, 120, read_deadline
  );
  if result->>'invocation_binding_sha256' <> repeat('4', 64)
     or result->>'claim_id' <> read_claim::text then
    raise exception 'v2 read claim did not persist exact invocation binding';
  end if;
  if public.connected_app_claim_action_v2(
    read_operation, read_operation, owner_id, task_id, turn_id,
    connection_id, grant_id, 'google', 'mail', 'mail.get', 1,
    repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('1', 64),
    null, repeat('2', 64), repeat('3', 64), repeat('4', 64), 1,
    read_request, read_claim, 120, read_deadline
  ) is distinct from result then
    raise exception 'v2 claim exact response-loss replay drifted';
  end if;
  begin
    perform public.connected_app_claim_action_v2(
      read_operation, read_operation, owner_id, task_id, turn_id,
      connection_id, grant_id, 'google', 'mail', 'mail.get', 1,
      repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('1', 64),
      null, repeat('2', 64), repeat('3', 64), repeat('9', 64), 1,
      read_request, read_claim, 120, read_deadline
    );
    raise exception 'v2 claim accepted invocation-binding drift';
  exception when sqlstate '55000' then
    null;
  end;
  if public.connected_app_read_action_v2(
       owner_id, read_operation, repeat('3', 64), repeat('4', 64)
     )->>'claim_id' <> read_claim::text then
    raise exception 'v2 exact readback failed';
  end if;
  begin
    perform public.connected_app_read_action_v2(
      owner_id, read_operation, repeat('3', 64), repeat('9', 64)
    );
    raise exception 'v2 readback accepted invocation-binding drift';
  exception when sqlstate '55000' then
    null;
  end;

  read_expiry := pg_catalog.clock_timestamp() + interval '250 milliseconds';
  result := public.connected_app_begin_access_v1(
    read_operation, owner_id, read_claim,
    (result->>'fencing_token')::bigint, repeat('b', 64),
    'read', expired_read_nonce, read_expiry
  );
  perform pg_catalog.pg_sleep(0.35);
  read_expiry := pg_catalog.clock_timestamp() + interval '80 seconds';
  begin
    perform public.connected_app_recover_access_v2(
      read_operation, owner_id,
      '60000000-0000-4000-8000-000000000099', recovery_request,
      recovered_claim, 120, grant_id, 1, repeat('a', 64), repeat('b', 64),
      repeat('c', 64), repeat('f', 64), 1, repeat('4', 64), 'read',
      read_nonce, read_expiry, recovered_deadline
    );
    raise exception 'v2 access recovery accepted the wrong expired claim';
  exception when sqlstate '55000' then
    null;
  end;
  first_recovery := public.connected_app_recover_access_v2(
    read_operation, owner_id, read_claim, recovery_request, recovered_claim,
    120, grant_id, 1, repeat('a', 64), repeat('b', 64), repeat('c', 64),
    repeat('f', 64), 1, repeat('4', 64), 'read', read_nonce, read_expiry,
    recovered_deadline
  );
  if first_recovery->>'claim_id' <> recovered_claim::text
     or first_recovery->>'claim_request_id' <> recovery_request::text
     or first_recovery->>'authority_sha256' <> repeat('f', 64)
     or (first_recovery->>'execution_deadline')::timestamptz <>
        recovered_deadline
     or first_recovery->>'read_use_nonce' <> read_nonce::text then
    raise exception 'v2 access recovery did not bind fresh authority exactly';
  end if;
  if public.connected_app_recover_access_v2(
    read_operation, owner_id, read_claim, recovery_request, recovered_claim,
    120, grant_id, 1, repeat('a', 64), repeat('b', 64), repeat('c', 64),
    repeat('f', 64), 1, repeat('4', 64), 'read', read_nonce, read_expiry,
    recovered_deadline
  ) is distinct from first_recovery then
    raise exception 'v2 access recovery response-loss replay drifted';
  end if;
  result := first_recovery;
  perform public.connected_app_consume_credential_lease_v1(
    read_operation, owner_id, connection_id, read_operation, 'mail.get',
    recovered_claim, (result->>'fencing_token')::bigint, 'read', read_nonce,
    read_expiry, 1, repeat('a', 64), repeat('b', 64), repeat('c', 64),
    repeat('f', 64), 1
  );
  observed_at := pg_catalog.clock_timestamp();
  first_terminal := public.connected_app_settle_action_v2(
    read_operation, recovered_claim, (result->>'fencing_token')::bigint,
    repeat('4', 64), read_nonce, null, null, false, 'read',
    repeat('6', 64), repeat('7', 64), null, null, observed_at
  );
  if first_terminal->>'terminal_resource_version_sha256' <> repeat('7', 64)
     or first_terminal->>'terminal_outcome' <> 'read' then
    raise exception 'v2 read settlement did not persist terminal version';
  end if;
  if public.connected_app_settle_action_v2(
    read_operation, recovered_claim, (result->>'fencing_token')::bigint,
    repeat('4', 64), read_nonce, null, null, false, 'read',
    repeat('6', 64), repeat('7', 64), null, null, observed_at
  ) is distinct from first_terminal then
    raise exception 'v2 read settlement exact response-loss replay drifted';
  end if;
  begin
    perform public.connected_app_settle_action_v2(
      read_operation, recovered_claim, (result->>'fencing_token')::bigint,
      repeat('4', 64), read_nonce, null, null, false, 'read',
      repeat('6', 64), repeat('8', 64), null, null, observed_at
    );
    raise exception 'v2 terminal replay accepted resource-version drift';
  exception when sqlstate '55000' then
    null;
  end;

  result := public.connected_app_claim_action_v2(
    write_operation, write_operation, owner_id, task_id, turn_id,
    connection_id, grant_id, 'google', 'mail', 'mail.send', 1,
    repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('4', 64),
    null, repeat('8', 64), repeat('9', 64), repeat('a', 64), 1,
    write_request, write_claim, 120, write_deadline
  );
  result := public.connected_app_begin_access_v1(
    write_operation, owner_id, write_claim,
    (result->>'fencing_token')::bigint, repeat('b', 64),
    'preobserve', preobserve_nonce, preobserve_expiry
  );
  perform public.connected_app_consume_credential_lease_v1(
    write_operation, owner_id, connection_id, write_operation, 'mail.send',
    write_claim, (result->>'fencing_token')::bigint, 'preobserve',
    preobserve_nonce, preobserve_expiry, 1, repeat('a', 64), repeat('b', 64),
    repeat('c', 64), repeat('8', 64), 1
  );
  result := public.connected_app_begin_effect_v1(
    write_operation, owner_id, write_claim,
    (result->>'fencing_token')::bigint, repeat('b', 64), approval_id,
    effect_nonce, effect_expiry
  );
  perform public.connected_app_consume_credential_lease_v1(
    write_operation, owner_id, connection_id, write_operation, 'mail.send',
    write_claim, (result->>'fencing_token')::bigint, 'effect', effect_nonce,
    effect_expiry, 1, repeat('a', 64), repeat('b', 64), repeat('c', 64),
    repeat('8', 64), 1
  );
  first_terminal := public.connected_app_settle_action_v2(
    write_operation, write_claim, (result->>'fencing_token')::bigint,
    repeat('a', 64), null, effect_nonce, null, false, 'succeeded',
    repeat('b', 64), repeat('c', 64), repeat('d', 64), repeat('e', 64),
    pg_catalog.clock_timestamp()
  );
  if first_terminal->>'terminal_outcome' <> 'succeeded'
     or first_terminal->>'terminal_resource_version_sha256' <> repeat('c', 64)
     or first_terminal->>'preobserve_use_nonce' <> preobserve_nonce::text then
    raise exception 'v2 write settlement did not derive durable preobserve receipt';
  end if;

  if pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_claim_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,bigint,uuid,uuid,integer,timestamp with time zone)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'service_role', 'public.connected_app_read_action_v1(uuid,uuid,text)', 'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_recover_access_v1(uuid,uuid,uuid,uuid,integer,text,uuid,timestamp with time zone)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_settle_action_v1(uuid,uuid,uuid,uuid,uuid,boolean,text,text,text,text,timestamp with time zone)',
       'EXECUTE'
     ) then
    raise exception 'legacy ledger RPC remained reachable after v2 composition';
  end if;
end;
$test$;

rollback;
