\set ON_ERROR_STOP on

do $test$
declare
  owner_id uuid := '10000000-0000-4000-8000-000000000001';
  session_id uuid := '10000000-0000-4000-8000-000000000002';
  chat_id uuid := '10000000-0000-4000-8000-000000000003';
  message_id uuid := '10000000-0000-4000-8000-000000000004';
  connection_id uuid := '10000000-0000-4000-8000-000000000005';
  incarnation_id uuid := '10000000-0000-4000-8000-000000000006';
  credential_id uuid := '10000000-0000-4000-8000-000000000007';
  planning_id uuid := '10000000-0000-4000-8000-000000000008';
  payload_id uuid := '10000000-0000-4000-8000-000000000009';
  invocation_id uuid := '10000000-0000-4000-8000-000000000010';
  origin_sha text := repeat('a', 64);
  request_sha text := repeat('b', 64);
  plan_sha text := repeat('c', 64);
  payload_sha text := repeat('d', 64);
  reference_sha text := repeat('e', 64);
  record_sha text := repeat('f', 64);
  requested_at timestamptz := pg_catalog.clock_timestamp();
  expires_at timestamptz;
  claim_row record;
  claimed_turn_id uuid;
  claim_token uuid;
  result jsonb;
begin
  expires_at := requested_at + interval '15 minutes';
  insert into public.users(id) values (owner_id);
  insert into public.sessions(id, user_id, expires_at)
  values (session_id, owner_id, requested_at + interval '1 day');
  insert into connected_app_private.connections(
    id, owner_id, provider, resource, account_kind, connection_incarnation_id,
    authorization_revision, authorization_state,
    authorization_snapshot_sha256, granted_actions,
    granted_actions_sha256, granted_scopes_sha256,
    external_account_id_sha256, broker_credential_ref,
    credential_ref_sha256, authorization_expires_at
  ) values (
    connection_id, owner_id, 'google', 'mail', 'personal', incarnation_id,
    1, 'active', repeat('1',64), array['mail.search'], repeat('2',64),
    repeat('3',64), repeat('4',64), credential_id, repeat('5',64),
    requested_at + interval '1 day'
  );
  select * into claim_row
  from public.connected_chat_claim_turn_v1(
    owner_id, chat_id, message_id, origin_sha, request_sha
  );
  claimed_turn_id := claim_row.turn_id;
  claim_token := claim_row.claim_token;
  if claim_row.job_state <> 'claimed' or claimed_turn_id is null or claim_token is null then
    raise exception 'chat claim fixture failed';
  end if;

  result := public.connected_plan_begin_v1(
    owner_id, session_id, chat_id, message_id, claimed_turn_id, claim_token,
    origin_sha, request_sha, planning_id, 'plan-bind-1', plan_sha,
    payload_id, requested_at, expires_at
  );
  if result->>'state' <> 'reserved' or result->>'planning_id' <> planning_id::text then
    raise exception 'plan begin failed: %', result;
  end if;
  result := public.connected_plan_begin_v1(
    owner_id, session_id, chat_id, message_id, claimed_turn_id, claim_token,
    origin_sha, request_sha, planning_id, 'plan-bind-1', plan_sha,
    payload_id, requested_at, expires_at
  );
  if result->>'state' <> 'reserved' then
    raise exception 'plan begin replay failed';
  end if;
  result := public.connected_plan_mark_invoked_v1(
    owner_id, session_id, chat_id, message_id, claimed_turn_id, claim_token,
    origin_sha, request_sha, planning_id, 'plan-bind-1', plan_sha,
    payload_id, requested_at, expires_at, invocation_id
  );
  if result->>'invoke_permitted' <> 'true'
     or result->'record'->>'state' <> 'invoked' then
    raise exception 'plan invocation claim failed: %', result;
  end if;
  result := public.connected_plan_mark_invoked_v1(
    owner_id, session_id, chat_id, message_id, claimed_turn_id, claim_token,
    origin_sha, request_sha, planning_id, 'plan-bind-1', plan_sha,
    payload_id, requested_at, expires_at, invocation_id
  );
  if result->>'invoke_permitted' <> 'false' then
    raise exception 'plan invocation replay permitted a second caller';
  end if;
  result := public.connected_plan_envelope_put_v1(
    owner_id, claimed_turn_id, planning_id, plan_sha, payload_id,
    'plan-hmac-1', payload_sha, reference_sha, requested_at, expires_at,
    'plan-kek-1', repeat('A',16), repeat('B',64), repeat('C',16),
    repeat('D',32), record_sha
  );
  if result->>'payload_id' <> payload_id::text
     or result ? 'record_state' then
    raise exception 'encrypted plan put failed: %', result;
  end if;
  result := public.connected_plan_envelope_read_v1(
    owner_id, claimed_turn_id, planning_id, plan_sha, payload_id
  );
  if result->>'payload_ciphertext' <> repeat('D',32) then
    raise exception 'encrypted plan read failed';
  end if;
  result := public.connected_plan_settle_v1(
    owner_id, session_id, chat_id, message_id, claimed_turn_id, claim_token,
    origin_sha, request_sha, planning_id, 'plan-bind-1', plan_sha,
    payload_id, requested_at, expires_at, invocation_id, 'action',
    connection_id, 'google', 'mail', 'mail.search', 'plan-hmac-1',
    payload_sha, reference_sha
  );
  if result->>'state' <> 'settled' or result->>'action' <> 'mail.search' then
    raise exception 'plan settlement failed: %', result;
  end if;
  result := public.connected_plan_settle_v1(
    owner_id, session_id, chat_id, message_id, claimed_turn_id, claim_token,
    origin_sha, request_sha, planning_id, 'plan-bind-1', plan_sha,
    payload_id, requested_at, expires_at, invocation_id, 'action',
    connection_id, 'google', 'mail', 'mail.search', 'plan-hmac-1',
    payload_sha, reference_sha
  );
  if result->>'state' <> 'settled' then
    raise exception 'plan settlement replay failed';
  end if;
  if not exists (
    select 1 from connected_chat_private.turns as turn
    where turn.turn_id = claimed_turn_id and turn.stage = 'planned'
      and turn.plan_payload_id = payload_id
      and turn.plan_payload_sha256 = payload_sha
      and turn.plan_reference_binding_sha256 = reference_sha
  ) then
    raise exception 'chat turn did not advance to planned';
  end if;

  update public.sessions set revoked_at = pg_catalog.clock_timestamp()
  where id = session_id;
  begin
    perform public.connected_plan_read_v1(
      owner_id, session_id, chat_id, message_id, claimed_turn_id, claim_token,
      origin_sha, request_sha, planning_id, 'plan-bind-1', plan_sha,
      payload_id, requested_at, expires_at
    );
    raise exception 'revoked session was accepted';
  exception when sqlstate '55000' then null;
  end;
  update public.sessions set revoked_at = null where id = session_id;

  delete from public.users where id = owner_id;
  if exists (select 1 from connected_plan_private.operations as operation
             where operation.owner_id = '10000000-0000-4000-8000-000000000001'::uuid)
     or exists (select 1 from connected_plan_private.envelopes as envelope
                where envelope.owner_id = '10000000-0000-4000-8000-000000000001'::uuid) then
    raise exception 'account deletion left connected plan rows';
  end if;
