-- Exactly-once encrypted planning for an authenticated connected-app chat turn.
-- The local release lock remains false; this migration is not applied remotely.

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
select pg_catalog.set_config('quote_all_identifiers', 'off', false);

do $preflight$
declare
  existing_schema oid := pg_catalog.to_regnamespace('connected_plan_private');
  observed_fingerprint text;
begin
  if pg_catalog.to_regclass('public.users') is null
     or pg_catalog.to_regclass('public.sessions') is null
     or pg_catalog.to_regclass('public.chat_jobs') is null
     or pg_catalog.to_regclass('connected_chat_private.turns') is null
     or pg_catalog.to_regclass('connected_app_private.connections') is null
     or pg_catalog.to_regclass('connected_app_private.action_authority') is null
     or pg_catalog.to_regprocedure('connected_app_private.owner_lock_v1(uuid)') is null then
    raise exception 'connected plan-once requires the reviewed chat and connected-app substrate'
      using errcode = '55000';
  end if;
  if existing_schema is null then
    if exists (
      select 1
      from pg_catalog.pg_proc as proc_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = proc_row.pronamespace
      where namespace_row.nspname = 'public'
        and proc_row.proname like 'connected_plan\_%' escape '\'
    ) then
      raise exception 'partial connected plan-once target; refusing repair'
        using errcode = '55000';
    end if;
    return;
  end if;
  if pg_catalog.to_regclass('connected_plan_private.operations') is null
     or pg_catalog.to_regclass('connected_plan_private.envelopes') is null
     or pg_catalog.to_regprocedure('public.connected_plan_begin_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamp with time zone,timestamp with time zone)') is null
     or pg_catalog.to_regprocedure('public.connected_plan_mark_invoked_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamp with time zone,timestamp with time zone,uuid)') is null
     or pg_catalog.to_regprocedure('public.connected_plan_settle_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamp with time zone,timestamp with time zone,uuid,text,uuid,text,text,text,text,text,text)') is null
     or pg_catalog.to_regprocedure('public.connected_plan_fail_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamp with time zone,timestamp with time zone,uuid,text)') is null
     or pg_catalog.to_regprocedure('public.connected_plan_mark_unknown_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamp with time zone,timestamp with time zone,uuid)') is null
     or pg_catalog.to_regprocedure('public.connected_plan_read_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamp with time zone,timestamp with time zone)') is null
     or pg_catalog.to_regprocedure('public.connected_plan_envelope_put_v1(uuid,uuid,uuid,text,uuid,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,text,text,text)') is null
     or pg_catalog.to_regprocedure('public.connected_plan_envelope_read_v1(uuid,uuid,uuid,text,uuid)') is null
     or pg_catalog.to_regprocedure('public.connected_plan_envelope_delete_v1(uuid,uuid,uuid,text,uuid)') is null then
    raise exception 'partial connected plan-once target; refusing repair'
      using errcode = '55000';
  end if;

  with classes as (
    select pg_catalog.jsonb_agg(
      class_row.relkind::text || '|' || class_row.relname
      order by class_row.relkind::text collate pg_catalog."C",
        class_row.relname collate pg_catalog."C"
    ) as value
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_plan_private'
  ), functions as (
    select pg_catalog.jsonb_agg(
      namespace_row.nspname || '|' || proc_row.proname || '|' ||
      pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || '|' ||
      pg_catalog.md5(proc_row.prosrc) || '|' || proc_row.prosecdef::text || '|' ||
      coalesce(proc_row.proconfig::text, '') || '|' || coalesce(proc_row.proacl::text, '')
      order by namespace_row.nspname collate pg_catalog."C",
        proc_row.proname collate pg_catalog."C",
        pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
          collate pg_catalog."C"
    ) as value
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'connected_plan_private'
       or (namespace_row.nspname = 'public'
           and proc_row.proname like 'connected_plan\_%' escape '\')
  ), relations as (
    select pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'name', class_row.relname,
        'owner', pg_catalog.pg_get_userbyid(class_row.relowner),
        'acl', coalesce(class_row.relacl::text, ''),
        'rls', class_row.relrowsecurity,
        'force', class_row.relforcerowsecurity,
        'comment', pg_catalog.obj_description(class_row.oid, 'pg_class'),
        'columns', (
          select pg_catalog.jsonb_agg(
            attribute_row.attname || '|' ||
            pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) || '|' ||
            attribute_row.attnotnull::text || '|' ||
            coalesce(pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid), '')
            order by attribute_row.attnum
          )
          from pg_catalog.pg_attribute as attribute_row
          left join pg_catalog.pg_attrdef as default_row
            on default_row.adrelid = attribute_row.attrelid
           and default_row.adnum = attribute_row.attnum
          where attribute_row.attrelid = class_row.oid
            and attribute_row.attnum > 0 and not attribute_row.attisdropped
        ),
        'constraints', (
          select pg_catalog.jsonb_agg(
            constraint_row.contype::text || '|' ||
            pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
            order by constraint_row.contype::text collate pg_catalog."C",
              pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
                collate pg_catalog."C"
          )
          from pg_catalog.pg_constraint as constraint_row
          where constraint_row.conrelid = class_row.oid
        ),
        'indexes', (
          select pg_catalog.jsonb_agg(
            pg_catalog.pg_get_indexdef(index_row.indexrelid)
            order by pg_catalog.pg_get_indexdef(index_row.indexrelid)
              collate pg_catalog."C"
          )
          from pg_catalog.pg_index as index_row
          where index_row.indrelid = class_row.oid
        )
      ) order by class_row.relname collate pg_catalog."C"
    ) as value
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_plan_private'
      and class_row.relkind in ('r', 'p')
  ), manifest as (
    select pg_catalog.jsonb_build_object(
      'schema_owner', pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      'schema_acl', coalesce(namespace_row.nspacl::text, ''),
      'schema_comment', pg_catalog.obj_description(namespace_row.oid, 'pg_namespace'),
      'classes', classes.value,
      'functions', functions.value,
      'relations', relations.value,
      'policies', (select pg_catalog.count(*) from pg_catalog.pg_policy as policy_row
        join pg_catalog.pg_class as class_row on class_row.oid = policy_row.polrelid
        join pg_catalog.pg_namespace as policy_namespace
          on policy_namespace.oid = class_row.relnamespace
        where policy_namespace.nspname = 'connected_plan_private'),
      'triggers', (select pg_catalog.count(*) from pg_catalog.pg_trigger as trigger_row
        join pg_catalog.pg_class as class_row on class_row.oid = trigger_row.tgrelid
        join pg_catalog.pg_namespace as trigger_namespace
          on trigger_namespace.oid = class_row.relnamespace
        where trigger_namespace.nspname = 'connected_plan_private'
          and not trigger_row.tgisinternal),
      'rules', (select pg_catalog.count(*) from pg_catalog.pg_rewrite as rule_row
        join pg_catalog.pg_class as class_row on class_row.oid = rule_row.ev_class
        join pg_catalog.pg_namespace as rule_namespace
          on rule_namespace.oid = class_row.relnamespace
        where rule_namespace.nspname = 'connected_plan_private'
          and rule_row.rulename <> '_RETURN'),
      'publications', (select pg_catalog.count(*) from pg_catalog.pg_publication_tables
        where schemaname = 'connected_plan_private')
    ) as value
    from pg_catalog.pg_namespace as namespace_row, classes, functions, relations
    where namespace_row.nspname = 'connected_plan_private'
  )
  select pg_catalog.md5(manifest.value::text) into observed_fingerprint from manifest;
  if observed_fingerprint <> 'ef903d32f3d06fc616dea62d477cddd5' then
    raise exception 'connected plan-once target drifted; refusing repair'
      using errcode = '55000';
  end if;
