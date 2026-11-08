\set ON_ERROR_STOP on

do $chat_test$ <<chat_test>>
declare
  owner_id constant uuid:='98100000-0000-4000-8000-000000000001';
  session_id constant uuid:='98100000-0000-4000-8000-000000000002';
  chat_id constant uuid:='98100000-0000-4000-8000-000000000003';
  message_id constant uuid:='98100000-0000-4000-8000-000000000004';
  connection_id constant uuid:='98100000-0000-4000-8000-000000000005';
  planning_id constant uuid:='98100000-0000-4000-8000-000000000006';
  plan_payload_id constant uuid:='98100000-0000-4000-8000-000000000007';
  invocation_id constant uuid:='98100000-0000-4000-8000-000000000008';
  request_id constant uuid:='98100000-0000-4000-8000-000000000009';
  grant_id constant uuid:='98100000-0000-4000-8000-00000000000a';
  action_id constant uuid:='98100000-0000-4000-8000-00000000000b';
  task_id constant uuid:='98100000-0000-4000-8000-00000000000c';
  parameters_payload_id constant uuid:='98100000-0000-4000-8000-00000000000d';
  origin_sha constant text:=repeat('a',64);
  request_sha constant text:=repeat('b',64);
  planning_sha constant text:=repeat('c',64);
  plan_payload_sha constant text:=repeat('d',64);
  plan_reference_sha constant text:=repeat('e',64);
  command_sha constant text:=repeat('f',64);
  parameters_sha constant text:=repeat('1',64);
  parameters_reference_sha constant text:=repeat('2',64);
  authorization_sha constant text:=repeat('3',64);
  actions_sha constant text:='edf4e2f8620ed30b54f928df774457286dc2ef026ce4632e334eb745639ccefd';
  scopes_sha constant text:=repeat('5',64);
  version_sha constant text:=repeat('6',64);
  requested_at timestamptz:=pg_catalog.clock_timestamp();
  plan_expires_at timestamptz;
  snapshot_expires_at timestamptz;
  claimed_turn_id uuid;
  claim_token uuid;
  row_value jsonb;
  replay_value jsonb;
