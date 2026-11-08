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
       'connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()'
     ) is not null then
    select connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()
      into target_fingerprint;
    if target_fingerprint<>'74257db1f45f1f755d1ea5c1389599b7' then
      raise exception 'connected OAuth owner-binding target drifted: %',
        target_fingerprint using errcode='55000';
    end if;
    return;
  end if;
  if pg_catalog.to_regprocedure(
       'connected_retention_private.retention_target_fingerprint_v1()'
     ) is null then
    raise exception 'connected OAuth owner-binding predecessor is absent'
      using errcode='55000';
  end if;
  select connected_retention_private.retention_target_fingerprint_v1()
    into predecessor_fingerprint;
  if predecessor_fingerprint<>'1578bda68f666f33ded70a8907274663' then
    raise exception 'connected OAuth owner-binding predecessor drifted: %',
      predecessor_fingerprint using errcode='55000';
  end if;
  if pg_catalog.to_regclass('connected_app_private.connections') is null
     or pg_catalog.to_regclass('connected_app_private.oauth_flows') is null
     or pg_catalog.to_regclass(
       'connected_app_private.oauth_callback_requests'
     ) is null
     or pg_catalog.to_regclass(
       'connected_app_private.oauth_operator_starts'
     ) is null
     or pg_catalog.to_regclass(
       'connected_app_private.oauth_exchange_permits'
     ) is null
     or pg_catalog.to_regclass(
       'connected_app_private.credential_cleanup_outbox'
     ) is null
     or pg_catalog.to_regclass(
       'connected_app_private.credential_ref_tombstones'
     ) is null
     or pg_catalog.to_regclass(
       'connected_app_private.oauth_provisional_credentials'
     ) is null
     or pg_catalog.to_regclass(
       'connected_app_private.provider_grant_cleanup_jobs'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_prepare_oauth_callback_v1(text,text,text,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_prepare_oauth_start_v1(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_oauth_read_completion_v2(uuid,text,uuid,uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_record_credential_cleanup_v1(uuid,uuid,text,text,text,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_provider_cleanup_begin_v1(uuid,uuid,uuid,uuid,text,text,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_provider_cleanup_attach_v1(uuid,text,text,text,jsonb)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_oauth_secret_ambiguous_v1(uuid,uuid,text,uuid,timestamp with time zone,boolean,uuid,text,text,text,text[],text,timestamp with time zone,timestamp with time zone,text,text,text,text,text,text,text)'
     ) is null then
    raise exception 'connected OAuth owner-binding predecessor is incomplete'
      using errcode='55000';
  end if;
  if exists(
       select 1
       from connected_app_private.connections as connection
       where connection.authorization_state='active'
       group by connection.owner_id,connection.provider,connection.resource
       having pg_catalog.count(*)>1
     ) then
    raise exception 'duplicate active connected account requires operator resolution'
      using errcode='55000';
  end if;
  if pg_catalog.to_regnamespace('connected_oauth_binding_private') is not null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_prepare_oauth_callback_v2(uuid,text,text,text,text,timestamp with time zone)'
     ) is not null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_prepare_oauth_start_v2(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)'
     ) is not null
     or pg_catalog.to_regclass(
       'connected_app_private.connected_app_connections_one_active_resource_idx'
     ) is not null then
    raise exception 'connected OAuth owner-binding target is partial'
      using errcode='55000';
  end if;
  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_app_private'),
         pg_catalog.to_regnamespace('connected_oauth_binding_private')
       )
     )
     or exists(
       select 1
       from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname in (
         'connected_app_private','connected_oauth_binding_private'
       )
     ) then
    raise exception 'connected OAuth owner-binding publication exposure refused'
      using errcode='55000';
  end if;
end;
$preflight$;

create schema if not exists connected_oauth_binding_private authorization postgres;
comment on schema connected_oauth_binding_private is
  'ASK_CRUMP_CONNECTED_OAUTH_CALLBACK_OWNER_SESSION_BINDING_V2_PRIVATE';
revoke all on schema connected_oauth_binding_private
  from public,anon,authenticated,service_role;

create table if not exists connected_oauth_binding_private.inactive_completions(
  completion_id uuid primary key,
  completion_binding_sha256 text not null
    check (completion_binding_sha256 ~ '^[0-9a-f]{64}$'),
  owner_id uuid not null references public.users(id) on delete cascade,
  connection_id uuid not null
    references connected_app_private.connections(id) on delete cascade,
  flow_id uuid not null unique
    references connected_app_private.oauth_flows(flow_id) on delete cascade,
  reason text not null check (reason in (
    'revoked','replaced','revision_changed','incarnation_changed',
    'newer_flow','account_changed'
  )),
  cleanup_id uuid,
  cleanup_binding_sha256 text,
  observed_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint inactive_completion_cleanup_pair check (
    (cleanup_id is null and cleanup_binding_sha256 is null)
    or (cleanup_id is not null
        and cleanup_binding_sha256 ~ '^[0-9a-f]{64}$')
  ),
  constraint inactive_completion_flow_identity check (completion_id=flow_id)
);
alter table connected_oauth_binding_private.inactive_completions owner to postgres;
alter table connected_oauth_binding_private.inactive_completions
  enable row level security;
alter table connected_oauth_binding_private.inactive_completions
  force row level security;
revoke all on table connected_oauth_binding_private.inactive_completions
  from public,anon,authenticated,service_role;
comment on table connected_oauth_binding_private.inactive_completions is
  'ASK_CRUMP_CONTENT_FREE_REPLAYABLE_INACTIVE_OAUTH_COMPLETION_V1';

create table if not exists connected_oauth_binding_private.denial_receipts(
  denial_binding_sha256 text primary key
    check (denial_binding_sha256 ~ '^[0-9a-f]{64}$'),
  owner_id uuid not null references public.users(id) on delete cascade,
  session_binding_sha256 text not null
    check (session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google','microsoft')),
  state_sha256 text not null check (state_sha256 ~ '^[0-9a-f]{64}$'),
  connection_id uuid not null
    references connected_app_private.connections(id) on delete cascade,
  flow_id uuid not null unique
    references connected_app_private.oauth_flows(flow_id) on delete cascade,
  observed_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  unique(provider,state_sha256)
);
alter table connected_oauth_binding_private.denial_receipts owner to postgres;
alter table connected_oauth_binding_private.denial_receipts enable row level security;
alter table connected_oauth_binding_private.denial_receipts force row level security;
revoke all on table connected_oauth_binding_private.denial_receipts
  from public,anon,authenticated,service_role;
comment on table connected_oauth_binding_private.denial_receipts is
  'ASK_CRUMP_CONTENT_FREE_OWNER_SESSION_BOUND_OAUTH_DENIAL_RECEIPT_V1';

create unique index if not exists connected_app_connections_one_active_resource_idx
  on connected_app_private.connections(owner_id,provider,resource)
  where authorization_state='active';
comment on index connected_app_private.connected_app_connections_one_active_resource_idx
  is 'ASK_CRUMP_ONE_ACTIVE_CONNECTION_PER_OWNER_PROVIDER_RESOURCE_V1';

create or replace function public.connected_app_operator_prepare_oauth_start_v2(
  p_request_id uuid,
  p_owner_id uuid,
  p_session_binding_sha256 text,
  p_command_binding_sha256 text,
  p_requested_connection_id uuid,
  p_proposed_flow_id uuid,
  p_proposed_nonce_id uuid,
  p_proposed_connection_id uuid,
  p_proposed_connection_incarnation_id uuid,
  p_current_flow_nonce_sha256 text,
  p_provider text,
  p_resource text,
  p_account_kind text,
  p_actions text[],
  p_actions_sha256 text,
  p_redirect_uri_sha256 text,
  p_requested_at timestamptz,
  p_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  start_row connected_app_private.oauth_operator_starts%rowtype;
  candidate connected_app_private.connections%rowtype;
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_request_id is null or p_owner_id is null
     or p_proposed_flow_id is null or p_proposed_nonce_id is null
     or p_proposed_connection_id is null
     or p_proposed_connection_incarnation_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_command_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_current_flow_nonce_sha256 !~ '^[0-9a-f]{64}$'
     or p_actions_sha256 !~ '^[0-9a-f]{64}$'
     or p_redirect_uri_sha256 !~ '^[0-9a-f]{64}$'
     or p_provider not in ('google','microsoft')
     or p_resource not in ('mail','calendar')
     or p_account_kind not in ('personal','work_school')
     or pg_catalog.cardinality(p_actions) not between 1 and 16
     or p_actions is distinct from array(
       select requested.action_name
       from pg_catalog.unnest(p_actions) as requested(action_name)
       order by requested.action_name
     )
     or exists(
       select 1
       from pg_catalog.unnest(p_actions) as requested(action_name)
       left join connected_app_private.action_authority as authority
         on authority.action=requested.action_name
       where requested.action_name is null or authority.action is null
          or authority.resource<>p_resource
     )
     or p_requested_at is null
     or p_requested_at<now_at-interval '5 minutes'
     or p_requested_at>now_at+interval '1 minute'
     or p_expires_at<>p_requested_at+interval '10 minutes' then
    raise exception 'invalid connected OAuth start command' using errcode='22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select start_command.* into start_row
  from connected_app_private.oauth_operator_starts as start_command
  where start_command.request_id=p_request_id
  for update;
  if found then
    -- The predecessor owns the exact replay comparison.  No stale-row
    -- resolution occurs before that byte-for-byte command fence succeeds.
    return public.connected_app_operator_prepare_oauth_start_v1(
      p_request_id,p_owner_id,p_session_binding_sha256,p_command_binding_sha256,
      p_requested_connection_id,p_proposed_flow_id,p_proposed_nonce_id,
      p_proposed_connection_id,p_proposed_connection_incarnation_id,
      p_current_flow_nonce_sha256,p_provider,p_resource,p_account_kind,
      p_actions,p_actions_sha256,p_redirect_uri_sha256,p_requested_at,p_expires_at
    );
  end if;

  for candidate in
    select connection.*
    from connected_app_private.connections as connection
    where connection.owner_id=p_owner_id
      and connection.provider=p_provider
      and connection.resource=p_resource
      and connection.authorization_state<>'revoked'
    order by connection.id
    for update
  loop
    if p_requested_connection_id is not null
       and candidate.id=p_requested_connection_id then
      -- A requested connection is the sole permitted start authority.  It
      -- may be active (refresh) or pending, but never with another live flow.
      if exists(
        select 1 from connected_app_private.oauth_operator_starts as prior_start
        where prior_start.connection_id=candidate.id
          and prior_start.expires_at>now_at
      ) or exists(
        select 1 from connected_app_private.oauth_flows as prior_flow
        where prior_flow.connection_id=candidate.id
          and (
            prior_flow.status in ('consumed','exchanged')
            or (prior_flow.status='pending' and prior_flow.expires_at>now_at)
          )
      ) then
        raise exception 'connected OAuth start authority is already live'
          using errcode='55000';
      end if;
      update connected_app_private.oauth_flows as stale_flow
      set status='invalidated',updated_at=now_at
      where stale_flow.connection_id=candidate.id
        and stale_flow.status='pending' and stale_flow.expires_at<=now_at;
      continue;
    end if;

    if candidate.authorization_state='active'
       or exists(
         select 1 from connected_app_private.oauth_operator_starts as prior_start
         where prior_start.connection_id=candidate.id
           and prior_start.expires_at>now_at
       )
       or exists(
         select 1 from connected_app_private.oauth_flows as prior_flow
         where prior_flow.connection_id=candidate.id
           and (
             prior_flow.status in ('consumed','exchanged','completed')
             or (prior_flow.status='pending' and prior_flow.expires_at>now_at)
           )
       ) then
      raise exception 'connected OAuth start authority already exists'
        using errcode='55000';
    end if;

    -- Only an expired, never-consumed pending authority may be retired.  A
    -- consumed/exchanged/completed flow is never rewritten by start cleanup.
    update connected_app_private.oauth_flows as stale_flow
    set status='invalidated',updated_at=now_at
    where stale_flow.connection_id=candidate.id
      and stale_flow.status='pending' and stale_flow.expires_at<=now_at;
    update connected_app_private.connections as stale_connection
    set authorization_revision=stale_connection.authorization_revision+1,
        authorization_state='revoked',current_flow_nonce_sha256=null,
        revoked_at=now_at,updated_at=now_at
    where stale_connection.id=candidate.id
      and stale_connection.owner_id=p_owner_id
      and stale_connection.authorization_state='pending';
  end loop;

  return public.connected_app_operator_prepare_oauth_start_v1(
    p_request_id,p_owner_id,p_session_binding_sha256,p_command_binding_sha256,
    p_requested_connection_id,p_proposed_flow_id,p_proposed_nonce_id,
    p_proposed_connection_id,p_proposed_connection_incarnation_id,
    p_current_flow_nonce_sha256,p_provider,p_resource,p_account_kind,
    p_actions,p_actions_sha256,p_redirect_uri_sha256,p_requested_at,p_expires_at
  );
end;
$fn$;
comment on function public.connected_app_operator_prepare_oauth_start_v2(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_OAUTH_START_V2_ONE_NONREVOKED_RESOURCE_AUTHORITY';

create or replace function public.connected_app_oauth_finalize_v2(
  p_flow_id uuid,
  p_consumption_id uuid,
  p_exchange_id uuid,
  p_exchange_binding_sha256 text,
  p_dispatch_fence_id uuid,
  p_owner_id uuid,
  p_connection_id uuid,
  p_connection_incarnation_id uuid,
  p_expected_base_revision bigint,
  p_current_flow_nonce_sha256 text,
  p_provider text,
  p_resource text,
  p_account_kind text,
  p_external_account_id_sha256 text,
  p_granted_scopes_sha256 text,
  p_broker_credential_ref uuid,
  p_credential_ref_sha256 text,
  p_authorization_issued_at timestamptz,
  p_authorization_expires_at timestamptz,
  p_authorization_snapshot_sha256 text,
  p_completion_id uuid,
  p_completion_binding_sha256 text,
  p_cleanup_id uuid,
  p_cleanup_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  result_row jsonb;
  connection_row connected_app_private.connections%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  permit_row connected_app_private.oauth_exchange_permits%rowtype;
  inactive_row connected_oauth_binding_private.inactive_completions%rowtype;
  cleanup_result jsonb;
  duplicate_connection_id uuid;
  observed_owner_id uuid;
  now_at timestamptz := pg_catalog.clock_timestamp();
  inactive_reason text;
begin
  if p_flow_id is null or p_consumption_id is null or p_exchange_id is null
     or p_dispatch_fence_id is null or p_owner_id is null
     or p_connection_id is null or p_connection_incarnation_id is null
     or p_completion_id is null or p_cleanup_id is null
     or p_broker_credential_ref is null
     or p_expected_base_revision is null or p_expected_base_revision<0
     or p_exchange_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_current_flow_nonce_sha256 !~ '^[0-9a-f]{64}$'
     or p_external_account_id_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_scopes_sha256 !~ '^[0-9a-f]{64}$'
     or p_credential_ref_sha256 !~ '^[0-9a-f]{64}$'
     or p_authorization_snapshot_sha256 !~ '^[0-9a-f]{64}$'
     or p_completion_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_cleanup_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_authorization_issued_at is null
     or p_authorization_expires_at<=p_authorization_issued_at
     or p_authorization_issued_at>now_at+interval '1 minute'
     or p_provider not in ('google','microsoft')
     or p_resource not in ('mail','calendar')
     or p_account_kind not in ('personal','work_school') then
    raise exception 'OAuth authorization completion binding is invalid'
      using errcode='22023';
  end if;

  -- A caller cannot use another owner's immutable row IDs to make this
  -- function enqueue cleanup or otherwise mutate that owner's control plane.
  select connection.owner_id into observed_owner_id
  from connected_app_private.connections as connection
  where connection.id=p_connection_id;
  if found and observed_owner_id<>p_owner_id then
    return pg_catalog.jsonb_build_object(
      'completed',false,'active',false,
      'completion_id',p_completion_id,
      'completion_binding_sha256',p_completion_binding_sha256,
      'connection_id',p_connection_id,
      'observed_at',now_at,
      'reason','replaced'
    );
  end if;
  select flow.owner_id into observed_owner_id
  from connected_app_private.oauth_flows as flow
  where flow.flow_id=p_flow_id;
  if found and observed_owner_id<>p_owner_id then
    return pg_catalog.jsonb_build_object(
      'completed',false,'active',false,
      'completion_id',p_completion_id,
      'completion_binding_sha256',p_completion_binding_sha256,
      'connection_id',p_connection_id,
      'observed_at',now_at,
      'reason','replaced'
    );
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select inactive.* into inactive_row
  from connected_oauth_binding_private.inactive_completions as inactive
  where inactive.completion_id=p_completion_id
  for update;
  if found then
    if inactive_row.completion_binding_sha256<>p_completion_binding_sha256
       or inactive_row.owner_id<>p_owner_id
       or inactive_row.connection_id<>p_connection_id
       or inactive_row.flow_id<>p_flow_id then
      raise exception 'inactive OAuth completion replay drifted'
        using errcode='55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'completed',false,'active',false,
      'completion_id',inactive_row.completion_id,
      'completion_binding_sha256',inactive_row.completion_binding_sha256,
      'connection_id',inactive_row.connection_id,
      'observed_at',inactive_row.observed_at,
      'reason',inactive_row.reason
    );
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id=p_connection_id and connection.owner_id=p_owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id=p_flow_id and flow.owner_id=p_owner_id
  for update;
  select permit.* into permit_row
  from connected_app_private.oauth_exchange_permits as permit
  where permit.exchange_id=p_exchange_id
    and permit.exchange_binding_sha256=p_exchange_binding_sha256
  for update;

  -- Exact replay of an already-retired duplicate loser.  The cleanup row is
  -- the durable proof for the cleanup-required branch; an exact live broker
  -- reference is the proof for the branch where cleanup would be unsafe.
  if connection_row.id is not null and flow_row.flow_id is not null
     and permit_row.permit_id is not null
     and connection_row.authorization_state='revoked'
     and connection_row.connection_incarnation_id=p_connection_incarnation_id
     and connection_row.authorization_revision=p_expected_base_revision+1
     and connection_row.current_flow_nonce_sha256 is null
     and flow_row.connection_id=p_connection_id
     and flow_row.connection_incarnation_id=p_connection_incarnation_id
     and flow_row.expected_base_revision=p_expected_base_revision
     and flow_row.current_flow_nonce_sha256=p_current_flow_nonce_sha256
     and flow_row.consumption_id=p_consumption_id
     and flow_row.status='invalidated'
     and flow_row.provider=p_provider and flow_row.resource=p_resource
     and flow_row.account_kind=p_account_kind
     and permit_row.flow_id=p_flow_id
     and permit_row.connection_id=p_connection_id
     and permit_row.dispatch_fence_id=p_dispatch_fence_id
     and permit_row.status='attempt_fenced' then
    if exists(
      select 1 from connected_app_private.credential_cleanup_outbox as cleanup
      where cleanup.cleanup_id=p_cleanup_id
        and cleanup.cleanup_binding_sha256=p_cleanup_binding_sha256
        and cleanup.broker_credential_ref=p_broker_credential_ref
        and cleanup.credential_ref_sha256=p_credential_ref_sha256
        and cleanup.provider=p_provider and cleanup.reason='stale_connection'
    ) then
      insert into connected_oauth_binding_private.inactive_completions(
        completion_id,completion_binding_sha256,owner_id,connection_id,flow_id,
        reason,cleanup_id,cleanup_binding_sha256,observed_at
      ) values (
        p_completion_id,p_completion_binding_sha256,p_owner_id,p_connection_id,
        p_flow_id,'replaced',p_cleanup_id,p_cleanup_binding_sha256,now_at
      ) returning * into inactive_row;
      return pg_catalog.jsonb_build_object(
        'completed',false,'active',false,
        'completion_id',inactive_row.completion_id,
        'completion_binding_sha256',inactive_row.completion_binding_sha256,
        'connection_id',inactive_row.connection_id,
        'observed_at',inactive_row.observed_at,
        'reason',inactive_row.reason
      );
    end if;
    if exists(
      select 1 from connected_app_private.connections as live_credential
      where live_credential.authorization_state='active'
        and (
          live_credential.broker_credential_ref=p_broker_credential_ref
          or live_credential.credential_ref_sha256=p_credential_ref_sha256
        )
    ) then
      insert into connected_oauth_binding_private.inactive_completions(
        completion_id,completion_binding_sha256,owner_id,connection_id,flow_id,
        reason,observed_at
      ) values (
        p_completion_id,p_completion_binding_sha256,p_owner_id,p_connection_id,
        p_flow_id,'replaced',now_at
      ) returning * into inactive_row;
      return pg_catalog.jsonb_build_object(
        'completed',false,'active',false,
        'completion_id',inactive_row.completion_id,
        'completion_binding_sha256',inactive_row.completion_binding_sha256,
        'connection_id',inactive_row.connection_id,
        'observed_at',inactive_row.observed_at,
        'reason',inactive_row.reason
      );
    end if;
  end if;

  -- Before the predecessor can perform its unique-index update, refuse any
  -- fresh completion when another ACTIVE connection already owns this whole
  -- owner/provider/resource authority.  The owner lock serializes both
  -- callback/finalize winner orders and account deletion.
  if connection_row.id is not null and flow_row.flow_id is not null
     and permit_row.permit_id is not null
     and connection_row.authorization_state<>'revoked'
     and connection_row.connection_incarnation_id=p_connection_incarnation_id
     and connection_row.authorization_revision=p_expected_base_revision
     and connection_row.current_flow_nonce_sha256=p_current_flow_nonce_sha256
     and connection_row.provider=p_provider
     and connection_row.resource=p_resource
     and connection_row.account_kind=p_account_kind
     and flow_row.connection_id=p_connection_id
     and flow_row.connection_incarnation_id=p_connection_incarnation_id
     and flow_row.expected_base_revision=p_expected_base_revision
     and flow_row.current_flow_nonce_sha256=p_current_flow_nonce_sha256
     and flow_row.consumption_id=p_consumption_id
     and flow_row.status='exchanged'
     and flow_row.provider=p_provider
     and flow_row.resource=p_resource
     and flow_row.account_kind=p_account_kind
     and permit_row.flow_id=p_flow_id
     and permit_row.connection_id=p_connection_id
     and permit_row.dispatch_fence_id=p_dispatch_fence_id
     and permit_row.status='attempt_fenced'
     and (
       p_expected_base_revision=0
       or connection_row.external_account_id_sha256 is not distinct from
          p_external_account_id_sha256
     ) then
    select live_connection.id into duplicate_connection_id
    from connected_app_private.connections as live_connection
    where live_connection.owner_id=p_owner_id
      and live_connection.provider=p_provider
      and live_connection.resource=p_resource
      and live_connection.authorization_state='active'
      and live_connection.id<>p_connection_id
    order by live_connection.id
    limit 1
    for update;
    if duplicate_connection_id is not null then
      perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
          p_credential_ref_sha256,81424519024640287::bigint
        )
      );
      if exists(
        select 1
        from connected_app_private.connections as live_credential
        where live_credential.authorization_state='active'
          and (
            live_credential.broker_credential_ref=p_broker_credential_ref
            or live_credential.credential_ref_sha256=p_credential_ref_sha256
          )
      ) then
        update connected_app_private.connections as losing_connection
        set authorization_revision=losing_connection.authorization_revision+1,
            authorization_state='revoked',broker_credential_ref=null,
            credential_ref_sha256=null,current_flow_nonce_sha256=null,
            authorization_expires_at=null,revoked_at=now_at,updated_at=now_at
        where losing_connection.id=p_connection_id
          and losing_connection.owner_id=p_owner_id
          and losing_connection.authorization_state='pending'
          and losing_connection.authorization_revision=p_expected_base_revision;
        if not found then
          raise exception 'duplicate OAuth loser connection retirement drifted'
            using errcode='55000';
        end if;
        update connected_app_private.oauth_flows as losing_flow
        set status='invalidated',updated_at=now_at
        where losing_flow.flow_id=p_flow_id and losing_flow.status='exchanged';
        if not found then
          raise exception 'duplicate OAuth loser flow retirement drifted'
            using errcode='55000';
        end if;
        insert into connected_oauth_binding_private.inactive_completions(
          completion_id,completion_binding_sha256,owner_id,connection_id,flow_id,
          reason,observed_at
        ) values (
          p_completion_id,p_completion_binding_sha256,p_owner_id,p_connection_id,
          p_flow_id,'replaced',now_at
        ) returning * into inactive_row;
        return pg_catalog.jsonb_build_object(
          'completed',false,'active',false,
          'completion_id',inactive_row.completion_id,
          'completion_binding_sha256',inactive_row.completion_binding_sha256,
          'connection_id',inactive_row.connection_id,
          'observed_at',inactive_row.observed_at,
          'reason',inactive_row.reason
        );
      end if;
      cleanup_result:=public.connected_app_record_credential_cleanup_v1(
        p_cleanup_id,p_broker_credential_ref,p_credential_ref_sha256,
        p_provider,'stale_connection',p_cleanup_binding_sha256
      );
      update connected_app_private.connections as losing_connection
      set authorization_revision=losing_connection.authorization_revision+1,
          authorization_state='revoked',broker_credential_ref=null,
          credential_ref_sha256=null,current_flow_nonce_sha256=null,
          authorization_expires_at=null,revoked_at=now_at,updated_at=now_at
      where losing_connection.id=p_connection_id
        and losing_connection.owner_id=p_owner_id
        and losing_connection.authorization_state='pending'
        and losing_connection.authorization_revision=p_expected_base_revision;
      if not found then
        raise exception 'duplicate OAuth loser connection retirement drifted'
          using errcode='55000';
      end if;
      update connected_app_private.oauth_flows as losing_flow
      set status='invalidated',updated_at=now_at
      where losing_flow.flow_id=p_flow_id and losing_flow.status='exchanged';
      if not found then
        raise exception 'duplicate OAuth loser flow retirement drifted'
          using errcode='55000';
      end if;
      insert into connected_oauth_binding_private.inactive_completions(
        completion_id,completion_binding_sha256,owner_id,connection_id,flow_id,
        reason,cleanup_id,cleanup_binding_sha256,observed_at
      ) values (
        p_completion_id,p_completion_binding_sha256,p_owner_id,p_connection_id,
        p_flow_id,'replaced',p_cleanup_id,p_cleanup_binding_sha256,now_at
      ) returning * into inactive_row;
      return pg_catalog.jsonb_build_object(
        'completed',false,'active',false,
        'completion_id',inactive_row.completion_id,
        'completion_binding_sha256',inactive_row.completion_binding_sha256,
        'connection_id',inactive_row.connection_id,
        'observed_at',inactive_row.observed_at,
        'reason',inactive_row.reason
      );
    end if;
  end if;

  result_row:=public.connected_app_oauth_finalize_v1(
    p_flow_id,p_consumption_id,p_exchange_id,p_exchange_binding_sha256,
    p_dispatch_fence_id,p_owner_id,p_connection_id,
    p_connection_incarnation_id,p_expected_base_revision,
    p_current_flow_nonce_sha256,p_provider,p_resource,p_account_kind,
    p_external_account_id_sha256,p_granted_scopes_sha256,
    p_broker_credential_ref,p_credential_ref_sha256,
    p_authorization_expires_at,p_completion_id,
    p_completion_binding_sha256,p_cleanup_id,p_cleanup_binding_sha256
  );
  if coalesce((result_row->>'completed')::boolean,false)
     and coalesce((result_row->>'active')::boolean,false) then
    update connected_app_private.connections as connection
    set authorization_snapshot_sha256=p_authorization_snapshot_sha256,
        authorization_issued_at=p_authorization_issued_at,
        updated_at=now_at
    where connection.id=p_connection_id
      and connection.owner_id=p_owner_id
      and connection.authorization_revision=p_expected_base_revision+1
      and connection.broker_credential_ref=p_broker_credential_ref
      and connection.credential_ref_sha256=p_credential_ref_sha256
      and connection.authorization_expires_at=p_authorization_expires_at
      and connection.authorization_snapshot_sha256 in (
        p_completion_binding_sha256,p_authorization_snapshot_sha256
      )
    returning * into connection_row;
    if not found then
      raise exception 'OAuth authorization correction lost its connection fence'
        using errcode='55000';
    end if;
    update connected_app_private.oauth_flows as flow
    set completion_authorization_snapshot_sha256=p_authorization_snapshot_sha256,
        completion_authorization_issued_at=p_authorization_issued_at,
        updated_at=now_at
    where flow.flow_id=p_flow_id
      and flow.completion_id=p_completion_id
      and flow.completion_binding_sha256=p_completion_binding_sha256
      and flow.completion_authorization_revision=p_expected_base_revision+1
      and flow.completion_authorization_snapshot_sha256 in (
        p_completion_binding_sha256,p_authorization_snapshot_sha256
      )
    returning * into flow_row;
    if not found then
      raise exception 'OAuth authorization correction lost its flow fence'
        using errcode='55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'completed',true,'active',true,
      'owner_id',connection_row.owner_id,
      'connection_id',connection_row.id,
      'connection_incarnation_id',connection_row.connection_incarnation_id,
      'consumption_id',flow_row.consumption_id,
      'exchange_id',p_exchange_id,
      'completion_id',flow_row.completion_id,
      'completion_binding_sha256',flow_row.completion_binding_sha256,
      'authorization_revision',connection_row.authorization_revision,
      'authorization_snapshot_sha256',connection_row.authorization_snapshot_sha256,
      'authorization_issued_at',connection_row.authorization_issued_at,
      'granted_actions',connection_row.granted_actions,
      'granted_actions_sha256',connection_row.granted_actions_sha256,
      'granted_scopes_sha256',connection_row.granted_scopes_sha256,
      'external_account_id_sha256',connection_row.external_account_id_sha256,
      'broker_credential_ref',connection_row.broker_credential_ref,
      'credential_ref_sha256',connection_row.credential_ref_sha256,
      'authorization_expires_at',connection_row.authorization_expires_at
    );
  end if;

  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id=p_connection_id and connection.owner_id=p_owner_id;
  inactive_reason:=case
    when connection_row.id is null then 'replaced'
    when connection_row.authorization_state='revoked' then 'revoked'
    when connection_row.connection_incarnation_id<>p_connection_incarnation_id
      then 'incarnation_changed'
    when connection_row.authorization_revision<>p_expected_base_revision
      then 'revision_changed'
    when connection_row.current_flow_nonce_sha256<>p_current_flow_nonce_sha256
      then 'newer_flow'
    when connection_row.external_account_id_sha256 is distinct from
         p_external_account_id_sha256 then 'account_changed'
    else 'replaced'
  end;
  if connection_row.id is not null
     and flow_row.flow_id=p_flow_id
     and flow_row.owner_id=p_owner_id
     and flow_row.connection_id=p_connection_id then
    insert into connected_oauth_binding_private.inactive_completions(
      completion_id,completion_binding_sha256,owner_id,connection_id,flow_id,
      reason,observed_at
    ) values (
      p_completion_id,p_completion_binding_sha256,p_owner_id,p_connection_id,
      p_flow_id,inactive_reason,now_at
    ) on conflict (completion_id) do nothing;
  end if;
  return pg_catalog.jsonb_build_object(
    'completed',false,'active',false,
    'completion_id',p_completion_id,
    'completion_binding_sha256',p_completion_binding_sha256,
    'connection_id',p_connection_id,
    'observed_at',now_at,
    'reason',inactive_reason
  );
end;
$fn$;
comment on function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) is 'ASK_CRUMP_CONNECTED_OAUTH_FINALIZE_V2_OWNER_RESOURCE_UNIQUE_AND_CLEANUP_SAFE';

