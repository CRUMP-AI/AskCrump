\set ON_ERROR_STOP on

do $approval_gate$ <<continuation_approval>>
declare
  owner_id constant uuid:='98600000-0000-4000-8000-000000000001';
  session_id constant uuid:='98600000-0000-4000-8000-000000000002';
  chat_id constant uuid:='98600000-0000-4000-8000-000000000003';
  message_id constant uuid:='98600000-0000-4000-8000-000000000004';
  connection_id constant uuid:='98600000-0000-4000-8000-000000000005';
  loop_id constant uuid:='98600000-0000-4000-8000-000000000006';
  step_id constant uuid:='98600000-0000-4000-8000-000000000007';
  wake_id constant uuid:='98600000-0000-4000-8000-000000000008';
  step_claim constant uuid:='98600000-0000-4000-8000-000000000009';
  invocation_id constant uuid:='98600000-0000-4000-8000-00000000000a';
  proposal_id constant uuid:='98600000-0000-4000-8000-00000000000b';
  request_id constant uuid:='98600000-0000-4000-8000-00000000000c';
  grant_id constant uuid:='98600000-0000-4000-8000-00000000000d';
  action_id constant uuid:='98600000-0000-4000-8000-00000000000e';
  task_id constant uuid:='98600000-0000-4000-8000-00000000000f';
  action_payload_id constant uuid:='98600000-0000-4000-8000-000000000010';
  approval_id constant uuid:='98600000-0000-4000-8000-000000000011';
  preview_id constant uuid:='98600000-0000-4000-8000-000000000012';
  decision_id constant uuid:='98600000-0000-4000-8000-000000000013';
  ledger_claim_id constant uuid:='98600000-0000-4000-8000-000000000014';
  continuation_request constant uuid:='98600000-0000-4000-8000-000000000015';
  continuation_token constant uuid:='98600000-0000-4000-8000-000000000016';
  origin_sha constant text:=repeat('a',64);
  request_sha constant text:=repeat('b',64);
  planning_sha constant text:=repeat('c',64);
  proposal_sha constant text:=repeat('d',64);
  proposal_binding_sha constant text:=repeat('e',64);
  authorization_sha constant text:=repeat('1',64);
  actions_sha constant text:=repeat('2',64);
  scopes_sha constant text:=repeat('3',64);
  command_sha constant text:=repeat('4',64);
  parameters_sha constant text:=repeat('5',64);
  parameters_reference_sha constant text:=repeat('6',64);
  approval_binding_sha constant text:=repeat('7',64);
  preview_reference_sha constant text:=repeat('8',64);
  preview_sha constant text:=repeat('9',64);
  terminal_sha constant text:=repeat('f',64);
  now_at timestamptz:=pg_catalog.clock_timestamp();
  expires_at timestamptz;
  turn_id uuid;
  turn_claim uuid;
  row_value jsonb;
  runnable_count integer;
