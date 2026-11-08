\set ON_ERROR_STOP on

create or replace function public.connected_loop_test_seed_v1(
  p_owner_id uuid,p_session_id uuid,p_chat_id uuid,p_message_id uuid,p_loop_id uuid
) returns jsonb language plpgsql set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  turn_id uuid;
  turn_claim uuid;
begin
  delete from public.users where id=p_owner_id;
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(
    p_owner_id,p_owner_id::text||'@loop-race.example.test',
    '$argon2id$connected-loop-race-v1',true,false,
    now_at-interval '1 minute',now_at-interval '1 minute',
    'production',now_at,false,now_at
  );
  insert into public.sessions(
    id,user_id,token_hash,device_id,device_name,platform,device_info,
    created_at,last_activity,expires_at
  ) values(
    p_session_id,p_owner_id,
    pg_catalog.md5(p_session_id::text)||pg_catalog.md5(p_session_id::text||':token'),
    p_session_id::text,
    'Connected loop race','web','{}'::jsonb,now_at,now_at,now_at+interval '1 day'
  );
  select claim.turn_id,claim.claim_token into strict turn_id,turn_claim
  from public.connected_chat_claim_turn_v1(
    p_owner_id,p_chat_id,p_message_id,repeat('a',64),repeat('b',64)) as claim;
  return public.connected_multi_step_start_v1(
    p_loop_id,p_owner_id,p_session_id,repeat('a',64),p_chat_id,p_message_id,
    turn_id,turn_claim,'UTC',repeat('b',64),now_at,now_at+interval '20 minutes',8);
end;
$fn$;

create or replace function public.connected_loop_test_claim_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_expected_revision bigint,
  p_wake_id uuid,p_claim_token uuid,p_delay_seconds numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  begin
    result:=public.connected_multi_step_claim_v1(
      p_owner_id,p_loop_id,p_step_id,p_expected_revision,p_wake_id,p_claim_token,
      repeat('c',64),pg_catalog.clock_timestamp(),30);
    perform pg_catalog.pg_sleep(p_delay_seconds);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
  end;
end;
$fn$;

create or replace function public.connected_loop_test_stop_v1(
  p_owner_id uuid,p_loop_id uuid,p_expected_revision bigint,p_delay_seconds numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare
  result jsonb;
begin
  begin
    result:=public.connected_multi_step_cancel_owner_v1(
      p_owner_id,p_loop_id,p_expected_revision,pg_catalog.clock_timestamp());
    perform pg_catalog.pg_sleep(p_delay_seconds);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
  end;
end;
$fn$;

select public.connected_loop_test_seed_v1(
  '97010000-0000-4000-8000-000000000001','97010000-0000-4000-8000-000000000002',
  '97010000-0000-4000-8000-000000000003','97010000-0000-4000-8000-000000000004',
  '97010000-0000-4000-8000-000000000005');
select public.connected_loop_test_seed_v1(
  '97020000-0000-4000-8000-000000000001','97020000-0000-4000-8000-000000000002',
  '97020000-0000-4000-8000-000000000003','97020000-0000-4000-8000-000000000004',
  '97020000-0000-4000-8000-000000000005');
select public.connected_loop_test_seed_v1(
  '97030000-0000-4000-8000-000000000001','97030000-0000-4000-8000-000000000002',
  '97030000-0000-4000-8000-000000000003','97030000-0000-4000-8000-000000000004',
  '97030000-0000-4000-8000-000000000005');

create temporary table connected_loop_race_results(
  lane text primary key,value jsonb not null
) on commit preserve rows;

select public.dblink_connect('connected_loop_a',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'connected-loop-race-a'));
select public.dblink_connect('connected_loop_b',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'connected-loop-race-b'));