end;
$test$;

do $tombstone$
declare
  owner_id uuid := '20000000-0000-4000-8000-000000000001';
  session_id uuid := '20000000-0000-4000-8000-000000000002';
  chat_id uuid := '20000000-0000-4000-8000-000000000003';
  message_id uuid := '20000000-0000-4000-8000-000000000004';
  planning_id uuid := '20000000-0000-4000-8000-000000000005';
  payload_id uuid := '20000000-0000-4000-8000-000000000006';
  invocation_id uuid := '20000000-0000-4000-8000-000000000007';
  requested_at timestamptz := pg_catalog.clock_timestamp();
  expires_at timestamptz;
  claim_row record;
  result jsonb;
begin
  expires_at := requested_at + interval '15 minutes';
  insert into public.users(id) values (owner_id);
  insert into public.sessions(id,user_id,expires_at)
  values(session_id,owner_id,requested_at + interval '1 day');
  select * into claim_row from public.connected_chat_claim_turn_v1(
    owner_id,chat_id,message_id,repeat('6',64),repeat('7',64)
  );
  perform public.connected_plan_begin_v1(
    owner_id,session_id,chat_id,message_id,claim_row.turn_id,claim_row.claim_token,
    repeat('6',64),repeat('7',64),planning_id,'plan-bind-1',repeat('8',64),
    payload_id,requested_at,expires_at
  );
  perform public.connected_plan_mark_invoked_v1(
    owner_id,session_id,chat_id,message_id,claim_row.turn_id,claim_row.claim_token,
    repeat('6',64),repeat('7',64),planning_id,'plan-bind-1',repeat('8',64),
    payload_id,requested_at,expires_at,invocation_id
  );
  perform public.connected_plan_envelope_put_v1(
    owner_id,claim_row.turn_id,planning_id,repeat('8',64),payload_id,
    'plan-hmac-1',repeat('9',64),repeat('a',64),requested_at,expires_at,
    'plan-kek-1',repeat('A',16),repeat('B',64),repeat('C',16),repeat('D',32),repeat('e',64)
  );
  if not public.connected_plan_envelope_delete_v1(
    owner_id,claim_row.turn_id,planning_id,repeat('8',64),payload_id
  ) then
    raise exception 'plan envelope deletion failed';
  end if;
  result := public.connected_plan_envelope_put_v1(
    owner_id,claim_row.turn_id,planning_id,repeat('8',64),payload_id,
    'plan-hmac-1',repeat('9',64),repeat('a',64),requested_at,expires_at,
    'plan-kek-1',repeat('A',16),repeat('B',64),repeat('C',16),repeat('D',32),repeat('e',64)
  );
  if result is not null then
    raise exception 'deleted plan envelope resurrected';
  end if;
end;
$tombstone$;

select 'CONNECTED_PLAN_ONCE_BEHAVIOR_OK' as result;
