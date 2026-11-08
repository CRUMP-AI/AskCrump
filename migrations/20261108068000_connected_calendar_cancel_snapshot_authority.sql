\set ON_ERROR_STOP on

begin;

select pg_catalog.set_config('search_path','pg_catalog,public',true);
select pg_catalog.set_config('quote_all_identifiers','off',true);

do $preflight$
declare
  predecessor_fingerprint text;
  target_fingerprint text;
begin
  if pg_catalog.to_regprocedure(
       'connected_cancel_private.cancel_snapshot_target_fingerprint_v1()'
     ) is not null then
    select connected_cancel_private.cancel_snapshot_target_fingerprint_v1()
      into target_fingerprint;
    if target_fingerprint <> '755dbb418bb4cef4d102f1587ee1c99a' then
      raise exception 'connected cancellation snapshot target drifted: %',
        target_fingerprint using errcode='55000';
    end if;
    return;
  end if;

  if pg_catalog.to_regprocedure(
       'connected_loop_private.multi_step_target_fingerprint_v1()'
     ) is null then
    raise exception 'connected cancellation snapshot predecessor is absent'
      using errcode='55000';
  end if;
  select connected_loop_private.multi_step_target_fingerprint_v1()
    into predecessor_fingerprint;
  if predecessor_fingerprint <> 'a63bd463531f048bac9024b17d5823c1' then
    raise exception 'connected cancellation snapshot predecessor drifted: %',
      predecessor_fingerprint using errcode='55000';
  end if;

  if pg_catalog.to_regclass('connected_app_private.action_preparations') is null
     or pg_catalog.to_regclass('connected_app_private.task_grants') is null
     or pg_catalog.to_regclass('connected_app_private.connections') is null
     or pg_catalog.to_regclass('connected_chat_private.turns') is null
     or pg_catalog.to_regclass('connected_plan_private.operations') is null
     or pg_catalog.to_regclass('connected_schedule_private.templates') is null
     or pg_catalog.to_regclass('connected_schedule_private.occurrences') is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.action_preparation_view_v1(uuid,uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null then
    raise exception 'connected cancellation snapshot predecessor is incomplete'
      using errcode='55000';
  end if;

  if pg_catalog.to_regnamespace('connected_cancel_private') is not null
     or exists(
       select 1
       from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=proc_row.pronamespace
       where namespace_row.nspname='public'
         and proc_row.proname in (
           'connected_app_prepare_cancel_snapshot_chat_v1',
           'connected_app_prepare_cancel_snapshot_schedule_v1',
           'connected_app_begin_cancel_snapshot_chat_v1',
           'connected_app_begin_cancel_snapshot_schedule_v1')) then
    raise exception 'connected cancellation snapshot target is partial'
      using errcode='55000';
  end if;

  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_app_private'),
         pg_catalog.to_regnamespace('connected_chat_private'),
         pg_catalog.to_regnamespace('connected_schedule_private'),
         pg_catalog.to_regnamespace('connected_cancel_private')))
     or exists(
       select 1
       from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname in (
         'connected_app_private','connected_chat_private',
         'connected_schedule_private','connected_cancel_private')) then
    raise exception 'connected cancellation snapshot publication exposure refused'
      using errcode='55000';
  end if;
end;
$preflight$;

create schema if not exists connected_cancel_private authorization postgres;
comment on schema connected_cancel_private is
  'ASK_CRUMP_CONNECTED_CANCEL_SNAPSHOT_V1_PRIVATE_CONTENT_FREE_AUTHORITY';
revoke all on schema connected_cancel_private
  from public,anon,authenticated,service_role;

create table if not exists connected_cancel_private.snapshot_reads (
  request_id uuid primary key
    references connected_app_private.action_preparations(request_id)
    on delete cascade,
  owner_id uuid not null references public.users(id) on delete cascade,
  session_id uuid not null,
  session_binding_sha256 text not null
    check(session_binding_sha256~'^[0-9a-f]{64}$'),
  source_kind text not null check(source_kind in ('chat','schedule')),
  source_id uuid not null,
  source_claim_id uuid not null,
  chat_id uuid,
  message_id uuid,
  schedule_id uuid,
  occurrence_id uuid,
  turn_id uuid not null,
  connection_id uuid not null
    references connected_app_private.connections(id) on delete cascade,
  grant_id uuid not null unique,
  action_id uuid not null unique,
  task_id uuid not null,
  command_binding_sha256 text not null
    check(command_binding_sha256~'^[0-9a-f]{64}$'),
  resource_version_sha256 text not null
    check(resource_version_sha256~'^[0-9a-f]{64}$'),
  status text not null default 'prepared'
    check(status in ('prepared','started')),
  requested_at timestamptz not null,
  expires_at timestamptz not null,
  started_at timestamptz,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_cancel_snapshot_source_shape check(
    (source_kind='chat' and chat_id is not null and message_id is not null
      and schedule_id is null and occurrence_id is null)
    or
    (source_kind='schedule' and chat_id is null and message_id is null
      and schedule_id is not null and occurrence_id is not null)),
  constraint connected_cancel_snapshot_status_shape check(
    (status='prepared' and started_at is null)
    or (status='started' and started_at is not null)),
  constraint connected_cancel_snapshot_time_shape check(
    expires_at>requested_at
    and expires_at<=requested_at+interval '5 minutes'
    and updated_at>=requested_at
    and (started_at is null or started_at>=requested_at)),
  unique(owner_id,source_kind,source_id,source_claim_id,request_id)
);
comment on table connected_cancel_private.snapshot_reads is
  'ASK_CRUMP_CONNECTED_CANCEL_SNAPSHOT_READS_V1_CONTENT_FREE_PARENT_CHILD_FENCE';
comment on column connected_cancel_private.snapshot_reads.resource_version_sha256 is
  'ASK_CRUMP_CONNECTED_CANCEL_EXPECTED_PROVIDER_RESOURCE_VERSION_SHA256';
