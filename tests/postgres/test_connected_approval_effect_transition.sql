\set ON_ERROR_STOP on

begin;

insert into public.users(id,created_at,registration_environment) values (
  'a1000000-0000-4000-8000-000000000001',
  pg_catalog.clock_timestamp(),'development'
);
insert into connected_app_private.connections (
  id,owner_id,provider,resource,account_kind,connection_incarnation_id,
  authorization_revision,authorization_state,authorization_snapshot_sha256,
  granted_actions,granted_actions_sha256,granted_scopes_sha256,
  external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
  authorization_expires_at
) values (
  'a2000000-0000-4000-8000-000000000001',
  'a1000000-0000-4000-8000-000000000001',
  'google','mail','personal','a2000000-0000-4000-8000-000000000002',
  1,'active',repeat('a',64),array['mail.send'],repeat('b',64),
  repeat('c',64),repeat('d',64),
  'a2000000-0000-4000-8000-000000000003',repeat('e',64),
  pg_catalog.clock_timestamp()+interval '2 hours'
);
insert into connected_app_private.task_grants (
  grant_id,owner_id,task_id,turn_id,connection_id,provider,resource,
  authorization_revision,authorization_snapshot_sha256,actions,
  actions_sha256,task_state_revision,expires_at
) values (
  'a3000000-0000-4000-8000-000000000001',
  'a1000000-0000-4000-8000-000000000001',
  'a3000000-0000-4000-8000-000000000002',
  'a3000000-0000-4000-8000-000000000003',
  'a2000000-0000-4000-8000-000000000001',
  'google','mail',1,repeat('a',64),array['mail.send'],repeat('b',64),1,
  pg_catalog.clock_timestamp()+interval '1 hour'
);
insert into connected_app_private.approvals (
  approval_id,action_id,owner_id,task_id,turn_id,connection_id,
  provider,resource,action,authorization_revision,
  authorization_snapshot_sha256,approval_class,parameters_sha256,
  resource_version_sha256,approval_binding_sha256,approved_at,expires_at
) values
  (
    'a4000000-0000-4000-8000-000000000001',
    'a5000000-0000-4000-8000-000000000001',
    'a1000000-0000-4000-8000-000000000001',
    'a3000000-0000-4000-8000-000000000002',
    'a3000000-0000-4000-8000-000000000003',
    'a2000000-0000-4000-8000-000000000001',
    'google','mail','mail.send',1,repeat('a',64),
    'external_communication',repeat('4',64),null,repeat('5',64),
    pg_catalog.clock_timestamp()-interval '1 minute',
    pg_catalog.clock_timestamp()+interval '10 minutes'
  ),
  (
    'a4000000-0000-4000-8000-000000000002',
    'a5000000-0000-4000-8000-000000000002',
    'a1000000-0000-4000-8000-000000000001',
    'a3000000-0000-4000-8000-000000000002',
    'a3000000-0000-4000-8000-000000000003',
    'a2000000-0000-4000-8000-000000000001',
    'google','mail','mail.send',1,repeat('a',64),
    'external_communication',repeat('4',64),null,repeat('6',64),
    pg_catalog.clock_timestamp()-interval '1 minute',
    pg_catalog.clock_timestamp()+interval '10 minutes'
  ),
  (
    'a4000000-0000-4000-8000-000000000003',
    'a5000000-0000-4000-8000-000000000003',
    'a1000000-0000-4000-8000-000000000001',
    'a3000000-0000-4000-8000-000000000002',
    'a3000000-0000-4000-8000-000000000003',
    'a2000000-0000-4000-8000-000000000001',
    'google','mail','mail.send',1,repeat('a',64),
    'external_communication',repeat('4',64),null,repeat('7',64),
    pg_catalog.clock_timestamp()-interval '10 minutes',
    pg_catalog.clock_timestamp()-interval '1 second'
  );

set local role service_role;

