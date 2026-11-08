\set ON_ERROR_STOP on

create extension if not exists dblink;

insert into public.users(id,created_at,registration_environment) values (
  'b1000000-0000-4000-8000-000000000001',
  pg_catalog.clock_timestamp(),'development'
);
insert into connected_app_private.connections (
  id,owner_id,provider,resource,account_kind,connection_incarnation_id,
  authorization_revision,authorization_state,authorization_snapshot_sha256,
  granted_actions,granted_actions_sha256,granted_scopes_sha256,
  external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
  authorization_expires_at
) values (
  'b2000000-0000-4000-8000-000000000001',
  'b1000000-0000-4000-8000-000000000001',
  'google','mail','personal','b2000000-0000-4000-8000-000000000002',
  1,'active',repeat('a',64),array['mail.send'],repeat('b',64),
  repeat('c',64),repeat('d',64),
  'b2000000-0000-4000-8000-000000000003',repeat('e',64),
  pg_catalog.clock_timestamp()+interval '2 hours'
);
insert into connected_app_private.task_grants (
  grant_id,owner_id,task_id,turn_id,connection_id,provider,resource,
  authorization_revision,authorization_snapshot_sha256,actions,
  actions_sha256,task_state_revision,expires_at
) values (
  'b3000000-0000-4000-8000-000000000001',
  'b1000000-0000-4000-8000-000000000001',
  'b3000000-0000-4000-8000-000000000002',
  'b3000000-0000-4000-8000-000000000003',
  'b2000000-0000-4000-8000-000000000001',
  'google','mail',1,repeat('a',64),array['mail.send'],repeat('b',64),1,
  pg_catalog.clock_timestamp()+interval '1 hour'
);
insert into connected_app_private.approvals (
  approval_id,action_id,owner_id,task_id,turn_id,connection_id,
  provider,resource,action,authorization_revision,
  authorization_snapshot_sha256,approval_class,parameters_sha256,
  resource_version_sha256,approval_binding_sha256,approved_at,expires_at
) values
(
  'b4000000-0000-4000-8000-000000000001',
  'b5000000-0000-4000-8000-000000000001',
  'b1000000-0000-4000-8000-000000000001',
  'b3000000-0000-4000-8000-000000000002',
  'b3000000-0000-4000-8000-000000000003',
  'b2000000-0000-4000-8000-000000000001',
  'google','mail','mail.send',1,repeat('a',64),
  'external_communication',repeat('4',64),null,repeat('5',64),
  pg_catalog.clock_timestamp()-interval '1 minute',
  pg_catalog.clock_timestamp()+interval '10 minutes'
),
(
  'b4000000-0000-4000-8000-000000000002',
  'b5000000-0000-4000-8000-000000000002',
  'b1000000-0000-4000-8000-000000000001',
  'b3000000-0000-4000-8000-000000000002',
  'b3000000-0000-4000-8000-000000000003',
  'b2000000-0000-4000-8000-000000000001',
  'google','mail','mail.send',1,repeat('a',64),
  'external_communication',repeat('4',64),null,repeat('6',64),
  pg_catalog.clock_timestamp()-interval '1 minute',
  pg_catalog.clock_timestamp()+interval '10 minutes'
);

set role service_role;
do $prepare$
declare
  result jsonb;
  expiry timestamptz:=pg_catalog.clock_timestamp()+interval '80 seconds';
  operation_id uuid;
  claim_id uuid;
  access_nonce uuid;
