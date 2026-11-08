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
       'connected_multi_account_private.multi_account_target_fingerprint_v1()'
     ) is not null then
    select connected_multi_account_private.multi_account_target_fingerprint_v1()
      into target_fingerprint;
    if target_fingerprint<>'4f6897dd07f0dca3fda59946c9f5c295' then
      raise exception 'connected multi-account target drifted: %',
        target_fingerprint using errcode='55000';
    end if;
    return;
  end if;

  if pg_catalog.to_regprocedure(
       'connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()'
     ) is null then
    raise exception 'connected multi-account predecessor is absent'
      using errcode='55000';
  end if;
  select connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()
    into predecessor_fingerprint;
  if predecessor_fingerprint<>'5e4480837c5ebb316da85be988a6561f' then
    raise exception 'connected multi-account predecessor drifted: %',
      predecessor_fingerprint using errcode='55000';
  end if;

  if pg_catalog.to_regclass('connected_app_private.connections') is null
     or pg_catalog.to_regclass(
       'connected_app_private.connected_app_connections_one_active_resource_idx'
     ) is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_prepare_oauth_start_v1(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_prepare_oauth_start_v2(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_oauth_finalize_v1(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,uuid,text,uuid,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)'
     ) is null then
    raise exception 'connected multi-account predecessor is incomplete'
      using errcode='55000';
  end if;

  if pg_catalog.to_regnamespace('connected_multi_account_private') is not null
     or pg_catalog.to_regclass(
       'connected_app_private.connected_app_connections_one_active_account_kind_resource_idx'
     ) is not null then
    raise exception 'connected multi-account target is partial'
      using errcode='55000';
  end if;

  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_app_private'),
          pg_catalog.to_regnamespace('connected_multi_account_private'),
          pg_catalog.to_regnamespace('connected_oauth_code_private')
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
          'connected_app_private','connected_multi_account_private',
          'connected_oauth_code_private'
       )
     ) then
    raise exception 'connected multi-account publication exposure refused'
      using errcode='55000';
  end if;
end;
$preflight$;

create schema if not exists connected_multi_account_private authorization postgres;
comment on schema connected_multi_account_private is
  'ASK_CRUMP_CONNECTED_MULTI_ACCOUNT_AUTHORITY_V1_PRIVATE';
revoke all on schema connected_multi_account_private
  from public,anon,authenticated,service_role;

lock table connected_app_private.connections in share row exclusive mode;

do $existing_data$
begin
  if exists(
       select 1
       from connected_app_private.connections as connection
       where connection.authorization_state='active'
       group by connection.owner_id,connection.provider,
         connection.account_kind,connection.resource
       having pg_catalog.count(*)>1
     ) then
    raise exception 'duplicate active connected account kind requires operator resolution'
      using errcode='55000';
  end if;
end;
$existing_data$;

drop index if exists
  connected_app_private.connected_app_connections_one_active_resource_idx;

create unique index if not exists
  connected_app_connections_one_active_account_kind_resource_idx
  on connected_app_private.connections(
    owner_id,provider,account_kind,resource
  ) where authorization_state='active';
comment on index
  connected_app_private.connected_app_connections_one_active_account_kind_resource_idx
  is 'ASK_CRUMP_ONE_ACTIVE_CONNECTION_PER_OWNER_PROVIDER_ACCOUNT_KIND_RESOURCE_V1';

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
      and connection.account_kind=p_account_kind
      and connection.resource=p_resource
      and connection.authorization_state<>'revoked'
    order by connection.id
    for update
  loop
    if p_requested_connection_id is not null
       and candidate.id=p_requested_connection_id then
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
) is 'ASK_CRUMP_CONNECTED_OAUTH_START_V2_ONE_NONREVOKED_ACCOUNT_KIND_RESOURCE_AUTHORITY';

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
      and live_connection.account_kind=p_account_kind
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
) is 'ASK_CRUMP_CONNECTED_OAUTH_FINALIZE_V2_OWNER_ACCOUNT_KIND_RESOURCE_UNIQUE_AND_CLEANUP_SAFE';

alter function public.connected_app_operator_prepare_oauth_start_v2(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) owner to postgres;
revoke all on function public.connected_app_operator_prepare_oauth_start_v2(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) from public,anon,authenticated;
grant execute on function public.connected_app_operator_prepare_oauth_start_v2(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) to service_role;

alter function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) owner to postgres;
revoke all on function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) from public,anon,authenticated;
grant execute on function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) to service_role;

create or replace function
  connected_multi_account_private.multi_account_target_fingerprint_v1()
