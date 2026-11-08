\set ON_ERROR_STOP on

create or replace function public.connected_oauth_687_race_id_v1(p_value text)
returns uuid language sql immutable set search_path='' as $fn$
  select (
    pg_catalog.substr(pg_catalog.md5(p_value),1,8)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),9,4)||'-4'||
    pg_catalog.substr(pg_catalog.md5(p_value),14,3)||'-8'||
    pg_catalog.substr(pg_catalog.md5(p_value),18,3)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),21,12)
  )::uuid
$fn$;

create or replace function public.connected_oauth_687_race_sha_v1(p_value text)
returns text language sql immutable set search_path='' as $fn$
  select pg_catalog.md5(p_value||':left')||pg_catalog.md5(p_value||':right')
$fn$;

create or replace function public.connected_oauth_687_seed_one_v1(
  p_lane text,p_side text,p_exchanged boolean
) returns void language plpgsql set search_path='' as $fn$
declare
  owner_id uuid:=public.connected_oauth_687_race_id_v1(p_lane||':owner');
  connection_id uuid:=public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':connection');
  incarnation_id uuid:=public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':incarnation');
  flow_id uuid:=public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':flow');
  nonce_id uuid:=public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':nonce');
  exchange_id uuid:=public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':exchange');
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,current_flow_nonce_sha256
  ) values(connection_id,owner_id,'google','mail','personal',incarnation_id,0,
    'pending',public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':nonce'));
  perform public.connected_app_oauth_create_pending_v1(
    flow_id,nonce_id,owner_id,connection_id,incarnation_id,0,
    public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':nonce'),
    public.connected_oauth_687_race_sha_v1(p_lane||':session'),
    'google','mail','personal',array['mail.get'],
    public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':actions'),
    public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':scopes'),
    public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':state'),
    repeat('P',43),
    public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':redirect'),
    public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':flow-binding'),
    public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':start-receipt'),
    now_at,now_at+interval '5 minutes'
  );
  if p_exchanged then
    perform public.connected_app_oauth_consume_pending_v1(
      flow_id,flow_id,owner_id,connection_id,incarnation_id,0,
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':nonce'),
      public.connected_oauth_687_race_sha_v1(p_lane||':session'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':flow-binding'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':consume')
    );
    perform public.connected_app_oauth_put_permit_capability_v2(
      exchange_id,flow_id,connection_id,exchange_id,
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':flow-binding'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
      now_at,now_at+interval '2 minutes','oauth-race-key',repeat('A',16),
      repeat('B',64),repeat('C',16),repeat('D',32),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':permit-record')
    );
    perform public.connected_app_oauth_consume_permit_v2(
      exchange_id,flow_id,connection_id,exchange_id,
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':flow-binding'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':dispatch')
    );
  end if;
end;
$fn$;

create or replace function public.connected_oauth_687_seed_lane_v1(
  p_lane text,p_exchanged boolean,p_two boolean default true
) returns void language plpgsql set search_path='' as $fn$
declare owner_id uuid:=public.connected_oauth_687_race_id_v1(p_lane||':owner');
begin
  delete from public.users where id=owner_id;
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(owner_id,owner_id::text||'@oauth-race.example.test',
    '$argon2id$oauth-race',true,false,pg_catalog.clock_timestamp()-interval '1 day',
    pg_catalog.clock_timestamp(),'production',
    pg_catalog.clock_timestamp()-interval '1 day',false,
    pg_catalog.clock_timestamp()-interval '1 day');
  perform public.connected_oauth_687_seed_one_v1(p_lane,'a',p_exchanged);
  if p_two then
    perform public.connected_oauth_687_seed_one_v1(p_lane,'b',p_exchanged);
  end if;
end;
$fn$;

create or replace function public.connected_oauth_687_finalize_v1(
  p_lane text,p_side text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare
  issued_at timestamptz:=pg_catalog.clock_timestamp();
  result jsonb;
begin
  begin
    result:=public.connected_app_oauth_finalize_v2(
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':flow'),
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':flow'),
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':exchange'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':dispatch'),
      public.connected_oauth_687_race_id_v1(p_lane||':owner'),
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':connection'),
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':incarnation'),
      0,public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':nonce'),
      'google','mail','personal',
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':external'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':scopes'),
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':credential'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':credential'),
      issued_at,issued_at+interval '1 hour',
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':authorization'),
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':flow'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':completion'),
      public.connected_oauth_687_race_id_v1(p_lane||':'||p_side||':cleanup'),
      public.connected_oauth_687_race_sha_v1(p_lane||':'||p_side||':cleanup')
    );
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_oauth_687_accept_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare
  result jsonb;
  received_at timestamptz:=pg_catalog.clock_timestamp();