create or replace function public.connected_app_oauth_read_completion_v3(
  p_completion_id uuid,
  p_completion_binding_sha256 text,
  p_owner_id uuid,
  p_connection_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  inactive_row connected_oauth_binding_private.inactive_completions%rowtype;
begin
  if p_completion_id is null or p_owner_id is null or p_connection_id is null
     or p_completion_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid OAuth completion read binding' using errcode='22023';
  end if;
  select inactive.* into inactive_row
  from connected_oauth_binding_private.inactive_completions as inactive
  where inactive.completion_id=p_completion_id
    and inactive.completion_binding_sha256=p_completion_binding_sha256
    and inactive.owner_id=p_owner_id
    and inactive.connection_id=p_connection_id;
  if found then
    perform connected_app_private.owner_lock_v1(p_owner_id);
    select inactive.* into inactive_row
    from connected_oauth_binding_private.inactive_completions as inactive
    where inactive.completion_id=p_completion_id
      and inactive.completion_binding_sha256=p_completion_binding_sha256
      and inactive.owner_id=p_owner_id
      and inactive.connection_id=p_connection_id
    for update;
    if not found then return null; end if;
    return pg_catalog.jsonb_build_object(
      'completed',false,'active',false,
      'completion_id',inactive_row.completion_id,
      'completion_binding_sha256',inactive_row.completion_binding_sha256,
      'connection_id',inactive_row.connection_id,
      'observed_at',inactive_row.observed_at,
      'reason',inactive_row.reason
    );
  end if;
  return public.connected_app_oauth_read_completion_v2(
    p_completion_id,p_completion_binding_sha256,p_owner_id,p_connection_id
  );
end;
$fn$;
comment on function public.connected_app_oauth_read_completion_v3(uuid,text,uuid,uuid)
  is 'ASK_CRUMP_CONNECTED_OAUTH_READ_COMPLETION_V3_REPLAYABLE_INACTIVE_RECEIPT';

create or replace function public.connected_app_operator_prepare_oauth_callback_v2(
  p_owner_id uuid,
  p_session_binding_sha256 text,
  p_provider text,
  p_state_sha256 text,
  p_callback_binding_sha256 text,
  p_received_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  callback_row connected_app_private.oauth_callback_requests%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
  effective_received_at timestamptz;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_owner_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_provider not in ('google', 'microsoft')
     or p_state_sha256 !~ '^[0-9a-f]{64}$'
     or p_callback_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_received_at is null
     or p_received_at > now_at + interval '1 minute' then
    raise exception 'invalid connected OAuth callback binding' using errcode='22023';
  end if;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.provider=p_provider and flow.state_sha256=p_state_sha256;
  if not found or flow_row.owner_id<>p_owner_id
     or flow_row.session_binding_sha256<>p_session_binding_sha256 then
    raise exception 'OAuth callback flow is unavailable' using errcode='55000';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id=flow_row.connection_id
    and connection.owner_id=p_owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id=flow_row.flow_id
  for update;
  if not found or flow_row.owner_id<>p_owner_id
     or flow_row.session_binding_sha256<>p_session_binding_sha256 then
    raise exception 'OAuth callback owner or session changed' using errcode='55000';
  end if;
  select callback.* into callback_row
  from connected_app_private.oauth_callback_requests as callback
  where callback.provider=p_provider and callback.state_sha256=p_state_sha256
  for update;
  if found then
    if callback_row.callback_binding_sha256<>p_callback_binding_sha256
       or callback_row.flow_id<>flow_row.flow_id then
      raise exception 'OAuth callback replay drifted' using errcode='55000';
    end if;
    effective_received_at:=callback_row.received_at;
  else
    effective_received_at:=p_received_at;
  end if;
  if connection_row.id is null
     or connection_row.authorization_state='revoked'
     or connection_row.connection_incarnation_id<>flow_row.connection_incarnation_id
     or connection_row.authorization_revision<>flow_row.expected_base_revision
     or connection_row.current_flow_nonce_sha256<>flow_row.current_flow_nonce_sha256
     or flow_row.provider<>p_provider
     or flow_row.state_sha256<>p_state_sha256
     or flow_row.status not in ('pending','consumed','exchanged','completed')
     or effective_received_at<flow_row.created_at
     or effective_received_at>=flow_row.expires_at then
    raise exception 'OAuth callback live authority changed' using errcode='55000';
  end if;
  if callback_row.callback_binding_sha256 is null
     and (flow_row.status<>'pending' or now_at>=flow_row.expires_at) then
    raise exception 'OAuth callback was not durably accepted in time'
      using errcode='55000';
  end if;
  if callback_row.callback_binding_sha256 is not null
     and flow_row.status='pending' then
    raise exception 'OAuth callback receipt exists without atomic consumption'
      using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'flow',pg_catalog.jsonb_build_object(
      'flow_id',flow_row.flow_id,
      'nonce_id',flow_row.nonce_id,
      'owner_id',flow_row.owner_id,
      'connection_id',flow_row.connection_id,
      'connection_incarnation_id',flow_row.connection_incarnation_id,
      'expected_base_revision',flow_row.expected_base_revision,
      'current_flow_nonce_sha256',flow_row.current_flow_nonce_sha256,
      'session_binding_sha256',flow_row.session_binding_sha256,
      'provider',flow_row.provider,
      'resource',flow_row.resource,
      'account_kind',flow_row.account_kind,
      'actions',flow_row.actions,
      'actions_sha256',flow_row.actions_sha256,
      'requested_scopes_sha256',flow_row.requested_scopes_sha256,
      'state_sha256',flow_row.state_sha256,
      'pkce_challenge',flow_row.pkce_challenge,
      'redirect_uri_sha256',flow_row.redirect_uri_sha256,
      'flow_binding_sha256',flow_row.flow_binding_sha256,
      'status',flow_row.status,
      'consumption_id',flow_row.consumption_id,
      'consume_binding_sha256',flow_row.consume_binding_sha256,
      'consumed_at',flow_row.consumed_at,
      'created_at',flow_row.created_at,
      'expires_at',flow_row.expires_at
    ),
    'callback_received_at',effective_received_at
  );
end;
$fn$;
comment on function public.connected_app_operator_prepare_oauth_callback_v2(
  uuid,text,text,text,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_OAUTH_CALLBACK_V2_CURRENT_OWNER_SESSION_BOUND';

create or replace function public.connected_app_operator_deny_oauth_callback_v1(
  p_owner_id uuid,
  p_session_binding_sha256 text,
  p_provider text,
  p_state_sha256 text,
  p_error text,
  p_denial_binding_sha256 text,
  p_received_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  receipt_row connected_oauth_binding_private.denial_receipts%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_owner_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_provider not in ('google','microsoft')
     or p_state_sha256 !~ '^[0-9a-f]{64}$'
     or p_error<>'access_denied'
     or p_denial_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_received_at is null
     or p_received_at>now_at+interval '1 minute' then
    raise exception 'invalid connected OAuth denial binding' using errcode='22023';
  end if;

  select receipt.* into receipt_row
  from connected_oauth_binding_private.denial_receipts as receipt
  where receipt.provider=p_provider and receipt.state_sha256=p_state_sha256;
  if found then
    if receipt_row.owner_id<>p_owner_id
       or receipt_row.session_binding_sha256<>p_session_binding_sha256
       or receipt_row.denial_binding_sha256<>p_denial_binding_sha256 then
      raise exception 'OAuth denial replay drifted' using errcode='55000';
    end if;
    perform connected_app_private.owner_lock_v1(p_owner_id);
    select receipt.* into receipt_row
    from connected_oauth_binding_private.denial_receipts as receipt
    where receipt.provider=p_provider and receipt.state_sha256=p_state_sha256
    for update;
    if not found
       or receipt_row.owner_id<>p_owner_id
       or receipt_row.session_binding_sha256<>p_session_binding_sha256
       or receipt_row.denial_binding_sha256<>p_denial_binding_sha256 then
      raise exception 'OAuth denial replay changed' using errcode='55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'denied',true,'flow_id',receipt_row.flow_id,
      'connection_id',receipt_row.connection_id,
      'observed_at',receipt_row.observed_at
    );
  end if;

  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.provider=p_provider and flow.state_sha256=p_state_sha256;
  if not found or flow_row.owner_id<>p_owner_id
     or flow_row.session_binding_sha256<>p_session_binding_sha256 then
    raise exception 'OAuth denial flow is unavailable' using errcode='55000';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id=flow_row.connection_id and connection.owner_id=p_owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id=flow_row.flow_id
  for update;
  select receipt.* into receipt_row
  from connected_oauth_binding_private.denial_receipts as receipt
  where receipt.provider=p_provider and receipt.state_sha256=p_state_sha256
  for update;
  if found then
    if receipt_row.owner_id<>p_owner_id
       or receipt_row.session_binding_sha256<>p_session_binding_sha256
       or receipt_row.denial_binding_sha256<>p_denial_binding_sha256 then
      raise exception 'OAuth denial winner drifted' using errcode='55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'denied',true,'flow_id',receipt_row.flow_id,
      'connection_id',receipt_row.connection_id,
      'observed_at',receipt_row.observed_at
    );
  end if;
  if connection_row.id is null
     or connection_row.authorization_state='revoked'
     or connection_row.connection_incarnation_id<>flow_row.connection_incarnation_id
     or connection_row.authorization_revision<>flow_row.expected_base_revision
     or connection_row.current_flow_nonce_sha256<>flow_row.current_flow_nonce_sha256
     or flow_row.owner_id<>p_owner_id
     or flow_row.session_binding_sha256<>p_session_binding_sha256
     or flow_row.provider<>p_provider or flow_row.state_sha256<>p_state_sha256
     or flow_row.status<>'pending'
     or p_received_at<flow_row.created_at or p_received_at>=flow_row.expires_at then
    raise exception 'OAuth denial live authority changed' using errcode='55000';
  end if;

  update connected_app_private.oauth_flows as denied_flow
  set status='invalidated',updated_at=now_at
  where denied_flow.flow_id=flow_row.flow_id and denied_flow.status='pending';
  if not found then
    raise exception 'OAuth denial flow retirement lost its fence'
      using errcode='55000';
  end if;
  delete from connected_app_private.oauth_operator_starts as start_command
  where start_command.flow_id=flow_row.flow_id
    and start_command.owner_id=p_owner_id
    and start_command.session_binding_sha256=p_session_binding_sha256;
  if connection_row.authorization_state='pending' then
    update connected_app_private.connections as denied_connection
    set authorization_revision=denied_connection.authorization_revision+1,
        authorization_state='revoked',current_flow_nonce_sha256=null,
        revoked_at=now_at,updated_at=now_at
    where denied_connection.id=connection_row.id
      and denied_connection.owner_id=p_owner_id
      and denied_connection.authorization_state='pending'
      and denied_connection.authorization_revision=flow_row.expected_base_revision
      and denied_connection.current_flow_nonce_sha256=flow_row.current_flow_nonce_sha256;
    if not found then
      raise exception 'OAuth denial connection retirement lost its fence'
        using errcode='55000';
    end if;
  end if;
  insert into connected_oauth_binding_private.denial_receipts(
    denial_binding_sha256,owner_id,session_binding_sha256,provider,state_sha256,
    connection_id,flow_id,observed_at
  ) values (
    p_denial_binding_sha256,p_owner_id,p_session_binding_sha256,p_provider,
    p_state_sha256,flow_row.connection_id,flow_row.flow_id,p_received_at
  ) returning * into receipt_row;
  return pg_catalog.jsonb_build_object(
    'denied',true,'flow_id',receipt_row.flow_id,
    'connection_id',receipt_row.connection_id,
    'observed_at',receipt_row.observed_at
  );
end;
$fn$;
comment on function public.connected_app_operator_deny_oauth_callback_v1(
  uuid,text,text,text,text,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_OAUTH_DENIAL_V1_EXACT_OWNER_SESSION_STATE_BOUND_RETRY_SAFE';

alter function public.connected_app_operator_prepare_oauth_start_v2(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) owner to postgres;
revoke all on function public.connected_app_operator_prepare_oauth_start_v1(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) from public,anon,authenticated,service_role;
revoke all on function public.connected_app_operator_prepare_oauth_start_v2(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) from public,anon,authenticated;
grant execute on function public.connected_app_operator_prepare_oauth_start_v2(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) to service_role;

alter function public.connected_app_operator_prepare_oauth_callback_v2(
  uuid,text,text,text,text,timestamptz
) owner to postgres;
revoke all on function public.connected_app_operator_prepare_oauth_callback_v1(
  text,text,text,timestamptz
) from public,anon,authenticated,service_role;
revoke all on function public.connected_app_operator_prepare_oauth_callback_v2(
  uuid,text,text,text,text,timestamptz
) from public,anon,authenticated;
grant execute on function public.connected_app_operator_prepare_oauth_callback_v2(
  uuid,text,text,text,text,timestamptz
) to service_role;

alter function public.connected_app_operator_deny_oauth_callback_v1(
  uuid,text,text,text,text,text,timestamptz
) owner to postgres;
revoke all on function public.connected_app_operator_deny_oauth_callback_v1(
  uuid,text,text,text,text,text,timestamptz
) from public,anon,authenticated;
grant execute on function public.connected_app_operator_deny_oauth_callback_v1(
  uuid,text,text,text,text,text,timestamptz
) to service_role;

alter function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) owner to postgres;
revoke all on function public.connected_app_oauth_finalize_v1(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,uuid,text,uuid,text
) from public,anon,authenticated,service_role;
revoke all on function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) from public,anon,authenticated;
grant execute on function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) to service_role;

