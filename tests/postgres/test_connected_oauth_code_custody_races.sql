\set ON_ERROR_STOP on

create or replace function public.connected_oauth_688_race_id_v1(p_value text)
returns uuid language sql immutable set search_path='' as $fn$
  select (
    pg_catalog.substr(pg_catalog.md5(p_value),1,8)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),9,4)||'-4'||
    pg_catalog.substr(pg_catalog.md5(p_value),14,3)||'-8'||
    pg_catalog.substr(pg_catalog.md5(p_value),18,3)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),21,12)
  )::uuid
$fn$;

create or replace function public.connected_oauth_688_race_sha_v1(p_value text)
returns text language sql immutable set search_path='' as $fn$
  select pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(p_value,'UTF8')),'hex'
  )
$fn$;

create or replace function public.connected_oauth_688_race_seed_v1(p_lane text)
returns void language plpgsql set search_path='' as $fn$
declare
  owner_id uuid:=public.connected_oauth_688_race_id_v1(p_lane||':owner');
  connection_id uuid:=public.connected_oauth_688_race_id_v1(p_lane||':connection');
  incarnation_id uuid:=public.connected_oauth_688_race_id_v1(p_lane||':incarnation');
  flow_id uuid:=public.connected_oauth_688_race_id_v1(p_lane||':flow');
  nonce_id uuid:=public.connected_oauth_688_race_id_v1(p_lane||':nonce');
  created_at timestamptz:=pg_catalog.clock_timestamp()-interval '1 minute';
  expires_at timestamptz:=pg_catalog.clock_timestamp()+interval '4 minutes';
  received_at timestamptz:=pg_catalog.clock_timestamp();
begin
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(
    owner_id,owner_id::text||'@oauth-688-race.example.test',
    '$argon2id$oauth-688-race',true,false,created_at-interval '1 day',
    pg_catalog.clock_timestamp(),'production',created_at-interval '1 day',
    false,created_at-interval '1 day'
  );
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,current_flow_nonce_sha256
  ) values(
    connection_id,owner_id,'google','mail','personal',incarnation_id,0,
    'pending',public.connected_oauth_688_race_sha_v1(p_lane||':nonce')
  );
  perform public.connected_app_oauth_secret_begin_v1(
    flow_id,nonce_id,owner_id,connection_id,incarnation_id,0,
    public.connected_oauth_688_race_sha_v1(p_lane||':nonce'),
    public.connected_oauth_688_race_sha_v1(p_lane||':session'),
    'google','mail','personal',array['mail.get'],
    public.connected_oauth_688_race_sha_v1(p_lane||':actions'),array['scope'],
    public.connected_oauth_688_race_sha_v1(p_lane||':scopes'),
    public.connected_oauth_688_race_sha_v1(p_lane||':state'),repeat('P',43),
    'https://www.askcrump.com/api/connected-apps/oauth/callback/google',
    created_at,expires_at,
    public.connected_oauth_688_race_sha_v1(p_lane||':flow-binding'),
    'oauth-688-race-key',repeat('A',16),repeat('B',64),repeat('C',16),
    repeat('D',64),public.connected_oauth_688_race_sha_v1(p_lane||':secret-record')
  );
  perform public.connected_app_oauth_create_pending_v1(
    flow_id,nonce_id,owner_id,connection_id,incarnation_id,0,
    public.connected_oauth_688_race_sha_v1(p_lane||':nonce'),
    public.connected_oauth_688_race_sha_v1(p_lane||':session'),
    'google','mail','personal',array['mail.get'],
    public.connected_oauth_688_race_sha_v1(p_lane||':actions'),
    public.connected_oauth_688_race_sha_v1(p_lane||':scopes'),
    public.connected_oauth_688_race_sha_v1(p_lane||':state'),repeat('P',43),
    public.connected_oauth_688_race_sha_v1(p_lane||':redirect'),
    public.connected_oauth_688_race_sha_v1(p_lane||':flow-binding'),
    public.connected_oauth_688_race_sha_v1(p_lane||':start-receipt'),
    created_at,expires_at
  );
  perform public.connected_app_operator_accept_oauth_callback_v2(
    owner_id,public.connected_oauth_688_race_sha_v1(p_lane||':session'),
    'google',flow_id,flow_id,flow_id,connection_id,incarnation_id,
    public.connected_oauth_688_race_sha_v1(p_lane||':nonce'),
    public.connected_oauth_688_race_sha_v1(p_lane||':state'),
    public.connected_oauth_688_race_sha_v1(p_lane||':callback'),
    public.connected_oauth_688_race_sha_v1(p_lane||':flow-binding'),
    public.connected_oauth_688_race_sha_v1(p_lane||':consume'),
    public.connected_oauth_688_race_sha_v1(p_lane||':exchange'),
    public.connected_oauth_688_race_sha_v1(repeat('P',43)),
    public.connected_oauth_688_race_sha_v1(p_lane||':redirect'),
    public.connected_oauth_688_race_sha_v1(p_lane||':authorization-code'),
    public.connected_oauth_688_race_sha_v1(p_lane||':code-authority'),
    received_at,received_at+interval '2 minutes',0,'oauth-code-688-race',
    repeat('N',16),repeat('C',64),
    public.connected_oauth_688_race_sha_v1(p_lane||':code-record')
  );