begin
  expires_at:=now_at+interval '10 minutes';
  delete from public.users where id=owner_id;
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(owner_id,'continuation-write@example.test',
    '$argon2id$continuation-write',true,false,now_at-interval '1 minute',
    now_at-interval '1 minute','production',now_at,false,now_at);
  insert into public.sessions(
    id,user_id,token_hash,device_id,device_name,platform,device_info,
    created_at,last_activity,expires_at
  ) values(session_id,owner_id,repeat('0',64),'continuation-write-device',
    'Continuation write','web','{}'::jsonb,now_at,now_at,now_at+interval '1 day');
  insert into public.user_chats(user_id,chat_id,title,messages,created_at,updated_at)
  values(owner_id,chat_id,'Continuation approval',
    pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
      'id',message_id,'role','user','content','Send the approved reply.')),
    now_at,now_at);
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(connection_id,owner_id,'google','mail','personal',
    '98600000-0000-4000-8000-000000000017',1,'active',authorization_sha,
    array['mail.send'],actions_sha,scopes_sha,repeat('a',64),
    '98600000-0000-4000-8000-000000000018',repeat('b',64),
    now_at+interval '1 day',now_at);
  select claim.turn_id,claim.claim_token into strict turn_id,turn_claim
  from public.connected_chat_claim_turn_v1(
    owner_id,chat_id,message_id,origin_sha,request_sha) as claim;
  perform public.connected_multi_step_start_v1(
    loop_id,owner_id,session_id,origin_sha,chat_id,message_id,turn_id,turn_claim,
    'UTC',request_sha,now_at,expires_at,8);
  perform public.connected_multi_step_claim_v1(
    owner_id,loop_id,step_id,1,wake_id,step_claim,planning_sha,now_at,30);
  perform public.connected_multi_step_mark_invoked_v1(
    owner_id,loop_id,step_id,0,2,wake_id,step_claim,planning_sha,
    invocation_id,now_at,60);
  perform public.connected_multi_step_put_envelope_v1(
    proposal_id,loop_id,step_id,owner_id,turn_id,0,planning_sha,
    'loop-commitment-v1',proposal_sha,proposal_binding_sha,now_at,expires_at,
    'loop-envelope-v1',repeat('A',16),repeat('B',64),repeat('C',16),
    repeat('D',64),repeat('0',64));
  perform public.connected_multi_step_attach_proposal_v1(
    owner_id,loop_id,step_id,0,3,wake_id,step_claim,planning_sha,invocation_id,
    proposal_id,proposal_sha,proposal_binding_sha,'action',connection_id,
    'google','mail','mail.send',1,authorization_sha,now_at);
  row_value:=public.connected_multi_step_prepare_action_v1(
    owner_id,session_id,chat_id,message_id,turn_id,turn_claim,origin_sha,
    request_sha,loop_id,step_id,0,4,planning_sha,proposal_id,proposal_sha,
    proposal_binding_sha,request_id,command_sha,grant_id,action_id,task_id,
    connection_id,'google','mail','mail.send',1,authorization_sha,
    actions_sha,scopes_sha,4,action_payload_id,parameters_reference_sha,
    parameters_sha,null,'connected-app-policy-v1',approval_id,
    approval_binding_sha,preview_id,preview_reference_sha,preview_sha,
    now_at,expires_at);
  if row_value->>'status'<>'pending_approval' then
    raise exception 'write preparation did not require approval: %',row_value;
  end if;
  perform public.connected_multi_step_settle_v1(
    owner_id,loop_id,step_id,0,4,wake_id,step_claim,planning_sha,invocation_id,
    proposal_id,proposal_sha,proposal_binding_sha,'waiting_approval',
    'pending_approval',action_id,approval_id,null,null,now_at);
  select pg_catalog.count(*) into runnable_count
  from public.connected_multi_step_continuation_list_v1(
    32,pg_catalog.clock_timestamp()) as item
  where item->>'loop_id'=loop_id::text;
  if runnable_count<>0 then
    raise exception 'unconsumed approval was runnable';
  end if;
  perform public.connected_app_operator_decide_approval_v1(
    decision_id,owner_id,origin_sha,approval_id,action_id,connection_id,
    task_id,turn_id,'google','mail','mail.send',1,authorization_sha,scopes_sha,
    'connected-app-policy-v1',1,approval_binding_sha,parameters_sha,null,
    preview_sha,'approved',pg_catalog.clock_timestamp());
  select pg_catalog.count(*) into runnable_count
  from public.connected_multi_step_continuation_list_v1(
    32,pg_catalog.clock_timestamp()) as item
  where item->>'loop_id'=loop_id::text;
  if runnable_count<>0 then
    raise exception 'approval without a durable action receipt was runnable';
  end if;
  insert into connected_app_private.action_ledger(
    operation_id,action_id,owner_id,task_id,turn_id,connection_id,grant_id,
    provider,resource,action,authorization_revision,authorization_snapshot_sha256,
    granted_actions_sha256,granted_scopes_sha256,parameters_sha256,
    resource_version_sha256,authority_sha256,idempotency_key_sha256,
    invocation_binding_sha256,task_state_revision,status,mutates_external_state,
    approval_class,claim_request_id,claim_id,fencing_token,lease_expires_at,
    execution_deadline,terminal_outcome,terminal_binding_sha256,terminal_at,
    created_at,updated_at
  ) values(action_id,action_id,owner_id,task_id,turn_id,connection_id,grant_id,
    'google','mail','mail.send',1,authorization_sha,actions_sha,scopes_sha,
    parameters_sha,null,repeat('a',64),repeat('b',64),repeat('c',64),4,
    'terminal',true,'external_communication',
    '98600000-0000-4000-8000-000000000019',ledger_claim_id,88,
    now_at+interval '1 minute',now_at+interval '5 minutes','succeeded',
    terminal_sha,pg_catalog.clock_timestamp(),now_at,pg_catalog.clock_timestamp());
  select pg_catalog.count(*) into runnable_count
  from public.connected_multi_step_continuation_list_v1(
    32,pg_catalog.clock_timestamp()) as item
  where item->>'loop_id'=loop_id::text;
  if runnable_count<>0 then
    raise exception 'unconsumed action approval was runnable';
  end if;
  update connected_app_private.approvals as approval_row
  set consumed_at=pg_catalog.clock_timestamp(),
      consumed_by_operation_id=continuation_approval.action_id
  where approval_row.approval_id=continuation_approval.approval_id;
  select item into strict row_value
  from public.connected_multi_step_continuation_list_v1(
    32,pg_catalog.clock_timestamp()) as item
  where item->>'loop_id'=loop_id::text;
  if row_value->>'kind'<>'approved_write'
     or row_value->>'task_state_revision'<>'5' then
    raise exception 'consumed approval and receipt were not runnable: %',row_value;
  end if;
  row_value:=public.connected_multi_step_continuation_claim_v1(
    owner_id,loop_id,5,continuation_request,continuation_token,
    pg_catalog.clock_timestamp(),90);
  if row_value->>'kind'<>'approved_write'
     or row_value->>'approval_step_id'<>step_id::text
     or row_value->>'action_id'<>action_id::text
     or row_value->>'approval_id'<>approval_id::text then
    raise exception 'database approval proof was not bound into claim: %',row_value;
  end if;
  row_value:=public.connected_multi_step_continuation_instruction_v1(
    owner_id,loop_id,continuation_request,continuation_token,1,
    pg_catalog.clock_timestamp());
  if row_value->>'instruction'<>'Send the approved reply.' then
    raise exception 'approved continuation instruction rehydration failed: %',row_value;
  end if;
  row_value:=public.connected_multi_step_continuation_fail_v1(
    owner_id,loop_id,continuation_request,continuation_token,1,5,
    'connections_missing',pg_catalog.clock_timestamp());
  if row_value->>'status'<>'failed'
     or row_value->>'task_state_revision'<>'6'
     or row_value->>'last_result_reference_id'<>action_id::text
     or row_value->>'last_result_binding_sha256'<>terminal_sha then
    raise exception 'deterministic failure lost approved write receipt: %',row_value;
  end if;
  delete from public.users where id=owner_id;
  if exists(select 1 from connected_loop_continuation_private.jobs
      where connected_loop_continuation_private.jobs.owner_id=continuation_approval.owner_id)
     or exists(select 1 from connected_loop_continuation_private.claims
      where connected_loop_continuation_private.claims.owner_id=continuation_approval.owner_id) then
    raise exception 'approval continuation deletion cascade failed';
  end if;
end;
$approval_gate$;

select 'CONNECTED_MULTI_STEP_CONTINUATION_APPROVAL_OK' as result;
