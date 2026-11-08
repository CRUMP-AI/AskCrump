\set ON_ERROR_STOP on

begin;

create or replace function public.connected_oauth_688_id_v1(p_value text)
returns uuid language sql immutable set search_path='' as $fn$
  select (
    pg_catalog.substr(pg_catalog.md5(p_value),1,8)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),9,4)||'-4'||
    pg_catalog.substr(pg_catalog.md5(p_value),14,3)||'-8'||
    pg_catalog.substr(pg_catalog.md5(p_value),18,3)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),21,12)
  )::uuid
$fn$;

create or replace function public.connected_oauth_688_sha_v1(p_value text)
returns text language sql immutable set search_path='' as $fn$
  select pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(p_value,'UTF8')),'hex'
  )
$fn$;

create or replace function public.connected_oauth_688_seed_v1(
  p_lane text,p_created_at timestamptz,p_expires_at timestamptz
) returns void language plpgsql set search_path='' as $fn$
declare
  owner_id uuid:=public.connected_oauth_688_id_v1(p_lane||':owner');
  connection_id uuid:=public.connected_oauth_688_id_v1(p_lane||':connection');
  incarnation_id uuid:=public.connected_oauth_688_id_v1(p_lane||':incarnation');
  flow_id uuid:=public.connected_oauth_688_id_v1(p_lane||':flow');
  nonce_id uuid:=public.connected_oauth_688_id_v1(p_lane||':nonce');
begin
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(
    owner_id,owner_id::text||'@oauth-688.example.test',
    '$argon2id$oauth-688',true,false,p_created_at-interval '1 day',
    pg_catalog.clock_timestamp(),'production',p_created_at-interval '1 day',
    false,p_created_at-interval '1 day'
  ) on conflict(id) do nothing;
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,current_flow_nonce_sha256
  ) values(
    connection_id,owner_id,'google','mail','personal',incarnation_id,0,
    'pending',public.connected_oauth_688_sha_v1(p_lane||':nonce')
  );
  perform public.connected_app_oauth_secret_begin_v1(
    flow_id,nonce_id,owner_id,connection_id,incarnation_id,0,
    public.connected_oauth_688_sha_v1(p_lane||':nonce'),
    public.connected_oauth_688_sha_v1(p_lane||':session'),
    'google','mail','personal',array['mail.get'],
    public.connected_oauth_688_sha_v1(p_lane||':actions'),array['scope'],
    public.connected_oauth_688_sha_v1(p_lane||':scopes'),
    public.connected_oauth_688_sha_v1(p_lane||':state'),repeat('P',43),
    'https://www.askcrump.com/api/connected-apps/oauth/callback/google',
    p_created_at,p_expires_at,
    public.connected_oauth_688_sha_v1(p_lane||':flow-binding'),
    'oauth-688-key',repeat('A',16),repeat('B',64),repeat('C',16),
    repeat('D',64),public.connected_oauth_688_sha_v1(p_lane||':secret-record')
  );
  perform public.connected_app_oauth_create_pending_v1(
    flow_id,nonce_id,owner_id,connection_id,incarnation_id,0,
    public.connected_oauth_688_sha_v1(p_lane||':nonce'),
    public.connected_oauth_688_sha_v1(p_lane||':session'),
    'google','mail','personal',array['mail.get'],
    public.connected_oauth_688_sha_v1(p_lane||':actions'),
    public.connected_oauth_688_sha_v1(p_lane||':scopes'),
    public.connected_oauth_688_sha_v1(p_lane||':state'),repeat('P',43),
    public.connected_oauth_688_sha_v1(p_lane||':redirect'),
    public.connected_oauth_688_sha_v1(p_lane||':flow-binding'),
    public.connected_oauth_688_sha_v1(p_lane||':start-receipt'),
    p_created_at,p_expires_at
  );
end;
$fn$;

create or replace function public.connected_oauth_688_accept_v1(
  p_lane text,p_received_at timestamptz
) returns jsonb language plpgsql set search_path='' as $fn$
declare
  target_flow_id uuid:=public.connected_oauth_688_id_v1(p_lane||':flow');
