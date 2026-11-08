\set ON_ERROR_STOP on

insert into public.users(id) values
  ('60000000-0000-4000-8000-000000000001'),
  ('60000000-0000-4000-8000-000000000002');
insert into public.sessions(id, user_id, expires_at) values
  (
    '60000000-0000-4000-8000-000000000011',
    '60000000-0000-4000-8000-000000000001',
    pg_catalog.statement_timestamp() + interval '1 hour'
  ),
  (
    '60000000-0000-4000-8000-000000000012',
    '60000000-0000-4000-8000-000000000002',
    pg_catalog.statement_timestamp() + interval '1 hour'
  );

set role service_role;

do $test$
declare
  owner_id constant uuid := '60000000-0000-4000-8000-000000000001';
  session_id constant uuid := '60000000-0000-4000-8000-000000000011';
  chat_id constant uuid := '60000000-0000-4000-8000-000000000021';
  message_id constant uuid := '60000000-0000-4000-8000-000000000022';
  assistant_id constant uuid := '60000000-0000-4000-8000-000000000023';
  completion_id constant uuid := '60000000-0000-4000-8000-000000000024';
  turn_id uuid;
  claim_token uuid;
  response jsonb;
  replay jsonb;
  readback jsonb;
  user_message jsonb := pg_catalog.jsonb_build_object(
    'id', message_id, 'role', 'user', 'content', 'private user content'
  );
  assistant_message jsonb := pg_catalog.jsonb_build_object(
    'id', assistant_id, 'role', 'assistant', 'inReplyTo', message_id,
    'content', 'private assistant content'
  );
  response_data jsonb;
begin
  response_data := pg_catalog.jsonb_build_object(
    'response', 'private assistant content',
    'assistantMessage', assistant_message,
    'connectedApp', pg_catalog.jsonb_build_object('state', 'delegated')
  );

  select claimed.turn_id, claimed.claim_token
    into strict turn_id, claim_token
  from public.connected_chat_claim_turn_v1(
    owner_id, chat_id, message_id, repeat('a', 64), repeat('b', 64)
  ) as claimed;

  response := public.connected_operator_complete_chat_v1(
    completion_id, owner_id, session_id, turn_id, chat_id, message_id,
    assistant_id, claim_token, repeat('a', 64), repeat('b', 64),
    'delegated', 'chat-completion-key-1', repeat('c', 64),
    'Inbox check', user_message, assistant_message, response_data
  );
  if response->>'completion_id' <> completion_id::text
     or response->>'kind' <> 'delegated'
     or response->>'response_binding_sha256' <> repeat('c', 64)
     or (response->>'resulting_revision')::bigint < 1
     or response->'response_data' is distinct from response_data then
    raise exception 'atomic connected chat completion returned the wrong receipt';
  end if;

  replay := public.connected_operator_complete_chat_v1(
    completion_id, owner_id, session_id, turn_id, chat_id, message_id,
    assistant_id, claim_token, repeat('a', 64), repeat('b', 64),
    'delegated', 'chat-completion-key-1', repeat('c', 64),
    'Inbox check', user_message, assistant_message, response_data
  );
  if replay is distinct from response then
    raise exception 'exact completion replay changed its receipt';
  end if;

  readback := public.connected_operator_read_chat_completion_v1(
    completion_id, owner_id, session_id, turn_id, chat_id, message_id,
    repeat('a', 64), repeat('b', 64), 'delegated',
    'chat-completion-key-1', repeat('c', 64)
  );
  if readback is distinct from response then
    raise exception 'completion readback did not recover the exact response';
  end if;
  if public.connected_operator_read_chat_completion_v1(
    completion_id, owner_id, session_id, turn_id, chat_id, message_id,
    repeat('a', 64), repeat('b', 64), 'delegated',
    'chat-completion-key-1', repeat('d', 64)
  ) is not null then
    raise exception 'mismatched response binding escaped readback';
  end if;

  begin
    perform public.connected_operator_complete_chat_v1(
      completion_id, owner_id, session_id, turn_id, chat_id, message_id,
      assistant_id, claim_token, repeat('a', 64), repeat('b', 64),
      'delegated', 'chat-completion-key-1', repeat('d', 64),
      'Inbox check', user_message, assistant_message, response_data
    );
    raise exception 'conflicting completion replay unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;

  begin
    perform 1 from connected_chat_completion_private.completions limit 1;
    raise exception 'service_role unexpectedly read the private receipt table';
  exception when insufficient_privilege then
    null;
  end;
end;
$test$;

