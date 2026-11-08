\set ON_ERROR_STOP on

create extension if not exists dblink with schema public;

create or replace function public.connected_continuation_test_seed_v1(
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
    p_owner_id,p_owner_id::text||'@continuation.example.test',
    '$argon2id$connected-continuation-v1',true,false,
    now_at-interval '1 minute',now_at-interval '1 minute',
    'production',now_at,false,now_at
  );
  insert into public.sessions(
    id,user_id,token_hash,device_id,device_name,platform,device_info,
    created_at,last_activity,expires_at
  ) values(
    p_session_id,p_owner_id,
    pg_catalog.md5(p_session_id::text)||pg_catalog.md5(p_session_id::text||':token'),
    p_session_id::text,'Continuation test','web','{}'::jsonb,
    now_at,now_at,now_at+interval '1 day'
  );
  insert into public.user_chats(user_id,chat_id,title,messages,created_at,updated_at)
  values(p_owner_id,p_chat_id,'Continuation test',
    pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
      'id',p_message_id,'role','user','content',
      'Check my calendar for next Tuesday.')),now_at,now_at);
  select claim.turn_id,claim.claim_token into strict turn_id,turn_claim
  from public.connected_chat_claim_turn_v1(
    p_owner_id,p_chat_id,p_message_id,repeat('a',64),repeat('b',64)) as claim;
  return public.connected_multi_step_start_v1(
    p_loop_id,p_owner_id,p_session_id,repeat('a',64),p_chat_id,p_message_id,
    turn_id,turn_claim,'UTC',repeat('b',64),now_at,
    now_at+interval '20 minutes',8);
end;
$fn$;

