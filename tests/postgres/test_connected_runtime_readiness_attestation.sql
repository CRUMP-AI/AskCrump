\set ON_ERROR_STOP on

begin;

insert into public.users(
  id,email,password_hash,is_verified,is_guest,created_at,updated_at,
  registration_environment,registration_submitted_at,
  password_setup_required,password_inbox_bound_at
) values(
  '69000000-0000-4000-8000-000000000001',
  'readiness-690@example.test','$argon2id$readiness-690',true,false,
  pg_catalog.clock_timestamp()-interval '1 day',pg_catalog.clock_timestamp(),
  'production',pg_catalog.clock_timestamp()-interval '1 day',false,
  pg_catalog.clock_timestamp()-interval '1 day'
);
insert into public.sessions(id,user_id,token_hash,expires_at,revoked_at) values(
  '69000000-0000-4000-8000-000000000002',
  '69000000-0000-4000-8000-000000000001',repeat('1',64),
  pg_catalog.clock_timestamp()+interval '2 hours',null
);
insert into connected_oauth_code_private.release_bootstrap_dedicated_attestations(
  ceremony_id,owner_id,session_id,descriptor_matrix_sha256,
  dedicated_account_attestation_sha256,confirmed_at
) values(
  '69000000-0000-4000-8000-000000000003',
  '69000000-0000-4000-8000-000000000001',
  '69000000-0000-4000-8000-000000000002',repeat('2',64),repeat('3',64),
  pg_catalog.clock_timestamp()
);
insert into connected_app_private.connections(
  id,owner_id,provider,resource,account_kind,connection_incarnation_id,
  authorization_revision,authorization_state,authorization_snapshot_sha256,
  granted_actions,granted_actions_sha256,granted_scopes_sha256,
  external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
  current_flow_nonce_sha256,authorization_expires_at
) values(
  '69000000-0000-4000-8000-000000000021',
  '69000000-0000-4000-8000-000000000001','microsoft','mail','personal',
  '69000000-0000-4000-8000-000000000022',1,'active',repeat('d',64),
  array['mail.get'],repeat('e',64),repeat('f',64),repeat('a',64),
  '69000000-0000-4000-8000-000000000023',repeat('c',64),repeat('b',64),
  pg_catalog.clock_timestamp()+interval '2 hours'
);

set local role service_role;

do $retirement$
declare
  expiry timestamptz;
  reference timestamptz:=pg_catalog.clock_timestamp();
  binding jsonb;
  erased jsonb;
  retired jsonb;
begin
  binding:=public.connected_app_get_binding_v2(
    '69000000-0000-4000-8000-000000000001',
    '69000000-0000-4000-8000-000000000021');
  expiry:=(binding->>'authorization_expires_at')::timestamptz;
  perform public.connected_app_credential_create_v1(
    '69000000-0000-4000-8000-000000000001',
    '69000000-0000-4000-8000-000000000021','microsoft',repeat('c',64),
    '69000000-0000-4000-8000-000000000022',repeat('1',64),'personal',
    1,repeat('d',64),repeat('e',64),repeat('f',64),repeat('a',64),expiry,
    1,reference,reference,repeat('2',64),repeat('3',64),'preview-key',
    repeat('A',16),repeat('B',64),repeat('C',16),repeat('D',32),repeat('4',64)
  );
  -- This is the exact Python crash-recovery boundary: credential erasure has
  -- committed while the connection is still active.  The retirement RPC must
  -- complete from descriptor/binding metadata without reopening token material.
  erased:=public.connected_app_credential_delete_v1(
    repeat('c',64),repeat('4',64),reference+interval '1 second');
  if erased->>'status'<>'erased' or erased->>'record_existed'<>'true' then
    raise exception 'credential erasure did not commit: %',erased;
  end if;
  retired:=public.connected_app_release_preview_retire_connection_v1(
    '69000000-0000-4000-8000-000000000001',
    '69000000-0000-4000-8000-000000000021',
    '69000000-0000-4000-8000-000000000022',1,repeat('b',64),
    repeat('d',64),repeat('c',64),
    '69000000-0000-4000-8000-000000000024',repeat('5',64));
  if retired->>'retired'<>'true' or retired->>'credential_erased'<>'true'
     or (retired->>'authorization_revision')::bigint<>2 then
    raise exception 'erase-first retirement result drifted: %',retired;
  end if;
  if public.connected_app_release_preview_retire_connection_v1(
       '69000000-0000-4000-8000-000000000001',
       '69000000-0000-4000-8000-000000000021',
       '69000000-0000-4000-8000-000000000022',1,repeat('b',64),
       repeat('d',64),repeat('c',64),
       '69000000-0000-4000-8000-000000000024',repeat('5',64)
     )->>'credential_erased'<>'true' then
    raise exception 'retirement response-loss replay did not attest erasure';
  end if;
  binding:=public.connected_app_get_binding_v2(
    '69000000-0000-4000-8000-000000000001',
    '69000000-0000-4000-8000-000000000021');
  if binding->>'authorization_state'<>'revoked'
     or (binding->>'authorization_revision')::bigint<>2
     or binding->>'broker_credential_ref' is not null
     or binding->>'credential_ref_sha256' is not null
     or public.connected_app_credential_read_v1(repeat('c',64))->>'status'
       <>'erased' then
    raise exception 'retirement final postconditions drifted';
  end if;
