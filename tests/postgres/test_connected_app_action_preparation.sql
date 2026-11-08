\set ON_ERROR_STOP on

-- Disposable PostgreSQL 17 behavior gate.  The base control-plane migration
-- must already be applied to this database.
insert into public.users(id) values
  ('80000000-0000-4000-8000-000000000001'),
  ('80000000-0000-4000-8000-000000000002');

insert into public.sessions(id, user_id, token_hash, expires_at, revoked_at) values
(
  '8a000000-0000-4000-8000-000000000001',
  '80000000-0000-4000-8000-000000000001', repeat('1', 64),
  pg_catalog.clock_timestamp() + interval '2 hours', null
),
(
  '8a000000-0000-4000-8000-000000000002',
  '80000000-0000-4000-8000-000000000002', repeat('2', 64),
  pg_catalog.clock_timestamp() + interval '2 hours', null
),
(
  '8a000000-0000-4000-8000-000000000003',
  '80000000-0000-4000-8000-000000000001', repeat('3', 64),
  pg_catalog.clock_timestamp() - interval '1 minute', null
),
(
  '8a000000-0000-4000-8000-000000000004',
  '80000000-0000-4000-8000-000000000001', repeat('4', 64),
  pg_catalog.clock_timestamp() + interval '2 hours', pg_catalog.clock_timestamp()
);

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256, authorization_expires_at,
  revoked_at
) values
(
  '81000000-0000-4000-8000-000000000001',
  '80000000-0000-4000-8000-000000000001',
  'google', 'mail', 'personal',
  '81000000-0000-4000-8000-000000000002',
  7, 'active', repeat('a', 64), array['mail.get', 'mail.send'],
  repeat('b', 64), repeat('c', 64), repeat('d', 64),
  '81000000-0000-4000-8000-000000000003', repeat('e', 64),
  pg_catalog.clock_timestamp() + interval '2 hours', null
),
(
  '81000000-0000-4000-8000-000000000004',
  '80000000-0000-4000-8000-000000000001',
  'google', 'mail', 'personal',
  '81000000-0000-4000-8000-000000000005',
  7, 'active', repeat('a', 64), array['mail.get'],
  repeat('b', 64), repeat('c', 64), repeat('f', 64),
  '81000000-0000-4000-8000-000000000006', repeat('e', 64),
  pg_catalog.clock_timestamp() - interval '1 minute', null
),
(
  '81000000-0000-4000-8000-000000000007',
  '80000000-0000-4000-8000-000000000001',
  'google', 'mail', 'personal',
  '81000000-0000-4000-8000-000000000008',
  8, 'revoked', null, null, null, null, null, null, null, null,
  pg_catalog.clock_timestamp()
);

set role service_role;

do $test$
declare
  owner_id constant uuid := '80000000-0000-4000-8000-000000000001';
  other_owner constant uuid := '80000000-0000-4000-8000-000000000002';
  connection_id constant uuid := '81000000-0000-4000-8000-000000000001';
  expired_connection constant uuid := '81000000-0000-4000-8000-000000000004';
  revoked_connection constant uuid := '81000000-0000-4000-8000-000000000007';
  requested_at timestamptz := pg_catalog.clock_timestamp();
  expires_at timestamptz := requested_at + interval '10 minutes';
  read_result jsonb;
  write_result jsonb;
