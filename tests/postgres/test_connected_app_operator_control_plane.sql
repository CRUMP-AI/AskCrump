\set ON_ERROR_STOP on

-- This behavior gate runs only against a disposable PostgreSQL 17 database
-- after 20261107190000_connected_app_control_plane.sql has applied.
insert into public.users(id) values
  ('00000000-0000-4000-8000-000000000001'),
  ('00000000-0000-4000-8000-000000000002');

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256,
  authorization_expires_at
) values (
  '10000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000001',
  'google', 'mail', 'personal',
  '10000000-0000-4000-8000-000000000002',
  2, 'active', repeat('a', 64), array['mail.get', 'mail.send'],
  repeat('b', 64), repeat('c', 64), repeat('d', 64),
  '10000000-0000-4000-8000-000000000003', repeat('e', 64),
  pg_catalog.clock_timestamp() + interval '2 hours'
);

insert into connected_app_private.task_grants (
  grant_id, owner_id, task_id, turn_id, connection_id,
  provider, resource, authorization_revision,
  authorization_snapshot_sha256, actions, actions_sha256,
  task_state_revision, expires_at
) values (
  '20000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000002',
  '20000000-0000-4000-8000-000000000003',
  '10000000-0000-4000-8000-000000000001',
  'google', 'mail', 2, repeat('a', 64), array['mail.get'],
  repeat('b', 64), 1, pg_catalog.clock_timestamp() + interval '1 hour'
);

-- A logical action may have more than one durable operation attempt.  The
-- public scalar projection must deterministically return only the newest.
insert into connected_app_private.action_ledger (
  operation_id, action_id, owner_id, task_id, turn_id, connection_id,
  grant_id, provider, resource, action, authorization_revision,
  authorization_snapshot_sha256, granted_actions_sha256,
  granted_scopes_sha256, parameters_sha256, authority_sha256,
  idempotency_key_sha256, task_state_revision, mutates_external_state,
  approval_class, claim_request_id, claim_id, lease_expires_at,
  execution_deadline, created_at, updated_at
) values
(
  '30000000-0000-4000-8000-000000000001',
  '30000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000002',
  '20000000-0000-4000-8000-000000000003',
  '10000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000001',
  'google', 'mail', 'mail.get', 2, repeat('a', 64), repeat('b', 64),
  repeat('c', 64), repeat('0', 64), repeat('f', 64), repeat('1', 64),
  1, false, 'none',
  '30000000-0000-4000-8000-000000000003',
  '30000000-0000-4000-8000-000000000004',
  pg_catalog.clock_timestamp() + interval '2 minutes',
  pg_catalog.clock_timestamp() + interval '5 minutes',
  pg_catalog.clock_timestamp() - interval '2 seconds',
  pg_catalog.clock_timestamp() - interval '2 seconds'
),
(
  '30000000-0000-4000-8000-000000000005',
  '30000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000002',
  '20000000-0000-4000-8000-000000000003',
  '10000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000001',
  'google', 'mail', 'mail.get', 2, repeat('a', 64), repeat('b', 64),
  repeat('c', 64), repeat('2', 64), repeat('f', 64), repeat('3', 64),
  1, false, 'none',
  '30000000-0000-4000-8000-000000000006',
  '30000000-0000-4000-8000-000000000007',
  pg_catalog.clock_timestamp() + interval '2 minutes',
  pg_catalog.clock_timestamp() + interval '5 minutes',
  pg_catalog.clock_timestamp() - interval '1 second',
  pg_catalog.clock_timestamp() - interval '1 second'
);

set role service_role;

do $test$
declare
  owner_id constant uuid := '00000000-0000-4000-8000-000000000001';
  other_owner constant uuid := '00000000-0000-4000-8000-000000000002';
  connection_id constant uuid := '10000000-0000-4000-8000-000000000001';
  schedule_id constant uuid := '40000000-0000-4000-8000-000000000001';
  schedule_request constant uuid := '40000000-0000-4000-8000-000000000002';
  pause_request constant uuid := '40000000-0000-4000-8000-000000000003';
  resume_request constant uuid := '40000000-0000-4000-8000-000000000004';
  disconnect_request constant uuid := '40000000-0000-4000-8000-000000000005';
  requested_at timestamptz := pg_catalog.clock_timestamp();
  result jsonb;
