\set ON_ERROR_STOP on

create extension if not exists dblink;

insert into public.users(id) values
  ('00000000-0000-4000-8000-000000008501');

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  current_flow_nonce_sha256, created_at, updated_at
) values (
  '00000000-0000-4000-8000-000000008511',
  '00000000-0000-4000-8000-000000008501',
  'google', 'mail', 'personal',
  '00000000-0000-4000-8000-000000008521', 0, 'pending',
  repeat('1', 64), pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()
);

set role service_role;

select public.connected_app_oauth_secret_begin_v1(
  flow_id, nonce_id,
  '00000000-0000-4000-8000-000000008501',
  '00000000-0000-4000-8000-000000008511',
  '00000000-0000-4000-8000-000000008521', 0,
  repeat('1',64), repeat('2',64), 'google', 'mail', 'personal',
  array['mail.search'], repeat('3',64), array['scope-a'], repeat('4',64),
  repeat('5',64), repeat('P',43), 'https://askcrump.com/oauth/callback',
  pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp() + interval '5 minutes',
  flow_binding, 'oauth-key', repeat('A',16), repeat('B',64),
  repeat('C',16), repeat('D',32), secret_binding
)
from (values
  ('00000000-0000-4000-8000-000000008601'::uuid,
   '00000000-0000-4000-8000-000000008611'::uuid, repeat('6',64), repeat('7',64)),
  ('00000000-0000-4000-8000-000000008602'::uuid,
   '00000000-0000-4000-8000-000000008612'::uuid, repeat('8',64), repeat('9',64)),
  ('00000000-0000-4000-8000-000000008603'::uuid,
   '00000000-0000-4000-8000-000000008613'::uuid, repeat('a',64), repeat('b',64))
) as flows(flow_id, nonce_id, flow_binding, secret_binding);

select public.connected_app_oauth_secret_fence_v1(
  '00000000-0000-4000-8000-000000008602',
  '00000000-0000-4000-8000-000000008622', repeat('c',64), repeat('8',64),
  '00000000-0000-4000-8000-000000008632',
  pg_catalog.clock_timestamp() + interval '2 minutes'
);
select public.connected_app_oauth_secret_fence_v1(
  '00000000-0000-4000-8000-000000008603',
  '00000000-0000-4000-8000-000000008623', repeat('d',64), repeat('a',64),
  '00000000-0000-4000-8000-000000008633',
  pg_catalog.clock_timestamp() + interval '2 minutes'
);

reset role;

do $races$
declare
  connection_string text := pg_catalog.format(
    'host=127.0.0.1 port=%s dbname=%s user=postgres',
    pg_catalog.current_setting('port'), pg_catalog.current_database()
  );
  result jsonb;
  response_text text;
  remote_error text;
