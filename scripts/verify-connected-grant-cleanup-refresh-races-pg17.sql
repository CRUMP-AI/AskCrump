\set ON_ERROR_STOP on

-- The harness always supplies these values. Defaults are only for an explicit
-- local developer run against the disposable PostgreSQL 17 fixture.
\if :{?connected_test_host}
\else
\set connected_test_host 127.0.0.1
\endif
\if :{?connected_test_port}
\else
select pg_catalog.current_setting('port') as connected_test_port \gset
\endif
\if :{?connected_test_user}
\else
select pg_catalog.current_user as connected_test_user \gset
\endif
\if :{?connected_test_password}
\else
\set connected_test_password postgres
\endif
\if :{?connected_test_database}
\else
select pg_catalog.current_database() as connected_test_database \gset
\endif
select
  pg_catalog.set_config(
    'connected_operator_ci.host', :'connected_test_host', false
  ) as host,
  pg_catalog.set_config(
    'connected_operator_ci.port', :'connected_test_port', false
  ) as port,
  pg_catalog.set_config(
    'connected_operator_ci.user', :'connected_test_user', false
  ) as username,
  pg_catalog.set_config(
    'connected_operator_ci.password', :'connected_test_password', false
  ) as password,
  pg_catalog.set_config(
    'connected_operator_ci.database', :'connected_test_database', false
  ) as database
\gset connected_operator_ci_
\unset connected_operator_ci_host
\unset connected_operator_ci_port
\unset connected_operator_ci_username
\unset connected_operator_ci_password
\unset connected_operator_ci_database

do $connection_settings$
begin
  if pg_catalog.current_setting('connected_operator_ci.host')
       !~ '^[A-Za-z0-9.:-]+$'
     or pg_catalog.current_setting('connected_operator_ci.port')
       !~ '^[0-9]{1,5}$'
     or pg_catalog.current_setting('connected_operator_ci.port')::integer
       not between 1 and 65535
     or pg_catalog.current_setting('connected_operator_ci.user')
       !~ '^[A-Za-z_][A-Za-z0-9_$]*$'
     or pg_catalog.length(
       pg_catalog.current_setting('connected_operator_ci.password')
     ) > 512
     or pg_catalog.current_setting('connected_operator_ci.database')
       <> pg_catalog.current_database() then
    raise exception 'invalid connected operator test connection settings'
      using errcode = '22023';
  end if;
end;
$connection_settings$;

create extension if not exists dblink;

delete from public.users where id in (
  '10000000-0000-4000-8000-000000006201',
  '10000000-0000-4000-8000-000000006202'
);
delete from connected_app_private.provider_grant_cleanup_claim_history
where claim_id in (
  '50000000-0000-4000-8000-000000006200',
  '50000000-0000-4000-8000-000000006201',
  '50000000-0000-4000-8000-000000006202'
);
delete from connected_app_private.provider_grant_cleanup_jobs
where cleanup_id in (
  '30000000-0000-4000-8000-000000006202',
  '40000000-0000-4000-8000-000000006202',
  '40000000-0000-4000-8000-000000006201'
)
or source_binding_sha256 in (repeat('8',64), repeat('2',64));
delete from connected_app_private.credential_refresh_lease_history
where lease_id = '30000000-0000-4000-8000-000000006201';
delete from connected_app_private.credential_refresh_quarantines
where credential_handle_sha256 = repeat('e',64);
delete from connected_app_private.credential_secret_tombstones
where credential_handle_sha256 = repeat('e',64);

insert into public.users(id, created_at, registration_environment) values
  ('10000000-0000-4000-8000-000000006201', pg_catalog.clock_timestamp(), 'development'),
  ('10000000-0000-4000-8000-000000006202', pg_catalog.clock_timestamp(), 'development');

