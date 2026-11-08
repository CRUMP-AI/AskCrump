\set ON_ERROR_STOP on

do $test$ <<multi_step_test>>
declare
  owner_id constant uuid := '96700000-0000-4000-8000-000000000001';
  other_owner_id constant uuid := '96700000-0000-4000-8000-000000000002';
  session_id constant uuid := '96700000-0000-4000-8000-000000000003';
  chat_id constant uuid := '96700000-0000-4000-8000-000000000004';
  message_id constant uuid := '96700000-0000-4000-8000-000000000005';
  loop_id constant uuid := '96700000-0000-4000-8000-000000000006';
  step_id constant uuid := '96700000-0000-4000-8000-000000000007';
  wake_id constant uuid := '96700000-0000-4000-8000-000000000008';
  step_claim constant uuid := '96700000-0000-4000-8000-000000000009';
  invocation_id constant uuid := '96700000-0000-4000-8000-00000000000a';
  proposal_id constant uuid := '96700000-0000-4000-8000-00000000000b';
  origin_sha constant text := repeat('a',64);
  request_sha constant text := repeat('b',64);
  planning_sha constant text := repeat('c',64);
  proposal_sha constant text := repeat('d',64);
  proposal_binding_sha constant text := repeat('e',64);
  now_at timestamptz := pg_catalog.clock_timestamp();
  expires_at timestamptz;
  turn_id uuid;
  turn_claim uuid;
  row_value jsonb;
  replay_value jsonb;
