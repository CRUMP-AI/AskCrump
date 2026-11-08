\set ON_ERROR_STOP on

create or replace function public.connected_retention_test_id_v1(p_value text)
returns uuid language sql immutable set search_path='' as $fn$
  select (
    pg_catalog.substr(pg_catalog.md5(p_value),1,8)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),9,4)||'-4'||
    pg_catalog.substr(pg_catalog.md5(p_value),14,3)||'-8'||
    pg_catalog.substr(pg_catalog.md5(p_value),18,3)||'-'||
    pg_catalog.substr(pg_catalog.md5(p_value),21,12)
  )::uuid
$fn$;

create or replace function public.connected_retention_test_sha_v1(p_value text)
returns text language sql immutable set search_path='' as $fn$
  select pg_catalog.md5(p_value||':left')||pg_catalog.md5(p_value||':right')
$fn$;

create or replace function public.connected_retention_test_seed_payload_v1(
  p_lane text,p_expired boolean
) returns uuid language plpgsql set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  owner_id uuid:=public.connected_retention_test_id_v1(p_lane||':owner');
  connection_id uuid:=public.connected_retention_test_id_v1(p_lane||':connection');
  v_payload_id uuid:=public.connected_retention_test_id_v1(p_lane||':payload');
  created_at timestamptz;
  expires_at timestamptz;
begin
  if p_expired then
    created_at:=now_at-interval '2 hours';
    expires_at:=now_at-interval '1 hour';
  else
    created_at:=now_at;
    expires_at:=now_at+interval '1 hour';
  end if;
  delete from public.users where id=owner_id;
  delete from connected_app_private.payload_tombstones
  where payload_id=v_payload_id;
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(owner_id,owner_id::text||'@retention.example.test',
    '$argon2id$retention-v1',true,false,now_at-interval '1 day',now_at,
    'production',now_at-interval '1 day',false,now_at-interval '1 day');
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_expires_at
  ) values(connection_id,owner_id,'google','mail','personal',
    public.connected_retention_test_id_v1(p_lane||':incarnation'),1,'active',
    public.connected_retention_test_sha_v1(p_lane||':authorization'),
    array['mail.send'],public.connected_retention_test_sha_v1(p_lane||':actions'),
    public.connected_retention_test_sha_v1(p_lane||':scopes'),
    public.connected_retention_test_sha_v1(p_lane||':external'),
    public.connected_retention_test_id_v1(p_lane||':credential'),
    public.connected_retention_test_sha_v1(p_lane||':credential-handle'),
    now_at+interval '1 day');
  perform public.connected_app_payload_put_v1(
    v_payload_id,owner_id,connection_id,
    public.connected_retention_test_id_v1(p_lane||':action'),
    'google','mail.send','retention-commitment',
    public.connected_retention_test_sha_v1(p_lane||':payload-sha'),
    created_at,expires_at,
    public.connected_retention_test_sha_v1(p_lane||':identity'),
    public.connected_retention_test_sha_v1(p_lane||':reference'),
    'retention-envelope',repeat('A',16),repeat('B',64),repeat('C',16),
    repeat('D',64),public.connected_retention_test_sha_v1(p_lane||':record'));
  return v_payload_id;
end;
$fn$;

create or replace function public.connected_retention_test_seed_plan_v1(
  p_lane text,p_expired boolean
) returns uuid language plpgsql set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  owner_id uuid:=public.connected_retention_test_id_v1(p_lane||':owner');
  session_id uuid:=public.connected_retention_test_id_v1(p_lane||':session');
  chat_id uuid:=public.connected_retention_test_id_v1(p_lane||':chat');
  message_id uuid:=public.connected_retention_test_id_v1(p_lane||':message');
  planning_id uuid:=public.connected_retention_test_id_v1(p_lane||':planning');
  v_payload_id uuid:=public.connected_retention_test_id_v1(p_lane||':payload');
  invocation_id uuid:=public.connected_retention_test_id_v1(p_lane||':invocation');
  claim record;
begin
  delete from public.users where id=owner_id;
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values(owner_id,owner_id::text||'@retention.example.test',
    '$argon2id$retention-v1',true,false,now_at-interval '1 day',now_at,
    'production',now_at-interval '1 day',false,now_at-interval '1 day');
  insert into public.sessions(
    id,user_id,token_hash,device_id,device_name,platform,device_info,
    created_at,last_activity,expires_at
  ) values(session_id,owner_id,
    pg_catalog.md5(session_id::text)||pg_catalog.md5(session_id::text||':token'),
    session_id::text,'Retention test','web','{}'::jsonb,
    now_at,now_at,now_at+interval '1 day');
  select * into strict claim from public.connected_chat_claim_turn_v1(
    owner_id,chat_id,message_id,
    public.connected_retention_test_sha_v1(p_lane||':origin'),
    public.connected_retention_test_sha_v1(p_lane||':request'));
  perform public.connected_plan_begin_v1(
    owner_id,session_id,chat_id,message_id,claim.turn_id,claim.claim_token,
    public.connected_retention_test_sha_v1(p_lane||':origin'),
    public.connected_retention_test_sha_v1(p_lane||':request'),planning_id,
    'retention-plan-binding',
    public.connected_retention_test_sha_v1(p_lane||':plan-binding'),v_payload_id,
    now_at,now_at+interval '15 minutes');
  perform public.connected_plan_mark_invoked_v1(
    owner_id,session_id,chat_id,message_id,claim.turn_id,claim.claim_token,
    public.connected_retention_test_sha_v1(p_lane||':origin'),
    public.connected_retention_test_sha_v1(p_lane||':request'),planning_id,
    'retention-plan-binding',
    public.connected_retention_test_sha_v1(p_lane||':plan-binding'),v_payload_id,
    now_at,now_at+interval '15 minutes',invocation_id);
  perform public.connected_plan_envelope_put_v1(
    owner_id,claim.turn_id,planning_id,
    public.connected_retention_test_sha_v1(p_lane||':plan-binding'),v_payload_id,
    'retention-plan-commitment',
    public.connected_retention_test_sha_v1(p_lane||':payload-sha'),
    public.connected_retention_test_sha_v1(p_lane||':reference'),
    now_at,now_at+interval '15 minutes','retention-plan-envelope',
    repeat('E',16),repeat('F',64),repeat('G',16),repeat('H',64),
    public.connected_retention_test_sha_v1(p_lane||':record'));
  if p_expired then
    update connected_plan_private.envelopes as envelope
    set created_at=now_at-interval '2 minutes',
        expires_at=now_at-interval '1 minute'
    where envelope.payload_id=v_payload_id;
  end if;
  return v_payload_id;
