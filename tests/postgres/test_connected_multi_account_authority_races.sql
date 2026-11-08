\set ON_ERROR_STOP on

create or replace function public.connected_multi_689_race_id_v1(p_value text)
returns uuid language sql immutable set search_path='' as $fn$
  select (
    pg_catalog.substr(pg_catalog.md5(p_value),1,8)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),9,4)||'-4'||
    pg_catalog.substr(pg_catalog.md5(p_value),14,3)||'-8'||
    pg_catalog.substr(pg_catalog.md5(p_value),18,3)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),21,12)
  )::uuid
$fn$;

create or replace function public.connected_multi_689_race_sha_v1(p_value text)
returns text language sql immutable set search_path='' as $fn$
  select pg_catalog.md5(p_value||':left')||pg_catalog.md5(p_value||':right')
$fn$;

create or replace function public.connected_multi_689_seed_one_v1(
  p_lane text,p_side text,p_account_kind text
) returns void language plpgsql set search_path='' as $fn$
declare
  owner_id uuid:=public.connected_multi_689_race_id_v1(p_lane||':owner');
  connection_id uuid:=public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':connection');
  incarnation_id uuid:=public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':incarnation');
  flow_id uuid:=public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':flow');
  nonce_id uuid:=public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':nonce');
  exchange_id uuid:=public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':exchange');
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,current_flow_nonce_sha256
  ) values(
    connection_id,owner_id,'microsoft','mail',p_account_kind,incarnation_id,0,
    'pending',public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':nonce')
  );
  perform public.connected_app_oauth_create_pending_v1(
    flow_id,nonce_id,owner_id,connection_id,incarnation_id,0,
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':nonce'),
    public.connected_multi_689_race_sha_v1(p_lane||':session'),
    'microsoft','mail',p_account_kind,array['mail.get'],
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':actions'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':scopes'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':state'),
    repeat('P',43),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':redirect'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':flow-binding'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':start-receipt'),
    now_at,now_at+interval '5 minutes'
  );
  perform public.connected_app_oauth_consume_pending_v1(
    flow_id,flow_id,owner_id,connection_id,incarnation_id,0,
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':nonce'),
    public.connected_multi_689_race_sha_v1(p_lane||':session'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':flow-binding'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':consume')
  );
  perform public.connected_app_oauth_put_permit_capability_v2(
    exchange_id,flow_id,connection_id,exchange_id,
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':flow-binding'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
    now_at,now_at+interval '2 minutes','oauth-race-key',repeat('A',16),
    repeat('B',64),repeat('C',16),repeat('D',32),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':permit-record')
  );
  perform public.connected_app_oauth_consume_permit_v2(
    exchange_id,flow_id,connection_id,exchange_id,
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':flow-binding'),
    public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
    public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':dispatch')
  );
end;
$fn$;

create or replace function public.connected_multi_689_seed_lane_v1(
  p_lane text,p_kind_b text
) returns void language plpgsql set search_path='' as $fn$
declare owner_id uuid:=public.connected_multi_689_race_id_v1(p_lane||':owner');
begin
  delete from public.users where id=owner_id;
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(
    owner_id,owner_id::text||'@multi-race.example.test','$argon2id$multi-race',
    true,false,pg_catalog.clock_timestamp()-interval '1 day',
    pg_catalog.clock_timestamp(),'production',
    pg_catalog.clock_timestamp()-interval '1 day',false,
    pg_catalog.clock_timestamp()-interval '1 day'
  );
  perform public.connected_multi_689_seed_one_v1(p_lane,'a','personal');
  perform public.connected_multi_689_seed_one_v1(p_lane,'b',p_kind_b);
end;
$fn$;

create or replace function public.connected_multi_689_finalize_v1(
  p_lane text,p_side text,p_account_kind text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare issued_at timestamptz:=pg_catalog.clock_timestamp(); result jsonb;
begin
  begin
    result:=public.connected_app_oauth_finalize_v2(
      public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':flow'),
      public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':flow'),
      public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':exchange'),
      public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':exchange-binding'),
      public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':dispatch'),
      public.connected_multi_689_race_id_v1(p_lane||':owner'),
      public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':connection'),
      public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':incarnation'),
      0,public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':nonce'),
      'microsoft','mail',p_account_kind,
      public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':external'),
      public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':scopes'),
      public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':credential'),
      public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':credential'),
      issued_at,issued_at+interval '1 hour',
      public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':authorization'),
      public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':flow'),
      public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':completion'),
      public.connected_multi_689_race_id_v1(p_lane||':'||p_side||':cleanup'),
      public.connected_multi_689_race_sha_v1(p_lane||':'||p_side||':cleanup')
    );
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create temporary table connected_multi_689_race_results(
  lane text primary key,value jsonb not null
) on commit preserve rows;

select public.dblink_connect('multi_689_a',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'multi-689-race-a'));
select public.dblink_connect('multi_689_b',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'multi-689-race-b'));