begin
  expires_at:=now_at+interval '20 minutes';
  delete from public.users where id in (owner_id,other_owner_id);
  if exists(
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.users'::pg_catalog.regclass
      and attname='registration_environment' and attnum>0 and not attisdropped
  ) then
    insert into public.users(
      id,email,password_hash,is_verified,is_guest,created_at,updated_at,
      registration_environment,registration_submitted_at,
      password_setup_required,password_inbox_bound_at
    ) values
      (owner_id,'multi-step-owner@example.test','$argon2id$multi-step-owner',
       true,false,now_at-interval '1 minute',now_at-interval '1 minute',
       'production',now_at,false,now_at),
      (other_owner_id,'multi-step-other@example.test','$argon2id$multi-step-other',
       true,false,now_at-interval '1 minute',now_at-interval '1 minute',
       'production',now_at,false,now_at);
  else
    insert into public.users(id) values(owner_id),(other_owner_id);
  end if;
  if exists(
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.sessions'::pg_catalog.regclass
      and attname='token_hash' and attnum>0 and not attisdropped
  ) then
    insert into public.sessions(
      id,user_id,token_hash,device_id,device_name,platform,device_info,
      created_at,last_activity,expires_at
    ) values(session_id,owner_id,repeat('0',64),'multi-step-device',
      'Multi step test','web','{}'::jsonb,now_at,now_at,now_at+interval '1 day');
  else
    insert into public.sessions(id,user_id,expires_at)
    values(session_id,owner_id,now_at+interval '1 day');
  end if;
  select claim.turn_id,claim.claim_token into strict turn_id,turn_claim
  from public.connected_chat_claim_turn_v1(
    owner_id,chat_id,message_id,origin_sha,request_sha) as claim;

  row_value:=public.connected_multi_step_start_v1(
    loop_id,owner_id,session_id,origin_sha,chat_id,message_id,turn_id,turn_claim,
    'America/New_York',request_sha,now_at,expires_at,8);
  if row_value->>'status'<>'active' or row_value->>'current_step'<>'0'
     or row_value->>'task_state_revision'<>'1' then
    raise exception 'multi-step start failed: %',row_value;
  end if;
  if public.connected_multi_step_start_v1(
    loop_id,owner_id,session_id,origin_sha,chat_id,message_id,turn_id,turn_claim,
    'America/New_York',request_sha,now_at,expires_at,8) is distinct from row_value then
    raise exception 'multi-step start response-loss replay changed';
  end if;
  if public.connected_multi_step_read_loop_v1(other_owner_id,loop_id) is not null then
    raise exception 'multi-step owner isolation failed';
  end if;
  row_value:=public.connected_multi_step_list_v1(owner_id,10);
  if pg_catalog.jsonb_typeof(row_value)<>'array'
     or pg_catalog.jsonb_array_length(row_value)<>1
     or row_value->0->>'loop_id'<>loop_id::text
     or row_value->0 ? 'owner_id'
     or row_value->0 ? 'session_id'
     or row_value->0 ? 'turn_claim_token'
     or row_value->0 ? 'request_binding_sha256'
     or row_value::text like '%multi-step-owner@example.test%'
     or public.connected_multi_step_list_v1(other_owner_id,10)<>'[]'::jsonb then
    raise exception 'multi-step owner-scoped content-free list failed: %',row_value;
  end if;
  row_value:=public.connected_multi_step_owner_status_v1(owner_id,loop_id);
  if row_value->>'loop_id'<>loop_id::text or row_value->>'status'<>'active'
     or row_value ? 'owner_id' or row_value ? 'session_id'
     or public.connected_multi_step_owner_status_v1(other_owner_id,loop_id)
        is not null then
    raise exception 'multi-step owner status projection failed: %',row_value;
  end if;

  row_value:=public.connected_multi_step_claim_v1(
    owner_id,loop_id,step_id,1,wake_id,step_claim,planning_sha,now_at,30);
  if row_value->>'kind'<>'claim' or row_value->>'state'<>'claimed'
     or row_value->'loop'->>'task_state_revision'<>'2' then
    raise exception 'multi-step claim failed: %',row_value;
  end if;
  row_value:=public.connected_multi_step_mark_invoked_v1(
    owner_id,loop_id,step_id,0,2,wake_id,step_claim,planning_sha,
    invocation_id,now_at,60);
  if row_value->>'state'<>'invoked' or (row_value->>'invoke_permitted')::boolean is not true
     or row_value->'loop'->>'task_state_revision'<>'3' then
    raise exception 'multi-step invocation failed: %',row_value;
  end if;
  replay_value:=public.connected_multi_step_mark_invoked_v1(
    owner_id,loop_id,step_id,0,2,wake_id,step_claim,planning_sha,
    invocation_id,now_at,60);
  if (replay_value->>'invoke_permitted')::boolean is not true
     or replay_value->>'invocation_id'<>invocation_id::text then
    raise exception 'mark-invoked response-loss recovery failed: %',replay_value;
  end if;

  row_value:=public.connected_multi_step_put_envelope_v1(
    proposal_id,loop_id,step_id,owner_id,turn_id,0,planning_sha,
    'loop-commitment-v1',proposal_sha,proposal_binding_sha,now_at,expires_at,
    'loop-envelope-v1',repeat('A',16),repeat('B',64),repeat('C',16),
    repeat('D',64),repeat('f',64));
  if row_value->>'proposal_id'<>proposal_id::text
     or row_value ? 'plaintext' then
    raise exception 'encrypted proposal custody failed: %',row_value;
  end if;
  replay_value:=public.connected_multi_step_put_envelope_v1(
    proposal_id,loop_id,step_id,owner_id,turn_id,0,planning_sha,
    'loop-commitment-v1',proposal_sha,proposal_binding_sha,now_at,expires_at,
    'loop-envelope-v1',repeat('A',16),repeat('B',64),repeat('C',16),
    repeat('D',64),repeat('f',64));
  if replay_value is distinct from row_value then
    raise exception 'encrypted proposal response-loss replay changed';
  end if;
  row_value:=public.connected_multi_step_attach_proposal_v1(
    owner_id,loop_id,step_id,0,3,wake_id,step_claim,planning_sha,invocation_id,
    proposal_id,proposal_sha,proposal_binding_sha,'complete',
    null,null,null,null,null,null,now_at);
  if row_value->>'proposal_kind'<>'complete'
     or row_value->'loop'->>'task_state_revision'<>'4' then
    raise exception 'proposal attachment failed: %',row_value;
  end if;
  row_value:=public.connected_multi_step_settle_v1(
    owner_id,loop_id,step_id,0,4,wake_id,step_claim,planning_sha,invocation_id,
    proposal_id,proposal_sha,proposal_binding_sha,'completed',null,
    null,null,null,null,now_at);
  if row_value->>'kind'<>'settlement'
     or row_value->'loop'->>'status'<>'completed'
     or row_value->'loop'->>'task_state_revision'<>'5' then
    raise exception 'terminal settlement failed: %',row_value;
  end if;
  replay_value:=public.connected_multi_step_settle_v1(
    owner_id,loop_id,step_id,0,4,wake_id,step_claim,planning_sha,invocation_id,
    proposal_id,proposal_sha,proposal_binding_sha,'completed',null,
    null,null,null,null,now_at);
  if replay_value is distinct from row_value then
    raise exception 'settlement response-loss replay changed';
  end if;
  if public.connected_multi_step_read_step_v1(other_owner_id,loop_id,step_id)
       is not null then
    raise exception 'step owner isolation failed';
  end if;

  delete from public.users where id in (owner_id,other_owner_id);
  if exists(select 1 from connected_loop_private.loops as item
       where item.owner_id=multi_step_test.owner_id)
     or exists(select 1 from connected_loop_private.steps as item
       where item.owner_id=multi_step_test.owner_id)
     or exists(select 1 from connected_loop_private.envelopes as item
       where item.owner_id=multi_step_test.owner_id) then
    raise exception 'account deletion left multi-step state';
  end if;