begin
  begin
    perform 1 from connected_app_private.connections limit 1;
    raise exception 'service_role unexpectedly read a private table';
  exception when insufficient_privilege then
    null;
  end;

  result := public.connected_app_operator_list_connections_v1(owner_id);
  if pg_catalog.jsonb_array_length(result) <> 1
     or result->0->>'connection_id' <> connection_id::text then
    raise exception 'owner connection list projection failed';
  end if;
  if public.connected_app_operator_list_connections_v1(other_owner) <> '[]'::jsonb
     or public.connected_app_operator_get_connection_authority_v1(
       other_owner, connection_id
     ) is not null then
    raise exception 'connection owner isolation failed';
  end if;

  result := public.connected_app_operator_get_action_v1(
    owner_id, '30000000-0000-4000-8000-000000000002'
  );
  if result->>'parameters_sha256' <> repeat('2', 64)
     or pg_catalog.jsonb_array_length(
       public.connected_app_operator_list_actions_v1(owner_id)
     ) <> 1 then
    raise exception 'singular newest action projection failed';
  end if;

  result := public.connected_app_operator_create_schedule_v1(
    schedule_request, schedule_id, owner_id, repeat('4', 64), repeat('5', 64),
    connection_id, '40000000-0000-4000-8000-000000000006',
    'google', 'mail', 'mail.send',
    '40000000-0000-4000-8000-000000000007', repeat('6', 64),
    'America/New_York', 3600, 1320, 420, true,
    requested_at, requested_at + interval '1 hour'
  );
  if result->>'status' <> 'active'
     or (result->>'task_state_revision')::bigint <> 1 then
    raise exception 'schedule creation failed';
  end if;
  if public.connected_app_operator_create_schedule_v1(
    schedule_request, schedule_id, owner_id, repeat('4', 64), repeat('5', 64),
    connection_id, '40000000-0000-4000-8000-000000000006',
    'google', 'mail', 'mail.send',
    '40000000-0000-4000-8000-000000000007', repeat('6', 64),
    'America/New_York', 3600, 1320, 420, true,
    requested_at, requested_at + interval '1 hour'
  ) is distinct from result then
    raise exception 'exact schedule-create replay failed';
  end if;
  begin
    perform public.connected_app_operator_create_schedule_v1(
      schedule_request, schedule_id, owner_id, repeat('4', 64), repeat('7', 64),
      connection_id, '40000000-0000-4000-8000-000000000006',
      'google', 'mail', 'mail.send',
      '40000000-0000-4000-8000-000000000007', repeat('6', 64),
      'America/New_York', 3600, 1320, 420, true,
      requested_at, requested_at + interval '1 hour'
    );
    raise exception 'drifted schedule-create replay unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
  if public.connected_app_operator_read_schedule_create_v1(
       owner_id, schedule_request
     )->>'schedule_id' <> schedule_id::text
     or public.connected_app_operator_read_schedule_create_v1(
       other_owner, schedule_request
     ) is not null then
    raise exception 'schedule-create response-loss readback failed';
  end if;

  result := public.connected_app_operator_transition_schedule_v1(
    pause_request, owner_id, repeat('4', 64), repeat('8', 64),
    schedule_id, 1, 'active', 'paused', requested_at
  );
  if result->>'status' <> 'paused' or result->'next_run_at' <> 'null'::jsonb
     or (result->>'task_state_revision')::bigint <> 2 then
    raise exception 'schedule pause failed';
  end if;
  if public.connected_app_operator_transition_schedule_v1(
    pause_request, owner_id, repeat('4', 64), repeat('8', 64),
    schedule_id, 1, 'active', 'paused', requested_at
  ) is distinct from result then
    raise exception 'exact schedule-transition replay failed';
  end if;
  result := public.connected_app_operator_transition_schedule_v1(
    resume_request, owner_id, repeat('4', 64), repeat('9', 64),
    schedule_id, 2, 'paused', 'active', requested_at
  );
  if result->>'status' <> 'active'
     or (result->>'task_state_revision')::bigint <> 3
     or result->'next_run_at' = 'null'::jsonb then
    raise exception 'schedule resume failed';
  end if;

  result := public.connected_app_operator_put_approval_review_v1(
    '50000000-0000-4000-8000-000000000001',
    '50000000-0000-4000-8000-000000000002', owner_id,
    '50000000-0000-4000-8000-000000000003',
    '50000000-0000-4000-8000-000000000004', connection_id,
    'google', 'mail', 'mail.send', 2, repeat('a', 64), repeat('c', 64),
    'connected-app-policy-v1', 1, 'external_communication',
    repeat('0', 64), repeat('1', 64), null, repeat('2', 64),
    '50000000-0000-4000-8000-000000000005',
    requested_at, requested_at + interval '5 minutes'
  );
  if result->>'status' <> 'pending'
     or pg_catalog.jsonb_array_length(
       public.connected_app_operator_list_approvals_v1(owner_id)
     ) <> 1
     or public.connected_app_operator_get_approval_v1(
       other_owner, '50000000-0000-4000-8000-000000000001'
     ) is not null then
    raise exception 'approval review projection or owner isolation failed';
  end if;
  result := public.connected_app_operator_decide_approval_v1(
    '50000000-0000-4000-8000-000000000006', owner_id, repeat('3', 64),
    '50000000-0000-4000-8000-000000000001',
    '50000000-0000-4000-8000-000000000002', connection_id,
    '50000000-0000-4000-8000-000000000003',
    '50000000-0000-4000-8000-000000000004',
    'google', 'mail', 'mail.send', 2, repeat('a', 64), repeat('c', 64),
    'connected-app-policy-v1', 1, repeat('0', 64), repeat('1', 64),
    null, repeat('2', 64), 'denied', requested_at
  );
  if result->>'status' <> 'denied'
     or public.connected_app_operator_read_approval_decision_v1(
       owner_id, '50000000-0000-4000-8000-000000000001',
       '50000000-0000-4000-8000-000000000006'
     )->>'status' <> 'denied' then
    raise exception 'approval denial/readback failed';
  end if;

  perform public.connected_app_operator_put_approval_review_v1(
    '50000000-0000-4000-8000-000000000007',
    '50000000-0000-4000-8000-000000000008', owner_id,
    '50000000-0000-4000-8000-000000000009',
    '50000000-0000-4000-8000-00000000000a', connection_id,
    'google', 'mail', 'mail.send', 2, repeat('a', 64), repeat('c', 64),
    'connected-app-policy-v1', 1, 'external_communication',
    repeat('4', 64), repeat('5', 64), null, repeat('6', 64),
    '50000000-0000-4000-8000-00000000000b',
    requested_at, requested_at + interval '5 minutes'
  );
  result := public.connected_app_operator_decide_approval_v1(
    '50000000-0000-4000-8000-00000000000c', owner_id, repeat('7', 64),
    '50000000-0000-4000-8000-000000000007',
    '50000000-0000-4000-8000-000000000008', connection_id,
    '50000000-0000-4000-8000-000000000009',
    '50000000-0000-4000-8000-00000000000a',
    'google', 'mail', 'mail.send', 2, repeat('a', 64), repeat('c', 64),
    'connected-app-policy-v1', 1, repeat('4', 64), repeat('5', 64),
    null, repeat('6', 64), 'approved', requested_at
  );
  if result->>'status' <> 'approved' then
    raise exception 'atomic approval creation failed';
  end if;

  result := public.connected_app_operator_disconnect_v1(
    disconnect_request, owner_id, repeat('4', 64), connection_id,
    '60000000-0000-4000-8000-000000000001', repeat('8', 64), requested_at
  );
  if result->>'authorization_state' <> 'revoked'
     or public.connected_app_operator_read_disconnect_v1(
       owner_id, connection_id, disconnect_request
     )->>'authorization_state' <> 'revoked'
     or public.connected_app_operator_read_disconnect_v1(
       other_owner, connection_id, disconnect_request
     ) is not null then
    raise exception 'atomic disconnect/readback failed';
  end if;