-- Distinct account kinds both win, regardless of dispatch order.
select public.connected_multi_689_seed_lane_v1('different-a-first','work_school');
select public.dblink_send_query('multi_689_a',$q$
  select public.connected_multi_689_finalize_v1(
    'different-a-first','a','personal',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('multi_689_b',$q$
  select public.connected_multi_689_finalize_v1(
    'different-a-first','b','work_school',0)::text
$q$);
insert into connected_multi_689_race_results select 'different-a',value::jsonb
from public.dblink_get_result('multi_689_a') as remote(value text);
insert into connected_multi_689_race_results select 'different-b',value::jsonb
from public.dblink_get_result('multi_689_b') as remote(value text);
select * from public.dblink_get_result('multi_689_a') as remote(value text);
select * from public.dblink_get_result('multi_689_b') as remote(value text);

select public.connected_multi_689_seed_lane_v1('different-b-first','work_school');
select public.dblink_send_query('multi_689_b',$q$
  select public.connected_multi_689_finalize_v1(
    'different-b-first','b','work_school',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('multi_689_a',$q$
  select public.connected_multi_689_finalize_v1(
    'different-b-first','a','personal',0)::text
$q$);
insert into connected_multi_689_race_results select 'different-reverse-b',value::jsonb
from public.dblink_get_result('multi_689_b') as remote(value text);
insert into connected_multi_689_race_results select 'different-reverse-a',value::jsonb
from public.dblink_get_result('multi_689_a') as remote(value text);
select * from public.dblink_get_result('multi_689_a') as remote(value text);
select * from public.dblink_get_result('multi_689_b') as remote(value text);

-- Duplicate same-kind authority still has exactly one winner in both orders.
select public.connected_multi_689_seed_lane_v1('same-a-first','personal');
select public.dblink_send_query('multi_689_a',$q$
  select public.connected_multi_689_finalize_v1(
    'same-a-first','a','personal',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('multi_689_b',$q$
  select public.connected_multi_689_finalize_v1(
    'same-a-first','b','personal',0)::text
$q$);
insert into connected_multi_689_race_results select 'same-a',value::jsonb
from public.dblink_get_result('multi_689_a') as remote(value text);
insert into connected_multi_689_race_results select 'same-b',value::jsonb
from public.dblink_get_result('multi_689_b') as remote(value text);
select * from public.dblink_get_result('multi_689_a') as remote(value text);
select * from public.dblink_get_result('multi_689_b') as remote(value text);

select public.connected_multi_689_seed_lane_v1('same-b-first','personal');
select public.dblink_send_query('multi_689_b',$q$
  select public.connected_multi_689_finalize_v1(
    'same-b-first','b','personal',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('multi_689_a',$q$
  select public.connected_multi_689_finalize_v1(
    'same-b-first','a','personal',0)::text
$q$);
insert into connected_multi_689_race_results select 'same-reverse-b',value::jsonb
from public.dblink_get_result('multi_689_b') as remote(value text);
insert into connected_multi_689_race_results select 'same-reverse-a',value::jsonb
from public.dblink_get_result('multi_689_a') as remote(value text);
select * from public.dblink_get_result('multi_689_a') as remote(value text);
select * from public.dblink_get_result('multi_689_b') as remote(value text);

do $assert$
declare row_record record;
begin
  if exists(
    select 1 from connected_multi_689_race_results
    where (value->>'ok')::boolean is not true
  ) then
    raise exception 'multi-account finalizer race raised unexpectedly: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_multi_689_race_results);
  end if;
  if exists(
    select 1 from connected_multi_689_race_results
    where lane like 'different-%' and value#>>'{value,active}'<>'true'
  ) then
    raise exception 'different account-kind finalizer lost authority: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_multi_689_race_results where lane like 'different-%');
  end if;
  if (select value#>>'{value,active}' from connected_multi_689_race_results
      where lane='same-a')<>'true'
     or (select value#>>'{value,active}' from connected_multi_689_race_results
         where lane='same-b')<>'false'
     or (select value#>>'{value,active}' from connected_multi_689_race_results
         where lane='same-reverse-b')<>'true'
     or (select value#>>'{value,active}' from connected_multi_689_race_results
         where lane='same-reverse-a')<>'false' then
    raise exception 'same account-kind winner order drifted: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_multi_689_race_results where lane like 'same-%');
  end if;
  for row_record in
    select owner_id,pg_catalog.count(*) as active_count,
      pg_catalog.count(distinct account_kind) as account_kind_count
    from connected_app_private.connections
    where owner_id in (
      public.connected_multi_689_race_id_v1('different-a-first:owner'),
      public.connected_multi_689_race_id_v1('different-b-first:owner')
    ) and authorization_state='active'
    group by owner_id
  loop
    if row_record.active_count<>2 or row_record.account_kind_count<>2 then
      raise exception 'different-kind authority cardinality drifted: %',row_record;
    end if;
  end loop;
  if exists(
    select 1 from connected_app_private.connections
    where owner_id in (
      public.connected_multi_689_race_id_v1('same-a-first:owner'),
      public.connected_multi_689_race_id_v1('same-b-first:owner')
    ) and authorization_state='active'
    group by owner_id having pg_catalog.count(*)<>1
  ) then
    raise exception 'duplicate same-kind active authority survived';
  end if;
end;
$assert$;

select public.dblink_disconnect('multi_689_a');
select public.dblink_disconnect('multi_689_b');

select 'CONNECTED_MULTI_ACCOUNT_AUTHORITY_RACES_OK' as result;
