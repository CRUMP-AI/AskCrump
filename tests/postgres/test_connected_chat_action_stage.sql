\set ON_ERROR_STOP on

do $test$
<<stage_test>>
declare
  owner_id constant uuid := '71900000-0000-4000-8000-000000000001';
  session_id constant uuid := '71900000-0000-4000-8000-000000000002';
  chat_id constant uuid := '71900000-0000-4000-8000-000000000003';
  message_id constant uuid := '71900000-0000-4000-8000-000000000004';
  connection_id constant uuid := '71900000-0000-4000-8000-000000000005';
  incarnation_id constant uuid := '71900000-0000-4000-8000-000000000006';
  credential_id constant uuid := '71900000-0000-4000-8000-000000000007';
  planning_id constant uuid := '71900000-0000-4000-8000-000000000008';
  plan_payload_id constant uuid := '71900000-0000-4000-8000-000000000009';
  invocation_id constant uuid := '71900000-0000-4000-8000-000000000010';
  request_id constant uuid := '71900000-0000-4000-8000-000000000011';
  grant_id constant uuid := '71900000-0000-4000-8000-000000000012';
  action_id constant uuid := '71900000-0000-4000-8000-000000000013';
  task_id constant uuid := '71900000-0000-4000-8000-000000000014';
  action_payload_id constant uuid := '71900000-0000-4000-8000-000000000015';
  execution_request_id constant uuid := '71900000-0000-4000-8000-000000000016';
  completion_id constant uuid := '71900000-0000-4000-8000-000000000017';
  assistant_id constant uuid := '71900000-0000-4000-8000-000000000018';
  origin_sha constant text := repeat('a',64);
  request_sha constant text := repeat('b',64);
  planning_sha constant text := repeat('c',64);
  plan_payload_sha constant text := repeat('d',64);
  plan_reference_sha constant text := repeat('e',64);
  command_sha constant text := repeat('f',64);
  action_payload_sha constant text := repeat('1',64);
  action_reference_sha constant text := repeat('2',64);
  authorization_sha constant text := repeat('3',64);
  granted_actions_sha constant text := repeat('4',64);
  granted_scopes_sha constant text := repeat('5',64);
  requested_at timestamptz := pg_catalog.clock_timestamp();
  expires_at timestamptz;
  claimed_turn_id uuid;
  claim_token uuid;
  row_value jsonb;
  user_message jsonb;
  assistant_message jsonb;
  response_data jsonb;
