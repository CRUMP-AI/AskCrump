\set ON_ERROR_STOP on

create or replace function public.connected_retention_race_id_v1(p_value text)
returns uuid language sql immutable set search_path='' as $fn$
  select (
    pg_catalog.substr(pg_catalog.md5(p_value),1,8)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),9,4)||'-4'||
    pg_catalog.substr(pg_catalog.md5(p_value),14,3)||'-8'||
    pg_catalog.substr(pg_catalog.md5(p_value),18,3)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),21,12)
  )::uuid
$fn$;

create or replace function public.connected_retention_race_sha_v1(p_value text)
returns text language sql immutable set search_path='' as $fn$
  select pg_catalog.md5(p_value||':left')||pg_catalog.md5(p_value||':right')
$fn$;

create or replace function public.connected_retention_race_seed_v1(
  p_lane text,p_with_payload boolean
) returns void language plpgsql set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  owner_id uuid:=public.connected_retention_race_id_v1(p_lane||':owner');
  connection_id uuid:=public.connected_retention_race_id_v1(p_lane||':connection');
begin
  delete from public.users where id=owner_id;
  -- Test-only reset after a prior interrupted verification run.  Production
  -- has no public tombstone deletion authority.
  delete from connected_app_private.payload_tombstones
  where payload_id=public.connected_retention_race_id_v1(p_lane||':payload');
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(owner_id,owner_id::text||'@retention-race.example.test',
    '$argon2id$retention-race-v1',true,false,now_at-interval '1 day',now_at,
    'production',now_at-interval '1 day',false,now_at-interval '1 day');
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at
  ) values(connection_id,owner_id,'google','mail','personal',
    public.connected_retention_race_id_v1(p_lane||':incarnation'),1,'active',
    public.connected_retention_race_sha_v1(p_lane||':authorization'),
    array['mail.send'],public.connected_retention_race_sha_v1(p_lane||':actions'),
    public.connected_retention_race_sha_v1(p_lane||':scopes'),
    public.connected_retention_race_sha_v1(p_lane||':external'),
    public.connected_retention_race_id_v1(p_lane||':credential'),
    public.connected_retention_race_sha_v1(p_lane||':credential-handle'),
    now_at+interval '1 day');
  if p_with_payload then
    perform public.connected_app_payload_put_v1(
      public.connected_retention_race_id_v1(p_lane||':payload'),owner_id,
      connection_id,public.connected_retention_race_id_v1(p_lane||':action'),
      'google','mail.send','retention-race-commitment',
      public.connected_retention_race_sha_v1(p_lane||':payload-sha'),
      now_at-interval '2 hours',now_at-interval '1 hour',
      public.connected_retention_race_sha_v1(p_lane||':identity'),
      public.connected_retention_race_sha_v1(p_lane||':reference'),
      'retention-race-envelope',repeat('A',16),repeat('B',64),repeat('C',16),
      repeat('D',64),public.connected_retention_race_sha_v1(p_lane||':record'));
  end if;
end;
$fn$;

create or replace function public.connected_retention_race_purge_v1(
  p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  begin
    result:=public.connected_app_purge_expired_ciphertext_v1(100,100,100);
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_retention_race_put_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare now_at timestamptz:=pg_catalog.clock_timestamp(); result jsonb;
begin
  begin
    result:=public.connected_app_payload_put_v1(
      public.connected_retention_race_id_v1(p_lane||':payload'),
      public.connected_retention_race_id_v1(p_lane||':owner'),
      public.connected_retention_race_id_v1(p_lane||':connection'),
      public.connected_retention_race_id_v1(p_lane||':action'),
      'google','mail.send','retention-race-commitment',
      public.connected_retention_race_sha_v1(p_lane||':payload-sha'),
      now_at-interval '2 hours',now_at-interval '1 hour',
      public.connected_retention_race_sha_v1(p_lane||':identity'),
      public.connected_retention_race_sha_v1(p_lane||':reference'),
      'retention-race-envelope',repeat('A',16),repeat('B',64),repeat('C',16),
      repeat('D',64),public.connected_retention_race_sha_v1(p_lane||':record'));
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_retention_race_read_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
declare result jsonb;
begin
  begin
    result:=public.connected_app_payload_read_v1(
      public.connected_retention_race_id_v1(p_lane||':payload'),
      public.connected_retention_race_sha_v1(p_lane||':identity'));
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true,'value',result);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create or replace function public.connected_retention_race_delete_owner_v1(
  p_lane text,p_delay numeric
) returns jsonb language plpgsql set search_path='' as $fn$
begin
  begin
    delete from public.users
    where id=public.connected_retention_race_id_v1(p_lane||':owner');
    perform pg_catalog.pg_sleep(p_delay);
    return pg_catalog.jsonb_build_object('ok',true);
  exception when others then
    return pg_catalog.jsonb_build_object('ok',false,'sqlstate',sqlstate);
  end;
