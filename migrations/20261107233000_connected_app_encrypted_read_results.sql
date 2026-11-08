begin;

select pg_catalog.set_config('search_path', 'pg_catalog,public', true);
select pg_catalog.set_config('quote_all_identifiers', 'off', true);

-- This migration accepts only the exact encrypted-store predecessor or this
-- exact target.  A partial/mixed/drifted state is refused before mutation.
-- Reviewed predecessor scoped catalog fingerprint:
-- 9c752ba79dc1b9b695d89f57fc17078d
do $preflight$
declare
  target_relations integer;
  target_functions integer;
  predecessor_fingerprint text;
  target_fingerprint text;
begin
  select pg_catalog.count(*) into target_relations
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_app_private'
    and class_row.relname = 'read_results';

  select pg_catalog.count(*) into target_functions
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname in (
      'connected_app_settle_read_result_v1',
      'connected_app_read_read_result_v1'
    );

  if target_relations = 0 and target_functions = 0 then
    select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
      pg_catalog.obj_description(
        pg_catalog.to_regclass('connected_app_private.action_ledger'), 'pg_class'
      ),
      pg_catalog.obj_description(
        pg_catalog.to_regclass('connected_app_private.payload_envelopes'), 'pg_class'
      ),
      (select pg_catalog.string_agg(
         attribute_row.attname || ':'
           || pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod)
           || ':' || attribute_row.attnotnull::text,
         ',' order by attribute_row.attnum
       )
       from pg_catalog.pg_attribute as attribute_row
       where attribute_row.attrelid =
         pg_catalog.to_regclass('connected_app_private.action_ledger')
         and attribute_row.attnum > 0 and not attribute_row.attisdropped),
      (select pg_catalog.string_agg(
         attribute_row.attname || ':'
           || pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod)
           || ':' || attribute_row.attnotnull::text,
         ',' order by attribute_row.attnum
       )
       from pg_catalog.pg_attribute as attribute_row
       where attribute_row.attrelid =
         pg_catalog.to_regclass('connected_app_private.payload_envelopes')
         and attribute_row.attnum > 0 and not attribute_row.attisdropped),
      (select pg_catalog.string_agg(
         constraint_row.conname || ':'
           || pg_catalog.pg_get_constraintdef(constraint_row.oid, true),
         ',' order by constraint_row.conname collate pg_catalog."C"
       )
       from pg_catalog.pg_constraint as constraint_row
       where constraint_row.conrelid in (
         pg_catalog.to_regclass('connected_app_private.action_ledger'),
         pg_catalog.to_regclass('connected_app_private.payload_envelopes')
       )),
      pg_catalog.pg_get_functiondef(
        pg_catalog.to_regprocedure('connected_app_private.owner_lock_v1(uuid)')
      ),
      pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure(
        'public.connected_app_consume_credential_lease_v1(uuid,uuid,uuid,uuid,text,uuid,bigint,text,uuid,timestamptz,bigint,text,text,text,text,bigint)'
      )),
      pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure(
        'public.connected_app_settle_action_v1(uuid,uuid,uuid,uuid,uuid,boolean,text,text,text,text,timestamptz)'
      )),
      pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure(
        'public.connected_app_payload_reference_get_v1(uuid,uuid,uuid,uuid,text,text)'
      )),
      (select pg_catalog.string_agg(
         authority.action,
         ',' order by authority.action collate pg_catalog."C"
       )
       from connected_app_private.action_authority as authority)
    )) into predecessor_fingerprint;

    if predecessor_fingerprint <> '9c752ba79dc1b9b695d89f57fc17078d'
       or pg_catalog.obj_description(
         pg_catalog.to_regclass('connected_app_private.payload_envelopes'), 'pg_class'
       ) is distinct from 'ASK_CRUMP_CONNECTED_PAYLOAD_ENVELOPES_V1_ENCRYPTED_ONLY'
       or pg_catalog.col_description(
         pg_catalog.to_regclass('connected_app_private.action_ledger'),
         (select attribute_row.attnum
          from pg_catalog.pg_attribute as attribute_row
          where attribute_row.attrelid =
            pg_catalog.to_regclass('connected_app_private.action_ledger')
            and attribute_row.attname = 'parameters_sha256')
       ) is distinct from
         'ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PAYLOAD_COMMITMENT_V1_NOT_PLAINTEXT_REQUEST_DIGEST'
       or pg_catalog.to_regprocedure(
         'public.connected_app_payload_reference_get_v1(uuid,uuid,uuid,uuid,text,text)'
       ) is null then
      raise exception 'connected-app encrypted read-result predecessor drifted'
        using errcode = '55000';
    end if;
  elsif target_relations = 1 and target_functions = 2 then
    select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
      pg_catalog.obj_description(
        pg_catalog.to_regclass('connected_app_private.read_results'), 'pg_class'
      ),
      (select pg_catalog.string_agg(
         attribute_row.attname || ':'
           || pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod)
           || ':' || attribute_row.attnotnull::text,
         ',' order by attribute_row.attnum
       ) from pg_catalog.pg_attribute as attribute_row
       where attribute_row.attrelid =
         pg_catalog.to_regclass('connected_app_private.read_results')
         and attribute_row.attnum > 0 and not attribute_row.attisdropped),
      (select pg_catalog.string_agg(
         constraint_row.conname || ':'
           || pg_catalog.pg_get_constraintdef(constraint_row.oid, true),
         ',' order by constraint_row.conname collate pg_catalog."C"
       ) from pg_catalog.pg_constraint as constraint_row
       where constraint_row.conrelid =
         pg_catalog.to_regclass('connected_app_private.read_results')),
      (select pg_catalog.string_agg(
         index_row.relname || ':' || pg_catalog.pg_get_indexdef(index_row.oid),
         ',' order by index_row.relname collate pg_catalog."C"
       ) from pg_catalog.pg_index as index_meta
       join pg_catalog.pg_class as index_row on index_row.oid = index_meta.indexrelid
       where index_meta.indrelid =
         pg_catalog.to_regclass('connected_app_private.read_results')),
      pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure(
        'public.connected_app_settle_read_result_v1(uuid,uuid,uuid,uuid,uuid,text,text,text,uuid,text,text,text,text,text,text,uuid,bigint,uuid,timestamptz,text)'
      )),
      pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure(
        'public.connected_app_read_read_result_v1(uuid,uuid,uuid,text)'
      )),
      pg_catalog.obj_description(pg_catalog.to_regprocedure(
        'public.connected_app_settle_read_result_v1(uuid,uuid,uuid,uuid,uuid,text,text,text,uuid,text,text,text,text,text,text,uuid,bigint,uuid,timestamptz,text)'
      ), 'pg_proc'),
      pg_catalog.obj_description(pg_catalog.to_regprocedure(
        'public.connected_app_read_read_result_v1(uuid,uuid,uuid,text)'
      ), 'pg_proc')
    )) into target_fingerprint;

    if target_fingerprint <> '98e077727ddee102f6effd4e78e11b78'
       or pg_catalog.obj_description(
         pg_catalog.to_regclass('connected_app_private.read_results'), 'pg_class'
       ) is distinct from
         'ASK_CRUMP_CONNECTED_READ_RESULTS_V1_OPAQUE_ENCRYPTED_REFERENCE_ONLY' then
      raise exception 'connected-app encrypted read-result target drifted'
        using errcode = '55000';
    end if;
  else
    raise exception 'connected-app encrypted read-result state is partial or mixed'
      using errcode = '55000';
  end if;