begin
  perform public.dblink_connect('oauth_secret_race_a', connection_string);
  perform public.dblink_connect('oauth_secret_race_b', connection_string);

  -- Exactly one host may win the provider-dispatch fence. The losing host
  -- blocks on the canonical owner/connection/flow order and then reads fresh=false.
  perform public.dblink_exec('oauth_secret_race_a', 'begin');
  perform public.dblink_exec('oauth_secret_race_a', 'set local role service_role');
  select response::jsonb into result
  from public.dblink(
    'oauth_secret_race_a',
    $sql$select public.connected_app_oauth_secret_fence_v1(
      '00000000-0000-4000-8000-000000008601',
      '00000000-0000-4000-8000-000000008621', repeat('e',64), repeat('6',64),
      '00000000-0000-4000-8000-000000008631',
      pg_catalog.clock_timestamp() + interval '2 minutes'
    )::text$sql$
  ) as remote_result(response text);
  if result->>'status' <> 'claimed' or result->>'fresh' <> 'true' then
    raise exception 'OAuth fence winner drifted: %', result;
  end if;
  perform public.dblink_exec('oauth_secret_race_b', 'begin');
  perform public.dblink_exec('oauth_secret_race_b', 'set local role service_role');
  perform public.dblink_send_query(
    'oauth_secret_race_b',
    $sql$select public.connected_app_oauth_secret_fence_v1(
      '00000000-0000-4000-8000-000000008601',
      '00000000-0000-4000-8000-000000008621', repeat('e',64), repeat('6',64),
      '00000000-0000-4000-8000-000000008639',
      pg_catalog.clock_timestamp() + interval '2 minutes'
    )::text$sql$
  );
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('oauth_secret_race_b') <> 1 then
    raise exception 'OAuth losing fence did not serialize';
  end if;
  perform public.dblink_exec('oauth_secret_race_a', 'commit');
  select response::jsonb into result
  from public.dblink_get_result('oauth_secret_race_b')
    as remote_result(response text);
  perform response from public.dblink_get_result('oauth_secret_race_b')
    as remote_result(response text);
  perform public.dblink_exec('oauth_secret_race_b', 'commit');
  if result->>'status' <> 'fenced' or result->>'fresh' <> 'false' then
    raise exception 'OAuth losing fence was not terminal: %', result;
  end if;

  -- GRANT wins, then abort must serialize and erase/tombstone both the flow
  -- and provisional refresh-token custody after the grant commits.
  perform public.dblink_exec('oauth_secret_race_a', 'begin');
  perform public.dblink_exec('oauth_secret_race_a', 'set local role service_role');
  select response::jsonb into result
  from public.dblink(
    'oauth_secret_race_a',
    $sql$select public.connected_app_oauth_secret_grant_v1(
      p_flow_id => '00000000-0000-4000-8000-000000008602',
      p_exchange_id => '00000000-0000-4000-8000-000000008622',
      p_exchange_binding_sha256 => repeat('c',64),
      p_attempt_id => '00000000-0000-4000-8000-000000008632',
      p_credential_handle_sha256 => repeat('1',64),
      p_external_account_id_hash => repeat('2',64),
      p_actual_scopes => array['scope-a'], p_actual_scopes_sha256 => repeat('4',64),
      p_issued_at => pg_catalog.clock_timestamp(),
      p_expires_at => pg_catalog.clock_timestamp() + interval '1 hour',
      p_provisional_id => '00000000-0000-4000-8000-000000008642',
      p_oauth_client_id_sha256 => repeat('3',64),
      p_provisional_binding_sha256 => repeat('5',64),
      p_terminal_key_id => 'oauth-key', p_terminal_wrapped_key_nonce => repeat('E',16),
      p_terminal_wrapped_key_ciphertext => repeat('F',64),
      p_terminal_secret_nonce => repeat('G',16), p_terminal_secret_ciphertext => repeat('H',32),
      p_terminal_record_binding_sha256 => repeat('6',64),
      p_provisional_key_id => 'oauth-key', p_provisional_wrapped_key_nonce => repeat('I',16),
      p_provisional_wrapped_key_ciphertext => repeat('J',64),
      p_provisional_secret_nonce => repeat('K',16), p_provisional_secret_ciphertext => repeat('L',32),
      p_provisional_record_binding_sha256 => repeat('7',64)
    )::text$sql$
  ) as remote_result(response text);
  if result->>'status' <> 'granted' then
    raise exception 'OAuth grant-winner setup failed: %', result;
  end if;
  perform public.dblink_exec('oauth_secret_race_b', 'begin');
  perform public.dblink_exec('oauth_secret_race_b', 'set local role service_role');
  perform public.dblink_send_query(
    'oauth_secret_race_b',
    $sql$select public.connected_app_oauth_secret_abort_v1(
      '00000000-0000-4000-8000-000000008602', repeat('8',64), 'aborted'
    )::text$sql$
  );
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('oauth_secret_race_b') <> 1 then
    raise exception 'OAuth abort did not serialize behind grant';
  end if;
  perform public.dblink_exec('oauth_secret_race_a', 'commit');
  select response::jsonb into result
  from public.dblink_get_result('oauth_secret_race_b')
    as remote_result(response text);
  perform response from public.dblink_get_result('oauth_secret_race_b')
    as remote_result(response text);
  perform public.dblink_exec('oauth_secret_race_b', 'commit');
  if result->>'status' <> 'erased' then
    raise exception 'OAuth serialized abort failed: %', result;
  end if;

  -- ABORT wins: a provider result arriving from a stale process cannot
  -- recreate provisional custody or a grant after the terminal tombstone.
  perform public.dblink_exec('oauth_secret_race_a', 'begin');
  perform public.dblink_exec('oauth_secret_race_a', 'set local role service_role');
  select response::jsonb into result
  from public.dblink(
    'oauth_secret_race_a',
    $sql$select public.connected_app_oauth_secret_abort_v1(
      '00000000-0000-4000-8000-000000008603', repeat('a',64), 'expired'
    )::text$sql$
  ) as remote_result(response text);
  perform public.dblink_exec('oauth_secret_race_b', 'begin');
  perform public.dblink_exec('oauth_secret_race_b', 'set local role service_role');
  perform public.dblink_send_query(
    'oauth_secret_race_b',
    $sql$select public.connected_app_oauth_secret_grant_v1(
      p_flow_id => '00000000-0000-4000-8000-000000008603',
      p_exchange_id => '00000000-0000-4000-8000-000000008623',
      p_exchange_binding_sha256 => repeat('d',64),
      p_attempt_id => '00000000-0000-4000-8000-000000008633',
      p_credential_handle_sha256 => repeat('8',64),
      p_external_account_id_hash => repeat('9',64),
      p_actual_scopes => array['scope-a'], p_actual_scopes_sha256 => repeat('4',64),
      p_issued_at => pg_catalog.clock_timestamp(),
      p_expires_at => pg_catalog.clock_timestamp() + interval '1 hour',
      p_provisional_id => '00000000-0000-4000-8000-000000008643',
      p_oauth_client_id_sha256 => repeat('3',64),
      p_provisional_binding_sha256 => repeat('5',64),
      p_terminal_key_id => 'oauth-key', p_terminal_wrapped_key_nonce => repeat('E',16),
      p_terminal_wrapped_key_ciphertext => repeat('F',64),
      p_terminal_secret_nonce => repeat('G',16), p_terminal_secret_ciphertext => repeat('H',32),
      p_terminal_record_binding_sha256 => repeat('6',64),
      p_provisional_key_id => 'oauth-key', p_provisional_wrapped_key_nonce => repeat('I',16),
      p_provisional_wrapped_key_ciphertext => repeat('J',64),
      p_provisional_secret_nonce => repeat('K',16), p_provisional_secret_ciphertext => repeat('L',32),
      p_provisional_record_binding_sha256 => repeat('7',64)
    )::text$sql$
  );
  perform pg_catalog.pg_sleep(0.05);
  if public.dblink_is_busy('oauth_secret_race_b') <> 1 then
    raise exception 'OAuth stale grant did not serialize behind abort';
  end if;
  perform public.dblink_exec('oauth_secret_race_a', 'commit');
  response_text := null;
  select response into response_text
  from public.dblink_get_result('oauth_secret_race_b', false)
    as remote_result(response text);
  remote_error := public.dblink_error_message('oauth_secret_race_b');
  perform public.dblink_get_result('oauth_secret_race_b', false);
  perform public.dblink_exec('oauth_secret_race_b', 'rollback');
  if response_text is not null
     or remote_error not like '%OAuth secret grant binding mismatch%' then
    raise exception 'OAuth abort-winner stale grant was not fenced: %, %',
      response_text, remote_error;
  end if;

  if exists (
    select 1 from connected_app_private.oauth_provisional_credentials
    where flow_id in (
      '00000000-0000-4000-8000-000000008602',
      '00000000-0000-4000-8000-000000008603'
    )
  ) or not exists (
    select 1 from connected_app_private.oauth_provisional_tombstones
    where credential_handle_sha256 = repeat('1',64)
  ) or not exists (
    select 1 from connected_app_private.oauth_secret_tombstones
    where flow_id = '00000000-0000-4000-8000-000000008603'
  ) then
    raise exception 'OAuth race tombstone invariants failed';
  end if;

  perform public.dblink_disconnect('oauth_secret_race_a');
  perform public.dblink_disconnect('oauth_secret_race_b');
exception when others then
  begin perform public.dblink_disconnect('oauth_secret_race_a'); exception when others then null; end;
  begin perform public.dblink_disconnect('oauth_secret_race_b'); exception when others then null; end;
  raise;
end;
$races$;

select 'CONNECTED_APP_OAUTH_SECRET_CUSTODY_RACES_OK' as result;