end;
$test$;

reset role;

-- A review and ledger sharing an action identity may never disagree on the
-- bound request/authority and then silently coalesce into a public result.
insert into connected_app_private.approval_reviews (
  approval_id, action_id, owner_id, task_id, turn_id, connection_id,
  provider, resource, action, authorization_revision,
  authorization_snapshot_sha256, granted_scopes_sha256, policy_version,
  action_revision, approval_class, approval_binding_sha256,
  parameters_sha256, preview_sha256, review_payload_ref, expires_at
) values (
  '70000000-0000-4000-8000-000000000001',
  '30000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000002',
  '20000000-0000-4000-8000-000000000003',
  '10000000-0000-4000-8000-000000000001',
  'google', 'mail', 'mail.send', 2, repeat('a', 64), repeat('c', 64),
  'connected-app-policy-v1', 1, 'external_communication', repeat('a', 64),
  repeat('b', 64), repeat('c', 64),
  '70000000-0000-4000-8000-000000000002',
  pg_catalog.clock_timestamp() + interval '5 minutes'
);

set role service_role;
do $drift$
begin
  begin
    perform public.connected_app_operator_get_action_v1(
      '00000000-0000-4000-8000-000000000001',
      '30000000-0000-4000-8000-000000000002'
    );
    raise exception 'drifted action projection unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
end;
$drift$;
reset role;
delete from connected_app_private.approval_reviews
where approval_id = '70000000-0000-4000-8000-000000000001';

do $verify$
begin
  if (select pg_catalog.count(*) from connected_app_private.operator_commands) <> 4
     or (select pg_catalog.count(*) from connected_app_private.approval_reviews) <> 2
     or (select pg_catalog.count(*) from connected_app_private.approvals) <> 1
     or (select pg_catalog.count(*) from connected_app_private.credential_cleanup_outbox) <> 1
     or (select pg_catalog.count(*) from connected_app_private.credential_ref_tombstones) <> 1
     or exists (
       select 1 from connected_app_private.credential_cleanup_outbox
       where cleanup_binding_sha256 <> repeat('8', 64)
          or credential_ref_sha256 <> repeat('e', 64)
          or cleanup_binding_sha256 = credential_ref_sha256
     )
     or exists (
       select 1 from connected_app_private.schedules
       where status <> 'cancelled' or next_run_at is not null
     )
     or exists (
       select 1 from connected_app_private.task_grants where revoked_at is null
     ) then
    raise exception 'operator control-plane atomic postconditions failed';
  end if;
end;
$verify$;