end;
$test$;

do $read_test$ <<multi_step_read_test>>
declare
  owner_id constant uuid := '96800000-0000-4000-8000-000000000001';
  session_id constant uuid := '96800000-0000-4000-8000-000000000002';
  chat_id constant uuid := '96800000-0000-4000-8000-000000000003';
  message_id constant uuid := '96800000-0000-4000-8000-000000000004';
  connection_id constant uuid := '96800000-0000-4000-8000-000000000005';
  loop_id constant uuid := '96800000-0000-4000-8000-000000000006';
  step_id constant uuid := '96800000-0000-4000-8000-000000000007';
  wake_id constant uuid := '96800000-0000-4000-8000-000000000008';
  step_claim constant uuid := '96800000-0000-4000-8000-000000000009';
  invocation_id constant uuid := '96800000-0000-4000-8000-00000000000a';
  proposal_id constant uuid := '96800000-0000-4000-8000-00000000000b';
  request_id constant uuid := '96800000-0000-4000-8000-00000000000c';
  grant_id constant uuid := '96800000-0000-4000-8000-00000000000d';
  action_id constant uuid := '96800000-0000-4000-8000-00000000000e';
  task_id constant uuid := '96800000-0000-4000-8000-00000000000f';
  action_payload_id constant uuid := '96800000-0000-4000-8000-000000000010';
  execution_id constant uuid := '96800000-0000-4000-8000-000000000011';
  result_payload_id constant uuid := '96800000-0000-5000-8000-000000000012';
  result_completion_id constant uuid := '96800000-0000-5000-8000-000000000013';
  result_claim_id constant uuid := '96800000-0000-4000-8000-000000000014';
  read_nonce constant uuid := '96800000-0000-4000-8000-000000000015';
  origin_sha constant text := repeat('a',64);
  request_sha constant text := repeat('b',64);
  planning_sha constant text := repeat('c',64);
  proposal_sha constant text := repeat('d',64);
  proposal_binding_sha constant text := repeat('e',64);
  authorization_sha constant text := repeat('1',64);
  actions_sha constant text := repeat('2',64);
  scopes_sha constant text := repeat('3',64);
  command_sha constant text := repeat('4',64);
  parameters_sha constant text := repeat('5',64);
  parameters_reference_sha constant text := repeat('6',64);
  authority_sha constant text := repeat('7',64);
  idempotency_sha constant text := repeat('8',64);
  result_binding_sha constant text := repeat('9',64);
  now_at timestamptz := pg_catalog.clock_timestamp();
  expires_at timestamptz;
  turn_id uuid;
  turn_claim uuid;
  row_value jsonb;
