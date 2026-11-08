\set ON_ERROR_STOP on

begin;

insert into public.users(id,registration_environment,created_at,updated_at) values
  ('10000000-0000-4000-8000-000000006871','development',now(),now()),
  ('10000000-0000-4000-8000-000000006872','development',now(),now());

create or replace function public.connected_oauth_binding_seed_v1(
  p_owner uuid,p_connection uuid,p_incarnation uuid,p_flow uuid,p_nonce uuid,
  p_nonce_sha text,p_state_sha text,p_flow_binding text,p_permit uuid,
  p_exchange_binding text,p_dispatch uuid
) returns void language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,current_flow_nonce_sha256
  ) values (
    p_connection,p_owner,'google','mail','personal',p_incarnation,
    0,'pending',p_nonce_sha
  );
  perform public.connected_app_oauth_create_pending_v1(
    p_flow,p_nonce,p_owner,p_connection,p_incarnation,0,p_nonce_sha,
    repeat('1',64),'google','mail','personal',array['mail.get'],repeat('3',64),
    repeat('4',64),p_state_sha,repeat('P',43),repeat('5',64),
    p_flow_binding,repeat('9',64),now_at,now_at+interval '5 minutes'
  );
  perform public.connected_app_oauth_consume_pending_v1(
    p_flow,p_flow,p_owner,p_connection,p_incarnation,0,p_nonce_sha,
    repeat('1',64),p_flow_binding,repeat('a',64)
  );
  perform public.connected_app_oauth_put_permit_capability_v2(
    p_permit,p_flow,p_connection,p_permit,p_exchange_binding,p_flow_binding,
    p_exchange_binding,now_at,now_at+interval '2 minutes','oauth-key',
    repeat('A',16),repeat('B',64),repeat('C',16),repeat('D',32),repeat('e',64)
  );
  perform public.connected_app_oauth_consume_permit_v2(
    p_permit,p_flow,p_connection,p_permit,p_exchange_binding,p_flow_binding,
    p_exchange_binding,p_dispatch
  );
end;
$fn$;