end;
$fn$;

create temporary table connected_retention_race_results(
  lane text primary key,value jsonb not null
) on commit preserve rows;

select public.dblink_connect('retention_a',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'retention-race-a'));
select public.dblink_connect('retention_b',pg_catalog.format(
  'host=%L port=%L dbname=%L user=%L application_name=%L',
  '127.0.0.1',current_setting('port'),current_database(),current_user,
  'retention-race-b'));

-- Two workers observe the same expired row; only one may count its erasure.
select public.connected_retention_race_seed_v1('retention-two-worker',true);
select public.dblink_send_query('retention_a',
  'select public.connected_retention_race_purge_v1(0.25)::text');
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_b',
  'select public.connected_retention_race_purge_v1(0)::text');
insert into connected_retention_race_results select 'two-a',value::jsonb
from public.dblink_get_result('retention_a') as remote(value text);
insert into connected_retention_race_results select 'two-b',value::jsonb
from public.dblink_get_result('retention_b') as remote(value text);
select * from public.dblink_get_result('retention_a') as remote(value text);
select * from public.dblink_get_result('retention_b') as remote(value text);

-- Purge wins before a replaying put; the permanent tombstone is returned.
select public.connected_retention_race_seed_v1('retention-purge-put',true);
select public.dblink_send_query('retention_a',
  'select public.connected_retention_race_purge_v1(0.25)::text');
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_b',$q$
  select public.connected_retention_race_put_v1('retention-purge-put',0)::text
$q$);
insert into connected_retention_race_results select 'purge-put-a',value::jsonb
from public.dblink_get_result('retention_a') as remote(value text);
insert into connected_retention_race_results select 'purge-put-b',value::jsonb
from public.dblink_get_result('retention_b') as remote(value text);
select * from public.dblink_get_result('retention_a') as remote(value text);
select * from public.dblink_get_result('retention_b') as remote(value text);

