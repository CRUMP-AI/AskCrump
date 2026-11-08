\set ON_ERROR_STOP on

create extension if not exists dblink;

do $setup$
declare
  claim_row record;
  requested_at timestamptz := pg_catalog.clock_timestamp();
begin
  insert into public.users(id)
  values ('30000000-0000-4000-8000-000000000001');
  insert into public.sessions(id,user_id,expires_at)
  values (
    '30000000-0000-4000-8000-000000000002',
    '30000000-0000-4000-8000-000000000001',
    requested_at + interval '1 day'
  );
  select * into claim_row from public.connected_chat_claim_turn_v1(
    '30000000-0000-4000-8000-000000000001',
    '30000000-0000-4000-8000-000000000003',
    '30000000-0000-4000-8000-000000000004',
    repeat('a',64), repeat('b',64)
  );
  perform public.connected_plan_begin_v1(
    '30000000-0000-4000-8000-000000000001',
    '30000000-0000-4000-8000-000000000002',
    '30000000-0000-4000-8000-000000000003',
    '30000000-0000-4000-8000-000000000004',
    claim_row.turn_id, claim_row.claim_token, repeat('a',64), repeat('b',64),
    '30000000-0000-4000-8000-000000000005', 'plan-bind-1', repeat('c',64),
    '30000000-0000-4000-8000-000000000006', requested_at,
    requested_at + interval '15 minutes'
  );
end;
$setup$;

select public.dblink_connect(
  'plan_race_a',
  'host=127.0.0.1 port=' || pg_catalog.current_setting('port') ||
  ' dbname=' || current_database() || ' user=postgres password=postgres'
);
select public.dblink_connect(
  'plan_race_b',
  'host=127.0.0.1 port=' || pg_catalog.current_setting('port') ||
  ' dbname=' || current_database() || ' user=postgres password=postgres'
);

select public.dblink_send_query('plan_race_a', $query$
  select (public.connected_plan_mark_invoked_v1(
    '30000000-0000-4000-8000-000000000001'::uuid,
    '30000000-0000-4000-8000-000000000002'::uuid,
    '30000000-0000-4000-8000-000000000003'::uuid,
    '30000000-0000-4000-8000-000000000004'::uuid,
    turn.turn_id, job.claim_token, repeat('a',64), repeat('b',64),
    operation.planning_id, operation.planning_binding_key_id,
    operation.planning_binding_sha256, operation.payload_id,
    operation.requested_at, operation.expires_at,
    '30000000-0000-4000-8000-000000000007'::uuid
  )->>'invoke_permitted')::text
  from connected_plan_private.operations as operation
  join connected_chat_private.turns as turn on turn.turn_id = operation.turn_id
  join public.chat_jobs as job on job.id = turn.job_id
  where operation.planning_id = '30000000-0000-4000-8000-000000000005'::uuid
$query$);
select public.dblink_send_query('plan_race_b', $query$
  select (public.connected_plan_mark_invoked_v1(
    '30000000-0000-4000-8000-000000000001'::uuid,
    '30000000-0000-4000-8000-000000000002'::uuid,
    '30000000-0000-4000-8000-000000000003'::uuid,
    '30000000-0000-4000-8000-000000000004'::uuid,
    turn.turn_id, job.claim_token, repeat('a',64), repeat('b',64),
    operation.planning_id, operation.planning_binding_key_id,
    operation.planning_binding_sha256, operation.payload_id,
    operation.requested_at, operation.expires_at,
    '30000000-0000-4000-8000-000000000007'::uuid
  )->>'invoke_permitted')::text
  from connected_plan_private.operations as operation
  join connected_chat_private.turns as turn on turn.turn_id = operation.turn_id
  join public.chat_jobs as job on job.id = turn.job_id
  where operation.planning_id = '30000000-0000-4000-8000-000000000005'::uuid
$query$);

create temporary table plan_race_results(value text);
insert into plan_race_results select value from public.dblink_get_result('plan_race_a') as result(value text);
insert into plan_race_results select value from public.dblink_get_result('plan_race_b') as result(value text);

do $assert$
begin
  if (select count(*) from plan_race_results where value = 'true') <> 1
     or (select count(*) from plan_race_results where value = 'false') <> 1
     or (select count(*) from connected_plan_private.operations
         where planning_id = '30000000-0000-4000-8000-000000000005'
           and state = 'invoked'
           and invocation_id = '30000000-0000-4000-8000-000000000007') <> 1 then
    raise exception 'connected plan invocation race did not produce one winner: %',
      (select pg_catalog.jsonb_agg(value order by value) from plan_race_results);
  end if;
end;
$assert$;

select public.dblink_disconnect('plan_race_a');
select public.dblink_disconnect('plan_race_b');
delete from public.users where id = '30000000-0000-4000-8000-000000000001';

select 'CONNECTED_PLAN_ONCE_RACE_OK' as result;
