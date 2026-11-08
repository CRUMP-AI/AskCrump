\set ON_ERROR_STOP on

begin;

insert into public.users(id, registration_environment, created_at, updated_at) values
  (
    '00000000-0000-4000-8000-000000008901', 'development',
    pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()
  );

set local role service_role;

do $start_behavior$
declare
  requested_at timestamptz := pg_catalog.clock_timestamp() - interval '2 minutes';
  expires_at timestamptz := requested_at + interval '10 minutes';
  result jsonb;
begin
  begin
    perform 1 from connected_app_private.oauth_operator_starts;
    raise exception 'service_role unexpectedly read OAuth operator starts';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform 1 from connected_app_private.oauth_callback_requests;
    raise exception 'service_role unexpectedly read OAuth callback requests';
  exception when insufficient_privilege then
    null;
  end;

  result := public.connected_app_operator_prepare_oauth_start_v1(
    '00000000-0000-4000-8000-000000008911',
    '00000000-0000-4000-8000-000000008901',
    repeat('1', 64), repeat('2', 64), null,
    '00000000-0000-4000-8000-000000008921',
    '00000000-0000-4000-8000-000000008922',
    '00000000-0000-4000-8000-000000008923',
    '00000000-0000-4000-8000-000000008924',
    repeat('3', 64), 'google', 'mail', 'personal',
    array['mail.get'], repeat('4', 64), repeat('5', 64),
    requested_at, expires_at
  );
  if result->>'request_id' <> '00000000-0000-4000-8000-000000008911'
     or result->>'flow_id' <> '00000000-0000-4000-8000-000000008921'
     or result->>'connection_id' <> '00000000-0000-4000-8000-000000008923'
     or result->>'connection_incarnation_id' <>
       '00000000-0000-4000-8000-000000008924'
     or result ? 'created_at' then
    raise exception 'OAuth start reservation drifted: %', result;
  end if;

  if public.connected_app_operator_prepare_oauth_start_v1(
    '00000000-0000-4000-8000-000000008911',
    '00000000-0000-4000-8000-000000008901',
    repeat('1', 64), repeat('2', 64), null,
    '00000000-0000-4000-8000-000000008921',
    '00000000-0000-4000-8000-000000008922',
    '00000000-0000-4000-8000-000000008923',
    '00000000-0000-4000-8000-000000008924',
    repeat('3', 64), 'google', 'mail', 'personal',
    array['mail.get'], repeat('4', 64), repeat('5', 64),
    requested_at, expires_at
  ) <> result then
    raise exception 'OAuth start exact replay changed';
  end if;

  if public.connected_app_operator_prepare_oauth_start_v1(
    '00000000-0000-4000-8000-000000008911',
    '00000000-0000-4000-8000-000000008901',
    repeat('1', 64), repeat('2', 64), null,
    '00000000-0000-4000-8000-000000008921',
    '00000000-0000-4000-8000-000000008922',
    '00000000-0000-4000-8000-000000008923',
    '00000000-0000-4000-8000-000000008924',
    repeat('3', 64), 'google', 'mail', 'personal',
    array['mail.get'], repeat('4', 64), repeat('5', 64),
    requested_at + interval '30 seconds', expires_at + interval '30 seconds'
  ) <> result then
    raise exception 'OAuth start transport retry timestamp changed reservation';
  end if;

  if public.connected_app_operator_read_oauth_start_v1(
    '00000000-0000-4000-8000-000000008901',
    '00000000-0000-4000-8000-000000008911'
  ) <> result then
    raise exception 'OAuth start read recovery changed';
  end if;

  begin
    perform public.connected_app_operator_prepare_oauth_start_v1(
      '00000000-0000-4000-8000-000000008911',
      '00000000-0000-4000-8000-000000008901',
      repeat('1', 64), repeat('2', 64), null,
      '00000000-0000-4000-8000-000000008921',
      '00000000-0000-4000-8000-000000008922',
      '00000000-0000-4000-8000-000000008923',
      '00000000-0000-4000-8000-000000008925',
      repeat('3', 64), 'google', 'mail', 'personal',
      array['mail.get'], repeat('4', 64), repeat('5', 64),
      requested_at, expires_at
    );
    raise exception 'OAuth start replay accepted a different incarnation';
  exception when sqlstate '55000' then
    null;
  end;

  perform public.connected_app_oauth_create_pending_v1(
    '00000000-0000-4000-8000-000000008921',
    '00000000-0000-4000-8000-000000008922',
    '00000000-0000-4000-8000-000000008901',
    '00000000-0000-4000-8000-000000008923',
    '00000000-0000-4000-8000-000000008924', 0,
    repeat('3', 64), repeat('1', 64), 'google', 'mail', 'personal',
    array['mail.get'], repeat('4', 64), repeat('6', 64), repeat('7', 64),
    repeat('P', 43), repeat('5', 64), repeat('8', 64), repeat('9', 64),
    requested_at, expires_at
  );

  result := public.connected_app_operator_prepare_oauth_callback_v1(
    'google', repeat('7', 64), repeat('a', 64), requested_at + interval '1 minute'
  );
  if result->'flow'->>'flow_id' <> '00000000-0000-4000-8000-000000008921'
     or result->'flow'->>'state_sha256' <> repeat('7', 64)
     or result->'flow'->>'status' <> 'pending'
     or result->'flow' ? 'authorization_code'
     or result ? 'state' then
    raise exception 'OAuth callback candidate drifted: %', result;
  end if;
  if public.connected_app_operator_read_oauth_callback_v1(
    'google', repeat('a', 64)
  ) is not null then
    raise exception 'read-only callback candidate created a durable completion';
  end if;

  result := public.connected_app_operator_accept_oauth_callback_v1(
    'google', repeat('7', 64), repeat('a', 64),
    requested_at + interval '1 minute',
    '00000000-0000-4000-8000-000000008921',
    '00000000-0000-4000-8000-000000008901',
    '00000000-0000-4000-8000-000000008923',
    '00000000-0000-4000-8000-000000008924',
    0, repeat('3', 64), repeat('1', 64), repeat('8', 64), repeat('b', 64)
  );
  if result->>'consumption_id' <> '00000000-0000-4000-8000-000000008921'
     or result->>'flow_id' <> '00000000-0000-4000-8000-000000008921'
     or result->>'connection_id' <> '00000000-0000-4000-8000-000000008923'
     or result->>'consume_binding_sha256' <> repeat('b', 64)
     or result->>'flow_binding_sha256' <> repeat('8', 64) then
    raise exception 'atomic OAuth callback acceptance drifted: %', result;
  end if;
