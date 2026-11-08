\set ON_ERROR_STOP on

do $test$ <<schedule_approval_test>>
declare
  owner_id constant uuid := '88400000-0000-4000-8000-000000000001';
  other_owner_id constant uuid := '88400000-0000-4000-8000-000000000002';
  connection_id constant uuid := '88400000-0000-4000-8000-000000000003';
  template_id constant uuid := '88400000-0000-4000-8000-000000000004';
  schedule_id constant uuid := '88400000-0000-4000-8000-000000000005';
  task_id constant uuid := '88400000-0000-4000-8000-000000000006';
  turn_id constant uuid := '88400000-0000-4000-8000-000000000007';
  claim_a constant uuid := '88400000-0000-4000-8000-000000000008';
  occurrence_id constant uuid := '88400000-0000-4000-8000-000000000009';
  action_id constant uuid := '88400000-0000-4000-8000-00000000000a';
  approval_id constant uuid := '88400000-0000-4000-8000-00000000000b';
  preview_id constant uuid := '88400000-0000-4000-8000-00000000000c';
  completion_a constant uuid := '88400000-0000-4000-8000-00000000000d';
  decision_id constant uuid := '88400000-0000-4000-8000-00000000000e';
  claim_b constant uuid := '88400000-0000-4000-8000-00000000000f';
  completion_b constant uuid := '88400000-0000-4000-8000-000000000010';
  authorization_sha constant text := repeat('1',64);
  actions_sha constant text := repeat('2',64);
  scopes_sha constant text := repeat('3',64);
  parameters_sha constant text := repeat('4',64);
  approval_binding_sha constant text := repeat('5',64);
  preview_sha constant text := repeat('6',64);
  preview_reference_sha constant text := repeat('7',64);
  session_sha constant text := repeat('8',64);
  now_at timestamptz := pg_catalog.clock_timestamp();
  occurrence_created timestamptz;
  approval_expires timestamptz;
  finished_at timestamptz;
  claim_result jsonb;
  put_result jsonb;
  replay_result jsonb;
  decision_result jsonb;
  listed jsonb;
