begin;

select pg_catalog.set_config('search_path', 'pg_catalog,public', true);
select pg_catalog.set_config('quote_all_identifiers', 'off', true);

-- This slice is intentionally isolated from connected_app_private and the
-- connected_chat_private manifest.  The durable preparation, review,
-- approval, and runtime-ledger rows remain the execution authority.
do $preflight$
declare
  target_relations integer;
  target_sequences integer;
  target_private_functions integer;
  target_public_functions integer;
  target_fingerprint text;
begin
  if pg_catalog.obj_description(
       pg_catalog.to_regclass('connected_app_private.action_preparations'),
       'pg_class'
     ) is distinct from
       'ASK_CRUMP_CONNECTED_APP_ACTION_PREPARATIONS_V1_CONTENT_FREE_NO_EXECUTION'
     or pg_catalog.obj_description(
       pg_catalog.to_regclass('connected_app_private.action_ledger'), 'pg_class'
     ) is distinct from
       'ASK_CRUMP_CONNECTED_APP_ACTION_LEDGER_V1_CONTENT_FREE'
     or pg_catalog.obj_description(
       pg_catalog.to_regclass('connected_app_private.read_results'), 'pg_class'
     ) is distinct from
       'ASK_CRUMP_CONNECTED_READ_RESULTS_V1_OPAQUE_ENCRYPTED_REFERENCE_ONLY'
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null then
    raise exception 'connected-dispatch predecessor is absent or drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.count(*) into target_relations
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_dispatch_private'
    and class_row.relname = 'execution_outbox'
    and class_row.relkind = 'r';

  select pg_catalog.count(*) into target_sequences
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_dispatch_private'
    and class_row.relname = 'lease_fencing_token_seq'
    and class_row.relkind = 'S';

  select pg_catalog.count(*) into target_private_functions
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'connected_dispatch_private'
    and proc_row.proname in (
      'execution_view_v1', 'ensure_one_v1',
      'settle_from_ledger_v1', 'reconcile_one_v1'
    );

  select pg_catalog.count(*) into target_public_functions
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname in (
      'connected_dispatch_scan_owners_v1',
      'connected_dispatch_reconcile_owner_v1',
      'connected_dispatch_ensure_v1',
      'connected_dispatch_claim_v1',
      'connected_dispatch_mark_invoked_v1',
      'connected_dispatch_preflight_failure_v1',
      'connected_dispatch_settle_v1',
      'connected_dispatch_report_runtime_exit_v1',
      'connected_dispatch_read_v1'
    );

  if target_relations = 0 and target_sequences = 0
     and target_private_functions = 0 and target_public_functions = 0 then
    if pg_catalog.to_regnamespace('connected_dispatch_private') is not null
       or exists (
         select 1 from pg_catalog.pg_proc as proc_row
         join pg_catalog.pg_namespace as namespace_row
           on namespace_row.oid = proc_row.pronamespace
         where namespace_row.nspname = 'public'
           and proc_row.proname like 'connected_dispatch_%'
       ) then
      raise exception 'connected-dispatch predecessor is partial'
        using errcode = '55000';
    end if;
  elsif target_relations = 1 and target_sequences = 1
        and target_private_functions = 4 and target_public_functions = 9 then
    select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
      pg_catalog.obj_description(
        pg_catalog.to_regnamespace('connected_dispatch_private'),
        'pg_namespace'
      ),
      pg_catalog.obj_description(
        pg_catalog.to_regclass('connected_dispatch_private.execution_outbox'),
        'pg_class'
      ),
      (select pg_catalog.string_agg(
         attribute_row.attname || ':'
           || pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod)
           || ':' || attribute_row.attnotnull::text,
         ',' order by attribute_row.attnum
       )
       from pg_catalog.pg_attribute as attribute_row
       where attribute_row.attrelid =
         pg_catalog.to_regclass('connected_dispatch_private.execution_outbox')
         and attribute_row.attnum > 0 and not attribute_row.attisdropped),
      (select pg_catalog.string_agg(
         constraint_row.conname || ':'
           || pg_catalog.pg_get_constraintdef(constraint_row.oid, true),
         ',' order by constraint_row.conname collate pg_catalog."C"
       )
       from pg_catalog.pg_constraint as constraint_row
       where constraint_row.conrelid =
         pg_catalog.to_regclass('connected_dispatch_private.execution_outbox')),
      (select pg_catalog.string_agg(
         index_row.relname || ':' || pg_catalog.pg_get_indexdef(index_row.oid),
         ',' order by index_row.relname collate pg_catalog."C"
       )
       from pg_catalog.pg_index as index_meta
       join pg_catalog.pg_class as index_row
         on index_row.oid = index_meta.indexrelid
       where index_meta.indrelid =
         pg_catalog.to_regclass('connected_dispatch_private.execution_outbox')),
      (select pg_catalog.string_agg(
         pg_catalog.pg_get_functiondef(proc_row.oid), E'\n'
         order by namespace_row.nspname collate pg_catalog."C",
                  proc_row.proname collate pg_catalog."C",
                  pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
                    collate pg_catalog."C"
       )
       from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid = proc_row.pronamespace
       where (namespace_row.nspname = 'connected_dispatch_private'
              and proc_row.proname in (
                'execution_view_v1', 'ensure_one_v1',
                'settle_from_ledger_v1', 'reconcile_one_v1'
              ))
          or (namespace_row.nspname = 'public'
              and proc_row.proname like 'connected_dispatch_%'))
    )) into target_fingerprint;
    if target_fingerprint <> 'f57cba04c9b7d590d97e1ea62f960f30' then
      raise exception 'connected-dispatch exact target drifted'
        using errcode = '55000';
    end if;
  else
    raise exception 'connected-dispatch state is partial or mixed'
      using errcode = '55000';
  end if;
end;
$preflight$;

create schema if not exists connected_dispatch_private authorization postgres;
comment on schema connected_dispatch_private is
  'ASK_CRUMP_CONNECTED_DISPATCH_PRIVATE_V1_CONTENT_FREE';
revoke all on schema connected_dispatch_private
  from public, anon, authenticated, service_role;

create sequence if not exists connected_dispatch_private.lease_fencing_token_seq
  as bigint start with 1 increment by 1 no minvalue no maxvalue cache 1;
comment on sequence connected_dispatch_private.lease_fencing_token_seq is
  'ASK_CRUMP_CONNECTED_DISPATCH_FENCING_V1_DATABASE_ALLOCATED';