begin
  expires_at:=now_at+interval '10 minutes';
  delete from connected_app_private.payload_tombstones
  where payload_id=result_payload_id;
  if exists(
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.users'::pg_catalog.regclass
      and attname='registration_environment' and attnum>0 and not attisdropped
  ) then
    insert into public.users(
      id,email,password_hash,is_verified,is_guest,created_at,updated_at,
      registration_environment,registration_submitted_at,
      password_setup_required,password_inbox_bound_at
    ) values(owner_id,'multi-step-read@example.test','$argon2id$multi-step-read',
      true,false,now_at-interval '1 minute',now_at-interval '1 minute',
      'production',now_at,false,now_at);
  else
    insert into public.users(id) values(owner_id);
  end if;
  if exists(
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.sessions'::pg_catalog.regclass
      and attname='token_hash' and attnum>0 and not attisdropped
  ) then
    insert into public.sessions(
      id,user_id,token_hash,device_id,device_name,platform,device_info,
      created_at,last_activity,expires_at
    ) values(session_id,owner_id,repeat('0',64),'multi-step-read-device',
      'Multi step read test','web','{}'::jsonb,now_at,now_at,now_at+interval '1 day');
  else
    insert into public.sessions(id,user_id,expires_at)
    values(session_id,owner_id,now_at+interval '1 day');
  end if;
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(connection_id,owner_id,'google','mail','personal',
    '96800000-0000-4000-8000-000000000016',1,'active',authorization_sha,
    array['mail.search'],actions_sha,scopes_sha,repeat('a',64),
    '96800000-0000-4000-8000-000000000017',repeat('b',64),
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
    repeat('D',64),repeat('f',64));
  perform public.connected_multi_step_attach_proposal_v1(
    owner_id,loop_id,step_id,0,3,wake_id,step_claim,planning_sha,invocation_id,
    proposal_id,proposal_sha,proposal_binding_sha,'action',connection_id,
    'google','mail','mail.search',1,authorization_sha,now_at);

  row_value:=public.connected_multi_step_prepare_action_v1(
    owner_id,session_id,chat_id,message_id,turn_id,turn_claim,origin_sha,
    request_sha,loop_id,step_id,0,4,planning_sha,proposal_id,proposal_sha,
    proposal_binding_sha,request_id,command_sha,grant_id,action_id,task_id,
    connection_id,'google','mail','mail.search',1,authorization_sha,
    actions_sha,scopes_sha,4,action_payload_id,parameters_reference_sha,
    parameters_sha,null,'connected-app-policy-v1',null,null,null,null,null,
    now_at,expires_at);
  if row_value->>'status'<>'ready' or row_value->>'action_id'<>action_id::text then
    raise exception 'multi-step read preparation failed: %',row_value;
  end if;
  row_value:=public.connected_multi_step_begin_read_v1(
    owner_id,session_id,chat_id,message_id,turn_id,turn_claim,origin_sha,
    request_sha,loop_id,step_id,0,4,planning_sha,proposal_id,proposal_sha,
    proposal_binding_sha,execution_id,request_id,action_id,command_sha);
  if row_value->>'stage'<>'executing'
     or row_value->>'execution_request_id'<>execution_id::text then
    raise exception 'multi-step read begin failed: %',row_value;
  end if;

  insert into connected_app_private.action_ledger(
    operation_id,action_id,owner_id,task_id,turn_id,connection_id,grant_id,
    provider,resource,action,authorization_revision,authorization_snapshot_sha256,
    granted_actions_sha256,granted_scopes_sha256,parameters_sha256,
    resource_version_sha256,authority_sha256,idempotency_key_sha256,
    invocation_binding_sha256,task_state_revision,status,mutates_external_state,approval_class,
    claim_request_id,claim_id,fencing_token,lease_expires_at,execution_deadline,
    access_phase,read_use_nonce,read_credential_expires_at,read_consumed_at,
    access_started_at,created_at,updated_at
  ) values(action_id,action_id,owner_id,task_id,turn_id,connection_id,grant_id,
    'google','mail','mail.search',1,authorization_sha,actions_sha,scopes_sha,
    parameters_sha,null,authority_sha,idempotency_sha,repeat('6',64),4,'access_granted',false,
    'none','96800000-0000-4000-8000-000000000018',result_claim_id,77,
    now_at+interval '1 minute',now_at+interval '5 minutes','read',read_nonce,
    now_at+interval '1 minute',now_at,now_at-interval '1 second',
    now_at-interval '2 seconds',now_at);
  perform public.connected_app_payload_put_v1(
    result_payload_id,owner_id,connection_id,action_id,'google','mail.search',
    'loop-result-commitment-v1',repeat('c',64),now_at,expires_at,
    repeat('d',64),repeat('e',64),'loop-result-wrap-v1',repeat('A',16),
    repeat('B',64),repeat('C',16),repeat('D',64),repeat('f',64));
  perform public.connected_app_settle_read_result_v1(
    result_completion_id,action_id,action_id,owner_id,connection_id,
    'google','mail','mail.search',result_payload_id,'loop-result-commitment-v1',
    repeat('c',64),repeat('e',64),repeat('1',64),authority_sha,idempotency_sha,
    result_claim_id,77,read_nonce,now_at,repeat('2',64));
  row_value:=public.connected_multi_step_settle_v1(
    owner_id,loop_id,step_id,0,4,wake_id,step_claim,planning_sha,invocation_id,
    proposal_id,proposal_sha,proposal_binding_sha,'active','read_complete',
    action_id,null,result_payload_id,result_binding_sha,now_at);
  if row_value->'loop'->>'status'<>'active'
     or row_value->'loop'->>'current_step'<>'1'
     or row_value->>'result_reference_id'<>result_payload_id::text then
    raise exception 'multi-step read settlement failed: %',row_value;
  end if;
  row_value:=public.connected_multi_step_stop_v1(
    loop_id,owner_id,session_id,origin_sha,chat_id,message_id,turn_id,turn_claim,
    'UTC',request_sha,now_at,expires_at,8,5,'cancelled',
    pg_catalog.clock_timestamp());
  if row_value->>'status'<>'cancelled' then
    raise exception 'multi-step cancellation failed: %',row_value;
  end if;
  delete from public.users where id=owner_id;