-- The reviewed decision RPC remains the only application boundary that may
-- mint an approval.  The three lower-level primitives must not be directly
-- callable by service_role; the postgres-owned SECURITY DEFINER boundaries
-- below still invoke them internally.
do $primitive_authority$
begin
  begin
    perform public.connected_app_create_approval_v1(
      'af000000-0000-4000-8000-000000000001',
      'af000000-0000-4000-8000-000000000002',
      'a1000000-0000-4000-8000-000000000001',
      'a3000000-0000-4000-8000-000000000002',
      'a3000000-0000-4000-8000-000000000003',
      'a2000000-0000-4000-8000-000000000001',
      'google','mail','mail.send',1,repeat('a',64),
      'external_communication',repeat('4',64),null,repeat('5',64),
      pg_catalog.clock_timestamp(),
      pg_catalog.clock_timestamp()+interval '5 minutes'
    );
    raise exception 'service_role directly called approval-create primitive';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.connected_app_consume_approval_v1(
      'a4000000-0000-4000-8000-000000000001',
      'a5000000-0000-4000-8000-000000000001',
      'a1000000-0000-4000-8000-000000000001',
      'af000000-0000-4000-8000-000000000003',1,repeat('5',64)
    );
    raise exception 'service_role directly called approval-consume primitive';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.connected_app_begin_effect_v1(
      'a5000000-0000-4000-8000-000000000001',
      'a1000000-0000-4000-8000-000000000001',
      'af000000-0000-4000-8000-000000000003',1,repeat('b',64),
      'a4000000-0000-4000-8000-000000000001',
      'af000000-0000-4000-8000-000000000004',
      pg_catalog.clock_timestamp()+interval '1 minute'
    );
    raise exception 'service_role directly called begin-effect primitive';
  exception when insufficient_privilege then null;
  end;
end;
$primitive_authority$;

do $reviewed_decision_path$
declare
  requested_at timestamptz:=pg_catalog.clock_timestamp();
  result jsonb;
begin
  result:=public.connected_app_operator_put_approval_review_v1(
    'af000000-0000-4000-8000-000000000011',
    'af000000-0000-4000-8000-000000000012',
    'a1000000-0000-4000-8000-000000000001',
    'a3000000-0000-4000-8000-000000000002',
    'a3000000-0000-4000-8000-000000000003',
    'a2000000-0000-4000-8000-000000000001',
    'google','mail','mail.send',1,repeat('a',64),repeat('c',64),
    'connected-app-policy-v1',1,'external_communication',
    repeat('d',64),repeat('4',64),null,repeat('2',64),
    'af000000-0000-4000-8000-000000000013',requested_at,
    requested_at+interval '5 minutes'
  );
  if result->>'status'<>'pending' then
    raise exception 'reviewed approval request path failed';
  end if;
  result:=public.connected_app_operator_decide_approval_v1(
    'af000000-0000-4000-8000-000000000014',
    'a1000000-0000-4000-8000-000000000001',repeat('3',64),
    'af000000-0000-4000-8000-000000000011',
    'af000000-0000-4000-8000-000000000012',
    'a2000000-0000-4000-8000-000000000001',
    'a3000000-0000-4000-8000-000000000002',
    'a3000000-0000-4000-8000-000000000003',
    'google','mail','mail.send',1,repeat('a',64),repeat('c',64),
    'connected-app-policy-v1',1,repeat('d',64),repeat('4',64),null,
    repeat('2',64),'approved',requested_at
  );
  if result->>'status'<>'approved' then
    raise exception 'reviewed decision could not mint approval';
  end if;
end;
$reviewed_decision_path$;

reset role;

do $behavior$
declare
  owner_id constant uuid:='a1000000-0000-4000-8000-000000000001';
  connection_id constant uuid:='a2000000-0000-4000-8000-000000000001';
  grant_id constant uuid:='a3000000-0000-4000-8000-000000000001';
  task_id constant uuid:='a3000000-0000-4000-8000-000000000002';
  turn_id constant uuid:='a3000000-0000-4000-8000-000000000003';
  v_operation_id uuid;
  v_approval_id uuid;
  v_claim_id uuid;
  v_access_nonce uuid;
  v_effect_nonce uuid;
  deadline timestamptz;
  access_expiry timestamptz;
  effect_expiry timestamptz;
  result jsonb;
  replay jsonb;
  fence bigint;
