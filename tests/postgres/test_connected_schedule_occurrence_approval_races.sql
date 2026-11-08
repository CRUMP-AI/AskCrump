\set ON_ERROR_STOP on

create or replace function public.connected_schedule_test_seed_v1(
  p_owner_id uuid,p_connection_id uuid,p_template_id uuid,p_schedule_id uuid,
  p_task_id uuid,p_turn_id uuid,p_claim_id uuid,p_occurrence_id uuid,
  p_action_id uuid,p_approval_id uuid,p_preview_id uuid
) returns jsonb language plpgsql set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  claimed jsonb;
  occurrence_created timestamptz;
begin
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(
    p_owner_id,p_owner_id::text||'@schedule-race.example.test',
    '$argon2id$schedule-approval-race-v1',true,false,
    now_at-interval '1 minute',now_at-interval '1 minute',
    'production',now_at,false,now_at
  );
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(
    p_connection_id,p_owner_id,'google','mail','personal',
    pg_catalog.gen_random_uuid(),1,'active',repeat('1',64),
    array['mail.send'],repeat('2',64),repeat('3',64),repeat('9',64),
    pg_catalog.gen_random_uuid(),repeat('a',64),now_at+interval '1 day',now_at
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
    p_template_id,p_schedule_id,p_owner_id,p_turn_id,p_connection_id,p_task_id,
    pg_catalog.gen_random_uuid(),repeat('b',64),'google','mail','mail.send',
    1,repeat('1',64),repeat('2',64),repeat('3',64),'race-commitment',
    repeat('4',64),null,pg_catalog.md5(p_schedule_id::text)||repeat('c',32),
    'race-key',repeat('A',16),repeat('B',64),repeat('C',16),repeat('D',32),
    pg_catalog.md5(p_template_id::text)||repeat('d',32),now_at,now_at
  );
  insert into connected_app_private.schedules(
    schedule_id,owner_id,connection_id,task_id,provider,resource,action,
    action_template_ref,parameters_sha256,task_state_revision,time_zone,
    cadence_seconds,requires_approval_every_run,status,next_run_at,
    created_at,updated_at
  ) values(
    p_schedule_id,p_owner_id,p_connection_id,p_task_id,'google','mail','mail.send',
    p_template_id,repeat('4',64),1,'UTC',300,true,'active',
    now_at-interval '1 second',now_at,now_at
  );
  claimed:=public.connected_app_claim_schedule_v3(
    p_claim_id,p_occurrence_id,p_action_id,p_approval_id,120
  );
  occurrence_created:=(claimed->>'occurrence_created_at')::timestamptz;
  perform public.connected_app_put_schedule_approval_v1(
    p_occurrence_id,p_schedule_id,p_owner_id,p_claim_id,p_approval_id,
    p_action_id,p_task_id,p_turn_id,p_connection_id,'google','mail','mail.send',
    1,repeat('1',64),repeat('3',64),'connected-app-policy-v1',1,
    'external_communication',
    pg_catalog.md5(p_owner_id::text)||
      pg_catalog.md5(p_owner_id::text||':approval'),
    repeat('4',64),null,repeat('6',64),
    p_preview_id,repeat('7',64),occurrence_created,
    occurrence_created+interval '10 minutes'
  );
  return claimed;
end;
$fn$;