begin
  plan_expires_at:=requested_at+interval '8 minutes';
  snapshot_expires_at:=requested_at+interval '4 minutes';
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(owner_id,'cancel-chat@example.test','$argon2id$cancel-chat',true,
    false,requested_at-interval '1 minute',requested_at-interval '1 minute',
    'production',requested_at,false,requested_at);
  insert into public.sessions(
    id,user_id,token_hash,device_id,device_name,platform,device_info,
    created_at,last_activity,expires_at
  ) values(session_id,owner_id,repeat('0',64),'cancel-chat-device',
    'Cancel snapshot test','web','{}'::jsonb,requested_at,requested_at,
    requested_at+interval '1 day');
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(connection_id,owner_id,'google','calendar','personal',
    '98100000-0000-4000-8000-00000000000e',1,'active',authorization_sha,
    array['calendar.cancel','calendar.get'],actions_sha,scopes_sha,repeat('7',64),
    '98100000-0000-4000-8000-00000000000f',repeat('8',64),
    requested_at+interval '1 day',requested_at);
  select claimed.turn_id,claimed.claim_token
    into strict claimed_turn_id,claim_token
  from public.connected_chat_claim_turn_v1(
    owner_id,chat_id,message_id,origin_sha,request_sha) as claimed;
  perform public.connected_plan_begin_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,'cancel-plan-key',planning_sha,
    plan_payload_id,requested_at,plan_expires_at);
  perform public.connected_plan_mark_invoked_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,'cancel-plan-key',planning_sha,
    plan_payload_id,requested_at,plan_expires_at,invocation_id);
  perform public.connected_plan_envelope_put_v1(
    owner_id,claimed_turn_id,planning_id,planning_sha,plan_payload_id,
    'cancel-plan-hmac',plan_payload_sha,plan_reference_sha,
    requested_at,plan_expires_at,'cancel-plan-kek',repeat('A',16),
    repeat('B',64),repeat('C',16),repeat('D',32),repeat('9',64));
  perform public.connected_plan_settle_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,'cancel-plan-key',planning_sha,
    plan_payload_id,requested_at,plan_expires_at,invocation_id,'action',
    connection_id,'google','calendar','calendar.cancel','cancel-plan-hmac',
    plan_payload_sha,plan_reference_sha);

  row_value:=public.connected_app_prepare_cancel_snapshot_chat_v1(
    owner_id,chat_id,message_id,claimed_turn_id,claim_token,origin_sha,
    request_sha,plan_payload_id,request_id,session_id,origin_sha,command_sha,
    grant_id,action_id,task_id,connection_id,'google','calendar','calendar.get',
    1,authorization_sha,actions_sha,scopes_sha,1,parameters_payload_id,
    parameters_reference_sha,parameters_sha,version_sha,
    'connected-app-policy-v1',requested_at,snapshot_expires_at);
  if row_value->>'request_id'<>request_id::text
     or row_value->>'action_id'<>action_id::text
     or row_value->>'status'<>'ready'
     or not exists(
       select 1 from connected_cancel_private.snapshot_reads as snapshot
       where snapshot.request_id=chat_test.request_id
         and snapshot.source_kind='chat' and snapshot.status='prepared')
     or not exists(
       select 1 from connected_chat_private.turns as turn_row
       where turn_row.turn_id=claimed_turn_id and turn_row.stage='planned') then
    raise exception 'interactive cancellation snapshot preparation failed: %',row_value;
  end if;
  replay_value:=public.connected_app_prepare_cancel_snapshot_chat_v1(
    owner_id,chat_id,message_id,claimed_turn_id,claim_token,origin_sha,
    request_sha,plan_payload_id,request_id,session_id,origin_sha,command_sha,
    grant_id,action_id,task_id,connection_id,'google','calendar','calendar.get',
    1,authorization_sha,actions_sha,scopes_sha,1,parameters_payload_id,
    parameters_reference_sha,parameters_sha,version_sha,
    'connected-app-policy-v1',requested_at,snapshot_expires_at);
  if replay_value is distinct from row_value then
    raise exception 'interactive snapshot response-loss replay changed';
  end if;
  row_value:=public.connected_app_begin_cancel_snapshot_chat_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,plan_payload_id,request_id,action_id,command_sha);
  if row_value->>'status'<>'started'
     or not exists(
       select 1 from connected_cancel_private.snapshot_reads as snapshot
       where snapshot.request_id=chat_test.request_id
         and snapshot.status='started' and snapshot.started_at is not null) then
    raise exception 'interactive cancellation snapshot start failed: %',row_value;
  end if;
  perform public.connected_app_begin_cancel_snapshot_chat_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,plan_payload_id,request_id,action_id,command_sha);
  begin
    perform public.connected_app_begin_cancel_snapshot_chat_v1(
      owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
      origin_sha,request_sha,plan_payload_id,request_id,
      '98100000-0000-4000-8000-000000000099',command_sha);
    raise exception 'interactive sibling action substitution succeeded';
  exception when sqlstate '55000' then null;
  end;
  delete from public.users where id=chat_test.owner_id;
  if exists(select 1 from connected_cancel_private.snapshot_reads as snapshot
       where snapshot.owner_id=chat_test.owner_id) then
    raise exception 'account deletion left interactive snapshot authority';
  end if;
end;
$chat_test$;