end;
$fn$;

create or replace function public.connected_oauth_688_race_claim_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  begin
    result:=public.connected_app_oauth_code_claim_v1(
      public.connected_oauth_688_race_id_v1(p_lane||':owner'),
      public.connected_oauth_688_race_sha_v1(p_lane||':session'),'google',
      public.connected_oauth_688_race_id_v1(p_lane||':flow'),
      public.connected_oauth_688_race_id_v1(p_lane||':flow'),
      public.connected_oauth_688_race_id_v1(p_lane||':flow'),
      public.connected_oauth_688_race_sha_v1(p_lane||':exchange'),
      public.connected_oauth_688_race_sha_v1(p_lane||':state')
    );
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_oauth_688_race_fence_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  begin
    result:=public.connected_app_oauth_secret_fence_v1(
      public.connected_oauth_688_race_id_v1(p_lane||':flow'),
      public.connected_oauth_688_race_id_v1(p_lane||':flow'),
      public.connected_oauth_688_race_sha_v1(p_lane||':exchange'),
      public.connected_oauth_688_race_sha_v1(p_lane||':flow-binding'),
      public.connected_oauth_688_race_id_v1(p_lane||':attempt'),
      pg_catalog.clock_timestamp()+interval '1 minute'
    );
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_oauth_688_race_delete_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare changed bigint;
begin
  begin
    perform connected_app_private.owner_lock_v1(
      public.connected_oauth_688_race_id_v1(p_lane||':owner')
    );
    delete from public.users
    where id=public.connected_oauth_688_race_id_v1(p_lane||':owner');
    get diagnostics changed=row_count;
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',changed=1);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create temporary table connected_oauth_688_race_results(
  lane text primary key,value jsonb not null
) on commit preserve rows;

select public.dblink_connect('oauth_688_a',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'oauth-688-race-a'));
select public.dblink_connect('oauth_688_b',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'oauth-688-race-b'));