returns text language sql stable security definer set search_path='' as $fingerprint$
  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
  from (
    select pg_catalog.concat_ws('|','schema',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),coalesce(description.description,''))
      as item
    from pg_catalog.pg_namespace as namespace_row
    left join pg_catalog.pg_description as description
      on description.objoid=namespace_row.oid and description.objsubid=0
    where namespace_row.nspname in (
      'connected_multi_account_private','connected_oauth_code_private'
    )
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
           and class_row.relname='connections')
       or (namespace_row.nspname='connected_oauth_code_private'
           and class_row.relname in (
             'authorization_code_custody',
             'release_bootstrap_dedicated_attestations'
           ))
    union all
    select pg_catalog.concat_ws('|','column',class_row.relname,
      attribute_row.attnum,attribute_row.attname,
      pg_catalog.format_type(attribute_row.atttypid,attribute_row.atttypmod),
      attribute_row.attnotnull,coalesce(attribute_row.attacl::text,''),
      coalesce(pg_catalog.pg_get_expr(
        default_row.adbin,default_row.adrelid),''),
      coalesce(description.description,''))
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row
      on class_row.oid=attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_row
      on default_row.adrelid=attribute_row.attrelid
     and default_row.adnum=attribute_row.attnum
    left join pg_catalog.pg_description as description
      on description.objoid=attribute_row.attrelid
     and description.objsubid=attribute_row.attnum
    where ((namespace_row.nspname='connected_app_private'
            and class_row.relname='connections')
       or (namespace_row.nspname='connected_oauth_code_private'
           and class_row.relname in (
             'authorization_code_custody',
             'release_bootstrap_dedicated_attestations'
           )))
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
           and class_row.relname='connections')
       or (namespace_row.nspname='connected_oauth_code_private'
           and class_row.relname in (
             'authorization_code_custody',
             'release_bootstrap_dedicated_attestations'
           ))
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
           and indexed_class.relname='connections')
       or (indexed_namespace.nspname='connected_oauth_code_private'
           and indexed_class.relname in (
             'authorization_code_custody',
             'release_bootstrap_dedicated_attestations'
           ))
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
      ('public','connected_app_oauth_finalize_v1'),
      ('public','connected_app_oauth_finalize_v2'),
      ('public','connected_app_operator_accept_oauth_callback_v2'),
      ('public','connected_app_oauth_code_read_v1'),
      ('public','connected_app_oauth_code_claim_v1'),
      ('public','connected_app_oauth_code_retire_v1'),
      ('public','connected_app_release_bootstrap_authenticate_v1'),
      ('connected_oauth_code_private','dedicated_attestation_sha256_v1'),
      ('public','connected_app_release_bootstrap_attest_dedicated_v1'),
      ('public','connected_app_release_bootstrap_read_dedicated_v1'),
      ('connected_oauth_code_private','oauth_code_custody_target_fingerprint_v1'))
    union all
    select pg_catalog.concat_ws('|','trigger',class_row.relname,
      trigger_row.tgname,pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid=trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where not trigger_row.tgisinternal
      and ((namespace_row.nspname='connected_app_private'
            and class_row.relname='connections')
       or (namespace_row.nspname='connected_oauth_code_private'
           and class_row.relname in (
             'authorization_code_custody',
             'release_bootstrap_dedicated_attestations'
           )))
    union all
    select pg_catalog.concat_ws('|','rule',class_row.relname,
      rewrite_row.rulename,pg_catalog.pg_get_ruledef(rewrite_row.oid,true))
    from pg_catalog.pg_rewrite as rewrite_row
    join pg_catalog.pg_class as class_row on class_row.oid=rewrite_row.ev_class
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where rewrite_row.rulename<>'_RETURN'
      and ((namespace_row.nspname='connected_app_private'
            and class_row.relname='connections')
       or (namespace_row.nspname='connected_oauth_code_private'
           and class_row.relname in (
             'authorization_code_custody',
             'release_bootstrap_dedicated_attestations'
           )))
    union all
    select pg_catalog.concat_ws('|','policy',class_row.relname,
      policy_row.polname,policy_row.polpermissive,policy_row.polcmd,
      coalesce((
        select pg_catalog.array_agg(
          case when policy_role.role_oid = 0 then 'public'::text
            else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end
          order by (case when policy_role.role_oid = 0 then 'public'::text
            else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end)
            collate pg_catalog."C"
        )::text
        from pg_catalog.unnest(policy_row.polroles)
          as policy_role(role_oid)
      ),''),
      coalesce(pg_catalog.pg_get_expr(
        policy_row.polqual,policy_row.polrelid,true),''),
      coalesce(pg_catalog.pg_get_expr(
        policy_row.polwithcheck,policy_row.polrelid,true),''))
    from pg_catalog.pg_policy as policy_row
    join pg_catalog.pg_class as class_row
      on class_row.oid=policy_row.polrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where (namespace_row.nspname='connected_app_private'
           and class_row.relname='connections')
       or (namespace_row.nspname='connected_oauth_code_private'
           and class_row.relname in (
             'authorization_code_custody',
             'release_bootstrap_dedicated_attestations'
           ))
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
         'connected_app_private','connected_multi_account_private',
         'connected_oauth_code_private'
       )
    union all
    select pg_catalog.concat_ws('|','publication_namespace',
      publication_row.pubname,namespace_row.nspname)
    from pg_catalog.pg_publication_namespace as publication_namespace
    join pg_catalog.pg_publication as publication_row
      on publication_row.oid=publication_namespace.pnpubid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=publication_namespace.pnnspid
    where namespace_row.nspname in (
      'connected_app_private','connected_multi_account_private',
      'connected_oauth_code_private'
    )
  ) as manifest(item)