do $schedule_test$ <<schedule_test>>
declare
  owner_id constant uuid:='98200000-0000-4000-8000-000000000001';
  connection_id constant uuid:='98200000-0000-4000-8000-000000000002';
  schedule_id constant uuid:='98200000-0000-4000-8000-000000000003';
  template_id constant uuid:='98200000-0000-4000-8000-000000000004';
  parent_task_id constant uuid:='98200000-0000-4000-8000-000000000005';
  turn_id constant uuid:='98200000-0000-4000-8000-000000000006';
  claim_id constant uuid:='98200000-0000-4000-8000-000000000007';
  occurrence_id constant uuid:='98200000-0000-4000-8000-000000000008';
  occurrence_action_id constant uuid:='98200000-0000-4000-8000-000000000009';
  occurrence_approval_id constant uuid:='98200000-0000-4000-8000-00000000000a';
  request_id constant uuid:='98200000-0000-4000-8000-00000000000b';
  synthetic_session_id constant uuid:='98200000-0000-4000-8000-00000000000c';
  child_grant_id constant uuid:='98200000-0000-4000-8000-00000000000d';
  child_action_id constant uuid:='98200000-0000-4000-8000-00000000000e';
  child_task_id constant uuid:='98200000-0000-4000-8000-00000000000f';
  parameters_payload_id constant uuid:='98200000-0000-4000-8000-000000000010';
  authorization_sha constant text:=repeat('1',64);
  actions_sha constant text:='edf4e2f8620ed30b54f928df774457286dc2ef026ce4632e334eb745639ccefd';
  scopes_sha constant text:=repeat('2',64);
  parameters_sha constant text:=repeat('3',64);
  version_sha constant text:=repeat('4',64);
  reference_sha constant text:=repeat('5',64);
  command_sha constant text:=repeat('6',64);
  session_binding_sha constant text:=repeat('7',64);
  now_at timestamptz:=pg_catalog.clock_timestamp();
  expires_at timestamptz;
  row_value jsonb;