begin
  for operation_id,claim_id,access_nonce in values
    ('b5000000-0000-4000-8000-000000000001'::uuid,
     'b6000000-0000-4000-8000-000000000001'::uuid,
     'b7000000-0000-4000-8000-000000000001'::uuid),
    ('b5000000-0000-4000-8000-000000000002'::uuid,
     'b6000000-0000-4000-8000-000000000002'::uuid,
     'b7000000-0000-4000-8000-000000000002'::uuid)
  loop
    result:=public.connected_app_claim_action_v2(
    operation_id,operation_id,
    'b1000000-0000-4000-8000-000000000001',
    'b3000000-0000-4000-8000-000000000002',
    'b3000000-0000-4000-8000-000000000003',
    'b2000000-0000-4000-8000-000000000001',
    'b3000000-0000-4000-8000-000000000001',
    'google','mail','mail.send',1,repeat('a',64),repeat('b',64),
    repeat('c',64),repeat('4',64),null,repeat('8',64),
    repeat(pg_catalog.right(operation_id::text,1),64),
    repeat(pg_catalog.right(operation_id::text,1),64),1,
    claim_id,claim_id,120,
    pg_catalog.clock_timestamp()+interval '5 minutes'
  );
  result:=public.connected_app_begin_access_v1(
    operation_id,
    'b1000000-0000-4000-8000-000000000001',
    claim_id,
    (result->>'fencing_token')::bigint,repeat('b',64),'preobserve',
    access_nonce,expiry
  );
  perform public.connected_app_consume_credential_lease_v1(
    operation_id,
    'b1000000-0000-4000-8000-000000000001',
    'b2000000-0000-4000-8000-000000000001',
    operation_id,'mail.send',claim_id,
    (result->>'fencing_token')::bigint,'preobserve',
    access_nonce,expiry,1,
    repeat('a',64),repeat('b',64),repeat('c',64),repeat('8',64),1
  );
  end loop;
end;
$prepare$;
reset role;

create or replace function public.connected_approval_effect_race_probe(
  p_operation_id uuid,p_approval_id uuid,p_claim_id uuid,
  p_approval_binding_sha256 text,p_nonce uuid,p_label text,p_delay numeric
)
returns text language plpgsql security invoker set search_path='' as $fn$
declare
  fence bigint;
  action_result jsonb;
begin
  action_result:=public.connected_app_read_action_v2(
    'b1000000-0000-4000-8000-000000000001',
    p_operation_id,repeat(pg_catalog.right(p_operation_id::text,1),64),
    repeat(pg_catalog.right(p_operation_id::text,1),64)
  );
  fence:=(action_result->>'fencing_token')::bigint;
  perform public.connected_app_consume_approval_and_begin_effect_v1(
    p_approval_id,p_operation_id,
    'b1000000-0000-4000-8000-000000000001',
    p_claim_id,fence,p_approval_binding_sha256,
    repeat('b',64),p_nonce,pg_catalog.clock_timestamp()+interval '60 seconds'
  );
  perform pg_catalog.pg_sleep(p_delay);
  return p_label||':success';
exception when sqlstate '55000' then
  return p_label||':refused';
end;
$fn$;
revoke all on function public.connected_approval_effect_race_probe(
  uuid,uuid,uuid,text,uuid,text,numeric
)
  from public,anon,authenticated;
grant execute on function public.connected_approval_effect_race_probe(
  uuid,uuid,uuid,text,uuid,text,numeric
)
  to service_role;

select public.dblink_connect(
  'approval_effect_race_a',
  'host=127.0.0.1 port='||pg_catalog.current_setting('port')||
  ' dbname='||pg_catalog.current_database()||' user=postgres'
);
select public.dblink_connect(
  'approval_effect_race_b',
  'host=127.0.0.1 port='||pg_catalog.current_setting('port')||
  ' dbname='||pg_catalog.current_database()||' user=postgres'
);
select public.dblink_exec('approval_effect_race_a','set role service_role');
select public.dblink_exec('approval_effect_race_b','set role service_role');
create temporary table approval_effect_race_results(
  lane text primary key,value text not null
);

