\set ON_ERROR_STOP on

do $setup$
declare
  owner_id constant uuid := '87300000-0000-4000-8000-000000000001';
  connection_id constant uuid := '87300000-0000-4000-8000-000000000002';
  template_id constant uuid := '87300000-0000-4000-8000-000000000003';
  schedule_id constant uuid := '87300000-0000-4000-8000-000000000004';
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  delete from public.users where id=owner_id;
  if exists (
    select 1 from pg_catalog.pg_attribute
    where attrelid='public.users'::pg_catalog.regclass
      and attname='registration_environment' and attnum>0 and not attisdropped
  ) then
    insert into public.users(
      id,email,password_hash,is_verified,is_guest,created_at,updated_at,
      registration_environment,registration_submitted_at,
      password_setup_required,password_inbox_bound_at
    ) values(
      owner_id,'connected-schedule-race@example.test',
      '$argon2id$connected-schedule-race-password-hash-v1',true,false,
      now_at-interval '1 minute',now_at-interval '1 minute',
      'production',now_at,false,now_at
    );
  else
    insert into public.users(id) values(owner_id);
  end if;
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at,authorization_issued_at
  ) values(
    connection_id,owner_id,'google','mail','personal',
    '87300000-0000-4000-8000-000000000005',1,'active',repeat('1',64),
    array['mail.search'],repeat('2',64),repeat('3',64),repeat('4',64),
    '87300000-0000-4000-8000-000000000006',repeat('5',64),
    now_at+interval '1 day',now_at
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
    template_id,schedule_id,owner_id,
    '87300000-0000-4000-8000-000000000007',connection_id,
    '87300000-0000-4000-8000-000000000008',
    '87300000-0000-4000-8000-000000000009',repeat('6',64),
    'google','mail','mail.search',1,repeat('1',64),repeat('2',64),
    repeat('3',64),'schedule-race-commitment',repeat('7',64),null,
    repeat('8',64),'schedule-race-key',repeat('A',16),repeat('B',64),
    repeat('C',16),repeat('D',32),repeat('9',64),now_at,now_at
  );
  insert into connected_app_private.schedules(
    schedule_id,owner_id,connection_id,task_id,provider,resource,action,
    action_template_ref,parameters_sha256,task_state_revision,time_zone,
    cadence_seconds,requires_approval_every_run,status,next_run_at,
    created_at,updated_at
  ) values(
    schedule_id,owner_id,connection_id,
    '87300000-0000-4000-8000-000000000008','google','mail','mail.search',
    template_id,repeat('7',64),1,'UTC',3600,false,'active',
    now_at-interval '1 second',now_at,now_at
  );
end;
$setup$;

create temporary table connected_schedule_race_results(
  lane text primary key,
  value jsonb
) on commit preserve rows;

select public.dblink_connect(
  'schedule_claim_a',
  pg_catalog.format(
    'host=%L port=%L dbname=%L user=%L application_name=%L',
    '127.0.0.1',current_setting('port'),current_database(),current_user,
    'connected-schedule-claim-a'
  )
);
select public.dblink_connect(
  'schedule_claim_b',
  pg_catalog.format(
    'host=%L port=%L dbname=%L user=%L application_name=%L',
    '127.0.0.1',current_setting('port'),current_database(),current_user,
    'connected-schedule-claim-b'
  )
);
select public.dblink_send_query(
  'schedule_claim_a',
  $$select public.connected_app_claim_schedule_v2(
    '87300000-0000-4000-8000-000000000010',120)::text$$
);
select public.dblink_send_query(
  'schedule_claim_b',
  $$select public.connected_app_claim_schedule_v2(
    '87300000-0000-4000-8000-000000000011',120)::text$$
);
insert into connected_schedule_race_results(lane,value)
select 'claim-a',result::jsonb
from public.dblink_get_result('schedule_claim_a') as remote(result text);
insert into connected_schedule_race_results(lane,value)
select 'claim-b',result::jsonb
from public.dblink_get_result('schedule_claim_b') as remote(result text);

do $claim_check$
declare
  winner uuid;
begin
  if (select count(*) from connected_schedule_race_results where value is not null)<>1 then
    raise exception 'two-connection schedule claim race did not have exactly one winner';
  end if;
  select (value->>'claim_id')::uuid into strict winner
  from connected_schedule_race_results where value is not null;
  if winner not in (
       '87300000-0000-4000-8000-000000000010'::uuid,
       '87300000-0000-4000-8000-000000000011'::uuid
     )
     or (select claim_id from connected_app_private.schedules
         where schedule_id='87300000-0000-4000-8000-000000000004')<>winner
     or (select count(*) from connected_app_private.task_grants
         where task_id='87300000-0000-4000-8000-000000000008'
           and revoked_at is null)<>1 then
    raise exception 'schedule claim/grant winner was not exact';
  end if;
end;
$claim_check$;

truncate connected_schedule_race_results;

select public.dblink_disconnect('schedule_claim_a');
select public.dblink_disconnect('schedule_claim_b');
select public.dblink_connect(
  'schedule_claim_a',
  pg_catalog.format(
    'host=%L port=%L dbname=%L user=%L application_name=%L',
    '127.0.0.1',current_setting('port'),current_database(),current_user,
    'connected-schedule-finish-a'
  )
);
select public.dblink_connect(
  'schedule_claim_b',
  pg_catalog.format(
    'host=%L port=%L dbname=%L user=%L application_name=%L',
    '127.0.0.1',current_setting('port'),current_database(),current_user,
    'connected-schedule-finish-b'
  )
);

do $finish_race$
declare
  winner uuid;
  finished_at timestamptz := pg_catalog.clock_timestamp();
  statement text;
begin
  select claim_id into strict winner from connected_app_private.schedules
  where schedule_id='87300000-0000-4000-8000-000000000004';
  statement := pg_catalog.format(
    'select public.connected_app_finish_schedule_v2(%L,%L,%L,%L,1,%L,%L,%L,%L)::text',
    '87300000-0000-4000-8000-000000000012',
    '87300000-0000-4000-8000-000000000004',
    '87300000-0000-4000-8000-000000000001',winner,'read',
    '87300000-0000-4000-8000-000000000013',
    finished_at+interval '60 seconds',finished_at
  );
  if public.dblink_send_query('schedule_claim_a',statement)<>1
     or public.dblink_send_query('schedule_claim_b',statement)<>1 then
    raise exception 'could not launch two-connection finish race';
  end if;
end;
$finish_race$;

insert into connected_schedule_race_results(lane,value)
select 'finish-a',result::jsonb
from public.dblink_get_result('schedule_claim_a') as remote(result text);
insert into connected_schedule_race_results(lane,value)
select 'finish-b',result::jsonb
from public.dblink_get_result('schedule_claim_b') as remote(result text);

do $finish_check$
begin
  if (select count(*) from connected_schedule_race_results where value is not null)<>2
     or (select count(distinct value) from connected_schedule_race_results)<>1
     or (select count(*) from connected_schedule_private.run_completions
         where schedule_id='87300000-0000-4000-8000-000000000004')<>1
     or (select count(*) from connected_app_private.task_grants
         where task_id='87300000-0000-4000-8000-000000000008'
           and revoked_at is null)<>0 then
    raise exception 'durable finish replay race duplicated or drifted';
  end if;
end;
$finish_check$;

select public.dblink_disconnect('schedule_claim_a');
select public.dblink_disconnect('schedule_claim_b');
delete from public.users where id='87300000-0000-4000-8000-000000000001';

select 'CONNECTED_SCHEDULE_TEMPLATE_RACES_OK' as result;
