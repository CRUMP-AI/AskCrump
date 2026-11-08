-- Restart-safe OAuth authorization authority and encrypted exchange-permit custody.
-- The connected-app source release lock remains false. This migration is local only.

begin;

select pg_catalog.set_config('search_path', 'pg_catalog,public', true);
select pg_catalog.set_config('quote_all_identifiers', 'off', true);

do $preflight$
declare
  target_columns integer;
  target_relations integer;
  target_functions integer;
  observed_fingerprint text;
  predecessor_fingerprint text;
begin
  if pg_catalog.to_regclass('connected_app_private.connections') is null
     or pg_catalog.to_regclass('connected_app_private.oauth_flows') is null
     or pg_catalog.to_regclass('connected_app_private.oauth_exchange_permits') is null
     or pg_catalog.to_regclass('connected_app_private.credential_cleanup_outbox') is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null then
    raise exception 'connected OAuth runtime authority predecessor is absent'
      using errcode = '55000';
  end if;

  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    (select pg_catalog.string_agg(
       namespace_row.nspname || '|' || proc_row.proname || '|' ||
       pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || '|' ||
       language_row.lanname || '|' || proc_row.provolatile::text || '|' ||
       proc_row.prosecdef::text || '|' || coalesce(proc_row.proconfig::text, '') || '|' ||
       pg_catalog.pg_get_userbyid(proc_row.proowner) || '|' ||
       pg_catalog.md5(proc_row.prosrc) || '|' ||
       coalesce(pg_catalog.obj_description(proc_row.oid, 'pg_proc'), ''),
       E'\n' order by namespace_row.nspname collate pg_catalog."C",
         proc_row.proname collate pg_catalog."C",
         pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
           collate pg_catalog."C"
     )
     from pg_catalog.pg_proc as proc_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = proc_row.pronamespace
     join pg_catalog.pg_language as language_row
       on language_row.oid = proc_row.prolang
     where (namespace_row.nspname = 'public' and proc_row.proname in (
       'connected_app_get_binding_v1',
       'connected_app_oauth_consume_pending_v1',
       'connected_app_oauth_consume_permit_v1',
       'connected_app_oauth_create_pending_v1',
       'connected_app_oauth_finalize_v1',
       'connected_app_oauth_issue_permit_v1',
       'connected_app_record_credential_cleanup_v1'
     )) or (namespace_row.nspname = 'connected_app_private'
       and proc_row.proname = 'owner_lock_v1')),
    (select pg_catalog.string_agg(
       attribute_row.attrelid::pg_catalog.regclass::text || '|' ||
       attribute_row.attname || '|' ||
       pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) || '|' ||
       attribute_row.attnotnull::text || '|' ||
       coalesce(pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid), ''),
       E'\n' order by attribute_row.attrelid::pg_catalog.regclass::text
         collate pg_catalog."C",
         attribute_row.attnum
     )
     from pg_catalog.pg_attribute as attribute_row
     left join pg_catalog.pg_attrdef as default_row
       on default_row.adrelid = attribute_row.attrelid
      and default_row.adnum = attribute_row.attnum
     where attribute_row.attrelid in (
       pg_catalog.to_regclass('connected_app_private.connections'),
       pg_catalog.to_regclass('connected_app_private.oauth_flows'),
       pg_catalog.to_regclass('connected_app_private.oauth_exchange_permits'),
       pg_catalog.to_regclass('connected_app_private.credential_cleanup_outbox')
     ) and attribute_row.attnum > 0 and not attribute_row.attisdropped
       and attribute_row.attname not in (
         'authorization_issued_at', 'completion_authorization_issued_at'
       )),
    (select pg_catalog.string_agg(
       constraint_row.conrelid::pg_catalog.regclass::text || '|' ||
       constraint_row.conname || '|' ||
       pg_catalog.pg_get_constraintdef(constraint_row.oid, true),
       E'\n' order by constraint_row.conrelid::pg_catalog.regclass::text
         collate pg_catalog."C",
         constraint_row.conname collate pg_catalog."C"
     )
     from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid in (
       pg_catalog.to_regclass('connected_app_private.connections'),
       pg_catalog.to_regclass('connected_app_private.oauth_flows'),
       pg_catalog.to_regclass('connected_app_private.oauth_exchange_permits'),
       pg_catalog.to_regclass('connected_app_private.credential_cleanup_outbox')
     ) and constraint_row.conname not in (
       'connected_app_connections_authorization_issued_check',
       'connected_app_oauth_completion_issued_check'
     )),
    (select pg_catalog.string_agg(
       index_row.indrelid::pg_catalog.regclass::text || '|' ||
       pg_catalog.pg_get_indexdef(index_row.indexrelid),
       E'\n' order by index_row.indrelid::pg_catalog.regclass::text
         collate pg_catalog."C",
         index_row.indexrelid::pg_catalog.regclass::text
           collate pg_catalog."C"
     )
     from pg_catalog.pg_index as index_row
     where index_row.indrelid in (
       pg_catalog.to_regclass('connected_app_private.connections'),
       pg_catalog.to_regclass('connected_app_private.oauth_flows'),
       pg_catalog.to_regclass('connected_app_private.oauth_exchange_permits'),
       pg_catalog.to_regclass('connected_app_private.credential_cleanup_outbox')
     )),
    (select pg_catalog.string_agg(
       class_row.oid::pg_catalog.regclass::text || '|' ||
       pg_catalog.pg_get_userbyid(class_row.relowner) || '|' ||
       coalesce(class_row.relacl::text, '') || '|' ||
       class_row.relrowsecurity::text || '|' || class_row.relforcerowsecurity::text || '|' ||
       coalesce(pg_catalog.obj_description(class_row.oid, 'pg_class'), ''),
       E'\n' order by class_row.oid::pg_catalog.regclass::text
         collate pg_catalog."C"
     )
     from pg_catalog.pg_class as class_row
     where class_row.oid in (
       pg_catalog.to_regclass('connected_app_private.connections'),
       pg_catalog.to_regclass('connected_app_private.oauth_flows'),
       pg_catalog.to_regclass('connected_app_private.oauth_exchange_permits'),
       pg_catalog.to_regclass('connected_app_private.credential_cleanup_outbox')
     )),
    (select pg_catalog.string_agg(
       policy_row.polrelid::pg_catalog.regclass::text || '|' || policy_row.polname || '|' ||
       policy_row.polcmd::text || '|' || policy_row.polpermissive::text || '|' ||
       coalesce(pg_catalog.pg_get_expr(policy_row.polqual, policy_row.polrelid), '') || '|' ||
       coalesce(pg_catalog.pg_get_expr(policy_row.polwithcheck, policy_row.polrelid), ''),
       E'\n' order by policy_row.polrelid::pg_catalog.regclass::text
         collate pg_catalog."C",
         policy_row.polname collate pg_catalog."C"
     )
     from pg_catalog.pg_policy as policy_row
     where policy_row.polrelid in (
       pg_catalog.to_regclass('connected_app_private.connections'),
       pg_catalog.to_regclass('connected_app_private.oauth_flows'),
       pg_catalog.to_regclass('connected_app_private.oauth_exchange_permits'),
       pg_catalog.to_regclass('connected_app_private.credential_cleanup_outbox')
     )),
    (select pg_catalog.string_agg(
       trigger_row.tgrelid::pg_catalog.regclass::text || '|' ||
       pg_catalog.pg_get_triggerdef(trigger_row.oid, true),
       E'\n' order by trigger_row.tgrelid::pg_catalog.regclass::text
         collate pg_catalog."C",
         trigger_row.tgname collate pg_catalog."C"
     )
     from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid in (
       pg_catalog.to_regclass('connected_app_private.connections'),
       pg_catalog.to_regclass('connected_app_private.oauth_flows'),
       pg_catalog.to_regclass('connected_app_private.oauth_exchange_permits'),
       pg_catalog.to_regclass('connected_app_private.credential_cleanup_outbox')
     ) and not trigger_row.tgisinternal),
    (select pg_catalog.string_agg(
       rule_row.ev_class::pg_catalog.regclass::text || '|' ||
       pg_catalog.pg_get_ruledef(rule_row.oid, true),
       E'\n' order by rule_row.ev_class::pg_catalog.regclass::text
         collate pg_catalog."C",
         rule_row.rulename collate pg_catalog."C"
     )
     from pg_catalog.pg_rewrite as rule_row
     where rule_row.ev_class in (
       pg_catalog.to_regclass('connected_app_private.connections'),
       pg_catalog.to_regclass('connected_app_private.oauth_flows'),
       pg_catalog.to_regclass('connected_app_private.oauth_exchange_permits'),
       pg_catalog.to_regclass('connected_app_private.credential_cleanup_outbox')
     ) and rule_row.rulename <> '_RETURN'),
    (select pg_catalog.count(*)::text from pg_catalog.pg_publication_tables
     where schemaname = 'connected_app_private' and tablename in (
       'connections', 'oauth_flows', 'oauth_exchange_permits',
       'credential_cleanup_outbox'
     ))
  )) into predecessor_fingerprint;
  if predecessor_fingerprint <> 'b370daab7379a1e09a620719948d6699' then
    raise exception 'connected OAuth runtime authority predecessor drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.count(*) into target_columns
  from pg_catalog.pg_attribute as attribute_row
  where ((attribute_row.attrelid = pg_catalog.to_regclass(
           'connected_app_private.connections'
         ) and attribute_row.attname = 'authorization_issued_at')
     or (attribute_row.attrelid = pg_catalog.to_regclass(
           'connected_app_private.oauth_flows'
         ) and attribute_row.attname = 'completion_authorization_issued_at'))
    and attribute_row.attnum > 0 and not attribute_row.attisdropped;

  select pg_catalog.count(*) into target_relations
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_app_private'
    and class_row.relname = 'oauth_permit_capability_custody'
    and class_row.relkind = 'r';

  select pg_catalog.count(*) into target_functions
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname in (
      'connected_app_get_binding_v2',
      'connected_app_oauth_revalidate_flow_v2',
      'connected_app_oauth_read_consumption_v2',
      'connected_app_oauth_put_permit_capability_v2',
      'connected_app_oauth_read_permit_capability_v2',
      'connected_app_oauth_consume_permit_v2',
      'connected_app_oauth_finalize_v2',
      'connected_app_oauth_read_completion_v2',
      'connected_app_read_credential_cleanup_v2'
    );

  if target_columns = 0 and target_relations = 0 and target_functions = 0 then
    return;
  end if;
  if target_columns <> 2 or target_relations <> 1 or target_functions <> 9 then
    raise exception 'connected OAuth runtime authority target is partial or mixed'
      using errcode = '55000';
  end if;

  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    (select pg_catalog.string_agg(
       attribute_row.attrelid::pg_catalog.regclass::text || '|' ||
       attribute_row.attname || '|' ||
       pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) || '|' ||
       attribute_row.attnotnull::text,
       E'\n' order by attribute_row.attrelid::pg_catalog.regclass::text
         collate pg_catalog."C",
         attribute_row.attname collate pg_catalog."C"
     )
     from pg_catalog.pg_attribute as attribute_row
     where attribute_row.attnum > 0 and not attribute_row.attisdropped
       and ((attribute_row.attrelid = pg_catalog.to_regclass(
               'connected_app_private.connections'
             ) and attribute_row.attname = 'authorization_issued_at')
         or (attribute_row.attrelid = pg_catalog.to_regclass(
               'connected_app_private.oauth_flows'
             ) and attribute_row.attname = 'completion_authorization_issued_at'))),
    (select pg_catalog.string_agg(
       attribute_row.attname || '|' ||
       pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) || '|' ||
       attribute_row.attnotnull::text || '|' ||
       coalesce(pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid), ''),
       E'\n' order by attribute_row.attnum
     )
     from pg_catalog.pg_attribute as attribute_row
     left join pg_catalog.pg_attrdef as default_row
       on default_row.adrelid = attribute_row.attrelid
      and default_row.adnum = attribute_row.attnum
     where attribute_row.attrelid = pg_catalog.to_regclass(
             'connected_app_private.oauth_permit_capability_custody'
           )
       and attribute_row.attnum > 0 and not attribute_row.attisdropped),
    (select pg_catalog.string_agg(
       constraint_row.conname || '|' ||
       pg_catalog.pg_get_constraintdef(constraint_row.oid, true),
       E'\n' order by constraint_row.conname collate pg_catalog."C"
     )
     from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = pg_catalog.to_regclass(
             'connected_app_private.oauth_permit_capability_custody'
           )
        or (constraint_row.conrelid = pg_catalog.to_regclass(
              'connected_app_private.connections'
            ) and constraint_row.conname =
              'connected_app_connections_authorization_issued_check')
        or (constraint_row.conrelid = pg_catalog.to_regclass(
              'connected_app_private.oauth_flows'
            ) and constraint_row.conname =
              'connected_app_oauth_completion_issued_check')),
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
         'connected_app_get_binding_v2',
         'connected_app_oauth_revalidate_flow_v2',
         'connected_app_oauth_read_consumption_v2',
         'connected_app_oauth_put_permit_capability_v2',
         'connected_app_oauth_read_permit_capability_v2',
         'connected_app_oauth_consume_permit_v2',
         'connected_app_oauth_finalize_v2',
         'connected_app_oauth_read_completion_v2',
         'connected_app_read_credential_cleanup_v2'
       )),
    (select coalesce(class_row.relacl::text, '') || '|' ||
            pg_catalog.pg_get_userbyid(class_row.relowner) || '|' ||
            class_row.relrowsecurity::text || '|' ||
            class_row.relforcerowsecurity::text || '|' ||
            coalesce(pg_catalog.obj_description(class_row.oid, 'pg_class'), '')
     from pg_catalog.pg_class as class_row
     where class_row.oid = pg_catalog.to_regclass(
       'connected_app_private.oauth_permit_capability_custody'
     )),
    (select pg_catalog.string_agg(
       proc_row.proname || '|' ||
       pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || '|' ||
       pg_catalog.pg_get_userbyid(proc_row.proowner) || '|' ||
       coalesce(proc_row.proacl::text, '') || '|' ||
       coalesce(pg_catalog.obj_description(proc_row.oid, 'pg_proc'), ''),
       E'\n' order by proc_row.proname collate pg_catalog."C",
         pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
           collate pg_catalog."C"
     )
     from pg_catalog.pg_proc as proc_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = proc_row.pronamespace
     where namespace_row.nspname = 'public'
       and proc_row.proname in (
         'connected_app_get_binding_v2',
         'connected_app_oauth_revalidate_flow_v2',
         'connected_app_oauth_read_consumption_v2',
         'connected_app_oauth_put_permit_capability_v2',
         'connected_app_oauth_read_permit_capability_v2',
         'connected_app_oauth_consume_permit_v2',
         'connected_app_oauth_finalize_v2',
         'connected_app_oauth_read_completion_v2',
         'connected_app_read_credential_cleanup_v2',
         'connected_app_oauth_finalize_v1',
         'connected_app_oauth_issue_permit_v1'
       )),
    (select pg_catalog.count(*)::text from pg_catalog.pg_policy as policy_row
     where policy_row.polrelid = pg_catalog.to_regclass(
       'connected_app_private.oauth_permit_capability_custody'
     )),
    (select pg_catalog.count(*)::text from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid = pg_catalog.to_regclass(
       'connected_app_private.oauth_permit_capability_custody'
     ) and not trigger_row.tgisinternal),
    (select pg_catalog.count(*)::text from pg_catalog.pg_rewrite as rule_row
     where rule_row.ev_class = pg_catalog.to_regclass(
       'connected_app_private.oauth_permit_capability_custody'
     ) and rule_row.rulename <> '_RETURN'),
    (select pg_catalog.count(*)::text from pg_catalog.pg_publication_tables
     where schemaname = 'connected_app_private'
       and tablename = 'oauth_permit_capability_custody')
  )) into observed_fingerprint;
  if observed_fingerprint <> 'cfd262b61a4f8c408b74b2ca18d97d8d' then
    raise exception 'connected OAuth runtime authority target drifted'
      using errcode = '55000';
  end if;
  return;