insert into connected_app_private.connections (
  id, owner_id, provider, resource, account_kind,
  connection_incarnation_id, authorization_revision, authorization_state,
  authorization_snapshot_sha256, granted_actions, granted_actions_sha256,
  granted_scopes_sha256, external_account_id_sha256,
  broker_credential_ref, credential_ref_sha256, authorization_expires_at
) values
  (
    '20000000-0000-4000-8000-000000006201',
    '10000000-0000-4000-8000-000000006201', 'google', 'mail', 'personal',
    '20000000-0000-4000-8000-000000006211', 1, 'active',
    repeat('a',64), array['mail.get'], repeat('b',64), repeat('c',64),
    repeat('d',64), '20000000-0000-4000-8000-000000006221', repeat('e',64),
    pg_catalog.clock_timestamp() + interval '2 hours'
  ),
  (
    '20000000-0000-4000-8000-000000006202',
    '10000000-0000-4000-8000-000000006202', 'microsoft', 'mail', 'work_school',
    '20000000-0000-4000-8000-000000006212', 1, 'active',
    repeat('1',64), array['mail.get'], repeat('2',64), repeat('3',64),
    repeat('4',64), '20000000-0000-4000-8000-000000006222', repeat('5',64),
    pg_catalog.clock_timestamp() + interval '2 hours'
  );

select public.connected_app_credential_create_v1(
  '10000000-0000-4000-8000-000000006201',
  '20000000-0000-4000-8000-000000006201', 'google', repeat('e',64),
  '20000000-0000-4000-8000-000000006211', repeat('0',64), 'personal',
  1, repeat('a',64), repeat('b',64), repeat('c',64), repeat('d',64),
  (select authorization_expires_at from connected_app_private.connections
   where id = '20000000-0000-4000-8000-000000006201'),
  1, '2026-11-08T05:00:00Z', '2026-11-08T05:00:00Z',
  repeat('6',64), repeat('7',64), 'credential-key', repeat('A',16),
  repeat('B',64), repeat('C',16), repeat('D',32), repeat('8',64)
);

select public.connected_app_credential_claim_refresh_v2(
  repeat('e',64), repeat('8',64),
  '30000000-0000-4000-8000-000000006201', 30
);

select public.connected_app_provider_cleanup_begin_v1(
  '40000000-0000-4000-8000-000000006202',
  '10000000-0000-4000-8000-000000006201',
  '20000000-0000-4000-8000-000000006201',
  '40000000-0000-4000-8000-000000006202',
  'google', repeat('0',64), pg_catalog.clock_timestamp() + interval '5 minutes'
);
select public.connected_app_provider_cleanup_attach_v1(
  '40000000-0000-4000-8000-000000006202', repeat('0',64),
  'credential', repeat('8',64),
  (
    select pg_catalog.to_jsonb(credential.*)
    from connected_app_private.credential_envelopes as credential
    where credential.credential_handle_sha256 = repeat('e',64)
  )
);
update connected_app_private.provider_grant_cleanup_jobs
set status = 'cleanup_pending', updated_at = pg_catalog.clock_timestamp()
where cleanup_id = '40000000-0000-4000-8000-000000006202';
select public.connected_app_provider_cleanup_claim_v1(
  '50000000-0000-4000-8000-000000006200', 30
);

select public.connected_app_provider_cleanup_begin_v1(
  '40000000-0000-4000-8000-000000006201',
  '10000000-0000-4000-8000-000000006202',
  '20000000-0000-4000-8000-000000006202',
  '40000000-0000-4000-8000-000000006201',
  'microsoft', repeat('1',64), pg_catalog.clock_timestamp() + interval '5 minutes'
);
select public.connected_app_provider_cleanup_attach_v1(
  '40000000-0000-4000-8000-000000006201', repeat('1',64),
  'provisional', repeat('2',64),
  pg_catalog.jsonb_build_object(
    'credential_handle_sha256', repeat('5',64),
    'secret_ciphertext', repeat('X',32),
    'record_binding_sha256', repeat('2',64)
  )
);
update connected_app_private.provider_grant_cleanup_jobs
set status = 'cleanup_pending', updated_at = pg_catalog.clock_timestamp()
where cleanup_id = '40000000-0000-4000-8000-000000006201';

do $races$
declare
  connection_text text := pg_catalog.format(
    'dbname=%L host=%L port=%s user=%L password=%L',
    pg_catalog.current_setting('connected_operator_ci.database'),
    pg_catalog.current_setting('connected_operator_ci.host'),
    pg_catalog.current_setting('connected_operator_ci.port'),
    pg_catalog.current_setting('connected_operator_ci.user'),
    pg_catalog.current_setting('connected_operator_ci.password')
  );
  response_text text;
  remote_error text;
  claim jsonb;
  fresh jsonb;