do $failed_fence$
declare
  owner_id constant uuid := '60000000-0000-4000-8000-000000000002';
  session_id constant uuid := '60000000-0000-4000-8000-000000000012';
  chat_id constant uuid := '60000000-0000-4000-8000-000000000031';
  message_id constant uuid := '60000000-0000-4000-8000-000000000032';
  assistant_id constant uuid := '60000000-0000-4000-8000-000000000033';
  turn_id uuid;
  claim_token uuid;
begin
  select claimed.turn_id, claimed.claim_token
    into strict turn_id, claim_token
  from public.connected_chat_claim_turn_v1(
    owner_id, chat_id, message_id, repeat('d', 64), repeat('e', 64)
  ) as claimed;
  begin
    perform public.connected_operator_complete_chat_v1(
      '60000000-0000-4000-8000-000000000034', owner_id, session_id,
      turn_id, chat_id, message_id, assistant_id,
      '60000000-0000-4000-8000-000000000099',
      repeat('d', 64), repeat('e', 64), 'delegated',
      'chat-completion-key-1', repeat('f', 64), 'No write',
      pg_catalog.jsonb_build_object(
        'id', message_id, 'role', 'user', 'content', 'must roll back'
      ),
      pg_catalog.jsonb_build_object(
        'id', assistant_id, 'role', 'assistant', 'inReplyTo', message_id,
        'content', 'must roll back'
      ),
      pg_catalog.jsonb_build_object(
        'assistantMessage', pg_catalog.jsonb_build_object(
          'id', assistant_id, 'role', 'assistant', 'inReplyTo', message_id,
          'content', 'must roll back'
        )
      )
    );
    raise exception 'wrong claim token unexpectedly completed a chat';
  exception when sqlstate '55000' then
    null;
  end;
end;
$failed_fence$;

reset role;

do $verify$
declare
  first_owner constant uuid := '60000000-0000-4000-8000-000000000001';
  second_owner constant uuid := '60000000-0000-4000-8000-000000000002';
  turn_id uuid;
  persisted_messages jsonb;
begin
  select chat.messages into strict persisted_messages
  from public.user_chats as chat
  where chat.user_id = first_owner
    and chat.chat_id = '60000000-0000-4000-8000-000000000021';
  if pg_catalog.jsonb_array_length(persisted_messages) <> 2
     or (
       select pg_catalog.count(*)
       from connected_chat_completion_private.completions as completion
       where completion.owner_id = first_owner
     ) <> 1
     or not exists (
       select 1 from public.chat_jobs as job
       where job.user_id = first_owner
         and job.status = 'completed'
         and job.claim_token is null
     )
     or not exists (
       select 1 from connected_chat_private.turns as turn
       where turn.owner_id = first_owner and turn.stage = 'terminal'
     ) then
    raise exception 'completion atomicity invariant failed';
  end if;

  if exists (
    select 1 from public.user_chats as chat where chat.user_id = second_owner
  )
     or exists (
       select 1 from connected_chat_completion_private.completions as completion
       where completion.owner_id = second_owner
     )
     or not exists (
       select 1 from public.chat_jobs as job
       where job.user_id = second_owner
         and job.status = 'processing'
         and job.claim_token is not null
     ) then
    raise exception 'failed completion did not roll back every write';
  end if;

  update public.sessions
  set revoked_at = pg_catalog.statement_timestamp()
  where id = '60000000-0000-4000-8000-000000000011';
  select completion.turn_id into strict turn_id
  from connected_chat_completion_private.completions as completion
  where completion.owner_id = first_owner;
  if public.connected_operator_read_chat_completion_v1(
    '60000000-0000-4000-8000-000000000024', first_owner,
    '60000000-0000-4000-8000-000000000011', turn_id,
    '60000000-0000-4000-8000-000000000021',
    '60000000-0000-4000-8000-000000000022',
    repeat('a', 64), repeat('b', 64), 'delegated',
    'chat-completion-key-1', repeat('c', 64)
  ) is not null then
    raise exception 'revoked session recovered a private completion';
  end if;

  delete from public.users where id = first_owner;
  if exists (
    select 1 from connected_chat_completion_private.completions
    where owner_id = first_owner
  )
     or exists (select 1 from public.chat_jobs where user_id = first_owner)
     or exists (
       select 1 from connected_chat_private.turns where owner_id = first_owner
     )
     or exists (select 1 from public.user_chats where user_id = first_owner)
     or exists (select 1 from public.sessions where user_id = first_owner) then
    raise exception 'account deletion left connected chat completion state';
  end if;
end;
$verify$;

delete from public.users where id = '60000000-0000-4000-8000-000000000002';