end;
$preflight$;

alter table connected_app_private.connections
  add column if not exists authorization_issued_at timestamptz;
alter table connected_app_private.oauth_flows
  add column if not exists completion_authorization_issued_at timestamptz;

do $constraints$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid = pg_catalog.to_regclass('connected_app_private.connections')
      and conname = 'connected_app_connections_authorization_issued_check'
  ) then
    alter table connected_app_private.connections
      add constraint connected_app_connections_authorization_issued_check
      check (
        authorization_issued_at is null or (
          authorization_state in ('active', 'revoked')
          and authorization_snapshot_sha256 is not null
        )
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid = pg_catalog.to_regclass('connected_app_private.oauth_flows')
      and conname = 'connected_app_oauth_completion_issued_check'
  ) then
    alter table connected_app_private.oauth_flows
      add constraint connected_app_oauth_completion_issued_check
      check (
        completion_authorization_issued_at is null or status = 'completed'
      );
  end if;
end;
$constraints$;

create table if not exists connected_app_private.oauth_permit_capability_custody (
  permit_id uuid primary key
    references connected_app_private.oauth_exchange_permits(permit_id)
    on delete cascade,
  exchange_binding_sha256 text not null
    check (exchange_binding_sha256 ~ '^[0-9a-f]{64}$'),
  permit_binding_sha256 text not null
    check (permit_binding_sha256 ~ '^[0-9a-f]{64}$'),
  capability_sha256 text not null unique
    check (capability_sha256 ~ '^[0-9a-f]{64}$'),
  key_id text not null
    check (key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  wrapped_key_nonce text not null,
  wrapped_key_ciphertext text not null,
  secret_nonce text not null,
  secret_ciphertext text not null,
  record_binding_sha256 text not null unique
    check (record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null,
  expires_at timestamptz not null,
  constraint connected_oauth_permit_custody_lifetime
    check (expires_at > created_at and expires_at <= created_at + interval '2 minutes')
);
comment on table connected_app_private.oauth_permit_capability_custody is
  'ASK_CRUMP_CONNECTED_OAUTH_PERMIT_CAPABILITY_V2_ENCRYPTED_PRIVATE';
alter table connected_app_private.oauth_permit_capability_custody enable row level security;
alter table connected_app_private.oauth_permit_capability_custody force row level security;
revoke all on table connected_app_private.oauth_permit_capability_custody
  from public, anon, authenticated, service_role;

create or replace function public.connected_app_get_binding_v2(
  p_owner_id uuid,
  p_connection_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
begin
  if p_owner_id is null or p_connection_id is null then
    raise exception 'binding identifiers are required' using errcode = '22023';
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id;
  if not found then return null; end if;
  return pg_catalog.jsonb_build_object(
    'owner_id', connection_row.owner_id,
    'connection_id', connection_row.id,
    'provider', connection_row.provider,
    'resource', connection_row.resource,
    'account_kind', connection_row.account_kind,
    'connection_incarnation_id', connection_row.connection_incarnation_id,
    'authorization_revision', connection_row.authorization_revision,
    'authorization_state', connection_row.authorization_state,
    'authorization_snapshot_sha256', connection_row.authorization_snapshot_sha256,
    'authorization_issued_at', connection_row.authorization_issued_at,
    'granted_actions', connection_row.granted_actions,
    'granted_actions_sha256', connection_row.granted_actions_sha256,
    'granted_scopes_sha256', connection_row.granted_scopes_sha256,
    'external_account_id_sha256', connection_row.external_account_id_sha256,
    'broker_credential_ref', connection_row.broker_credential_ref,
    'credential_ref_sha256', connection_row.credential_ref_sha256,
    'current_flow_nonce_sha256', connection_row.current_flow_nonce_sha256,
    'authorization_expires_at', connection_row.authorization_expires_at,
    'revoked_at', connection_row.revoked_at
  );
end;
$fn$;
comment on function public.connected_app_get_binding_v2(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_GET_BINDING_V2_RESTART_AUTHORITY_SERVICE_ROLE_ONLY';

create or replace function public.connected_app_oauth_revalidate_flow_v2(
  p_flow_id uuid,
  p_expected_flow_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  if p_flow_id is null
     or p_expected_flow_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'OAuth flow read binding is invalid' using errcode = '22023';
  end if;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = p_flow_id;
  if not found then return null; end if;
  perform connected_app_private.owner_lock_v1(flow_row.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = flow_row.connection_id and connection.owner_id = flow_row.owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = p_flow_id
  for update;
  if connection_row.id is null or flow_row.flow_id is null
     or flow_row.flow_binding_sha256 <> p_expected_flow_binding_sha256
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> flow_row.connection_incarnation_id
     or connection_row.authorization_revision <> flow_row.expected_base_revision
     or connection_row.current_flow_nonce_sha256 <> flow_row.current_flow_nonce_sha256 then
    raise exception 'OAuth flow live authority changed' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'flow_id', flow_row.flow_id,
    'nonce_id', flow_row.nonce_id,
    'owner_id', flow_row.owner_id,
    'connection_id', flow_row.connection_id,
    'connection_incarnation_id', flow_row.connection_incarnation_id,
    'expected_base_revision', flow_row.expected_base_revision,
    'current_flow_nonce_sha256', flow_row.current_flow_nonce_sha256,
    'session_binding_sha256', flow_row.session_binding_sha256,
    'provider', flow_row.provider,
    'resource', flow_row.resource,
    'account_kind', flow_row.account_kind,
    'actions', flow_row.actions,
    'actions_sha256', flow_row.actions_sha256,
    'requested_scopes_sha256', flow_row.requested_scopes_sha256,
    'state_sha256', flow_row.state_sha256,
    'pkce_challenge', flow_row.pkce_challenge,
    'redirect_uri_sha256', flow_row.redirect_uri_sha256,
    'flow_binding_sha256', flow_row.flow_binding_sha256,
    'status', flow_row.status,
    'consumption_id', flow_row.consumption_id,
    'consume_binding_sha256', flow_row.consume_binding_sha256,
    'consumed_at', flow_row.consumed_at,
    'created_at', flow_row.created_at,
    'expires_at', flow_row.expires_at
  );
end;
$fn$;
comment on function public.connected_app_oauth_revalidate_flow_v2(uuid,text) is
  'ASK_CRUMP_CONNECTED_OAUTH_REVALIDATE_FLOW_V2_LIVE_AUTHORITY';

create or replace function public.connected_app_oauth_read_consumption_v2(
  p_flow_id uuid,
  p_consumption_id uuid,
  p_flow_binding_sha256 text,
  p_consume_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  if p_flow_id is null or p_consumption_id is null
     or p_flow_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_consume_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'OAuth consumption read binding is invalid' using errcode = '22023';
  end if;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = p_flow_id;
  if not found then return null; end if;
  perform connected_app_private.owner_lock_v1(flow_row.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = flow_row.connection_id
    and connection.owner_id = flow_row.owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = p_flow_id
  for update;
  if connection_row.id is null or flow_row.flow_id is null
     or flow_row.flow_binding_sha256 <> p_flow_binding_sha256
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> flow_row.connection_incarnation_id
     or connection_row.authorization_revision <> flow_row.expected_base_revision
     or connection_row.current_flow_nonce_sha256 <> flow_row.current_flow_nonce_sha256 then
    raise exception 'OAuth consumption live authority changed' using errcode = '55000';
  end if;
  if flow_row.consumption_id <> p_consumption_id
     or flow_row.consume_binding_sha256 <> p_consume_binding_sha256
     or flow_row.status not in ('consumed','exchanged','completed') then
    return null;
  end if;
  return pg_catalog.jsonb_build_object(
    'consumption_id', flow_row.consumption_id,
    'flow_id', flow_row.flow_id,
    'connection_id', flow_row.connection_id,
    'connection_incarnation_id', flow_row.connection_incarnation_id,
    'expected_base_revision', flow_row.expected_base_revision,
    'current_flow_nonce_sha256', flow_row.current_flow_nonce_sha256,
    'consume_binding_sha256', flow_row.consume_binding_sha256,
    'flow_binding_sha256', flow_row.flow_binding_sha256,
    'consumed_at', flow_row.consumed_at
  );
end;
$fn$;
comment on function public.connected_app_oauth_read_consumption_v2(uuid,uuid,text,text) is
  'ASK_CRUMP_CONNECTED_OAUTH_READ_CONSUMPTION_V2_CONTENT_FREE';

create or replace function public.connected_app_oauth_put_permit_capability_v2(
  p_permit_id uuid,
  p_flow_id uuid,
  p_connection_id uuid,
  p_exchange_id uuid,
  p_capability_sha256 text,
  p_permit_binding_sha256 text,
  p_exchange_binding_sha256 text,
  p_issued_at timestamptz,
  p_deadline_at timestamptz,
  p_key_id text,
  p_wrapped_key_nonce text,
  p_wrapped_key_ciphertext text,
  p_secret_nonce text,
  p_secret_ciphertext text,
  p_record_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  permit_result jsonb;
  custody_row connected_app_private.oauth_permit_capability_custody%rowtype;
begin
  if p_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_key_id !~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
     or pg_catalog.octet_length(p_wrapped_key_nonce) not between 16 and 64
     or pg_catalog.octet_length(p_wrapped_key_ciphertext) not between 48 and 256
     or pg_catalog.octet_length(p_secret_nonce) not between 16 and 64
     or pg_catalog.octet_length(p_secret_ciphertext) not between 32 and 2048 then
    raise exception 'OAuth permit custody envelope is invalid' using errcode = '22023';
  end if;
  permit_result := public.connected_app_oauth_issue_permit_v1(
    p_permit_id, p_flow_id, p_connection_id, p_exchange_id,
    p_capability_sha256, p_permit_binding_sha256,
    p_exchange_binding_sha256, p_issued_at, p_deadline_at
  );
  select custody.* into custody_row
  from connected_app_private.oauth_permit_capability_custody as custody
  where custody.permit_id = p_permit_id
     or custody.record_binding_sha256 = p_record_binding_sha256
  for update;
  if found then
    if custody_row.permit_id <> p_permit_id
       or custody_row.exchange_binding_sha256 <> p_exchange_binding_sha256
       or custody_row.permit_binding_sha256 <> p_permit_binding_sha256
       or custody_row.capability_sha256 <> p_capability_sha256
       or custody_row.key_id <> p_key_id
       or custody_row.wrapped_key_nonce <> p_wrapped_key_nonce
       or custody_row.wrapped_key_ciphertext <> p_wrapped_key_ciphertext
       or custody_row.secret_nonce <> p_secret_nonce
       or custody_row.secret_ciphertext <> p_secret_ciphertext
       or custody_row.record_binding_sha256 <> p_record_binding_sha256
       or custody_row.created_at <> p_issued_at
       or custody_row.expires_at <> p_deadline_at then
      raise exception 'OAuth permit capability replay drifted' using errcode = '55000';
    end if;
  else
    insert into connected_app_private.oauth_permit_capability_custody(
      permit_id, exchange_binding_sha256, permit_binding_sha256,
      capability_sha256, key_id, wrapped_key_nonce, wrapped_key_ciphertext,
      secret_nonce, secret_ciphertext, record_binding_sha256,
      created_at, expires_at
    ) values (
      p_permit_id, p_exchange_binding_sha256, p_permit_binding_sha256,
      p_capability_sha256, p_key_id, p_wrapped_key_nonce, p_wrapped_key_ciphertext,
      p_secret_nonce, p_secret_ciphertext, p_record_binding_sha256,
      p_issued_at, p_deadline_at
    ) returning * into custody_row;
  end if;
  return pg_catalog.jsonb_build_object(
    'permit', permit_result,
    'custody', pg_catalog.jsonb_build_object(
      'permit_id', custody_row.permit_id,
      'exchange_binding_sha256', custody_row.exchange_binding_sha256,
      'permit_binding_sha256', custody_row.permit_binding_sha256,
      'capability_sha256', custody_row.capability_sha256,
      'key_id', custody_row.key_id,
      'wrapped_key_nonce', custody_row.wrapped_key_nonce,
      'wrapped_key_ciphertext', custody_row.wrapped_key_ciphertext,
      'secret_nonce', custody_row.secret_nonce,
      'secret_ciphertext', custody_row.secret_ciphertext,
      'record_binding_sha256', custody_row.record_binding_sha256,
      'created_at', custody_row.created_at,
      'expires_at', custody_row.expires_at
    )
  );
end;
$fn$;
comment on function public.connected_app_oauth_put_permit_capability_v2(
  uuid,uuid,uuid,uuid,text,text,text,timestamptz,timestamptz,
  text,text,text,text,text,text
) is 'ASK_CRUMP_CONNECTED_OAUTH_PERMIT_CAPABILITY_V2_ATOMIC_ENCRYPTED';

create or replace function public.connected_app_oauth_read_permit_capability_v2(
  p_permit_id uuid,
  p_exchange_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  custody_row connected_app_private.oauth_permit_capability_custody%rowtype;
  permit_row connected_app_private.oauth_exchange_permits%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  select permit.* into permit_row
  from connected_app_private.oauth_exchange_permits as permit
  where permit.permit_id = p_permit_id
    and permit.exchange_binding_sha256 = p_exchange_binding_sha256;
  if not found then return null; end if;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = permit_row.flow_id;
  if not found then return null; end if;
  perform connected_app_private.owner_lock_v1(flow_row.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = flow_row.connection_id
    and connection.owner_id = flow_row.owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = permit_row.flow_id
  for update;
  select permit.* into permit_row
  from connected_app_private.oauth_exchange_permits as permit
  where permit.permit_id = p_permit_id
  for update;
  select custody.* into custody_row
  from connected_app_private.oauth_permit_capability_custody as custody
  where custody.permit_id = p_permit_id
  for update;
  if connection_row.id is null or flow_row.flow_id is null
     or permit_row.permit_id is null or custody_row.permit_id is null
     or permit_row.exchange_binding_sha256 <> p_exchange_binding_sha256
     or custody_row.exchange_binding_sha256 <> p_exchange_binding_sha256
     or permit_row.permit_binding_sha256 <> custody_row.permit_binding_sha256
     or permit_row.capability_sha256 <> custody_row.capability_sha256
     or permit_row.status <> 'issued'
     or flow_row.status <> 'consumed'
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> flow_row.connection_incarnation_id
     or connection_row.authorization_revision <> flow_row.expected_base_revision
     or connection_row.current_flow_nonce_sha256 <> flow_row.current_flow_nonce_sha256
     or pg_catalog.clock_timestamp() >= permit_row.deadline_at then
    delete from connected_app_private.oauth_permit_capability_custody
    where permit_id = p_permit_id;
    return null;
  end if;
  return pg_catalog.jsonb_build_object(
    'permit_id', custody_row.permit_id,
    'exchange_binding_sha256', custody_row.exchange_binding_sha256,
    'permit_binding_sha256', custody_row.permit_binding_sha256,
    'capability_sha256', custody_row.capability_sha256,
    'key_id', custody_row.key_id,
    'wrapped_key_nonce', custody_row.wrapped_key_nonce,
    'wrapped_key_ciphertext', custody_row.wrapped_key_ciphertext,
    'secret_nonce', custody_row.secret_nonce,
    'secret_ciphertext', custody_row.secret_ciphertext,
    'record_binding_sha256', custody_row.record_binding_sha256,
    'created_at', custody_row.created_at,
    'expires_at', custody_row.expires_at
  );
end;
$fn$;
comment on function public.connected_app_oauth_read_permit_capability_v2(uuid,text) is
  'ASK_CRUMP_CONNECTED_OAUTH_READ_PERMIT_CAPABILITY_V2_ENCRYPTED';

create or replace function public.connected_app_oauth_consume_permit_v2(
  p_permit_id uuid,
  p_flow_id uuid,
  p_connection_id uuid,
  p_exchange_id uuid,
  p_capability_sha256 text,
  p_permit_binding_sha256 text,
  p_exchange_binding_sha256 text,
  p_dispatch_fence_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  permit_row connected_app_private.oauth_exchange_permits%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_dispatch_fence_id is null then
    raise exception 'OAuth dispatch fence is required' using errcode = '22023';
  end if;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = p_flow_id;
  if not found then
    raise exception 'OAuth flow not found' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(flow_row.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = p_flow_id
  for update;
  select permit.* into permit_row
  from connected_app_private.oauth_exchange_permits as permit
  where permit.permit_id = p_permit_id
  for update;
  if connection_row.id is null or flow_row.flow_id is null
     or permit_row.permit_id is null
     or permit_row.flow_id <> p_flow_id
     or permit_row.connection_id <> p_connection_id
     or permit_row.exchange_id <> p_exchange_id
     or permit_row.capability_sha256 is distinct from p_capability_sha256
     or permit_row.permit_binding_sha256 <> p_permit_binding_sha256
     or permit_row.exchange_binding_sha256 <> p_exchange_binding_sha256
     or flow_row.status not in ('consumed', 'exchanged')
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> flow_row.connection_incarnation_id
     or connection_row.authorization_revision <> flow_row.expected_base_revision
     or connection_row.current_flow_nonce_sha256 <> flow_row.current_flow_nonce_sha256 then
    raise exception 'OAuth exchange permit is stale or forged' using errcode = '55000';
  end if;
  if permit_row.status <> 'issued' then
    if permit_row.dispatch_fence_id <> p_dispatch_fence_id then
      raise exception 'OAuth exchange permit already consumed' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'claimed', false,
      'status', permit_row.status,
      'permit_id', permit_row.permit_id,
      'exchange_binding_sha256', permit_row.exchange_binding_sha256,
      'permit_binding_sha256', permit_row.permit_binding_sha256,
      'consumed_at', permit_row.consumed_at
    );
  end if;
  if now_at >= permit_row.deadline_at then
    update connected_app_private.oauth_exchange_permits as permit
    set status = 'expired', dispatch_fence_id = p_dispatch_fence_id
    where permit.permit_id = p_permit_id
    returning * into permit_row;
    delete from connected_app_private.oauth_permit_capability_custody
    where permit_id = p_permit_id;
    return pg_catalog.jsonb_build_object(
      'claimed', false,
      'status', 'expired',
      'permit_id', permit_row.permit_id,
      'exchange_binding_sha256', permit_row.exchange_binding_sha256,
      'permit_binding_sha256', permit_row.permit_binding_sha256,
      'consumed_at', null
    );
  end if;
  update connected_app_private.oauth_exchange_permits as permit
  set status = 'attempt_fenced',
      dispatch_fence_id = p_dispatch_fence_id,
      consumed_at = now_at
  where permit.permit_id = p_permit_id
  returning * into permit_row;
  update connected_app_private.oauth_flows
  set status = 'exchanged', updated_at = now_at
  where flow_id = p_flow_id and status = 'consumed';
  delete from connected_app_private.oauth_permit_capability_custody
  where permit_id = p_permit_id;
  return pg_catalog.jsonb_build_object(
    'claimed', true,
    'status', 'attempt_fenced',
    'permit_id', permit_row.permit_id,
    'exchange_binding_sha256', permit_row.exchange_binding_sha256,
    'permit_binding_sha256', permit_row.permit_binding_sha256,
    'consumed_at', permit_row.consumed_at
  );
end;
$fn$;
comment on function public.connected_app_oauth_consume_permit_v2(
  uuid,uuid,uuid,uuid,text,text,text,uuid
) is 'ASK_CRUMP_CONNECTED_OAUTH_CONSUME_PERMIT_V2_FRESH_WINNER_ONLY';

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
  now_at timestamptz := pg_catalog.clock_timestamp();
  inactive_reason text;
begin
  if p_authorization_issued_at is null
     or p_authorization_expires_at <= p_authorization_issued_at
     or p_authorization_issued_at > now_at + interval '1 minute'
     or p_authorization_snapshot_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'OAuth authorization snapshot binding is invalid'
      using errcode = '22023';
  end if;
  result_row := public.connected_app_oauth_finalize_v1(
    p_flow_id, p_consumption_id, p_exchange_id,
    p_exchange_binding_sha256, p_dispatch_fence_id,
    p_owner_id, p_connection_id, p_connection_incarnation_id,
    p_expected_base_revision, p_current_flow_nonce_sha256,
    p_provider, p_resource, p_account_kind,
    p_external_account_id_sha256, p_granted_scopes_sha256,
    p_broker_credential_ref, p_credential_ref_sha256,
    p_authorization_expires_at, p_completion_id,
    p_completion_binding_sha256, p_cleanup_id, p_cleanup_binding_sha256
  );
  if coalesce((result_row->>'completed')::boolean, false)
     and coalesce((result_row->>'active')::boolean, false) then
    update connected_app_private.connections as connection
    set authorization_snapshot_sha256 = p_authorization_snapshot_sha256,
        authorization_issued_at = p_authorization_issued_at,
        updated_at = now_at
    where connection.id = p_connection_id
      and connection.owner_id = p_owner_id
      and connection.authorization_revision = p_expected_base_revision + 1
      and connection.broker_credential_ref = p_broker_credential_ref
      and connection.credential_ref_sha256 = p_credential_ref_sha256
      and connection.authorization_expires_at = p_authorization_expires_at
      and connection.authorization_snapshot_sha256 in (
        p_completion_binding_sha256, p_authorization_snapshot_sha256
      )
    returning * into connection_row;
    if not found then
      raise exception 'OAuth authorization correction lost its connection fence'
        using errcode = '55000';
    end if;
    update connected_app_private.oauth_flows as flow
    set completion_authorization_snapshot_sha256 = p_authorization_snapshot_sha256,
        completion_authorization_issued_at = p_authorization_issued_at,
        updated_at = now_at
    where flow.flow_id = p_flow_id
      and flow.completion_id = p_completion_id
      and flow.completion_binding_sha256 = p_completion_binding_sha256
      and flow.completion_authorization_revision = p_expected_base_revision + 1
      and flow.completion_authorization_snapshot_sha256 in (
        p_completion_binding_sha256, p_authorization_snapshot_sha256
      )
    returning * into flow_row;
    if not found then
      raise exception 'OAuth authorization correction lost its flow fence'
        using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'completed', true, 'active', true,
      'owner_id', connection_row.owner_id,
      'connection_id', connection_row.id,
      'connection_incarnation_id', connection_row.connection_incarnation_id,
      'consumption_id', flow_row.consumption_id,
      'exchange_id', p_exchange_id,
      'completion_id', flow_row.completion_id,
      'completion_binding_sha256', flow_row.completion_binding_sha256,
      'authorization_revision', connection_row.authorization_revision,
      'authorization_snapshot_sha256', connection_row.authorization_snapshot_sha256,
      'authorization_issued_at', connection_row.authorization_issued_at,
      'granted_actions', connection_row.granted_actions,
      'granted_actions_sha256', connection_row.granted_actions_sha256,
      'granted_scopes_sha256', connection_row.granted_scopes_sha256,
      'external_account_id_sha256', connection_row.external_account_id_sha256,
      'broker_credential_ref', connection_row.broker_credential_ref,
      'credential_ref_sha256', connection_row.credential_ref_sha256,
      'authorization_expires_at', connection_row.authorization_expires_at
    );
  end if;

  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id;
  inactive_reason := case
    when connection_row.id is null then 'replaced'
    when connection_row.authorization_state = 'revoked' then 'revoked'
    when connection_row.connection_incarnation_id <> p_connection_incarnation_id
      then 'incarnation_changed'
    when connection_row.authorization_revision <> p_expected_base_revision
      then 'revision_changed'
    when connection_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256
      then 'newer_flow'
    when connection_row.external_account_id_sha256 is distinct from
         p_external_account_id_sha256 then 'account_changed'
    else 'replaced'
  end;
  return pg_catalog.jsonb_build_object(
    'completed', false, 'active', false,
    'completion_id', p_completion_id,
    'completion_binding_sha256', p_completion_binding_sha256,
    'connection_id', p_connection_id,
    'observed_at', now_at,
    'reason', inactive_reason
  );
end;
$fn$;
comment on function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) is 'ASK_CRUMP_CONNECTED_OAUTH_FINALIZE_V2_SEPARATE_AUTHORIZATION_AND_REPLAY_HASHES';

create or replace function public.connected_app_oauth_read_completion_v2(
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
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
  inactive_reason text;
begin
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.completion_id = p_completion_id
    and flow.completion_binding_sha256 = p_completion_binding_sha256
    and flow.owner_id = p_owner_id
    and flow.connection_id = p_connection_id;
  if not found then return null; end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.completion_id = p_completion_id
    and flow.completion_binding_sha256 = p_completion_binding_sha256
  for update;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id
  for update;
  if flow_row.status = 'completed'
     and connection_row.id is not null
     and connection_row.authorization_state = 'active'
     and connection_row.connection_incarnation_id = flow_row.connection_incarnation_id
     and connection_row.authorization_revision = flow_row.completion_authorization_revision
     and connection_row.authorization_snapshot_sha256 =
         flow_row.completion_authorization_snapshot_sha256
     and connection_row.authorization_issued_at =
         flow_row.completion_authorization_issued_at
     and connection_row.current_flow_nonce_sha256 = flow_row.current_flow_nonce_sha256
     and connection_row.external_account_id_sha256 =
         flow_row.completion_external_account_id_sha256
     and connection_row.broker_credential_ref = flow_row.completion_broker_credential_ref
     and connection_row.credential_ref_sha256 = flow_row.completion_credential_ref_sha256 then
    return pg_catalog.jsonb_build_object(
      'completed', true, 'active', true,
      'owner_id', flow_row.owner_id,
      'connection_id', flow_row.connection_id,
      'connection_incarnation_id', flow_row.connection_incarnation_id,
      'consumption_id', flow_row.consumption_id,
      'exchange_id', (
        select permit.exchange_id
        from connected_app_private.oauth_exchange_permits as permit
        where permit.flow_id = flow_row.flow_id and permit.status = 'terminal'
        limit 1
      ),
      'completion_id', flow_row.completion_id,
      'completion_binding_sha256', flow_row.completion_binding_sha256,
      'authorization_revision', flow_row.completion_authorization_revision,
      'authorization_snapshot_sha256', flow_row.completion_authorization_snapshot_sha256,
      'authorization_issued_at', flow_row.completion_authorization_issued_at,
      'granted_actions', flow_row.completion_granted_actions,
      'granted_actions_sha256', flow_row.completion_granted_actions_sha256,
      'granted_scopes_sha256', flow_row.completion_granted_scopes_sha256,
      'external_account_id_sha256', flow_row.completion_external_account_id_sha256,
      'broker_credential_ref', flow_row.completion_broker_credential_ref,
      'credential_ref_sha256', flow_row.completion_credential_ref_sha256,
      'authorization_expires_at', flow_row.completion_authorization_expires_at
    );
  end if;
  inactive_reason := case
    when connection_row.id is null then 'replaced'
    when connection_row.authorization_state = 'revoked' then 'revoked'
    when connection_row.connection_incarnation_id <> flow_row.connection_incarnation_id
      then 'incarnation_changed'
    when connection_row.authorization_revision <>
         flow_row.completion_authorization_revision then 'revision_changed'
    when connection_row.current_flow_nonce_sha256 <> flow_row.current_flow_nonce_sha256
      then 'newer_flow'
    when connection_row.external_account_id_sha256 is distinct from
         flow_row.completion_external_account_id_sha256 then 'account_changed'
    else 'replaced'
  end;
  return pg_catalog.jsonb_build_object(
    'completed', true, 'active', false,
    'completion_id', flow_row.completion_id,
    'completion_binding_sha256', flow_row.completion_binding_sha256,
    'connection_id', flow_row.connection_id,
    'observed_at', now_at,
    'reason', inactive_reason
  );
end;
$fn$;
comment on function public.connected_app_oauth_read_completion_v2(uuid,text,uuid,uuid) is
  'ASK_CRUMP_CONNECTED_OAUTH_READ_COMPLETION_V2_LIVE_REVALIDATION';

create or replace function public.connected_app_read_credential_cleanup_v2(
  p_cleanup_id uuid,
  p_cleanup_binding_sha256 text
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'cleanup_id', cleanup.cleanup_id,
    'cleanup_binding_sha256', cleanup.cleanup_binding_sha256,
    'recorded_at', cleanup.created_at
  )
  from connected_app_private.credential_cleanup_outbox as cleanup
  where cleanup.cleanup_id = p_cleanup_id
    and cleanup.cleanup_binding_sha256 = p_cleanup_binding_sha256
$fn$;
comment on function public.connected_app_read_credential_cleanup_v2(uuid,text) is
  'ASK_CRUMP_CONNECTED_OAUTH_READ_CLEANUP_V2_CONTENT_FREE';

revoke all on function public.connected_app_get_binding_v2(uuid,uuid)
  from public, anon, authenticated;
revoke all on function public.connected_app_oauth_revalidate_flow_v2(uuid,text)
  from public, anon, authenticated;
revoke all on function public.connected_app_oauth_read_consumption_v2(uuid,uuid,text,text)
  from public, anon, authenticated;
revoke all on function public.connected_app_oauth_put_permit_capability_v2(
  uuid,uuid,uuid,uuid,text,text,text,timestamptz,timestamptz,
  text,text,text,text,text,text
) from public, anon, authenticated;
revoke all on function public.connected_app_oauth_read_permit_capability_v2(uuid,text)
  from public, anon, authenticated;
revoke all on function public.connected_app_oauth_consume_permit_v2(
  uuid,uuid,uuid,uuid,text,text,text,uuid
) from public, anon, authenticated;
revoke all on function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) from public, anon, authenticated;
revoke all on function public.connected_app_oauth_read_completion_v2(uuid,text,uuid,uuid)
  from public, anon, authenticated;
revoke all on function public.connected_app_read_credential_cleanup_v2(uuid,text)
  from public, anon, authenticated;

grant execute on function public.connected_app_get_binding_v2(uuid,uuid)
  to service_role;
grant execute on function public.connected_app_oauth_revalidate_flow_v2(uuid,text)
  to service_role;
grant execute on function public.connected_app_oauth_read_consumption_v2(uuid,uuid,text,text)
  to service_role;
grant execute on function public.connected_app_oauth_put_permit_capability_v2(
  uuid,uuid,uuid,uuid,text,text,text,timestamptz,timestamptz,
  text,text,text,text,text,text
) to service_role;
grant execute on function public.connected_app_oauth_read_permit_capability_v2(uuid,text)
  to service_role;
grant execute on function public.connected_app_oauth_consume_permit_v2(
  uuid,uuid,uuid,uuid,text,text,text,uuid
) to service_role;
grant execute on function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) to service_role;
grant execute on function public.connected_app_oauth_read_completion_v2(uuid,text,uuid,uuid)
  to service_role;
grant execute on function public.connected_app_read_credential_cleanup_v2(uuid,text)
  to service_role;

-- The old finalize conflates the completion replay hash with authorization.
-- The old permit writer can create a durable permit without durable capability
-- custody. Keep both callable only from the reviewed v2 wrappers.
revoke all on function public.connected_app_oauth_finalize_v1(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,uuid,text,uuid,text
) from public, anon, authenticated, service_role;
revoke all on function public.connected_app_oauth_issue_permit_v1(
  uuid,uuid,uuid,uuid,text,text,text,timestamptz,timestamptz
) from public, anon, authenticated, service_role;

do $postflight$
declare
  bad_functions integer;
  relation_row record;
  function_row record;
begin
  if pg_catalog.to_regclass(
       'connected_app_private.oauth_permit_capability_custody'
     ) is null
     or pg_catalog.to_regprocedure('public.connected_app_get_binding_v2(uuid,uuid)') is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)'
     ) is null
     or not pg_catalog.has_function_privilege(
       'service_role', 'public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)', 'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'service_role', 'public.connected_app_oauth_finalize_v1(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,uuid,text,uuid,text)', 'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'service_role', 'public.connected_app_oauth_issue_permit_v1(uuid,uuid,uuid,uuid,text,text,text,timestamp with time zone,timestamp with time zone)', 'EXECUTE'
     ) then
    raise exception 'connected OAuth runtime authority postflight failed'
      using errcode = '55000';
  end if;
  select pg_catalog.count(*) into bad_functions
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname in (
      'connected_app_get_binding_v2',
      'connected_app_oauth_revalidate_flow_v2',
      'connected_app_oauth_read_consumption_v2',
      'connected_app_oauth_put_permit_capability_v2',
      'connected_app_oauth_read_permit_capability_v2',
      'connected_app_oauth_consume_permit_v2',
      'connected_app_oauth_finalize_v2',
      'connected_app_oauth_read_completion_v2',
      'connected_app_read_credential_cleanup_v2'
    )
    and (not proc_row.prosecdef
      or proc_row.proconfig is distinct from array['search_path=""']::text[]);
  if bad_functions <> 0 then
    raise exception 'connected OAuth runtime authority function config drifted'
      using errcode = '55000';
  end if;
  select class_row.oid, class_row.relowner, class_row.relrowsecurity,
         class_row.relforcerowsecurity
    into relation_row
  from pg_catalog.pg_class as class_row
  where class_row.oid = pg_catalog.to_regclass(
    'connected_app_private.oauth_permit_capability_custody'
  );
  if pg_catalog.pg_get_userbyid(relation_row.relowner) <> 'postgres'
     or not relation_row.relrowsecurity or not relation_row.relforcerowsecurity
     or exists (
       select 1 from pg_catalog.aclexplode(coalesce(
         (select relacl from pg_catalog.pg_class where oid = relation_row.oid),
         pg_catalog.acldefault('r', relation_row.relowner)
       )) as acl_row where acl_row.grantee <> relation_row.relowner
     )
     or exists (
       select 1 from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid = relation_row.oid
     ) then
    raise exception 'connected OAuth permit custody table authority drifted'
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
        'connected_app_get_binding_v2',
        'connected_app_oauth_revalidate_flow_v2',
        'connected_app_oauth_read_consumption_v2',
        'connected_app_oauth_put_permit_capability_v2',
        'connected_app_oauth_read_permit_capability_v2',
        'connected_app_oauth_consume_permit_v2',
        'connected_app_oauth_finalize_v2',
        'connected_app_oauth_read_completion_v2',
        'connected_app_read_credential_cleanup_v2'
      )
  loop
    if pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
       or not function_row.prosecdef
       or function_row.proconfig is distinct from array['search_path=""']::text[]
       or not exists (
         select 1 from pg_catalog.aclexplode(coalesce(
           (select proacl from pg_catalog.pg_proc where oid = function_row.oid),
           pg_catalog.acldefault('f', function_row.proowner)
         )) as acl_row
         where acl_row.grantee = (
           select oid from pg_catalog.pg_roles where rolname = 'service_role'
         ) and acl_row.privilege_type = 'EXECUTE'
       )
       or exists (
         select 1 from pg_catalog.aclexplode(coalesce(
           (select proacl from pg_catalog.pg_proc where oid = function_row.oid),
           pg_catalog.acldefault('f', function_row.proowner)
         )) as acl_row
         where acl_row.privilege_type <> 'EXECUTE'
            or acl_row.grantee not in (
              function_row.proowner,
              (select oid from pg_catalog.pg_roles where rolname = 'service_role')
            )
       ) then
      raise exception 'connected OAuth runtime RPC authority drifted: %',
        function_row.proname using errcode = '55000';
    end if;
  end loop;
end;
$postflight$;

commit;