begin
  for v_operation_id,v_approval_id,v_claim_id,v_access_nonce,v_effect_nonce in
    values
      ('a5000000-0000-4000-8000-000000000001'::uuid,
       'a4000000-0000-4000-8000-000000000001'::uuid,
       'a6000000-0000-4000-8000-000000000001'::uuid,
       'a7000000-0000-4000-8000-000000000001'::uuid,
       'a8000000-0000-4000-8000-000000000001'::uuid),
      ('a5000000-0000-4000-8000-000000000002'::uuid,
       'a4000000-0000-4000-8000-000000000002'::uuid,
       'a6000000-0000-4000-8000-000000000002'::uuid,
       'a7000000-0000-4000-8000-000000000002'::uuid,
       'a8000000-0000-4000-8000-000000000002'::uuid),
      ('a5000000-0000-4000-8000-000000000003'::uuid,
       'a4000000-0000-4000-8000-000000000003'::uuid,
       'a6000000-0000-4000-8000-000000000003'::uuid,
       'a7000000-0000-4000-8000-000000000003'::uuid,
       'a8000000-0000-4000-8000-000000000003'::uuid)
  loop
    deadline:=pg_catalog.clock_timestamp()+interval '5 minutes';
    access_expiry:=pg_catalog.clock_timestamp()+interval '80 seconds';
    result:=public.connected_app_claim_action_v2(
      v_operation_id,v_operation_id,owner_id,task_id,turn_id,connection_id,
      grant_id,
      'google','mail','mail.send',1,repeat('a',64),repeat('b',64),
      repeat('c',64),repeat('4',64),null,repeat('8',64),
      repeat(pg_catalog.right(v_operation_id::text,1),64),
      repeat('a',64),1,v_claim_id,v_claim_id,120,deadline
    );
    fence:=(result->>'fencing_token')::bigint;
    result:=public.connected_app_begin_access_v1(
      v_operation_id,owner_id,v_claim_id,fence,repeat('b',64),
      'preobserve',v_access_nonce,access_expiry
    );
    perform public.connected_app_consume_credential_lease_v1(
      v_operation_id,owner_id,connection_id,v_operation_id,'mail.send',
      v_claim_id,fence,'preobserve',v_access_nonce,access_expiry,1,
      repeat('a',64),
      repeat('b',64),repeat('c',64),repeat('8',64),1
    );

    if v_operation_id='a5000000-0000-4000-8000-000000000001'::uuid then
      effect_expiry:=pg_catalog.clock_timestamp()+interval '70 seconds';
      result:=public.connected_app_consume_approval_and_begin_effect_v1(
        v_approval_id,v_operation_id,owner_id,v_claim_id,fence,repeat('5',64),
        repeat('b',64),v_effect_nonce,effect_expiry
      );
      replay:=public.connected_app_consume_approval_and_begin_effect_v1(
        v_approval_id,v_operation_id,owner_id,v_claim_id,fence,repeat('5',64),
        repeat('b',64),v_effect_nonce,effect_expiry
      );
      if result is distinct from replay or result->>'status'<>'effect_possible'
         or not exists(
           select 1 from connected_app_private.approvals as approval
           where approval.approval_id=v_approval_id
             and approval.consumed_by_operation_id=v_operation_id
             and approval.consumed_at is not null) then
        raise exception 'atomic approval-effect success/replay failed';
      end if;
      begin
        perform public.connected_app_consume_approval_and_begin_effect_v1(
          v_approval_id,v_operation_id,owner_id,v_claim_id,fence,
          repeat('0',64),repeat('b',64),v_effect_nonce,effect_expiry
        );
        raise exception 'effect replay accepted a different approval binding';
      exception when sqlstate '55000' then null;
      end;
      begin
        perform public.connected_app_consume_approval_and_begin_effect_v1(
          v_approval_id,v_operation_id,owner_id,v_claim_id,fence,repeat('5',64),
          repeat('b',64),'a8000000-0000-4000-8000-000000000099',effect_expiry
        );
        raise exception 'effect replay accepted a different nonce';
      exception when sqlstate '55000' then null;
      end;
    elsif v_operation_id='a5000000-0000-4000-8000-000000000002'::uuid then
      effect_expiry:=pg_catalog.clock_timestamp()+interval '70 seconds';
      begin
        perform public.connected_app_consume_approval_and_begin_effect_v1(
          'a4000000-0000-4000-8000-000000000001',v_operation_id,owner_id,
          v_claim_id,fence,repeat('5',64),repeat('b',64),v_effect_nonce,
          effect_expiry
        );
        raise exception 'consumed approval crossed to a different operation';
      exception when sqlstate '55000' then null;
      end;
      begin
        perform public.connected_app_consume_approval_and_begin_effect_v1(
          v_approval_id,v_operation_id,owner_id,v_claim_id,fence,repeat('6',64),
          repeat('f',64),v_effect_nonce,effect_expiry
        );
        raise exception 'effect transition accepted wrong granted-actions hash';
      exception when sqlstate '55000' then null;
      end;
      if exists(
           select 1 from connected_app_private.approvals as approval
           where approval.approval_id=v_approval_id
             and approval.consumed_at is not null)
         or (select ledger.status from connected_app_private.action_ledger as ledger
             where ledger.operation_id=v_operation_id)<>'access_granted' then
        raise exception 'failed effect transition did not roll approval back';
      end if;
      begin
        perform public.connected_app_consume_approval_and_begin_effect_v1(
          v_approval_id,v_operation_id,owner_id,v_claim_id,fence,repeat('0',64),
          repeat('b',64),v_effect_nonce,effect_expiry
        );
        raise exception 'effect transition accepted wrong approval binding';
      exception when sqlstate '55000' then null;
      end;
      if exists(
           select 1 from connected_app_private.approvals as approval
           where approval.approval_id=v_approval_id
             and approval.consumed_at is not null) then
        raise exception 'wrong approval binding changed one-use authority';
      end if;
    else
      effect_expiry:=pg_catalog.clock_timestamp()+interval '70 seconds';
      begin
        perform public.connected_app_consume_approval_and_begin_effect_v1(
          v_approval_id,v_operation_id,owner_id,v_claim_id,fence,repeat('7',64),
          repeat('b',64),v_effect_nonce,effect_expiry
        );
        raise exception 'effect transition accepted an expired approval';
      exception when sqlstate '55000' then null;
      end;
      if exists(
           select 1 from connected_app_private.approvals as approval
           where approval.approval_id=v_approval_id
             and approval.consumed_at is not null) then
        raise exception 'expired approval was consumed';
      end if;
    end if;
  end loop;