create index if not exists connected_cancel_snapshot_owner_idx
  on connected_cancel_private.snapshot_reads(owner_id,updated_at desc,request_id);
create index if not exists connected_cancel_snapshot_source_idx
  on connected_cancel_private.snapshot_reads(
    source_kind,source_id,source_claim_id,status,expires_at);
alter table connected_cancel_private.snapshot_reads enable row level security;
alter table connected_cancel_private.snapshot_reads force row level security;
revoke all on table connected_cancel_private.snapshot_reads
  from public,anon,authenticated,service_role;

create or replace function connected_cancel_private.prepare_snapshot_v1(
  p_source_kind text,p_source_id uuid,p_source_claim_id uuid,
  p_chat_id uuid,p_message_id uuid,p_schedule_id uuid,p_occurrence_id uuid,
  p_request_id uuid,p_owner_id uuid,p_session_id uuid,
  p_session_binding_sha256 text,p_command_binding_sha256 text,
  p_grant_id uuid,p_action_id uuid,p_task_id uuid,p_turn_id uuid,
  p_connection_id uuid,p_provider text,p_resource text,p_action text,
  p_authorization_revision bigint,p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text,p_granted_scopes_sha256 text,
  p_task_state_revision bigint,p_parameters_payload_id uuid,
  p_parameters_reference_binding_sha256 text,p_parameters_sha256 text,
  p_resource_version_sha256 text,p_policy_version text,
  p_requested_at timestamptz,p_expires_at timestamptz
) returns jsonb
language plpgsql security definer set search_path='' as $fn$
declare
  preparation_row connected_app_private.action_preparations%rowtype;
  snapshot_row connected_cancel_private.snapshot_reads%rowtype;
  connection_row connected_app_private.connections%rowtype;
  identity_value uuid;
  now_at timestamptz:=pg_catalog.clock_timestamp();
  grant_actions_sha256 constant text:=
    'c2baacb1b196e947ab293e04fdf3baf96bca3fd8e3dbec20d43e1be891e004a5';
