\set ON_ERROR_STOP on

create extension if not exists dblink;

insert into public.users(id) values
  ('90000000-0000-4000-8000-000000000001');
insert into public.sessions(id, user_id, token_hash, expires_at) values (
  '90000000-0000-4000-8000-000000000002',
  '90000000-0000-4000-8000-000000000001', repeat('1', 64),
  pg_catalog.clock_timestamp() + interval '2 hours'
);
insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256, authorization_expires_at
) values (
  '90000000-0000-4000-8000-000000000003',
  '90000000-0000-4000-8000-000000000001',
  'google', 'mail', 'personal',
  '90000000-0000-4000-8000-000000000004',
  4, 'active', repeat('a', 64), array['mail.get'],
  repeat('b', 64), repeat('c', 64), repeat('d', 64),
  '90000000-0000-4000-8000-000000000005', repeat('e', 64),
  pg_catalog.clock_timestamp() + interval '2 hours'
);

do $race$
declare
  connection_string text := pg_catalog.format(
    'host=127.0.0.1 port=%s dbname=%s user=postgres',
    pg_catalog.current_setting('port'),
    pg_catalog.current_database()
  );
  requested_at timestamptz := pg_catalog.clock_timestamp();
  expires_at timestamptz := requested_at + interval '10 minutes';
  prepare_sql text;
  winner jsonb;
  replay jsonb;
begin
  prepare_sql := pg_catalog.format(
    $sql$
      select public.connected_app_operator_prepare_action_v1(
        '91000000-0000-4000-8000-000000000001',
        '90000000-0000-4000-8000-000000000001',
        '90000000-0000-4000-8000-000000000002',
        repeat('1', 64), repeat('6', 64),
        '92000000-0000-4000-8000-000000000001',
        '93000000-0000-4000-8000-000000000001',
        '94000000-0000-4000-8000-000000000001',
        '95000000-0000-4000-8000-000000000001',
        '90000000-0000-4000-8000-000000000003',
        'google', 'mail', 'mail.get', 4,
        repeat('a', 64), repeat('b', 64), repeat('c', 64), 1,
        '96000000-0000-4000-8000-000000000001',
        repeat('3', 64), repeat('4', 64), null,
        'connected-app-policy-v1', null, null, null, null, null,
        %L::timestamptz, %L::timestamptz
      )::text
    $sql$,
    requested_at,
    expires_at
  );

  perform public.dblink_connect('action_prepare_race_a', connection_string);
  perform public.dblink_connect('action_prepare_race_b', connection_string);
  perform public.dblink_exec('action_prepare_race_a', 'begin');
  perform public.dblink_exec('action_prepare_race_a', 'set local role service_role');
  select response::jsonb into winner
  from public.dblink('action_prepare_race_a', prepare_sql)
    as remote_result(response text);
  if winner->>'status' <> 'ready' then
    raise exception 'first preparation winner was invalid: %', winner;
  end if;

  perform public.dblink_exec('action_prepare_race_b', 'begin');
  perform public.dblink_exec('action_prepare_race_b', 'set local role service_role');
  if public.dblink_send_query('action_prepare_race_b', prepare_sql) <> 1 then
    raise exception 'second preparation race did not start';
  end if;
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('action_prepare_race_b') <> 1 then
    raise exception 'same-request preparation did not serialize';
  end if;

  perform public.dblink_exec('action_prepare_race_a', 'commit');
  select response::jsonb into replay
  from public.dblink_get_result('action_prepare_race_b')
    as remote_result(response text);
  perform response
  from public.dblink_get_result('action_prepare_race_b')
    as remote_result(response text);
  perform public.dblink_exec('action_prepare_race_b', 'commit');
  if replay is distinct from winner then
    raise exception 'same-request concurrent replay drifted: %, %', winner, replay;
  end if;

  perform public.dblink_disconnect('action_prepare_race_a');
  perform public.dblink_disconnect('action_prepare_race_b');
exception when others then
  begin
    perform public.dblink_disconnect('action_prepare_race_a');
  exception when others then null;
  end;
  begin
    perform public.dblink_disconnect('action_prepare_race_b');
  exception when others then null;
  end;
  raise;
end;
$race$;

do $verify$
begin
  if (
    select pg_catalog.count(*)
    from connected_app_private.action_preparations
    where request_id = '91000000-0000-4000-8000-000000000001'
  ) <> 1 or (
    select pg_catalog.count(*)
    from connected_app_private.task_grants
    where grant_id = '92000000-0000-4000-8000-000000000001'
  ) <> 1 or exists (
    select 1 from connected_app_private.action_ledger
    where action_id = '93000000-0000-4000-8000-000000000001'
  ) then
    raise exception 'concurrent preparation produced duplicate or executable state';
  end if;
end;
$verify$;

select 'CONNECTED_APP_ACTION_PREPARATION_RACE_OK' as result;
