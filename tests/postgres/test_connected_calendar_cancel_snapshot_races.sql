\set ON_ERROR_STOP on

create or replace function public.connected_cancel_test_id_v1(p_value text)
returns uuid language sql immutable set search_path='' as $fn$
  select (
    pg_catalog.substr(pg_catalog.md5(p_value),1,8)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),9,4)||'-4'||
    pg_catalog.substr(pg_catalog.md5(p_value),14,3)||'-8'||
    pg_catalog.substr(pg_catalog.md5(p_value),18,3)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),21,12)
  )::uuid
$fn$;

create or replace function public.connected_cancel_test_sha_v1(p_value text)
returns text language sql immutable set search_path='' as $fn$
  select pg_catalog.md5(p_value||':left')||pg_catalog.md5(p_value||':right')
$fn$;

create or replace function public.connected_cancel_test_seed_v1(p_lane text)
returns void language plpgsql set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.date_trunc('second',pg_catalog.clock_timestamp());
  owner_id uuid:=public.connected_cancel_test_id_v1(p_lane||':owner');
  connection_id uuid:=public.connected_cancel_test_id_v1(p_lane||':connection');
  schedule_id uuid:=public.connected_cancel_test_id_v1(p_lane||':schedule');
  template_id uuid:=public.connected_cancel_test_id_v1(p_lane||':template');
  parent_task_id uuid:=public.connected_cancel_test_id_v1(p_lane||':parent-task');
  turn_id uuid:=public.connected_cancel_test_id_v1(p_lane||':turn');
  claim_id uuid:=public.connected_cancel_test_id_v1(p_lane||':claim');
  occurrence_id uuid:=public.connected_cancel_test_id_v1(p_lane||':occurrence');
  authorization_sha constant text:=repeat('1',64);
  actions_sha constant text:=
    'edf4e2f8620ed30b54f928df774457286dc2ef026ce4632e334eb745639ccefd';
  scopes_sha constant text:=repeat('2',64);
  parameters_sha constant text:=repeat('3',64);
  version_sha constant text:=repeat('4',64);
begin
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(owner_id,owner_id::text||'@cancel-race.example.test',
    '$argon2id$cancel-race',true,false,now_at-interval '1 minute',now_at,
    'production',now_at,false,now_at);
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(connection_id,owner_id,'google','calendar','personal',
    public.connected_cancel_test_id_v1(p_lane||':incarnation'),2,'active',
    authorization_sha,array['calendar.cancel','calendar.get'],actions_sha,
    scopes_sha,repeat('8',64),
    public.connected_cancel_test_id_v1(p_lane||':credential'),repeat('9',64),
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
    public.connected_cancel_test_id_v1(p_lane||':plan'),
    public.connected_cancel_test_sha_v1(p_lane||':plan-reference'),
    'google','calendar','calendar.cancel',2,authorization_sha,actions_sha,
    scopes_sha,'cancel-race-commitment',parameters_sha,version_sha,
    public.connected_cancel_test_sha_v1(p_lane||':reference'),
    'cancel-race-envelope',repeat('A',16),repeat('B',64),
    repeat('C',16),repeat('D',64),
    public.connected_cancel_test_sha_v1(p_lane||':record-binding'),
    'live',now_at,now_at);
  insert into connected_app_private.schedules(
    schedule_id,owner_id,connection_id,task_id,provider,resource,action,
    action_template_ref,parameters_sha256,task_state_revision,time_zone,
    cadence_seconds,requires_approval_every_run,status,next_run_at,
    claim_id,claim_expires_at,created_at,updated_at
  ) values(schedule_id,owner_id,connection_id,parent_task_id,'google','calendar',
    'calendar.cancel',template_id,parameters_sha,3,'UTC',3600,true,'active',
    now_at-interval '1 minute',claim_id,now_at+interval '3 minutes',
    now_at-interval '1 day',now_at);
  insert into connected_app_private.task_grants(
    grant_id,owner_id,task_id,turn_id,connection_id,provider,resource,
    authorization_revision,authorization_snapshot_sha256,actions,
    actions_sha256,task_state_revision,expires_at
  ) values(claim_id,owner_id,parent_task_id,turn_id,connection_id,'google',
    'calendar',2,authorization_sha,array['calendar.cancel'],
    '9114e5237c49ef53d3bc53bb651bc65517220385e42e34cd7b47e14ac02411e3',
    3,now_at+interval '3 minutes');
  insert into connected_schedule_private.occurrences(
    occurrence_id,schedule_id,owner_id,action_id,approval_id,task_id,turn_id,
    connection_id,provider,resource,action,authorization_revision,
    authorization_snapshot_sha256,granted_scopes_sha256,task_state_revision,
    parameters_sha256,resource_version_sha256,scheduled_for,
    occurrence_created_at,current_claim_id,status,updated_at
  ) values(occurrence_id,schedule_id,owner_id,
    public.connected_cancel_test_id_v1(p_lane||':parent-action'),
    public.connected_cancel_test_id_v1(p_lane||':parent-approval'),
    parent_task_id,turn_id,connection_id,'google','calendar','calendar.cancel',
    2,authorization_sha,scopes_sha,3,parameters_sha,version_sha,
    now_at-interval '1 minute',now_at,claim_id,'pending_approval',now_at);