begin
  if p_source_kind not in ('chat','schedule')
     or p_source_id is null or p_source_claim_id is null
     or p_request_id is null or p_owner_id is null or p_session_id is null
     or p_grant_id is null or p_action_id is null or p_task_id is null
     or p_turn_id is null or p_connection_id is null
     or p_session_binding_sha256!~'^[0-9a-f]{64}$'
     or p_command_binding_sha256!~'^[0-9a-f]{64}$'
     or p_provider not in ('google','microsoft')
     or p_resource<>'calendar' or p_action<>'calendar.get'
     or p_authorization_revision<1 or p_task_state_revision<1
     or p_authorization_snapshot_sha256!~'^[0-9a-f]{64}$'
     or p_granted_actions_sha256!~'^[0-9a-f]{64}$'
     or p_granted_scopes_sha256!~'^[0-9a-f]{64}$'
     or p_parameters_payload_id is null
     or p_parameters_reference_binding_sha256!~'^[0-9a-f]{64}$'
     or p_parameters_sha256!~'^[0-9a-f]{64}$'
     or p_resource_version_sha256!~'^[0-9a-f]{64}$'
     or p_policy_version<>'connected-app-policy-v1'
     or p_requested_at<now_at-interval '5 minutes'
     or p_requested_at>now_at+interval '1 minute'
     or p_expires_at<=now_at or p_expires_at<=p_requested_at
     or p_expires_at>p_requested_at+interval '5 minutes'
     or (p_source_kind='chat' and (
       p_chat_id is null or p_message_id is null
       or p_schedule_id is not null or p_occurrence_id is not null))
     or (p_source_kind='schedule' and (
       p_chat_id is not null or p_message_id is not null
       or p_schedule_id is null or p_occurrence_id is null)) then
    raise exception 'invalid cancellation snapshot preparation'
      using errcode='22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  for identity_value in
    select identity_row.identity_value
    from pg_catalog.unnest(array[
      p_request_id,p_grant_id,p_action_id,p_task_id,p_parameters_payload_id,
      p_source_id,p_source_claim_id
    ]::uuid[]) as identity_row(identity_value)
    order by identity_row.identity_value
  loop
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(
        identity_value::text,729105384609243177::bigint));
  end loop;

  select preparation.* into preparation_row
  from connected_app_private.action_preparations as preparation
  where preparation.request_id=p_request_id for update;
  if found then
    select snapshot.* into snapshot_row
    from connected_cancel_private.snapshot_reads as snapshot
    where snapshot.request_id=p_request_id for update;
    if not found or preparation_row.owner_id<>p_owner_id
       or preparation_row.session_binding_sha256<>p_session_binding_sha256
       or preparation_row.command_binding_sha256<>p_command_binding_sha256
       or preparation_row.grant_id<>p_grant_id
       or preparation_row.action_id<>p_action_id
       or preparation_row.task_id<>p_task_id
       or preparation_row.turn_id<>p_turn_id
       or preparation_row.connection_id<>p_connection_id
       or preparation_row.provider<>p_provider
       or preparation_row.resource<>'calendar'
       or preparation_row.action<>'calendar.get'
       or preparation_row.authorization_revision<>p_authorization_revision
       or preparation_row.authorization_snapshot_sha256<>
          p_authorization_snapshot_sha256
       or preparation_row.granted_actions_sha256<>p_granted_actions_sha256
       or preparation_row.granted_scopes_sha256<>p_granted_scopes_sha256
       or preparation_row.task_state_revision<>p_task_state_revision
       or preparation_row.payload_id<>p_parameters_payload_id
       or preparation_row.payload_reference_binding_sha256<>
          p_parameters_reference_binding_sha256
       or preparation_row.parameters_sha256<>p_parameters_sha256
       or preparation_row.resource_version_sha256<>
          p_resource_version_sha256
       or preparation_row.policy_version<>p_policy_version
       or preparation_row.mutates_external_state
       or preparation_row.status<>'ready'
       or preparation_row.approval_id is not null
       or preparation_row.requested_at<>p_requested_at
       or preparation_row.expires_at<>p_expires_at
       or snapshot_row.owner_id<>p_owner_id
       or snapshot_row.session_id<>p_session_id
       or snapshot_row.session_binding_sha256<>p_session_binding_sha256
       or snapshot_row.source_kind<>p_source_kind
       or snapshot_row.source_id<>p_source_id
       or snapshot_row.source_claim_id<>p_source_claim_id
       or snapshot_row.chat_id is distinct from p_chat_id
       or snapshot_row.message_id is distinct from p_message_id
       or snapshot_row.schedule_id is distinct from p_schedule_id
       or snapshot_row.occurrence_id is distinct from p_occurrence_id
       or snapshot_row.turn_id<>p_turn_id
       or snapshot_row.connection_id<>p_connection_id
       or snapshot_row.grant_id<>p_grant_id
       or snapshot_row.action_id<>p_action_id
       or snapshot_row.task_id<>p_task_id
       or snapshot_row.command_binding_sha256<>p_command_binding_sha256
       or snapshot_row.resource_version_sha256<>p_resource_version_sha256
       or snapshot_row.requested_at<>p_requested_at
       or snapshot_row.expires_at<>p_expires_at then
      raise exception 'cancellation snapshot preparation replay drifted'
        using errcode='55000';
    end if;
    return connected_app_private.action_preparation_view_v1(
      p_owner_id,p_request_id);
  end if;

  if exists(
       select 1 from connected_app_private.action_preparations as preparation
       where preparation.command_binding_sha256=p_command_binding_sha256
          or preparation.grant_id=p_grant_id
          or preparation.action_id=p_action_id
          or preparation.payload_id=p_parameters_payload_id)
     or exists(
       select 1 from connected_app_private.task_grants as grant_row
       where grant_row.grant_id=p_grant_id)
     or exists(
       select 1 from connected_app_private.action_ledger as ledger
       where ledger.action_id=p_action_id)
     or exists(
       select 1 from connected_cancel_private.snapshot_reads as snapshot
       where snapshot.action_id=p_action_id or snapshot.grant_id=p_grant_id) then
    raise exception 'cancellation snapshot identity belongs to a sibling'
      using errcode='55000';
  end if;

  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id=p_connection_id and connection.owner_id=p_owner_id
  for update;
  if not found or connection_row.authorization_state<>'active'
     or connection_row.provider<>p_provider
     or connection_row.resource<>'calendar'
     or connection_row.authorization_revision<>p_authorization_revision
     or connection_row.authorization_snapshot_sha256<>
        p_authorization_snapshot_sha256
     or connection_row.granted_actions_sha256<>p_granted_actions_sha256
     or connection_row.granted_scopes_sha256<>p_granted_scopes_sha256
     or not ('calendar.get'=any(connection_row.granted_actions))
     or not ('calendar.cancel'=any(connection_row.granted_actions))
     or connection_row.authorization_expires_at is null
     or connection_row.authorization_expires_at<=now_at
     or p_expires_at>connection_row.authorization_expires_at then
    raise exception 'cancellation snapshot connection authority changed'
      using errcode='55000';
  end if;

  insert into connected_app_private.task_grants(
    grant_id,owner_id,task_id,turn_id,connection_id,provider,resource,
    authorization_revision,authorization_snapshot_sha256,actions,
    actions_sha256,task_state_revision,expires_at
  ) values(
    p_grant_id,p_owner_id,p_task_id,p_turn_id,p_connection_id,p_provider,
    'calendar',p_authorization_revision,p_authorization_snapshot_sha256,
    array['calendar.get'],grant_actions_sha256,p_task_state_revision,p_expires_at);

  insert into connected_app_private.action_preparations(
    request_id,owner_id,session_binding_sha256,command_binding_sha256,
    grant_id,action_id,task_id,turn_id,connection_id,provider,resource,action,
    authorization_revision,authorization_snapshot_sha256,
    granted_actions_sha256,granted_scopes_sha256,grant_actions_sha256,
    task_state_revision,payload_id,payload_reference_binding_sha256,
    parameters_sha256,resource_version_sha256,policy_version,
    mutates_external_state,approval_class,status,approval_id,
    approval_binding_sha256,preview_payload_id,
    preview_reference_binding_sha256,preview_sha256,requested_at,expires_at
  ) values(
    p_request_id,p_owner_id,p_session_binding_sha256,p_command_binding_sha256,
    p_grant_id,p_action_id,p_task_id,p_turn_id,p_connection_id,p_provider,
    'calendar','calendar.get',p_authorization_revision,
    p_authorization_snapshot_sha256,p_granted_actions_sha256,
    p_granted_scopes_sha256,grant_actions_sha256,p_task_state_revision,
    p_parameters_payload_id,p_parameters_reference_binding_sha256,
    p_parameters_sha256,p_resource_version_sha256,p_policy_version,
    false,'none','ready',null,null,null,null,null,p_requested_at,p_expires_at);

  insert into connected_cancel_private.snapshot_reads(
    request_id,owner_id,session_id,session_binding_sha256,source_kind,
    source_id,source_claim_id,chat_id,message_id,schedule_id,occurrence_id,
    turn_id,connection_id,grant_id,action_id,task_id,command_binding_sha256,
    resource_version_sha256,status,requested_at,expires_at,updated_at
  ) values(
    p_request_id,p_owner_id,p_session_id,p_session_binding_sha256,
    p_source_kind,p_source_id,p_source_claim_id,p_chat_id,p_message_id,
    p_schedule_id,p_occurrence_id,p_turn_id,p_connection_id,p_grant_id,
    p_action_id,p_task_id,p_command_binding_sha256,
    p_resource_version_sha256,'prepared',p_requested_at,p_expires_at,now_at);

  return connected_app_private.action_preparation_view_v1(
    p_owner_id,p_request_id);