end;
$behavior$;

do $authority$
declare
  procedure_oid oid:=pg_catalog.to_regprocedure(
    'public.connected_app_consume_approval_and_begin_effect_v1(uuid,uuid,uuid,uuid,bigint,text,text,uuid,timestamp with time zone)'
  );
  create_approval_oid oid:=pg_catalog.to_regprocedure(
    'public.connected_app_create_approval_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,timestamp with time zone,timestamp with time zone)'
  );
  consume_approval_oid oid:=pg_catalog.to_regprocedure(
    'public.connected_app_consume_approval_v1(uuid,uuid,uuid,uuid,bigint,text)'
  );
  begin_effect_oid oid:=pg_catalog.to_regprocedure(
    'public.connected_app_begin_effect_v1(uuid,uuid,uuid,bigint,text,uuid,uuid,timestamp with time zone)'
  );
  decision_oid oid:=pg_catalog.to_regprocedure(
    'public.connected_app_operator_decide_approval_v1(uuid,uuid,text,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,text,text,text,text,text,timestamp with time zone)'
  );
begin
  if procedure_oid is null or create_approval_oid is null
     or consume_approval_oid is null or begin_effect_oid is null
     or decision_oid is null
     or not pg_catalog.has_function_privilege('service_role',procedure_oid,'execute')
     or pg_catalog.has_function_privilege('authenticated',procedure_oid,'execute')
     or pg_catalog.has_function_privilege('anon',procedure_oid,'execute')
     or pg_catalog.has_function_privilege('public',procedure_oid,'execute')
     or pg_catalog.has_function_privilege(
       'service_role',create_approval_oid,'execute')
     or pg_catalog.has_function_privilege(
       'service_role',consume_approval_oid,'execute')
     or pg_catalog.has_function_privilege(
       'service_role',begin_effect_oid,'execute')
     or not pg_catalog.has_function_privilege(
       'service_role',decision_oid,'execute') then
    raise exception 'atomic approval-effect RPC authority failed';
  end if;
end;
$authority$;

rollback;

select 'CONNECTED_APPROVAL_EFFECT_TRANSITION_OK' as result;