end;
$read_test$;

do $write_test$ <<multi_step_write_test>>
declare
  owner_id constant uuid := '96900000-0000-4000-8000-000000000001';
  session_id constant uuid := '96900000-0000-4000-8000-000000000002';
  chat_id constant uuid := '96900000-0000-4000-8000-000000000003';
  message_id constant uuid := '96900000-0000-4000-8000-000000000004';
  connection_id constant uuid := '96900000-0000-4000-8000-000000000005';
  loop_id constant uuid := '96900000-0000-4000-8000-000000000006';
  step_id constant uuid := '96900000-0000-4000-8000-000000000007';
  wake_id constant uuid := '96900000-0000-4000-8000-000000000008';
  step_claim constant uuid := '96900000-0000-4000-8000-000000000009';
  invocation_id constant uuid := '96900000-0000-4000-8000-00000000000a';
  proposal_id constant uuid := '96900000-0000-4000-8000-00000000000b';
  request_id constant uuid := '96900000-0000-4000-8000-00000000000c';
  grant_id constant uuid := '96900000-0000-4000-8000-00000000000d';
  action_id constant uuid := '96900000-0000-4000-8000-00000000000e';
  task_id constant uuid := '96900000-0000-4000-8000-00000000000f';
  action_payload_id constant uuid := '96900000-0000-4000-8000-000000000010';
  approval_id constant uuid := '96900000-0000-4000-8000-000000000011';
  preview_id constant uuid := '96900000-0000-4000-8000-000000000012';
  decision_id constant uuid := '96900000-0000-4000-8000-000000000013';
  ledger_claim_id constant uuid := '96900000-0000-4000-8000-000000000014';
  origin_sha constant text := repeat('a',64);
  request_sha constant text := repeat('b',64);
  planning_sha constant text := repeat('c',64);
  proposal_sha constant text := repeat('d',64);
  proposal_binding_sha constant text := repeat('e',64);
  authorization_sha constant text := repeat('1',64);
  actions_sha constant text := repeat('2',64);
  scopes_sha constant text := repeat('3',64);
  command_sha constant text := repeat('4',64);
  parameters_sha constant text := repeat('5',64);
  parameters_reference_sha constant text := repeat('6',64);
  approval_binding_sha constant text := repeat('7',64);
  preview_reference_sha constant text := repeat('8',64);
  preview_sha constant text := repeat('9',64);
  terminal_sha constant text := repeat('f',64);
  now_at timestamptz := pg_catalog.clock_timestamp();
  expires_at timestamptz;
  turn_id uuid;
  turn_claim uuid;
  row_value jsonb;
  receipt jsonb;