begin
  expires_at := requested_at + interval '8 minutes';
  if exists (
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.users'::pg_catalog.regclass
      and attname='registration_environment' and attnum>0 and not attisdropped
  ) then
    insert into public.users(
      id,email,password_hash,is_verified,is_guest,created_at,updated_at,
      registration_environment,registration_submitted_at,
      password_setup_required,password_inbox_bound_at
    ) values(
      owner_id,'connected-stage@example.test',
      '$argon2id$connected-stage-password-hash-v1',true,false,
      requested_at - interval '1 minute',requested_at - interval '1 minute',
      'production',requested_at,false,requested_at
    );
  else
    insert into public.users(id) values(owner_id);
  end if;
  if exists (
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.sessions'::pg_catalog.regclass
      and attname='token_hash' and attnum>0 and not attisdropped
  ) then
    insert into public.sessions(
      id,user_id,token_hash,device_id,device_name,platform,device_info,
      created_at,last_activity,expires_at
    ) values(
      session_id,owner_id,repeat('0',64),'connected-stage-device',
      'Connected stage test','web','{}'::jsonb,requested_at,requested_at,
      requested_at + interval '1 day'
    );
  else
    insert into public.sessions(id,user_id,expires_at)
    values(session_id,owner_id,requested_at + interval '1 day');
  end if;
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(
    connection_id,owner_id,'google','mail','personal',incarnation_id,
    1,'active',authorization_sha,array['mail.search'],granted_actions_sha,
    granted_scopes_sha,repeat('6',64),credential_id,repeat('7',64),
    requested_at + interval '1 day',requested_at
  );

  select claimed.turn_id,claimed.claim_token into strict claimed_turn_id,claim_token
  from public.connected_chat_claim_turn_v1(
    owner_id,chat_id,message_id,origin_sha,request_sha
  ) as claimed;
  perform public.connected_plan_begin_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,'stage-plan-key',planning_sha,
    plan_payload_id,requested_at,expires_at
  );
  perform public.connected_plan_mark_invoked_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,'stage-plan-key',planning_sha,
    plan_payload_id,requested_at,expires_at,invocation_id
  );
  perform public.connected_plan_envelope_put_v1(
    owner_id,claimed_turn_id,planning_id,planning_sha,plan_payload_id,
    'stage-hmac-key',plan_payload_sha,plan_reference_sha,
    requested_at,expires_at,'stage-kek',repeat('A',16),repeat('B',64),
    repeat('C',16),repeat('D',32),repeat('8',64)
  );
  perform public.connected_plan_settle_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,'stage-plan-key',planning_sha,
    plan_payload_id,requested_at,expires_at,invocation_id,'action',
    connection_id,'google','mail','mail.search','stage-hmac-key',
    plan_payload_sha,plan_reference_sha
  );

  row_value := public.connected_operator_prepare_chat_action_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,request_id,origin_sha,command_sha,
    grant_id,action_id,task_id,connection_id,plan_payload_id,
    plan_reference_sha,'google','mail','mail.search',1,authorization_sha,
    granted_actions_sha,granted_scopes_sha,1,action_payload_id,
    action_reference_sha,action_payload_sha,null,'connected-app-policy-v1',
    null,null,null,null,null,requested_at,expires_at
  );
  if row_value->>'request_id'<>request_id::text
     or row_value->>'status'<>'ready'
     or not exists(
       select 1 from connected_chat_private.turns as turn
       where turn.turn_id=claimed_turn_id and turn.stage='prepared'
         and turn.preparation_request_id=stage_test.request_id
         and turn.action_id=stage_test.action_id
     ) then
    raise exception 'planned-to-prepared transition failed: %',row_value;
  end if;
  if public.connected_operator_prepare_chat_action_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,request_id,origin_sha,command_sha,
    grant_id,action_id,task_id,connection_id,plan_payload_id,
    plan_reference_sha,'google','mail','mail.search',1,authorization_sha,
    granted_actions_sha,granted_scopes_sha,1,action_payload_id,
    action_reference_sha,action_payload_sha,null,'connected-app-policy-v1',
    null,null,null,null,null,requested_at,expires_at
  ) is distinct from row_value then
    raise exception 'preparation replay changed';
  end if;

  row_value := public.connected_operator_begin_chat_read_v1(
    execution_request_id,owner_id,session_id,chat_id,message_id,claimed_turn_id,
    origin_sha,request_sha,claim_token,request_id,action_id,command_sha
  );
  if row_value->>'stage'<>'executing'
     or row_value->>'execution_request_id'<>execution_request_id::text
     or not exists(
       select 1 from connected_chat_private.turns as turn
       where turn.turn_id=claimed_turn_id and turn.stage='executing'
         and turn.execution_request_id=stage_test.execution_request_id
     ) then
    raise exception 'prepared-to-executing transition failed: %',row_value;
  end if;
  perform public.connected_operator_begin_chat_read_v1(
    execution_request_id,owner_id,session_id,chat_id,message_id,claimed_turn_id,
    origin_sha,request_sha,claim_token,request_id,action_id,command_sha
  );
  begin
    perform public.connected_operator_begin_chat_read_v1(
      '71900000-0000-4000-8000-000000000099',owner_id,session_id,
      chat_id,message_id,claimed_turn_id,origin_sha,request_sha,claim_token,
      request_id,action_id,command_sha
    );
    raise exception 'conflicting execution replay unexpectedly succeeded';
  exception when sqlstate '55000' then null;
  end;

  user_message := pg_catalog.jsonb_build_object(
    'id',message_id,'role','user','content','private user content'
  );
  assistant_message := pg_catalog.jsonb_build_object(
    'id',assistant_id,'role','assistant','inReplyTo',message_id,
    'content','private assistant content'
  );
  response_data := pg_catalog.jsonb_build_object(
    'assistantMessage',assistant_message,
    'connectedApp',pg_catalog.jsonb_build_object('state','completed')
  );
  row_value := public.connected_operator_complete_chat_v1(
    completion_id,owner_id,session_id,claimed_turn_id,chat_id,message_id,
    assistant_id,claim_token,origin_sha,request_sha,'action_terminal',
    'stage-completion-key',repeat('9',64),'Connected result',
    user_message,assistant_message,response_data
  );
  if row_value->>'completion_id'<>completion_id::text
     or not exists(
       select 1 from connected_chat_private.turns as turn
       where turn.turn_id=claimed_turn_id and turn.stage='terminal'
     ) then
    raise exception 'executing action could not complete atomically';
  end if;

  delete from public.users where id=stage_test.owner_id;
  if exists(
       select 1 from connected_chat_private.turns as turn_row
       where turn_row.owner_id=stage_test.owner_id
     )
     or exists(
       select 1 from connected_plan_private.operations as operation_row
       where operation_row.owner_id=stage_test.owner_id
     )
     or exists(
       select 1 from connected_app_private.action_preparations as preparation_row
       where preparation_row.owner_id=stage_test.owner_id
     )
     or exists(
       select 1 from connected_chat_completion_private.completions as completion_row
       where completion_row.owner_id=stage_test.owner_id
     )
     or exists(
       select 1 from public.sessions as session_row
       where session_row.user_id=stage_test.owner_id
     ) then
    raise exception 'account deletion left chat action-stage state';
  end if;
end;
$test$;

select 'CONNECTED_CHAT_ACTION_STAGE_OK' as result;