-- Put wins from an absent row.  The concurrent scan cannot see an uncommitted
-- insert; the next bounded cycle deterministically erases it.
select public.connected_retention_race_seed_v1('retention-put-purge',false);
select public.dblink_send_query('retention_a',$q$
  select public.connected_retention_race_put_v1('retention-put-purge',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_b',
  'select public.connected_retention_race_purge_v1(0)::text');
insert into connected_retention_race_results select 'put-purge-a',value::jsonb
from public.dblink_get_result('retention_a') as remote(value text);
insert into connected_retention_race_results select 'put-purge-b',value::jsonb
from public.dblink_get_result('retention_b') as remote(value text);
select * from public.dblink_get_result('retention_a') as remote(value text);
select * from public.dblink_get_result('retention_b') as remote(value text);
insert into connected_retention_race_results(lane,value)
values('put-purge-next',public.connected_retention_race_purge_v1(0));

-- Read holds the shared payload fence first, then purge erases.
select public.connected_retention_race_seed_v1('retention-read-purge',true);
select public.dblink_send_query('retention_a',$q$
  select public.connected_retention_race_read_v1('retention-read-purge',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_b',
  'select public.connected_retention_race_purge_v1(0)::text');
insert into connected_retention_race_results select 'read-purge-a',value::jsonb
from public.dblink_get_result('retention_a') as remote(value text);
insert into connected_retention_race_results select 'read-purge-b',value::jsonb
from public.dblink_get_result('retention_b') as remote(value text);
select * from public.dblink_get_result('retention_a') as remote(value text);
select * from public.dblink_get_result('retention_b') as remote(value text);

-- Purge holds the fence first; the reader observes only the tombstone.
select public.connected_retention_race_seed_v1('retention-purge-read',true);
select public.dblink_send_query('retention_a',
  'select public.connected_retention_race_purge_v1(0.25)::text');
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_b',$q$
  select public.connected_retention_race_read_v1('retention-purge-read',0)::text
$q$);
insert into connected_retention_race_results select 'purge-read-a',value::jsonb
from public.dblink_get_result('retention_a') as remote(value text);
insert into connected_retention_race_results select 'purge-read-b',value::jsonb
from public.dblink_get_result('retention_b') as remote(value text);
select * from public.dblink_get_result('retention_a') as remote(value text);
select * from public.dblink_get_result('retention_b') as remote(value text);

-- Account deletion owns the canonical owner lock before purge.
select public.connected_retention_race_seed_v1('retention-delete-purge',true);
select public.dblink_send_query('retention_a',$q$
  select public.connected_retention_race_delete_owner_v1(
    'retention-delete-purge',0.25)::text
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_b',
  'select public.connected_retention_race_purge_v1(0)::text');
insert into connected_retention_race_results select 'delete-purge-a',value::jsonb
from public.dblink_get_result('retention_a') as remote(value text);
insert into connected_retention_race_results select 'delete-purge-b',value::jsonb
from public.dblink_get_result('retention_b') as remote(value text);
select * from public.dblink_get_result('retention_a') as remote(value text);
select * from public.dblink_get_result('retention_b') as remote(value text);

-- Purge owns the owner lock first; deletion waits and then removes the owner.
select public.connected_retention_race_seed_v1('retention-purge-delete',true);
select public.dblink_send_query('retention_a',
  'select public.connected_retention_race_purge_v1(0.25)::text');
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('retention_b',$q$
  select public.connected_retention_race_delete_owner_v1(
    'retention-purge-delete',0)::text
$q$);
insert into connected_retention_race_results select 'purge-delete-a',value::jsonb
from public.dblink_get_result('retention_a') as remote(value text);
insert into connected_retention_race_results select 'purge-delete-b',value::jsonb
from public.dblink_get_result('retention_b') as remote(value text);
select * from public.dblink_get_result('retention_a') as remote(value text);
select * from public.dblink_get_result('retention_b') as remote(value text);

do $check$
begin
  if exists(select 1 from connected_retention_race_results
            where value->>'ok'<>'true') then
    raise exception 'retention race raised: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_retention_race_results);
  end if;
  if (select ((value->'value'->>'payloads_purged')::integer)
      from connected_retention_race_results where lane='two-a')<>1
     or (select ((value->'value'->>'payloads_purged')::integer)
         from connected_retention_race_results where lane='two-b')<>0
     or (select value->'value'->>'status'
         from connected_retention_race_results where lane='purge-put-b')<>'erased'
     or (select value->'value'->>'status'
         from connected_retention_race_results where lane='put-purge-a')<>'present'
     or (select value->'value'->>'status'
         from connected_retention_race_results where lane='read-purge-a')<>'present'
     or (select value->'value'->>'status'
         from connected_retention_race_results where lane='purge-read-b')<>'erased'
     or (select (value->'value'->>'payloads_purged')::integer
         from connected_retention_race_results where lane='put-purge-next')<1
     or exists(select 1 from public.users where id in(
          public.connected_retention_race_id_v1('retention-delete-purge:owner'),
          public.connected_retention_race_id_v1('retention-purge-delete:owner'))) then
    raise exception 'retention race winner result drifted: %',
      (select pg_catalog.jsonb_object_agg(lane,value)
       from connected_retention_race_results);
  end if;
  if exists(select 1 from connected_app_private.payload_envelopes
       where payload_id=public.connected_retention_race_id_v1(
         'retention-put-purge:payload')) then
    raise exception 'put-first retention was not erased on the next cycle';
  end if;
end;
$check$;

select public.dblink_disconnect('retention_a');
select public.dblink_disconnect('retention_b');

do $cleanup$
declare lane text;
begin
  foreach lane in array array[
    'retention-two-worker','retention-purge-put','retention-put-purge',
    'retention-read-purge','retention-purge-read','retention-delete-purge',
    'retention-purge-delete']
  loop
    delete from public.users
    where id=public.connected_retention_race_id_v1(lane||':owner');
  end loop;
end;
$cleanup$;

drop function public.connected_retention_race_delete_owner_v1(text,numeric);
drop function public.connected_retention_race_read_v1(text,numeric);
drop function public.connected_retention_race_put_v1(text,numeric);
drop function public.connected_retention_race_purge_v1(numeric);
drop function public.connected_retention_race_seed_v1(text,boolean);
drop function public.connected_retention_race_sha_v1(text);
drop function public.connected_retention_race_id_v1(text);

select 'CONNECTED_CIPHERTEXT_RETENTION_RACES_OK' as result;
