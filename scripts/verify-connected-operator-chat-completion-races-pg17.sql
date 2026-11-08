\set ON_ERROR_STOP on

create extension if not exists dblink;

insert into public.users(id) values
  ('61000000-0000-4000-8000-000000000001');
insert into public.sessions(id, user_id, expires_at) values (
  '61000000-0000-4000-8000-000000000002',
  '61000000-0000-4000-8000-000000000001',
  pg_catalog.statement_timestamp() + interval '1 hour'
);

set role service_role;
select * from public.connected_chat_claim_turn_v1(
  '61000000-0000-4000-8000-000000000001',
  '61000000-0000-4000-8000-000000000003',
  '61000000-0000-4000-8000-000000000004',
  repeat('a', 64), repeat('b', 64)
);
reset role;

do $race$
declare
  v_owner_id constant uuid := '61000000-0000-4000-8000-000000000001';
  v_chat_id constant uuid := '61000000-0000-4000-8000-000000000003';
  v_message_id constant uuid := '61000000-0000-4000-8000-000000000004';
  v_assistant_id constant uuid := '61000000-0000-4000-8000-000000000005';
  turn_id uuid;
  claim_token uuid;
  connection_string text := pg_catalog.format(
    'host=127.0.0.1 port=%s dbname=%s user=postgres',
    pg_catalog.current_setting('port'),
    pg_catalog.current_database()
  );
  complete_sql text;
  user_message jsonb := pg_catalog.jsonb_build_object(
    'id', v_message_id, 'role', 'user', 'content', 'private race input'
  );
  assistant_message jsonb := pg_catalog.jsonb_build_object(
    'id', v_assistant_id, 'role', 'assistant', 'inReplyTo', v_message_id,
    'content', 'private race result'
  );
  response_data jsonb;
  winner jsonb;
  replay jsonb;
begin
  select turn.turn_id, job.claim_token into strict turn_id, claim_token
  from connected_chat_private.turns as turn
  join public.chat_jobs as job on job.id = turn.job_id
  where turn.owner_id = v_owner_id and turn.message_id = v_message_id;
  response_data := pg_catalog.jsonb_build_object(
    'response', 'private race result',
    'assistantMessage', assistant_message,
    'connectedApp', pg_catalog.jsonb_build_object('state', 'delegated')
  );
  complete_sql := pg_catalog.format(
    $sql$
      select public.connected_operator_complete_chat_v1(
        '61000000-0000-4000-8000-000000000006',
        %L::uuid,
        '61000000-0000-4000-8000-000000000002',
        %L::uuid,
        %L::uuid,
        %L::uuid,
        %L::uuid,
        %L::uuid,
        repeat('a', 64), repeat('b', 64), 'delegated',
        'chat-completion-key-1', repeat('c', 64), 'Race check',
        %L::jsonb, %L::jsonb, %L::jsonb
      )::text
    $sql$,
    v_owner_id, turn_id, v_chat_id, v_message_id, v_assistant_id, claim_token,
    user_message::text, assistant_message::text, response_data::text
  );

  perform public.dblink_connect('chat_complete_race_a', connection_string);
  perform public.dblink_connect('chat_complete_race_b', connection_string);
  perform public.dblink_exec('chat_complete_race_a', 'begin');
  perform public.dblink_exec('chat_complete_race_a', 'set local role service_role');
  select remote_result.response::jsonb into strict winner
  from public.dblink('chat_complete_race_a', complete_sql)
    as remote_result(response text);

  perform public.dblink_exec('chat_complete_race_b', 'begin');
  perform public.dblink_exec('chat_complete_race_b', 'set local role service_role');
  if public.dblink_send_query('chat_complete_race_b', complete_sql) <> 1 then
    raise exception 'second chat completion race did not start';
  end if;
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('chat_complete_race_b') <> 1 then
    raise exception 'same-turn chat completion did not serialize';
  end if;

  perform public.dblink_exec('chat_complete_race_a', 'commit');
  select remote_result.response::jsonb into strict replay
  from public.dblink_get_result('chat_complete_race_b')
    as remote_result(response text);
  perform response
  from public.dblink_get_result('chat_complete_race_b')
    as remote_result(response text);
  perform public.dblink_exec('chat_complete_race_b', 'commit');
  if replay is distinct from winner then
    raise exception 'same-turn concurrent replay drifted';
  end if;

  perform public.dblink_disconnect('chat_complete_race_a');
  perform public.dblink_disconnect('chat_complete_race_b');
exception when others then
  begin
    perform public.dblink_disconnect('chat_complete_race_a');
  exception when others then null;
  end;
  begin
    perform public.dblink_disconnect('chat_complete_race_b');
  exception when others then null;
  end;
  raise;
end;
$race$;

do $verify$
declare
  v_owner_id constant uuid := '61000000-0000-4000-8000-000000000001';
  messages jsonb;
begin
  select chat.messages into strict messages
  from public.user_chats as chat
  where chat.user_id = v_owner_id
    and chat.chat_id = '61000000-0000-4000-8000-000000000003';
  if pg_catalog.jsonb_array_length(messages) <> 2
     or (
       select pg_catalog.count(*)
       from connected_chat_completion_private.completions as completion
       where completion.owner_id = v_owner_id
     ) <> 1
     or not exists (
       select 1 from public.chat_jobs as job
       where job.user_id = v_owner_id
         and job.status = 'completed' and job.claim_token is null
     )
     or not exists (
       select 1 from connected_chat_private.turns as turn
       where turn.owner_id = v_owner_id and turn.stage = 'terminal'
     ) then
    raise exception 'concurrent completion produced duplicate or partial state';
  end if;
end;
$verify$;

delete from public.users
where id = '61000000-0000-4000-8000-000000000001';

select 'CONNECTED_OPERATOR_CHAT_COMPLETION_RACE_OK' as result;