begin
  perform public.dblink_connect('cleanup_refresh_a', connection_text);
  perform public.dblink_connect('cleanup_refresh_b', connection_text);

  -- Authority change wins while an old refresh claimant is delayed. The
  -- delayed claimant must never commit rotated ciphertext after the owner
  -- lock is released.
  perform public.dblink_exec('cleanup_refresh_a', 'begin');
  perform response
  from public.dblink(
    'cleanup_refresh_a',
    $sql$select connected_app_private.owner_lock_v1(
      '10000000-0000-4000-8000-000000006201'
    )::text$sql$
  ) as remote_result(response text);
  perform public.dblink_exec('cleanup_refresh_a', 'set local role service_role');
  perform response
  from public.dblink(
    'cleanup_refresh_a',
    $sql$select public.connected_app_revoke_connection_v1(
      '10000000-0000-4000-8000-000000006201',
      '20000000-0000-4000-8000-000000006201',
      '30000000-0000-4000-8000-000000006202', repeat('e',64), repeat('0',64)
    )::text$sql$
  ) as remote_result(response text);
  perform public.dblink_exec('cleanup_refresh_b', 'begin');
  perform public.dblink_exec('cleanup_refresh_b', 'set local role service_role');
  perform public.dblink_send_query(
    'cleanup_refresh_b',
    $sql$select public.connected_app_credential_commit_refresh_v2(
      p_owner_id => '10000000-0000-4000-8000-000000006201',
      p_connection_id => '20000000-0000-4000-8000-000000006201',
      p_provider => 'google', p_credential_handle_sha256 => repeat('e',64),
      p_connection_incarnation_id => '20000000-0000-4000-8000-000000006211',
      p_oauth_client_id_sha256 => repeat('0',64), p_account_kind => 'personal',
      p_authorization_revision => 1,
      p_authorization_snapshot_sha256 => repeat('a',64),
      p_granted_actions_sha256 => repeat('b',64),
      p_granted_scopes_sha256 => repeat('c',64),
      p_external_account_id_hash => repeat('d',64),
      p_authorization_expires_at => '2099-01-01T00:00:00Z', p_secret_revision => 2,
      p_created_at => '2026-11-08T05:00:00Z',
      p_updated_at => '2026-11-08T05:01:00Z',
      p_authority_binding_sha256 => repeat('6',64),
      p_metadata_binding_sha256 => repeat('9',64), p_key_id => 'credential-key',
      p_wrapped_key_nonce => repeat('E',16),
      p_wrapped_key_ciphertext => repeat('F',64),
      p_secret_nonce => repeat('G',16), p_secret_ciphertext => repeat('H',32),
      p_record_binding_sha256 => repeat('f',64),
      p_expected_record_binding_sha256 => repeat('8',64),
      p_lease_id => '30000000-0000-4000-8000-000000006201'
    )::text$sql$
  );
  perform pg_catalog.pg_sleep(0.08);
  perform public.dblink_exec('cleanup_refresh_a', 'commit');
  response_text := null;
  select response into response_text
  from public.dblink_get_result('cleanup_refresh_b', false)
    as remote_result(response text);
  remote_error := public.dblink_error_message('cleanup_refresh_b');
  perform public.dblink_get_result('cleanup_refresh_b', false);
  perform public.dblink_exec('cleanup_refresh_b', 'rollback');
  if response_text is not null
     or (
       remote_error not like '%credential refresh v2 commit authority drifted%'
       and remote_error not like '%credential refresh v2 commit generation retired%'
     ) then
    raise exception 'authority-winner refresh commit was not fenced: %, %',
      response_text, remote_error;
  end if;
  if exists (
       select 1 from connected_app_private.credential_envelopes
       where credential_handle_sha256 = repeat('e',64)
     ) or not exists (
       select 1 from connected_app_private.credential_secret_tombstones
       where credential_handle_sha256 = repeat('e',64)
     ) then
    raise exception 'stale refresh claimant changed ciphertext after revocation';
  end if;
  if not exists (
       select 1 from connected_app_private.provider_grant_cleanup_claim_history
       where claim_id = '50000000-0000-4000-8000-000000006200'
         and cleanup_id = '40000000-0000-4000-8000-000000006202'
         and outcome = 'expired'
     ) or public.connected_app_provider_cleanup_claim_v1(
       '50000000-0000-4000-8000-000000006200', 30
     )->>'status' <> 'stale' then
    raise exception 'direct credential revocation did not permanently retire cleanup claim';
  end if;

  -- The refresh-revocation fixture created its own cleanup job. It has served
  -- its fencing assertion; remove that exact fixture row so the next claim is
  -- deterministically the attached account-deletion race below.
  perform public.dblink_exec(
    'cleanup_refresh_a',
    $sql$delete from connected_app_private.provider_grant_cleanup_jobs
      where source_binding_sha256 = repeat('8',64)$sql$
  );

  -- Claim wins briefly, then account deletion must retire that claim, preserve
  -- encrypted cleanup custody, and make the stale worker unable to settle.
  perform public.dblink_exec('cleanup_refresh_a', 'begin');
  perform public.dblink_exec('cleanup_refresh_a', 'set local role service_role');
  select response::jsonb into claim
  from public.dblink(
    'cleanup_refresh_a',
    $sql$select public.connected_app_provider_cleanup_claim_v1(
      '50000000-0000-4000-8000-000000006201', 30
    )::text$sql$
  ) as remote_result(response text);
  if claim->>'status' <> 'claimed' then
    raise exception 'cleanup claim race setup failed: %', claim;
  end if;
  perform public.dblink_exec('cleanup_refresh_b', 'begin');
  perform public.dblink_send_query(
    'cleanup_refresh_b',
    $sql$delete from public.users
      where id = '10000000-0000-4000-8000-000000006202'$sql$
  );
  perform pg_catalog.pg_sleep(0.08);
  perform public.dblink_exec('cleanup_refresh_a', 'commit');
  perform response
  from public.dblink_get_result('cleanup_refresh_b') as remote_result(response text);
  perform response
  from public.dblink_get_result('cleanup_refresh_b') as remote_result(response text);
  perform public.dblink_exec('cleanup_refresh_b', 'commit');

  begin
    perform public.connected_app_provider_cleanup_finish_v1(
      '40000000-0000-4000-8000-000000006201',
      '50000000-0000-4000-8000-000000006201',
      'user_action_required', null
    );
    raise exception 'stale cleanup claimant settled after account deletion';
  exception when sqlstate '55000' then
    null;
  end;
  if not exists (
    select 1 from connected_app_private.provider_grant_cleanup_claim_history
    where claim_id = '50000000-0000-4000-8000-000000006201'
      and outcome = 'expired'
  ) or not exists (
    select 1 from connected_app_private.provider_grant_cleanup_jobs
    where cleanup_id = '40000000-0000-4000-8000-000000006201'
      and owner_id is null and connection_id is null
      and encrypted_record is not null and status = 'cleanup_pending'
  ) then
    raise exception 'account deletion lost cleanup custody or replay fencing';
  end if;
  fresh := public.connected_app_provider_cleanup_claim_v1(
    '50000000-0000-4000-8000-000000006202', 30
  );
  if fresh->>'status' <> 'claimed'
     or fresh->'record'->>'cleanup_id' <> '40000000-0000-4000-8000-000000006201' then
    raise exception 'fresh post-deletion cleanup worker could not recover custody: %', fresh;
  end if;

  perform public.dblink_disconnect('cleanup_refresh_a');
  perform public.dblink_disconnect('cleanup_refresh_b');
exception when others then
  begin perform public.dblink_disconnect('cleanup_refresh_a'); exception when others then null; end;
  begin perform public.dblink_disconnect('cleanup_refresh_b'); exception when others then null; end;
  raise;
end;
$races$;

delete from public.users where id = '10000000-0000-4000-8000-000000006201';
delete from connected_app_private.provider_grant_cleanup_jobs
where cleanup_id = '40000000-0000-4000-8000-000000006201';

select 'CONNECTED_GRANT_CLEANUP_REFRESH_RACES_OK' as result;
