begin;

select pg_catalog.set_config('search_path', 'pg_catalog,public', true);
select pg_catalog.set_config('quote_all_identifiers', 'off', true);

-- The public HTTP route authenticates the owner in the application.  This
-- service-role-only database index proves that the requested opaque result ID
-- is the exact encrypted payload settled for that owner's terminal read.  It
-- returns content-free bindings only; ciphertext is opened separately by the
-- reviewed payload vault.
do $preflight$
declare
  predecessor_fingerprint text;
  target_count integer;
  target_fingerprint text;
begin
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
       order by proc_row.proname,
                pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
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
       ',' order by proc_row.proname
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
  )) into predecessor_fingerprint;

  if predecessor_fingerprint <> '192b3c7abb884d47736df936c1820bc9'
     or pg_catalog.obj_description(
       pg_catalog.to_regclass('connected_app_private.read_results'), 'pg_class'
     ) is distinct from
       'ASK_CRUMP_CONNECTED_READ_RESULTS_V1_OPAQUE_ENCRYPTED_REFERENCE_ONLY'
     or pg_catalog.obj_description(
       pg_catalog.to_regclass('connected_app_private.payload_envelopes'), 'pg_class'
     ) is distinct from
       'ASK_CRUMP_CONNECTED_PAYLOAD_ENVELOPES_V1_ENCRYPTED_ONLY' then
    raise exception 'connected owner read-result predecessor drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.count(*) into target_count
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname = 'connected_app_open_read_result_v1';

  if target_count = 0 then
    null;
  elsif target_count = 1 and pg_catalog.to_regprocedure(
    'public.connected_app_open_read_result_v1(uuid,uuid)'
  ) is not null then
    select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
      pg_catalog.pg_get_functiondef(proc_row.oid),
      pg_catalog.obj_description(proc_row.oid, 'pg_proc'),
      pg_catalog.pg_get_userbyid(proc_row.proowner),
      proc_row.prosecdef::text,
      proc_row.provolatile::text,
      proc_row.proconfig::text,
      proc_row.proacl::text
    )) into target_fingerprint
    from pg_catalog.pg_proc as proc_row
    where proc_row.oid = pg_catalog.to_regprocedure(
      'public.connected_app_open_read_result_v1(uuid,uuid)'
    );
    if target_fingerprint <> 'f03f8f3204e5623fd950ad1ffb9fd430' then
      raise exception 'connected owner read-result target drifted'
        using errcode = '55000';
    end if;
  else
    raise exception 'connected owner read-result state is partial or mixed'
      using errcode = '55000';
  end if;
end;
$preflight$;