-- Two workers race for step zero.  Only the first exact claim may exist.
select public.dblink_send_query('connected_loop_a',$q$
  select public.connected_loop_test_claim_v1(
    '97010000-0000-4000-8000-000000000001','97010000-0000-4000-8000-000000000005',
    '97010000-0000-4000-8000-000000000006',1,
    '97010000-0000-4000-8000-000000000007','97010000-0000-4000-8000-000000000008',
    0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('connected_loop_b',$q$
  select public.connected_loop_test_claim_v1(
    '97010000-0000-4000-8000-000000000001','97010000-0000-4000-8000-000000000005',
    '97010000-0000-4000-8000-000000000009',1,
    '97010000-0000-4000-8000-00000000000a','97010000-0000-4000-8000-00000000000b',
    0)::text
$q$);
insert into connected_loop_race_results select 'worker-a',result::jsonb
from public.dblink_get_result('connected_loop_a') as remote(result text);
insert into connected_loop_race_results select 'worker-b',result::jsonb
from public.dblink_get_result('connected_loop_b') as remote(result text);
select * from public.dblink_get_result('connected_loop_a') as remote(result text);
select * from public.dblink_get_result('connected_loop_b') as remote(result text);

-- Claim owns the owner lock first; a stale cancel revision is refused.
select public.dblink_send_query('connected_loop_a',$q$
  select public.connected_loop_test_claim_v1(
    '97020000-0000-4000-8000-000000000001','97020000-0000-4000-8000-000000000005',
    '97020000-0000-4000-8000-000000000006',1,
    '97020000-0000-4000-8000-000000000007','97020000-0000-4000-8000-000000000008',
    0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('connected_loop_b',$q$
  select public.connected_loop_test_stop_v1(
    '97020000-0000-4000-8000-000000000001','97020000-0000-4000-8000-000000000005',
    1,0)::text
$q$);
insert into connected_loop_race_results select 'claim-first',result::jsonb
from public.dblink_get_result('connected_loop_a') as remote(result text);
insert into connected_loop_race_results select 'cancel-second',result::jsonb
from public.dblink_get_result('connected_loop_b') as remote(result text);
select * from public.dblink_get_result('connected_loop_a') as remote(result text);
select * from public.dblink_get_result('connected_loop_b') as remote(result text);

-- Cancel owns the owner lock first; no step may be admitted afterward.
select public.dblink_send_query('connected_loop_a',$q$
  select public.connected_loop_test_stop_v1(
    '97030000-0000-4000-8000-000000000001','97030000-0000-4000-8000-000000000005',
    1,0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('connected_loop_b',$q$
  select public.connected_loop_test_claim_v1(
    '97030000-0000-4000-8000-000000000001','97030000-0000-4000-8000-000000000005',
    '97030000-0000-4000-8000-000000000006',1,
    '97030000-0000-4000-8000-000000000007','97030000-0000-4000-8000-000000000008',
    0)::text
$q$);
insert into connected_loop_race_results select 'cancel-first',result::jsonb
from public.dblink_get_result('connected_loop_a') as remote(result text);
insert into connected_loop_race_results select 'claim-second',result::jsonb
from public.dblink_get_result('connected_loop_b') as remote(result text);
select * from public.dblink_get_result('connected_loop_a') as remote(result text);
select * from public.dblink_get_result('connected_loop_b') as remote(result text);

do $check$
declare replay jsonb;
begin
  if exists(
    select 1 from connected_loop_race_results
    where lane in ('worker-a','claim-first','cancel-first')
      and value->>'ok'<>'true'
  ) or exists(
    select 1 from connected_loop_race_results
    where lane in ('worker-b','cancel-second','claim-second')
      and (value->>'ok'<>'false' or value->>'sqlstate'<>'55000')
  ) then
    raise exception 'connected loop race winner results drifted: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_loop_race_results);
  end if;
  if (select count(*) from connected_loop_private.steps
      where owner_id='97010000-0000-4000-8000-000000000001')<>1
     or not exists(select 1 from connected_loop_private.loops
       where owner_id='97010000-0000-4000-8000-000000000001'
         and status='active' and task_state_revision=2)
     or (select count(*) from connected_loop_private.steps
       where owner_id='97020000-0000-4000-8000-000000000001')<>1
     or not exists(select 1 from connected_loop_private.loops
       where owner_id='97020000-0000-4000-8000-000000000001'
         and status='active' and task_state_revision=2)
     or exists(select 1 from connected_loop_private.steps
       where owner_id='97030000-0000-4000-8000-000000000001')
     or not exists(select 1 from connected_loop_private.loops
       where owner_id='97030000-0000-4000-8000-000000000001'
         and status='cancelled' and task_state_revision=2) then
    raise exception 'connected loop race final state violated exact winner fences';
  end if;
  replay:=public.connected_multi_step_cancel_owner_v1(
    '97030000-0000-4000-8000-000000000001',
    '97030000-0000-4000-8000-000000000005',1,pg_catalog.clock_timestamp());
  if replay->>'status'<>'cancelled' or replay->>'task_state_revision'<>'2'
     or replay ? 'owner_id' or replay ? 'session_id'
     or replay ? 'turn_claim_token' or replay ? 'request_binding_sha256' then
    raise exception 'connected loop cancel replay exposed unsafe state: %',replay;
  end if;
  begin
    perform public.connected_multi_step_cancel_owner_v1(
      '97030000-0000-4000-8000-000000000001',
      '97030000-0000-4000-8000-000000000005',9,pg_catalog.clock_timestamp());
    raise exception 'connected loop stale cancelled revision was accepted';
  exception when sqlstate '55000' then
    null;
  end;
end;
$check$;

select public.dblink_disconnect('connected_loop_a');
select public.dblink_disconnect('connected_loop_b');
delete from public.users where id in (
  '97010000-0000-4000-8000-000000000001',
  '97020000-0000-4000-8000-000000000001',
  '97030000-0000-4000-8000-000000000001');
drop function public.connected_loop_test_seed_v1(uuid,uuid,uuid,uuid,uuid);
drop function public.connected_loop_test_claim_v1(uuid,uuid,uuid,bigint,uuid,uuid,numeric);
drop function public.connected_loop_test_stop_v1(uuid,uuid,bigint,numeric);

select 'CONNECTED_MULTI_STEP_OPERATOR_LOOP_RACES_OK' as result;