create or replace function public.connected_oauth_binding_finalize_v1(
  p_owner uuid,p_connection uuid,p_incarnation uuid,p_flow uuid,p_nonce_sha text,
  p_permit uuid,p_exchange_binding text,p_dispatch uuid,p_external text,
  p_broker uuid,p_credential text,p_completion uuid,p_cleanup uuid,
  p_cleanup_binding text
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  issued_at timestamptz:=pg_catalog.clock_timestamp();
begin
  return public.connected_app_oauth_finalize_v2(
    p_flow,p_flow,p_permit,p_exchange_binding,p_dispatch,p_owner,p_connection,
    p_incarnation,0,p_nonce_sha,'google','mail','personal',p_external,
    repeat('4',64),p_broker,p_credential,issued_at,issued_at+interval '1 hour',
    repeat('0',64),p_completion,repeat('f',64),p_cleanup,p_cleanup_binding
  );
end;
$fn$;

do $behavior$
declare
  owner_id constant uuid:='10000000-0000-4000-8000-000000006871';
  other_owner constant uuid:='10000000-0000-4000-8000-000000006872';
  first_result jsonb;
  loser_result jsonb;
  replay_result jsonb;
  denial_result jsonb;
  start_result jsonb;
  before_update timestamptz;
  requested_at timestamptz:=pg_catalog.clock_timestamp()-interval '1 minute';
begin
  if pg_catalog.has_function_privilege(
       'service_role','public.connected_app_operator_prepare_oauth_start_v1(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)','execute'
     ) or pg_catalog.has_function_privilege(
       'service_role','public.connected_app_oauth_finalize_v1(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,uuid,text,uuid,text)','execute'
     ) then
    raise exception 'legacy OAuth start/finalize remained callable';
  end if;

  perform public.connected_oauth_binding_seed_v1(
    owner_id,'20000000-0000-4000-8000-000000006871',
    '20000000-0000-4000-8000-000000006881',
    '30000000-0000-4000-8000-000000006871',
    '30000000-0000-4000-8000-000000006881',repeat('1',64),repeat('5',64),
    repeat('6',64),'40000000-0000-4000-8000-000000006871',repeat('7',64),
    '40000000-0000-4000-8000-000000006881'
  );
  perform public.connected_oauth_binding_seed_v1(
    owner_id,'20000000-0000-4000-8000-000000006872',
    '20000000-0000-4000-8000-000000006882',
    '30000000-0000-4000-8000-000000006872',
    '30000000-0000-4000-8000-000000006882',repeat('2',64),repeat('6',64),
    repeat('7',64),'40000000-0000-4000-8000-000000006872',repeat('8',64),
    '40000000-0000-4000-8000-000000006882'
  );

  first_result:=public.connected_oauth_binding_finalize_v1(
    owner_id,'20000000-0000-4000-8000-000000006871',
    '20000000-0000-4000-8000-000000006881',
    '30000000-0000-4000-8000-000000006871',repeat('1',64),
    '40000000-0000-4000-8000-000000006871',repeat('7',64),
    '40000000-0000-4000-8000-000000006881',repeat('d',64),
    '50000000-0000-4000-8000-000000006871',
    '338b1ef138718d611666a668477e331ce8267591c3155b2c821df5dcab999dc9',
    '30000000-0000-4000-8000-000000006871',
    '50000000-0000-4000-8000-000000006891',repeat('1',64)
  );
  if first_result->>'completed'<>'true' or first_result->>'active'<>'true' then
    raise exception 'first OAuth finalize did not activate: %',first_result;
  end if;

  loser_result:=public.connected_oauth_binding_finalize_v1(
    owner_id,'20000000-0000-4000-8000-000000006872',
    '20000000-0000-4000-8000-000000006882',
    '30000000-0000-4000-8000-000000006872',repeat('2',64),
    '40000000-0000-4000-8000-000000006872',repeat('8',64),
    '40000000-0000-4000-8000-000000006882',repeat('c',64),
    '50000000-0000-4000-8000-000000006872',
    'b6814b46c91505f8c32a0ac42897d366f6bdcfad2a27817840762fa8a617e96b',
    '30000000-0000-4000-8000-000000006872',
    '50000000-0000-4000-8000-000000006892',repeat('2',64)
  );
  if loser_result<>pg_catalog.jsonb_build_object(
       'completed',false,'active',false,
       'completion_id','30000000-0000-4000-8000-000000006872'::uuid,
       'completion_binding_sha256',repeat('f',64),
       'connection_id','20000000-0000-4000-8000-000000006872'::uuid,
       'observed_at',loser_result->'observed_at','reason','replaced'
     ) then
    raise exception 'duplicate resource loser drifted: %',loser_result;
  end if;
  if not exists(
    select 1 from connected_app_private.connections
    where id='20000000-0000-4000-8000-000000006872'
      and authorization_state='revoked' and authorization_revision=1
      and current_flow_nonce_sha256 is null
  ) or not exists(
    select 1 from connected_app_private.oauth_flows
    where flow_id='30000000-0000-4000-8000-000000006872'
      and status='invalidated'
  ) or not exists(
    select 1 from connected_app_private.credential_cleanup_outbox
    where cleanup_id='50000000-0000-4000-8000-000000006892'
      and credential_ref_sha256=
        'b6814b46c91505f8c32a0ac42897d366f6bdcfad2a27817840762fa8a617e96b'
  ) then
    raise exception 'duplicate loser was not atomically retired: connection=%, flow=%, cleanup=%, receipt=%, cleanups=%',
      (select pg_catalog.row_to_json(c) from connected_app_private.connections c
       where id='20000000-0000-4000-8000-000000006872'),
      (select pg_catalog.row_to_json(f) from connected_app_private.oauth_flows f
       where flow_id='30000000-0000-4000-8000-000000006872'),
      (select pg_catalog.row_to_json(x) from connected_app_private.credential_cleanup_outbox x
       where cleanup_id='50000000-0000-4000-8000-000000006892'),
      (select pg_catalog.row_to_json(r) from connected_oauth_binding_private.inactive_completions r
       where completion_id='30000000-0000-4000-8000-000000006872'),
      (select pg_catalog.jsonb_agg(pg_catalog.to_jsonb(x)-'broker_credential_ref')
       from connected_app_private.credential_cleanup_outbox x);
  end if;
  replay_result:=public.connected_oauth_binding_finalize_v1(
    owner_id,'20000000-0000-4000-8000-000000006872',
    '20000000-0000-4000-8000-000000006882',
    '30000000-0000-4000-8000-000000006872',repeat('2',64),
    '40000000-0000-4000-8000-000000006872',repeat('8',64),
    '40000000-0000-4000-8000-000000006882',repeat('c',64),
    '50000000-0000-4000-8000-000000006872',
    'b6814b46c91505f8c32a0ac42897d366f6bdcfad2a27817840762fa8a617e96b',
    '30000000-0000-4000-8000-000000006872',
    '50000000-0000-4000-8000-000000006892',repeat('2',64)
  );
  if replay_result<>loser_result then
    raise exception 'duplicate loser replay changed: % / %',loser_result,replay_result;
  end if;
  replay_result:=public.connected_app_oauth_read_completion_v3(
    '30000000-0000-4000-8000-000000006872',repeat('f',64),owner_id,
    '20000000-0000-4000-8000-000000006872'
  );
  if replay_result<>loser_result or not exists(
    select 1 from connected_oauth_binding_private.inactive_completions
    where completion_id='30000000-0000-4000-8000-000000006872'
      and cleanup_id='50000000-0000-4000-8000-000000006892'
      and cleanup_binding_sha256=repeat('2',64)
  ) then
    raise exception 'duplicate loser response-loss readback drifted: %',replay_result;
  end if;

  select updated_at into before_update from connected_app_private.connections
  where id='20000000-0000-4000-8000-000000006872';
  replay_result:=public.connected_oauth_binding_finalize_v1(
    other_owner,'20000000-0000-4000-8000-000000006872',
    '20000000-0000-4000-8000-000000006882',
    '30000000-0000-4000-8000-000000006872',repeat('2',64),
    '40000000-0000-4000-8000-000000006872',repeat('8',64),
    '40000000-0000-4000-8000-000000006882',repeat('c',64),
    '50000000-0000-4000-8000-000000006872',
    'b6814b46c91505f8c32a0ac42897d366f6bdcfad2a27817840762fa8a617e96b',
    '50000000-0000-4000-8000-000000006882',
    '50000000-0000-4000-8000-000000006892',repeat('2',64)
  );
  if replay_result->>'reason'<>'replaced'
     or (select updated_at from connected_app_private.connections
         where id='20000000-0000-4000-8000-000000006872')<>before_update then
    raise exception 'cross-owner finalize mutated authority: %',replay_result;
  end if;

  -- A provisional reference that is already live is never queued for cleanup,
  -- but its losing pending connection and flow are still retired.
  perform public.connected_oauth_binding_seed_v1(
    owner_id,'20000000-0000-4000-8000-000000006873',
    '20000000-0000-4000-8000-000000006883',
    '30000000-0000-4000-8000-000000006873',
    '30000000-0000-4000-8000-000000006883',repeat('3',64),repeat('7',64),
    repeat('8',64),'40000000-0000-4000-8000-000000006873',repeat('9',64),
    '40000000-0000-4000-8000-000000006883'
  );
  replay_result:=public.connected_oauth_binding_finalize_v1(
    owner_id,'20000000-0000-4000-8000-000000006873',
    '20000000-0000-4000-8000-000000006883',
    '30000000-0000-4000-8000-000000006873',repeat('3',64),
    '40000000-0000-4000-8000-000000006873',repeat('9',64),
    '40000000-0000-4000-8000-000000006883',repeat('b',64),
    '50000000-0000-4000-8000-000000006871',
    '338b1ef138718d611666a668477e331ce8267591c3155b2c821df5dcab999dc9',
    '30000000-0000-4000-8000-000000006873',
    '50000000-0000-4000-8000-000000006893',repeat('3',64)
  );
  if replay_result->>'reason'<>'replaced'
     or replay_result->>'active'<>'false'
     or exists(select 1 from connected_app_private.credential_cleanup_outbox
               where cleanup_id='50000000-0000-4000-8000-000000006893')
     or not exists(select 1 from connected_app_private.connections
                   where id='20000000-0000-4000-8000-000000006873'
                     and authorization_state='revoked')
     or not exists(select 1 from connected_app_private.oauth_flows
                   where flow_id='30000000-0000-4000-8000-000000006873'
                     and status='invalidated') then
    raise exception 'already-live credential loser handling drifted: %',replay_result;
  end if;

  perform public.connected_app_revoke_connection_v1(
    owner_id,'20000000-0000-4000-8000-000000006871',
    '50000000-0000-4000-8000-000000006894',
    '338b1ef138718d611666a668477e331ce8267591c3155b2c821df5dcab999dc9',
    repeat('4',64)
  );
  start_result:=public.connected_app_operator_prepare_oauth_start_v2(
    '60000000-0000-4000-8000-000000006871',owner_id,repeat('1',64),
    repeat('2',64),null,'60000000-0000-4000-8000-000000006872',
    '60000000-0000-4000-8000-000000006873',
    '60000000-0000-4000-8000-000000006874',
    '60000000-0000-4000-8000-000000006875',repeat('5',64),
    'google','mail','personal',array['mail.get'],repeat('3',64),repeat('4',64),
    requested_at,requested_at+interval '10 minutes'
  );
  if start_result->>'connection_id'<>'60000000-0000-4000-8000-000000006874' then
    raise exception 'reconnect after duplicate retirement failed: %',start_result;
  end if;
  if public.connected_app_operator_prepare_oauth_start_v2(
    '60000000-0000-4000-8000-000000006871',owner_id,repeat('1',64),
    repeat('2',64),null,'60000000-0000-4000-8000-000000006872',
    '60000000-0000-4000-8000-000000006873',
    '60000000-0000-4000-8000-000000006874',
    '60000000-0000-4000-8000-000000006875',repeat('5',64),
    'google','mail','personal',array['mail.get'],repeat('3',64),repeat('4',64),
    requested_at,requested_at+interval '10 minutes'
  )<>start_result then
    raise exception 'OAuth start v2 exact replay changed';
  end if;

  perform public.connected_app_oauth_create_pending_v1(
    '60000000-0000-4000-8000-000000006872',
    '60000000-0000-4000-8000-000000006873',owner_id,
    '60000000-0000-4000-8000-000000006874',
    '60000000-0000-4000-8000-000000006875',0,repeat('5',64),repeat('1',64),
    'google','mail','personal',array['mail.get'],repeat('3',64),repeat('4',64),
    'd41d04862722239994ef4f4f00f106016c1cbc7a9f91de0f4eeefb60feb503b7',
    repeat('Q',43),repeat('4',64),repeat('8',64),repeat('9',64),
    pg_catalog.clock_timestamp(),pg_catalog.clock_timestamp()+interval '5 minutes'
  );
  denial_result:=public.connected_app_operator_deny_oauth_callback_v1(
    owner_id,repeat('1',64),'google',
    'd41d04862722239994ef4f4f00f106016c1cbc7a9f91de0f4eeefb60feb503b7',
    'access_denied','b5b72d8be3069432ffc3b3d09c03af98dcd5b44e577f3410cbd61d6eb401e555',
    pg_catalog.clock_timestamp()
  );
  if denial_result->>'denied'<>'true'
     or denial_result->>'flow_id'<>'60000000-0000-4000-8000-000000006872'
     or not exists(
       select 1 from connected_app_private.connections
       where id='60000000-0000-4000-8000-000000006874'
         and authorization_state='revoked' and authorization_revision=1
     ) or not exists(
       select 1 from connected_app_private.oauth_flows
       where flow_id='60000000-0000-4000-8000-000000006872'
         and status='invalidated'
     ) or exists(
       select 1 from connected_app_private.oauth_operator_starts
       where flow_id='60000000-0000-4000-8000-000000006872'
     ) then
    raise exception 'OAuth denial retirement drifted: %',denial_result;
  end if;
  if public.connected_app_operator_deny_oauth_callback_v1(
    owner_id,repeat('1',64),'google',
    'd41d04862722239994ef4f4f00f106016c1cbc7a9f91de0f4eeefb60feb503b7',
    'access_denied','b5b72d8be3069432ffc3b3d09c03af98dcd5b44e577f3410cbd61d6eb401e555',
    pg_catalog.clock_timestamp()
  )<>denial_result then
    raise exception 'OAuth denial exact replay changed';
  end if;
  begin
    perform public.connected_app_operator_deny_oauth_callback_v1(
      other_owner,repeat('1',64),'google',
      'd41d04862722239994ef4f4f00f106016c1cbc7a9f91de0f4eeefb60feb503b7',
      'access_denied','b5b72d8be3069432ffc3b3d09c03af98dcd5b44e577f3410cbd61d6eb401e555',
      pg_catalog.clock_timestamp()
    );
    raise exception 'foreign-owner OAuth denial unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
  begin
    perform public.connected_app_operator_deny_oauth_callback_v1(
      owner_id,repeat('2',64),'google',
      'd41d04862722239994ef4f4f00f106016c1cbc7a9f91de0f4eeefb60feb503b7',
      'access_denied','b5b72d8be3069432ffc3b3d09c03af98dcd5b44e577f3410cbd61d6eb401e555',
      pg_catalog.clock_timestamp()
    );
    raise exception 'foreign-session OAuth denial unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
  begin
    perform public.connected_app_operator_deny_oauth_callback_v1(
      owner_id,repeat('1',64),'microsoft',
      'd41d04862722239994ef4f4f00f106016c1cbc7a9f91de0f4eeefb60feb503b7',
      'access_denied','b5b72d8be3069432ffc3b3d09c03af98dcd5b44e577f3410cbd61d6eb401e555',
      pg_catalog.clock_timestamp()
    );
    raise exception 'foreign-provider OAuth denial unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
  begin
    perform public.connected_app_operator_deny_oauth_callback_v1(
      owner_id,repeat('1',64),'google',repeat('0',64),'access_denied',
      'b5b72d8be3069432ffc3b3d09c03af98dcd5b44e577f3410cbd61d6eb401e555',
      pg_catalog.clock_timestamp()
    );
    raise exception 'foreign-state OAuth denial unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
  start_result:=public.connected_app_operator_prepare_oauth_start_v2(
    '60000000-0000-4000-8000-000000006876',owner_id,repeat('1',64),
    repeat('a',64),null,'60000000-0000-4000-8000-000000006877',
    '60000000-0000-4000-8000-000000006878',
    '60000000-0000-4000-8000-000000006879',
    '60000000-0000-4000-8000-000000006880',repeat('b',64),
    'google','mail','personal',array['mail.get'],repeat('3',64),repeat('4',64),
    requested_at,requested_at+interval '10 minutes'
  );
  if start_result->>'connection_id'<>'60000000-0000-4000-8000-000000006879' then
    raise exception 'OAuth denial did not permit immediate retry: %',start_result;
  end if;
end;
$behavior$;

rollback;

select 'CONNECTED_OAUTH_OWNER_BINDING_BEHAVIOR_OK' as result;