create or replace function public.connected_app_open_read_result_v1(
  p_owner_id uuid,
  p_result_payload_id uuid
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $fn$
declare
  result_row connected_app_private.read_results%rowtype;
  action_row connected_app_private.action_ledger%rowtype;
  payload_row connected_app_private.payload_envelopes%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_owner_id is null or p_result_payload_id is null then
    raise exception 'connected read-result owner keys are invalid'
      using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);

  select result.* into result_row
  from connected_app_private.read_results as result
  where result.owner_id = p_owner_id
    and result.result_payload_id = p_result_payload_id
  for share;
  if not found then
    return null;
  end if;

  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.owner_id = p_owner_id
    and ledger.operation_id = result_row.operation_id
  for share;
  if not found then
    raise exception 'connected read-result terminal action is absent'
      using errcode = '55000';
  end if;

  select envelope.* into payload_row
  from connected_app_private.payload_envelopes as envelope
  where envelope.owner_id = p_owner_id
    and envelope.payload_id = p_result_payload_id
  for share;
  if not found then
    raise exception 'connected read-result encrypted payload is absent'
      using errcode = '55000';
  end if;

  if result_row.completed_at is null
     or result_row.completed_at > now_at + interval '1 minute'
     or result_row.operation_id <> result_row.action_id
     or action_row.operation_id <> result_row.operation_id
     or action_row.action_id <> result_row.action_id
     or action_row.owner_id <> result_row.owner_id
     or action_row.connection_id <> result_row.connection_id
     or action_row.provider <> result_row.provider
     or action_row.resource <> result_row.resource
     or action_row.action <> result_row.action
     or action_row.mutates_external_state
     or action_row.status <> 'terminal'
     or action_row.terminal_outcome <> 'read'
     or action_row.access_phase <> 'read'
     or action_row.read_consumed_at is null
     or action_row.claim_id <> result_row.claim_id
     or action_row.fencing_token <> result_row.fencing_token
     or action_row.read_use_nonce is distinct from result_row.read_use_nonce
     or action_row.invocation_binding_sha256 <>
       result_row.terminal_binding_sha256
     or action_row.terminal_binding_sha256 <>
       result_row.terminal_binding_sha256
     or action_row.authority_sha256 <> result_row.authority_sha256
     or action_row.idempotency_key_sha256 <>
       result_row.idempotency_key_sha256
     or action_row.terminal_resource_version_sha256 is distinct from
       result_row.resource_version_sha256
     or action_row.observed_at <> result_row.observed_at
     or action_row.terminal_at <> result_row.completed_at
     or result_row.completed_at > now_at + interval '1 minute'
     or payload_row.payload_id <> result_row.result_payload_id
     or payload_row.owner_id <> result_row.owner_id
     or payload_row.connection_id <> result_row.connection_id
     or payload_row.action_id <> result_row.action_id
     or payload_row.provider <> result_row.provider
     or payload_row.action <> result_row.action
     or payload_row.commitment_key_id <>
       result_row.result_commitment_key_id
     or payload_row.payload_sha256 <> result_row.result_payload_sha256
     or payload_row.reference_binding_sha256 <>
       result_row.result_reference_binding_sha256
     or payload_row.created_at < action_row.read_consumed_at
     or payload_row.created_at > result_row.completed_at
     or payload_row.expires_at <= payload_row.created_at
     or payload_row.expires_at > payload_row.created_at + interval '7 days' then
    raise exception 'connected owner read-result binding drifted'
      using errcode = '55000';
  end if;

  return pg_catalog.jsonb_build_object(
    'operation_id', action_row.operation_id,
    'owner_id', action_row.owner_id,
    'task_id', action_row.task_id,
    'turn_id', action_row.turn_id,
    'connection_id', action_row.connection_id,
    'provider', action_row.provider,
    'resource', action_row.resource,
    'action', action_row.action,
    'parameters_sha256', action_row.parameters_sha256,
    'request_resource_version_sha256', action_row.resource_version_sha256,
    'terminal_resource_version_sha256',
      action_row.terminal_resource_version_sha256,
    'invocation_binding_sha256', action_row.invocation_binding_sha256,
    'idempotency_key_sha256', action_row.idempotency_key_sha256,
    'terminal_binding_sha256', action_row.terminal_binding_sha256,
    'authority_sha256', action_row.authority_sha256,
    'observed_at', action_row.observed_at,
    'result_payload_id', result_row.result_payload_id,
    'expires_at', payload_row.expires_at
  );
end;
$fn$;

comment on function public.connected_app_open_read_result_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_OPEN_READ_RESULT_V1_OWNER_BOUND_CONTENT_FREE_INDEX';
alter function public.connected_app_open_read_result_v1(uuid,uuid)
  owner to postgres;
revoke all on function public.connected_app_open_read_result_v1(uuid,uuid)
  from public;
revoke all on function public.connected_app_open_read_result_v1(uuid,uuid)
  from anon;
revoke all on function public.connected_app_open_read_result_v1(uuid,uuid)
  from authenticated;
revoke all on function public.connected_app_open_read_result_v1(uuid,uuid)
  from service_role;
grant execute on function public.connected_app_open_read_result_v1(uuid,uuid)
  to service_role;

do $postflight$
declare
  target_fingerprint text;
  proc_row record;
begin
  select proc.oid, proc.proowner, proc.prosecdef, proc.provolatile,
         proc.proconfig, proc.proacl
  into proc_row
  from pg_catalog.pg_proc as proc
  where proc.oid = pg_catalog.to_regprocedure(
    'public.connected_app_open_read_result_v1(uuid,uuid)'
  );
  if not found
     or pg_catalog.pg_get_userbyid(proc_row.proowner) <> 'postgres'
     or not proc_row.prosecdef
     or proc_row.provolatile <> 'v'
     or proc_row.proconfig is distinct from array['search_path=""']::text[]
     or not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_open_read_result_v1(uuid,uuid)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'anon',
       'public.connected_app_open_read_result_v1(uuid,uuid)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'authenticated',
       'public.connected_app_open_read_result_v1(uuid,uuid)',
       'EXECUTE'
     ) then
    raise exception 'connected owner read-result authority drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    pg_catalog.pg_get_functiondef(proc.oid),
    pg_catalog.obj_description(proc.oid, 'pg_proc'),
    pg_catalog.pg_get_userbyid(proc.proowner),
    proc.prosecdef::text,
    proc.provolatile::text,
    proc.proconfig::text,
    proc.proacl::text
  )) into target_fingerprint
  from pg_catalog.pg_proc as proc
  where proc.oid = pg_catalog.to_regprocedure(
    'public.connected_app_open_read_result_v1(uuid,uuid)'
  );
  if target_fingerprint <> 'f03f8f3204e5623fd950ad1ffb9fd430' then
    raise exception 'connected owner read-result exact target failed'
      using errcode = '55000';
  end if;
end;
$postflight$;

commit;

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
