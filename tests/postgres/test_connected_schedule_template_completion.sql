\set ON_ERROR_STOP on

do $test$
<<schedule_test>>
declare
  owner_id constant uuid := '76300000-0000-4000-8000-000000000001';
  session_id constant uuid := '76300000-0000-4000-8000-000000000002';
  chat_id constant uuid := '76300000-0000-4000-8000-000000000003';
  message_id constant uuid := '76300000-0000-4000-8000-000000000004';
  connection_id constant uuid := '76300000-0000-4000-8000-000000000005';
  incarnation_id constant uuid := '76300000-0000-4000-8000-000000000006';
  credential_id constant uuid := '76300000-0000-4000-8000-000000000007';
  planning_id constant uuid := '76300000-0000-4000-8000-000000000008';
  plan_payload_id constant uuid := '76300000-0000-4000-8000-000000000009';
  invocation_id constant uuid := '76300000-0000-4000-8000-000000000010';
  request_id constant uuid := '76300000-0000-4000-8000-000000000011';
  schedule_id constant uuid := '76300000-0000-4000-8000-000000000012';
  template_id constant uuid := '76300000-0000-4000-8000-000000000013';
  task_id constant uuid := '76300000-0000-4000-8000-000000000014';
  claim_id constant uuid := '76300000-0000-4000-8000-000000000015';
  completion_id constant uuid := '76300000-0000-4000-8000-000000000016';
  operation_id constant uuid := '76300000-0000-4000-8000-000000000017';
  origin_sha constant text := repeat('a',64);
  request_sha constant text := repeat('b',64);
  planning_sha constant text := repeat('c',64);
  plan_payload_sha constant text := repeat('d',64);
  plan_reference_sha constant text := repeat('e',64);
  authorization_sha constant text := repeat('1',64);
  granted_actions_sha constant text := repeat('2',64);
  granted_scopes_sha constant text := repeat('3',64);
  parameters_sha constant text := repeat('4',64);
  template_reference_sha constant text := repeat('5',64);
  template_record_sha constant text := repeat('6',64);
  requested_at timestamptz := pg_catalog.clock_timestamp();
  expires_at timestamptz;
  finished_at timestamptz;
  claimed_turn_id uuid;
  claim_token uuid;
  result jsonb;
  replay jsonb;