end;
$preflight$;

create table if not exists connected_app_private.read_results (
  completion_id uuid primary key,
  operation_id uuid not null unique,
  action_id uuid not null,
  owner_id uuid not null,
  connection_id uuid not null,
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  action text not null check (action in (
    'mail.search', 'mail.get', 'calendar.list', 'calendar.get',
    'calendar.free_busy'
  )),
  result_payload_id uuid not null unique,
  result_commitment_key_id text not null
    check (result_commitment_key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  result_payload_sha256 text not null
    check (result_payload_sha256 ~ '^[0-9a-f]{64}$'),
  result_reference_binding_sha256 text not null
    check (result_reference_binding_sha256 ~ '^[0-9a-f]{64}$'),
  terminal_binding_sha256 text not null
    check (terminal_binding_sha256 ~ '^[0-9a-f]{64}$'),
  authority_sha256 text not null check (authority_sha256 ~ '^[0-9a-f]{64}$'),
  idempotency_key_sha256 text not null
    check (idempotency_key_sha256 ~ '^[0-9a-f]{64}$'),
  claim_id uuid not null,
  fencing_token bigint not null check (fencing_token >= 1),
  read_use_nonce uuid not null,
  observed_at timestamptz not null,
  resource_version_sha256 text
    check (resource_version_sha256 is null or resource_version_sha256 ~ '^[0-9a-f]{64}$'),
  completed_at timestamptz not null,
  constraint connected_read_result_operation_action_same
    check (operation_id = action_id),
  constraint connected_read_result_action_resource_shape check (
    (resource = 'mail' and action in ('mail.search', 'mail.get'))
    or (resource = 'calendar' and action in (
      'calendar.list', 'calendar.get', 'calendar.free_busy'
    ))
  ),
  constraint connected_read_result_time_shape check (completed_at >= observed_at),
  constraint connected_read_result_action_fk foreign key (operation_id)
    references connected_app_private.action_ledger(operation_id) on delete cascade,
  constraint connected_read_result_owner_fk foreign key (owner_id)
    references public.users(id) on delete cascade,
  constraint connected_read_result_connection_fk foreign key (owner_id, connection_id)
    references connected_app_private.connections(owner_id, id) on delete cascade,
  constraint connected_read_result_payload_fk foreign key (result_payload_id)
    references connected_app_private.payload_envelopes(payload_id) on delete cascade
);
comment on table connected_app_private.read_results is
  'ASK_CRUMP_CONNECTED_READ_RESULTS_V1_OPAQUE_ENCRYPTED_REFERENCE_ONLY';
create index if not exists connected_read_results_owner_fk_idx
  on connected_app_private.read_results(owner_id, connection_id, operation_id);
create index if not exists connected_read_results_action_fk_idx
  on connected_app_private.read_results(action, operation_id);

alter table connected_app_private.read_results enable row level security;
alter table connected_app_private.read_results force row level security;

create or replace function public.connected_app_settle_read_result_v1(
  p_completion_id uuid,
  p_operation_id uuid,
  p_action_id uuid,
  p_owner_id uuid,
  p_connection_id uuid,
  p_provider text,
  p_resource text,
  p_action text,
  p_result_payload_id uuid,
  p_result_commitment_key_id text,
  p_result_payload_sha256 text,
  p_result_reference_binding_sha256 text,
  p_terminal_binding_sha256 text,
  p_authority_sha256 text,
  p_idempotency_key_sha256 text,
  p_claim_id uuid,
  p_fencing_token bigint,
  p_read_use_nonce uuid,
  p_observed_at timestamptz,
  p_resource_version_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  action_row connected_app_private.action_ledger%rowtype;
  payload_row connected_app_private.payload_envelopes%rowtype;
  result_row connected_app_private.read_results%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_completion_id is null or p_operation_id is null or p_action_id is null
     or p_owner_id is null or p_connection_id is null or p_result_payload_id is null
     or p_claim_id is null or p_read_use_nonce is null or p_observed_at is null
     or p_operation_id <> p_action_id
     or p_provider not in ('google', 'microsoft')
     or p_resource not in ('mail', 'calendar')
     or p_action not in (
       'mail.search', 'mail.get', 'calendar.list', 'calendar.get',
       'calendar.free_busy'
     )
     or not (
       (p_resource = 'mail' and p_action in ('mail.search', 'mail.get'))
       or (p_resource = 'calendar' and p_action in (
         'calendar.list', 'calendar.get', 'calendar.free_busy'
       ))
     )
     or p_result_commitment_key_id is null
     or p_result_commitment_key_id !~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
     or p_result_payload_sha256 is null
     or p_result_payload_sha256 !~ '^[0-9a-f]{64}$'
     or p_result_reference_binding_sha256 is null
     or p_result_reference_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_terminal_binding_sha256 is null
     or p_terminal_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_authority_sha256 is null or p_authority_sha256 !~ '^[0-9a-f]{64}$'
     or p_idempotency_key_sha256 is null
     or p_idempotency_key_sha256 !~ '^[0-9a-f]{64}$'
     or p_fencing_token is null or p_fencing_token < 1
     or (
       p_resource_version_sha256 is not null
       and p_resource_version_sha256 !~ '^[0-9a-f]{64}$'
     ) then
    raise exception 'invalid encrypted read-result settlement'
      using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id and ledger.owner_id = p_owner_id
  for update;
  if not found then
    raise exception 'read action not found' using errcode = '55000';
  end if;

  select payload.* into payload_row
  from connected_app_private.payload_envelopes as payload
  where payload.payload_id = p_result_payload_id
  for update;
  if not found then
    raise exception 'encrypted read-result payload not found' using errcode = '55000';
  end if;

  select result.* into result_row
  from connected_app_private.read_results as result
  where result.operation_id = p_operation_id
     or result.completion_id = p_completion_id
     or result.result_payload_id = p_result_payload_id
  for update;

  if action_row.status = 'terminal' then
    if action_row.terminal_outcome = 'read'
       and found
       and result_row.completion_id = p_completion_id
       and result_row.operation_id = p_operation_id
       and result_row.action_id = p_action_id
       and result_row.owner_id = p_owner_id
       and result_row.connection_id = p_connection_id
       and result_row.provider = p_provider
       and result_row.resource = p_resource
       and result_row.action = p_action
       and result_row.result_payload_id = p_result_payload_id
       and result_row.result_commitment_key_id = p_result_commitment_key_id
       and result_row.result_payload_sha256 = p_result_payload_sha256
       and result_row.result_reference_binding_sha256 =
         p_result_reference_binding_sha256
       and result_row.terminal_binding_sha256 = p_terminal_binding_sha256
       and result_row.authority_sha256 = p_authority_sha256
       and result_row.idempotency_key_sha256 = p_idempotency_key_sha256
       and result_row.claim_id = p_claim_id
       and result_row.fencing_token = p_fencing_token
       and result_row.read_use_nonce = p_read_use_nonce
       and result_row.observed_at = p_observed_at
       and result_row.resource_version_sha256 is not distinct from
         p_resource_version_sha256
       and action_row.terminal_binding_sha256 = p_terminal_binding_sha256
       and action_row.authority_sha256 = p_authority_sha256
       and action_row.idempotency_key_sha256 = p_idempotency_key_sha256 then
      return pg_catalog.jsonb_build_object(
        'status', 'terminal', 'record', pg_catalog.to_jsonb(result_row)
      );
    end if;
    raise exception 'encrypted read-result terminal replay drifted'
      using errcode = '55000';
  end if;

  if found then
    raise exception 'encrypted read-result identity collision'
      using errcode = '55000';
  end if;

  if action_row.action_id <> p_action_id
     or action_row.connection_id <> p_connection_id
     or action_row.provider <> p_provider
     or action_row.resource <> p_resource
     or action_row.action <> p_action
     or action_row.mutates_external_state
     or action_row.status <> 'access_granted'
     or action_row.access_phase <> 'read'
     or action_row.claim_id <> p_claim_id
     or action_row.fencing_token <> p_fencing_token
     or action_row.read_use_nonce is distinct from p_read_use_nonce
     or action_row.read_consumed_at is null
     or action_row.authority_sha256 <> p_authority_sha256
     or action_row.idempotency_key_sha256 <> p_idempotency_key_sha256
     or action_row.execution_deadline < p_observed_at
     or action_row.access_started_at is null
     or p_observed_at < action_row.access_started_at
     or p_observed_at < action_row.read_consumed_at
     or p_observed_at > now_at + interval '1 minute' then
    raise exception 'encrypted read-result action fence mismatch'
      using errcode = '55000';
  end if;

  if payload_row.owner_id <> p_owner_id
     or payload_row.connection_id <> p_connection_id
     or payload_row.action_id <> p_action_id
     or payload_row.provider <> p_provider
     or payload_row.action <> p_action
     or payload_row.commitment_key_id <> p_result_commitment_key_id
     or payload_row.payload_sha256 <> p_result_payload_sha256
     or payload_row.reference_binding_sha256 <>
       p_result_reference_binding_sha256
     or payload_row.created_at < action_row.read_consumed_at
     or payload_row.created_at > now_at + interval '1 minute'
     or payload_row.expires_at <= now_at then
    raise exception 'encrypted read-result payload fence mismatch'
      using errcode = '55000';
  end if;

  insert into connected_app_private.read_results (
    completion_id, operation_id, action_id, owner_id, connection_id,
    provider, resource, action, result_payload_id,
    result_commitment_key_id, result_payload_sha256,
    result_reference_binding_sha256, terminal_binding_sha256,
    authority_sha256, idempotency_key_sha256, claim_id, fencing_token,
    read_use_nonce, observed_at, resource_version_sha256, completed_at
  ) values (
    p_completion_id, p_operation_id, p_action_id, p_owner_id, p_connection_id,
    p_provider, p_resource, p_action, p_result_payload_id,
    p_result_commitment_key_id, p_result_payload_sha256,
    p_result_reference_binding_sha256, p_terminal_binding_sha256,
    p_authority_sha256, p_idempotency_key_sha256, p_claim_id, p_fencing_token,
    p_read_use_nonce, p_observed_at, p_resource_version_sha256, now_at
  ) returning * into result_row;

  update connected_app_private.action_ledger as ledger
  set status = 'terminal', terminal_outcome = 'read',
      terminal_binding_sha256 = p_terminal_binding_sha256,
      provider_request_id_sha256 = null,
      provider_resource_id_sha256 = null,
      observed_at = p_observed_at,
      postobserve_impossible = false,
      terminal_at = now_at,
      updated_at = now_at
  where ledger.operation_id = p_operation_id
    and ledger.status = 'access_granted'
    and ledger.claim_id = p_claim_id
    and ledger.fencing_token = p_fencing_token
    and ledger.read_use_nonce = p_read_use_nonce;
  if not found then
    raise exception 'encrypted read-result settlement lost its fence'
      using errcode = '55000';
  end if;

  return pg_catalog.jsonb_build_object(
    'status', 'terminal', 'record', pg_catalog.to_jsonb(result_row)
  );
end;
$fn$;
comment on function public.connected_app_settle_read_result_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,text,uuid,text,text,text,text,text,text,
  uuid,bigint,uuid,timestamptz,text
) is 'ASK_CRUMP_CONNECTED_APP_SETTLE_READ_RESULT_V1_ATOMIC_TERMINAL_OPAQUE_REF';

create or replace function public.connected_app_read_read_result_v1(
  p_owner_id uuid,
  p_operation_id uuid,
  p_completion_id uuid,
  p_idempotency_key_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  action_row connected_app_private.action_ledger%rowtype;
  result_row connected_app_private.read_results%rowtype;
begin
  if p_owner_id is null or p_operation_id is null or p_completion_id is null
     or p_idempotency_key_sha256 is null
     or p_idempotency_key_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'encrypted read-result readback keys are invalid'
      using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id and ledger.owner_id = p_owner_id
  for share;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'absent', 'record', null);
  end if;
  if action_row.idempotency_key_sha256 <> p_idempotency_key_sha256
     or action_row.mutates_external_state then
    raise exception 'encrypted read-result readback binding drifted'
      using errcode = '55000';
  end if;

  select result.* into result_row
  from connected_app_private.read_results as result
  where result.operation_id = p_operation_id
     or result.completion_id = p_completion_id;

  if action_row.status = 'terminal' then
    if action_row.terminal_outcome <> 'read'
       or not found
       or result_row.completion_id <> p_completion_id
       or result_row.owner_id <> p_owner_id
       or result_row.idempotency_key_sha256 <> p_idempotency_key_sha256
       or result_row.terminal_binding_sha256 <>
         action_row.terminal_binding_sha256
       or result_row.authority_sha256 <> action_row.authority_sha256 then
      raise exception 'encrypted read-result terminal invariant drifted'
        using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'status', 'terminal', 'record', pg_catalog.to_jsonb(result_row)
    );
  end if;

  if found then
    raise exception 'encrypted read-result appeared before terminal settlement'
      using errcode = '55000';
  end if;
  if action_row.status = 'claimed' then
    return pg_catalog.jsonb_build_object(
      'status', 'not_consumed', 'record', null
    );
  end if;
  if action_row.status = 'access_granted' and action_row.access_phase = 'read' then
    return pg_catalog.jsonb_build_object(
      'status',
      case when action_row.read_consumed_at is null
        then 'not_consumed' else 'consumed_unknown' end,
      'record', null
    );
  end if;
  raise exception 'encrypted read-result action state is invalid'
    using errcode = '55000';