end;
$fn$;
comment on function connected_cancel_private.prepare_snapshot_v1(
  text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,
  uuid,uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,
  timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_CANCEL_SNAPSHOT_PREPARE_V1_CHILD_READ_ONLY';

create or replace function public.connected_app_prepare_cancel_snapshot_chat_v1(
  p_owner_id uuid,p_chat_id uuid,p_message_id uuid,p_turn_id uuid,
  p_claim_token uuid,p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text,p_parent_plan_payload_id uuid,
  p_request_id uuid,p_session_id uuid,p_session_binding_sha256 text,
  p_command_binding_sha256 text,p_grant_id uuid,p_action_id uuid,
  p_task_id uuid,p_connection_id uuid,p_provider text,p_resource text,
  p_action text,p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,p_task_state_revision bigint,
  p_parameters_payload_id uuid,p_parameters_reference_binding_sha256 text,
  p_parameters_sha256 text,p_resource_version_sha256 text,
  p_policy_version text,p_requested_at timestamptz,p_expires_at timestamptz
) returns jsonb
language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  session_row public.sessions%rowtype;
  job_row public.chat_jobs%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  operation_row connected_plan_private.operations%rowtype;
begin
  if p_owner_id is null or p_chat_id is null or p_message_id is null
     or p_turn_id is null or p_claim_token is null
     or p_parent_plan_payload_id is null
     or p_origin_session_binding_sha256!~'^[0-9a-f]{64}$'
     or p_request_binding_sha256!~'^[0-9a-f]{64}$'
     or p_session_id is null
     or p_session_binding_sha256<>p_origin_session_binding_sha256
     or p_resource<>'calendar' or p_action<>'calendar.get'
     or p_task_state_revision<>1 then
    raise exception 'invalid interactive cancellation snapshot binding'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select session.* into session_row from public.sessions as session
  where session.id=p_session_id and session.user_id=p_owner_id for share;
  if not found or session_row.revoked_at is not null
     or session_row.expires_at<=now_at then
    raise exception 'cancellation snapshot session changed' using errcode='55000';
  end if;
  select job.* into job_row from public.chat_jobs as job
  where job.user_id=p_owner_id and job.message_id=p_message_id for update;
  if not found or job_row.chat_id<>p_chat_id or job_row.status<>'processing'
     or job_row.claim_token is distinct from p_claim_token then
    raise exception 'cancellation snapshot chat claim changed' using errcode='55000';
  end if;
  select turn.* into turn_row from connected_chat_private.turns as turn
  where turn.turn_id=p_turn_id and turn.job_id=job_row.id for update;
  if not found or turn_row.owner_id<>p_owner_id or turn_row.chat_id<>p_chat_id
     or turn_row.message_id<>p_message_id
     or turn_row.origin_session_binding_sha256<>p_origin_session_binding_sha256
     or turn_row.request_binding_sha256<>p_request_binding_sha256
     or turn_row.stage not in ('planned','prepared','executing') then
    raise exception 'cancellation snapshot chat turn changed' using errcode='55000';
  end if;
  select operation.* into operation_row
  from connected_plan_private.operations as operation
  where operation.planning_id=turn_row.planning_id and operation.turn_id=p_turn_id
  for update;
  if not found or operation_row.state<>'settled'
     or operation_row.disposition<>'action'
     or operation_row.owner_id<>p_owner_id
     or operation_row.session_id<>p_session_id
     or operation_row.chat_id<>p_chat_id or operation_row.message_id<>p_message_id
     or operation_row.claim_token is distinct from p_claim_token
     or operation_row.origin_session_binding_sha256<>
        p_origin_session_binding_sha256
     or operation_row.request_binding_sha256<>p_request_binding_sha256
     or operation_row.connection_id is distinct from p_connection_id
     or operation_row.provider is distinct from p_provider
     or operation_row.resource is distinct from 'calendar'
     or operation_row.action is distinct from 'calendar.cancel'
     or operation_row.payload_id is distinct from p_parent_plan_payload_id
     or operation_row.payload_id is distinct from turn_row.plan_payload_id
     or operation_row.expires_at<=now_at or p_expires_at>operation_row.expires_at then
    raise exception 'cancellation snapshot settled plan changed' using errcode='55000';
  end if;
  return connected_cancel_private.prepare_snapshot_v1(
    'chat',p_parent_plan_payload_id,p_claim_token,p_chat_id,p_message_id,
    null,null,p_request_id,p_owner_id,p_session_id,p_session_binding_sha256,
    p_command_binding_sha256,p_grant_id,p_action_id,p_task_id,p_turn_id,
    p_connection_id,p_provider,p_resource,p_action,p_authorization_revision,
    p_authorization_snapshot_sha256,p_granted_actions_sha256,
    p_granted_scopes_sha256,p_task_state_revision,p_parameters_payload_id,
    p_parameters_reference_binding_sha256,p_parameters_sha256,
    p_resource_version_sha256,p_policy_version,p_requested_at,p_expires_at);
end;
$fn$;
comment on function public.connected_app_prepare_cancel_snapshot_chat_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text,text,uuid,uuid,uuid,
  uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,
  timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_CANCEL_SNAPSHOT_CHAT_V1_EXACT_PARENT_PLAN';

create or replace function public.connected_app_prepare_cancel_snapshot_schedule_v1(
  p_owner_id uuid,p_schedule_id uuid,p_claim_id uuid,p_occurrence_id uuid,
  p_turn_id uuid,p_request_id uuid,p_session_id uuid,
  p_session_binding_sha256 text,p_command_binding_sha256 text,
  p_grant_id uuid,p_action_id uuid,p_task_id uuid,p_connection_id uuid,
  p_provider text,p_resource text,p_action text,p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,p_task_state_revision bigint,
  p_parameters_payload_id uuid,p_parameters_reference_binding_sha256 text,
  p_parameters_sha256 text,p_resource_version_sha256 text,
  p_policy_version text,p_requested_at timestamptz,p_expires_at timestamptz
) returns jsonb
language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  schedule_row connected_app_private.schedules%rowtype;
  template_row connected_schedule_private.templates%rowtype;
  occurrence_row connected_schedule_private.occurrences%rowtype;
  parent_grant connected_app_private.task_grants%rowtype;
begin
  if p_owner_id is null or p_schedule_id is null or p_claim_id is null
     or p_occurrence_id is null or p_turn_id is null
     or p_session_id is null or p_resource<>'calendar'
     or p_action<>'calendar.get' then
    raise exception 'invalid scheduled cancellation snapshot binding'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  if exists(select 1 from public.sessions where id=p_session_id) then
    raise exception 'scheduled cancellation snapshot session is not synthetic'
      using errcode='55000';
  end if;
  select schedule.* into schedule_row
  from connected_app_private.schedules as schedule
  where schedule.schedule_id=p_schedule_id and schedule.owner_id=p_owner_id
  for update;
  if not found or schedule_row.status<>'active'
     or schedule_row.claim_id is distinct from p_claim_id
     or schedule_row.claim_expires_at is null
     or schedule_row.claim_expires_at<=now_at
     or schedule_row.connection_id<>p_connection_id
     or schedule_row.provider<>p_provider or schedule_row.resource<>'calendar'
     or schedule_row.action<>'calendar.cancel'
     or not schedule_row.requires_approval_every_run
     or schedule_row.task_state_revision<>p_task_state_revision
     or schedule_row.updated_at<>p_requested_at
     or p_expires_at>schedule_row.claim_expires_at then
    raise exception 'scheduled cancellation snapshot claim changed'
      using errcode='55000';
  end if;
  select template.* into template_row
  from connected_schedule_private.templates as template
  where template.template_id=schedule_row.action_template_ref for update;
  select occurrence.* into occurrence_row
  from connected_schedule_private.occurrences as occurrence
  where occurrence.occurrence_id=p_occurrence_id for update;
  select grant_row.* into parent_grant
  from connected_app_private.task_grants as grant_row
  where grant_row.grant_id=p_claim_id for update;
  if template_row.template_id is null or template_row.record_state<>'live'
     or template_row.owner_id<>p_owner_id
     or template_row.schedule_id<>p_schedule_id
     or template_row.turn_id<>p_turn_id
     or template_row.connection_id<>p_connection_id
     or template_row.task_id<>schedule_row.task_id
     or template_row.provider<>p_provider or template_row.resource<>'calendar'
     or template_row.action<>'calendar.cancel'
     or template_row.authorization_revision<>p_authorization_revision
     or template_row.authorization_snapshot_sha256<>
        p_authorization_snapshot_sha256
     or template_row.granted_actions_sha256<>p_granted_actions_sha256
     or template_row.granted_scopes_sha256<>p_granted_scopes_sha256
     or template_row.resource_version_sha256 is null
     or template_row.resource_version_sha256<>p_resource_version_sha256
     or occurrence_row.occurrence_id is null
     or occurrence_row.schedule_id<>p_schedule_id
     or occurrence_row.owner_id<>p_owner_id
     or occurrence_row.current_claim_id is distinct from p_claim_id
     or occurrence_row.turn_id<>p_turn_id
     or occurrence_row.connection_id<>p_connection_id
     or occurrence_row.provider<>p_provider or occurrence_row.resource<>'calendar'
     or occurrence_row.action<>'calendar.cancel'
     or occurrence_row.status<>'pending_approval'
     or occurrence_row.authorization_revision<>p_authorization_revision
     or occurrence_row.authorization_snapshot_sha256<>
        p_authorization_snapshot_sha256
     or occurrence_row.granted_scopes_sha256<>p_granted_scopes_sha256
     or occurrence_row.task_state_revision<>p_task_state_revision
     or occurrence_row.resource_version_sha256<>p_resource_version_sha256
     or parent_grant.grant_id is null or parent_grant.owner_id<>p_owner_id
     or parent_grant.task_id<>schedule_row.task_id
     or parent_grant.turn_id<>p_turn_id
     or parent_grant.connection_id<>p_connection_id
     or parent_grant.provider<>p_provider or parent_grant.resource<>'calendar'
     or not ('calendar.cancel'=any(parent_grant.actions))
     or parent_grant.authorization_revision<>p_authorization_revision
     or parent_grant.authorization_snapshot_sha256<>
        p_authorization_snapshot_sha256
     or parent_grant.task_state_revision<>p_task_state_revision
     or parent_grant.revoked_at is not null or parent_grant.expires_at<=now_at then
    raise exception 'scheduled cancellation occurrence authority changed'
      using errcode='55000';
  end if;
  return connected_cancel_private.prepare_snapshot_v1(
    'schedule',p_occurrence_id,p_claim_id,null,null,p_schedule_id,
    p_occurrence_id,p_request_id,p_owner_id,p_session_id,
    p_session_binding_sha256,p_command_binding_sha256,p_grant_id,p_action_id,
    p_task_id,p_turn_id,p_connection_id,p_provider,p_resource,p_action,
    p_authorization_revision,p_authorization_snapshot_sha256,
    p_granted_actions_sha256,p_granted_scopes_sha256,p_task_state_revision,
    p_parameters_payload_id,p_parameters_reference_binding_sha256,
    p_parameters_sha256,p_resource_version_sha256,p_policy_version,
    p_requested_at,p_expires_at);
end;
$fn$;
comment on function public.connected_app_prepare_cancel_snapshot_schedule_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,text,text,text,
  bigint,text,text,text,bigint,uuid,text,text,text,text,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_CANCEL_SNAPSHOT_SCHEDULE_V1_EXACT_OCCURRENCE';

create or replace function public.connected_app_begin_cancel_snapshot_chat_v1(
  p_owner_id uuid,p_session_id uuid,p_chat_id uuid,p_message_id uuid,
  p_turn_id uuid,p_claim_token uuid,p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text,p_parent_plan_payload_id uuid,
  p_request_id uuid,p_action_id uuid,p_command_binding_sha256 text
) returns jsonb
language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  snapshot_row connected_cancel_private.snapshot_reads%rowtype;
  session_row public.sessions%rowtype;
  job_row public.chat_jobs%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  operation_row connected_plan_private.operations%rowtype;
  preparation_row connected_app_private.action_preparations%rowtype;
  grant_row connected_app_private.task_grants%rowtype;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select snapshot.* into snapshot_row
  from connected_cancel_private.snapshot_reads as snapshot
  where snapshot.request_id=p_request_id and snapshot.owner_id=p_owner_id
  for update;
  select session.* into session_row from public.sessions as session
  where session.id=p_session_id and session.user_id=p_owner_id for share;
  select job.* into job_row from public.chat_jobs as job
  where job.user_id=p_owner_id and job.message_id=p_message_id for update;
  select turn.* into turn_row from connected_chat_private.turns as turn
  where turn.turn_id=p_turn_id and turn.job_id=job_row.id for update;
  select operation.* into operation_row
  from connected_plan_private.operations as operation
  where operation.planning_id=turn_row.planning_id and operation.turn_id=p_turn_id
  for update;
  select preparation.* into preparation_row
  from connected_app_private.action_preparations as preparation
  where preparation.request_id=p_request_id for update;
  select grant_value.* into grant_row
  from connected_app_private.task_grants as grant_value
  where grant_value.grant_id=snapshot_row.grant_id for update;
  if snapshot_row.request_id is null or snapshot_row.source_kind<>'chat'
     or snapshot_row.source_id<>p_parent_plan_payload_id
     or snapshot_row.source_claim_id<>p_claim_token
     or snapshot_row.session_id<>p_session_id
     or snapshot_row.session_binding_sha256<>p_origin_session_binding_sha256
     or snapshot_row.chat_id<>p_chat_id or snapshot_row.message_id<>p_message_id
     or snapshot_row.turn_id<>p_turn_id
     or snapshot_row.action_id<>p_action_id
     or snapshot_row.command_binding_sha256<>p_command_binding_sha256
     or snapshot_row.expires_at<=now_at
     or session_row.id is null or session_row.revoked_at is not null
     or session_row.expires_at<=now_at
     or job_row.id is null or job_row.chat_id<>p_chat_id
     or job_row.status<>'processing'
     or job_row.claim_token is distinct from p_claim_token
     or turn_row.turn_id is null or turn_row.owner_id<>p_owner_id
     or turn_row.origin_session_binding_sha256<>p_origin_session_binding_sha256
     or turn_row.request_binding_sha256<>p_request_binding_sha256
     or turn_row.stage not in ('planned','prepared','executing')
     or operation_row.planning_id is null or operation_row.state<>'settled'
     or operation_row.owner_id<>p_owner_id
     or operation_row.session_id<>p_session_id
     or operation_row.connection_id is distinct from snapshot_row.connection_id
     or operation_row.resource is distinct from 'calendar'
     or operation_row.action is distinct from 'calendar.cancel'
     or operation_row.payload_id is distinct from p_parent_plan_payload_id
     or preparation_row.action_id<>p_action_id
     or preparation_row.command_binding_sha256<>p_command_binding_sha256
     or preparation_row.action<>'calendar.get'
     or preparation_row.status<>'ready'
     or preparation_row.expires_at<=now_at
     or grant_row.grant_id is null or grant_row.revoked_at is not null
     or grant_row.expires_at<=now_at then
    raise exception 'interactive cancellation snapshot start authority changed'
      using errcode='55000';
  end if;
  if snapshot_row.status='prepared' then
    update connected_cancel_private.snapshot_reads as snapshot
    set status='started',started_at=now_at,updated_at=now_at
    where snapshot.request_id=p_request_id and snapshot.status='prepared';
    if not found then
      raise exception 'interactive cancellation snapshot start lost its fence'
        using errcode='55000';
    end if;
  elsif snapshot_row.status<>'started' then
    raise exception 'interactive cancellation snapshot start is invalid'
      using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'request_id',p_request_id,'action_id',p_action_id,
    'status','started','updated_at',now_at);