-- Code recovery wins before the broker fence, then the fence closes recovery.
select public.connected_oauth_688_race_seed_v1('claim-first');
select public.dblink_send_query('oauth_688_a',$q$
  select public.connected_oauth_688_race_claim_v1('claim-first',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('oauth_688_b',$q$
  select public.connected_oauth_688_race_fence_v1('claim-first',0)::text
$q$);
insert into connected_oauth_688_race_results select 'claim-first',value::jsonb
from public.dblink_get_result('oauth_688_a') as remote(value text);
insert into connected_oauth_688_race_results select 'fence-after-claim',value::jsonb
from public.dblink_get_result('oauth_688_b') as remote(value text);
select * from public.dblink_get_result('oauth_688_a') as remote(value text);
select * from public.dblink_get_result('oauth_688_b') as remote(value text);

-- The reverse winner proves a durable fence prevents any later code recovery.
select public.connected_oauth_688_race_seed_v1('fence-first');
select public.dblink_send_query('oauth_688_a',$q$
  select public.connected_oauth_688_race_fence_v1('fence-first',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('oauth_688_b',$q$
  select public.connected_oauth_688_race_claim_v1('fence-first',0)::text
$q$);
insert into connected_oauth_688_race_results select 'fence-first',value::jsonb
from public.dblink_get_result('oauth_688_a') as remote(value text);
insert into connected_oauth_688_race_results select 'claim-after-fence',value::jsonb
from public.dblink_get_result('oauth_688_b') as remote(value text);
select * from public.dblink_get_result('oauth_688_a') as remote(value text);
select * from public.dblink_get_result('oauth_688_b') as remote(value text);

-- Account deletion after a recovery claim erases the encrypted code.
select public.connected_oauth_688_race_seed_v1('claim-delete');
select public.dblink_send_query('oauth_688_a',$q$
  select public.connected_oauth_688_race_claim_v1('claim-delete',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('oauth_688_b',$q$
  select public.connected_oauth_688_race_delete_v1('claim-delete',0)::text
$q$);
insert into connected_oauth_688_race_results select 'claim-before-delete',value::jsonb
from public.dblink_get_result('oauth_688_a') as remote(value text);
insert into connected_oauth_688_race_results select 'delete-after-claim',value::jsonb
from public.dblink_get_result('oauth_688_b') as remote(value text);
select * from public.dblink_get_result('oauth_688_a') as remote(value text);
select * from public.dblink_get_result('oauth_688_b') as remote(value text);

-- Account deletion first makes recovery unavailable and leaves no orphan.
select public.connected_oauth_688_race_seed_v1('delete-first');
select public.dblink_send_query('oauth_688_a',$q$
  select public.connected_oauth_688_race_delete_v1('delete-first',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('oauth_688_b',$q$
  select public.connected_oauth_688_race_claim_v1('delete-first',0)::text
$q$);
insert into connected_oauth_688_race_results select 'delete-first',value::jsonb
from public.dblink_get_result('oauth_688_a') as remote(value text);
insert into connected_oauth_688_race_results select 'claim-after-delete',value::jsonb
from public.dblink_get_result('oauth_688_b') as remote(value text);
select * from public.dblink_get_result('oauth_688_a') as remote(value text);
select * from public.dblink_get_result('oauth_688_b') as remote(value text);

do $assert$
begin
  if (select value->>'ok' from connected_oauth_688_race_results
      where lane='claim-first')<>'true'
     or (select value->>'ok' from connected_oauth_688_race_results
         where lane='fence-after-claim')<>'true'
     or (select value->>'ok' from connected_oauth_688_race_results
         where lane='fence-first')<>'true'
     or (select value->>'ok' from connected_oauth_688_race_results
         where lane='claim-after-fence')<>'false'
     or (select value->>'sqlstate' from connected_oauth_688_race_results
         where lane='claim-after-fence')<>'55000' then
    raise exception 'claim/fence winner-order contract drifted: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_oauth_688_race_results);
  end if;
  if (select value->>'ok' from connected_oauth_688_race_results
      where lane='claim-before-delete')<>'true'
     or (select value->>'ok' from connected_oauth_688_race_results
         where lane='delete-after-claim')<>'true'
     or (select value->>'ok' from connected_oauth_688_race_results
         where lane='delete-first')<>'true'
     or (select value->>'ok' from connected_oauth_688_race_results
         where lane='claim-after-delete')<>'false'
     or exists(
       select 1 from connected_oauth_code_private.authorization_code_custody
       where owner_id in (
         public.connected_oauth_688_race_id_v1('claim-delete:owner'),
         public.connected_oauth_688_race_id_v1('delete-first:owner')
       )
     ) then
    raise exception 'claim/deletion winner-order contract drifted: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_oauth_688_race_results);
  end if;
end;
$assert$;

select public.dblink_disconnect('oauth_688_a');
select public.dblink_disconnect('oauth_688_b');

select 'CONNECTED_OAUTH_CODE_CUSTODY_RACES_OK' as result;