begin
  delete from public.users where id in (owner_id,other_owner_id);
  if exists (
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.users'::pg_catalog.regclass
      and attname='registration_environment' and attnum>0 and not attisdropped
  ) then
    insert into public.users(
      id,email,password_hash,is_verified,is_guest,created_at,updated_at,
      registration_environment,registration_submitted_at,
      password_setup_required,password_inbox_bound_at
    ) values
      (owner_id,'schedule-approval-owner@example.test',
       '$argon2id$schedule-approval-owner-v1',true,false,
       now_at-interval '1 minute',now_at-interval '1 minute',
       'production',now_at,false,now_at),
      (other_owner_id,'schedule-approval-other@example.test',
       '$argon2id$schedule-approval-other-v1',true,false,
       now_at-interval '1 minute',now_at-interval '1 minute',
       'production',now_at,false,now_at);
  else
    insert into public.users(id) values(owner_id),(other_owner_id);
  end if;
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(
    connection_id,owner_id,'google','mail','personal',
    '88400000-0000-4000-8000-000000000011',1,'active',authorization_sha,
    array['mail.send'],actions_sha,scopes_sha,repeat('9',64),
    '88400000-0000-4000-8000-000000000012',repeat('a',64),
    now_at+interval '1 day',now_at
  );
  insert into connected_schedule_private.templates(
    template_id,schedule_id,owner_id,turn_id,connection_id,task_id,
    plan_payload_id,plan_reference_binding_sha256,provider,resource,action,
    authorization_revision,authorization_snapshot_sha256,
    granted_actions_sha256,granted_scopes_sha256,commitment_key_id,
    parameters_sha256,resource_version_sha256,reference_binding_sha256,
    key_id,wrapped_key_nonce,wrapped_key_ciphertext,payload_nonce,
    payload_ciphertext,record_binding_sha256,created_at,updated_at
  ) values(
    template_id,schedule_id,owner_id,turn_id,connection_id,task_id,
    '88400000-0000-4000-8000-000000000013',repeat('b',64),
    'google','mail','mail.send',1,authorization_sha,actions_sha,scopes_sha,
    'schedule-approval-commitment',parameters_sha,null,repeat('c',64),
    'schedule-approval-key',repeat('A',16),repeat('B',64),repeat('C',16),
    repeat('D',32),repeat('d',64),now_at,now_at
  );
  insert into connected_app_private.schedules(
    schedule_id,owner_id,connection_id,task_id,provider,resource,action,
    action_template_ref,parameters_sha256,task_state_revision,time_zone,
    cadence_seconds,requires_approval_every_run,status,next_run_at,
    created_at,updated_at
  ) values(
    schedule_id,owner_id,connection_id,task_id,'google','mail','mail.send',
    template_id,parameters_sha,1,'UTC',300,true,'active',
    now_at-interval '1 second',now_at,now_at
  );

  claim_result := public.connected_app_claim_schedule_v3(
    claim_a,occurrence_id,action_id,approval_id,120
  );
  if claim_result->>'occurrence_id'<>occurrence_id::text
     or claim_result->>'occurrence_action_id'<>action_id::text
     or claim_result->>'occurrence_approval_id'<>approval_id::text then
    raise exception 'fresh occurrence identities were not exact: %',claim_result;
  end if;
  occurrence_created := (claim_result->>'occurrence_created_at')::timestamptz;
  approval_expires := occurrence_created+interval '10 minutes';
  put_result := public.connected_app_put_schedule_approval_v1(
    occurrence_id,schedule_id,owner_id,claim_a,approval_id,action_id,task_id,
    turn_id,connection_id,'google','mail','mail.send',1,authorization_sha,
    scopes_sha,'connected-app-policy-v1',1,'external_communication',
    approval_binding_sha,parameters_sha,null,preview_sha,preview_id,
    preview_reference_sha,occurrence_created,approval_expires
  );
  replay_result := public.connected_app_put_schedule_approval_v1(
    occurrence_id,schedule_id,owner_id,claim_a,approval_id,action_id,task_id,
    turn_id,connection_id,'google','mail','mail.send',1,authorization_sha,
    scopes_sha,'connected-app-policy-v1',1,'external_communication',
    approval_binding_sha,parameters_sha,null,preview_sha,preview_id,
    preview_reference_sha,occurrence_created,approval_expires
  );
  if replay_result is distinct from put_result
     or put_result->>'status'<>'pending'
     or public.connected_app_read_schedule_approval_v1(owner_id,occurrence_id)
        is distinct from put_result
     or public.connected_app_read_schedule_approval_v1(other_owner_id,occurrence_id)
        is not null then
    raise exception 'pending approval response-loss or owner readback failed';
  end if;
  listed := public.connected_app_operator_list_approvals_v1(owner_id);
  if pg_catalog.jsonb_array_length(listed)<>1
     or listed->0->>'approval_id'<>approval_id::text
     or listed->0->>'status'<>'pending'
     or public.connected_app_operator_get_action_v1(owner_id,action_id)
        ->>'status'<>'pending_approval' then
    raise exception 'existing authenticated UI projection missed scheduled approval: %',listed;
  end if;

  finished_at := pg_catalog.clock_timestamp();
  perform public.connected_app_finish_schedule_v3(
    completion_a,schedule_id,owner_id,claim_a,1,'waiting_approval',null,
    finished_at+interval '60 seconds',finished_at,occurrence_id
  );
  if exists(
    select 1 from connected_schedule_private.occurrences as occurrence
    where occurrence.occurrence_id=schedule_approval_test.occurrence_id
      and (occurrence.terminal_at is not null
        or occurrence.current_claim_id is not null)
  ) then
    raise exception 'waiting completion did not preserve an unclaimed occurrence';
  end if;

  decision_result := public.connected_app_operator_decide_approval_v1(
    decision_id,owner_id,session_sha,approval_id,action_id,connection_id,
    task_id,turn_id,'google','mail','mail.send',1,authorization_sha,scopes_sha,
    'connected-app-policy-v1',1,approval_binding_sha,parameters_sha,null,
    preview_sha,'approved',pg_catalog.clock_timestamp()
  );
  replay_result := public.connected_app_operator_decide_approval_v1(
    decision_id,owner_id,session_sha,approval_id,action_id,connection_id,
    task_id,turn_id,'google','mail','mail.send',1,authorization_sha,scopes_sha,
    'connected-app-policy-v1',1,approval_binding_sha,parameters_sha,null,
    preview_sha,'approved',(decision_result->>'decided_at')::timestamptz
  );
  if decision_result->>'status'<>'approved'
     or replay_result is distinct from decision_result then
    raise exception 'owner approval decision or response-loss replay failed';
  end if;

  update connected_app_private.schedules as schedule
  set next_run_at=pg_catalog.clock_timestamp()-interval '1 second'
  where schedule.schedule_id=schedule_approval_test.schedule_id;
  claim_result := public.connected_app_claim_schedule_v3(
    claim_b,'88400000-0000-4000-8000-000000000014',
    '88400000-0000-4000-8000-000000000015',
    '88400000-0000-4000-8000-000000000016',120
  );
  if claim_result->>'occurrence_id'<>occurrence_id::text
     or claim_result->>'occurrence_action_id'<>action_id::text
     or claim_result->>'occurrence_approval_id'<>approval_id::text
     or claim_result->>'occurrence_created_at'<>put_result->>'occurrence_created_at' then
    raise exception 'approval between leases did not retain exact occurrence: %',claim_result;
  end if;

  begin
    finished_at := pg_catalog.clock_timestamp();
    perform public.connected_app_finish_schedule_v3(
      completion_b,schedule_id,owner_id,claim_b,1,'succeeded',action_id,
      finished_at+interval '60 seconds',finished_at,occurrence_id
    );
    raise exception 'unconsumed approval unexpectedly authorized successful finish';
  exception when sqlstate '55000' then
    if sqlerrm<>'schedule occurrence completion lacks consumed approval' then
      raise;
    end if;
  end;

  delete from public.users where id in (owner_id,other_owner_id);
  if exists(select 1 from connected_schedule_private.occurrences as occurrence
            where occurrence.owner_id in (
              schedule_approval_test.owner_id,schedule_approval_test.other_owner_id))
     or exists(select 1 from connected_app_private.approval_reviews as review
               where review.owner_id in (
                 schedule_approval_test.owner_id,schedule_approval_test.other_owner_id)) then
    raise exception 'account deletion left schedule approval state';
  end if;
end;
$test$;

do $acl$
begin
  if not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_read_schedule_approval_v1(uuid,uuid)','EXECUTE')
     or pg_catalog.has_function_privilege(
       'authenticated',
       'public.connected_app_read_schedule_approval_v1(uuid,uuid)','EXECUTE')
     or pg_catalog.has_table_privilege(
       'service_role','connected_schedule_private.occurrences','SELECT') then
    raise exception 'schedule occurrence approval ACL boundary failed';
  end if;
end;
$acl$;

select 'CONNECTED_SCHEDULE_OCCURRENCE_APPROVAL_OK' as result;