begin
  expires_at:=now_at+interval '10 minutes';
  if exists(
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.users'::pg_catalog.regclass
      and attname='registration_environment' and attnum>0 and not attisdropped
  ) then
    insert into public.users(
      id,email,password_hash,is_verified,is_guest,created_at,updated_at,
      registration_environment,registration_submitted_at,
      password_setup_required,password_inbox_bound_at
    ) values(owner_id,'multi-step-write@example.test','$argon2id$multi-step-write',
      true,false,now_at-interval '1 minute',now_at-interval '1 minute',
      'production',now_at,false,now_at);
  else
    insert into public.users(id) values(owner_id);
  end if;
  if exists(
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.sessions'::pg_catalog.regclass
      and attname='token_hash' and attnum>0 and not attisdropped
  ) then
    insert into public.sessions(
      id,user_id,token_hash,device_id,device_name,platform,device_info,
      created_at,last_activity,expires_at
    ) values(session_id,owner_id,repeat('0',64),'multi-step-write-device',
      'Multi step write test','web','{}'::jsonb,now_at,now_at,now_at+interval '1 day');
  else
    insert into public.sessions(id,user_id,expires_at)
    values(session_id,owner_id,now_at+interval '1 day');
  end if;
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(connection_id,owner_id,'google','mail','personal',
    '96900000-0000-4000-8000-000000000015',1,'active',authorization_sha,
    array['mail.send'],actions_sha,scopes_sha,repeat('a',64),
    '96900000-0000-4000-8000-000000000016',repeat('b',64),
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
  if row_value->>'status'<>'pending_approval'
     or row_value->>'approval_id'<>approval_id::text then
    raise exception 'multi-step write preparation failed: %',row_value;
  end if;
  row_value:=public.connected_multi_step_settle_v1(
    owner_id,loop_id,step_id,0,4,wake_id,step_claim,planning_sha,invocation_id,
    proposal_id,proposal_sha,proposal_binding_sha,'waiting_approval',
    'pending_approval',action_id,approval_id,null,null,now_at);
  if row_value->'loop'->>'status'<>'waiting_approval'
     or row_value->>'approval_id'<>approval_id::text then
    raise exception 'multi-step write did not stop for approval: %',row_value;
  end if;
  perform public.connected_app_operator_decide_approval_v1(
    decision_id,owner_id,origin_sha,approval_id,action_id,connection_id,
    task_id,turn_id,'google','mail','mail.send',1,authorization_sha,scopes_sha,
    'connected-app-policy-v1',1,approval_binding_sha,parameters_sha,null,
    preview_sha,'approved',pg_catalog.clock_timestamp());
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
    '96900000-0000-4000-8000-000000000017',ledger_claim_id,88,
    now_at+interval '1 minute',now_at+interval '5 minutes','succeeded',
    terminal_sha,pg_catalog.clock_timestamp(),now_at,pg_catalog.clock_timestamp());
  update connected_app_private.approvals as approval_row
  set consumed_at=pg_catalog.clock_timestamp(),
    consumed_by_operation_id=multi_step_write_test.action_id
  where approval_row.approval_id=multi_step_write_test.approval_id;
  receipt:=public.connected_multi_step_read_write_result_v1(
    owner_id,loop_id,step_id,action_id,approval_id);
  if receipt->>'result_reference_id'<>action_id::text
     or receipt->>'result_binding_sha256'<>terminal_sha
     or receipt->>'status'<>'succeeded' then
    raise exception 'multi-step write receipt failed: %',receipt;
  end if;
  row_value:=public.connected_multi_step_resume_approved_v1(
    loop_id,owner_id,session_id,origin_sha,chat_id,message_id,turn_id,turn_claim,
    'UTC',request_sha,now_at,expires_at,8,5,step_id,action_id,approval_id,
    action_id,terminal_sha,pg_catalog.clock_timestamp());
  if row_value->>'status'<>'active' or row_value->>'pending_approval_id' is not null
     or row_value->>'last_result_reference_id'<>action_id::text then
    raise exception 'multi-step approved write resume failed: %',row_value;
  end if;
  if public.connected_multi_step_resume_approved_v1(
    loop_id,owner_id,session_id,origin_sha,chat_id,message_id,turn_id,turn_claim,
    'UTC',request_sha,now_at,expires_at,8,5,step_id,action_id,approval_id,
    action_id,terminal_sha,pg_catalog.clock_timestamp()) is distinct from row_value then
    raise exception 'multi-step approved write response-loss replay changed';
  end if;
  receipt:=public.connected_multi_step_read_write_result_v1(
    owner_id,loop_id,step_id,action_id,approval_id);
  row_value:=public.connected_multi_step_read_step_v1(owner_id,loop_id,step_id);
  if receipt->>'result_reference_id'<>action_id::text
     or receipt->>'result_binding_sha256'<>terminal_sha
     or row_value->>'approval_id'<>approval_id::text
     or row_value->>'result_reference_id'<>action_id::text
     or row_value->>'result_binding_sha256'<>terminal_sha then
    raise exception 'multi-step post-restart write receipt recovery failed: %, %',
      receipt,row_value;
  end if;
  delete from public.users where id=owner_id;
end;
$write_test$;

select 'CONNECTED_MULTI_STEP_OPERATOR_LOOP_OK' as result;