begin
  begin
    perform 1 from connected_app_private.action_preparations limit 1;
    raise exception 'service_role unexpectedly read the private preparation table';
  exception when insufficient_privilege then
    null;
  end;

  read_result := public.connected_app_operator_prepare_action_v1(
    '82000000-0000-4000-8000-000000000001', owner_id,
    '8a000000-0000-4000-8000-000000000001',
    repeat('1', 64), repeat('2', 64),
    '83000000-0000-4000-8000-000000000001',
    '84000000-0000-4000-8000-000000000001',
    '85000000-0000-4000-8000-000000000001',
    '86000000-0000-4000-8000-000000000001',
    connection_id, 'google', 'mail', 'mail.get', 7,
    repeat('a', 64), repeat('b', 64), repeat('c', 64), 3,
    '87000000-0000-4000-8000-000000000001',
    repeat('3', 64), repeat('4', 64), null,
    'connected-app-policy-v1', null, null, null, null, null,
    requested_at, expires_at
  );
  if read_result->>'status' <> 'ready'
     or read_result->>'approval_id' is not null
     or read_result->>'grant_actions_sha256'
        <> 'cf3c5f14bfb4fdaf65b7be317e91db19e678d58f1ac1e114defa9af82f7f40ac'
     or read_result ? 'target_binding_sha256'
     or read_result ? 'content' then
    raise exception 'read preparation projection is invalid';
  end if;
  if public.connected_app_operator_prepare_action_v1(
    '82000000-0000-4000-8000-000000000001', owner_id,
    '8a000000-0000-4000-8000-000000000001',
    repeat('1', 64), repeat('2', 64),
    '83000000-0000-4000-8000-000000000001',
    '84000000-0000-4000-8000-000000000001',
    '85000000-0000-4000-8000-000000000001',
    '86000000-0000-4000-8000-000000000001',
    connection_id, 'google', 'mail', 'mail.get', 7,
    repeat('a', 64), repeat('b', 64), repeat('c', 64), 3,
    '87000000-0000-4000-8000-000000000001',
    repeat('3', 64), repeat('4', 64), null,
    'connected-app-policy-v1', null, null, null, null, null,
    requested_at, expires_at
  ) is distinct from read_result then
    raise exception 'exact read preparation replay failed';
  end if;
  if public.connected_app_operator_read_action_preparation_v1(
       owner_id, '82000000-0000-4000-8000-000000000001'
     ) is distinct from read_result
     or public.connected_app_operator_read_action_preparation_v1(
       other_owner, '82000000-0000-4000-8000-000000000001'
     ) is not null then
    raise exception 'read preparation response-loss readback or isolation failed';
  end if;

  begin
    perform public.connected_app_operator_prepare_action_v1(
      '82000000-0000-4000-8000-000000000001', owner_id,
      '8a000000-0000-4000-8000-000000000001',
      repeat('1', 64), repeat('2', 64),
      '83000000-0000-4000-8000-000000000001',
      '84000000-0000-4000-8000-000000000001',
      '85000000-0000-4000-8000-000000000001',
      '86000000-0000-4000-8000-000000000001',
      connection_id, 'google', 'mail', 'mail.get', 7,
      repeat('a', 64), repeat('b', 64), repeat('c', 64), 3,
      '87000000-0000-4000-8000-000000000001',
      repeat('3', 64), repeat('9', 64), null,
      'connected-app-policy-v1', null, null, null, null, null,
      requested_at, expires_at
    );
    raise exception 'drifted preparation replay unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;

  write_result := public.connected_app_operator_prepare_action_v1(
    '82000000-0000-4000-8000-000000000002', owner_id,
    '8a000000-0000-4000-8000-000000000001',
    repeat('1', 64), repeat('5', 64),
    '83000000-0000-4000-8000-000000000002',
    '84000000-0000-4000-8000-000000000002',
    '85000000-0000-4000-8000-000000000002',
    '86000000-0000-4000-8000-000000000002',
    connection_id, 'google', 'mail', 'mail.send', 7,
    repeat('a', 64), repeat('b', 64), repeat('c', 64), 4,
    '87000000-0000-4000-8000-000000000002',
    repeat('6', 64), repeat('7', 64), null,
    'connected-app-policy-v1',
    '88000000-0000-4000-8000-000000000001', repeat('8', 64),
    '89000000-0000-4000-8000-000000000001', repeat('9', 64),
    repeat('0', 64), requested_at, expires_at
  );
  if write_result->>'status' <> 'pending_approval'
     or write_result->>'approval_class' <> 'external_communication'
     or write_result->>'approval_id'
        <> '88000000-0000-4000-8000-000000000001'
     or write_result->>'preview_payload_id'
        <> '89000000-0000-4000-8000-000000000001' then
    raise exception 'write preparation review projection failed';
  end if;

  -- Fresh sibling requests cannot reuse any prepared action identity.
  begin
    perform public.connected_app_operator_prepare_action_v1(
      '82000000-0000-4000-8000-000000000003', owner_id,
      '8a000000-0000-4000-8000-000000000001',
      repeat('1', 64), repeat('a', 64),
      '83000000-0000-4000-8000-000000000003',
      '84000000-0000-4000-8000-000000000001',
      '85000000-0000-4000-8000-000000000003',
      '86000000-0000-4000-8000-000000000003',
      connection_id, 'google', 'mail', 'mail.get', 7,
      repeat('a', 64), repeat('b', 64), repeat('c', 64), 1,
      '87000000-0000-4000-8000-000000000003',
      repeat('b', 64), repeat('c', 64), null,
      'connected-app-policy-v1', null, null, null, null, null,
      requested_at, expires_at
    );
    raise exception 'sibling action identity reuse unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;

  -- Every current-authority component fails closed before a grant is created.
  begin
    perform public.connected_app_operator_prepare_action_v1(
      '82000000-0000-4000-8000-000000000004', owner_id,
      '8a000000-0000-4000-8000-000000000001',
      repeat('1', 64), repeat('d', 64),
      '83000000-0000-4000-8000-000000000004',
      '84000000-0000-4000-8000-000000000004',
      '85000000-0000-4000-8000-000000000004',
      '86000000-0000-4000-8000-000000000004',
      connection_id, 'google', 'mail', 'mail.get', 6,
      repeat('a', 64), repeat('b', 64), repeat('c', 64), 1,
      '87000000-0000-4000-8000-000000000004',
      repeat('d', 64), repeat('e', 64), null,
      'connected-app-policy-v1', null, null, null, null, null,
      requested_at, expires_at
    );
    raise exception 'stale authorization revision unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
  begin
    perform public.connected_app_operator_prepare_action_v1(
      '82000000-0000-4000-8000-000000000005', owner_id,
      '8a000000-0000-4000-8000-000000000001',
      repeat('1', 64), repeat('e', 64),
      '83000000-0000-4000-8000-000000000005',
      '84000000-0000-4000-8000-000000000005',
      '85000000-0000-4000-8000-000000000005',
      '86000000-0000-4000-8000-000000000005',
      connection_id, 'google', 'mail', 'mail.get', 7,
      repeat('a', 64), repeat('b', 64), repeat('f', 64), 1,
      '87000000-0000-4000-8000-000000000005',
      repeat('d', 64), repeat('e', 64), null,
      'connected-app-policy-v1', null, null, null, null, null,
      requested_at, expires_at
    );
    raise exception 'stale scope snapshot unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
  begin
    perform public.connected_app_operator_prepare_action_v1(
      '82000000-0000-4000-8000-000000000006', owner_id,
      '8a000000-0000-4000-8000-000000000001',
      repeat('1', 64), repeat('f', 64),
      '83000000-0000-4000-8000-000000000006',
      '84000000-0000-4000-8000-000000000006',
      '85000000-0000-4000-8000-000000000006',
      '86000000-0000-4000-8000-000000000006',
      expired_connection, 'google', 'mail', 'mail.get', 7,
      repeat('a', 64), repeat('b', 64), repeat('c', 64), 1,
      '87000000-0000-4000-8000-000000000006',
      repeat('d', 64), repeat('e', 64), null,
      'connected-app-policy-v1', null, null, null, null, null,
      requested_at, expires_at
    );
    raise exception 'expired connection unexpectedly prepared an action';
  exception when sqlstate '55000' then
    null;
  end;
  begin
    perform public.connected_app_operator_prepare_action_v1(
      '82000000-0000-4000-8000-000000000007', owner_id,
      '8a000000-0000-4000-8000-000000000001',
      repeat('1', 64), repeat('0', 64),
      '83000000-0000-4000-8000-000000000007',
      '84000000-0000-4000-8000-000000000007',
      '85000000-0000-4000-8000-000000000007',
      '86000000-0000-4000-8000-000000000007',
      revoked_connection, 'google', 'mail', 'mail.get', 8,
      repeat('a', 64), repeat('b', 64), repeat('c', 64), 1,
      '87000000-0000-4000-8000-000000000007',
      repeat('d', 64), repeat('e', 64), null,
      'connected-app-policy-v1', null, null, null, null, null,
      requested_at, expires_at
    );
    raise exception 'revoked connection unexpectedly prepared an action';
  exception when sqlstate '55000' then
    null;
  end;
  begin
    perform public.connected_app_operator_prepare_action_v1(
      '82000000-0000-4000-8000-000000000008', other_owner,
      '8a000000-0000-4000-8000-000000000002',
      repeat('1', 64), repeat('0', 64),
      '83000000-0000-4000-8000-000000000008',
      '84000000-0000-4000-8000-000000000008',
      '85000000-0000-4000-8000-000000000008',
      '86000000-0000-4000-8000-000000000008',
      connection_id, 'google', 'mail', 'mail.get', 7,
      repeat('a', 64), repeat('b', 64), repeat('c', 64), 1,
      '87000000-0000-4000-8000-000000000008',
      repeat('d', 64), repeat('e', 64), null,
      'connected-app-policy-v1', null, null, null, null, null,
      requested_at, expires_at
    );
    raise exception 'cross-owner preparation unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
  begin
    perform public.connected_app_operator_prepare_action_v1(
      '82000000-0000-4000-8000-000000000009', owner_id,
      '8a000000-0000-4000-8000-000000000003',
      repeat('1', 64), repeat('0', 64),
      '83000000-0000-4000-8000-000000000009',
      '84000000-0000-4000-8000-000000000009',
      '85000000-0000-4000-8000-000000000009',
      '86000000-0000-4000-8000-000000000009',
      connection_id, 'google', 'mail', 'mail.get', 7,
      repeat('a', 64), repeat('b', 64), repeat('c', 64), 1,
      '87000000-0000-4000-8000-000000000009',
      repeat('d', 64), repeat('e', 64), null,
      'connected-app-policy-v1', null, null, null, null, null,
      requested_at, expires_at
    );
    raise exception 'expired session unexpectedly prepared an action';
  exception when sqlstate '55000' then
    null;
  end;
  begin
    perform public.connected_app_operator_prepare_action_v1(
      '82000000-0000-4000-8000-00000000000a', owner_id,
      '8a000000-0000-4000-8000-000000000004',
      repeat('1', 64), repeat('0', 64),
      '83000000-0000-4000-8000-00000000000a',
      '84000000-0000-4000-8000-00000000000a',
      '85000000-0000-4000-8000-00000000000a',
      '86000000-0000-4000-8000-00000000000a',
      connection_id, 'google', 'mail', 'mail.get', 7,
      repeat('a', 64), repeat('b', 64), repeat('c', 64), 1,
      '87000000-0000-4000-8000-00000000000a',
      repeat('d', 64), repeat('e', 64), null,
      'connected-app-policy-v1', null, null, null, null, null,
      requested_at, expires_at
    );
    raise exception 'revoked session unexpectedly prepared an action';
  exception when sqlstate '55000' then
    null;
  end;
end;
$test$;

reset role;

do $verify$
begin
  if (select pg_catalog.count(*) from connected_app_private.action_preparations) <> 2
     or (select pg_catalog.count(*) from connected_app_private.task_grants) <> 2
     or (select pg_catalog.count(*) from connected_app_private.approval_reviews) <> 1
     or (select pg_catalog.count(*) from connected_app_private.action_ledger) <> 0
     or exists (
       select 1 from connected_app_private.action_preparations
       where (status = 'ready' and approval_id is not null)
          or (status = 'pending_approval' and approval_id is null)
     ) then
    raise exception 'action preparation atomic postconditions failed';
  end if;
end;
$verify$;