alter function public.connected_app_oauth_read_completion_v3(uuid,text,uuid,uuid)
  owner to postgres;
revoke all on function public.connected_app_oauth_read_completion_v2(
  uuid,text,uuid,uuid
) from public,anon,authenticated,service_role;
revoke all on function public.connected_app_oauth_read_completion_v3(
  uuid,text,uuid,uuid
) from public,anon,authenticated;
grant execute on function public.connected_app_oauth_read_completion_v3(
  uuid,text,uuid,uuid
) to service_role;

create or replace function connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()
returns text language sql stable security definer set search_path='' as $fingerprint$
  select pg_catalog.md5(pg_catalog.string_agg(item,E'\n' order by item))
  from (
    select pg_catalog.concat_ws('|','schema',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),coalesce(description.description,''))
      as item
    from pg_catalog.pg_namespace as namespace_row
    left join pg_catalog.pg_description as description
      on description.objoid=namespace_row.oid and description.objsubid=0
    where namespace_row.nspname='connected_oauth_binding_private'
    union all
    select pg_catalog.concat_ws('|','relation',class_row.relname,
      class_row.relkind,class_row.relrowsecurity,class_row.relforcerowsecurity,
      pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text,''),coalesce(description.description,''))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_description as description
      on description.objoid=class_row.oid and description.objsubid=0
    where (namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'connections','oauth_flows','oauth_operator_starts',
        'oauth_callback_requests','oauth_exchange_permits',
        'credential_cleanup_outbox','credential_ref_tombstones',
        'oauth_provisional_credentials','provider_grant_cleanup_jobs'
      )) or (namespace_row.nspname='connected_oauth_binding_private'
        and class_row.relname in ('inactive_completions','denial_receipts'))
    union all
    select pg_catalog.concat_ws('|','column',class_row.relname,
      attribute_row.attnum,attribute_row.attname,
      pg_catalog.format_type(attribute_row.atttypid,attribute_row.atttypmod),
      attribute_row.attnotnull,coalesce(pg_catalog.pg_get_expr(
        default_row.adbin,default_row.adrelid),''))
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row
      on class_row.oid=attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_row
      on default_row.adrelid=attribute_row.attrelid
     and default_row.adnum=attribute_row.attnum
    where ((namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'connections','oauth_flows','oauth_operator_starts',
        'oauth_callback_requests','oauth_exchange_permits',
        'credential_cleanup_outbox','credential_ref_tombstones',
        'oauth_provisional_credentials','provider_grant_cleanup_jobs'
      )) or (namespace_row.nspname='connected_oauth_binding_private'
        and class_row.relname in ('inactive_completions','denial_receipts')))
      and attribute_row.attnum>0 and not attribute_row.attisdropped
    union all
    select pg_catalog.concat_ws('|','constraint',class_row.relname,
      constraint_row.conname,constraint_row.contype,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_class as class_row
      on class_row.oid=constraint_row.conrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where (namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'connections','oauth_flows','oauth_operator_starts',
        'oauth_callback_requests','oauth_exchange_permits',
        'credential_cleanup_outbox','credential_ref_tombstones',
        'oauth_provisional_credentials','provider_grant_cleanup_jobs'
      )) or (namespace_row.nspname='connected_oauth_binding_private'
        and class_row.relname in ('inactive_completions','denial_receipts'))
    union all
    select pg_catalog.concat_ws('|','index',index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid),
      coalesce(pg_catalog.obj_description(index_class.oid,'pg_class'),''))
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as index_class
      on index_class.oid=index_row.indexrelid
    join pg_catalog.pg_class as indexed_class
      on indexed_class.oid=index_row.indrelid
    join pg_catalog.pg_namespace as indexed_namespace
      on indexed_namespace.oid=indexed_class.relnamespace
    where (indexed_namespace.nspname='connected_app_private'
      and indexed_class.relname in (
        'connections','oauth_flows','oauth_operator_starts',
        'oauth_callback_requests','oauth_exchange_permits',
        'credential_cleanup_outbox','credential_ref_tombstones',
        'oauth_provisional_credentials','provider_grant_cleanup_jobs'
      )) or (indexed_namespace.nspname='connected_oauth_binding_private'
        and indexed_class.relname in ('inactive_completions','denial_receipts'))
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
      ('connected_app_private','owner_lock_v1'),
      ('public','connected_app_operator_prepare_oauth_start_v1'),
      ('public','connected_app_operator_prepare_oauth_start_v2'),
      ('public','connected_app_operator_prepare_oauth_callback_v1'),
      ('public','connected_app_operator_prepare_oauth_callback_v2'),
      ('public','connected_app_operator_deny_oauth_callback_v1'),
      ('public','connected_app_operator_accept_oauth_callback_v1'),
      ('public','connected_app_operator_read_oauth_callback_v1'),
      ('public','connected_app_oauth_finalize_v1'),
      ('public','connected_app_oauth_finalize_v2'),
      ('public','connected_app_oauth_read_completion_v2'),
      ('public','connected_app_oauth_read_completion_v3'),
      ('public','connected_app_record_credential_cleanup_v1'),
      ('public','connected_app_provider_cleanup_begin_v1'),
      ('public','connected_app_provider_cleanup_attach_v1'),
      ('public','connected_app_oauth_secret_ambiguous_v1'),
      ('public','connected_app_oauth_provisional_read_v1'))
    union all
    select pg_catalog.concat_ws('|','trigger',class_row.relname,
      trigger_row.tgname,pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid=trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where not trigger_row.tgisinternal
      and ((namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'connections','oauth_flows','oauth_operator_starts',
        'oauth_callback_requests','oauth_exchange_permits',
        'credential_cleanup_outbox','credential_ref_tombstones',
        'oauth_provisional_credentials','provider_grant_cleanup_jobs'
      )) or (namespace_row.nspname='connected_oauth_binding_private'
        and class_row.relname in ('inactive_completions','denial_receipts')))
    union all
    select pg_catalog.concat_ws('|','rule',class_row.relname,
      rewrite_row.rulename,pg_catalog.pg_get_ruledef(rewrite_row.oid,true))
    from pg_catalog.pg_rewrite as rewrite_row
    join pg_catalog.pg_class as class_row on class_row.oid=rewrite_row.ev_class
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where rewrite_row.rulename<>'_RETURN'
      and ((namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'connections','oauth_flows','oauth_operator_starts',
        'oauth_callback_requests','oauth_exchange_permits',
        'credential_cleanup_outbox','credential_ref_tombstones',
        'oauth_provisional_credentials','provider_grant_cleanup_jobs'
      )) or (namespace_row.nspname='connected_oauth_binding_private'
        and class_row.relname in ('inactive_completions','denial_receipts')))
    union all
    select pg_catalog.concat_ws('|','publication',publication_row.pubname,
      publication_row.puballtables,coalesce(namespace_row.nspname,''),
      coalesce(class_row.relname,''))
    from pg_catalog.pg_publication as publication_row
    left join pg_catalog.pg_publication_rel as publication_relation
      on publication_relation.prpubid=publication_row.oid
    left join pg_catalog.pg_class as class_row
      on class_row.oid=publication_relation.prrelid
    left join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where publication_row.puballtables
       or namespace_row.nspname in (
         'connected_app_private','connected_oauth_binding_private'
       )
  ) as manifest(item)