end;
$fn$;

do $behavior$
declare
  expired_payload uuid;
  live_payload uuid;
  expired_plan uuid;
  live_plan uuid;
  result jsonb;
begin
  expired_payload:=public.connected_retention_test_seed_payload_v1(
    'retention-behavior-expired-payload',true);
  live_payload:=public.connected_retention_test_seed_payload_v1(
    'retention-behavior-live-payload',false);
  expired_plan:=public.connected_retention_test_seed_plan_v1(
    'retention-behavior-expired-plan',true);
  live_plan:=public.connected_retention_test_seed_plan_v1(
    'retention-behavior-live-plan',false);

  result:=public.connected_app_purge_expired_ciphertext_v1(10,10,10);
  if result<>'{"payloads_purged":1,"plans_purged":1,"loop_envelopes_purged":0}'::jsonb then
    raise exception 'retention behavior count drifted: %',result;
  end if;
  if exists(select 1 from connected_app_private.payload_envelopes
            where payload_id=expired_payload)
     or not exists(select 1 from connected_app_private.payload_tombstones
                   where payload_id=expired_payload and record_existed)
     or (public.connected_app_payload_read_v1(
           expired_payload,
           public.connected_retention_test_sha_v1(
             'retention-behavior-expired-payload:identity'))->>'status')<>'erased'
     or not exists(select 1 from connected_app_private.payload_envelopes
                   where payload_id=live_payload and payload_ciphertext=repeat('D',64)) then
    raise exception 'payload physical retention invariant failed';
  end if;
  if not exists(
       select 1 from connected_plan_private.envelopes
       where payload_id=expired_plan and record_state='deleted'
         and commitment_key_id is null and payload_sha256 is null
         and reference_binding_sha256 is null and key_id is null
         and wrapped_key_nonce is null and wrapped_key_ciphertext is null
         and payload_nonce is null and payload_ciphertext is null
         and record_binding_sha256 is null and deleted_at is not null)
     or public.connected_plan_envelope_read_v1(
          public.connected_retention_test_id_v1(
            'retention-behavior-expired-plan:owner'),
          (select turn_id from connected_plan_private.envelopes
           where payload_id=expired_plan),
          public.connected_retention_test_id_v1(
            'retention-behavior-expired-plan:planning'),
          public.connected_retention_test_sha_v1(
            'retention-behavior-expired-plan:plan-binding'),expired_plan) is not null
     or not exists(select 1 from connected_plan_private.envelopes
                   where payload_id=live_plan and record_state='live'
                     and payload_ciphertext=repeat('H',64)) then
    raise exception 'plan ciphertext tombstone invariant failed';
  end if;
  if public.connected_app_purge_expired_ciphertext_v1(10,10,10)
       <>'{"payloads_purged":0,"plans_purged":0,"loop_envelopes_purged":0}'::jsonb then
    raise exception 'retention replay was not idempotent';
  end if;
end;
$behavior$;

do $bounded$
declare result jsonb;
begin
  perform public.connected_retention_test_seed_payload_v1('retention-bound-a',true);
  perform public.connected_retention_test_seed_payload_v1('retention-bound-b',true);
  result:=public.connected_app_purge_expired_ciphertext_v1(1,1,1);
  if result->>'payloads_purged'<>'1'
     or (select count(*) from connected_app_private.payload_envelopes
         where owner_id in(
           public.connected_retention_test_id_v1('retention-bound-a:owner'),
           public.connected_retention_test_id_v1('retention-bound-b:owner')))<>1 then
    raise exception 'retention payload bound failed: %',result;
  end if;
  perform public.connected_app_purge_expired_ciphertext_v1(10,10,10);
end;
$bounded$;

do $cleanup$
declare lane text;
begin
  foreach lane in array array[
    'retention-behavior-expired-payload','retention-behavior-live-payload',
    'retention-behavior-expired-plan','retention-behavior-live-plan',
    'retention-bound-a','retention-bound-b']
  loop
    delete from public.users
    where id=public.connected_retention_test_id_v1(lane||':owner');
  end loop;
end;
$cleanup$;

drop function public.connected_retention_test_seed_plan_v1(text,boolean);
drop function public.connected_retention_test_seed_payload_v1(text,boolean);
drop function public.connected_retention_test_sha_v1(text);
drop function public.connected_retention_test_id_v1(text);

select 'CONNECTED_CIPHERTEXT_RETENTION_BEHAVIOR_OK' as result;
