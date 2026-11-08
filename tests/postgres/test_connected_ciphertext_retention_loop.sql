\set ON_ERROR_STOP on

create or replace function public.connected_retention_loop_id_v1(p_value text)
returns uuid language sql immutable set search_path='' as $fn$
  select (
    pg_catalog.substr(pg_catalog.md5(p_value),1,8)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),9,4)||'-4'||
    pg_catalog.substr(pg_catalog.md5(p_value),14,3)||'-8'||
    pg_catalog.substr(pg_catalog.md5(p_value),18,3)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),21,12)
  )::uuid
$fn$;

create or replace function public.connected_retention_loop_sha_v1(p_value text)
returns text language sql immutable set search_path='' as $fn$
  select pg_catalog.md5(p_value||':left')||pg_catalog.md5(p_value||':right')
$fn$;

create or replace function public.connected_retention_loop_seed_v1(
  p_lane text,p_expired boolean
) returns uuid language plpgsql set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  owner_id uuid:=public.connected_retention_loop_id_v1(p_lane||':owner');
  session_id uuid:=public.connected_retention_loop_id_v1(p_lane||':session');
  chat_id uuid:=public.connected_retention_loop_id_v1(p_lane||':chat');
  message_id uuid:=public.connected_retention_loop_id_v1(p_lane||':message');
  v_loop_id uuid:=public.connected_retention_loop_id_v1(p_lane||':loop');
  step_id uuid:=public.connected_retention_loop_id_v1(p_lane||':step');
  claim_request_id uuid:=public.connected_retention_loop_id_v1(p_lane||':claim-request');
  claim_token uuid:=public.connected_retention_loop_id_v1(p_lane||':step-claim');
  invocation_id uuid:=public.connected_retention_loop_id_v1(p_lane||':invocation');
  v_proposal_id uuid:=public.connected_retention_loop_id_v1(p_lane||':proposal');
  chat_claim record;
begin
  delete from public.users where id=owner_id;
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(owner_id,owner_id::text||'@retention-loop.example.test',
    '$argon2id$retention-loop-v1',true,false,now_at-interval '1 day',now_at,
    'production',now_at-interval '1 day',false,now_at-interval '1 day');
  insert into public.sessions(
    id,user_id,token_hash,device_id,device_name,platform,device_info,
    created_at,last_activity,expires_at
  ) values(session_id,owner_id,
    pg_catalog.md5(session_id::text)||pg_catalog.md5(session_id::text||':token'),
    session_id::text,'Retention loop','web','{}'::jsonb,
    now_at,now_at,now_at+interval '1 day');
  select * into strict chat_claim from public.connected_chat_claim_turn_v1(
    owner_id,chat_id,message_id,
    public.connected_retention_loop_sha_v1(p_lane||':session-binding'),
    public.connected_retention_loop_sha_v1(p_lane||':request-binding'));
  perform public.connected_multi_step_start_v1(
    v_loop_id,owner_id,session_id,
    public.connected_retention_loop_sha_v1(p_lane||':session-binding'),
    chat_id,message_id,chat_claim.turn_id,chat_claim.claim_token,'UTC',
    public.connected_retention_loop_sha_v1(p_lane||':request-binding'),
    now_at,now_at+interval '20 minutes',8);
  perform public.connected_multi_step_claim_v1(
    owner_id,v_loop_id,step_id,1,claim_request_id,claim_token,
    public.connected_retention_loop_sha_v1(p_lane||':planning-binding'),
    now_at,30);
  perform public.connected_multi_step_mark_invoked_v1(
    owner_id,v_loop_id,step_id,0,2,claim_request_id,claim_token,
    public.connected_retention_loop_sha_v1(p_lane||':planning-binding'),
    invocation_id,now_at,30);
  perform public.connected_multi_step_put_envelope_v1(
    v_proposal_id,v_loop_id,step_id,owner_id,chat_claim.turn_id,0,
    public.connected_retention_loop_sha_v1(p_lane||':planning-binding'),
    'retention-loop-commitment',
    public.connected_retention_loop_sha_v1(p_lane||':proposal-sha'),
    public.connected_retention_loop_sha_v1(p_lane||':reference'),
    now_at,now_at+interval '20 minutes','retention-loop-envelope',
    repeat('A',16),repeat('B',64),repeat('C',16),repeat('D',64),
    public.connected_retention_loop_sha_v1(p_lane||':record'));
  if p_expired then
    update connected_loop_private.loops as loop_value
    set requested_at=now_at-interval '2 minutes',
        expires_at=now_at-interval '1 minute'
    where loop_value.loop_id=v_loop_id;
    update connected_loop_private.envelopes as envelope
    set created_at=now_at-interval '2 minutes',
        expires_at=now_at-interval '1 minute'
    where envelope.proposal_id=v_proposal_id;
  end if;
  return v_proposal_id;