end;
$fn$;
comment on function public.connected_app_begin_cancel_snapshot_chat_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text
) is 'ASK_CRUMP_CONNECTED_CANCEL_SNAPSHOT_CHAT_BEGIN_V1_JUST_IN_TIME';

create or replace function public.connected_app_begin_cancel_snapshot_schedule_v1(
  p_owner_id uuid,p_schedule_id uuid,p_claim_id uuid,p_occurrence_id uuid,
  p_turn_id uuid,p_request_id uuid,p_action_id uuid,
  p_command_binding_sha256 text
) returns jsonb
language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  snapshot_row connected_cancel_private.snapshot_reads%rowtype;
  schedule_row connected_app_private.schedules%rowtype;
  occurrence_row connected_schedule_private.occurrences%rowtype;
  preparation_row connected_app_private.action_preparations%rowtype;
  grant_row connected_app_private.task_grants%rowtype;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select snapshot.* into snapshot_row
  from connected_cancel_private.snapshot_reads as snapshot
  where snapshot.request_id=p_request_id and snapshot.owner_id=p_owner_id
  for update;
  select schedule.* into schedule_row
  from connected_app_private.schedules as schedule
  where schedule.schedule_id=p_schedule_id and schedule.owner_id=p_owner_id
  for update;
  select occurrence.* into occurrence_row
  from connected_schedule_private.occurrences as occurrence
  where occurrence.occurrence_id=p_occurrence_id for update;
  select preparation.* into preparation_row
  from connected_app_private.action_preparations as preparation
  where preparation.request_id=p_request_id for update;
  select grant_value.* into grant_row
  from connected_app_private.task_grants as grant_value
  where grant_value.grant_id=snapshot_row.grant_id for update;
  if snapshot_row.request_id is null or snapshot_row.source_kind<>'schedule'
     or snapshot_row.source_id<>p_occurrence_id
     or snapshot_row.source_claim_id<>p_claim_id
     or snapshot_row.schedule_id<>p_schedule_id
     or snapshot_row.occurrence_id<>p_occurrence_id
     or snapshot_row.turn_id<>p_turn_id
     or snapshot_row.action_id<>p_action_id
     or snapshot_row.command_binding_sha256<>p_command_binding_sha256
     or snapshot_row.expires_at<=now_at
     or schedule_row.schedule_id is null or schedule_row.status<>'active'
     or schedule_row.claim_id is distinct from p_claim_id
     or schedule_row.claim_expires_at is null
     or schedule_row.claim_expires_at<=now_at
     or schedule_row.connection_id<>snapshot_row.connection_id
     or schedule_row.resource<>'calendar'
     or schedule_row.action<>'calendar.cancel'
     or not schedule_row.requires_approval_every_run
     or occurrence_row.occurrence_id is null
     or occurrence_row.current_claim_id is distinct from p_claim_id
     or occurrence_row.owner_id<>p_owner_id
     or occurrence_row.turn_id<>p_turn_id
     or occurrence_row.status<>'pending_approval'
     or preparation_row.action_id<>p_action_id
     or preparation_row.command_binding_sha256<>p_command_binding_sha256
     or preparation_row.action<>'calendar.get'
     or preparation_row.status<>'ready'
     or preparation_row.expires_at<=now_at
     or grant_row.grant_id is null or grant_row.revoked_at is not null
     or grant_row.expires_at<=now_at then
    raise exception 'scheduled cancellation snapshot start authority changed'
      using errcode='55000';
  end if;
  if snapshot_row.status='prepared' then
    update connected_cancel_private.snapshot_reads as snapshot
    set status='started',started_at=now_at,updated_at=now_at
    where snapshot.request_id=p_request_id and snapshot.status='prepared';
    if not found then
      raise exception 'scheduled cancellation snapshot start lost its fence'
        using errcode='55000';
    end if;
  elsif snapshot_row.status<>'started' then
    raise exception 'scheduled cancellation snapshot start is invalid'
      using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'request_id',p_request_id,'action_id',p_action_id,
    'status','started','updated_at',now_at);