$fingerprint$;
comment on function
  connected_multi_account_private.multi_account_target_fingerprint_v1() is
  'ASK_CRUMP_CONNECTED_MULTI_ACCOUNT_AUTHORITY_TARGET_FINGERPRINT_V1';
alter function connected_multi_account_private.multi_account_target_fingerprint_v1()
  owner to postgres;
revoke all on function
  connected_multi_account_private.multi_account_target_fingerprint_v1()
  from public,anon,authenticated,service_role;

do $postflight$
declare
  target_fingerprint text;
begin
  select connected_multi_account_private.multi_account_target_fingerprint_v1()
    into target_fingerprint;
  if target_fingerprint<>'4f6897dd07f0dca3fda59946c9f5c295' then
    raise exception 'connected multi-account postflight drifted: %',
      target_fingerprint using errcode='55000';
  end if;

  if pg_catalog.to_regclass(
       'connected_app_private.connected_app_connections_one_active_resource_idx'
     ) is not null
     or not exists(
       select 1 from pg_catalog.pg_index as index_row
       where index_row.indexrelid=pg_catalog.to_regclass(
         'connected_app_private.connected_app_connections_one_active_account_kind_resource_idx'
       ) and index_row.indisunique and index_row.indisvalid
     )
     or pg_catalog.has_function_privilege(
       'service_role','public.connected_app_operator_prepare_oauth_start_v1(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)','execute'
     )
     or pg_catalog.has_function_privilege(
       'service_role','public.connected_app_oauth_finalize_v1(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,uuid,text,uuid,text)','execute'
     )
     or pg_catalog.has_function_privilege(
       'public','public.connected_app_operator_prepare_oauth_start_v2(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)','execute'
     )
     or pg_catalog.has_function_privilege(
       'anon','public.connected_app_operator_prepare_oauth_start_v2(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)','execute'
     )
     or pg_catalog.has_function_privilege(
       'authenticated','public.connected_app_operator_prepare_oauth_start_v2(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)','execute'
     )
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_operator_prepare_oauth_start_v2(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)','execute'
     )
     or pg_catalog.has_function_privilege(
       'public','public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)','execute'
     )
     or pg_catalog.has_function_privilege(
       'anon','public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)','execute'
     )
     or pg_catalog.has_function_privilege(
       'authenticated','public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)','execute'
     )
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)','execute'
     )
     or pg_catalog.has_schema_privilege(
       'service_role','connected_multi_account_private','usage'
     )
     or exists(
       select 1
       from pg_catalog.pg_class as class_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname='connected_app_private'
         and class_row.relname='connections'
         and (not class_row.relrowsecurity or not class_row.relforcerowsecurity
              or pg_catalog.pg_get_userbyid(class_row.relowner)<>'postgres')
     )
     or exists(
       select 1
       from pg_catalog.pg_policy as policy_row
       join pg_catalog.pg_class as class_row
         on class_row.oid=policy_row.polrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where (namespace_row.nspname='connected_app_private'
              and class_row.relname='connections')
          or (namespace_row.nspname='connected_oauth_code_private'
              and class_row.relname in (
                'authorization_code_custody',
                'release_bootstrap_dedicated_attestations'
              ))
     )
     or exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_app_private'),
          pg_catalog.to_regnamespace('connected_multi_account_private'),
          pg_catalog.to_regnamespace('connected_oauth_code_private')
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
          'connected_app_private','connected_multi_account_private',
          'connected_oauth_code_private'
       )
     ) then
    raise exception 'connected multi-account authority drifted'
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