begin
  begin
    perform public.connected_app_operator_prepare_oauth_callback_v2(
      public.connected_oauth_687_race_id_v1(p_lane||':owner'),
      public.connected_oauth_687_race_sha_v1(p_lane||':session'),'google',
      public.connected_oauth_687_race_sha_v1(p_lane||':a:state'),
      public.connected_oauth_687_race_sha_v1(p_lane||':callback'),received_at
    );
    result:=public.connected_app_operator_accept_oauth_callback_v1(
      'google',public.connected_oauth_687_race_sha_v1(p_lane||':a:state'),
      public.connected_oauth_687_race_sha_v1(p_lane||':callback'),received_at,
      public.connected_oauth_687_race_id_v1(p_lane||':a:flow'),
      public.connected_oauth_687_race_id_v1(p_lane||':owner'),
      public.connected_oauth_687_race_id_v1(p_lane||':a:connection'),
      public.connected_oauth_687_race_id_v1(p_lane||':a:incarnation'),0,
      public.connected_oauth_687_race_sha_v1(p_lane||':a:nonce'),
      public.connected_oauth_687_race_sha_v1(p_lane||':session'),
      public.connected_oauth_687_race_sha_v1(p_lane||':a:flow-binding'),
      public.connected_oauth_687_race_sha_v1(p_lane||':consume')
    );
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_oauth_687_deny_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  begin
    result:=public.connected_app_operator_deny_oauth_callback_v1(
      public.connected_oauth_687_race_id_v1(p_lane||':owner'),
      public.connected_oauth_687_race_sha_v1(p_lane||':session'),'google',
      public.connected_oauth_687_race_sha_v1(p_lane||':a:state'),'access_denied',
      public.connected_oauth_687_race_sha_v1(p_lane||':denial'),
      pg_catalog.clock_timestamp()
    );
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create temporary table connected_oauth_687_race_results(
  lane text primary key,value jsonb not null
) on commit preserve rows;

select public.dblink_connect('oauth_687_a',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'oauth-687-race-a'));
select public.dblink_connect('oauth_687_b',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'oauth-687-race-b'));