end;
$fn$;

do $behavior$
declare
  expired_proposal uuid;
  live_proposal uuid;
  result jsonb;
begin
  expired_proposal:=public.connected_retention_loop_seed_v1(
    'retention-loop-expired',true);
  live_proposal:=public.connected_retention_loop_seed_v1(
    'retention-loop-live',false);
  result:=public.connected_app_purge_expired_ciphertext_v1(10,10,10);
  if result->>'loop_envelopes_purged'<>'1'
     or exists(select 1 from connected_loop_private.envelopes
               where proposal_id=expired_proposal)
     or not exists(select 1 from connected_loop_private.loops
                   where loop_id=public.connected_retention_loop_id_v1(
                     'retention-loop-expired:loop'))
     or not exists(select 1 from connected_loop_private.steps
                   where step_id=public.connected_retention_loop_id_v1(
                     'retention-loop-expired:step'))
     or public.connected_multi_step_read_envelope_v1(
          public.connected_retention_loop_id_v1('retention-loop-expired:owner'),
          public.connected_retention_loop_id_v1('retention-loop-expired:loop'),
          public.connected_retention_loop_id_v1('retention-loop-expired:step'),
          expired_proposal) is not null
     or not exists(select 1 from connected_loop_private.envelopes
                   where proposal_id=live_proposal
                     and payload_ciphertext=repeat('D',64)) then
    raise exception 'multi-step ciphertext retention invariant failed: %',result;
  end if;
  if (public.connected_app_purge_expired_ciphertext_v1(10,10,10)
      ->>'loop_envelopes_purged')<>'0' then
    raise exception 'multi-step ciphertext purge replay was not idempotent';
  end if;
end;
$behavior$;

create or replace function public.connected_retention_loop_read_race_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare value jsonb;
begin
  begin
    value:=public.connected_multi_step_read_envelope_v1(
      public.connected_retention_loop_id_v1(p_lane||':owner'),
      public.connected_retention_loop_id_v1(p_lane||':loop'),
      public.connected_retention_loop_id_v1(p_lane||':step'),
      public.connected_retention_loop_id_v1(p_lane||':proposal'));
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',value);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_retention_loop_purge_race_v1(
  p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare value jsonb;
begin
  begin
    value:=public.connected_app_purge_expired_ciphertext_v1(100,100,100);
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',value);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_retention_loop_delete_race_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
begin
  begin
    delete from public.users
    where id=public.connected_retention_loop_id_v1(p_lane||':owner');
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_retention_loop_continue_race_v1(
  p_lane text
) returns jsonb language plpgsql set search_path='' as $fn$
declare value jsonb;
begin
  begin
    value:=public.connected_multi_step_continuation_claim_v1(
      public.connected_retention_loop_id_v1(p_lane||':owner'),
      public.connected_retention_loop_id_v1(p_lane||':loop'),3,
      public.connected_retention_loop_id_v1(p_lane||':continuation-request'),
      public.connected_retention_loop_id_v1(p_lane||':continuation-token'),
      pg_catalog.clock_timestamp(),30);
    return pg_catalog.jsonb_build_object('ok',true,'value',value);
  exception when others then
    return pg_catalog.jsonb_build_object(
      'ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create temporary table connected_retention_loop_race_results(
  lane text primary key,value jsonb not null
) on commit preserve rows;
select public.dblink_connect('retention_loop_a',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'retention-loop-race-a'));
select public.dblink_connect('retention_loop_b',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'retention-loop-race-b'));

-- An already-open envelope wins the owner fence, then purge deletes it.
select public.connected_retention_loop_seed_v1('retention-loop-read-purge',true);
select public.dblink_send_query('retention_loop_a',$q$
  select public.connected_retention_loop_read_race_v1(
    'retention-loop-read-purge',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_loop_b',
  'select public.connected_retention_loop_purge_race_v1(0)::text');
insert into connected_retention_loop_race_results select 'read-purge',value::jsonb
from public.dblink_get_result('retention_loop_a') as remote(value text);
insert into connected_retention_loop_race_results select 'read-purge-clean',value::jsonb
from public.dblink_get_result('retention_loop_b') as remote(value text);
select * from public.dblink_get_result('retention_loop_a') as remote(value text);
select * from public.dblink_get_result('retention_loop_b') as remote(value text);
delete from public.users where id=public.connected_retention_loop_id_v1(
  'retention-loop-read-purge:owner');

-- Purge wins first; the later open observes no ciphertext.
select public.connected_retention_loop_seed_v1('retention-loop-purge-read',true);
select public.dblink_send_query('retention_loop_a',
  'select public.connected_retention_loop_purge_race_v1(0.25)::text');
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_loop_b',$q$
  select public.connected_retention_loop_read_race_v1(
    'retention-loop-purge-read',0)::text
$q$);
insert into connected_retention_loop_race_results select 'purge-read',value::jsonb
from public.dblink_get_result('retention_loop_a') as remote(value text);
insert into connected_retention_loop_race_results select 'purge-read-open',value::jsonb
from public.dblink_get_result('retention_loop_b') as remote(value text);
select * from public.dblink_get_result('retention_loop_a') as remote(value text);
select * from public.dblink_get_result('retention_loop_b') as remote(value text);