begin
  return public.connected_app_operator_accept_oauth_callback_v2(
    public.connected_oauth_688_id_v1(p_lane||':owner'),
    public.connected_oauth_688_sha_v1(p_lane||':session'),'google',target_flow_id,
    target_flow_id,target_flow_id,
    public.connected_oauth_688_id_v1(p_lane||':connection'),
    public.connected_oauth_688_id_v1(p_lane||':incarnation'),
    public.connected_oauth_688_sha_v1(p_lane||':nonce'),
    public.connected_oauth_688_sha_v1(p_lane||':state'),
    public.connected_oauth_688_sha_v1(p_lane||':callback'),
    public.connected_oauth_688_sha_v1(p_lane||':flow-binding'),
    public.connected_oauth_688_sha_v1(p_lane||':consume'),
    public.connected_oauth_688_sha_v1(p_lane||':exchange'),
    public.connected_oauth_688_sha_v1(repeat('P',43)),
    public.connected_oauth_688_sha_v1(p_lane||':redirect'),
    public.connected_oauth_688_sha_v1(p_lane||':authorization-code'),
    public.connected_oauth_688_sha_v1(p_lane||':code-authority'),
    p_received_at,least(
      (select row_value.expires_at
       from connected_app_private.oauth_flows as row_value
       where row_value.flow_id=target_flow_id),
      p_received_at+interval '2 minutes'
    ),0,'oauth-code-688',repeat('N',16),repeat('C',64),
    public.connected_oauth_688_sha_v1(p_lane||':code-record')
  );
end;
$fn$;

do $exact_catalog_drift$
declare
  expected_fingerprint text;
  drifted_fingerprint text;
begin
  expected_fingerprint:=
    connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1();
  if expected_fingerprint<>'5e4480837c5ebb316da85be988a6561f'
     or exists(
       select 1
       from pg_catalog.pg_attribute as attribute_row
       join pg_catalog.pg_class as class_row
         on class_row.oid=attribute_row.attrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname='connected_oauth_code_private'
         and class_row.relname in (
           'authorization_code_custody',
           'release_bootstrap_dedicated_attestations'
         )
         and attribute_row.attnum>0
         and not attribute_row.attisdropped
         and attribute_row.attacl is not null
     )
     or exists(
       select 1
       from pg_catalog.pg_policy as policy_row
       join pg_catalog.pg_class as class_row
         on class_row.oid=policy_row.polrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname='connected_oauth_code_private'
     ) then
    raise exception 'code custody exact ACL/policy baseline drifted';
  end if;
  execute 'grant select(flow_id) on connected_oauth_code_private.authorization_code_custody to service_role';
  drifted_fingerprint:=
    connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1();
  if drifted_fingerprint=expected_fingerprint then
    raise exception 'column ACL drift was not fingerprinted';
  end if;
  execute 'revoke select(flow_id) on connected_oauth_code_private.authorization_code_custody from service_role';
  if connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()
       <>expected_fingerprint then
    raise exception 'column ACL cleanup did not restore exact target';
  end if;
  execute 'create policy oauth_688_drift_policy on connected_oauth_code_private.authorization_code_custody for select to service_role using (true)';
  drifted_fingerprint:=
    connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1();
  if drifted_fingerprint=expected_fingerprint then
    raise exception 'RLS policy drift was not fingerprinted';
  end if;
  execute 'drop policy oauth_688_drift_policy on connected_oauth_code_private.authorization_code_custody';
  if connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()
       <>expected_fingerprint then
    raise exception 'RLS policy cleanup did not restore exact target';
  end if;
end;
$exact_catalog_drift$;

do $behavior$
declare
  lane constant text:='available';
  target_flow_id uuid:=public.connected_oauth_688_id_v1(lane||':flow');
  owner_id uuid:=public.connected_oauth_688_id_v1(lane||':owner');
  callback_received_at timestamptz:=pg_catalog.clock_timestamp();
  result jsonb;
  first_claim timestamptz;
  second_claim timestamptz;
  attempt_id uuid:=public.connected_oauth_688_id_v1(lane||':attempt');
