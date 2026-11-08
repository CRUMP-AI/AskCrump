begin;

select pg_catalog.set_config('search_path', 'pg_catalog,public', true);
select pg_catalog.set_config('quote_all_identifiers', 'off', true);

-- This is a forward-only compatibility bridge for the unreleased connected
-- runtime.  Existing action rows cannot be assigned an invocation commitment
-- honestly, so the predecessor is accepted only while its ledger is empty.
do $preflight$
declare
  target_columns integer;
  target_functions integer;
  target_fingerprint text;
begin
  if pg_catalog.obj_description(
       pg_catalog.to_regclass('connected_app_private.action_ledger'), 'pg_class'
     ) is distinct from 'ASK_CRUMP_CONNECTED_APP_ACTION_LEDGER_V1_CONTENT_FREE'
     or pg_catalog.to_regprocedure(
       'public.connected_app_claim_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,bigint,uuid,uuid,integer,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_read_action_v1(uuid,uuid,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_settle_action_v1(uuid,uuid,uuid,uuid,uuid,boolean,text,text,text,text,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_get_binding_v2(uuid,uuid)'
     ) is null then
    raise exception 'connected runtime ledger predecessor is absent or drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.count(*) into target_columns
  from pg_catalog.pg_attribute as attribute_row
  where attribute_row.attrelid =
      pg_catalog.to_regclass('connected_app_private.action_ledger')
    and attribute_row.attname in (
      'invocation_binding_sha256', 'terminal_resource_version_sha256'
    )
    and attribute_row.attnum > 0 and not attribute_row.attisdropped;

  select pg_catalog.count(*) into target_functions
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname in (
      'connected_app_claim_action_v2',
      'connected_app_read_action_v2',
      'connected_app_recover_access_v2',
      'connected_app_settle_action_v2'
    );

  if target_columns = 0 and target_functions = 0 then
    if exists (select 1 from connected_app_private.action_ledger) then
      raise exception 'connected runtime ledger cannot backfill invocation binding'
        using errcode = '55000';
    end if;
  elsif target_columns = 2 and target_functions = 4 then
    select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
      (select pg_catalog.string_agg(
         attribute_row.attname || ':'
           || pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod)
           || ':' || attribute_row.attnotnull::text
           || ':' || coalesce(
                pg_catalog.col_description(
                  attribute_row.attrelid, attribute_row.attnum
                ), ''
              ),
         ',' order by attribute_row.attnum
       )
       from pg_catalog.pg_attribute as attribute_row
       where attribute_row.attrelid =
           pg_catalog.to_regclass('connected_app_private.action_ledger')
         and attribute_row.attname in (
           'invocation_binding_sha256', 'terminal_resource_version_sha256'
         )
         and attribute_row.attnum > 0 and not attribute_row.attisdropped),
      (select pg_catalog.string_agg(
         pg_catalog.pg_get_functiondef(proc_row.oid), E'\n'
         order by proc_row.proname collate pg_catalog."C",
                  pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
                    collate pg_catalog."C"
       )
       from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid = proc_row.pronamespace
       where namespace_row.nspname = 'public'
         and proc_row.proname in (
           'connected_app_claim_action_v2',
           'connected_app_read_action_v2',
           'connected_app_recover_access_v2',
           'connected_app_settle_action_v2'
         )),
      (select pg_catalog.string_agg(
         proc_row.proname || ':' || proc_row.proacl::text,
         ',' order by proc_row.proname collate pg_catalog."C"
       )
       from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid = proc_row.pronamespace
       where namespace_row.nspname = 'public'
         and proc_row.proname in (
           'connected_app_claim_action_v1',
           'connected_app_read_action_v1',
           'connected_app_recover_access_v1',
           'connected_app_settle_action_v1',
           'connected_app_claim_action_v2',
           'connected_app_read_action_v2',
           'connected_app_recover_access_v2',
           'connected_app_settle_action_v2'
         ))
    )) into target_fingerprint;
    if target_fingerprint <> '192b3c7abb884d47736df936c1820bc9' then
      raise exception 'connected runtime ledger exact target drifted'
        using errcode = '55000';
    end if;
  else
    raise exception 'connected runtime ledger state is partial or mixed'
      using errcode = '55000';
  end if;