end;
$preflight$;

begin;

create schema if not exists connected_plan_private authorization postgres;
comment on schema connected_plan_private is
  'ASK_CRUMP_CONNECTED_PLAN_ONCE_V1_ENCRYPTED_CONTENT_PRIVATE';
revoke all on schema connected_plan_private from public, anon, authenticated, service_role;

create table if not exists connected_plan_private.operations (
  planning_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  turn_id uuid not null unique references connected_chat_private.turns(turn_id) on delete cascade,
  chat_id uuid not null,
  message_id uuid not null,
  session_id uuid not null,
  claim_token uuid not null,
  origin_session_binding_sha256 text not null
    check (origin_session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  request_binding_sha256 text not null
    check (request_binding_sha256 ~ '^[0-9a-f]{64}$'),
  planning_binding_key_id text not null
    check (planning_binding_key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
  planning_binding_sha256 text not null
    check (planning_binding_sha256 ~ '^[0-9a-f]{64}$'),
  payload_id uuid not null unique,
  state text not null default 'reserved'
    check (state in ('reserved', 'invoked', 'settled', 'failed', 'effect_unknown')),
  invocation_id uuid unique,
  invocation_started_at timestamptz,
  invocation_expires_at timestamptz,
  disposition text check (disposition is null or disposition in ('none','clarify','action','schedule')),
  connection_id uuid references connected_app_private.connections(id),
  provider text check (provider is null or provider in ('google','microsoft')),
  resource text check (resource is null or resource in ('mail','calendar')),
  action text references connected_app_private.action_authority(action),
  payload_commitment_key_id text
    check (payload_commitment_key_id is null or payload_commitment_key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  payload_sha256 text check (payload_sha256 is null or payload_sha256 ~ '^[0-9a-f]{64}$'),
  payload_reference_binding_sha256 text
    check (payload_reference_binding_sha256 is null or payload_reference_binding_sha256 ~ '^[0-9a-f]{64}$'),
  error_code text check (error_code is null or error_code ~ '^[A-Z0-9_]{1,80}$'),
  requested_at timestamptz not null,
  expires_at timestamptz not null,
  settled_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  unique(owner_id, message_id),
  check (expires_at > requested_at and expires_at <= requested_at + interval '30 minutes'),
  check ((state = 'reserved') = (invocation_id is null)),
  check ((invocation_id is null) = (invocation_started_at is null)),
  check ((invocation_id is null) = (invocation_expires_at is null)),
  check ((state = 'settled') = (disposition is not null)),
  check ((state = 'settled') = (payload_commitment_key_id is not null)),
  check ((state = 'settled') = (payload_sha256 is not null)),
  check ((state = 'settled') = (payload_reference_binding_sha256 is not null)),
  check ((state = 'settled') = (settled_at is not null)),
  check ((state in ('failed','effect_unknown')) = (error_code is not null)),
  check (
    (disposition in ('action','schedule')
      and connection_id is not null and provider is not null
      and resource is not null and action is not null)
    or (disposition is null or disposition in ('none','clarify'))
      and connection_id is null and provider is null and resource is null and action is null
  )
);
comment on table connected_plan_private.operations is
  'ASK_CRUMP_CONNECTED_PLAN_OPERATIONS_V1_OPAQUE_BINDINGS_ONLY';
create index if not exists connected_plan_operations_owner_updated_idx
  on connected_plan_private.operations(owner_id, updated_at desc, planning_id);
create index if not exists connected_plan_operations_state_expiry_idx
  on connected_plan_private.operations(state, expires_at, planning_id);
alter table connected_plan_private.operations enable row level security;
alter table connected_plan_private.operations force row level security;
revoke all on table connected_plan_private.operations from public, anon, authenticated, service_role;

create table if not exists connected_plan_private.envelopes (
  payload_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  turn_id uuid not null references connected_chat_private.turns(turn_id) on delete cascade,
  planning_id uuid not null unique references connected_plan_private.operations(planning_id) on delete cascade,
  planning_binding_sha256 text not null
    check (planning_binding_sha256 ~ '^[0-9a-f]{64}$'),
  record_state text not null check (record_state in ('live','deleted')),
  commitment_key_id text
    check (commitment_key_id is null or commitment_key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  payload_sha256 text check (payload_sha256 is null or payload_sha256 ~ '^[0-9a-f]{64}$'),
  reference_binding_sha256 text
    check (reference_binding_sha256 is null or reference_binding_sha256 ~ '^[0-9a-f]{64}$'),
  key_id text check (key_id is null or key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  wrapped_key_nonce text,
  wrapped_key_ciphertext text,
  payload_nonce text,
  payload_ciphertext text,
  record_binding_sha256 text
    check (record_binding_sha256 is null or record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null,
  expires_at timestamptz not null,
  deleted_at timestamptz,
  check (expires_at > created_at and expires_at <= created_at + interval '30 minutes'),
  check (
    (record_state = 'live' and commitment_key_id is not null
      and payload_sha256 is not null and reference_binding_sha256 is not null
      and key_id is not null and wrapped_key_nonce is not null
      and wrapped_key_ciphertext is not null and payload_nonce is not null
      and payload_ciphertext is not null and record_binding_sha256 is not null
      and deleted_at is null)
    or (record_state = 'deleted' and commitment_key_id is null
      and payload_sha256 is null and reference_binding_sha256 is null
      and key_id is null and wrapped_key_nonce is null
      and wrapped_key_ciphertext is null and payload_nonce is null
      and payload_ciphertext is null and record_binding_sha256 is null
      and deleted_at is not null)
  )
);
comment on table connected_plan_private.envelopes is
  'ASK_CRUMP_CONNECTED_PLAN_ENVELOPES_V1_CIPHERTEXT_OR_TOMBSTONE';
create index if not exists connected_plan_envelopes_owner_idx
  on connected_plan_private.envelopes(owner_id, planning_id, payload_id);
create index if not exists connected_plan_envelopes_expiry_idx
  on connected_plan_private.envelopes(record_state, expires_at, payload_id);
alter table connected_plan_private.envelopes enable row level security;
alter table connected_plan_private.envelopes force row level security;
revoke all on table connected_plan_private.envelopes from public, anon, authenticated, service_role;

create or replace function connected_plan_private.operation_view_v1(p_planning_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'state', operation.state,
    'planning_id', operation.planning_id,
    'owner_id', operation.owner_id,
    'turn_id', operation.turn_id,
    'planning_binding_key_id', operation.planning_binding_key_id,
    'planning_binding_sha256', operation.planning_binding_sha256,
    'payload_id', operation.payload_id,
    'invocation_id', operation.invocation_id,
    'invocation_expires_at', operation.invocation_expires_at,
    'disposition', operation.disposition,
    'connection_id', operation.connection_id,
    'provider', operation.provider,
    'resource', operation.resource,
    'action', operation.action,
    'payload_commitment_key_id', operation.payload_commitment_key_id,
    'payload_sha256', operation.payload_sha256,
    'payload_reference_binding_sha256', operation.payload_reference_binding_sha256,
    'error_code', operation.error_code,
    'requested_at', operation.requested_at,
    'expires_at', operation.expires_at,
    'updated_at', operation.updated_at
  )
  from connected_plan_private.operations as operation
  where operation.planning_id = p_planning_id
$fn$;
revoke all on function connected_plan_private.operation_view_v1(uuid)
  from public, anon, authenticated, service_role;

create or replace function connected_plan_private.envelope_view_v1(p_payload_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'payload_id', envelope.payload_id,
    'owner_id', envelope.owner_id,
    'turn_id', envelope.turn_id,
    'planning_id', envelope.planning_id,
    'planning_binding_sha256', envelope.planning_binding_sha256,
    'commitment_key_id', envelope.commitment_key_id,
    'payload_sha256', envelope.payload_sha256,
    'created_at', envelope.created_at,
    'expires_at', envelope.expires_at,
    'key_id', envelope.key_id,
    'wrapped_key_nonce', envelope.wrapped_key_nonce,
    'wrapped_key_ciphertext', envelope.wrapped_key_ciphertext,
    'payload_nonce', envelope.payload_nonce,
    'payload_ciphertext', envelope.payload_ciphertext,
    'record_binding_sha256', envelope.record_binding_sha256
  )
  from connected_plan_private.envelopes as envelope
  where envelope.payload_id = p_payload_id and envelope.record_state = 'live'
$fn$;
revoke all on function connected_plan_private.envelope_view_v1(uuid)
  from public, anon, authenticated, service_role;

create or replace function connected_plan_private.lock_operation_v1(
  p_owner_id uuid, p_session_id uuid, p_chat_id uuid, p_message_id uuid,
  p_turn_id uuid, p_claim_token uuid, p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text, p_planning_id uuid,
  p_planning_binding_key_id text, p_planning_binding_sha256 text,
  p_payload_id uuid, p_requested_at timestamptz, p_expires_at timestamptz
)
returns connected_plan_private.operations
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  session_row public.sessions%rowtype;
  job_row public.chat_jobs%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  operation_row connected_plan_private.operations%rowtype;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select session.* into session_row
  from public.sessions as session
  where session.id = p_session_id and session.user_id = p_owner_id
  for share;
  if not found or session_row.revoked_at is not null or session_row.expires_at <= now_at then
    raise exception 'connected plan session authority changed' using errcode = '55000';
  end if;
  select job.* into job_row
  from public.chat_jobs as job
  where job.user_id = p_owner_id and job.message_id = p_message_id
  for update;
  if not found or job_row.chat_id <> p_chat_id or job_row.status <> 'processing'
     or job_row.claim_token <> p_claim_token then
    raise exception 'connected plan chat claim changed' using errcode = '55000';
  end if;
  select turn.* into turn_row
  from connected_chat_private.turns as turn
  where turn.turn_id = p_turn_id and turn.job_id = job_row.id
  for update;
  if not found or turn_row.owner_id <> p_owner_id or turn_row.chat_id <> p_chat_id
     or turn_row.message_id <> p_message_id
     or turn_row.origin_session_binding_sha256 <> p_origin_session_binding_sha256
     or turn_row.request_binding_sha256 <> p_request_binding_sha256 then
    raise exception 'connected plan turn binding changed' using errcode = '55000';
  end if;
  select operation.* into operation_row
  from connected_plan_private.operations as operation
  where operation.planning_id = p_planning_id
  for update;
  if not found or operation_row.owner_id <> p_owner_id
     or operation_row.turn_id <> p_turn_id or operation_row.chat_id <> p_chat_id
     or operation_row.message_id <> p_message_id
     or operation_row.session_id <> p_session_id
     or operation_row.claim_token <> p_claim_token
     or operation_row.origin_session_binding_sha256 <> p_origin_session_binding_sha256
     or operation_row.request_binding_sha256 <> p_request_binding_sha256
     or operation_row.planning_binding_key_id <> p_planning_binding_key_id
     or operation_row.planning_binding_sha256 <> p_planning_binding_sha256
     or operation_row.payload_id <> p_payload_id
     or operation_row.requested_at <> p_requested_at
     or operation_row.expires_at <> p_expires_at then
    raise exception 'connected plan operation binding changed' using errcode = '55000';
  end if;
  return operation_row;
end;
$fn$;
revoke all on function connected_plan_private.lock_operation_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz)
  from public, anon, authenticated, service_role;

create or replace function public.connected_plan_begin_v1(
  p_owner_id uuid, p_session_id uuid, p_chat_id uuid, p_message_id uuid,
  p_turn_id uuid, p_claim_token uuid, p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text, p_planning_id uuid,
  p_planning_binding_key_id text, p_planning_binding_sha256 text,
  p_payload_id uuid, p_requested_at timestamptz, p_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  session_row public.sessions%rowtype;
  job_row public.chat_jobs%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  operation_row connected_plan_private.operations%rowtype;
begin
  if p_owner_id is null or p_session_id is null or p_chat_id is null
     or p_message_id is null or p_turn_id is null or p_claim_token is null
     or p_planning_id is null or p_payload_id is null
     or p_origin_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_request_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_planning_binding_key_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
     or p_planning_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_requested_at < now_at - interval '5 minutes'
     or p_requested_at > now_at + interval '1 minute'
     or p_expires_at <= now_at or p_expires_at <= p_requested_at
     or p_expires_at > p_requested_at + interval '30 minutes' then
    raise exception 'invalid connected plan bounds' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select session.* into session_row
  from public.sessions as session
  where session.id = p_session_id and session.user_id = p_owner_id
  for share;
  if not found or session_row.revoked_at is not null or session_row.expires_at <= now_at then
    raise exception 'connected plan session authority changed' using errcode = '55000';
  end if;
  select job.* into job_row
  from public.chat_jobs as job
  where job.user_id = p_owner_id and job.message_id = p_message_id
  for update;
  if not found or job_row.chat_id <> p_chat_id or job_row.status <> 'processing'
     or job_row.claim_token <> p_claim_token then
    raise exception 'connected plan chat claim changed' using errcode = '55000';
  end if;
  select turn.* into turn_row
  from connected_chat_private.turns as turn
  where turn.turn_id = p_turn_id and turn.job_id = job_row.id
  for update;
  if not found or turn_row.owner_id <> p_owner_id or turn_row.chat_id <> p_chat_id
     or turn_row.message_id <> p_message_id
     or turn_row.origin_session_binding_sha256 <> p_origin_session_binding_sha256
     or turn_row.request_binding_sha256 <> p_request_binding_sha256 then
    raise exception 'connected plan turn binding changed' using errcode = '55000';
  end if;
  select operation.* into operation_row
  from connected_plan_private.operations as operation
  where operation.planning_id = p_planning_id or operation.turn_id = p_turn_id
  order by operation.planning_id
  limit 1
  for update;
  if found then
    if operation_row.planning_id <> p_planning_id
       or operation_row.owner_id <> p_owner_id or operation_row.turn_id <> p_turn_id
       or operation_row.chat_id <> p_chat_id or operation_row.message_id <> p_message_id
       or operation_row.session_id <> p_session_id
       or operation_row.claim_token <> p_claim_token
       or operation_row.origin_session_binding_sha256 <> p_origin_session_binding_sha256
       or operation_row.request_binding_sha256 <> p_request_binding_sha256
       or operation_row.planning_binding_key_id <> p_planning_binding_key_id
       or operation_row.planning_binding_sha256 <> p_planning_binding_sha256
       or operation_row.payload_id <> p_payload_id
       or operation_row.requested_at <> p_requested_at
       or operation_row.expires_at <> p_expires_at then
      raise exception 'connected plan replay drifted' using errcode = '55000';
    end if;
    return connected_plan_private.operation_view_v1(p_planning_id);
  end if;
  if turn_row.planning_id is not null or turn_row.stage <> 'claimed' then
    raise exception 'connected plan turn already advanced' using errcode = '55000';
  end if;
  insert into connected_plan_private.operations(
    planning_id, owner_id, turn_id, chat_id, message_id,
    session_id, claim_token,
    origin_session_binding_sha256, request_binding_sha256,
    planning_binding_key_id, planning_binding_sha256, payload_id,
    state, requested_at, expires_at, created_at, updated_at
  ) values (
    p_planning_id, p_owner_id, p_turn_id, p_chat_id, p_message_id,
    p_session_id, p_claim_token,
    p_origin_session_binding_sha256, p_request_binding_sha256,
    p_planning_binding_key_id, p_planning_binding_sha256, p_payload_id,
    'reserved', p_requested_at, p_expires_at, now_at, now_at
  );
  update connected_chat_private.turns as turn
  set stage = 'planning', planning_id = p_planning_id,
      planning_binding_sha256 = p_planning_binding_sha256, updated_at = now_at
  where turn.turn_id = p_turn_id;
  return connected_plan_private.operation_view_v1(p_planning_id);
end;
$fn$;
comment on function public.connected_plan_begin_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz) is
  'ASK_CRUMP_CONNECTED_PLAN_BEGIN_V1_LIVE_SESSION_CHAT_CLAIM_BOUND';

create or replace function public.connected_plan_mark_invoked_v1(
  p_owner_id uuid, p_session_id uuid, p_chat_id uuid, p_message_id uuid,
  p_turn_id uuid, p_claim_token uuid, p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text, p_planning_id uuid,
  p_planning_binding_key_id text, p_planning_binding_sha256 text,
  p_payload_id uuid, p_requested_at timestamptz, p_expires_at timestamptz,
  p_invocation_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  operation_row connected_plan_private.operations%rowtype;
  permitted boolean := false;
begin
  if p_invocation_id is null then
    raise exception 'invalid connected plan invocation' using errcode = '22023';
  end if;
  operation_row := connected_plan_private.lock_operation_v1(
    p_owner_id, p_session_id, p_chat_id, p_message_id, p_turn_id, p_claim_token,
    p_origin_session_binding_sha256, p_request_binding_sha256, p_planning_id,
    p_planning_binding_key_id, p_planning_binding_sha256, p_payload_id,
    p_requested_at, p_expires_at
  );
  if operation_row.expires_at <= now_at then
    raise exception 'connected plan expired' using errcode = '55000';
  end if;
  if operation_row.state = 'reserved' then
    update connected_plan_private.operations as operation
    set state = 'invoked', invocation_id = p_invocation_id,
        invocation_started_at = now_at,
        invocation_expires_at = case
          when now_at + interval '45 seconds' < expires_at
            then now_at + interval '45 seconds'
          else expires_at
        end,
        updated_at = now_at
    where operation.planning_id = p_planning_id;
    permitted := true;
  elsif operation_row.state = 'invoked' then
    if operation_row.invocation_id <> p_invocation_id then
      raise exception 'connected plan invocation drifted' using errcode = '55000';
    end if;
  else
    raise exception 'connected plan is not invokable' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'record', connected_plan_private.operation_view_v1(p_planning_id),
    'invoke_permitted', permitted
  );
end;
$fn$;
comment on function public.connected_plan_mark_invoked_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid) is
  'ASK_CRUMP_CONNECTED_PLAN_INVOKE_V1_ONE_WINNER_NO_RETRY';

create or replace function public.connected_plan_settle_v1(
  p_owner_id uuid, p_session_id uuid, p_chat_id uuid, p_message_id uuid,
  p_turn_id uuid, p_claim_token uuid, p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text, p_planning_id uuid,
  p_planning_binding_key_id text, p_planning_binding_sha256 text,
  p_payload_id uuid, p_requested_at timestamptz, p_expires_at timestamptz,
  p_invocation_id uuid, p_disposition text, p_connection_id uuid,
  p_provider text, p_resource text, p_action text,
  p_payload_commitment_key_id text, p_payload_sha256 text,
  p_payload_reference_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  operation_row connected_plan_private.operations%rowtype;
  envelope_row connected_plan_private.envelopes%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  if p_invocation_id is null
     or p_disposition not in ('none','clarify','action','schedule')
     or p_payload_commitment_key_id !~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
     or p_payload_sha256 !~ '^[0-9a-f]{64}$'
     or p_payload_reference_binding_sha256 !~ '^[0-9a-f]{64}$'
     or ((p_disposition in ('action','schedule')) <>
       (p_connection_id is not null and p_provider is not null
        and p_resource is not null and p_action is not null)) then
    raise exception 'invalid connected plan settlement' using errcode = '22023';
  end if;
  operation_row := connected_plan_private.lock_operation_v1(
    p_owner_id, p_session_id, p_chat_id, p_message_id, p_turn_id, p_claim_token,
    p_origin_session_binding_sha256, p_request_binding_sha256, p_planning_id,
    p_planning_binding_key_id, p_planning_binding_sha256, p_payload_id,
    p_requested_at, p_expires_at
  );
  if operation_row.state = 'settled' then
    if operation_row.invocation_id <> p_invocation_id
       or operation_row.disposition <> p_disposition
       or operation_row.connection_id is distinct from p_connection_id
       or operation_row.provider is distinct from p_provider
       or operation_row.resource is distinct from p_resource
       or operation_row.action is distinct from p_action
       or operation_row.payload_commitment_key_id <> p_payload_commitment_key_id
       or operation_row.payload_sha256 <> p_payload_sha256
       or operation_row.payload_reference_binding_sha256
          <> p_payload_reference_binding_sha256 then
      raise exception 'connected plan settlement replay drifted' using errcode = '55000';
    end if;
    return connected_plan_private.operation_view_v1(p_planning_id);
  end if;
  if operation_row.state <> 'invoked' or operation_row.invocation_id <> p_invocation_id
     or operation_row.expires_at <= now_at then
    raise exception 'connected plan is not settleable' using errcode = '55000';
  end if;
  select envelope.* into envelope_row
  from connected_plan_private.envelopes as envelope
  where envelope.payload_id = p_payload_id
  for update;
  if not found or envelope_row.record_state <> 'live'
     or envelope_row.owner_id <> p_owner_id or envelope_row.turn_id <> p_turn_id
     or envelope_row.planning_id <> p_planning_id
     or envelope_row.planning_binding_sha256 <> p_planning_binding_sha256
     or envelope_row.commitment_key_id <> p_payload_commitment_key_id
     or envelope_row.payload_sha256 <> p_payload_sha256
     or envelope_row.reference_binding_sha256 <> p_payload_reference_binding_sha256
     or envelope_row.expires_at <= now_at then
    raise exception 'connected plan envelope binding changed' using errcode = '55000';
  end if;
  if p_disposition in ('action','schedule') then
    select connection.* into connection_row
    from connected_app_private.connections as connection
    where connection.id = p_connection_id and connection.owner_id = p_owner_id
    for share;
    if not found or connection_row.authorization_state <> 'active'
       or connection_row.revoked_at is not null
       or (connection_row.authorization_expires_at is not null
           and connection_row.authorization_expires_at <= now_at)
       or connection_row.provider <> p_provider or connection_row.resource <> p_resource
       or connection_row.granted_actions is null
       or not (p_action = any(connection_row.granted_actions))
       or not exists (
         select 1 from connected_app_private.action_authority as catalog
         where catalog.action = p_action and catalog.resource = p_resource
       ) then
      raise exception 'connected plan authority changed' using errcode = '55000';
    end if;
  end if;
  update connected_plan_private.operations as operation
  set state = 'settled', disposition = p_disposition,
      connection_id = p_connection_id, provider = p_provider,
      resource = p_resource, action = p_action,
      payload_commitment_key_id = p_payload_commitment_key_id,
      payload_sha256 = p_payload_sha256,
      payload_reference_binding_sha256 = p_payload_reference_binding_sha256,
      settled_at = now_at, updated_at = now_at
  where operation.planning_id = p_planning_id;
  update connected_chat_private.turns as turn
  set stage = 'planned', plan_payload_id = p_payload_id,
      plan_payload_sha256 = p_payload_sha256,
      plan_reference_binding_sha256 = p_payload_reference_binding_sha256,
      updated_at = now_at
  where turn.turn_id = p_turn_id;
  return connected_plan_private.operation_view_v1(p_planning_id);
end;
$fn$;
comment on function public.connected_plan_settle_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid,text,uuid,text,text,text,text,text,text) is
  'ASK_CRUMP_CONNECTED_PLAN_SETTLE_V1_ENCRYPTED_REF_CURRENT_AUTHORITY';

create or replace function public.connected_plan_fail_v1(
  p_owner_id uuid, p_session_id uuid, p_chat_id uuid, p_message_id uuid,
  p_turn_id uuid, p_claim_token uuid, p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text, p_planning_id uuid,
  p_planning_binding_key_id text, p_planning_binding_sha256 text,
  p_payload_id uuid, p_requested_at timestamptz, p_expires_at timestamptz,
  p_invocation_id uuid, p_error_code text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  operation_row connected_plan_private.operations%rowtype;
begin
  if p_invocation_id is null or p_error_code !~ '^[A-Z0-9_]{1,80}$' then
    raise exception 'invalid connected plan failure' using errcode = '22023';
  end if;
  operation_row := connected_plan_private.lock_operation_v1(
    p_owner_id, p_session_id, p_chat_id, p_message_id, p_turn_id, p_claim_token,
    p_origin_session_binding_sha256, p_request_binding_sha256, p_planning_id,
    p_planning_binding_key_id, p_planning_binding_sha256, p_payload_id,
    p_requested_at, p_expires_at
  );
  if operation_row.state = 'failed' then
    if operation_row.invocation_id <> p_invocation_id
       or operation_row.error_code <> p_error_code then
      raise exception 'connected plan failure replay drifted' using errcode = '55000';
    end if;
    return connected_plan_private.operation_view_v1(p_planning_id);
  end if;
  if operation_row.state <> 'invoked' or operation_row.invocation_id <> p_invocation_id then
    raise exception 'connected plan is not failable' using errcode = '55000';
  end if;
  update connected_plan_private.operations as operation
  set state = 'failed', error_code = p_error_code, updated_at = now_at
  where operation.planning_id = p_planning_id;
  return connected_plan_private.operation_view_v1(p_planning_id);
end;
$fn$;
comment on function public.connected_plan_fail_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid,text) is
  'ASK_CRUMP_CONNECTED_PLAN_FAIL_V1_NO_AUTOMATIC_REINVOKE';

create or replace function public.connected_plan_mark_unknown_v1(
  p_owner_id uuid, p_session_id uuid, p_chat_id uuid, p_message_id uuid,
  p_turn_id uuid, p_claim_token uuid, p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text, p_planning_id uuid,
  p_planning_binding_key_id text, p_planning_binding_sha256 text,
  p_payload_id uuid, p_requested_at timestamptz, p_expires_at timestamptz,
  p_invocation_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  operation_row connected_plan_private.operations%rowtype;
begin
  operation_row := connected_plan_private.lock_operation_v1(
    p_owner_id, p_session_id, p_chat_id, p_message_id, p_turn_id, p_claim_token,
    p_origin_session_binding_sha256, p_request_binding_sha256, p_planning_id,
    p_planning_binding_key_id, p_planning_binding_sha256, p_payload_id,
    p_requested_at, p_expires_at
  );
  if operation_row.state = 'effect_unknown' then
    if operation_row.invocation_id <> p_invocation_id then
      raise exception 'connected plan unknown replay drifted' using errcode = '55000';
    end if;
    return connected_plan_private.operation_view_v1(p_planning_id);
  end if;
  if operation_row.state <> 'invoked' or operation_row.invocation_id <> p_invocation_id
     or operation_row.invocation_expires_at > now_at then
    raise exception 'connected plan ambiguity is not recoverable yet' using errcode = '55000';
  end if;
  if exists (
    select 1 from connected_plan_private.envelopes as envelope
    where envelope.payload_id = p_payload_id and envelope.record_state = 'live'
  ) then
    raise exception 'connected plan encrypted result requires settlement' using errcode = '55000';
  end if;
  update connected_plan_private.operations as operation
  set state = 'effect_unknown', error_code = 'MODEL_EFFECT_UNKNOWN', updated_at = now_at
  where operation.planning_id = p_planning_id;
  update connected_chat_private.turns as turn
  set stage = 'effect_unknown', updated_at = now_at
  where turn.turn_id = p_turn_id;
  return connected_plan_private.operation_view_v1(p_planning_id);
end;
$fn$;
comment on function public.connected_plan_mark_unknown_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid) is
  'ASK_CRUMP_CONNECTED_PLAN_UNKNOWN_V1_LEASE_EXPIRED_NO_ENVELOPE';

create or replace function public.connected_plan_read_v1(
  p_owner_id uuid, p_session_id uuid, p_chat_id uuid, p_message_id uuid,
  p_turn_id uuid, p_claim_token uuid, p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text, p_planning_id uuid,
  p_planning_binding_key_id text, p_planning_binding_sha256 text,
  p_payload_id uuid, p_requested_at timestamptz, p_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  operation_row connected_plan_private.operations%rowtype;
begin
  operation_row := connected_plan_private.lock_operation_v1(
    p_owner_id, p_session_id, p_chat_id, p_message_id, p_turn_id, p_claim_token,
    p_origin_session_binding_sha256, p_request_binding_sha256, p_planning_id,
    p_planning_binding_key_id, p_planning_binding_sha256, p_payload_id,
    p_requested_at, p_expires_at
  );
  return connected_plan_private.operation_view_v1(p_planning_id);
exception when no_data_found then
  return null;
end;
$fn$;
comment on function public.connected_plan_read_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz) is
  'ASK_CRUMP_CONNECTED_PLAN_READ_V1_LIVE_SESSION_CURRENT_CLAIM_BOUND';

create or replace function public.connected_plan_envelope_put_v1(
  p_owner_id uuid, p_turn_id uuid, p_planning_id uuid,
  p_planning_binding_sha256 text, p_payload_id uuid,
  p_commitment_key_id text, p_payload_sha256 text,
  p_reference_binding_sha256 text, p_created_at timestamptz,
  p_expires_at timestamptz, p_key_id text,
  p_wrapped_key_nonce text, p_wrapped_key_ciphertext text,
  p_payload_nonce text, p_payload_ciphertext text,
  p_record_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  operation_row connected_plan_private.operations%rowtype;
  envelope_row connected_plan_private.envelopes%rowtype;
begin
  if p_owner_id is null or p_turn_id is null or p_planning_id is null
     or p_payload_id is null
     or p_planning_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_commitment_key_id !~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
     or p_payload_sha256 !~ '^[0-9a-f]{64}$'
     or p_reference_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_key_id !~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
     or p_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_wrapped_key_nonce !~ '^[A-Za-z0-9_-]{16}$'
     or length(p_wrapped_key_ciphertext) not between 64 and 120
     or p_wrapped_key_ciphertext !~ '^[A-Za-z0-9_-]+$'
     or p_payload_nonce !~ '^[A-Za-z0-9_-]{16}$'
     or length(p_payload_ciphertext) not between 23 and 90000
     or p_payload_ciphertext !~ '^[A-Za-z0-9_-]+$'
     or p_created_at > now_at + interval '1 minute'
     or p_expires_at <= now_at or p_expires_at <= p_created_at
     or p_expires_at > p_created_at + interval '30 minutes' then
    raise exception 'invalid connected plan envelope' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select operation.* into operation_row
  from connected_plan_private.operations as operation
  where operation.planning_id = p_planning_id
  for update;
  if not found or operation_row.owner_id <> p_owner_id
     or operation_row.turn_id <> p_turn_id
     or operation_row.planning_binding_sha256 <> p_planning_binding_sha256
     or operation_row.payload_id <> p_payload_id
     or operation_row.state <> 'invoked'
     or operation_row.requested_at <> p_created_at
     or operation_row.expires_at <> p_expires_at then
    raise exception 'connected plan envelope authority changed' using errcode = '55000';
  end if;
  select envelope.* into envelope_row
  from connected_plan_private.envelopes as envelope
  where envelope.payload_id = p_payload_id
  for update;
  if found then
    if envelope_row.owner_id <> p_owner_id or envelope_row.turn_id <> p_turn_id
       or envelope_row.planning_id <> p_planning_id
       or envelope_row.planning_binding_sha256 <> p_planning_binding_sha256 then
      raise exception 'connected plan envelope identity drifted' using errcode = '55000';
    end if;
    if envelope_row.record_state = 'deleted' then
      return null;
    end if;
    -- Randomized envelope encryption deliberately produces different
    -- ciphertext on a replay.  Return the first immutable record for the same
    -- exact identity; the vault decrypts it and constant-time compares the
    -- keyed plaintext commitment before accepting the replay.  This also
    -- permits a safe retry across wrapping/commitment-key rotation.
    if envelope_row.created_at <> p_created_at
       or envelope_row.expires_at <> p_expires_at then
      raise exception 'connected plan envelope replay drifted' using errcode = '55000';
    end if;
    return connected_plan_private.envelope_view_v1(p_payload_id);
  end if;
  insert into connected_plan_private.envelopes(
    payload_id, owner_id, turn_id, planning_id, planning_binding_sha256,
    record_state, commitment_key_id, payload_sha256,
    reference_binding_sha256, key_id, wrapped_key_nonce,
    wrapped_key_ciphertext, payload_nonce, payload_ciphertext,
    record_binding_sha256, created_at, expires_at
  ) values (
    p_payload_id, p_owner_id, p_turn_id, p_planning_id,
    p_planning_binding_sha256, 'live', p_commitment_key_id,
    p_payload_sha256, p_reference_binding_sha256, p_key_id,
    p_wrapped_key_nonce, p_wrapped_key_ciphertext, p_payload_nonce,
    p_payload_ciphertext, p_record_binding_sha256, p_created_at, p_expires_at
  );
  return connected_plan_private.envelope_view_v1(p_payload_id);
end;
$fn$;
comment on function public.connected_plan_envelope_put_v1(uuid,uuid,uuid,text,uuid,text,text,text,timestamptz,timestamptz,text,text,text,text,text,text) is
  'ASK_CRUMP_CONNECTED_PLAN_ENVELOPE_PUT_V1_CIPHERTEXT_ONLY_PUT_ONCE';

create or replace function public.connected_plan_envelope_read_v1(
  p_owner_id uuid, p_turn_id uuid, p_planning_id uuid,
  p_planning_binding_sha256 text, p_payload_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  operation_row connected_plan_private.operations%rowtype;
  envelope_row connected_plan_private.envelopes%rowtype;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select operation.* into operation_row
  from connected_plan_private.operations as operation
  where operation.planning_id = p_planning_id
  for share;
  if not found or operation_row.owner_id <> p_owner_id
     or operation_row.turn_id <> p_turn_id
     or operation_row.planning_binding_sha256 <> p_planning_binding_sha256
     or operation_row.payload_id <> p_payload_id
     or operation_row.state not in ('invoked','settled') then
    return null;
  end if;
  select envelope.* into envelope_row
  from connected_plan_private.envelopes as envelope
  where envelope.payload_id = p_payload_id
  for share;
  if not found or envelope_row.record_state <> 'live'
     or envelope_row.owner_id <> p_owner_id or envelope_row.turn_id <> p_turn_id
     or envelope_row.planning_id <> p_planning_id
     or envelope_row.planning_binding_sha256 <> p_planning_binding_sha256 then
    return null;
  end if;
  return connected_plan_private.envelope_view_v1(p_payload_id);
end;
$fn$;
comment on function public.connected_plan_envelope_read_v1(uuid,uuid,uuid,text,uuid) is
  'ASK_CRUMP_CONNECTED_PLAN_ENVELOPE_READ_V1_EXACT_OPERATION_BINDING';

create or replace function public.connected_plan_envelope_delete_v1(
  p_owner_id uuid, p_turn_id uuid, p_planning_id uuid,
  p_planning_binding_sha256 text, p_payload_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  operation_row connected_plan_private.operations%rowtype;
  envelope_row connected_plan_private.envelopes%rowtype;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select operation.* into operation_row
  from connected_plan_private.operations as operation
  where operation.planning_id = p_planning_id
  for update;
  if not found or operation_row.owner_id <> p_owner_id
     or operation_row.turn_id <> p_turn_id
     or operation_row.planning_binding_sha256 <> p_planning_binding_sha256
     or operation_row.payload_id <> p_payload_id then
    raise exception 'connected plan envelope deletion authority changed' using errcode = '55000';
  end if;
  select envelope.* into envelope_row
  from connected_plan_private.envelopes as envelope
  where envelope.payload_id = p_payload_id
  for update;
  if found then
    if envelope_row.owner_id <> p_owner_id or envelope_row.turn_id <> p_turn_id
       or envelope_row.planning_id <> p_planning_id
       or envelope_row.planning_binding_sha256 <> p_planning_binding_sha256 then
      raise exception 'connected plan envelope deletion drifted' using errcode = '55000';
    end if;
    if envelope_row.record_state = 'deleted' then
      return true;
    end if;
    update connected_plan_private.envelopes as envelope
    set record_state = 'deleted', commitment_key_id = null,
        payload_sha256 = null, reference_binding_sha256 = null,
        key_id = null, wrapped_key_nonce = null,
        wrapped_key_ciphertext = null, payload_nonce = null,
        payload_ciphertext = null, record_binding_sha256 = null,
        deleted_at = now_at
    where envelope.payload_id = p_payload_id;
    return true;
  end if;
  insert into connected_plan_private.envelopes(
    payload_id, owner_id, turn_id, planning_id, planning_binding_sha256,
    record_state, created_at, expires_at, deleted_at
  ) values (
    p_payload_id, p_owner_id, p_turn_id, p_planning_id,
    p_planning_binding_sha256, 'deleted', operation_row.requested_at,
    operation_row.expires_at, now_at
  );
  return true;
end;
$fn$;
comment on function public.connected_plan_envelope_delete_v1(uuid,uuid,uuid,text,uuid) is
  'ASK_CRUMP_CONNECTED_PLAN_ENVELOPE_DELETE_V1_PERMANENT_TOMBSTONE';

revoke all on function public.connected_plan_begin_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz)
  from public, anon, authenticated;
revoke all on function public.connected_plan_mark_invoked_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid)
  from public, anon, authenticated;
revoke all on function public.connected_plan_settle_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid,text,uuid,text,text,text,text,text,text)
  from public, anon, authenticated;
revoke all on function public.connected_plan_fail_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid,text)
  from public, anon, authenticated;
revoke all on function public.connected_plan_mark_unknown_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid)
  from public, anon, authenticated;
revoke all on function public.connected_plan_read_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz)
  from public, anon, authenticated;
revoke all on function public.connected_plan_envelope_put_v1(uuid,uuid,uuid,text,uuid,text,text,text,timestamptz,timestamptz,text,text,text,text,text,text)
  from public, anon, authenticated;
revoke all on function public.connected_plan_envelope_read_v1(uuid,uuid,uuid,text,uuid)
  from public, anon, authenticated;
revoke all on function public.connected_plan_envelope_delete_v1(uuid,uuid,uuid,text,uuid)
  from public, anon, authenticated;

grant execute on function public.connected_plan_begin_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz)
  to service_role;