-- The first exact finalize wins owner/provider/resource authority.
select public.connected_oauth_687_seed_lane_v1('finalize-a-first',true);
select public.dblink_send_query('oauth_687_a',$q$
  select public.connected_oauth_687_finalize_v1('finalize-a-first','a',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('oauth_687_b',$q$
  select public.connected_oauth_687_finalize_v1('finalize-a-first','b',0)::text
$q$);
insert into connected_oauth_687_race_results select 'finalize-a',value::jsonb
from public.dblink_get_result('oauth_687_a') as remote(value text);
insert into connected_oauth_687_race_results select 'finalize-b',value::jsonb
from public.dblink_get_result('oauth_687_b') as remote(value text);
select * from public.dblink_get_result('oauth_687_a') as remote(value text);
select * from public.dblink_get_result('oauth_687_b') as remote(value text);

-- Reverse dispatch proves the other connection can win with the same result.
select public.connected_oauth_687_seed_lane_v1('finalize-b-first',true);
select public.dblink_send_query('oauth_687_b',$q$
  select public.connected_oauth_687_finalize_v1('finalize-b-first','b',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('oauth_687_a',$q$
  select public.connected_oauth_687_finalize_v1('finalize-b-first','a',0)::text
$q$);
insert into connected_oauth_687_race_results select 'reverse-b',value::jsonb
from public.dblink_get_result('oauth_687_b') as remote(value text);
insert into connected_oauth_687_race_results select 'reverse-a',value::jsonb
from public.dblink_get_result('oauth_687_a') as remote(value text);
select * from public.dblink_get_result('oauth_687_a') as remote(value text);
select * from public.dblink_get_result('oauth_687_b') as remote(value text);

-- Denial wins: no later success callback can consume the invalidated flow.
select public.connected_oauth_687_seed_lane_v1('denial-first',false,false);
select public.dblink_send_query('oauth_687_a',$q$
  select public.connected_oauth_687_deny_v1('denial-first',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('oauth_687_b',$q$
  select public.connected_oauth_687_accept_v1('denial-first',0)::text
$q$);
insert into connected_oauth_687_race_results select 'denial-first',value::jsonb
from public.dblink_get_result('oauth_687_a') as remote(value text);
insert into connected_oauth_687_race_results select 'accept-after-denial',value::jsonb
from public.dblink_get_result('oauth_687_b') as remote(value text);
select * from public.dblink_get_result('oauth_687_a') as remote(value text);
select * from public.dblink_get_result('oauth_687_b') as remote(value text);

-- Success callback wins: denial cannot rewrite a consumed flow.
select public.connected_oauth_687_seed_lane_v1('accept-first',false,false);
select public.dblink_send_query('oauth_687_a',$q$
  select public.connected_oauth_687_accept_v1('accept-first',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('oauth_687_b',$q$
  select public.connected_oauth_687_deny_v1('accept-first',0)::text
$q$);
insert into connected_oauth_687_race_results select 'accept-first',value::jsonb
from public.dblink_get_result('oauth_687_a') as remote(value text);
insert into connected_oauth_687_race_results select 'denial-after-accept',value::jsonb
from public.dblink_get_result('oauth_687_b') as remote(value text);
select * from public.dblink_get_result('oauth_687_a') as remote(value text);
select * from public.dblink_get_result('oauth_687_b') as remote(value text);

do $assert$
begin
  if not coalesce((select (value->>'ok')::boolean from connected_oauth_687_race_results
                   where lane='finalize-a'),false)
     or not coalesce((select (value->>'ok')::boolean from connected_oauth_687_race_results
                      where lane='finalize-b'),false)
     or (select value#>>'{value,active}' from connected_oauth_687_race_results
         where lane='finalize-a')<>'true'
     or (select value#>>'{value,active}' from connected_oauth_687_race_results
         where lane='finalize-b')<>'false'
     or (select value#>>'{value,active}' from connected_oauth_687_race_results
         where lane='reverse-b')<>'true'
     or (select value#>>'{value,active}' from connected_oauth_687_race_results
         where lane='reverse-a')<>'false' then
    raise exception 'two-finalizer winner-order contract drifted: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_oauth_687_race_results where lane like 'finalize-%'
          or lane like 'reverse-%');
  end if;
  if (select value->>'ok' from connected_oauth_687_race_results
      where lane='denial-first')<>'true'
     or (select value->>'ok' from connected_oauth_687_race_results
         where lane='accept-after-denial')<>'false'
     or (select value->>'ok' from connected_oauth_687_race_results
         where lane='accept-first')<>'true'
     or (select value->>'ok' from connected_oauth_687_race_results
         where lane='denial-after-accept')<>'false'
     or not exists(
       select 1 from connected_app_private.oauth_flows
       where flow_id=public.connected_oauth_687_race_id_v1('denial-first:a:flow')
         and status='invalidated'
     ) or not exists(
       select 1 from connected_app_private.oauth_flows
       where flow_id=public.connected_oauth_687_race_id_v1('accept-first:a:flow')
         and status='consumed'
     ) then
    raise exception 'callback-denial winner-order contract drifted: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_oauth_687_race_results where lane like '%denial%'
          or lane like '%accept%');
  end if;
  if exists(
    select 1 from connected_app_private.connections
    where owner_id in (
      public.connected_oauth_687_race_id_v1('finalize-a-first:owner'),
      public.connected_oauth_687_race_id_v1('finalize-b-first:owner')
    ) and authorization_state='active'
    group by owner_id,provider,resource having pg_catalog.count(*)<>1
  ) then
    raise exception 'duplicate active authority survived a finalize race';
  end if;
end;
$assert$;

select public.dblink_disconnect('oauth_687_a');
select public.dblink_disconnect('oauth_687_b');

select 'CONNECTED_OAUTH_OWNER_BINDING_RACES_OK' as result;