create or replace function public.connected_continuation_test_claim_v1(
  p_owner_id uuid,p_loop_id uuid,p_revision bigint,
  p_request_id uuid,p_claim_token uuid,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  begin
    result:=public.connected_multi_step_continuation_claim_v1(
      p_owner_id,p_loop_id,p_revision,p_request_id,p_claim_token,
      pg_catalog.clock_timestamp(),90);
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
  end;
end;
$fn$;

create or replace function public.connected_continuation_test_cancel_v1(
  p_owner_id uuid,p_loop_id uuid,p_revision bigint,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  begin
    result:=public.connected_multi_step_cancel_owner_v1(
      p_owner_id,p_loop_id,p_revision,pg_catalog.clock_timestamp());
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate,'message',sqlerrm);
  end;
end;
$fn$;

select public.connected_continuation_test_seed_v1(
  '98500000-0000-4000-8000-000000000001',
  '98500000-0000-4000-8000-000000000002',
  '98500000-0000-4000-8000-000000000003',
  '98500000-0000-4000-8000-000000000004',
  '98500000-0000-4000-8000-000000000005');

do $behavior$
declare
  owner_id constant uuid:='98500000-0000-4000-8000-000000000001';
  loop_id constant uuid:='98500000-0000-4000-8000-000000000005';
  request_one constant uuid:='98500000-0000-4000-8000-000000000006';
  token_one constant uuid:='98500000-0000-4000-8000-000000000007';
  request_two constant uuid:='98500000-0000-4000-8000-000000000008';
  token_two constant uuid:='98500000-0000-4000-8000-000000000009';
  settlement_id constant uuid:='98500000-0000-4000-8000-00000000000a';
  row_value jsonb;
  replay jsonb;
begin
  select item into strict row_value
  from public.connected_multi_step_continuation_list_v1(
    8,pg_catalog.clock_timestamp()) as item
  where item->>'loop_id'=loop_id::text;
  if row_value->>'kind'<>'active'
     or row_value->>'task_state_revision'<>'1' then
    raise exception 'active continuation discovery failed: %',row_value;
  end if;
  row_value:=public.connected_multi_step_continuation_claim_v1(
    owner_id,loop_id,1,request_one,token_one,pg_catalog.clock_timestamp(),90);
  replay:=public.connected_multi_step_continuation_claim_v1(
    owner_id,loop_id,1,request_one,token_one,pg_catalog.clock_timestamp(),90);
  if replay is distinct from row_value or row_value->>'claim_generation'<>'1'
     or row_value->>'claim_state'<>'claimed' then
    raise exception 'claim response-loss replay changed: %, %',row_value,replay;
  end if;
  replay:=public.connected_multi_step_continuation_instruction_v1(
    owner_id,loop_id,request_one,token_one,1,pg_catalog.clock_timestamp());
  if replay->>'instruction'<>'Check my calendar for next Tuesday.'
     or replay ? 'session_id' or replay ? 'request_binding_sha256' then
    raise exception 'instruction custody binding failed: %',replay;
  end if;
  begin
    perform public.connected_multi_step_continuation_instruction_v1(
      '98500000-0000-4000-8000-000000000099',loop_id,
      request_one,token_one,1,pg_catalog.clock_timestamp());
    raise exception 'cross-owner instruction substitution was accepted';
  exception when sqlstate '55000' then null;
  end;
  perform public.connected_multi_step_continuation_renew_v1(
    owner_id,loop_id,request_one,token_one,1,1,
    pg_catalog.clock_timestamp(),90);
  row_value:=public.connected_multi_step_continuation_settle_v1(
    owner_id,loop_id,request_one,token_one,1,settlement_id,
    'retryable',1,pg_catalog.clock_timestamp());
  replay:=public.connected_multi_step_continuation_settle_v1(
    owner_id,loop_id,request_one,token_one,1,settlement_id,
    'retryable',1,pg_catalog.clock_timestamp());
  if replay is distinct from row_value
     or public.connected_multi_step_continuation_read_settlement_v1(
       settlement_id,request_one,token_one) is distinct from row_value then
    raise exception 'settlement response-loss recovery changed';
  end if;
  update connected_loop_continuation_private.jobs
  set available_at=pg_catalog.clock_timestamp()-interval '1 second'
  where connected_loop_continuation_private.jobs.loop_id=
    '98500000-0000-4000-8000-000000000005'::uuid;
  perform public.connected_multi_step_continuation_claim_v1(
    owner_id,loop_id,1,request_two,token_two,pg_catalog.clock_timestamp(),90);
  update connected_loop_continuation_private.claims
  set claimed_at=pg_catalog.clock_timestamp()-interval '2 minutes',
      claim_expires_at=pg_catalog.clock_timestamp()-interval '1 minute'
  where claim_request_id=request_two;
  update connected_loop_continuation_private.jobs
  set available_at=pg_catalog.clock_timestamp()-interval '1 second'
  where connected_loop_continuation_private.jobs.loop_id=
    '98500000-0000-4000-8000-000000000005'::uuid;
  replay:=public.connected_multi_step_continuation_claim_v1(
    owner_id,loop_id,1,
    '98500000-0000-4000-8000-00000000000b',
    '98500000-0000-4000-8000-00000000000c',
    pg_catalog.clock_timestamp(),90);
  if replay->>'claim_generation'<>'3'
     or not exists(select 1 from connected_loop_continuation_private.claims
       where claim_request_id=request_two and status='superseded') then
    raise exception 'host-crash lease recovery failed: %',replay;
  end if;
  delete from public.user_chats
  where user_id=owner_id
    and chat_id='98500000-0000-4000-8000-000000000003';
  replay:=public.connected_multi_step_continuation_instruction_v1(
    owner_id,loop_id,
    '98500000-0000-4000-8000-00000000000b',
    '98500000-0000-4000-8000-00000000000c',3,
    pg_catalog.clock_timestamp());
  if replay->'instruction'<>'null'::jsonb then
    raise exception 'deleted instruction did not fail closed: %',replay;
  end if;
end;
$behavior$;

select public.connected_continuation_test_seed_v1(
  '98510000-0000-4000-8000-000000000001','98510000-0000-4000-8000-000000000002',
  '98510000-0000-4000-8000-000000000003','98510000-0000-4000-8000-000000000004',
  '98510000-0000-4000-8000-000000000005');
select public.connected_continuation_test_seed_v1(
  '98520000-0000-4000-8000-000000000001','98520000-0000-4000-8000-000000000002',
  '98520000-0000-4000-8000-000000000003','98520000-0000-4000-8000-000000000004',
  '98520000-0000-4000-8000-000000000005');
select public.connected_continuation_test_seed_v1(
  '98530000-0000-4000-8000-000000000001','98530000-0000-4000-8000-000000000002',
  '98530000-0000-4000-8000-000000000003','98530000-0000-4000-8000-000000000004',
  '98530000-0000-4000-8000-000000000005');

create temporary table connected_continuation_race_results(
  lane text primary key,value jsonb not null
) on commit preserve rows;

select public.dblink_connect('continuation_a',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'connected-continuation-a'));
select public.dblink_connect('continuation_b',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'connected-continuation-b'));