end;
$fn$;
comment on function public.connected_app_begin_cancel_snapshot_schedule_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text
) is 'ASK_CRUMP_CONNECTED_CANCEL_SNAPSHOT_SCHEDULE_BEGIN_V1_JUST_IN_TIME';

alter table connected_cancel_private.snapshot_reads owner to postgres;
alter function connected_cancel_private.prepare_snapshot_v1(
  text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,
  uuid,uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,
  timestamptz,timestamptz
) owner to postgres;
alter function public.connected_app_prepare_cancel_snapshot_chat_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text,text,uuid,uuid,uuid,
  uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,
  timestamptz,timestamptz
) owner to postgres;
alter function public.connected_app_prepare_cancel_snapshot_schedule_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,text,text,text,
  bigint,text,text,text,bigint,uuid,text,text,text,text,timestamptz,timestamptz
) owner to postgres;
alter function public.connected_app_begin_cancel_snapshot_chat_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text
) owner to postgres;
alter function public.connected_app_begin_cancel_snapshot_schedule_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text
) owner to postgres;

revoke all on function connected_cancel_private.prepare_snapshot_v1(
  text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,
  uuid,uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,
  timestamptz,timestamptz
) from public,anon,authenticated,service_role;
revoke all on function public.connected_app_prepare_cancel_snapshot_chat_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text,text,uuid,uuid,uuid,
  uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,
  timestamptz,timestamptz
) from public,anon,authenticated;
revoke all on function public.connected_app_prepare_cancel_snapshot_schedule_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,text,text,text,
  bigint,text,text,text,bigint,uuid,text,text,text,text,timestamptz,timestamptz
) from public,anon,authenticated;
revoke all on function public.connected_app_begin_cancel_snapshot_chat_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text
) from public,anon,authenticated;
revoke all on function public.connected_app_begin_cancel_snapshot_schedule_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text
) from public,anon,authenticated;
grant execute on function public.connected_app_prepare_cancel_snapshot_chat_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text,text,uuid,uuid,uuid,
  uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,
  timestamptz,timestamptz
) to service_role;
grant execute on function public.connected_app_prepare_cancel_snapshot_schedule_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,text,text,text,
  bigint,text,text,text,bigint,uuid,text,text,text,text,timestamptz,timestamptz
) to service_role;
grant execute on function public.connected_app_begin_cancel_snapshot_chat_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text
) to service_role;
grant execute on function public.connected_app_begin_cancel_snapshot_schedule_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text
) to service_role;