-- Hold the winner's owner advisory lock until the competing request has
-- arrived, then reverse the dispatch order on a distinct operation.  This
-- proves both winner orders rather than relying on scheduler timing.
select public.dblink_send_query('approval_effect_race_a',$q$
  select public.connected_approval_effect_race_probe(
    'b5000000-0000-4000-8000-000000000001',
    'b4000000-0000-4000-8000-000000000001',
    'b6000000-0000-4000-8000-000000000001',repeat('5',64),
    'b8000000-0000-4000-8000-000000000001','a-first',0.25)
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('approval_effect_race_b',$q$
  select public.connected_approval_effect_race_probe(
    'b5000000-0000-4000-8000-000000000001',
    'b4000000-0000-4000-8000-000000000001',
    'b6000000-0000-4000-8000-000000000001',repeat('5',64),
    'b8000000-0000-4000-8000-000000000002','b-second',0)
$q$);
insert into approval_effect_race_results
  select 'a-first',value from public.dblink_get_result('approval_effect_race_a')
    as result(value text);
insert into approval_effect_race_results
  select 'b-second',value from public.dblink_get_result('approval_effect_race_b')
    as result(value text);
select * from public.dblink_get_result('approval_effect_race_a')
  as result(value text);
select * from public.dblink_get_result('approval_effect_race_b')
  as result(value text);

select public.dblink_send_query('approval_effect_race_b',$q$
  select public.connected_approval_effect_race_probe(
    'b5000000-0000-4000-8000-000000000002',
    'b4000000-0000-4000-8000-000000000002',
    'b6000000-0000-4000-8000-000000000002',repeat('6',64),
    'b8000000-0000-4000-8000-000000000004','b-first',0.25)
$q$);
select pg_catalog.pg_sleep(0.05);
select public.dblink_send_query('approval_effect_race_a',$q$
  select public.connected_approval_effect_race_probe(
    'b5000000-0000-4000-8000-000000000002',
    'b4000000-0000-4000-8000-000000000002',
    'b6000000-0000-4000-8000-000000000002',repeat('6',64),
    'b8000000-0000-4000-8000-000000000003','a-second',0)
$q$);
insert into approval_effect_race_results
  select 'b-first',value from public.dblink_get_result('approval_effect_race_b')
    as result(value text);
insert into approval_effect_race_results
  select 'a-second',value from public.dblink_get_result('approval_effect_race_a')
    as result(value text);
select * from public.dblink_get_result('approval_effect_race_a')
  as result(value text);
select * from public.dblink_get_result('approval_effect_race_b')
  as result(value text);

do $verify$
begin
  if (select value from approval_effect_race_results
      where lane='a-first')<>'a-first:success'
     or (select value from approval_effect_race_results
         where lane='b-second')<>'b-second:refused'
     or (select value from approval_effect_race_results
         where lane='b-first')<>'b-first:success'
     or (select value from approval_effect_race_results
         where lane='a-second')<>'a-second:refused'
     or not exists(
       select 1 from connected_app_private.approvals as approval
       where approval.approval_id='b4000000-0000-4000-8000-000000000001'
         and approval.consumed_by_operation_id=
           'b5000000-0000-4000-8000-000000000001'
         and approval.consumed_at is not null)
     or not exists(
       select 1 from connected_app_private.approvals as approval
       where approval.approval_id='b4000000-0000-4000-8000-000000000002'
         and approval.consumed_by_operation_id=
           'b5000000-0000-4000-8000-000000000002'
         and approval.consumed_at is not null)
     or not exists(
       select 1 from connected_app_private.action_ledger as ledger
       where ledger.operation_id='b5000000-0000-4000-8000-000000000001'
         and ledger.status='effect_possible'
         and ledger.effect_use_nonce=
           'b8000000-0000-4000-8000-000000000001')
     or not exists(
       select 1 from connected_app_private.action_ledger as ledger
       where ledger.operation_id='b5000000-0000-4000-8000-000000000002'
         and ledger.status='effect_possible'
         and ledger.effect_use_nonce=
           'b8000000-0000-4000-8000-000000000004') then
    raise exception 'approval-effect both-winner race drifted: %',
      (select pg_catalog.jsonb_object_agg(lane,value order by lane)
       from approval_effect_race_results);
  end if;
end;
$verify$;

select public.dblink_disconnect('approval_effect_race_a');
select public.dblink_disconnect('approval_effect_race_b');
drop function public.connected_approval_effect_race_probe(
  uuid,uuid,uuid,text,uuid,text,numeric
);
delete from public.users
where id='b1000000-0000-4000-8000-000000000001';

select 'CONNECTED_APPROVAL_EFFECT_RACE_OK' as result;