-- Purge and account deletion share owner -> loop -> step -> envelope order.
select public.connected_retention_loop_seed_v1('retention-loop-delete-purge',true);
select public.dblink_send_query('retention_loop_a',$q$
  select public.connected_retention_loop_delete_race_v1(
    'retention-loop-delete-purge',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_loop_b',
  'select public.connected_retention_loop_purge_race_v1(0)::text');
insert into connected_retention_loop_race_results select 'delete-purge',value::jsonb
from public.dblink_get_result('retention_loop_a') as remote(value text);
insert into connected_retention_loop_race_results select 'delete-purge-clean',value::jsonb
from public.dblink_get_result('retention_loop_b') as remote(value text);
select * from public.dblink_get_result('retention_loop_a') as remote(value text);
select * from public.dblink_get_result('retention_loop_b') as remote(value text);

select public.connected_retention_loop_seed_v1('retention-loop-purge-delete',true);
select public.dblink_send_query('retention_loop_a',
  'select public.connected_retention_loop_purge_race_v1(0.25)::text');
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_loop_b',$q$
  select public.connected_retention_loop_delete_race_v1(
    'retention-loop-purge-delete',0)::text
$q$);
insert into connected_retention_loop_race_results select 'purge-delete',value::jsonb
from public.dblink_get_result('retention_loop_a') as remote(value text);
insert into connected_retention_loop_race_results select 'purge-delete-owner',value::jsonb
from public.dblink_get_result('retention_loop_b') as remote(value text);
select * from public.dblink_get_result('retention_loop_a') as remote(value text);
select * from public.dblink_get_result('retention_loop_b') as remote(value text);

-- An expired loop can never become runnable while purge owns the same fence.
select public.connected_retention_loop_seed_v1('retention-loop-continuation',true);
select public.dblink_send_query('retention_loop_a',
  'select public.connected_retention_loop_purge_race_v1(0.25)::text');
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_loop_b',$q$
  select public.connected_retention_loop_continue_race_v1(
    'retention-loop-continuation')::text
$q$);
insert into connected_retention_loop_race_results select 'purge-continuation',value::jsonb
from public.dblink_get_result('retention_loop_a') as remote(value text);
insert into connected_retention_loop_race_results select 'continuation-refused',value::jsonb
from public.dblink_get_result('retention_loop_b') as remote(value text);
select * from public.dblink_get_result('retention_loop_a') as remote(value text);
select * from public.dblink_get_result('retention_loop_b') as remote(value text);

do $race_check$
begin
  if exists(select 1 from connected_retention_loop_race_results
            where lane<>'continuation-refused' and value->>'ok'<>'true')
     or (select value->>'ok' from connected_retention_loop_race_results
         where lane='continuation-refused')<>'false'
     or (select value->>'sqlstate' from connected_retention_loop_race_results
         where lane='continuation-refused')<>'55000'
     or (select value->'value' from connected_retention_loop_race_results
         where lane='read-purge') is null
     or (select value->'value' from connected_retention_loop_race_results
         where lane='purge-read-open') is distinct from 'null'::jsonb
     or exists(select 1 from public.users where id in(
       public.connected_retention_loop_id_v1('retention-loop-delete-purge:owner'),
       public.connected_retention_loop_id_v1('retention-loop-purge-delete:owner'))) then
    raise exception 'multi-step retention race invariant failed: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_retention_loop_race_results);
  end if;
end;
$race_check$;

select public.dblink_disconnect('retention_loop_a');
select public.dblink_disconnect('retention_loop_b');

delete from public.users where id in(
  public.connected_retention_loop_id_v1('retention-loop-expired:owner'),
  public.connected_retention_loop_id_v1('retention-loop-live:owner'),
  public.connected_retention_loop_id_v1('retention-loop-purge-read:owner'),
  public.connected_retention_loop_id_v1('retention-loop-continuation:owner'));
drop function public.connected_retention_loop_seed_v1(text,boolean);
drop function public.connected_retention_loop_continue_race_v1(text);
drop function public.connected_retention_loop_delete_race_v1(text,numeric);
drop function public.connected_retention_loop_purge_race_v1(numeric);
drop function public.connected_retention_loop_read_race_v1(text,numeric);
drop function public.connected_retention_loop_sha_v1(text);
drop function public.connected_retention_loop_id_v1(text);

select 'CONNECTED_CIPHERTEXT_RETENTION_LOOP_OK' as result;