select public.dblink_send_query('continuation_a',$q$
  select public.connected_continuation_test_claim_v1(
    '98510000-0000-4000-8000-000000000001','98510000-0000-4000-8000-000000000005',1,
    '98510000-0000-4000-8000-000000000006','98510000-0000-4000-8000-000000000007',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('continuation_b',$q$
  select public.connected_continuation_test_claim_v1(
    '98510000-0000-4000-8000-000000000001','98510000-0000-4000-8000-000000000005',1,
    '98510000-0000-4000-8000-000000000008','98510000-0000-4000-8000-000000000009',0)::text
$q$);
insert into connected_continuation_race_results select 'worker-a',result::jsonb
from public.dblink_get_result('continuation_a') as remote(result text);
insert into connected_continuation_race_results select 'worker-b',result::jsonb
from public.dblink_get_result('continuation_b') as remote(result text);
select * from public.dblink_get_result('continuation_a') as remote(result text);
select * from public.dblink_get_result('continuation_b') as remote(result text);

select public.dblink_send_query('continuation_a',$q$
  select public.connected_continuation_test_claim_v1(
    '98520000-0000-4000-8000-000000000001','98520000-0000-4000-8000-000000000005',1,
    '98520000-0000-4000-8000-000000000006','98520000-0000-4000-8000-000000000007',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('continuation_b',$q$
  select public.connected_continuation_test_cancel_v1(
    '98520000-0000-4000-8000-000000000001','98520000-0000-4000-8000-000000000005',1,0)::text
$q$);
insert into connected_continuation_race_results select 'claim-first',result::jsonb
from public.dblink_get_result('continuation_a') as remote(result text);
insert into connected_continuation_race_results select 'cancel-second',result::jsonb
from public.dblink_get_result('continuation_b') as remote(result text);
select * from public.dblink_get_result('continuation_a') as remote(result text);
select * from public.dblink_get_result('continuation_b') as remote(result text);

select public.dblink_send_query('continuation_a',$q$
  select public.connected_continuation_test_cancel_v1(
    '98530000-0000-4000-8000-000000000001','98530000-0000-4000-8000-000000000005',1,0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('continuation_b',$q$
  select public.connected_continuation_test_claim_v1(
    '98530000-0000-4000-8000-000000000001','98530000-0000-4000-8000-000000000005',1,
    '98530000-0000-4000-8000-000000000006','98530000-0000-4000-8000-000000000007',0)::text
$q$);
insert into connected_continuation_race_results select 'cancel-first',result::jsonb
from public.dblink_get_result('continuation_a') as remote(result text);
insert into connected_continuation_race_results select 'claim-second',result::jsonb
from public.dblink_get_result('continuation_b') as remote(result text);
select * from public.dblink_get_result('continuation_a') as remote(result text);
select * from public.dblink_get_result('continuation_b') as remote(result text);

do $race_check$
begin
  if exists(select 1 from connected_continuation_race_results
      where lane in ('worker-a','claim-first','cancel-second','cancel-first')
        and value->>'ok'<>'true')
     or exists(select 1 from connected_continuation_race_results
      where lane='worker-b'
        and (value->>'ok'<>'false' or value->>'sqlstate'<>'55P03'))
     or exists(select 1 from connected_continuation_race_results
      where lane='claim-second'
        and (value->>'ok'<>'false' or value->>'sqlstate'<>'55000')) then
    raise exception 'continuation race outcomes drifted: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_continuation_race_results);
  end if;
  if not exists(select 1 from connected_loop_private.loops
       where owner_id='98520000-0000-4000-8000-000000000001'
         and status='cancelled' and task_state_revision=2)
     or not exists(select 1 from connected_loop_private.loops
       where owner_id='98530000-0000-4000-8000-000000000001'
         and status='cancelled' and task_state_revision=2) then
    raise exception 'continuation cancel race final state drifted';
  end if;
  begin
    perform public.connected_multi_step_continuation_instruction_v1(
      '98520000-0000-4000-8000-000000000001',
      '98520000-0000-4000-8000-000000000005',
      '98520000-0000-4000-8000-000000000006',
      '98520000-0000-4000-8000-000000000007',1,
      pg_catalog.clock_timestamp());
    raise exception 'cancelled claim rehydrated the original instruction';
  exception when sqlstate '55000' then null;
  end;
end;
$race_check$;

select public.dblink_disconnect('continuation_a');
select public.dblink_disconnect('continuation_b');

delete from public.users where id in (
  '98500000-0000-4000-8000-000000000001',
  '98510000-0000-4000-8000-000000000001',
  '98520000-0000-4000-8000-000000000001',
  '98530000-0000-4000-8000-000000000001');

do $deletion_check$
begin
  if exists(select 1 from connected_loop_continuation_private.jobs
      where owner_id::text like '985%')
     or exists(select 1 from connected_loop_continuation_private.claims
      where owner_id::text like '985%') then
    raise exception 'continuation account deletion left queue rows';
  end if;
end;
$deletion_check$;

drop function public.connected_continuation_test_seed_v1(uuid,uuid,uuid,uuid,uuid);
drop function public.connected_continuation_test_claim_v1(uuid,uuid,bigint,uuid,uuid,numeric);
drop function public.connected_continuation_test_cancel_v1(uuid,uuid,bigint,numeric);

select 'CONNECTED_MULTI_STEP_CONTINUATION_QUEUE_OK' as result;