grant execute on function public.connected_plan_mark_invoked_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid)
  to service_role;
grant execute on function public.connected_plan_settle_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid,text,uuid,text,text,text,text,text,text)
  to service_role;
grant execute on function public.connected_plan_fail_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid,text)
  to service_role;
grant execute on function public.connected_plan_mark_unknown_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz,uuid)
  to service_role;
grant execute on function public.connected_plan_read_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamptz,timestamptz)
  to service_role;
grant execute on function public.connected_plan_envelope_put_v1(uuid,uuid,uuid,text,uuid,text,text,text,timestamptz,timestamptz,text,text,text,text,text,text)
  to service_role;
grant execute on function public.connected_plan_envelope_read_v1(uuid,uuid,uuid,text,uuid)
  to service_role;
grant execute on function public.connected_plan_envelope_delete_v1(uuid,uuid,uuid,text,uuid)
  to service_role;

do $postflight$
declare
  operation_oid oid := pg_catalog.to_regclass('connected_plan_private.operations');
  envelope_oid oid := pg_catalog.to_regclass('connected_plan_private.envelopes');
begin
  if operation_oid is null or envelope_oid is null
     or pg_catalog.pg_get_userbyid(
       (select namespace_row.nspowner from pg_catalog.pg_namespace as namespace_row
        where namespace_row.nspname = 'connected_plan_private')
     ) <> 'postgres'
     or not (select class_row.relrowsecurity and class_row.relforcerowsecurity
             from pg_catalog.pg_class as class_row where class_row.oid = operation_oid)
     or not (select class_row.relrowsecurity and class_row.relforcerowsecurity
             from pg_catalog.pg_class as class_row where class_row.oid = envelope_oid)
     or exists (select 1 from pg_catalog.pg_policy as policy_row
                where policy_row.polrelid in (operation_oid, envelope_oid))
     or exists (select 1 from pg_catalog.pg_trigger as trigger_row
                where trigger_row.tgrelid in (operation_oid, envelope_oid)
                  and not trigger_row.tgisinternal)
     or exists (select 1 from pg_catalog.pg_rewrite as rule_row
                where rule_row.ev_class in (operation_oid, envelope_oid)
                  and rule_row.rulename <> '_RETURN')
     or exists (select 1 from pg_catalog.pg_publication_tables
                where schemaname = 'connected_plan_private') then
    raise exception 'connected plan-once postflight failed' using errcode = '55000';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname like 'connected_plan\_%' escape '\'
      and (not proc_row.prosecdef
        or proc_row.proconfig is distinct from array['search_path=""']::text[]
        or pg_catalog.has_function_privilege('public', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('anon', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('authenticated', proc_row.oid, 'EXECUTE')
        or not pg_catalog.has_function_privilege('service_role', proc_row.oid, 'EXECUTE'))
  ) then
    raise exception 'connected plan-once function authority drifted' using errcode = '55000';
  end if;
end;
$postflight$;

commit;