begin
  expires_at:=now_at+interval '90 seconds';
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(owner_id,'cancel-schedule@example.test','$argon2id$cancel-schedule',
    true,false,now_at-interval '1 minute',now_at-interval '1 minute',
    'production',now_at,false,now_at);
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(connection_id,owner_id,'google','calendar','personal',
    '98200000-0000-4000-8000-000000000011',2,'active',authorization_sha,
    array['calendar.cancel','calendar.get'],actions_sha,scopes_sha,repeat('8',64),
    '98200000-0000-4000-8000-000000000012',repeat('9',64),
    now_at+interval '1 day',now_at);
  insert into connected_schedule_private.templates(
    template_id,schedule_id,owner_id,turn_id,connection_id,task_id,
    plan_payload_id,plan_reference_binding_sha256,provider,resource,action,
    authorization_revision,authorization_snapshot_sha256,
    granted_actions_sha256,granted_scopes_sha256,commitment_key_id,
    parameters_sha256,resource_version_sha256,reference_binding_sha256,
    key_id,wrapped_key_nonce,wrapped_key_ciphertext,payload_nonce,
    payload_ciphertext,record_binding_sha256,record_state,created_at,updated_at
  ) values(template_id,schedule_id,owner_id,turn_id,connection_id,parent_task_id,
    '98200000-0000-4000-8000-000000000013',repeat('a',64),'google',
    'calendar','calendar.cancel',2,authorization_sha,actions_sha,scopes_sha,
    'cancel-commitment',parameters_sha,version_sha,reference_sha,
    'cancel-envelope',repeat('A',16),repeat('B',64),repeat('C',16),
    repeat('D',64),repeat('e',64),'live',now_at,now_at);
  insert into connected_app_private.schedules(
    schedule_id,owner_id,connection_id,task_id,provider,resource,action,
    action_template_ref,parameters_sha256,task_state_revision,time_zone,
    cadence_seconds,quiet_start_minute,quiet_end_minute,
    requires_approval_every_run,status,next_run_at,claim_id,claim_expires_at,
    created_at,updated_at
  ) values(schedule_id,owner_id,connection_id,parent_task_id,'google','calendar',
    'calendar.cancel',template_id,parameters_sha,3,'UTC',3600,null,null,true,
    'active',now_at-interval '1 minute',claim_id,now_at+interval '2 minutes',
    now_at-interval '1 day',now_at);
  insert into connected_app_private.task_grants(
    grant_id,owner_id,task_id,turn_id,connection_id,provider,resource,
    authorization_revision,authorization_snapshot_sha256,actions,
    actions_sha256,task_state_revision,expires_at
  ) values(claim_id,owner_id,parent_task_id,turn_id,connection_id,'google',
    'calendar',2,authorization_sha,array['calendar.cancel'],
    '9114e5237c49ef53d3bc53bb651bc65517220385e42e34cd7b47e14ac02411e3',
    3,now_at+interval '2 minutes');
  insert into connected_schedule_private.occurrences(
    occurrence_id,schedule_id,owner_id,action_id,approval_id,task_id,turn_id,
    connection_id,provider,resource,action,authorization_revision,
    authorization_snapshot_sha256,granted_scopes_sha256,task_state_revision,
    parameters_sha256,resource_version_sha256,scheduled_for,
    occurrence_created_at,current_claim_id,status,updated_at
  ) values(occurrence_id,schedule_id,owner_id,occurrence_action_id,
    occurrence_approval_id,parent_task_id,turn_id,connection_id,'google',
    'calendar','calendar.cancel',2,authorization_sha,scopes_sha,3,
    parameters_sha,version_sha,now_at-interval '1 minute',now_at,
    claim_id,'pending_approval',now_at);

  row_value:=public.connected_app_prepare_cancel_snapshot_schedule_v1(
    owner_id,schedule_id,claim_id,occurrence_id,turn_id,request_id,
    synthetic_session_id,session_binding_sha,command_sha,child_grant_id,
    child_action_id,child_task_id,connection_id,'google','calendar',
    'calendar.get',2,authorization_sha,actions_sha,scopes_sha,3,
    parameters_payload_id,repeat('b',64),repeat('c',64),version_sha,
    'connected-app-policy-v1',now_at,expires_at);
  if row_value->>'status'<>'ready'
     or not exists(
       select 1 from connected_cancel_private.snapshot_reads as snapshot
       where snapshot.request_id=schedule_test.request_id
         and snapshot.source_kind='schedule'
         and snapshot.occurrence_id=schedule_test.occurrence_id
         and snapshot.status='prepared') then
    raise exception 'scheduled cancellation snapshot preparation failed: %',row_value;
  end if;
  row_value:=public.connected_app_begin_cancel_snapshot_schedule_v1(
    owner_id,schedule_id,claim_id,occurrence_id,turn_id,request_id,
    child_action_id,command_sha);
  if row_value->>'status'<>'started' then
    raise exception 'scheduled cancellation snapshot start failed: %',row_value;
  end if;
  perform public.connected_app_begin_cancel_snapshot_schedule_v1(
    owner_id,schedule_id,claim_id,occurrence_id,turn_id,request_id,
    child_action_id,command_sha);
  update connected_schedule_private.occurrences as occurrence
  set current_claim_id='98200000-0000-4000-8000-000000000099'
  where occurrence.occurrence_id=schedule_test.occurrence_id;
  begin
    perform public.connected_app_begin_cancel_snapshot_schedule_v1(
      owner_id,schedule_id,claim_id,occurrence_id,turn_id,request_id,
      child_action_id,command_sha);
    raise exception 'lost schedule claim still authorized provider read';
  exception when sqlstate '55000' then null;
  end;
  delete from public.users where id=schedule_test.owner_id;
  if exists(select 1 from connected_cancel_private.snapshot_reads as snapshot
       where snapshot.owner_id=schedule_test.owner_id) then
    raise exception 'account deletion left scheduled snapshot authority';
  end if;
end;
$schedule_test$;

select 'CONNECTED_CALENDAR_CANCEL_SNAPSHOT_AUTHORITY_OK' as result;