begin
  if pg_catalog.has_schema_privilege(
       'service_role','connected_oauth_code_private','usage')
     or pg_catalog.has_table_privilege(
       'service_role',
       'connected_oauth_code_private.authorization_code_custody','select')
     or pg_catalog.has_table_privilege(
       'service_role',
       'connected_oauth_code_private.release_bootstrap_dedicated_attestations',
       'select')
     or pg_catalog.has_function_privilege(
       'authenticated',
       'public.connected_app_oauth_code_claim_v1(uuid,text,text,uuid,uuid,uuid,text,text)',
       'execute')
     or pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_operator_accept_oauth_callback_v1(text,text,text,timestamp with time zone,uuid,uuid,uuid,uuid,bigint,text,text,text,text)',
       'execute') then
    raise exception 'code custody direct authority escaped service-only RPCs';
  end if;
  perform public.connected_oauth_688_seed_v1(
    lane,callback_received_at-interval '1 minute',
    callback_received_at+interval '4 minutes'
  );
  result:=public.connected_oauth_688_accept_v1(lane,callback_received_at);
  if result->>'flow_id'<>target_flow_id::text
     or not exists(
       select 1
       from connected_oauth_code_private.authorization_code_custody as code
       where code.flow_id=target_flow_id and code.status='available'
         and code.code_ciphertext=repeat('C',64)
         and code.expires_at=callback_received_at+interval '2 minutes'
     ) then
    raise exception 'atomic callback/code custody acceptance drifted: %',result;
  end if;
  result:=public.connected_app_oauth_code_read_v1(
    owner_id,public.connected_oauth_688_sha_v1(lane||':session'),'google',
    target_flow_id,target_flow_id,target_flow_id,
    public.connected_oauth_688_id_v1(lane||':connection'),
    public.connected_oauth_688_id_v1(lane||':incarnation'),
    public.connected_oauth_688_sha_v1(lane||':nonce'),
    public.connected_oauth_688_sha_v1(lane||':state'),
    public.connected_oauth_688_sha_v1(lane||':callback'),
    public.connected_oauth_688_sha_v1(lane||':flow-binding'),
    public.connected_oauth_688_sha_v1(lane||':consume'),
    public.connected_oauth_688_sha_v1(lane||':exchange'),
    public.connected_oauth_688_sha_v1(repeat('P',43)),
    public.connected_oauth_688_sha_v1(lane||':redirect'),
    public.connected_oauth_688_sha_v1(lane||':authorization-code'),
    public.connected_oauth_688_sha_v1(lane||':code-authority'),
    callback_received_at,callback_received_at+interval '2 minutes'
  );
  if result->>'status'<>'available' or result->>'code_ciphertext'<>repeat('C',64) then
    raise exception 'response-loss readback drifted: %',result;
  end if;
  result:=public.connected_app_oauth_code_claim_v1(
    owner_id,public.connected_oauth_688_sha_v1(lane||':session'),'google',
    target_flow_id,target_flow_id,target_flow_id,
    public.connected_oauth_688_sha_v1(lane||':exchange'),
    public.connected_oauth_688_sha_v1(lane||':state')
  );
  first_claim:=(result->>'claimed_at')::timestamptz;
  result:=public.connected_app_oauth_code_claim_v1(
    owner_id,public.connected_oauth_688_sha_v1(lane||':session'),'google',
    target_flow_id,target_flow_id,target_flow_id,
    public.connected_oauth_688_sha_v1(lane||':exchange'),
    public.connected_oauth_688_sha_v1(lane||':state')
  );
  second_claim:=(result->>'claimed_at')::timestamptz;
  if first_claim is null or second_claim<>first_claim then
    raise exception 'lost-process code claim was not idempotent';
  end if;
  begin
    perform public.connected_app_oauth_code_claim_v1(
      owner_id,repeat('0',64),'google',target_flow_id,target_flow_id,
      target_flow_id,
      public.connected_oauth_688_sha_v1(lane||':exchange'),
      public.connected_oauth_688_sha_v1(lane||':state')
    );
    raise exception 'wrong-session code claim unexpectedly succeeded';
  exception when sqlstate '55000' then null;
  end;
  perform public.connected_app_oauth_secret_fence_v1(
    target_flow_id,target_flow_id,
    public.connected_oauth_688_sha_v1(lane||':exchange'),
    public.connected_oauth_688_sha_v1(lane||':flow-binding'),attempt_id,
    callback_received_at+interval '1 minute'
  );
  begin
    perform public.connected_app_oauth_code_claim_v1(
      owner_id,public.connected_oauth_688_sha_v1(lane||':session'),'google',
      target_flow_id,target_flow_id,target_flow_id,
      public.connected_oauth_688_sha_v1(lane||':exchange'),
      public.connected_oauth_688_sha_v1(lane||':state')
    );
    raise exception 'code reopened after durable exchange fence';
  exception when sqlstate '55000' then null;
  end;
  result:=public.connected_app_oauth_code_retire_v1(
    owner_id,public.connected_oauth_688_sha_v1(lane||':session'),'google',
    target_flow_id,target_flow_id,target_flow_id,
    public.connected_oauth_688_sha_v1(lane||':exchange'),
    public.connected_oauth_688_sha_v1(lane||':state'),'ambiguous'
  );
  if result->>'retired'<>'true' or not exists(
    select 1
    from connected_oauth_code_private.authorization_code_custody as code
    where code.flow_id=target_flow_id and code.status='retired'
      and code.code_ciphertext is null and code.code_nonce is null
      and code.code_key_id is null
  ) then
    raise exception 'terminal code erasure drifted: %',result;
  end if;
end;
$behavior$;