end;
$fn$;
comment on function public.connected_app_read_read_result_v1(
  uuid,uuid,uuid,text
) is 'ASK_CRUMP_CONNECTED_APP_READ_READ_RESULT_V1_CONTENT_FREE_RECOVERY';

alter table connected_app_private.read_results owner to postgres;
revoke all on table connected_app_private.read_results from public;
revoke all on table connected_app_private.read_results from anon;
revoke all on table connected_app_private.read_results from authenticated;
revoke all on table connected_app_private.read_results from service_role;

alter function public.connected_app_settle_read_result_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,text,uuid,text,text,text,text,text,text,
  uuid,bigint,uuid,timestamptz,text
) owner to postgres;
alter function public.connected_app_read_read_result_v1(
  uuid,uuid,uuid,text
) owner to postgres;
revoke all on function public.connected_app_settle_read_result_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,text,uuid,text,text,text,text,text,text,
  uuid,bigint,uuid,timestamptz,text
) from public;
revoke all on function public.connected_app_settle_read_result_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,text,uuid,text,text,text,text,text,text,
  uuid,bigint,uuid,timestamptz,text
) from anon;
revoke all on function public.connected_app_settle_read_result_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,text,uuid,text,text,text,text,text,text,
  uuid,bigint,uuid,timestamptz,text
) from authenticated;
revoke all on function public.connected_app_settle_read_result_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,text,uuid,text,text,text,text,text,text,
  uuid,bigint,uuid,timestamptz,text
) from service_role;
grant execute on function public.connected_app_settle_read_result_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,text,uuid,text,text,text,text,text,text,
  uuid,bigint,uuid,timestamptz,text
) to service_role;
revoke all on function public.connected_app_read_read_result_v1(
  uuid,uuid,uuid,text
) from public;
revoke all on function public.connected_app_read_read_result_v1(
  uuid,uuid,uuid,text
) from anon;
revoke all on function public.connected_app_read_read_result_v1(
  uuid,uuid,uuid,text
) from authenticated;
revoke all on function public.connected_app_read_read_result_v1(
  uuid,uuid,uuid,text
) from service_role;
grant execute on function public.connected_app_read_read_result_v1(
  uuid,uuid,uuid,text
) to service_role;

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
  where namespace_row.nspname = 'connected_app_private'
    and class_row.relname = 'read_results';
  if not found
     or pg_catalog.pg_get_userbyid(relation_row.relowner) <> 'postgres'
     or not relation_row.relrowsecurity or not relation_row.relforcerowsecurity
     or exists (
       select 1 from pg_catalog.aclexplode(
         coalesce(
           (select class_row.relacl from pg_catalog.pg_class as class_row
            where class_row.oid = relation_row.oid),
           pg_catalog.acldefault('r', relation_row.relowner)
         )
       ) as acl_row
       where acl_row.grantee <> relation_row.relowner
     ) then
    raise exception 'connected-app read-result table authority drifted'
      using errcode = '55000';
  end if;

  for function_row in
    select proc_row.oid, proc_row.proname, proc_row.proowner,
           proc_row.prosecdef, proc_row.proconfig
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname in (
        'connected_app_settle_read_result_v1',
        'connected_app_read_read_result_v1'
      )
  loop
    if pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
       or not function_row.prosecdef
       or function_row.proconfig is distinct from array['search_path=""']::text[]
       or not exists (
         select 1 from pg_catalog.aclexplode(
           coalesce(
             (select proc_row.proacl from pg_catalog.pg_proc as proc_row
              where proc_row.oid = function_row.oid),
             pg_catalog.acldefault('f', function_row.proowner)
           )
         ) as acl_row
         where acl_row.grantee = (
           select role_row.oid from pg_catalog.pg_roles as role_row
           where role_row.rolname = 'service_role'
         ) and acl_row.privilege_type = 'EXECUTE'
       ) or exists (
         select 1 from pg_catalog.aclexplode(
           coalesce(
             (select proc_row.proacl from pg_catalog.pg_proc as proc_row
              where proc_row.oid = function_row.oid),
             pg_catalog.acldefault('f', function_row.proowner)
           )
         ) as acl_row
         where acl_row.privilege_type <> 'EXECUTE'
            or acl_row.grantee not in (
              function_row.proowner,
              (select role_row.oid from pg_catalog.pg_roles as role_row
               where role_row.rolname = 'service_role')
            )
       ) then
      raise exception 'connected-app read-result function authority drifted: %',
        function_row.proname using errcode = '55000';
    end if;
  end loop;

  if exists (
    select 1 from pg_catalog.pg_policy as policy_row
    where policy_row.polrelid =
      pg_catalog.to_regclass('connected_app_private.read_results')
  ) or exists (
    select 1 from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid =
      pg_catalog.to_regclass('connected_app_private.read_results')
      and not trigger_row.tgisinternal
  ) or exists (
    select 1 from pg_catalog.pg_rewrite as rule_row
    where rule_row.ev_class =
      pg_catalog.to_regclass('connected_app_private.read_results')
      and rule_row.rulename <> '_RETURN'
  ) or exists (
    select 1 from pg_catalog.pg_publication where puballtables
  ) or exists (
    select 1 from pg_catalog.pg_publication_rel as publication_relation
    where publication_relation.prrelid =
      pg_catalog.to_regclass('connected_app_private.read_results')
  ) then
    raise exception 'connected-app read-result exposure drifted'
      using errcode = '55000';
  end if;
end;
$postflight$;

commit;

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