create or replace function public.connected_schedule_test_decide_v1(
  p_owner_id uuid,p_connection_id uuid,p_task_id uuid,p_turn_id uuid,
  p_action_id uuid,p_approval_id uuid,p_delay_seconds numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  begin
    result:=public.connected_app_operator_decide_approval_v1(
      pg_catalog.gen_random_uuid(),p_owner_id,repeat('8',64),p_approval_id,
      p_action_id,p_connection_id,p_task_id,p_turn_id,'google','mail','mail.send',
      1,repeat('1',64),repeat('3',64),'connected-app-policy-v1',1,
      pg_catalog.md5(p_owner_id::text)||
        pg_catalog.md5(p_owner_id::text||':approval'),
      repeat('4',64),null,repeat('6',64),'approved',
      pg_catalog.clock_timestamp()
    );
    perform pg_catalog.pg_sleep(p_delay_seconds);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
  end;
end;
$fn$;

create or replace function public.connected_schedule_test_cancel_v1(
  p_request_id uuid,p_owner_id uuid,p_schedule_id uuid,p_delay_seconds numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  begin
    result:=public.connected_app_operator_transition_schedule_v1(
      p_request_id,p_owner_id,repeat('8',64),repeat('9',64),p_schedule_id,
      1,'active','cancelled',pg_catalog.clock_timestamp()
    );
    perform pg_catalog.pg_sleep(p_delay_seconds);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
  end;
end;
$fn$;

create or replace function public.connected_schedule_test_wait_v1(
  p_completion_id uuid,p_owner_id uuid,p_schedule_id uuid,p_claim_id uuid,
  p_occurrence_id uuid,p_delay_seconds numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare
  result jsonb;
  finished_at timestamptz:=pg_catalog.clock_timestamp();
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  begin
    result:=public.connected_app_finish_schedule_v3(
      p_completion_id,p_schedule_id,p_owner_id,p_claim_id,1,
      'waiting_approval',null,finished_at+interval '60 seconds',finished_at,
      p_occurrence_id
    );
    perform pg_catalog.pg_sleep(p_delay_seconds);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
  end;
end;
$fn$;

-- Seed four independent owners.  The first two have their claim released for
-- decision-vs-cancel races.  The latter two retain it for decision-vs-lease
-- release races.
select public.connected_schedule_test_seed_v1(
  '88510000-0000-4000-8000-000000000001','88510000-0000-4000-8000-000000000002',
  '88510000-0000-4000-8000-000000000003','88510000-0000-4000-8000-000000000004',
  '88510000-0000-4000-8000-000000000005','88510000-0000-4000-8000-000000000006',
  '88510000-0000-4000-8000-000000000007','88510000-0000-4000-8000-000000000008',
  '88510000-0000-4000-8000-000000000009','88510000-0000-4000-8000-00000000000a',
  '88510000-0000-4000-8000-00000000000b');
select public.connected_schedule_test_seed_v1(
  '88520000-0000-4000-8000-000000000001','88520000-0000-4000-8000-000000000002',
  '88520000-0000-4000-8000-000000000003','88520000-0000-4000-8000-000000000004',
  '88520000-0000-4000-8000-000000000005','88520000-0000-4000-8000-000000000006',
  '88520000-0000-4000-8000-000000000007','88520000-0000-4000-8000-000000000008',
  '88520000-0000-4000-8000-000000000009','88520000-0000-4000-8000-00000000000a',
  '88520000-0000-4000-8000-00000000000b');
select public.connected_schedule_test_seed_v1(
  '88530000-0000-4000-8000-000000000001','88530000-0000-4000-8000-000000000002',
  '88530000-0000-4000-8000-000000000003','88530000-0000-4000-8000-000000000004',
  '88530000-0000-4000-8000-000000000005','88530000-0000-4000-8000-000000000006',
  '88530000-0000-4000-8000-000000000007','88530000-0000-4000-8000-000000000008',
  '88530000-0000-4000-8000-000000000009','88530000-0000-4000-8000-00000000000a',
  '88530000-0000-4000-8000-00000000000b');
select public.connected_schedule_test_seed_v1(
  '88540000-0000-4000-8000-000000000001','88540000-0000-4000-8000-000000000002',
  '88540000-0000-4000-8000-000000000003','88540000-0000-4000-8000-000000000004',
  '88540000-0000-4000-8000-000000000005','88540000-0000-4000-8000-000000000006',
  '88540000-0000-4000-8000-000000000007','88540000-0000-4000-8000-000000000008',
  '88540000-0000-4000-8000-000000000009','88540000-0000-4000-8000-00000000000a',
  '88540000-0000-4000-8000-00000000000b');

do $release_cancel_claims$
declare finished_at timestamptz;
begin
  finished_at:=pg_catalog.clock_timestamp();
  perform public.connected_app_finish_schedule_v3(
    '88510000-0000-4000-8000-00000000000c',
    '88510000-0000-4000-8000-000000000004',
    '88510000-0000-4000-8000-000000000001',
    '88510000-0000-4000-8000-000000000007',1,'waiting_approval',null,
    finished_at+interval '60 seconds',finished_at,
    '88510000-0000-4000-8000-000000000008');
  finished_at:=pg_catalog.clock_timestamp();
  perform public.connected_app_finish_schedule_v3(
    '88520000-0000-4000-8000-00000000000c',
    '88520000-0000-4000-8000-000000000004',
    '88520000-0000-4000-8000-000000000001',
    '88520000-0000-4000-8000-000000000007',1,'waiting_approval',null,
    finished_at+interval '60 seconds',finished_at,
    '88520000-0000-4000-8000-000000000008');
end;
$release_cancel_claims$;

create temporary table connected_schedule_approval_race_results(
  lane text primary key,value jsonb not null
) on commit preserve rows;

select public.dblink_connect('schedule_approval_a',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'schedule-approval-race-a'));
select public.dblink_connect('schedule_approval_b',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'schedule-approval-race-b'));

-- Approval owns the canonical owner lock first; cancellation follows and
-- terminalizes the occurrence before any scheduler can consume it.
select public.dblink_send_query('schedule_approval_a',$q$
  select public.connected_schedule_test_decide_v1(
    '88510000-0000-4000-8000-000000000001','88510000-0000-4000-8000-000000000002',
    '88510000-0000-4000-8000-000000000005','88510000-0000-4000-8000-000000000006',
    '88510000-0000-4000-8000-000000000009','88510000-0000-4000-8000-00000000000a',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('schedule_approval_b',$q$
  select public.connected_schedule_test_cancel_v1(
    '88510000-0000-4000-8000-00000000000d','88510000-0000-4000-8000-000000000001',
    '88510000-0000-4000-8000-000000000004',0)::text
$q$);
insert into connected_schedule_approval_race_results select 'approve-first',result::jsonb
from public.dblink_get_result('schedule_approval_a') as remote(result text);
insert into connected_schedule_approval_race_results select 'cancel-second',result::jsonb
from public.dblink_get_result('schedule_approval_b') as remote(result text);
-- libpq exposes a final empty result after the row-bearing result.  Drain it
-- before reusing either named asynchronous connection.
select * from public.dblink_get_result('schedule_approval_a') as remote(result text);
select * from public.dblink_get_result('schedule_approval_b') as remote(result text);

-- Cancellation owns the lock first; the later approval is refused because
-- the trigger has already terminalized the occurrence.
select public.dblink_send_query('schedule_approval_a',$q$
  select public.connected_schedule_test_cancel_v1(
    '88520000-0000-4000-8000-00000000000d','88520000-0000-4000-8000-000000000001',
    '88520000-0000-4000-8000-000000000004',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('schedule_approval_b',$q$
  select public.connected_schedule_test_decide_v1(
    '88520000-0000-4000-8000-000000000001','88520000-0000-4000-8000-000000000002',
    '88520000-0000-4000-8000-000000000005','88520000-0000-4000-8000-000000000006',
    '88520000-0000-4000-8000-000000000009','88520000-0000-4000-8000-00000000000a',0)::text
$q$);
insert into connected_schedule_approval_race_results select 'cancel-first',result::jsonb
from public.dblink_get_result('schedule_approval_a') as remote(result text);
insert into connected_schedule_approval_race_results select 'approve-second',result::jsonb
from public.dblink_get_result('schedule_approval_b') as remote(result text);
select * from public.dblink_get_result('schedule_approval_a') as remote(result text);
select * from public.dblink_get_result('schedule_approval_b') as remote(result text);

-- Approval then waiting-finish: both succeed; the exact approved occurrence
-- remains open and unclaimed for the next bounded worker lease.
select public.dblink_send_query('schedule_approval_a',$q$
  select public.connected_schedule_test_decide_v1(
    '88530000-0000-4000-8000-000000000001','88530000-0000-4000-8000-000000000002',
    '88530000-0000-4000-8000-000000000005','88530000-0000-4000-8000-000000000006',
    '88530000-0000-4000-8000-000000000009','88530000-0000-4000-8000-00000000000a',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('schedule_approval_b',$q$
  select public.connected_schedule_test_wait_v1(
    '88530000-0000-4000-8000-00000000000c','88530000-0000-4000-8000-000000000001',
    '88530000-0000-4000-8000-000000000004','88530000-0000-4000-8000-000000000007',
    '88530000-0000-4000-8000-000000000008',0)::text
$q$);
insert into connected_schedule_approval_race_results select 'approve-before-lease',result::jsonb
from public.dblink_get_result('schedule_approval_a') as remote(result text);
insert into connected_schedule_approval_race_results select 'lease-after-approve',result::jsonb
from public.dblink_get_result('schedule_approval_b') as remote(result text);
select * from public.dblink_get_result('schedule_approval_a') as remote(result text);
select * from public.dblink_get_result('schedule_approval_b') as remote(result text);

-- Waiting-finish then approval: releasing a short lease never invalidates the
-- durable occurrence, so the owner can still approve that exact occurrence.
select public.dblink_send_query('schedule_approval_a',$q$
  select public.connected_schedule_test_wait_v1(
    '88540000-0000-4000-8000-00000000000c','88540000-0000-4000-8000-000000000001',
    '88540000-0000-4000-8000-000000000004','88540000-0000-4000-8000-000000000007',
    '88540000-0000-4000-8000-000000000008',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('schedule_approval_b',$q$
  select public.connected_schedule_test_decide_v1(
    '88540000-0000-4000-8000-000000000001','88540000-0000-4000-8000-000000000002',
    '88540000-0000-4000-8000-000000000005','88540000-0000-4000-8000-000000000006',
    '88540000-0000-4000-8000-000000000009','88540000-0000-4000-8000-00000000000a',0)::text
$q$);
insert into connected_schedule_approval_race_results select 'lease-before-approve',result::jsonb
from public.dblink_get_result('schedule_approval_a') as remote(result text);
insert into connected_schedule_approval_race_results select 'approve-after-lease',result::jsonb
from public.dblink_get_result('schedule_approval_b') as remote(result text);
select * from public.dblink_get_result('schedule_approval_a') as remote(result text);
select * from public.dblink_get_result('schedule_approval_b') as remote(result text);

do $check$
begin
  if exists(
    select 1 from connected_schedule_approval_race_results
    where lane<>'approve-second' and value->>'ok'<>'true'
  ) or (select value->>'sqlstate' from connected_schedule_approval_race_results
        where lane='approve-second')<>'55000' then
    raise exception 'approval/cancel/lease winner results were not exact: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_schedule_approval_race_results);
  end if;
  if not exists(
       select 1 from connected_schedule_private.occurrences as occurrence
       join connected_app_private.approval_reviews as review
         on review.approval_id=occurrence.approval_id
       where occurrence.owner_id='88510000-0000-4000-8000-000000000001'
         and occurrence.status='cancelled' and occurrence.terminal_at is not null
         and review.status='approved')
     or not exists(
       select 1 from connected_schedule_private.occurrences as occurrence
       join connected_app_private.approval_reviews as review
         on review.approval_id=occurrence.approval_id
       where occurrence.owner_id='88520000-0000-4000-8000-000000000001'
         and occurrence.status='cancelled' and occurrence.terminal_at is not null
         and review.status='pending'
         and not exists(select 1 from connected_app_private.approvals as approval
           where approval.approval_id=occurrence.approval_id)) then
    raise exception 'approval-vs-cancel final state violated the terminal fence';
  end if;
  if (select count(*) from connected_schedule_private.occurrences as occurrence
      join connected_app_private.approval_reviews as review
        on review.approval_id=occurrence.approval_id
      where occurrence.owner_id in (
        '88530000-0000-4000-8000-000000000001',
        '88540000-0000-4000-8000-000000000001')
        and occurrence.status='pending_approval'
        and occurrence.terminal_at is null
        and occurrence.current_claim_id is null
        and review.status='approved')<>2 then
    raise exception 'approval-vs-lease final state lost an approved occurrence';
  end if;
end;
$check$;

select public.dblink_disconnect('schedule_approval_a');
select public.dblink_disconnect('schedule_approval_b');
delete from public.users where id in (
  '88510000-0000-4000-8000-000000000001',
  '88520000-0000-4000-8000-000000000001',
  '88530000-0000-4000-8000-000000000001',
  '88540000-0000-4000-8000-000000000001');
drop function public.connected_schedule_test_seed_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid);
drop function public.connected_schedule_test_decide_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,numeric);
drop function public.connected_schedule_test_cancel_v1(uuid,uuid,uuid,numeric);
drop function public.connected_schedule_test_wait_v1(uuid,uuid,uuid,uuid,uuid,numeric);

select 'CONNECTED_SCHEDULE_OCCURRENCE_APPROVAL_RACES_OK' as result;