$fingerprint$;
comment on function connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()
  is 'ASK_CRUMP_CONNECTED_OAUTH_OWNER_SESSION_BINDING_TARGET_FINGERPRINT_V1';
alter function connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()
  owner to postgres;
revoke all on function connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()
  from public,anon,authenticated,service_role;

do $postflight$
declare
  target_fingerprint text;
begin
  select connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()
    into target_fingerprint;
  if target_fingerprint<>'74257db1f45f1f755d1ea5c1389599b7' then
    raise exception 'connected OAuth owner-binding postflight drifted: %',
      target_fingerprint using errcode='55000';
  end if;
  if pg_catalog.has_function_privilege(
       'service_role','public.connected_app_operator_prepare_oauth_start_v1(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'service_role','public.connected_app_oauth_finalize_v1(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,uuid,text,uuid,text)','execute')
     or pg_catalog.has_function_privilege(
       'service_role','public.connected_app_operator_prepare_oauth_callback_v1(text,text,text,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'public','public.connected_app_operator_prepare_oauth_start_v2(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_operator_prepare_oauth_start_v2(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'public','public.connected_app_operator_prepare_oauth_callback_v2(uuid,text,text,text,text,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'anon','public.connected_app_operator_prepare_oauth_callback_v2(uuid,text,text,text,text,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'authenticated','public.connected_app_operator_prepare_oauth_callback_v2(uuid,text,text,text,text,timestamp with time zone)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_operator_prepare_oauth_callback_v2(uuid,text,text,text,text,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'public','public.connected_app_operator_deny_oauth_callback_v1(uuid,text,text,text,text,text,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'anon','public.connected_app_operator_deny_oauth_callback_v1(uuid,text,text,text,text,text,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'authenticated','public.connected_app_operator_deny_oauth_callback_v1(uuid,text,text,text,text,text,timestamp with time zone)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_operator_deny_oauth_callback_v1(uuid,text,text,text,text,text,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'public','public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)','execute')
     or pg_catalog.has_function_privilege(
       'service_role','public.connected_app_oauth_read_completion_v2(uuid,text,uuid,uuid)','execute')
     or pg_catalog.has_function_privilege(
       'public','public.connected_app_oauth_read_completion_v3(uuid,text,uuid,uuid)','execute')
     or pg_catalog.has_function_privilege(
       'anon','public.connected_app_oauth_read_completion_v3(uuid,text,uuid,uuid)','execute')
     or pg_catalog.has_function_privilege(
       'authenticated','public.connected_app_oauth_read_completion_v3(uuid,text,uuid,uuid)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_oauth_read_completion_v3(uuid,text,uuid,uuid)','execute')
     or pg_catalog.has_schema_privilege(
       'service_role','connected_oauth_binding_private','usage')
     or pg_catalog.has_table_privilege(
       'service_role','connected_oauth_binding_private.inactive_completions','select')
     or pg_catalog.has_table_privilege(
       'service_role','connected_oauth_binding_private.denial_receipts','select')
     or not exists(
       select 1 from pg_catalog.pg_index as index_row
       where index_row.indexrelid=pg_catalog.to_regclass(
         'connected_app_private.connected_app_connections_one_active_resource_idx'
       ) and index_row.indisunique and index_row.indisvalid
     )
     or exists(select 1 from pg_catalog.pg_publication where puballtables) then
    raise exception 'connected OAuth owner-binding authority drifted'
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