end;
$preflight$;

alter table connected_app_private.action_ledger
  add column if not exists invocation_binding_sha256 text not null
    check (invocation_binding_sha256 ~ '^[0-9a-f]{64}$'),
  add column if not exists terminal_resource_version_sha256 text
    check (
      terminal_resource_version_sha256 is null
      or terminal_resource_version_sha256 ~ '^[0-9a-f]{64}$'
    );

comment on column connected_app_private.action_ledger.invocation_binding_sha256 is
  'ASK_CRUMP_CONNECTED_RUNTIME_INVOCATION_BINDING_V2_EXACT_RESTART_SAFE';
comment on column connected_app_private.action_ledger.terminal_resource_version_sha256 is
  'ASK_CRUMP_CONNECTED_RUNTIME_TERMINAL_RESOURCE_VERSION_V2_CONTENT_FREE';

create or replace function public.connected_app_claim_action_v2(
  p_operation_id uuid,
  p_action_id uuid,
  p_owner_id uuid,
  p_task_id uuid,
  p_turn_id uuid,
  p_connection_id uuid,
  p_grant_id uuid,
  p_provider text,
  p_resource text,
  p_action text,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,
  p_parameters_sha256 text,
  p_resource_version_sha256 text,
  p_authority_sha256 text,
  p_idempotency_key_sha256 text,
  p_invocation_binding_sha256 text,
  p_task_state_revision bigint,
  p_claim_request_id uuid,
  p_claim_id uuid,
  p_lease_seconds integer,
  p_execution_deadline timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  grant_row connected_app_private.task_grants%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  action_row connected_app_private.action_ledger%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_operation_id is null or p_action_id is null or p_owner_id is null
     or p_task_id is null or p_turn_id is null or p_connection_id is null
     or p_grant_id is null or p_claim_request_id is null or p_claim_id is null
     or p_operation_id <> p_action_id
     or p_lease_seconds not between 30 and 300
     or p_execution_deadline is null
     or p_execution_deadline <= now_at
     or p_execution_deadline > now_at + interval '1 hour'
     or p_authorization_revision is null or p_authorization_revision < 1
     or p_task_state_revision is null or p_task_state_revision < 1
     or p_authorization_snapshot_sha256 is null
     or p_authorization_snapshot_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_actions_sha256 is null
     or p_granted_actions_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_scopes_sha256 is null
     or p_granted_scopes_sha256 !~ '^[0-9a-f]{64}$'
     or p_parameters_sha256 is null
     or p_parameters_sha256 !~ '^[0-9a-f]{64}$'
     or (p_resource_version_sha256 is not null
         and p_resource_version_sha256 !~ '^[0-9a-f]{64}$')
     or p_authority_sha256 is null
     or p_authority_sha256 !~ '^[0-9a-f]{64}$'
     or p_idempotency_key_sha256 is null
     or p_idempotency_key_sha256 !~ '^[0-9a-f]{64}$'
     or p_invocation_binding_sha256 is null
     or p_invocation_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid action claim bounds' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action = p_action;
  if not found or authority_row.resource <> p_resource then
    raise exception 'action is not in the database allowlist'
      using errcode = '55000';
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id
  for update;
  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = p_grant_id
  for update;
  if connection_row.id is null or grant_row.grant_id is null
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or not (p_action = any(connection_row.granted_actions))
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at)
     or grant_row.owner_id <> p_owner_id
     or grant_row.task_id <> p_task_id
     or grant_row.turn_id <> p_turn_id
     or grant_row.connection_id <> p_connection_id
     or grant_row.provider <> p_provider
     or grant_row.resource <> p_resource
     or grant_row.authorization_revision <> p_authorization_revision
     or grant_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or grant_row.task_state_revision <> p_task_state_revision
     or grant_row.revoked_at is not null
     or grant_row.expires_at <= now_at
     or not (p_action = any(grant_row.actions)) then
    raise exception 'action grant authority changed' using errcode = '55000';
  end if;

  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.owner_id = p_owner_id
    and ledger.connection_id = p_connection_id
    and ledger.idempotency_key_sha256 = p_idempotency_key_sha256
  for update;
  if found then
    if action_row.operation_id <> p_operation_id
       or action_row.action_id <> p_action_id
       or action_row.task_id <> p_task_id
       or action_row.turn_id <> p_turn_id
       or action_row.grant_id <> p_grant_id
       or action_row.provider <> p_provider
       or action_row.resource <> p_resource
       or action_row.action <> p_action
       or action_row.authorization_revision <> p_authorization_revision
       or action_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
       or action_row.granted_actions_sha256 <> p_granted_actions_sha256
       or action_row.granted_scopes_sha256 <> p_granted_scopes_sha256
       or action_row.parameters_sha256 <> p_parameters_sha256
       or action_row.resource_version_sha256 is distinct from p_resource_version_sha256
       or action_row.authority_sha256 <> p_authority_sha256
       or action_row.idempotency_key_sha256 <> p_idempotency_key_sha256
       or action_row.invocation_binding_sha256 <> p_invocation_binding_sha256
       or action_row.task_state_revision <> p_task_state_revision
       or action_row.mutates_external_state <> authority_row.mutates_external_state
       or action_row.approval_class <> authority_row.approval_class
       or action_row.execution_deadline <> p_execution_deadline then
      raise exception 'action idempotency replay drifted' using errcode = '55000';
    end if;
    if action_row.status = 'claimed'
       and action_row.lease_expires_at <= now_at
       and action_row.execution_deadline > now_at then
      update connected_app_private.action_ledger as ledger
      set claim_request_id = p_claim_request_id,
          claim_id = p_claim_id,
          fencing_token = pg_catalog.nextval(
            'connected_app_private.action_fencing_token_seq'::regclass
          ),
          lease_expires_at = now_at + pg_catalog.make_interval(secs => p_lease_seconds),
          updated_at = now_at
      where ledger.operation_id = p_operation_id
      returning * into action_row;
    end if;
    return pg_catalog.to_jsonb(action_row);
  end if;

  insert into connected_app_private.action_ledger (
    operation_id, action_id, owner_id, task_id, turn_id, connection_id,
    grant_id, provider, resource, action, authorization_revision,
    authorization_snapshot_sha256, granted_actions_sha256,
    granted_scopes_sha256, parameters_sha256,
    resource_version_sha256, authority_sha256, idempotency_key_sha256,
    invocation_binding_sha256, task_state_revision,
    mutates_external_state, approval_class, claim_request_id, claim_id,
    lease_expires_at, execution_deadline
  ) values (
    p_operation_id, p_action_id, p_owner_id, p_task_id, p_turn_id,
    p_connection_id, p_grant_id, p_provider, p_resource, p_action,
    p_authorization_revision, p_authorization_snapshot_sha256,
    p_granted_actions_sha256, p_granted_scopes_sha256, p_parameters_sha256,
    p_resource_version_sha256, p_authority_sha256, p_idempotency_key_sha256,
    p_invocation_binding_sha256, p_task_state_revision,
    authority_row.mutates_external_state, authority_row.approval_class,
    p_claim_request_id, p_claim_id,
    now_at + pg_catalog.make_interval(secs => p_lease_seconds),
    p_execution_deadline
  ) returning * into action_row;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_claim_action_v2(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,
  text,text,text,text,text,bigint,uuid,uuid,integer,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_CLAIM_ACTION_V2_INVOCATION_BOUND_NO_LEGACY_FALLBACK';

create or replace function public.connected_app_read_action_v2(
  p_owner_id uuid,
  p_operation_id uuid,
  p_idempotency_key_sha256 text,
  p_invocation_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  action_row connected_app_private.action_ledger%rowtype;
begin
  if p_owner_id is null or p_operation_id is null
     or p_idempotency_key_sha256 is null
     or p_idempotency_key_sha256 !~ '^[0-9a-f]{64}$'
     or p_invocation_binding_sha256 is null
     or p_invocation_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid action readback binding' using errcode = '22023';
  end if;
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id and ledger.owner_id = p_owner_id;
  if not found then
    return null;
  end if;
  if action_row.idempotency_key_sha256 <> p_idempotency_key_sha256
     or action_row.invocation_binding_sha256 <> p_invocation_binding_sha256 then
    raise exception 'action readback binding drifted' using errcode = '55000';
  end if;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_read_action_v2(uuid,uuid,text,text) is
  'ASK_CRUMP_CONNECTED_APP_READ_ACTION_V2_EXACT_INVOCATION_BINDING';

create or replace function public.connected_app_recover_access_v2(
  p_operation_id uuid,
  p_owner_id uuid,
  p_expired_claim_id uuid,
  p_recovery_request_id uuid,
  p_claim_id uuid,
  p_lease_seconds integer,
  p_grant_id uuid,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,
  p_authority_sha256 text,
  p_task_state_revision bigint,
  p_invocation_binding_sha256 text,
  p_access_phase text,
  p_access_use_nonce uuid,
  p_credential_expires_at timestamptz,
  p_execution_deadline timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  action_row connected_app_private.action_ledger%rowtype;
  connection_row connected_app_private.connections%rowtype;
  grant_row connected_app_private.task_grants%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_operation_id is null or p_owner_id is null
     or p_expired_claim_id is null or p_recovery_request_id is null
     or p_claim_id is null or p_grant_id is null
     or p_expired_claim_id = p_claim_id
     or p_lease_seconds not between 30 and 300
     or p_authorization_revision is null or p_authorization_revision < 1
     or p_task_state_revision is null or p_task_state_revision < 1
     or p_authorization_snapshot_sha256 is null
     or p_authorization_snapshot_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_actions_sha256 is null
     or p_granted_actions_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_scopes_sha256 is null
     or p_granted_scopes_sha256 !~ '^[0-9a-f]{64}$'
     or p_authority_sha256 is null
     or p_authority_sha256 !~ '^[0-9a-f]{64}$'
     or p_invocation_binding_sha256 is null
     or p_invocation_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_access_phase not in ('read', 'preobserve')
     or p_access_use_nonce is null
     or p_credential_expires_at is null
     or p_credential_expires_at <= now_at
     or p_credential_expires_at >
        now_at + pg_catalog.make_interval(secs => p_lease_seconds)
     or p_execution_deadline is null or p_execution_deadline <= now_at
     or p_execution_deadline > now_at + interval '1 hour'
     or p_credential_expires_at > p_execution_deadline then
    raise exception 'invalid access recovery bounds' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id and ledger.owner_id = p_owner_id
  for update;
  if not found then
    raise exception 'action not found' using errcode = '55000';
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = action_row.connection_id
    and connection.owner_id = p_owner_id
  for update;
  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = p_grant_id
  for update;
  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action = action_row.action;

  if action_row.status = 'access_granted'
     and action_row.claim_request_id = p_recovery_request_id
     and action_row.claim_id = p_claim_id then
    if action_row.grant_id = p_grant_id
       and action_row.authorization_revision = p_authorization_revision
       and action_row.authorization_snapshot_sha256 =
           p_authorization_snapshot_sha256
       and action_row.granted_actions_sha256 = p_granted_actions_sha256
       and action_row.granted_scopes_sha256 = p_granted_scopes_sha256
       and action_row.authority_sha256 = p_authority_sha256
       and action_row.task_state_revision = p_task_state_revision
       and action_row.invocation_binding_sha256 = p_invocation_binding_sha256
       and action_row.access_phase = p_access_phase
       and action_row.lease_expires_at = p_credential_expires_at
       and action_row.execution_deadline = p_execution_deadline
       and (
         (p_access_phase = 'read'
          and action_row.read_use_nonce = p_access_use_nonce
          and action_row.preobserve_use_nonce is null)
         or
         (p_access_phase = 'preobserve'
          and action_row.preobserve_use_nonce = p_access_use_nonce
          and action_row.read_use_nonce is null)
       ) then
      return pg_catalog.to_jsonb(action_row);
    end if;
    raise exception 'access recovery replay drifted' using errcode = '55000';
  end if;

  if action_row.status <> 'access_granted'
     or action_row.claim_id <> p_expired_claim_id
     or action_row.effect_use_nonce is not null
     or action_row.lease_expires_at > now_at
     or action_row.invocation_binding_sha256 <> p_invocation_binding_sha256
     or action_row.access_phase <> p_access_phase
     or authority_row.action is null
     or authority_row.resource <> action_row.resource
     or authority_row.mutates_external_state <> action_row.mutates_external_state
     or authority_row.approval_class <> action_row.approval_class
     or (action_row.mutates_external_state and p_access_phase <> 'preobserve')
     or (not action_row.mutates_external_state and p_access_phase <> 'read')
     or connection_row.id is null
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> action_row.provider
     or connection_row.resource <> action_row.resource
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256 <>
        p_authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or not (action_row.action = any(connection_row.granted_actions))
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at)
     or (connection_row.authorization_expires_at is not null
         and p_execution_deadline > connection_row.authorization_expires_at)
     or grant_row.grant_id is null
     or grant_row.owner_id <> p_owner_id
     or grant_row.task_id <> action_row.task_id
     or grant_row.turn_id <> action_row.turn_id
     or grant_row.connection_id <> action_row.connection_id
     or grant_row.provider <> action_row.provider
     or grant_row.resource <> action_row.resource
     or grant_row.authorization_revision <> p_authorization_revision
     or grant_row.authorization_snapshot_sha256 <>
        p_authorization_snapshot_sha256
     or grant_row.task_state_revision <> p_task_state_revision
     or grant_row.revoked_at is not null
     or grant_row.expires_at <= now_at
     or p_execution_deadline > grant_row.expires_at
     or not (action_row.action = any(grant_row.actions)) then
    raise exception 'action access is not recoverable under fresh authority'
      using errcode = '55000';
  end if;

  update connected_app_private.action_ledger as ledger
  set grant_id = p_grant_id,
      authorization_revision = p_authorization_revision,
      authorization_snapshot_sha256 = p_authorization_snapshot_sha256,
      granted_actions_sha256 = p_granted_actions_sha256,
      granted_scopes_sha256 = p_granted_scopes_sha256,
      authority_sha256 = p_authority_sha256,
      task_state_revision = p_task_state_revision,
      claim_request_id = p_recovery_request_id,
      claim_id = p_claim_id,
      fencing_token = pg_catalog.nextval(
        'connected_app_private.action_fencing_token_seq'::regclass
      ),
      lease_expires_at = p_credential_expires_at,
      execution_deadline = p_execution_deadline,
      read_use_nonce = case when p_access_phase = 'read'
        then p_access_use_nonce else null end,
      read_credential_expires_at = case when p_access_phase = 'read'
        then p_credential_expires_at else null end,
      read_consumed_at = null,
      preobserve_use_nonce = case when p_access_phase = 'preobserve'
        then p_access_use_nonce else null end,
      preobserve_credential_expires_at = case when p_access_phase = 'preobserve'
        then p_credential_expires_at else null end,
      preobserve_consumed_at = null,
      access_started_at = now_at,
      updated_at = now_at
  where ledger.operation_id = p_operation_id
  returning * into action_row;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_recover_access_v2(
  uuid,uuid,uuid,uuid,uuid,integer,uuid,bigint,text,text,text,text,bigint,
  text,text,uuid,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_RECOVER_ACCESS_V2_FRESH_AUTHORITY_INVOCATION_BOUND';

create or replace function public.connected_app_settle_action_v2(
  p_operation_id uuid,
  p_claim_id uuid,
  p_fencing_token bigint,
  p_invocation_binding_sha256 text,
  p_access_use_nonce uuid,
  p_effect_use_nonce uuid,
  p_postobserve_use_nonce uuid,
  p_postobserve_impossible boolean,
  p_terminal_outcome text,
  p_terminal_binding_sha256 text,
  p_terminal_resource_version_sha256 text,
  p_provider_request_id_sha256 text,
  p_provider_resource_id_sha256 text,
  p_observed_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  action_row connected_app_private.action_ledger%rowtype;
  owner_value uuid;
begin
  if p_operation_id is null or p_claim_id is null
     or p_fencing_token is null or p_fencing_token < 1
     or p_invocation_binding_sha256 is null
     or p_invocation_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_postobserve_impossible is null
     or p_terminal_outcome is null
     or p_terminal_outcome not in ('read', 'succeeded', 'ambiguous')
     or p_terminal_binding_sha256 is null
     or p_terminal_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_observed_at is null
     or (p_terminal_resource_version_sha256 is not null
         and p_terminal_resource_version_sha256 !~ '^[0-9a-f]{64}$')
     or (p_provider_request_id_sha256 is not null
         and p_provider_request_id_sha256 !~ '^[0-9a-f]{64}$')
     or (p_provider_resource_id_sha256 is not null
         and p_provider_resource_id_sha256 !~ '^[0-9a-f]{64}$') then
    raise exception 'invalid terminal action result' using errcode = '22023';
  end if;

  select ledger.owner_id into owner_value
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id;
  if not found then
    raise exception 'action not found' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(owner_value);
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id and ledger.owner_id = owner_value
  for update;
  if not found then
    raise exception 'action not found' using errcode = '55000';
  end if;
  if action_row.claim_id <> p_claim_id
     or action_row.fencing_token <> p_fencing_token
     or action_row.invocation_binding_sha256 <> p_invocation_binding_sha256 then
    raise exception 'terminal action claim drifted' using errcode = '55000';
  end if;

  if action_row.status = 'terminal' then
    if action_row.terminal_outcome = p_terminal_outcome
       and action_row.terminal_binding_sha256 = p_terminal_binding_sha256
       and action_row.terminal_resource_version_sha256
           is not distinct from p_terminal_resource_version_sha256
       and action_row.provider_request_id_sha256
           is not distinct from p_provider_request_id_sha256
       and action_row.provider_resource_id_sha256
           is not distinct from p_provider_resource_id_sha256
       and action_row.observed_at = p_observed_at
       and action_row.postobserve_impossible = p_postobserve_impossible
       and (
         (p_terminal_outcome = 'read'
          and action_row.read_use_nonce is not distinct from p_access_use_nonce
          and p_effect_use_nonce is null and p_postobserve_use_nonce is null)
         or
         (p_terminal_outcome <> 'read'
          and p_access_use_nonce is null
          and action_row.effect_use_nonce is not distinct from p_effect_use_nonce
          and action_row.postobserve_use_nonce
              is not distinct from p_postobserve_use_nonce)
       ) then
      return pg_catalog.to_jsonb(action_row);
    end if;
    raise exception 'terminal action replay drifted' using errcode = '55000';
  end if;

  if (p_terminal_outcome = 'read' and (
        action_row.mutates_external_state
        or p_access_use_nonce is null
        or p_effect_use_nonce is not null
        or p_postobserve_use_nonce is not null
        or p_postobserve_impossible
        or p_provider_request_id_sha256 is not null
        or p_provider_resource_id_sha256 is not null
      ))
     or (p_terminal_outcome = 'succeeded' and (
        not action_row.mutates_external_state
        or p_access_use_nonce is not null
        or p_effect_use_nonce is null
        or p_terminal_resource_version_sha256 is null
        or p_provider_request_id_sha256 is null
        or p_provider_resource_id_sha256 is null
        or p_postobserve_impossible
      ))
     or (p_terminal_outcome = 'ambiguous' and (
        not action_row.mutates_external_state
        or p_access_use_nonce is not null
        or p_effect_use_nonce is null
        or p_terminal_resource_version_sha256 is not null
        or p_provider_request_id_sha256 is not null
        or p_provider_resource_id_sha256 is not null
        or (p_postobserve_impossible and p_postobserve_use_nonce is not null)
      )) then
    raise exception 'terminal action shape drifted' using errcode = '55000';
  end if;

  perform public.connected_app_settle_action_v1(
    p_operation_id,
    owner_value,
    case when p_terminal_outcome = 'read'
      then p_access_use_nonce else action_row.preobserve_use_nonce end,
    p_effect_use_nonce,
    p_postobserve_use_nonce,
    p_postobserve_impossible,
    p_terminal_outcome,
    p_terminal_binding_sha256,
    p_provider_request_id_sha256,
    p_provider_resource_id_sha256,
    p_observed_at
  );
  update connected_app_private.action_ledger as ledger
  set terminal_resource_version_sha256 = p_terminal_resource_version_sha256,
      updated_at = pg_catalog.clock_timestamp()
  where ledger.operation_id = p_operation_id
  returning * into action_row;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_settle_action_v2(
  uuid,uuid,bigint,text,uuid,uuid,uuid,boolean,text,text,text,text,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_SETTLE_ACTION_V2_CLAIM_FENCE_EXACT_REPLAY';

revoke all on function public.connected_app_claim_action_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,
  text,text,text,text,bigint,uuid,uuid,integer,timestamptz
) from service_role;
revoke all on function public.connected_app_read_action_v1(uuid,uuid,text)
  from service_role;
revoke all on function public.connected_app_recover_access_v1(
  uuid,uuid,uuid,uuid,integer,text,uuid,timestamptz
) from service_role;
revoke all on function public.connected_app_settle_action_v1(
  uuid,uuid,uuid,uuid,uuid,boolean,text,text,text,text,timestamptz
) from service_role;

revoke all on function public.connected_app_claim_action_v2(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,
  text,text,text,text,text,bigint,uuid,uuid,integer,timestamptz
) from public, anon, authenticated;
revoke all on function public.connected_app_read_action_v2(uuid,uuid,text,text)
  from public, anon, authenticated;
revoke all on function public.connected_app_recover_access_v2(
  uuid,uuid,uuid,uuid,uuid,integer,uuid,bigint,text,text,text,text,bigint,
  text,text,uuid,timestamptz,timestamptz
) from public, anon, authenticated;
revoke all on function public.connected_app_settle_action_v2(
  uuid,uuid,bigint,text,uuid,uuid,uuid,boolean,text,text,text,text,text,timestamptz
) from public, anon, authenticated;
grant execute on function public.connected_app_claim_action_v2(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,
  text,text,text,text,text,bigint,uuid,uuid,integer,timestamptz
) to service_role;
grant execute on function public.connected_app_read_action_v2(uuid,uuid,text,text)
  to service_role;
grant execute on function public.connected_app_recover_access_v2(
  uuid,uuid,uuid,uuid,uuid,integer,uuid,bigint,text,text,text,text,bigint,
  text,text,uuid,timestamptz,timestamptz
) to service_role;
grant execute on function public.connected_app_settle_action_v2(
  uuid,uuid,bigint,text,uuid,uuid,uuid,boolean,text,text,text,text,text,timestamptz
) to service_role;

do $postflight$
begin
  if (select pg_catalog.count(*)
       from pg_catalog.pg_attribute as attribute_row
       where attribute_row.attrelid =
           pg_catalog.to_regclass('connected_app_private.action_ledger')
         and attribute_row.attname = 'invocation_binding_sha256'
         and attribute_row.attnotnull
         and not attribute_row.attisdropped
     ) <> 1
     or pg_catalog.obj_description(
       pg_catalog.to_regprocedure(
         'public.connected_app_claim_action_v2(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,text,bigint,uuid,uuid,integer,timestamp with time zone)'
       ), 'pg_proc'
     ) is distinct from
       'ASK_CRUMP_CONNECTED_APP_CLAIM_ACTION_V2_INVOCATION_BOUND_NO_LEGACY_FALLBACK'
     or pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_claim_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,bigint,uuid,uuid,integer,timestamp with time zone)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'service_role', 'public.connected_app_read_action_v1(uuid,uuid,text)', 'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_recover_access_v1(uuid,uuid,uuid,uuid,integer,text,uuid,timestamp with time zone)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_settle_action_v1(uuid,uuid,uuid,uuid,uuid,boolean,text,text,text,text,timestamp with time zone)',
       'EXECUTE'
     ) then
    raise exception 'connected runtime ledger postflight failed'
      using errcode = '55000';
  end if;
end;
$postflight$;

commit;