do $expired_and_fresh$
declare
  lane constant text:='expired';
  fresh_lane constant text:='expired-fresh';
  target_flow_id uuid:=public.connected_oauth_688_id_v1(lane||':flow');
  owner_id uuid:=public.connected_oauth_688_id_v1(lane||':owner');
  received_at timestamptz:=pg_catalog.clock_timestamp()-interval '2 minutes 1 second';
  result jsonb;
begin
  perform public.connected_oauth_688_seed_v1(
    lane,received_at-interval '10 seconds',pg_catalog.clock_timestamp()+interval '2 minutes'
  );
  perform public.connected_oauth_688_accept_v1(lane,received_at);
  result:=public.connected_app_oauth_code_retire_v1(
    owner_id,public.connected_oauth_688_sha_v1(lane||':session'),'google',
    target_flow_id,target_flow_id,target_flow_id,
    public.connected_oauth_688_sha_v1(lane||':exchange'),
    public.connected_oauth_688_sha_v1(lane||':state'),'safe_restart'
  );
  if result->>'retired'<>'true' then
    raise exception 'expired undispatched code did not retire safely: %',result;
  end if;
  -- A fresh generation gets a distinct state/code custody row after retirement.
  perform public.connected_oauth_688_seed_v1(
    fresh_lane,pg_catalog.clock_timestamp()-interval '1 minute',
    pg_catalog.clock_timestamp()+interval '4 minutes'
  );
  perform public.connected_oauth_688_accept_v1(
    fresh_lane,pg_catalog.clock_timestamp()
  );
  if not exists(
    select 1
    from connected_oauth_code_private.authorization_code_custody as code
    where code.flow_id=public.connected_oauth_688_id_v1(fresh_lane||':flow')
      and code.status='available'
  ) then
    raise exception 'fresh OAuth generation was blocked after safe retirement';
  end if;
end;
$expired_and_fresh$;

do $attestation$
declare
  lane constant text:='attestation';
  owner_id uuid:=public.connected_oauth_688_id_v1(lane||':owner');
  session_id uuid:=public.connected_oauth_688_id_v1(lane||':session-id');
  ceremony_id uuid:=public.connected_oauth_688_id_v1(lane||':ceremony');
  matrix_sha text:=public.connected_oauth_688_sha_v1(lane||':matrix');
  attestation_sha text;
  result jsonb;
begin
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(
    owner_id,owner_id::text||'@oauth-688.example.test','$argon2id$oauth-688',
    true,false,pg_catalog.clock_timestamp()-interval '1 day',
    pg_catalog.clock_timestamp(),'production',
    pg_catalog.clock_timestamp()-interval '1 day',false,
    pg_catalog.clock_timestamp()-interval '1 day'
  );
  insert into public.sessions(id,user_id,token_hash,expires_at)
  values(session_id,owner_id,public.connected_oauth_688_sha_v1(lane||':token'),
    pg_catalog.clock_timestamp()+interval '1 hour');
  attestation_sha:=
    connected_oauth_code_private.dedicated_attestation_sha256_v1(
      ceremony_id,owner_id,matrix_sha
    );
  result:=public.connected_app_release_bootstrap_attest_dedicated_v1(
    ceremony_id,owner_id,session_id,
    public.connected_oauth_688_sha_v1(session_id::text),matrix_sha,
    attestation_sha
  );
  if result->>'owner_id'<>owner_id::text
     or result->>'descriptor_matrix_sha256'<>matrix_sha
     or result->>'dedicated_account_attestation_sha256'<>attestation_sha
     or public.connected_app_release_bootstrap_read_dedicated_v1(
       attestation_sha
     )<>result then
    raise exception 'dedicated-account attestation receipt drifted: %',result;
  end if;
  begin
    perform public.connected_app_release_bootstrap_attest_dedicated_v1(
      ceremony_id,owner_id,session_id,
      public.connected_oauth_688_sha_v1(session_id::text),matrix_sha,
      attestation_sha
    );
    raise exception 'dedicated-account confirmation replay unexpectedly inserted';
  exception when unique_violation then null;
  end;
  delete from public.users where id=owner_id;
  if public.connected_app_release_bootstrap_read_dedicated_v1(
       attestation_sha
     ) is not null then
    raise exception 'account deletion retained dedicated-account attestation';
  end if;
end;
$attestation$;

-- Code custody is erased with its account, with no orphaned private authority.
delete from public.users
where id=public.connected_oauth_688_id_v1('available:owner');
do $deletion$
begin
  if exists(
    select 1 from connected_oauth_code_private.authorization_code_custody
    where owner_id=public.connected_oauth_688_id_v1('available:owner')
  ) then
    raise exception 'account deletion retained authorization-code custody';
  end if;
end;
$deletion$;

rollback;

select 'CONNECTED_OAUTH_CODE_CUSTODY_BEHAVIOR_OK' as result;