create table if not exists connected_dispatch_private.execution_outbox (
  operation_id uuid primary key,
  request_id uuid not null unique
    references connected_app_private.action_preparations(request_id)
    on delete cascade,
  action_id uuid not null unique
    references connected_app_private.action_preparations(action_id)
    on delete cascade,
  owner_id uuid not null references public.users(id) on delete cascade,
  grant_id uuid not null
    references connected_app_private.task_grants(grant_id) on delete cascade,
  task_id uuid not null,
  turn_id uuid not null,
  connection_id uuid not null
    references connected_app_private.connections(id) on delete cascade,
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  action text not null,
  authorization_revision bigint not null check (authorization_revision >= 1),
  authorization_snapshot_sha256 text not null
    check (authorization_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  granted_actions_sha256 text not null
    check (granted_actions_sha256 ~ '^[0-9a-f]{64}$'),
  granted_scopes_sha256 text not null
    check (granted_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  grant_actions text[] not null check (cardinality(grant_actions) between 1 and 16),
  grant_actions_sha256 text not null
    check (grant_actions_sha256 ~ '^[0-9a-f]{64}$'),
  task_state_revision bigint not null check (task_state_revision >= 1),
  payload_id uuid not null,
  payload_reference_binding_sha256 text not null
    check (payload_reference_binding_sha256 ~ '^[0-9a-f]{64}$'),
  parameters_sha256 text not null check (parameters_sha256 ~ '^[0-9a-f]{64}$'),
  resource_version_sha256 text
    check (resource_version_sha256 is null or resource_version_sha256 ~ '^[0-9a-f]{64}$'),
  policy_version text not null check (length(policy_version) between 1 and 128),
  mutates_external_state boolean not null,
  approval_class text not null check (
    approval_class in (
      'none', 'external_write_reversible', 'external_communication',
      'calendar_write', 'destructive'
    )
  ),
  preparation_status text not null check (preparation_status in ('ready', 'pending_approval')),
  requested_at timestamptz not null,
  preparation_expires_at timestamptz not null,
  grant_expires_at timestamptz not null,
  approval_id uuid references connected_app_private.approvals(approval_id)
    on delete cascade,
  approval_binding_sha256 text
    check (approval_binding_sha256 is null or approval_binding_sha256 ~ '^[0-9a-f]{64}$'),
  approval_approved_at timestamptz,
  approval_expires_at timestamptz,
  status text not null default 'queued' check (
    status in (
      'queued', 'leased', 'invoked', 'read_succeeded', 'write_succeeded',
      'ambiguous', 'failed', 'cancelled', 'authority_stale', 'effect_unknown'
    )
  ),
  next_attempt_at timestamptz,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  claim_id uuid,
  fencing_token bigint check (fencing_token is null or fencing_token >= 1),
  lease_expires_at timestamptz,
  claimed_at timestamptz,
  invocation_started_at timestamptz,
  terminal_outcome text check (
    terminal_outcome is null or terminal_outcome in (
      'read', 'succeeded', 'ambiguous', 'failed', 'cancelled', 'authority_stale'
    )
  ),
  read_result_ref uuid,
  receipt_outcome text check (
    receipt_outcome is null or receipt_outcome in (
      'drafted', 'sent', 'created', 'updated', 'cancelled'
    )
  ),
  provider_request_id_sha256 text
    check (provider_request_id_sha256 is null or provider_request_id_sha256 ~ '^[0-9a-f]{64}$'),
  provider_resource_id_sha256 text
    check (provider_resource_id_sha256 is null or provider_resource_id_sha256 ~ '^[0-9a-f]{64}$'),
  result_resource_version_sha256 text
    check (result_resource_version_sha256 is null or result_resource_version_sha256 ~ '^[0-9a-f]{64}$'),
  terminal_binding_sha256 text
    check (terminal_binding_sha256 is null or terminal_binding_sha256 ~ '^[0-9a-f]{64}$'),
  failure_code_sha256 text
    check (failure_code_sha256 is null or failure_code_sha256 ~ '^[0-9a-f]{64}$'),
  completed_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_dispatch_operation_identity check (operation_id = action_id),
  constraint connected_dispatch_authority_shape check (
    (not mutates_external_state and approval_class = 'none'
      and preparation_status = 'ready')
    or (mutates_external_state and approval_class <> 'none'
      and preparation_status = 'pending_approval')
  ),
  constraint connected_dispatch_approval_shape check (
    (not mutates_external_state and approval_id is null
      and approval_binding_sha256 is null and approval_approved_at is null
      and approval_expires_at is null)
    or (mutates_external_state and approval_id is not null
      and approval_binding_sha256 is not null and approval_approved_at is not null
      and approval_expires_at is not null
      and approval_expires_at > approval_approved_at)
  ),
  constraint connected_dispatch_state_shape check (
    (status = 'queued' and next_attempt_at is not null
      and claim_id is null and fencing_token is null and lease_expires_at is null
      and claimed_at is null and invocation_started_at is null
      and completed_at is null and terminal_outcome is null)
    or (status = 'leased' and next_attempt_at is null
      and claim_id is not null and fencing_token is not null
      and lease_expires_at is not null and claimed_at is not null
      and invocation_started_at is null and completed_at is null
      and terminal_outcome is null)
    or (status = 'invoked' and next_attempt_at is null
      and claim_id is not null and fencing_token is not null
      and lease_expires_at is not null and claimed_at is not null
      and invocation_started_at is not null and completed_at is null
      and terminal_outcome is null)
    or (status in (
        'read_succeeded', 'write_succeeded', 'ambiguous', 'failed',
        'cancelled', 'authority_stale', 'effect_unknown'
      ) and next_attempt_at is null and completed_at is not null
      and terminal_outcome is not null)
  ),
  constraint connected_dispatch_result_shape check (
    (status = 'read_succeeded' and terminal_outcome = 'read'
      and read_result_ref is not null and terminal_binding_sha256 is not null
      and receipt_outcome is null and provider_request_id_sha256 is null
      and provider_resource_id_sha256 is null and failure_code_sha256 is null)
    or (status = 'write_succeeded' and terminal_outcome = 'succeeded'
      and read_result_ref is null and receipt_outcome is not null
      and provider_request_id_sha256 is not null
      and provider_resource_id_sha256 is not null
      and result_resource_version_sha256 is not null
      and terminal_binding_sha256 is not null and failure_code_sha256 is null)
    or (status = 'ambiguous' and terminal_outcome = 'ambiguous'
      and read_result_ref is null and receipt_outcome is null
      and provider_request_id_sha256 is null
      and provider_resource_id_sha256 is null
      and result_resource_version_sha256 is null
      and terminal_binding_sha256 is not null and failure_code_sha256 is null)
    or (status = 'effect_unknown' and terminal_outcome = 'ambiguous'
      and read_result_ref is null and receipt_outcome is null
      and provider_request_id_sha256 is null
      and provider_resource_id_sha256 is null
      and result_resource_version_sha256 is null and failure_code_sha256 is null)
    or (status = 'failed' and terminal_outcome = 'failed'
      and read_result_ref is null and receipt_outcome is null
      and provider_request_id_sha256 is null
      and provider_resource_id_sha256 is null
      and result_resource_version_sha256 is null
      and failure_code_sha256 is not null)
    or (status in ('cancelled', 'authority_stale')
      and terminal_outcome = status and read_result_ref is null
      and receipt_outcome is null and provider_request_id_sha256 is null
      and provider_resource_id_sha256 is null
      and result_resource_version_sha256 is null
      and terminal_binding_sha256 is null and failure_code_sha256 is null)
    or (status in ('queued', 'leased', 'invoked')
      and read_result_ref is null and receipt_outcome is null
      and provider_request_id_sha256 is null
      and provider_resource_id_sha256 is null
      and result_resource_version_sha256 is null
      and terminal_binding_sha256 is null and failure_code_sha256 is null)
  )
);
comment on table connected_dispatch_private.execution_outbox is
  'ASK_CRUMP_CONNECTED_DISPATCH_OUTBOX_V1_CONTENT_FREE_RUNTIME_LEDGER_FINAL';
comment on column connected_dispatch_private.execution_outbox.parameters_sha256 is
  'ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PAYLOAD_COMMITMENT_V1_NOT_PLAINTEXT_REQUEST_DIGEST';
create unique index if not exists connected_dispatch_claim_id_idx
  on connected_dispatch_private.execution_outbox(claim_id)
  where claim_id is not null;
create index if not exists connected_dispatch_ready_idx
  on connected_dispatch_private.execution_outbox(owner_id, next_attempt_at, action_id)
  where status = 'queued';
create index if not exists connected_dispatch_stale_lease_idx
  on connected_dispatch_private.execution_outbox(owner_id, lease_expires_at, action_id)
  where status in ('leased', 'invoked');
create index if not exists connected_dispatch_connection_idx
  on connected_dispatch_private.execution_outbox(connection_id, action_id);

alter table connected_dispatch_private.execution_outbox enable row level security;
alter table connected_dispatch_private.execution_outbox force row level security;

create or replace function connected_dispatch_private.execution_view_v1(
  p_owner_id uuid, p_action_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.to_jsonb(outbox) - 'claimed_at'
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
$fn$;
comment on function connected_dispatch_private.execution_view_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_DISPATCH_VIEW_V1_CONTENT_FREE';

create or replace function connected_dispatch_private.ensure_one_v1(
  p_owner_id uuid, p_request_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  preparation_row connected_app_private.action_preparations%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  connection_row connected_app_private.connections%rowtype;
  grant_row connected_app_private.task_grants%rowtype;
  review_row connected_app_private.approval_reviews%rowtype;
  approval_row connected_app_private.approvals%rowtype;
  outbox_row connected_dispatch_private.execution_outbox%rowtype;
  eligible boolean := false;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_owner_id is null or p_request_id is null then
    raise exception 'connected-dispatch ensure keys are invalid'
      using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);

  select preparation.* into preparation_row
  from connected_app_private.action_preparations as preparation
  where preparation.owner_id = p_owner_id
    and preparation.request_id = p_request_id
  for share;
  if not found then
    return null;
  end if;
  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action = preparation_row.action
  for share;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id
    and connection.id = preparation_row.connection_id
  for share;
  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.owner_id = p_owner_id
    and task_grant.grant_id = preparation_row.grant_id
  for share;

  if preparation_row.mutates_external_state then
    select review.* into review_row
    from connected_app_private.approval_reviews as review
    where review.owner_id = p_owner_id
      and review.approval_id = preparation_row.approval_id
    for share;
    select approval.* into approval_row
    from connected_app_private.approvals as approval
    where approval.owner_id = p_owner_id
      and approval.approval_id = preparation_row.approval_id
    for share;
  end if;

  eligible := authority_row.action is not null
    and authority_row.resource = preparation_row.resource
    and authority_row.mutates_external_state = preparation_row.mutates_external_state
    and authority_row.approval_class = preparation_row.approval_class
    and preparation_row.expires_at > now_at
    and ((not preparation_row.mutates_external_state
          and preparation_row.status = 'ready'
          and preparation_row.approval_id is null)
      or (preparation_row.mutates_external_state
          and preparation_row.status = 'pending_approval'
          and preparation_row.approval_id is not null))
    and connection_row.id is not null
    and connection_row.authorization_state = 'active'
    and connection_row.provider = preparation_row.provider
    and connection_row.resource = preparation_row.resource
    and connection_row.authorization_revision = preparation_row.authorization_revision
    and connection_row.authorization_snapshot_sha256 =
      preparation_row.authorization_snapshot_sha256
    and connection_row.granted_actions_sha256 = preparation_row.granted_actions_sha256
    and connection_row.granted_scopes_sha256 = preparation_row.granted_scopes_sha256
    and preparation_row.action = any(connection_row.granted_actions)
    and connection_row.authorization_expires_at is not null
    and connection_row.authorization_expires_at > now_at
    and grant_row.grant_id is not null
    and grant_row.task_id = preparation_row.task_id
    and grant_row.turn_id = preparation_row.turn_id
    and grant_row.connection_id = preparation_row.connection_id
    and grant_row.provider = preparation_row.provider
    and grant_row.resource = preparation_row.resource
    and grant_row.authorization_revision = preparation_row.authorization_revision
    and grant_row.authorization_snapshot_sha256 =
      preparation_row.authorization_snapshot_sha256
    and grant_row.actions_sha256 = preparation_row.grant_actions_sha256
    and preparation_row.action = any(grant_row.actions)
    and grant_row.task_state_revision = preparation_row.task_state_revision
    and grant_row.revoked_at is null and grant_row.expires_at > now_at;

  if preparation_row.mutates_external_state then
    eligible := eligible
      and review_row.approval_id is not null
      and review_row.status = 'approved'
      and review_row.action_id = preparation_row.action_id
      and review_row.connection_id = preparation_row.connection_id
      and review_row.task_id = preparation_row.task_id
      and review_row.turn_id = preparation_row.turn_id
      and review_row.provider = preparation_row.provider
      and review_row.resource = preparation_row.resource
      and review_row.action = preparation_row.action
      and review_row.authorization_revision = preparation_row.authorization_revision
      and review_row.authorization_snapshot_sha256 =
        preparation_row.authorization_snapshot_sha256
      and review_row.granted_scopes_sha256 = preparation_row.granted_scopes_sha256
      and review_row.policy_version = preparation_row.policy_version
      and review_row.approval_class = preparation_row.approval_class
      and review_row.approval_binding_sha256 = preparation_row.approval_binding_sha256
      and review_row.parameters_sha256 = preparation_row.parameters_sha256
      and review_row.resource_version_sha256 is not distinct from
        preparation_row.resource_version_sha256
      and review_row.expires_at > now_at
      and approval_row.approval_id is not null
      and approval_row.action_id = preparation_row.action_id
      and approval_row.connection_id = preparation_row.connection_id
      and approval_row.task_id = preparation_row.task_id
      and approval_row.turn_id = preparation_row.turn_id
      and approval_row.provider = preparation_row.provider
      and approval_row.resource = preparation_row.resource
      and approval_row.action = preparation_row.action
      and approval_row.authorization_revision = preparation_row.authorization_revision
      and approval_row.authorization_snapshot_sha256 =
        preparation_row.authorization_snapshot_sha256
      and approval_row.approval_class = preparation_row.approval_class
      and approval_row.approval_binding_sha256 = preparation_row.approval_binding_sha256
      and approval_row.parameters_sha256 = preparation_row.parameters_sha256
      and approval_row.resource_version_sha256 is not distinct from
        preparation_row.resource_version_sha256
      and approval_row.approved_at = review_row.decided_at
      and approval_row.expires_at = review_row.expires_at
      and approval_row.expires_at > now_at
      and approval_row.consumed_at is null
      and approval_row.consumed_by_operation_id is null;
  end if;

  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.action_id = preparation_row.action_id
     or outbox.request_id = preparation_row.request_id
  for update;
  if found then
    if outbox_row.operation_id <> preparation_row.action_id
       or outbox_row.request_id <> preparation_row.request_id
       or outbox_row.owner_id <> preparation_row.owner_id
       or outbox_row.grant_id <> preparation_row.grant_id
       or outbox_row.action_id <> preparation_row.action_id
       or outbox_row.task_id <> preparation_row.task_id
       or outbox_row.turn_id <> preparation_row.turn_id
       or outbox_row.connection_id <> preparation_row.connection_id
       or outbox_row.provider <> preparation_row.provider
       or outbox_row.resource <> preparation_row.resource
       or outbox_row.action <> preparation_row.action
       or outbox_row.authorization_revision <> preparation_row.authorization_revision
       or outbox_row.authorization_snapshot_sha256 <>
          preparation_row.authorization_snapshot_sha256
       or outbox_row.granted_actions_sha256 <> preparation_row.granted_actions_sha256
       or outbox_row.granted_scopes_sha256 <> preparation_row.granted_scopes_sha256
       or outbox_row.grant_actions_sha256 <> preparation_row.grant_actions_sha256
       or outbox_row.task_state_revision <> preparation_row.task_state_revision
       or outbox_row.payload_id <> preparation_row.payload_id
       or outbox_row.payload_reference_binding_sha256 <>
          preparation_row.payload_reference_binding_sha256
       or outbox_row.parameters_sha256 <> preparation_row.parameters_sha256
       or outbox_row.resource_version_sha256 is distinct from
          preparation_row.resource_version_sha256
       or outbox_row.policy_version <> preparation_row.policy_version
       or outbox_row.mutates_external_state <> preparation_row.mutates_external_state
       or outbox_row.approval_class <> preparation_row.approval_class
       or outbox_row.preparation_status <> preparation_row.status
       or outbox_row.requested_at <> preparation_row.requested_at
       or outbox_row.preparation_expires_at <> preparation_row.expires_at
       or outbox_row.approval_id is distinct from approval_row.approval_id
       or outbox_row.approval_binding_sha256 is distinct from
          approval_row.approval_binding_sha256 then
      raise exception 'connected-dispatch replay drifted'
        using errcode = '55000';
    end if;
    if not eligible and outbox_row.status in ('queued', 'leased') then
      update connected_dispatch_private.execution_outbox as outbox
      set status = 'authority_stale', next_attempt_at = null,
          claim_id = null, fencing_token = null, lease_expires_at = null,
          claimed_at = null, terminal_outcome = 'authority_stale',
          completed_at = now_at, updated_at = now_at
      where outbox.operation_id = outbox_row.operation_id;
    end if;
    return connected_dispatch_private.execution_view_v1(
      p_owner_id, preparation_row.action_id
    );
  end if;

  if not eligible then
    return null;
  end if;
  insert into connected_dispatch_private.execution_outbox (
    operation_id, request_id, owner_id, grant_id, action_id, task_id,
    turn_id, connection_id, provider, resource, action,
    authorization_revision, authorization_snapshot_sha256,
    granted_actions_sha256, granted_scopes_sha256,
    grant_actions, grant_actions_sha256, task_state_revision,
    payload_id, payload_reference_binding_sha256, parameters_sha256,
    resource_version_sha256, policy_version, mutates_external_state,
    approval_class, preparation_status, requested_at,
    preparation_expires_at, grant_expires_at, approval_id,
    approval_binding_sha256, approval_approved_at, approval_expires_at,
    status, next_attempt_at
  ) values (
    preparation_row.action_id, preparation_row.request_id,
    preparation_row.owner_id, preparation_row.grant_id,
    preparation_row.action_id, preparation_row.task_id,
    preparation_row.turn_id, preparation_row.connection_id,
    preparation_row.provider, preparation_row.resource,
    preparation_row.action, preparation_row.authorization_revision,
    preparation_row.authorization_snapshot_sha256,
    preparation_row.granted_actions_sha256,
    preparation_row.granted_scopes_sha256, grant_row.actions,
    preparation_row.grant_actions_sha256,
    preparation_row.task_state_revision, preparation_row.payload_id,
    preparation_row.payload_reference_binding_sha256,
    preparation_row.parameters_sha256,
    preparation_row.resource_version_sha256, preparation_row.policy_version,
    preparation_row.mutates_external_state,
    preparation_row.approval_class, preparation_row.status,
    preparation_row.requested_at, preparation_row.expires_at,
    grant_row.expires_at, approval_row.approval_id,
    approval_row.approval_binding_sha256, approval_row.approved_at,
    approval_row.expires_at, 'queued', now_at
  );
  return connected_dispatch_private.execution_view_v1(
    p_owner_id, preparation_row.action_id
  );
end;
$fn$;
comment on function connected_dispatch_private.ensure_one_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_DISPATCH_ENSURE_V1_SOURCE_OF_TRUTH_RECONCILER';

create or replace function connected_dispatch_private.settle_from_ledger_v1(
  p_owner_id uuid, p_action_id uuid, p_runtime_finished boolean
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  outbox_row connected_dispatch_private.execution_outbox%rowtype;
  ledger_row connected_app_private.action_ledger%rowtype;
  read_row connected_app_private.read_results%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
  retry_at timestamptz;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
  for update;
  if not found then
    return null;
  end if;
  if outbox_row.status in (
    'read_succeeded', 'write_succeeded', 'ambiguous', 'failed',
    'cancelled', 'authority_stale', 'effect_unknown'
  ) then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  if outbox_row.status <> 'invoked' then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;

  select ledger.* into ledger_row
  from connected_app_private.action_ledger as ledger
  where ledger.owner_id = p_owner_id
    and ledger.operation_id = outbox_row.operation_id
  for share;
  if found and (
       ledger_row.action_id <> outbox_row.action_id
       or ledger_row.task_id <> outbox_row.task_id
       or ledger_row.turn_id <> outbox_row.turn_id
       or ledger_row.connection_id <> outbox_row.connection_id
       or ledger_row.grant_id <> outbox_row.grant_id
       or ledger_row.provider <> outbox_row.provider
       or ledger_row.resource <> outbox_row.resource
       or ledger_row.action <> outbox_row.action
       or ledger_row.authorization_revision <> outbox_row.authorization_revision
       or ledger_row.authorization_snapshot_sha256 <>
          outbox_row.authorization_snapshot_sha256
       or ledger_row.granted_actions_sha256 <> outbox_row.granted_actions_sha256
       or ledger_row.granted_scopes_sha256 <> outbox_row.granted_scopes_sha256
       or ledger_row.parameters_sha256 <> outbox_row.parameters_sha256
       or ledger_row.resource_version_sha256 is distinct from
          outbox_row.resource_version_sha256
       or ledger_row.task_state_revision <> outbox_row.task_state_revision
       or ledger_row.mutates_external_state <> outbox_row.mutates_external_state
       or ledger_row.approval_class <> outbox_row.approval_class
     ) then
    raise exception 'connected-dispatch runtime-ledger binding drifted'
      using errcode = '55000';
  end if;

  if found and ledger_row.status = 'terminal' then
    if ledger_row.terminal_outcome = 'read' then
      select result.* into read_row
      from connected_app_private.read_results as result
      where result.owner_id = p_owner_id
        and result.operation_id = outbox_row.operation_id
      for share;
      if outbox_row.mutates_external_state or not found
         or read_row.terminal_binding_sha256 <> ledger_row.terminal_binding_sha256
         or read_row.authority_sha256 <> ledger_row.authority_sha256
         or read_row.idempotency_key_sha256 <> ledger_row.idempotency_key_sha256
         or read_row.completed_at is null then
        raise exception 'connected-dispatch encrypted read result is not terminal'
          using errcode = '55000';
      end if;
      update connected_dispatch_private.execution_outbox as outbox
      set status = 'read_succeeded', terminal_outcome = 'read',
          read_result_ref = read_row.result_payload_id,
          result_resource_version_sha256 = ledger_row.resource_version_sha256,
          terminal_binding_sha256 = ledger_row.terminal_binding_sha256,
          completed_at = ledger_row.terminal_at, updated_at = now_at
      where outbox.operation_id = outbox_row.operation_id;
    elsif ledger_row.terminal_outcome = 'succeeded' then
      if not outbox_row.mutates_external_state
         or ledger_row.provider_request_id_sha256 is null
         or ledger_row.provider_resource_id_sha256 is null
         or ledger_row.resource_version_sha256 is null then
        raise exception 'connected-dispatch write receipt is incomplete'
          using errcode = '55000';
      end if;
      update connected_dispatch_private.execution_outbox as outbox
      set status = 'write_succeeded', terminal_outcome = 'succeeded',
          receipt_outcome = case outbox_row.action
            when 'mail.create_draft' then 'drafted'
            when 'mail.send' then 'sent'
            when 'mail.reply' then 'sent'
            when 'calendar.create' then 'created'
            when 'calendar.update' then 'updated'
            when 'calendar.cancel' then 'cancelled'
            else null end,
          provider_request_id_sha256 = ledger_row.provider_request_id_sha256,
          provider_resource_id_sha256 = ledger_row.provider_resource_id_sha256,
          result_resource_version_sha256 = ledger_row.resource_version_sha256,
          terminal_binding_sha256 = ledger_row.terminal_binding_sha256,
          completed_at = ledger_row.terminal_at, updated_at = now_at
      where outbox.operation_id = outbox_row.operation_id;
    elsif ledger_row.terminal_outcome = 'ambiguous' then
      update connected_dispatch_private.execution_outbox as outbox
      set status = 'ambiguous', terminal_outcome = 'ambiguous',
          terminal_binding_sha256 = ledger_row.terminal_binding_sha256,
          completed_at = ledger_row.terminal_at, updated_at = now_at
      where outbox.operation_id = outbox_row.operation_id;
    elsif ledger_row.terminal_outcome = 'failed' then
      update connected_dispatch_private.execution_outbox as outbox
      set status = 'failed', terminal_outcome = 'failed',
          terminal_binding_sha256 = ledger_row.terminal_binding_sha256,
          failure_code_sha256 = ledger_row.terminal_binding_sha256,
          completed_at = ledger_row.terminal_at, updated_at = now_at
      where outbox.operation_id = outbox_row.operation_id;
    else
      raise exception 'connected-dispatch runtime terminal is unsupported'
        using errcode = '55000';
    end if;
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;

  if found and ledger_row.status = 'effect_possible'
     and (p_runtime_finished or outbox_row.lease_expires_at <= now_at) then
    update connected_dispatch_private.execution_outbox as outbox
    set status = 'effect_unknown', terminal_outcome = 'ambiguous',
        completed_at = now_at, updated_at = now_at
    where outbox.operation_id = outbox_row.operation_id;
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;

  if found and ledger_row.status = 'access_granted'
     and not outbox_row.mutates_external_state
     and ledger_row.read_consumed_at is not null
     and (p_runtime_finished or outbox_row.lease_expires_at <= now_at) then
    update connected_dispatch_private.execution_outbox as outbox
    set status = 'effect_unknown', terminal_outcome = 'ambiguous',
        completed_at = now_at, updated_at = now_at
    where outbox.operation_id = outbox_row.operation_id;
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;

  if (p_runtime_finished or outbox_row.lease_expires_at <= now_at)
     and (
       not found
       or (ledger_row.status in ('claimed', 'access_granted')
           and ledger_row.lease_expires_at <= now_at)
     ) then
    retry_at := now_at + pg_catalog.make_interval(
      secs => least(
        300,
        pg_catalog.power(2::numeric,
          least(outbox_row.attempt_count, 8))::integer
      )
    );
    update connected_dispatch_private.execution_outbox as outbox
    set status = 'queued', next_attempt_at = retry_at,
        claim_id = null, fencing_token = null, lease_expires_at = null,
        claimed_at = null, invocation_started_at = null, updated_at = now_at
    where outbox.operation_id = outbox_row.operation_id;
  end if;
  return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
end;
$fn$;
comment on function connected_dispatch_private.settle_from_ledger_v1(uuid,uuid,boolean) is
  'ASK_CRUMP_CONNECTED_DISPATCH_SETTLE_V1_RUNTIME_LEDGER_FINAL_AUTHORITY';

create or replace function connected_dispatch_private.reconcile_one_v1(
  p_owner_id uuid, p_action_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  outbox_row connected_dispatch_private.execution_outbox%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
  for update;
  if not found then
    return null;
  end if;
  if outbox_row.status = 'invoked' then
    return connected_dispatch_private.settle_from_ledger_v1(
      p_owner_id, p_action_id, false
    );
  end if;
  if outbox_row.status = 'leased' and outbox_row.lease_expires_at <= now_at then
    update connected_dispatch_private.execution_outbox as outbox
    set status = 'queued',
        next_attempt_at = now_at + pg_catalog.make_interval(
          secs => least(
            300,
            pg_catalog.power(2::numeric,
              least(outbox_row.attempt_count, 8))::integer
          )
        ),
        claim_id = null, fencing_token = null, lease_expires_at = null,
        claimed_at = null, updated_at = now_at
    where outbox.operation_id = outbox_row.operation_id;
  end if;
  perform connected_dispatch_private.ensure_one_v1(
    p_owner_id, outbox_row.request_id
  );
  return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
end;
$fn$;
comment on function connected_dispatch_private.reconcile_one_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_DISPATCH_RECONCILE_ONE_V1_BOUNDED_NO_PROVIDER';

create or replace function public.connected_dispatch_scan_owners_v1(
  p_limit integer
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $fn$
declare
  result jsonb;
begin
  if p_limit not between 1 and 100 then
    raise exception 'connected-dispatch scan limit is invalid'
      using errcode = '22023';
  end if;
  with owners as (
    select outbox.owner_id
    from connected_dispatch_private.execution_outbox as outbox
    where outbox.status in ('queued', 'leased', 'invoked')
    union
    select preparation.owner_id
    from connected_app_private.action_preparations as preparation
    left join connected_app_private.approval_reviews as review
      on review.owner_id = preparation.owner_id
     and review.approval_id = preparation.approval_id
    where preparation.expires_at > pg_catalog.statement_timestamp()
      and (preparation.status = 'ready' or review.status = 'approved')
  ), bounded as (
    select owner_id from owners order by owner_id limit p_limit
  )
  select coalesce(
    pg_catalog.jsonb_agg(owner_id::text order by owner_id), '[]'::jsonb
  ) into result from bounded;
  return result;
end;
$fn$;
comment on function public.connected_dispatch_scan_owners_v1(integer) is
  'ASK_CRUMP_CONNECTED_DISPATCH_SCAN_OWNERS_V1_BOUNDED_CONTENT_FREE';

create or replace function public.connected_dispatch_reconcile_owner_v1(
  p_owner_id uuid, p_limit integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  candidate record;
  reconciled integer := 0;
  ensured integer := 0;
  ready jsonb;
begin
  if p_owner_id is null or p_limit not between 1 and 100 then
    raise exception 'connected-dispatch reconcile bounds are invalid'
      using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);

  for candidate in
    select outbox.action_id
    from connected_dispatch_private.execution_outbox as outbox
    where outbox.owner_id = p_owner_id
      and outbox.status in ('queued', 'leased', 'invoked')
    order by outbox.action_id
    limit p_limit
  loop
    perform connected_dispatch_private.reconcile_one_v1(
      p_owner_id, candidate.action_id
    );
    reconciled := reconciled + 1;
  end loop;

  for candidate in
    select preparation.request_id
    from connected_app_private.action_preparations as preparation
    left join connected_app_private.approval_reviews as review
      on review.owner_id = preparation.owner_id
     and review.approval_id = preparation.approval_id
    where preparation.owner_id = p_owner_id
      and preparation.expires_at > pg_catalog.clock_timestamp()
      and (preparation.status = 'ready' or review.status = 'approved')
      and not exists (
        select 1
        from connected_dispatch_private.execution_outbox as outbox
        where outbox.request_id = preparation.request_id
      )
    order by preparation.request_id
    limit p_limit
  loop
    if connected_dispatch_private.ensure_one_v1(
         p_owner_id, candidate.request_id
       ) is not null then
      ensured := ensured + 1;
    end if;
  end loop;

  select coalesce(
    pg_catalog.jsonb_agg(
      connected_dispatch_private.execution_view_v1(
        outbox.owner_id, outbox.action_id
      ) order by outbox.next_attempt_at, outbox.action_id
    ), '[]'::jsonb
  ) into ready
  from (
    select candidate_outbox.*
    from connected_dispatch_private.execution_outbox as candidate_outbox
    where candidate_outbox.owner_id = p_owner_id
      and candidate_outbox.status = 'queued'
      and candidate_outbox.next_attempt_at <= pg_catalog.clock_timestamp()
    order by candidate_outbox.next_attempt_at, candidate_outbox.action_id
    limit p_limit
  ) as outbox;

  return pg_catalog.jsonb_build_object(
    'owner_id', p_owner_id,
    'ensured_count', ensured,
    'reconciled_count', reconciled,
    'ready', ready
  );
end;
$fn$;
comment on function public.connected_dispatch_reconcile_owner_v1(uuid,integer) is
  'ASK_CRUMP_CONNECTED_DISPATCH_RECONCILE_OWNER_V1_BOUNDED_SOURCE_DISCOVERY';

create or replace function public.connected_dispatch_ensure_v1(
  p_owner_id uuid, p_request_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
begin
  if p_owner_id is null or p_request_id is null then
    raise exception 'connected-dispatch ensure keys are invalid'
      using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  return connected_dispatch_private.ensure_one_v1(p_owner_id, p_request_id);
end;
$fn$;
comment on function public.connected_dispatch_ensure_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_DISPATCH_ENSURE_PUBLIC_V1_SERVICE_ONLY';

create or replace function public.connected_dispatch_claim_v1(
  p_owner_id uuid, p_action_id uuid, p_claim_id uuid,
  p_lease_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  outbox_row connected_dispatch_private.execution_outbox%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
  lease_until timestamptz;
begin
  if p_owner_id is null or p_action_id is null or p_claim_id is null
     or p_lease_seconds not between 30 and 300 then
    raise exception 'connected-dispatch claim bounds are invalid'
      using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
  for update;
  if not found then
    return null;
  end if;
  perform connected_dispatch_private.ensure_one_v1(
    p_owner_id, outbox_row.request_id
  );
  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
  for update;
  if outbox_row.status = 'invoked' then
    return connected_dispatch_private.settle_from_ledger_v1(
      p_owner_id, p_action_id, false
    );
  end if;
  if outbox_row.status not in ('queued', 'leased') then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  if outbox_row.status = 'leased' and outbox_row.lease_expires_at > now_at then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  if outbox_row.status = 'queued' and outbox_row.next_attempt_at > now_at then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  lease_until := least(
    outbox_row.preparation_expires_at,
    now_at + pg_catalog.make_interval(secs => p_lease_seconds)
  );
  if lease_until <= now_at + interval '5 seconds' then
    update connected_dispatch_private.execution_outbox as outbox
    set status = 'authority_stale', next_attempt_at = null,
        claim_id = null, fencing_token = null, lease_expires_at = null,
        claimed_at = null, terminal_outcome = 'authority_stale',
        completed_at = now_at, updated_at = now_at
    where outbox.operation_id = outbox_row.operation_id;
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  update connected_dispatch_private.execution_outbox as outbox
  set status = 'leased', next_attempt_at = null,
      claim_id = p_claim_id,
      fencing_token = pg_catalog.nextval(
        'connected_dispatch_private.lease_fencing_token_seq'::regclass
      ),
      lease_expires_at = lease_until, claimed_at = now_at,
      invocation_started_at = null,
      attempt_count = outbox.attempt_count + 1,
      updated_at = now_at
  where outbox.operation_id = outbox_row.operation_id;
  return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
end;
$fn$;
comment on function public.connected_dispatch_claim_v1(uuid,uuid,uuid,integer) is
  'ASK_CRUMP_CONNECTED_DISPATCH_CLAIM_V1_ONE_WINNER_LEASED';

create or replace function public.connected_dispatch_mark_invoked_v1(
  p_owner_id uuid, p_action_id uuid, p_claim_id uuid,
  p_fencing_token bigint
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  outbox_row connected_dispatch_private.execution_outbox%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_owner_id is null or p_action_id is null or p_claim_id is null
     or p_fencing_token < 1 then
    raise exception 'connected-dispatch invocation fence is invalid'
      using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
  for update;
  if not found then
    return null;
  end if;
  if outbox_row.status = 'invoked'
     and outbox_row.claim_id = p_claim_id
     and outbox_row.fencing_token = p_fencing_token then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  perform connected_dispatch_private.ensure_one_v1(
    p_owner_id, outbox_row.request_id
  );
  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
  for update;
  if outbox_row.status <> 'leased'
     or outbox_row.claim_id <> p_claim_id
     or outbox_row.fencing_token <> p_fencing_token
     or outbox_row.lease_expires_at <= now_at then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  update connected_dispatch_private.execution_outbox as outbox
  set status = 'invoked', invocation_started_at = now_at, updated_at = now_at
  where outbox.operation_id = outbox_row.operation_id;
  return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
end;
$fn$;
comment on function public.connected_dispatch_mark_invoked_v1(uuid,uuid,uuid,bigint) is
  'ASK_CRUMP_CONNECTED_DISPATCH_MARK_INVOKED_V1_DURABLE_RUNTIME_BOUNDARY';

create or replace function public.connected_dispatch_preflight_failure_v1(
  p_owner_id uuid, p_action_id uuid, p_claim_id uuid,
  p_fencing_token bigint, p_retryable boolean,
  p_failure_code_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  outbox_row connected_dispatch_private.execution_outbox%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_owner_id is null or p_action_id is null or p_claim_id is null
     or p_fencing_token < 1 or p_retryable is null
     or p_failure_code_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'connected-dispatch preflight failure is invalid'
      using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
  for update;
  if not found then return null; end if;
  if outbox_row.status <> 'leased'
     or outbox_row.claim_id <> p_claim_id
     or outbox_row.fencing_token <> p_fencing_token
     or outbox_row.invocation_started_at is not null then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  if p_retryable then
    update connected_dispatch_private.execution_outbox as outbox
    set status = 'queued',
        next_attempt_at = now_at + pg_catalog.make_interval(
          secs => least(
            300,
            pg_catalog.power(2::numeric,
              least(outbox_row.attempt_count, 8))::integer
          )
        ),
        claim_id = null, fencing_token = null, lease_expires_at = null,
        claimed_at = null, updated_at = now_at
    where outbox.operation_id = outbox_row.operation_id;
  else
    update connected_dispatch_private.execution_outbox as outbox
    set status = 'failed', terminal_outcome = 'failed',
        next_attempt_at = null, failure_code_sha256 = p_failure_code_sha256,
        completed_at = now_at, updated_at = now_at
    where outbox.operation_id = outbox_row.operation_id;
  end if;
  return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
end;
$fn$;
comment on function public.connected_dispatch_preflight_failure_v1(uuid,uuid,uuid,bigint,boolean,text) is
  'ASK_CRUMP_CONNECTED_DISPATCH_PREFLIGHT_FAILURE_V1_NO_PROVIDER_EFFECT';

create or replace function public.connected_dispatch_settle_v1(
  p_owner_id uuid, p_action_id uuid, p_claim_id uuid,
  p_fencing_token bigint
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  outbox_row connected_dispatch_private.execution_outbox%rowtype;
begin
  if p_owner_id is null or p_action_id is null or p_claim_id is null
     or p_fencing_token < 1 then
    raise exception 'connected-dispatch settlement fence is invalid'
      using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
  for share;
  if not found then return null; end if;
  if outbox_row.claim_id is distinct from p_claim_id
     or outbox_row.fencing_token is distinct from p_fencing_token then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  return connected_dispatch_private.settle_from_ledger_v1(
    p_owner_id, p_action_id, true
  );
end;
$fn$;
comment on function public.connected_dispatch_settle_v1(uuid,uuid,uuid,bigint) is
  'ASK_CRUMP_CONNECTED_DISPATCH_SETTLE_PUBLIC_V1_LEDGER_READBACK';

create or replace function public.connected_dispatch_report_runtime_exit_v1(
  p_owner_id uuid, p_action_id uuid, p_claim_id uuid,
  p_fencing_token bigint
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  outbox_row connected_dispatch_private.execution_outbox%rowtype;
begin
  if p_owner_id is null or p_action_id is null or p_claim_id is null
     or p_fencing_token < 1 then
    raise exception 'connected-dispatch runtime-exit fence is invalid'
      using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select outbox.* into outbox_row
  from connected_dispatch_private.execution_outbox as outbox
  where outbox.owner_id = p_owner_id and outbox.action_id = p_action_id
  for share;
  if not found then return null; end if;
  if outbox_row.claim_id is distinct from p_claim_id
     or outbox_row.fencing_token is distinct from p_fencing_token then
    return connected_dispatch_private.execution_view_v1(p_owner_id, p_action_id);
  end if;
  return connected_dispatch_private.settle_from_ledger_v1(
    p_owner_id, p_action_id, true
  );
end;
$fn$;
comment on function public.connected_dispatch_report_runtime_exit_v1(uuid,uuid,uuid,bigint) is
  'ASK_CRUMP_CONNECTED_DISPATCH_RUNTIME_EXIT_V1_NO_BLIND_EFFECT_RETRY';

create or replace function public.connected_dispatch_read_v1(
  p_owner_id uuid, p_action_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select connected_dispatch_private.execution_view_v1(
    p_owner_id, p_action_id
  )
$fn$;
comment on function public.connected_dispatch_read_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_DISPATCH_READ_V1_OWNER_ACTION_RESPONSE_LOSS';

alter schema connected_dispatch_private owner to postgres;
alter table connected_dispatch_private.execution_outbox owner to postgres;
alter sequence connected_dispatch_private.lease_fencing_token_seq owner to postgres;

revoke all on all tables in schema connected_dispatch_private
  from public, anon, authenticated, service_role;
revoke all on all sequences in schema connected_dispatch_private
  from public, anon, authenticated, service_role;
revoke all on all functions in schema connected_dispatch_private
  from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema connected_dispatch_private
  revoke all on tables from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema connected_dispatch_private
  revoke all on sequences from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema connected_dispatch_private
  revoke all on functions from public, anon, authenticated, service_role;

do $public_acl$
declare
  function_row record;
  role_name text;
begin
  for function_row in
    select proc_row.oid,
           namespace_row.nspname || '.' || proc_row.proname || '('
             || pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || ')' as signature
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname like 'connected_dispatch_%'
  loop
    execute pg_catalog.format('alter function %s owner to postgres', function_row.signature);
    execute pg_catalog.format('revoke all on function %s from public', function_row.signature);
    for role_name in select role_row.rolname from pg_catalog.pg_roles as role_row
    loop
      if role_name <> 'postgres' then
        execute pg_catalog.format(
          'revoke all on function %s from %I', function_row.signature, role_name
        );
      end if;
    end loop;
    execute pg_catalog.format(
      'grant execute on function %s to service_role', function_row.signature
    );
  end loop;
end;
$public_acl$;

do $postflight$
declare
  relation_row record;
  function_row record;
begin
  select class_row.oid, class_row.relowner, class_row.relrowsecurity,
         class_row.relforcerowsecurity
  into relation_row
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_dispatch_private'
    and class_row.relname = 'execution_outbox';
  if not found
     or pg_catalog.pg_get_userbyid(relation_row.relowner) <> 'postgres'
     or not relation_row.relrowsecurity or not relation_row.relforcerowsecurity
     or exists (
       select 1
       from pg_catalog.aclexplode(coalesce(
         (select class_row.relacl from pg_catalog.pg_class as class_row
          where class_row.oid = relation_row.oid),
         pg_catalog.acldefault('r', relation_row.relowner)
       )) as acl_row
       where acl_row.grantee <> relation_row.relowner
     ) then
    raise exception 'connected-dispatch table authority drifted'
      using errcode = '55000';
  end if;

  for function_row in
    select proc_row.oid, proc_row.proname, proc_row.proowner,
           proc_row.prosecdef, proc_row.proconfig
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname like 'connected_dispatch_%'
  loop
    if pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
       or not function_row.prosecdef
       or function_row.proconfig is distinct from array['search_path=""']::text[]
       or not exists (
         select 1 from pg_catalog.aclexplode(coalesce(
           (select proc_row.proacl from pg_catalog.pg_proc as proc_row
            where proc_row.oid = function_row.oid),
           pg_catalog.acldefault('f', function_row.proowner)
         )) as acl_row
         where acl_row.grantee = (
           select role_row.oid from pg_catalog.pg_roles as role_row
           where role_row.rolname = 'service_role'
         ) and acl_row.privilege_type = 'EXECUTE'
       ) or exists (
         select 1 from pg_catalog.aclexplode(coalesce(
           (select proc_row.proacl from pg_catalog.pg_proc as proc_row
            where proc_row.oid = function_row.oid),
           pg_catalog.acldefault('f', function_row.proowner)
         )) as acl_row
         where acl_row.privilege_type <> 'EXECUTE'
            or acl_row.grantee not in (
              function_row.proowner,
              (select role_row.oid from pg_catalog.pg_roles as role_row
               where role_row.rolname = 'service_role')
            )
       ) then
      raise exception 'connected-dispatch function authority drifted: %',
        function_row.proname using errcode = '55000';
    end if;
  end loop;

  if (select pg_catalog.count(*)
      from pg_catalog.pg_proc as proc_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = proc_row.pronamespace
      where namespace_row.nspname = 'public'
        and proc_row.proname like 'connected_dispatch_%') <> 9
     or exists (
       select 1 from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid =
         pg_catalog.to_regclass('connected_dispatch_private.execution_outbox')
     ) or exists (
       select 1 from pg_catalog.pg_trigger as trigger_row
       where trigger_row.tgrelid =
         pg_catalog.to_regclass('connected_dispatch_private.execution_outbox')
         and not trigger_row.tgisinternal
     ) or exists (
       select 1 from pg_catalog.pg_rewrite as rule_row
       where rule_row.ev_class =
         pg_catalog.to_regclass('connected_dispatch_private.execution_outbox')
         and rule_row.rulename <> '_RETURN'
     ) or exists (
       select 1 from pg_catalog.pg_publication where puballtables
     ) or exists (
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       where publication_relation.prrelid =
         pg_catalog.to_regclass('connected_dispatch_private.execution_outbox')
     ) then
    raise exception 'connected-dispatch catalog exposure drifted'
      using errcode = '55000';
  end if;
end;
$postflight$;

commit;

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