begin
  expires_at := requested_at + interval '12 minutes';
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
      owner_id,'connected-schedule@example.test',
      '$argon2id$connected-schedule-password-hash-v1',true,false,
      requested_at-interval '1 minute',requested_at-interval '1 minute',
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
      session_id,owner_id,repeat('0',64),'connected-schedule-device',
      'Connected schedule test','web','{}'::jsonb,requested_at,requested_at,
      requested_at+interval '1 day'
    );
  else
    insert into public.sessions(id,user_id,expires_at)
    values(session_id,owner_id,requested_at+interval '1 day');
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
    granted_scopes_sha,repeat('7',64),credential_id,repeat('8',64),
    requested_at+interval '1 day',requested_at
  );
  select claimed.turn_id,claimed.claim_token into strict claimed_turn_id,claim_token
  from public.connected_chat_claim_turn_v1(
    owner_id,chat_id,message_id,origin_sha,request_sha
  ) as claimed;
  perform public.connected_plan_begin_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,'schedule-plan-key',planning_sha,
    plan_payload_id,requested_at,expires_at
  );
  perform public.connected_plan_mark_invoked_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,'schedule-plan-key',planning_sha,
    plan_payload_id,requested_at,expires_at,invocation_id
  );
  perform public.connected_plan_envelope_put_v1(
    owner_id,claimed_turn_id,planning_id,planning_sha,plan_payload_id,
    'schedule-plan-hmac',plan_payload_sha,plan_reference_sha,
    requested_at,expires_at,'schedule-plan-kek',repeat('A',16),repeat('B',64),
    repeat('C',16),repeat('D',32),repeat('9',64)
  );
  perform public.connected_plan_settle_v1(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,'schedule-plan-key',planning_sha,
    plan_payload_id,requested_at,expires_at,invocation_id,'schedule',
    connection_id,'google','mail','mail.search','schedule-plan-hmac',
    plan_payload_sha,plan_reference_sha
  );

  result := public.connected_operator_create_chat_schedule_v2(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,plan_payload_id,request_id,schedule_id,
    template_id,task_id,connection_id,'google','mail','mail.search',1,
    authorization_sha,granted_actions_sha,granted_scopes_sha,
    'schedule-template-hmac',parameters_sha,null,template_reference_sha,
    'schedule-template-kek',repeat('E',16),repeat('F',64),repeat('G',16),
    repeat('H',32),template_record_sha,'UTC',60,null,null,false,requested_at
  );
  if result->>'request_id'<>request_id::text
     or result->>'schedule_id'<>schedule_id::text
     or result->>'template_id'<>template_id::text
     or result->>'turn_id'<>claimed_turn_id::text
     or not exists(select 1 from connected_chat_private.turns as turn
       where turn.turn_id=claimed_turn_id and turn.stage='prepared'
         and turn.schedule_request_id=schedule_test.request_id
         and turn.schedule_id=schedule_test.schedule_id) then
    raise exception 'atomic chat schedule creation failed: %',result;
  end if;
  replay := public.connected_operator_create_chat_schedule_v2(
    owner_id,session_id,chat_id,message_id,claimed_turn_id,claim_token,
    origin_sha,request_sha,planning_id,plan_payload_id,request_id,schedule_id,
    template_id,task_id,connection_id,'google','mail','mail.search',1,
    authorization_sha,granted_actions_sha,granted_scopes_sha,
    'schedule-template-hmac',parameters_sha,null,template_reference_sha,
    'schedule-template-kek',repeat('X',16),repeat('Y',64),repeat('Z',16),
    repeat('Q',32),repeat('0',64),'UTC',60,null,null,false,requested_at
  );
  if replay is distinct from result then
    raise exception 'response-loss replay changed schedule result';
  end if;
  if public.connected_operator_read_chat_schedule_v2(owner_id,request_id)
       is distinct from result then
    raise exception 'schedule readback changed exact result';
  end if;
  if public.connected_app_read_schedule_template_v2(template_id)
       ->>'payload_ciphertext'<>repeat('H',32) then
    raise exception 'encrypted template custody read failed';
  end if;

  update connected_app_private.schedules as schedule
  set next_run_at=pg_catalog.clock_timestamp()-interval '1 second'
  where schedule.schedule_id=schedule_test.schedule_id;
  result := public.connected_app_claim_schedule_v2(claim_id,120);
  if result->>'claim_id'<>claim_id::text
     or result->>'grant_id'<>claim_id::text
     or result->>'template_reference_binding_sha256'<>template_reference_sha
     or not exists(select 1 from connected_app_private.task_grants as grant_row
       where grant_row.grant_id=claim_id and grant_row.actions=array['mail.search']) then
    raise exception 'v2 schedule claim/grant failed: %',result;
  end if;
  if public.connected_app_read_schedule_claim_v2(claim_id) is distinct from result then
    raise exception 'claim response-loss readback changed';
  end if;
  finished_at := pg_catalog.clock_timestamp();
  result := public.connected_app_finish_schedule_v2(
    completion_id,schedule_id,owner_id,claim_id,1,'read',operation_id,
    finished_at+interval '60 seconds',finished_at
  );
  if result->>'completion_id'<>completion_id::text
     or result->>'outcome'<>'read' then
    raise exception 'durable schedule finish failed: %',result;
  end if;
  replay := public.connected_app_finish_schedule_v2(
    completion_id,schedule_id,owner_id,claim_id,1,'read',operation_id,
    finished_at+interval '60 seconds',finished_at
  );
  if replay is distinct from result
     or public.connected_app_read_schedule_finish_v2(
          schedule_id,claim_id,completion_id) is distinct from result then
    raise exception 'durable completion replay/readback changed';
  end if;

  -- Simulate a crash that left the prior claim grant apparently live.  A
  -- later revoked-authority claim must pause the schedule and retire it.
  update connected_app_private.task_grants as grant_row set revoked_at=null
  where grant_row.grant_id=claim_id;
  update connected_app_private.schedules as schedule
  set next_run_at=pg_catalog.clock_timestamp()-interval '1 second'
  where schedule.schedule_id=schedule_test.schedule_id;
  update connected_app_private.connections as connection set authorization_state='revoked',
    revoked_at=pg_catalog.clock_timestamp(),authorization_expires_at=null,
    broker_credential_ref=null,credential_ref_sha256=null
  where connection.id=schedule_test.connection_id;
  result := public.connected_app_claim_schedule_v2(
    '76300000-0000-4000-8000-000000000099',120);
  if result is not null then
    raise exception 'revoked authority unexpectedly returned a claim: %',result;
  end if;
  if not exists(select 1 from connected_app_private.schedules as schedule
       where schedule.schedule_id=schedule_test.schedule_id and schedule.status='paused'
         and schedule.claim_id is null) then
    raise exception 'revoked authority did not fail closed and pause';
  end if;
  if exists(select 1 from connected_app_private.task_grants as grant_row
      where grant_row.grant_id=claim_id and grant_row.revoked_at is null) then
    raise exception 'revoked schedule authority left a live task grant';
  end if;

  update connected_app_private.schedules as schedule set status='cancelled',next_run_at=null
  where schedule.schedule_id=schedule_test.schedule_id;
  if exists(select 1 from connected_schedule_private.templates as template
      where template.template_id=schedule_test.template_id
        and (template.record_state<>'deleted' or template.payload_ciphertext is not null)) then
    raise exception 'schedule cancel did not erase ciphertext';
  end if;
  delete from public.users as app_user where app_user.id=schedule_test.owner_id;
  if exists(select 1 from connected_schedule_private.templates as template where template.owner_id=schedule_test.owner_id)
     or exists(select 1 from connected_schedule_private.run_completions as completion where completion.owner_id=schedule_test.owner_id)
     or exists(select 1 from connected_app_private.schedules as schedule where schedule.owner_id=schedule_test.owner_id) then
    raise exception 'account deletion left schedule custody state';
  end if;
end;
$test$;

do $acl$
begin
  if pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_operator_create_schedule_v1(uuid,uuid,uuid,text,text,uuid,uuid,text,text,text,uuid,text,text,integer,integer,integer,boolean,timestamp with time zone,timestamp with time zone)',
       'EXECUTE')
     or pg_catalog.has_function_privilege(
       'service_role','public.connected_app_claim_schedule_v1(uuid,integer)','EXECUTE')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_claim_schedule_v2(uuid,integer)','EXECUTE')
     or pg_catalog.has_function_privilege(
       'authenticated','public.connected_app_claim_schedule_v2(uuid,integer)','EXECUTE') then
    raise exception 'schedule v2 ACL boundary failed';
  end if;
end;
$acl$;

select 'CONNECTED_SCHEDULE_TEMPLATE_COMPLETION_OK' as result;