create or replace function connected_cancel_private.cancel_snapshot_target_fingerprint_v1()
returns text language sql stable security definer set search_path='' as $fingerprint$
  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
  from (
    select pg_catalog.concat_ws('|','schema',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),
      coalesce(description.description,'')) as item
    from pg_catalog.pg_namespace as namespace_row
    left join pg_catalog.pg_description as description
      on description.objoid=namespace_row.oid and description.objsubid=0
    where namespace_row.nspname='connected_cancel_private'
    union all
    select pg_catalog.concat_ws('|','relation',class_row.relname,class_row.relkind,
      class_row.relrowsecurity,class_row.relforcerowsecurity,
      pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text,''),coalesce(description.description,''))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_description as description
      on description.objoid=class_row.oid and description.objsubid=0
    where namespace_row.nspname='connected_cancel_private'
      and class_row.relname='snapshot_reads'
    union all
    select pg_catalog.concat_ws('|','column',attribute.attnum,attribute.attname,
      pg_catalog.format_type(attribute.atttypid,attribute.atttypmod),
      attribute.attnotnull,coalesce(
        pg_catalog.pg_get_expr(default_value.adbin,default_value.adrelid),''),
      coalesce(pg_catalog.col_description(attribute.attrelid,attribute.attnum),''))
    from pg_catalog.pg_attribute as attribute
    left join pg_catalog.pg_attrdef as default_value
      on default_value.adrelid=attribute.attrelid
     and default_value.adnum=attribute.attnum
    where attribute.attrelid=
      pg_catalog.to_regclass('connected_cancel_private.snapshot_reads')
      and attribute.attnum>0 and not attribute.attisdropped
    union all
    select pg_catalog.concat_ws('|','constraint',constraint_row.conname,
      constraint_row.contype,pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid=
      pg_catalog.to_regclass('connected_cancel_private.snapshot_reads')
    union all
    select pg_catalog.concat_ws('|','index',index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid))
    from pg_catalog.pg_class as index_class
    join pg_catalog.pg_index as index_row
      on index_row.indexrelid=index_class.oid
    where index_row.indrelid=
      pg_catalog.to_regclass('connected_cancel_private.snapshot_reads')
    union all
    select pg_catalog.concat_ws('|','function',
      procedure.oid::pg_catalog.regprocedure::text,
      pg_catalog.pg_get_userbyid(procedure.proowner),procedure.prosecdef,
      procedure.provolatile,coalesce(procedure.proconfig::text,''),
      coalesce(procedure.proacl::text,''),coalesce(description.description,''),
      pg_catalog.md5(pg_catalog.pg_get_functiondef(procedure.oid)))
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=procedure.pronamespace
    left join pg_catalog.pg_description as description
      on description.objoid=procedure.oid and description.objsubid=0
    where (namespace_row.nspname,procedure.proname) in (
      ('connected_cancel_private','prepare_snapshot_v1'),
      ('public','connected_app_prepare_cancel_snapshot_chat_v1'),
      ('public','connected_app_prepare_cancel_snapshot_schedule_v1'),
      ('public','connected_app_begin_cancel_snapshot_chat_v1'),
      ('public','connected_app_begin_cancel_snapshot_schedule_v1'))
    union all
    select pg_catalog.concat_ws('|','trigger',trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid=
      pg_catalog.to_regclass('connected_cancel_private.snapshot_reads')
      and not trigger_row.tgisinternal
    union all
    select pg_catalog.concat_ws('|','rule',rule_row.rulename,
      pg_catalog.pg_get_ruledef(rule_row.oid,true))
    from pg_catalog.pg_rewrite as rule_row
    where rule_row.ev_class=
      pg_catalog.to_regclass('connected_cancel_private.snapshot_reads')
      and rule_row.rulename<>'_RETURN'
    union all
    select pg_catalog.concat_ws('|','publication',publication_row.pubname,
      publication_row.puballtables,coalesce(namespace_row.nspname,''),
      coalesce(class_row.relname,''))
    from pg_catalog.pg_publication as publication_row
    left join pg_catalog.pg_publication_rel as publication_rel
      on publication_rel.prpubid=publication_row.oid
    left join pg_catalog.pg_class as class_row
      on class_row.oid=publication_rel.prrelid
    left join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where publication_row.puballtables
       or namespace_row.nspname='connected_cancel_private'
  ) as manifest(item)