end;
$start_behavior$;

reset role;

-- Model response loss after the atomic callback+consume commit, then recovery
-- after the public flow deadline. The exact retry must use the stored receipt.
update connected_app_private.oauth_flows
set expires_at = pg_catalog.clock_timestamp() - interval '30 seconds'
where flow_id = '00000000-0000-4000-8000-000000008921';

set local role service_role;

do $callback_recovery$
declare
  result jsonb;
begin
  result := public.connected_app_operator_prepare_oauth_callback_v1(
    'google', repeat('7', 64), repeat('a', 64), pg_catalog.clock_timestamp()
  );
  if result->'flow'->>'flow_id' <> '00000000-0000-4000-8000-000000008921'
     or result->'flow'->>'status' <> 'consumed' then
    raise exception 'accepted callback candidate could not recover after deadline: %', result;
  end if;

  result := public.connected_app_operator_accept_oauth_callback_v1(
    'google', repeat('7', 64), repeat('a', 64), pg_catalog.clock_timestamp(),
    '00000000-0000-4000-8000-000000008921',
    '00000000-0000-4000-8000-000000008901',
    '00000000-0000-4000-8000-000000008923',
    '00000000-0000-4000-8000-000000008924',
    0, repeat('3', 64), repeat('1', 64), repeat('8', 64), repeat('b', 64)
  );
  if result->>'consume_binding_sha256' <> repeat('b', 64)
     or result->>'consumed_at' is null then
    raise exception 'atomic callback consumption could not replay after deadline: %', result;
  end if;

  begin
    perform public.connected_app_operator_prepare_oauth_callback_v1(
      'google', repeat('7', 64), repeat('b', 64), pg_catalog.clock_timestamp()
    );
    raise exception 'OAuth callback accepted a different callback binding';
  exception when sqlstate '55000' then
    null;
  end;

  if public.connected_app_operator_read_oauth_callback_v1(
    'google', repeat('a', 64)
  ) is not null then
    raise exception 'unfinished OAuth callback was exposed as completed';
  end if;
end;
$callback_recovery$;

rollback;

select 'CONNECTED_OAUTH_OPERATOR_BRIDGE_OK' as result;