end;
$retirement$;

reset role;
do $retirement_private$
begin
  if exists(
      select 1 from connected_app_private.credential_envelopes
      where credential_handle_sha256=repeat('c',64))
     or not exists(
      select 1 from connected_app_private.credential_secret_tombstones
      where credential_handle_sha256=repeat('c',64)) then
    raise exception 'retirement private erasure postconditions drifted';
  end if;
end;
$retirement_private$;
set local role service_role;

do $private_boundary$
begin
  begin
    perform 1 from connected_readiness_private.provider_smoke;
    raise exception 'service_role read private provider smoke';
  exception when insufficient_privilege then null;
  end;
  begin
    perform 1 from connected_readiness_private.release_preview_effect;
    raise exception 'service_role read private release-preview effects';
  exception when insufficient_privilege then null;
  end;
end;
$private_boundary$;

do $behavior$
declare
  invocation_id uuid;
  target_fingerprint text;
  effects jsonb:=pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000011',
      'provider','google','account_kind','personal','resource','mail',
      'marker_sha256',repeat('a',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000012',
      'provider','google','account_kind','personal','resource','calendar',
      'marker_sha256',repeat('b',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000013',
      'provider','microsoft','account_kind','personal','resource','mail',
      'marker_sha256',repeat('c',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000014',
      'provider','microsoft','account_kind','personal','resource','calendar',
      'marker_sha256',repeat('d',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000015',
      'provider','microsoft','account_kind','work_school','resource','mail',
      'marker_sha256',repeat('e',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000016',
      'provider','microsoft','account_kind','work_school','resource','calendar',
      'marker_sha256',repeat('f',64))
  );
  claimed jsonb;
  begun jsonb;
  state record;
  challenge jsonb;
  challenge_id uuid;
  recorded jsonb;
  readiness jsonb;
begin
  target_fingerprint:='59714dce4c61f8140eddc1a2c8606b70';

  begin
    perform * from public.connected_app_runtime_readiness_v1(
      repeat('4',64),
      '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a',
      target_fingerprint,
      'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6',
      'dpl_12345678abcd',repeat('5',40),repeat('6',64),'gkms1',
      '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f');
    raise exception 'runtime readiness succeeded without provider smoke';
  exception when sqlstate '55000' then null;
  end;

  select pg_catalog.to_jsonb(result) into strict claimed
  from public.connected_app_claim_release_preview_ceremony_v1(
    '69000000-0000-4000-8000-000000000004',
    '69000000-0000-4000-8000-000000000001',repeat('7',64),repeat('8',64),
    'dpl_12345678abcd',repeat('5',40),repeat('6',64)) as result;
  invocation_id:=(claimed->>'invocation_id')::uuid;
  if (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(claimed))<>7
     or claimed->>'recovery'<>'false'
     or (claimed->>'expires_at')::timestamptz<=
       (claimed->>'issued_at')::timestamptz
     or (claimed->>'expires_at')::timestamptz>
       (claimed->>'issued_at')::timestamptz+interval '15 minutes' then
    raise exception 'release-preview claim drifted: %',claimed;
  end if;

  select public.connected_app_release_preview_begin_v1(
    invocation_id,
    '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f',
    repeat('2',64),repeat('3',64),repeat('9',64),'personal',effects,
    repeat('4',64),
    '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a',
    target_fingerprint,
    'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6',
    'dpl_12345678abcd',repeat('5',40),repeat('6',64),'gkms1'
  ) into strict begun;
  if begun->>'invocation_id'<>invocation_id::text
     or begun->>'effect_manifest_sha256'<>repeat('9',64)
     or (begun->>'effects')::integer<>6 then
    raise exception 'release-preview begin drifted: %',begun;
  end if;

  for state in
    select * from public.connected_app_release_preview_status_v1(invocation_id)
  loop
    perform public.connected_app_release_preview_effect_v1(
      invocation_id,state.effect_id,0,'pending','dispatched',null);
    perform public.connected_app_release_preview_effect_v1(
      invocation_id,state.effect_id,1,'dispatched','observed',repeat('0',64));
    perform public.connected_app_release_preview_effect_v1(
      invocation_id,state.effect_id,2,'observed','cleanup',repeat('0',64));
    perform public.connected_app_release_preview_effect_v1(
      invocation_id,state.effect_id,3,'cleanup',
      case when state.resource='mail'
        then 'retained_test_artifact' else 'clean' end,repeat('0',64));
  end loop;
  if (select pg_catalog.count(*)
      from public.connected_app_release_preview_status_v1(invocation_id))<>6 then
    raise exception 'release-preview effect status count drifted';
  end if;
  for state in
    select *
    from public.connected_app_release_preview_authority_status_v1(invocation_id)
  loop
    if state.provider='google' then
      perform public.connected_app_release_preview_authority_v1(
        invocation_id,state.provider,state.account_kind,0,'pending',
        'revocation_dispatched',null);
      perform public.connected_app_release_preview_authority_v1(
        invocation_id,state.provider,state.account_kind,1,
        'revocation_dispatched','revocation_attested',repeat('b',64));
      perform public.connected_app_release_preview_authority_v1(
        invocation_id,state.provider,state.account_kind,2,
        'revocation_attested','local_retired',repeat('b',64));
    else
      perform public.connected_app_release_preview_authority_v1(
        invocation_id,state.provider,state.account_kind,0,'pending',
        'local_retired',null);
    end if;
  end loop;
  if (select pg_catalog.count(*)
      from public.connected_app_release_preview_authority_status_v1(invocation_id)
      where phase='local_retired')<>3 then
    raise exception 'release-preview authority status drifted';
  end if;
  perform public.connected_app_release_preview_finalize_v1(invocation_id);

  select pg_catalog.to_jsonb(issued) into strict challenge
  from public.connected_app_issue_provider_smoke_challenge_v1(
    repeat('4',64),
    '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a',
    target_fingerprint,
    'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6',
    'dpl_12345678abcd',repeat('5',40),repeat('6',64),'gkms1',
    '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f',
    repeat('2',64),repeat('3',64),invocation_id,repeat('9',64)) as issued;
  challenge_id:=(challenge->>'challenge_id')::uuid;
  if (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(challenge))<>16
     or challenge->>'database_target_fingerprint'<>target_fingerprint
     or challenge->>'release_preview_invocation_id'<>invocation_id::text then
    raise exception 'provider smoke challenge drifted: %',challenge;
  end if;

  select pg_catalog.to_jsonb(result) into strict recorded
  from public.connected_app_record_provider_smoke_v1(
    repeat('4',64),
    '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a',
    target_fingerprint,
    'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6',
    'dpl_12345678abcd',repeat('5',40),repeat('6',64),'gkms1',
    '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f',
    repeat('2',64),repeat('3',64),invocation_id,repeat('9',64),
    challenge_id,repeat('a',64)) as result;
  if (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(recorded))<>14
     or recorded->>'release_preview_invocation_id'<>invocation_id::text then
    raise exception 'provider smoke record drifted: %',recorded;
  end if;

  begin
    perform public.connected_app_record_provider_smoke_v1(
      repeat('4',64),
      '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a',
      target_fingerprint,
      'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6',
      'dpl_12345678abcd',repeat('5',40),repeat('6',64),'gkms1',
      '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f',
      repeat('2',64),repeat('3',64),invocation_id,repeat('9',64),
      challenge_id,repeat('a',64));
    raise exception 'provider smoke challenge replay succeeded';
  exception when sqlstate '55000' then null;
  end;

  select pg_catalog.to_jsonb(result) into strict readiness
  from public.connected_app_runtime_readiness_v1(
    repeat('4',64),
    '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a',
    target_fingerprint,
    'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6',
    'dpl_12345678abcd',repeat('5',40),repeat('6',64),'gkms1',
    '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f')
    as result;
  if (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(readiness))<>19
     or readiness->>'provider_smoke_attestation_sha256'<>repeat('a',64)
     or readiness->>'release_preview_invocation_id'<>invocation_id::text
     or (readiness->>'expires_at')::timestamptz<=
       (readiness->>'checked_at')::timestamptz
     or (readiness->>'expires_at')::timestamptz>
       (readiness->>'checked_at')::timestamptz+interval '15 minutes' then
    raise exception 'runtime readiness response drifted: %',readiness;
  end if;

  begin
    perform * from public.connected_app_claim_release_preview_ceremony_v1(
      '69000000-0000-4000-8000-000000000005',
      '69000000-0000-4000-8000-000000000001',repeat('7',64),repeat('8',64),
      'dpl_12345678abcd',repeat('5',40),repeat('6',64));
    raise exception 'terminal release-preview ceremony replay succeeded';
  exception when sqlstate '55000' then null;
  end;

  select pg_catalog.to_jsonb(result) into strict claimed
  from public.connected_app_claim_release_preview_ceremony_v1(
    '69000000-0000-4000-8000-000000000006',
    '69000000-0000-4000-8000-000000000001',repeat('7',64),repeat('8',64),
    'dpl_87654321dcba',repeat('6',40),repeat('7',64)) as result;
  if (claimed->>'invocation_id')=invocation_id::text
     or claimed->>'deployment_id'<>'dpl_87654321dcba' then
    raise exception 'release-preview terminal generation rollover drifted: %',
      claimed;
  end if;
end;
$behavior$;

reset role;

do $failed_generation$
<<failed_generation>>
declare
  invocation_id uuid;
  claimed jsonb;
  begun jsonb;
  failed jsonb;
  effect_row record;
  authority_row record;
  effects jsonb:=pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000031',
      'provider','google','account_kind','personal','resource','mail',
      'marker_sha256',repeat('a',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000032',
      'provider','google','account_kind','personal','resource','calendar',
      'marker_sha256',repeat('b',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000033',
      'provider','microsoft','account_kind','personal','resource','mail',
      'marker_sha256',repeat('c',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000034',
      'provider','microsoft','account_kind','personal','resource','calendar',
      'marker_sha256',repeat('d',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000035',
      'provider','microsoft','account_kind','work_school','resource','mail',
      'marker_sha256',repeat('e',64)),
    pg_catalog.jsonb_build_object('effect_id','69000000-0000-4000-8000-000000000036',
      'provider','microsoft','account_kind','work_school','resource','calendar',
      'marker_sha256',repeat('f',64))
  );
begin
  select ceremony.invocation_id into strict invocation_id
  from connected_readiness_private.release_preview_ceremony as ceremony
  where ceremony.status='running'
    and ceremony.deployment_id='dpl_87654321dcba';
  begun:=public.connected_app_release_preview_begin_v1(
    invocation_id,
    '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f',
    repeat('2',64),repeat('3',64),repeat('a',64),'personal',effects,
    repeat('4',64),
    '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a',
    '59714dce4c61f8140eddc1a2c8606b70',
    'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6',
    'dpl_87654321dcba',repeat('6',40),repeat('7',64),'gkms1');
  if begun->>'invocation_id'<>invocation_id::text then
    raise exception 'failed-generation begin drifted: %',begun;
  end if;

  -- Expiry never authorizes a new provider effect, but it also must not make
  -- a fully retired content-free failure impossible to record. First prove
  -- the same expired invocation cannot terminalize with unsettled authority.
  update connected_readiness_private.release_preview_ceremony as ceremony
  set issued_at=pg_catalog.statement_timestamp()-interval '15 minutes',
      expires_at=pg_catalog.statement_timestamp()-interval '1 second'
  where ceremony.invocation_id=failed_generation.invocation_id;
  begin
    perform public.connected_app_release_preview_fail_v1(invocation_id);
    raise exception 'expired invocation failed with unsettled authority';
  exception when sqlstate '55000' then null;
  end;
  if (select ceremony.status
      from connected_readiness_private.release_preview_ceremony as ceremony
      where ceremony.invocation_id=failed_generation.invocation_id)<>'running'
     or (select invocation.status
         from connected_readiness_private.release_preview_invocation as invocation
         where invocation.invocation_id=failed_generation.invocation_id)<>'running'
     or (select pg_catalog.count(*)
         from connected_readiness_private.release_preview_effect as effect
         where effect.invocation_id=failed_generation.invocation_id
           and effect.phase='pending')<>6 then
    raise exception 'unsettled-authority failure attempt mutated state';
  end if;

  -- Provider-effect and authority transitions themselves remain forbidden
  -- after expiry. Renew only this test generation to drive the exact cleanup
  -- states, then expire it again before terminal failure below.
  update connected_readiness_private.release_preview_ceremony as ceremony
  set issued_at=pg_catalog.statement_timestamp(),
      expires_at=pg_catalog.statement_timestamp()+interval '15 minutes'
  where ceremony.invocation_id=failed_generation.invocation_id
    and ceremony.status='running';

  for authority_row in
    select *
    from public.connected_app_release_preview_authority_status_v1(invocation_id)
  loop
    if authority_row.provider='google' then
      perform public.connected_app_release_preview_authority_v1(
        invocation_id,authority_row.provider,authority_row.account_kind,0,
        'pending','revocation_dispatched',null);
      perform public.connected_app_release_preview_authority_v1(
        invocation_id,authority_row.provider,authority_row.account_kind,1,
        'revocation_dispatched','revocation_attested',repeat('b',64));
      perform public.connected_app_release_preview_authority_v1(
        invocation_id,authority_row.provider,authority_row.account_kind,2,
        'revocation_attested','local_retired',repeat('b',64));
    else
      perform public.connected_app_release_preview_authority_v1(
        invocation_id,authority_row.provider,authority_row.account_kind,0,
        'pending','local_retired',null);
    end if;
  end loop;

  select * into strict effect_row
  from public.connected_app_release_preview_status_v1(invocation_id)
  where provider='google' and account_kind='personal' and resource='mail';
  perform public.connected_app_release_preview_effect_v1(
    invocation_id,effect_row.effect_id,0,'pending','dispatched',null);
  perform public.connected_app_release_preview_effect_v1(
    invocation_id,effect_row.effect_id,1,'dispatched','observed',repeat('0',64));
  begin
    perform public.connected_app_release_preview_fail_v1(invocation_id);
    raise exception 'failure terminalized an observed artifact';
  exception when sqlstate '55000' then null;
  end;
  if (select ceremony.status
      from connected_readiness_private.release_preview_ceremony as ceremony
      where ceremony.invocation_id=failed_generation.invocation_id)<>'running'
     or (select effect.phase
         from connected_readiness_private.release_preview_effect as effect
         where effect.effect_id=effect_row.effect_id)<>'observed' then
    raise exception 'observed-artifact failure attempt mutated state';
  end if;
  perform public.connected_app_release_preview_effect_v1(
    invocation_id,effect_row.effect_id,2,'observed','cleanup',repeat('0',64));
  begin
    perform public.connected_app_release_preview_fail_v1(invocation_id);
    raise exception 'failure terminalized an in-progress cleanup';
  exception when sqlstate '55000' then null;
  end;
  if (select invocation.status
      from connected_readiness_private.release_preview_invocation as invocation
      where invocation.invocation_id=failed_generation.invocation_id)<>'running'
     or (select effect.phase
         from connected_readiness_private.release_preview_effect as effect
         where effect.effect_id=effect_row.effect_id)<>'cleanup' then
    raise exception 'cleanup-artifact failure attempt mutated state';
  end if;
  perform public.connected_app_release_preview_effect_v1(
    invocation_id,effect_row.effect_id,3,'cleanup','retained_test_artifact',
    repeat('0',64));

  update connected_readiness_private.release_preview_ceremony as ceremony
  set issued_at=pg_catalog.statement_timestamp()-interval '15 minutes',
      expires_at=pg_catalog.statement_timestamp()-interval '1 second'
  where ceremony.invocation_id=failed_generation.invocation_id
    and ceremony.status='running';
  failed:=public.connected_app_release_preview_fail_v1(invocation_id);
  if failed->>'status'<>'failed'
     or failed->>'invocation_id'<>invocation_id::text
     or (failed->>'unknown_effects')::integer<>5 then
    raise exception 'expired fully-retired failure drifted: %',failed;
  end if;
  if public.connected_app_release_preview_fail_v1(invocation_id)<>failed then
    raise exception 'failed invocation replay was not exact';
  end if;
  if (select pg_catalog.count(*)
      from connected_readiness_private.release_preview_effect as effect
      where effect.invocation_id=failed_generation.invocation_id
        and effect.phase='effect_unknown')<>5
     or (select pg_catalog.count(*)
         from connected_readiness_private.release_preview_effect as effect
         where effect.invocation_id=failed_generation.invocation_id
           and effect.phase='retained_test_artifact')<>1 then
    raise exception 'failed invocation fabricated cleanup state';
  end if;

  begin
    perform * from public.connected_app_claim_release_preview_ceremony_v1(
      '69000000-0000-4000-8000-000000000007',
      '69000000-0000-4000-8000-000000000001',repeat('7',64),repeat('8',64),
      'dpl_87654321dcba',repeat('6',40),repeat('7',64));
    raise exception 'failed terminal tuple restarted';
  exception when sqlstate '55000' then null;
  end;
  select pg_catalog.to_jsonb(result) into strict claimed
  from public.connected_app_claim_release_preview_ceremony_v1(
    '69000000-0000-4000-8000-000000000008',
    '69000000-0000-4000-8000-000000000001',repeat('7',64),repeat('8',64),
    'dpl_freshgen690',repeat('7',40),repeat('8',64)) as result;
  if claimed->>'invocation_id'=invocation_id::text
     or claimed->>'deployment_id'<>'dpl_freshgen690' then
    raise exception 'failed terminal generation rollover drifted: %',claimed;
  end if;
end;
$failed_generation$;

do $history$
begin
  if (select pg_catalog.count(*)
      from connected_readiness_private.release_preview_ceremony)<>3
     or not exists(
       select 1 from connected_readiness_private.release_preview_ceremony
       where status='succeeded' and deployment_id='dpl_12345678abcd'
         and commit_sha=repeat('5',40)
         and host_configuration_ciphertext_sha256=repeat('6',64))
     or not exists(
       select 1 from connected_readiness_private.release_preview_ceremony
       where status='failed' and deployment_id='dpl_87654321dcba'
         and commit_sha=repeat('6',40)
         and host_configuration_ciphertext_sha256=repeat('7',64))
     or not exists(
       select 1 from connected_readiness_private.release_preview_ceremony
       where status='running' and deployment_id='dpl_freshgen690'
         and commit_sha=repeat('7',40)
         and host_configuration_ciphertext_sha256=repeat('8',64)) then
    raise exception 'release-preview immutable history was not preserved';
  end if;
end;
$history$;

set local role anon;
do $anon_boundary$
begin
  begin
    perform * from public.connected_app_runtime_readiness_v1(
      repeat('4',64),
      '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a',
      repeat('0',32),
      'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6',
      'dpl_12345678abcd',repeat('5',40),repeat('6',64),'gkms1',
      '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f');
    raise exception 'anon executed runtime readiness';
  exception when insufficient_privilege then null;
  end;
end;
$anon_boundary$;
reset role;

grant execute on function public.connected_app_runtime_readiness_v1(
  text,text,text,text,text,text,text,text,text) to authenticated;
set local role service_role;
do $catalog_drift$
declare target_fingerprint text:='59714dce4c61f8140eddc1a2c8606b70';
begin
  begin
    perform * from public.connected_app_runtime_readiness_v1(
      repeat('4',64),
      '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a',
      target_fingerprint,
      'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6',
      'dpl_12345678abcd',repeat('5',40),repeat('6',64),'gkms1',
      '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f');
    raise exception 'runtime readiness ignored catalog privilege drift';
  exception when sqlstate '55000' then null;
  end;
end;
$catalog_drift$;
reset role;

rollback;

select 'CONNECTED_RUNTIME_READINESS_ATTESTATION_OK' as result;