$fingerprint$;
comment on function connected_cancel_private.cancel_snapshot_target_fingerprint_v1()
  is 'ASK_CRUMP_CONNECTED_CANCEL_SNAPSHOT_TARGET_FINGERPRINT_V1';
alter function connected_cancel_private.cancel_snapshot_target_fingerprint_v1()
  owner to postgres;
revoke all on function connected_cancel_private.cancel_snapshot_target_fingerprint_v1()
  from public,anon,authenticated,service_role;

do $postflight$
declare
  target_fingerprint text;
  function_name text;
begin
  select connected_cancel_private.cancel_snapshot_target_fingerprint_v1()
    into target_fingerprint;
  if target_fingerprint<>'755dbb418bb4cef4d102f1587ee1c99a' then
    raise exception 'connected cancellation snapshot postflight drifted: %',
      target_fingerprint using errcode='55000';
  end if;
  foreach function_name in array array[
    'public.connected_app_prepare_cancel_snapshot_chat_v1(uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone)',
    'public.connected_app_prepare_cancel_snapshot_schedule_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone)',
    'public.connected_app_begin_cancel_snapshot_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text)',
    'public.connected_app_begin_cancel_snapshot_schedule_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text)'
  ] loop
    if pg_catalog.has_function_privilege('public',function_name,'execute')
       or pg_catalog.has_function_privilege('anon',function_name,'execute')
       or pg_catalog.has_function_privilege('authenticated',function_name,'execute')
       or not pg_catalog.has_function_privilege('service_role',function_name,'execute') then
      raise exception 'connected cancellation snapshot function ACL drifted: %',
        function_name using errcode='55000';
    end if;
  end loop;
  if pg_catalog.has_schema_privilege(
       'service_role','connected_cancel_private','usage')
     or pg_catalog.has_table_privilege(
       'service_role','connected_cancel_private.snapshot_reads','select')
     or exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       where class_row.oid=
         pg_catalog.to_regclass('connected_cancel_private.snapshot_reads')) then
    raise exception 'connected cancellation snapshot private boundary drifted'
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