end;
$fn$;

create or replace function public.connected_cancel_test_prepare_v1(
  p_lane text,p_delay_seconds numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare requested_at timestamptz; result jsonb;
begin
  select schedule.updated_at into strict requested_at
  from connected_app_private.schedules as schedule
  where schedule.schedule_id=public.connected_cancel_test_id_v1(p_lane||':schedule');
  begin
    result:=public.connected_app_prepare_cancel_snapshot_schedule_v1(
      public.connected_cancel_test_id_v1(p_lane||':owner'),
      public.connected_cancel_test_id_v1(p_lane||':schedule'),
      public.connected_cancel_test_id_v1(p_lane||':claim'),
      public.connected_cancel_test_id_v1(p_lane||':occurrence'),
      public.connected_cancel_test_id_v1(p_lane||':turn'),
      public.connected_cancel_test_id_v1(p_lane||':request'),
      public.connected_cancel_test_id_v1(p_lane||':session'),
      public.connected_cancel_test_sha_v1(p_lane||':session-binding'),
      public.connected_cancel_test_sha_v1(p_lane||':command-binding'),
      public.connected_cancel_test_id_v1(p_lane||':child-grant'),
      public.connected_cancel_test_id_v1(p_lane||':child-action'),
      public.connected_cancel_test_id_v1(p_lane||':child-task'),
      public.connected_cancel_test_id_v1(p_lane||':connection'),
      'google','calendar','calendar.get',2,repeat('1',64),
      'edf4e2f8620ed30b54f928df774457286dc2ef026ce4632e334eb745639ccefd',
      repeat('2',64),3,public.connected_cancel_test_id_v1(p_lane||':payload'),
      public.connected_cancel_test_sha_v1(p_lane||':payload-reference'),
      public.connected_cancel_test_sha_v1(p_lane||':parameters'),repeat('4',64),
      'connected-app-policy-v1',requested_at,requested_at+interval '90 seconds');
    perform pg_catalog.pg_sleep(p_delay_seconds);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
  end;
end;
$fn$;

create or replace function public.connected_cancel_test_begin_v1(
  p_lane text,p_delay_seconds numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  begin
    result:=public.connected_app_begin_cancel_snapshot_schedule_v1(
      public.connected_cancel_test_id_v1(p_lane||':owner'),
      public.connected_cancel_test_id_v1(p_lane||':schedule'),
      public.connected_cancel_test_id_v1(p_lane||':claim'),
      public.connected_cancel_test_id_v1(p_lane||':occurrence'),
      public.connected_cancel_test_id_v1(p_lane||':turn'),
      public.connected_cancel_test_id_v1(p_lane||':request'),
      public.connected_cancel_test_id_v1(p_lane||':child-action'),
      public.connected_cancel_test_sha_v1(p_lane||':command-binding'));
    perform pg_catalog.pg_sleep(p_delay_seconds);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
  end;
end;
$fn$;

create or replace function public.connected_cancel_test_release_v1(
  p_lane text,p_delay_seconds numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare v_owner_id uuid:=public.connected_cancel_test_id_v1(p_lane||':owner');
begin
  perform connected_app_private.owner_lock_v1(v_owner_id);
  update connected_app_private.schedules as schedule
  set claim_id=null,claim_expires_at=null,updated_at=pg_catalog.clock_timestamp()
  where schedule.schedule_id=public.connected_cancel_test_id_v1(p_lane||':schedule')
    and schedule.owner_id=v_owner_id;
  update connected_schedule_private.occurrences as occurrence
  set current_claim_id=null,updated_at=pg_catalog.clock_timestamp()
  where occurrence.occurrence_id=
      public.connected_cancel_test_id_v1(p_lane||':occurrence')
    and occurrence.owner_id=v_owner_id;
  perform pg_catalog.pg_sleep(p_delay_seconds);
  return pg_catalog.jsonb_build_object('ok',true);
exception when others then
  return pg_catalog.jsonb_build_object(
    'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
end;
$fn$;

select public.connected_cancel_test_seed_v1('prepare');
select public.connected_cancel_test_seed_v1('begin-first');
select public.connected_cancel_test_seed_v1('release-first');
select public.connected_cancel_test_prepare_v1('begin-first',0);
select public.connected_cancel_test_prepare_v1('release-first',0);

create temporary table connected_cancel_race_results(
  lane text primary key,value jsonb not null
) on commit preserve rows;
select public.dblink_connect('cancel_snapshot_a',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'cancel-snapshot-race-a'));
select public.dblink_connect('cancel_snapshot_b',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'cancel-snapshot-race-b'));

-- Exact concurrent preparation converges to one response-loss-safe child read.
select public.dblink_send_query('cancel_snapshot_a',$q$
  select public.connected_cancel_test_prepare_v1('prepare',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('cancel_snapshot_b',$q$
  select public.connected_cancel_test_prepare_v1('prepare',0)::text
$q$);
insert into connected_cancel_race_results select 'prepare-first',result::jsonb
from public.dblink_get_result('cancel_snapshot_a') as remote(result text);
insert into connected_cancel_race_results select 'prepare-replay',result::jsonb
from public.dblink_get_result('cancel_snapshot_b') as remote(result text);
select * from public.dblink_get_result('cancel_snapshot_a') as remote(result text);
select * from public.dblink_get_result('cancel_snapshot_b') as remote(result text);

-- Begin owns the owner fence first; claim release serializes after it.
select public.dblink_send_query('cancel_snapshot_a',$q$
  select public.connected_cancel_test_begin_v1('begin-first',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('cancel_snapshot_b',$q$
  select public.connected_cancel_test_release_v1('begin-first',0)::text
$q$);
insert into connected_cancel_race_results select 'begin-winner',result::jsonb
from public.dblink_get_result('cancel_snapshot_a') as remote(result text);
insert into connected_cancel_race_results select 'release-loser',result::jsonb
from public.dblink_get_result('cancel_snapshot_b') as remote(result text);
select * from public.dblink_get_result('cancel_snapshot_a') as remote(result text);
select * from public.dblink_get_result('cancel_snapshot_b') as remote(result text);

-- Claim release owns the fence first; the provider-read start fails closed.
select public.dblink_send_query('cancel_snapshot_a',$q$
  select public.connected_cancel_test_release_v1('release-first',1)::text
$q$);
select pg_catalog.pg_sleep(0.2);
select public.dblink_send_query('cancel_snapshot_b',$q$
  select public.connected_cancel_test_begin_v1('release-first',0)::text
$q$);
insert into connected_cancel_race_results select 'release-winner',result::jsonb
from public.dblink_get_result('cancel_snapshot_a') as remote(result text);
insert into connected_cancel_race_results select 'begin-loser',result::jsonb
from public.dblink_get_result('cancel_snapshot_b') as remote(result text);
select * from public.dblink_get_result('cancel_snapshot_a') as remote(result text);
select * from public.dblink_get_result('cancel_snapshot_b') as remote(result text);

do $assertions$
declare first_value jsonb; replay_value jsonb;
begin
  select value into first_value from connected_cancel_race_results
  where lane='prepare-first';
  select value into replay_value from connected_cancel_race_results
  where lane='prepare-replay';
  if first_value->>'ok'<>'true' or replay_value->>'ok'<>'true'
     or first_value->'value' is distinct from replay_value->'value'
     or (select count(*) from connected_cancel_private.snapshot_reads
         where owner_id=public.connected_cancel_test_id_v1('prepare:owner'))<>1
     or (select count(*) from connected_app_private.action_preparations
         where owner_id=public.connected_cancel_test_id_v1('prepare:owner'))<>1 then
    raise exception 'concurrent cancellation snapshot replay did not converge';
  end if;
  if (select value->>'ok' from connected_cancel_race_results
      where lane='begin-winner')<>'true'
     or (select value->>'ok' from connected_cancel_race_results
         where lane='release-loser')<>'true'
     or not exists(select 1 from connected_cancel_private.snapshot_reads
       where owner_id=public.connected_cancel_test_id_v1('begin-first:owner')
         and status='started') then
    raise exception 'begin-first cancellation snapshot race failed: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_cancel_race_results
       where lane in ('begin-winner','release-loser'));
  end if;
  if (select value->>'ok' from connected_cancel_race_results
      where lane='release-winner')<>'true'
     or (select value->>'ok' from connected_cancel_race_results
         where lane='begin-loser')<>'false'
     or (select value->>'sqlstate' from connected_cancel_race_results
         where lane='begin-loser')<>'55000'
     or not exists(select 1 from connected_cancel_private.snapshot_reads
       where owner_id=public.connected_cancel_test_id_v1('release-first:owner')
         and status='prepared') then
    raise exception 'claim-loss-first cancellation snapshot race failed: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_cancel_race_results
       where lane in ('release-winner','begin-loser'));
  end if;
end;
$assertions$;

select public.dblink_disconnect('cancel_snapshot_a');
select public.dblink_disconnect('cancel_snapshot_b');
select 'CONNECTED_CALENDAR_CANCEL_SNAPSHOT_RACES_OK' as result;
