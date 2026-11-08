-- ASK_CRUMP_CONNECTED_APP_CONTROL_PLANE_V1
--
-- Local-only, source-locked control-plane foundation for owner-connected mail
-- and calendars.  This migration stores no provider bearer/refresh token,
-- authorization code, OAuth state, PKCE verifier, mailbox/calendar content,
-- email address, subject, body, recipient, or event text.  Provider secrets
-- remain in an external credential broker and are represented here only by an
-- opaque UUID reference and SHA-256 bindings.
--
-- IMPORTANT: fresh first apply and a bounded owner-operator behavior gate
-- passed on disposable local PostgreSQL 17.11.  Catalog/race/rollback and the
-- exact-target verified no-op reapply gates described in
-- docs/CONNECTED_APP_STORAGE_CONTRACT_2026-11-07.md are mandatory before this
-- migration may be proposed, applied, or released.

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
select pg_catalog.set_config('quote_all_identifiers', 'off', false);

do $preflight$
declare
  existing_schema oid := pg_catalog.to_regnamespace('connected_app_private');
  observed_target_fingerprint text;
  observed_target_components jsonb;
begin
  if pg_catalog.to_regclass('public.users') is null then
    raise exception 'connected-app control plane requires public.users'
      using errcode = '55000';
  end if;
  if not exists (
    select 1
    from pg_catalog.pg_class as class_row
    where class_row.oid = pg_catalog.to_regclass('public.sessions')
      and class_row.relkind = 'r'
  ) or (
    select pg_catalog.count(*)
    from pg_catalog.pg_attribute as attribute_row
    where attribute_row.attrelid = pg_catalog.to_regclass('public.sessions')
      and not attribute_row.attisdropped
      and (
        (attribute_row.attname in ('id', 'user_id')
          and pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) = 'uuid')
        or (attribute_row.attname in ('expires_at', 'revoked_at')
          and pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod)
            = 'timestamp with time zone')
      )
  ) <> 4 or not exists (
    select 1
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_attribute as attribute_row
      on attribute_row.attrelid = index_row.indrelid
     and attribute_row.attnum = index_row.indkey[0]
    where index_row.indrelid = pg_catalog.to_regclass('public.sessions')
      and index_row.indisprimary
      and index_row.indnkeyatts = 1
      and attribute_row.attname = 'id'
  ) then
    raise exception 'connected-app control plane requires canonical public.sessions authority'
      using errcode = '55000';
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'postgres')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'service_role')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'anon') then
    raise exception 'connected-app control plane requires hosted API roles'
      using errcode = '55000';
  end if;
  if pg_catalog.to_regprocedure('pg_catalog.gen_random_uuid()') is null then
    raise exception 'connected-app control plane requires database randomness'
      using errcode = '55000';
  end if;

  -- The body below is syntactically idempotent only after this complete
  -- target attestation succeeds.  A partial, mixed, or drifted target is
  -- rejected before any IF NOT EXISTS / CREATE OR REPLACE statement can run.
  if existing_schema is not null then
    with target_items as (
      select pg_catalog.jsonb_build_array(
        'schema', namespace_row.nspname,
        pg_catalog.pg_get_userbyid(namespace_row.nspowner),
        pg_catalog.obj_description(namespace_row.oid, 'pg_namespace'),
        coalesce(namespace_row.nspacl::text, '')
      ) as value
      from pg_catalog.pg_namespace as namespace_row
      where namespace_row.nspname = 'connected_app_private'

      union all
      select pg_catalog.jsonb_build_array(
        'relation', class_row.relname, class_row.relkind, class_row.relpersistence,
        class_row.relrowsecurity, class_row.relforcerowsecurity,
        class_row.relreplident, pg_catalog.pg_get_userbyid(class_row.relowner),
        coalesce(class_row.relacl::text, ''),
        pg_catalog.obj_description(class_row.oid, 'pg_class')
      )
      from pg_catalog.pg_class as class_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relkind in ('r', 'S')

      union all
      select pg_catalog.jsonb_build_array(
        'column', class_row.relname, attribute_row.attnum,
        attribute_row.attname,
        pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod),
        attribute_row.attnotnull, attribute_row.attidentity,
        attribute_row.attgenerated,
        coalesce(pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid), ''),
        coalesce(collation_row.collname, ''),
        coalesce(attribute_row.attacl::text, ''),
        pg_catalog.col_description(class_row.oid, attribute_row.attnum)
      )
      from pg_catalog.pg_attribute as attribute_row
      join pg_catalog.pg_class as class_row
        on class_row.oid = attribute_row.attrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      left join pg_catalog.pg_attrdef as default_row
        on default_row.adrelid = attribute_row.attrelid
       and default_row.adnum = attribute_row.attnum
      left join pg_catalog.pg_collation as collation_row
        on collation_row.oid = attribute_row.attcollation
       and attribute_row.attcollation <> 0
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relkind = 'r'
        and attribute_row.attnum > 0
        and not attribute_row.attisdropped

      union all
      select pg_catalog.jsonb_build_array(
        'constraint', class_row.relname, constraint_row.conname,
        constraint_row.contype, constraint_row.condeferrable,
        constraint_row.condeferred, constraint_row.convalidated,
        pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
      )
      from pg_catalog.pg_constraint as constraint_row
      join pg_catalog.pg_class as class_row
        on class_row.oid = constraint_row.conrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'

      union all
      select pg_catalog.jsonb_build_array(
        'index', table_row.relname, index_class.relname,
        index_row.indisunique, index_row.indisprimary,
        index_row.indisexclusion, index_row.indimmediate,
        index_row.indisvalid, index_row.indisready, index_row.indislive,
        pg_catalog.pg_get_indexdef(index_row.indexrelid)
      )
      from pg_catalog.pg_index as index_row
      join pg_catalog.pg_class as table_row on table_row.oid = index_row.indrelid
      join pg_catalog.pg_class as index_class on index_class.oid = index_row.indexrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = table_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'

      union all
      select pg_catalog.jsonb_build_array(
        'sequence', sequence_row.sequencename, sequence_row.data_type,
        sequence_row.start_value, sequence_row.min_value,
        sequence_row.max_value, sequence_row.increment_by,
        sequence_row.cycle, sequence_row.cache_size,
        pg_catalog.pg_get_userbyid(class_row.relowner),
        coalesce(class_row.relacl::text, ''),
        pg_catalog.obj_description(class_row.oid, 'pg_class')
      )
      from pg_catalog.pg_sequences as sequence_row
      join pg_catalog.pg_class as class_row
        on class_row.oid = pg_catalog.to_regclass(
          pg_catalog.format(
            '%I.%I', sequence_row.schemaname, sequence_row.sequencename
          )
        )
      where sequence_row.schemaname = 'connected_app_private'

      union all
      select pg_catalog.jsonb_build_array(
        'type', type_row.typname, type_row.typtype, type_row.typcategory,
        type_row.typnotnull, pg_catalog.pg_get_userbyid(type_row.typowner),
        coalesce(type_row.typacl::text, ''),
        coalesce(
          pg_catalog.format_type(type_row.typbasetype, type_row.typtypmod), ''
        ),
        pg_catalog.obj_description(type_row.oid, 'pg_type')
      )
      from pg_catalog.pg_type as type_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = type_row.typnamespace
      where namespace_row.nspname = 'connected_app_private'

      union all
      select pg_catalog.jsonb_build_array(
        'function', namespace_row.nspname, proc_row.proname,
        pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
        pg_catalog.pg_get_function_result(proc_row.oid), language_row.lanname,
        proc_row.provolatile, proc_row.proparallel, proc_row.proisstrict,
        proc_row.prosecdef, proc_row.proleakproof, proc_row.prokind,
        coalesce(proc_row.proconfig::text, ''),
        pg_catalog.pg_get_userbyid(proc_row.proowner),
        coalesce(proc_row.proacl::text, ''), pg_catalog.md5(proc_row.prosrc),
        pg_catalog.obj_description(proc_row.oid, 'pg_proc')
      )
      from pg_catalog.pg_proc as proc_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = proc_row.pronamespace
      join pg_catalog.pg_language as language_row
        on language_row.oid = proc_row.prolang
      where namespace_row.nspname = 'connected_app_private'
         or (
           namespace_row.nspname = 'public'
           and proc_row.proname like 'connected_app\_%' escape '\'
         )

      union all
      select pg_catalog.jsonb_build_array(
        'trigger', namespace_row.nspname, class_row.relname,
        trigger_row.tgname, trigger_row.tgenabled, trigger_row.tgtype,
        trigger_function_namespace.nspname, trigger_function.proname,
        pg_catalog.pg_get_function_identity_arguments(trigger_function.oid),
        pg_catalog.pg_get_triggerdef(trigger_row.oid, true),
        pg_catalog.obj_description(trigger_row.oid, 'pg_trigger')
      )
      from pg_catalog.pg_trigger as trigger_row
      join pg_catalog.pg_class as class_row on class_row.oid = trigger_row.tgrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      join pg_catalog.pg_proc as trigger_function
        on trigger_function.oid = trigger_row.tgfoid
      join pg_catalog.pg_namespace as trigger_function_namespace
        on trigger_function_namespace.oid = trigger_function.pronamespace
      where not trigger_row.tgisinternal
        and (
          namespace_row.nspname = 'connected_app_private'
          or (
            namespace_row.nspname = 'public'
            and class_row.relname = 'users'
            and trigger_row.tgname like 'connected_app\_%' escape '\'
          )
        )

      union all
      select pg_catalog.jsonb_build_array(
        'rule', namespace_row.nspname, class_row.relname, rule_row.rulename,
        rule_row.ev_enabled, pg_catalog.pg_get_ruledef(rule_row.oid, true)
      )
      from pg_catalog.pg_rewrite as rule_row
      join pg_catalog.pg_class as class_row on class_row.oid = rule_row.ev_class
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and rule_row.rulename <> '_RETURN'

      union all
      select pg_catalog.jsonb_build_array(
        'policy', class_row.relname, policy_row.polname,
        policy_row.polpermissive, policy_row.polcmd,
        policy_row.polroles::text,
        pg_catalog.pg_get_expr(policy_row.polqual, policy_row.polrelid),
        pg_catalog.pg_get_expr(policy_row.polwithcheck, policy_row.polrelid)
      )
      from pg_catalog.pg_policy as policy_row
      join pg_catalog.pg_class as class_row on class_row.oid = policy_row.polrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'

      union all
      select pg_catalog.jsonb_build_array(
        'default_acl', pg_catalog.pg_get_userbyid(default_acl.defaclrole),
        default_acl.defaclobjtype, coalesce(default_acl.defaclacl::text, '')
      )
      from pg_catalog.pg_default_acl as default_acl
      where default_acl.defaclnamespace = existing_schema

      union all
      select pg_catalog.jsonb_build_array(
        'allowlist', authority.action, authority.resource,
        authority.mutates_external_state, authority.approval_class
      )
      from connected_app_private.action_authority as authority

      union all
      select pg_catalog.jsonb_build_array(
        'publication_all_tables', publication_row.pubname,
        publication_row.puballtables
      )
      from pg_catalog.pg_publication as publication_row
      where publication_row.puballtables

      union all
      select pg_catalog.jsonb_build_array(
        'publication_private', publication_row.pubname, class_row.relname
      )
      from pg_catalog.pg_publication_rel as publication_relation
      join pg_catalog.pg_publication as publication_row
        on publication_row.oid = publication_relation.prpubid
      join pg_catalog.pg_class as class_row
        on class_row.oid = publication_relation.prrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'

      union all
      select pg_catalog.jsonb_build_array(
        'effective', role_name,
        coalesce(
          pg_catalog.has_schema_privilege(
            role_name, 'connected_app_private', 'USAGE'
          ), false
        ),
        coalesce((
          select pg_catalog.bool_or(pg_catalog.has_table_privilege(
            role_name,
            pg_catalog.format('%I.%I', namespace_row.nspname, class_row.relname),
            'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
          ))
          from pg_catalog.pg_class as class_row
          join pg_catalog.pg_namespace as namespace_row
            on namespace_row.oid = class_row.relnamespace
          where namespace_row.nspname = 'connected_app_private'
            and class_row.relkind = 'r'
        ), false),
        coalesce((
          select pg_catalog.bool_and(
            case when role_name = 'service_role'
              then pg_catalog.has_function_privilege(
                role_name, proc_row.oid, 'EXECUTE'
              )
              else not pg_catalog.has_function_privilege(
                role_name, proc_row.oid, 'EXECUTE'
              )
            end
          )
          from pg_catalog.pg_proc as proc_row
          join pg_catalog.pg_namespace as namespace_row
            on namespace_row.oid = proc_row.pronamespace
          where namespace_row.nspname = 'public'
            and proc_row.proname like 'connected_app\_%' escape '\'
        ), false),
        coalesce(
          pg_catalog.pg_has_role(role_name, 'postgres', 'USAGE'), false
        )
      )
      from pg_catalog.unnest(
        array['anon', 'authenticated', 'service_role']
      ) as role_name
    ), target_components as (
      select
        item.value ->> 0 as kind,
        pg_catalog.md5(
          pg_catalog.string_agg(
            item.value::text, E'\n' order by item.value::text
          )
        ) as fingerprint
      from target_items as item
      group by item.value ->> 0
    )
    select
      (
        select pg_catalog.md5(
          pg_catalog.string_agg(
            item.value::text, E'\n' order by item.value::text
          )
        )
        from target_items as item
      ),
      (
        select pg_catalog.jsonb_object_agg(
          component.kind, component.fingerprint order by component.kind
        )
        from target_components as component
      )
    into observed_target_fingerprint, observed_target_components;

    if observed_target_fingerprint <> '3700cbb8e9d67dab331d090b26a70510' then
      raise exception
        'partial or drifted connected-app target; refusing repair: %',
        observed_target_fingerprint
        using errcode = '55000',
          detail = pg_catalog.format(
            'component fingerprints: %s', observed_target_components::text
          );
    end if;
  end if;

  if existing_schema is null and exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname like 'connected_app_%'
  ) then
    raise exception 'partial public connected-app RPC target; refusing repair'
      using errcode = '55000';
  end if;
end;
$preflight$;

begin;

create schema if not exists connected_app_private authorization postgres;
comment on schema connected_app_private is 'ASK_CRUMP_CONNECTED_APP_CONTROL_PLANE_V1';
revoke all on schema connected_app_private from public, anon, authenticated, service_role;

-- This database-owned allowlist is the only source of action mutability and
-- approval class.  Service callers cannot downgrade a write to a read or pick
-- a weaker approval class.
create table if not exists connected_app_private.action_authority (
  action text primary key,
  resource text not null check (resource in ('mail', 'calendar')),
  mutates_external_state boolean not null,
  approval_class text not null check (
    approval_class in (
      'none', 'external_write_reversible', 'external_communication',
      'calendar_write', 'destructive'
    )
  ),
  constraint connected_app_action_authority_shape check (
    (not mutates_external_state and approval_class = 'none')
    or (mutates_external_state and approval_class <> 'none')
  )
);
comment on table connected_app_private.action_authority is
  'ASK_CRUMP_CONNECTED_APP_ACTION_AUTHORITY_V1_DATABASE_OWNED_ALLOWLIST';
insert into connected_app_private.action_authority (
  action, resource, mutates_external_state, approval_class
) values
  ('mail.search', 'mail', false, 'none'),
  ('mail.get', 'mail', false, 'none'),
  ('mail.create_draft', 'mail', true, 'external_write_reversible'),
  ('mail.send', 'mail', true, 'external_communication'),
  ('mail.reply', 'mail', true, 'external_communication'),
  ('calendar.list', 'calendar', false, 'none'),
  ('calendar.get', 'calendar', false, 'none'),
  ('calendar.free_busy', 'calendar', false, 'none'),
  ('calendar.create', 'calendar', true, 'calendar_write'),
  ('calendar.update', 'calendar', true, 'calendar_write'),
  ('calendar.cancel', 'calendar', true, 'calendar_write')
on conflict (action) do nothing;

create table if not exists connected_app_private.connections (
  id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  account_kind text not null check (account_kind in ('personal', 'work_school')),
  connection_incarnation_id uuid not null,
  authorization_revision bigint not null default 0 check (authorization_revision >= 0),
  authorization_state text not null default 'pending'
    check (authorization_state in ('pending', 'active', 'revoked')),
  authorization_snapshot_sha256 text
    check (authorization_snapshot_sha256 is null or authorization_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  granted_actions text[]
    check (granted_actions is null or cardinality(granted_actions) between 1 and 16),
  granted_actions_sha256 text
    check (granted_actions_sha256 is null or granted_actions_sha256 ~ '^[0-9a-f]{64}$'),
  granted_scopes_sha256 text
    check (granted_scopes_sha256 is null or granted_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  external_account_id_sha256 text
    check (external_account_id_sha256 is null or external_account_id_sha256 ~ '^[0-9a-f]{64}$'),
  broker_credential_ref uuid,
  credential_ref_sha256 text
    check (credential_ref_sha256 is null or credential_ref_sha256 ~ '^[0-9a-f]{64}$'),
  current_flow_nonce_sha256 text
    check (current_flow_nonce_sha256 is null or current_flow_nonce_sha256 ~ '^[0-9a-f]{64}$'),
  authorization_expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_app_connections_authority_shape check (
    (authorization_state = 'active'
      and authorization_revision >= 1
      and authorization_snapshot_sha256 is not null
      and granted_actions is not null
      and granted_actions_sha256 is not null
      and granted_scopes_sha256 is not null
      and external_account_id_sha256 is not null
      and broker_credential_ref is not null
      and credential_ref_sha256 is not null
      and revoked_at is null)
    or (authorization_state = 'pending'
      and authorization_revision >= 0
      and broker_credential_ref is null
      and credential_ref_sha256 is null
      and revoked_at is null)
    or (authorization_state = 'revoked'
      and broker_credential_ref is null
      and credential_ref_sha256 is null
      and revoked_at is not null)
  )
);
comment on table connected_app_private.connections is 'ASK_CRUMP_CONNECTED_APP_CONNECTIONS_V1_CONTENT_FREE';
create unique index if not exists connected_app_connections_owner_id_idx
  on connected_app_private.connections(owner_id, id);
create unique index if not exists connected_app_connections_incarnation_idx
  on connected_app_private.connections(id, connection_incarnation_id);
create unique index if not exists connected_app_connections_active_identity_idx
  on connected_app_private.connections(owner_id, provider, resource, external_account_id_sha256)
  where authorization_state = 'active';
create unique index if not exists connected_app_connections_active_broker_ref_idx
  on connected_app_private.connections(broker_credential_ref)
  where authorization_state = 'active';

create table if not exists connected_app_private.oauth_flows (
  flow_id uuid primary key,
  nonce_id uuid not null,
  owner_id uuid not null references public.users(id) on delete cascade,
  connection_id uuid not null references connected_app_private.connections(id) on delete cascade,
  connection_incarnation_id uuid not null,
  expected_base_revision bigint not null check (expected_base_revision >= 0),
  current_flow_nonce_sha256 text not null check (current_flow_nonce_sha256 ~ '^[0-9a-f]{64}$'),
  session_binding_sha256 text not null check (session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  account_kind text not null check (account_kind in ('personal', 'work_school')),
  actions text[] not null check (cardinality(actions) between 1 and 16),
  actions_sha256 text not null check (actions_sha256 ~ '^[0-9a-f]{64}$'),
  requested_scopes_sha256 text not null check (requested_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  state_sha256 text not null check (state_sha256 ~ '^[0-9a-f]{64}$'),
  pkce_challenge text not null check (pkce_challenge ~ '^[A-Za-z0-9_-]{43}$'),
  redirect_uri_sha256 text not null check (redirect_uri_sha256 ~ '^[0-9a-f]{64}$'),
  flow_binding_sha256 text not null check (flow_binding_sha256 ~ '^[0-9a-f]{64}$'),
  broker_start_receipt_sha256 text not null check (broker_start_receipt_sha256 ~ '^[0-9a-f]{64}$'),
  status text not null default 'pending'
    check (status in ('pending', 'consumed', 'exchanged', 'completed', 'invalidated')),
  consumption_id uuid,
  consume_binding_sha256 text
    check (consume_binding_sha256 is null or consume_binding_sha256 ~ '^[0-9a-f]{64}$'),
  consumed_at timestamptz,
  completion_id uuid,
  completion_binding_sha256 text
    check (completion_binding_sha256 is null or completion_binding_sha256 ~ '^[0-9a-f]{64}$'),
  completion_broker_credential_ref uuid,
  completion_credential_ref_sha256 text
    check (completion_credential_ref_sha256 is null or completion_credential_ref_sha256 ~ '^[0-9a-f]{64}$'),
  completion_authorization_revision bigint
    check (completion_authorization_revision is null or completion_authorization_revision >= 1),
  completion_authorization_snapshot_sha256 text
    check (completion_authorization_snapshot_sha256 is null or completion_authorization_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  completion_external_account_id_sha256 text
    check (completion_external_account_id_sha256 is null or completion_external_account_id_sha256 ~ '^[0-9a-f]{64}$'),
  completion_granted_actions text[]
    check (completion_granted_actions is null or cardinality(completion_granted_actions) between 1 and 16),
  completion_granted_actions_sha256 text
    check (completion_granted_actions_sha256 is null or completion_granted_actions_sha256 ~ '^[0-9a-f]{64}$'),
  completion_granted_scopes_sha256 text
    check (completion_granted_scopes_sha256 is null or completion_granted_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  completion_authorization_expires_at timestamptz,
  created_at timestamptz not null,
  expires_at timestamptz not null,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_app_oauth_flows_time_check check (expires_at > created_at),
  constraint connected_app_oauth_flows_consumption_shape check (
    (status = 'pending' and consumption_id is null and consume_binding_sha256 is null
      and consumed_at is null and completion_id is null
      and completion_binding_sha256 is null
      and completion_broker_credential_ref is null
      and completion_credential_ref_sha256 is null
      and completion_authorization_revision is null
      and completion_authorization_snapshot_sha256 is null
      and completion_external_account_id_sha256 is null
      and completion_granted_actions is null
      and completion_granted_actions_sha256 is null
      and completion_granted_scopes_sha256 is null
      and completion_authorization_expires_at is null)
    or (status = 'invalidated' and (
      (consumption_id is null and consume_binding_sha256 is null and consumed_at is null)
      or (consumption_id is not null and consume_binding_sha256 is not null and consumed_at is not null)
    ) and completion_id is null and completion_binding_sha256 is null
      and completion_broker_credential_ref is null
      and completion_credential_ref_sha256 is null
      and completion_authorization_revision is null
      and completion_authorization_snapshot_sha256 is null
      and completion_external_account_id_sha256 is null
      and completion_granted_actions is null
      and completion_granted_actions_sha256 is null
      and completion_granted_scopes_sha256 is null
      and completion_authorization_expires_at is null)
    or (status in ('consumed', 'exchanged')
      and consumption_id is not null
      and consume_binding_sha256 is not null
      and consumed_at is not null
      and completion_id is null
      and completion_binding_sha256 is null
      and completion_broker_credential_ref is null
      and completion_credential_ref_sha256 is null
      and completion_authorization_revision is null
      and completion_authorization_snapshot_sha256 is null
      and completion_external_account_id_sha256 is null
      and completion_granted_actions is null
      and completion_granted_actions_sha256 is null
      and completion_granted_scopes_sha256 is null
      and completion_authorization_expires_at is null)
    or (status = 'completed'
      and consumption_id is not null
      and consume_binding_sha256 is not null
      and consumed_at is not null
      and completion_id is not null
      and completion_binding_sha256 is not null
      and completion_broker_credential_ref is not null
      and completion_credential_ref_sha256 is not null
      and completion_authorization_revision is not null
      and completion_authorization_snapshot_sha256 is not null
      and completion_external_account_id_sha256 is not null
      and completion_granted_actions is not null
      and completion_granted_actions_sha256 is not null
      and completion_granted_scopes_sha256 is not null)
  )
);
comment on table connected_app_private.oauth_flows is 'ASK_CRUMP_CONNECTED_APP_OAUTH_FLOWS_V1_NO_RAW_SECRETS';
create unique index if not exists connected_app_oauth_flow_nonce_idx
  on connected_app_private.oauth_flows(connection_id, current_flow_nonce_sha256);
create unique index if not exists connected_app_oauth_consumption_idx
  on connected_app_private.oauth_flows(consumption_id) where consumption_id is not null;
create index if not exists connected_app_oauth_flow_expiry_idx
  on connected_app_private.oauth_flows(expires_at, flow_id)
  where status in ('pending', 'consumed', 'exchanged');
create index if not exists connected_app_oauth_flow_owner_fk_idx
  on connected_app_private.oauth_flows(owner_id, flow_id);

create table if not exists connected_app_private.oauth_exchange_permits (
  permit_id uuid primary key,
  flow_id uuid not null references connected_app_private.oauth_flows(flow_id) on delete cascade,
  connection_id uuid not null references connected_app_private.connections(id) on delete cascade,
  exchange_id uuid not null,
  capability_sha256 text not null check (capability_sha256 ~ '^[0-9a-f]{64}$'),
  permit_binding_sha256 text not null check (permit_binding_sha256 ~ '^[0-9a-f]{64}$'),
  exchange_binding_sha256 text not null check (exchange_binding_sha256 ~ '^[0-9a-f]{64}$'),
  status text not null default 'issued'
    check (status in ('issued', 'attempt_fenced', 'terminal', 'expired')),
  dispatch_fence_id uuid,
  issued_at timestamptz not null,
  deadline_at timestamptz not null,
  consumed_at timestamptz,
  terminal_sha256 text check (terminal_sha256 is null or terminal_sha256 ~ '^[0-9a-f]{64}$'),
  terminal_completion_id uuid,
  terminal_flow_id uuid,
  terminal_connection_id uuid,
  terminal_broker_credential_ref uuid,
  terminal_credential_ref_sha256 text
    check (terminal_credential_ref_sha256 is null or terminal_credential_ref_sha256 ~ '^[0-9a-f]{64}$'),
  terminal_authorization_revision bigint
    check (terminal_authorization_revision is null or terminal_authorization_revision >= 1),
  constraint connected_app_oauth_permit_time_check check (deadline_at > issued_at),
  constraint connected_app_oauth_permit_fence_shape check (
    (status = 'issued' and dispatch_fence_id is null and consumed_at is null)
    or (status = 'attempt_fenced' and dispatch_fence_id is not null and consumed_at is not null
      and terminal_sha256 is null and terminal_completion_id is null)
    or (status = 'terminal' and dispatch_fence_id is not null and consumed_at is not null
      and terminal_sha256 is not null
      and terminal_completion_id is not null
      and terminal_flow_id is not null
      and terminal_connection_id is not null
      and terminal_broker_credential_ref is not null
      and terminal_credential_ref_sha256 is not null
      and terminal_authorization_revision is not null)
    or (status = 'expired' and dispatch_fence_id is not null and consumed_at is null
      and terminal_sha256 is null and terminal_completion_id is null
      and terminal_flow_id is null and terminal_connection_id is null
      and terminal_broker_credential_ref is null
      and terminal_credential_ref_sha256 is null
      and terminal_authorization_revision is null)
  )
);
comment on table connected_app_private.oauth_exchange_permits is 'ASK_CRUMP_CONNECTED_APP_OAUTH_PERMITS_V1_NO_PROVIDER_SECRETS';
create unique index if not exists connected_app_oauth_exchange_once_idx
  on connected_app_private.oauth_exchange_permits(exchange_id, exchange_binding_sha256);
create unique index if not exists connected_app_oauth_permit_capability_idx
  on connected_app_private.oauth_exchange_permits(capability_sha256);
create index if not exists connected_app_oauth_permit_expiry_idx
  on connected_app_private.oauth_exchange_permits(deadline_at, permit_id)
  where status = 'issued';
create index if not exists connected_app_oauth_permit_flow_fk_idx
  on connected_app_private.oauth_exchange_permits(flow_id, permit_id);
create index if not exists connected_app_oauth_permit_connection_fk_idx
  on connected_app_private.oauth_exchange_permits(connection_id, permit_id);

-- This queue intentionally has no owner/user foreign key and contains no
-- provider token.  It survives account cascade long enough for the broker to
-- revoke one opaque UUID reference, then is deleted.
create table if not exists connected_app_private.credential_cleanup_outbox (
  cleanup_id uuid primary key,
  broker_credential_ref uuid not null,
  credential_ref_sha256 text not null check (credential_ref_sha256 ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google', 'microsoft')),
  reason text not null check (reason in ('stale_connection', 'connection_revoked', 'owner_deleted', 'rotation')),
  cleanup_binding_sha256 text not null check (cleanup_binding_sha256 ~ '^[0-9a-f]{64}$'),
  status text not null default 'queued'
    check (status in ('queued', 'leased', 'completed', 'failed_permanent')),
  attempts integer not null default 0 check (attempts between 0 and 8),
  next_attempt_at timestamptz not null default pg_catalog.clock_timestamp(),
  lease_id uuid,
  lease_expires_at timestamptz,
  terminal_lease_id uuid,
  terminal_at timestamptz,
  recovery_id uuid,
  recovery_count integer not null default 0 check (recovery_count between 0 and 8),
  delete_after timestamptz not null default (pg_catalog.clock_timestamp() + interval '7 days'),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_app_cleanup_retention_check check (
    delete_after > created_at and delete_after <= created_at + interval '30 days'
  ),
  constraint connected_app_cleanup_lease_shape check (
    (status = 'leased' and lease_id is not null and lease_expires_at is not null)
    or (status <> 'leased' and lease_id is null and lease_expires_at is null)
  ),
  constraint connected_app_cleanup_terminal_shape check (
    (status in ('completed', 'failed_permanent')
      and terminal_at is not null and terminal_lease_id is not null)
    or (status in ('queued', 'leased')
      and terminal_at is null and terminal_lease_id is null)
  )
);
comment on table connected_app_private.credential_cleanup_outbox is 'ASK_CRUMP_CONNECTED_APP_CREDENTIAL_CLEANUP_V1_UNLINKED';
create unique index if not exists connected_app_cleanup_binding_idx
  on connected_app_private.credential_cleanup_outbox(cleanup_binding_sha256);
create index if not exists connected_app_cleanup_ready_idx
  on connected_app_private.credential_cleanup_outbox(next_attempt_at, created_at, cleanup_id)
  where status = 'queued';
create index if not exists connected_app_cleanup_expired_lease_idx
  on connected_app_private.credential_cleanup_outbox(lease_expires_at, cleanup_id)
  where status = 'leased';
create unique index if not exists connected_app_cleanup_lease_id_idx
  on connected_app_private.credential_cleanup_outbox(lease_id)
  where lease_id is not null;
create unique index if not exists connected_app_cleanup_terminal_lease_id_idx
  on connected_app_private.credential_cleanup_outbox(terminal_lease_id)
  where terminal_lease_id is not null;
create unique index if not exists connected_app_cleanup_recovery_id_idx
  on connected_app_private.credential_cleanup_outbox(recovery_id)
  where recovery_id is not null;

-- A credential handle that has ever entered cleanup is permanently retired.
-- This content-free tombstone survives bounded outbox purging so a broker bug
-- or reference reuse can never make an old cleanup command target new live
-- authority.
create table if not exists connected_app_private.credential_ref_tombstones (
  credential_ref_sha256 text primary key
    check (credential_ref_sha256 ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google', 'microsoft')),
  retired_at timestamptz not null default pg_catalog.clock_timestamp()
);
comment on table connected_app_private.credential_ref_tombstones is
  'ASK_CRUMP_CONNECTED_APP_CREDENTIAL_REF_TOMBSTONES_V1_CONTENT_FREE_PERMANENT';

create table if not exists connected_app_private.task_grants (
  grant_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  task_id uuid not null,
  turn_id uuid not null,
  connection_id uuid not null references connected_app_private.connections(id) on delete cascade,
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  authorization_revision bigint not null check (authorization_revision >= 1),
  authorization_snapshot_sha256 text not null check (authorization_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  actions text[] not null check (cardinality(actions) between 1 and 16),
  actions_sha256 text not null check (actions_sha256 ~ '^[0-9a-f]{64}$'),
  task_state_revision bigint not null check (task_state_revision >= 1),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  unique(owner_id, task_id, turn_id, connection_id, grant_id)
);
comment on table connected_app_private.task_grants is 'ASK_CRUMP_CONNECTED_APP_TASK_GRANTS_V1_CONTENT_FREE';
create index if not exists connected_app_task_grants_live_idx
  on connected_app_private.task_grants(owner_id, task_id, turn_id, connection_id, expires_at)
  where revoked_at is null;
create index if not exists connected_app_task_grants_owner_fk_idx
  on connected_app_private.task_grants(owner_id, grant_id);
create index if not exists connected_app_task_grants_connection_fk_idx
  on connected_app_private.task_grants(connection_id, grant_id);

create table if not exists connected_app_private.approvals (
  approval_id uuid primary key,
  action_id uuid not null,
  owner_id uuid not null references public.users(id) on delete cascade,
  task_id uuid not null,
  turn_id uuid not null,
  connection_id uuid not null references connected_app_private.connections(id) on delete cascade,
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  action text not null,
  authorization_revision bigint not null check (authorization_revision >= 1),
  authorization_snapshot_sha256 text not null check (authorization_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  approval_class text not null check (approval_class in ('external_write_reversible', 'external_communication', 'calendar_write', 'destructive')),
  parameters_sha256 text not null check (parameters_sha256 ~ '^[0-9a-f]{64}$'),
  resource_version_sha256 text check (resource_version_sha256 is null or resource_version_sha256 ~ '^[0-9a-f]{64}$'),
  approval_binding_sha256 text not null check (approval_binding_sha256 ~ '^[0-9a-f]{64}$'),
  approved_at timestamptz not null,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  consumed_by_operation_id uuid,
  constraint connected_app_approval_time_check check (
    expires_at > approved_at and expires_at <= approved_at + interval '15 minutes'
  ),
  constraint connected_app_approval_consumed_shape check (
    (consumed_at is null and consumed_by_operation_id is null)
    or (consumed_at is not null and consumed_by_operation_id is not null)
  )
);
comment on table connected_app_private.approvals is 'ASK_CRUMP_CONNECTED_APP_APPROVALS_V1_ONE_USE';
comment on column connected_app_private.approvals.parameters_sha256 is
  'ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PAYLOAD_COMMITMENT_V1_NOT_PLAINTEXT_REQUEST_DIGEST';
create unique index if not exists connected_app_approval_binding_idx
  on connected_app_private.approvals(approval_binding_sha256);
create index if not exists connected_app_approval_live_idx
  on connected_app_private.approvals(owner_id, connection_id, expires_at)
  where consumed_at is null;
create index if not exists connected_app_approvals_owner_fk_idx
  on connected_app_private.approvals(owner_id, approval_id);
create index if not exists connected_app_approvals_connection_fk_idx
  on connected_app_private.approvals(connection_id, approval_id);

-- Pending user review is separate from the one-use execution approval above.
-- The review row contains only hashes and an opaque encrypted-payload handle;
-- plaintext mail/calendar preview content remains in the payload vault.
create table if not exists connected_app_private.approval_reviews (
  approval_id uuid primary key,
  action_id uuid not null unique,
  owner_id uuid not null references public.users(id) on delete cascade,
  task_id uuid not null,
  turn_id uuid not null,
  connection_id uuid not null references connected_app_private.connections(id) on delete cascade,
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  action text not null,
  authorization_revision bigint not null check (authorization_revision >= 1),
  authorization_snapshot_sha256 text not null check (authorization_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  granted_scopes_sha256 text not null check (granted_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  policy_version text not null check (length(policy_version) between 1 and 128),
  action_revision bigint not null default 1 check (action_revision >= 1),
  approval_class text not null check (approval_class in ('external_write_reversible', 'external_communication', 'calendar_write', 'destructive')),
  approval_binding_sha256 text not null unique check (approval_binding_sha256 ~ '^[0-9a-f]{64}$'),
  parameters_sha256 text not null check (parameters_sha256 ~ '^[0-9a-f]{64}$'),
  resource_version_sha256 text check (resource_version_sha256 is null or resource_version_sha256 ~ '^[0-9a-f]{64}$'),
  preview_sha256 text not null check (preview_sha256 ~ '^[0-9a-f]{64}$'),
  review_payload_ref uuid not null,
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'denied')),
  decision_id uuid unique,
  decision_session_binding_sha256 text
    check (decision_session_binding_sha256 is null or decision_session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  decided_at timestamptz,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_app_approval_review_time_check check (
    expires_at > created_at and expires_at <= created_at + interval '15 minutes'
  ),
  constraint connected_app_approval_review_decision_shape check (
    (status = 'pending' and decision_id is null
      and decision_session_binding_sha256 is null and decided_at is null)
    or (status in ('approved', 'denied') and decision_id is not null
      and decision_session_binding_sha256 is not null and decided_at is not null)
  )
);
comment on table connected_app_private.approval_reviews is
  'ASK_CRUMP_CONNECTED_APP_APPROVAL_REVIEWS_V1_PAYLOAD_REFERENCE_ONLY';
comment on column connected_app_private.approval_reviews.parameters_sha256 is
  'ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PAYLOAD_COMMITMENT_V1_NOT_PLAINTEXT_REQUEST_DIGEST';
comment on column connected_app_private.approval_reviews.preview_sha256 is
  'ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PREVIEW_COMMITMENT_V1_NOT_PREDICTABLE_CONTENT_DIGEST';
create index if not exists connected_app_approval_reviews_owner_idx
  on connected_app_private.approval_reviews(owner_id, updated_at desc, approval_id);
create index if not exists connected_app_approval_reviews_connection_idx
  on connected_app_private.approval_reviews(connection_id, approval_id);

-- One authenticated ordinary-language request becomes either an execution-
-- ready read or a write awaiting exact owner review.  Customer content and
-- predictable request digests remain exclusively inside encrypted payload
-- envelopes; this row holds only opaque IDs and keyed commitments.
create table if not exists connected_app_private.action_preparations (
  request_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  session_binding_sha256 text not null
    check (session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  command_binding_sha256 text not null unique
    check (command_binding_sha256 ~ '^[0-9a-f]{64}$'),
  grant_id uuid not null unique
    references connected_app_private.task_grants(grant_id) on delete cascade,
  action_id uuid not null unique,
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
  grant_actions_sha256 text not null
    check (grant_actions_sha256 ~ '^[0-9a-f]{64}$'),
  task_state_revision bigint not null check (task_state_revision >= 1),
  payload_id uuid not null unique,
  payload_reference_binding_sha256 text not null
    check (payload_reference_binding_sha256 ~ '^[0-9a-f]{64}$'),
  parameters_sha256 text not null
    check (parameters_sha256 ~ '^[0-9a-f]{64}$'),
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
  status text not null check (status in ('ready', 'pending_approval')),
  approval_id uuid unique
    references connected_app_private.approval_reviews(approval_id) on delete cascade,
  approval_binding_sha256 text unique
    check (approval_binding_sha256 is null or approval_binding_sha256 ~ '^[0-9a-f]{64}$'),
  preview_payload_id uuid unique,
  preview_reference_binding_sha256 text
    check (
      preview_reference_binding_sha256 is null
      or preview_reference_binding_sha256 ~ '^[0-9a-f]{64}$'
    ),
  preview_sha256 text
    check (preview_sha256 is null or preview_sha256 ~ '^[0-9a-f]{64}$'),
  requested_at timestamptz not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_app_action_preparation_lifetime check (
    expires_at > requested_at and expires_at <= requested_at + interval '15 minutes'
  ),
  constraint connected_app_action_preparation_authority_shape check (
    (not mutates_external_state and approval_class = 'none' and status = 'ready')
    or (mutates_external_state and approval_class <> 'none' and status = 'pending_approval')
  ),
  constraint connected_app_action_preparation_review_shape check (
    (status = 'ready' and approval_id is null
      and approval_binding_sha256 is null and preview_payload_id is null
      and preview_reference_binding_sha256 is null and preview_sha256 is null)
    or (status = 'pending_approval' and approval_id is not null
      and approval_binding_sha256 is not null and preview_payload_id is not null
      and preview_reference_binding_sha256 is not null and preview_sha256 is not null)
  )
);
comment on table connected_app_private.action_preparations is
  'ASK_CRUMP_CONNECTED_APP_ACTION_PREPARATIONS_V1_CONTENT_FREE_NO_EXECUTION';
comment on column connected_app_private.action_preparations.parameters_sha256 is
  'ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PAYLOAD_COMMITMENT_V1_NOT_PLAINTEXT_REQUEST_DIGEST';
comment on column connected_app_private.action_preparations.preview_sha256 is
  'ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PREVIEW_COMMITMENT_V1_NOT_PREDICTABLE_CONTENT_DIGEST';
create index if not exists connected_app_action_preparations_owner_idx
  on connected_app_private.action_preparations(owner_id, requested_at desc, request_id);
create index if not exists connected_app_action_preparations_connection_idx
  on connected_app_private.action_preparations(connection_id, action_id);
create index if not exists connected_app_action_preparations_expiry_idx
  on connected_app_private.action_preparations(expires_at, request_id);

create sequence if not exists connected_app_private.action_fencing_token_seq
  as bigint start with 1 increment by 1 no minvalue no maxvalue cache 1;
comment on sequence connected_app_private.action_fencing_token_seq is
  'ASK_CRUMP_CONNECTED_APP_ACTION_FENCING_TOKEN_V1_DATABASE_ALLOCATED';

create table if not exists connected_app_private.action_ledger (
  operation_id uuid primary key,
  action_id uuid not null,
  owner_id uuid not null references public.users(id) on delete cascade,
  task_id uuid not null,
  turn_id uuid not null,
  connection_id uuid not null references connected_app_private.connections(id) on delete cascade,
  grant_id uuid not null references connected_app_private.task_grants(grant_id) on delete cascade,
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  action text not null,
  authorization_revision bigint not null check (authorization_revision >= 1),
  authorization_snapshot_sha256 text not null check (authorization_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  granted_actions_sha256 text not null check (granted_actions_sha256 ~ '^[0-9a-f]{64}$'),
  granted_scopes_sha256 text not null check (granted_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  parameters_sha256 text not null check (parameters_sha256 ~ '^[0-9a-f]{64}$'),
  resource_version_sha256 text check (resource_version_sha256 is null or resource_version_sha256 ~ '^[0-9a-f]{64}$'),
  authority_sha256 text not null check (authority_sha256 ~ '^[0-9a-f]{64}$'),
  idempotency_key_sha256 text not null check (idempotency_key_sha256 ~ '^[0-9a-f]{64}$'),
  task_state_revision bigint not null check (task_state_revision >= 1),
  status text not null default 'claimed'
    check (status in ('claimed', 'access_granted', 'effect_possible', 'terminal')),
  mutates_external_state boolean not null,
  approval_class text not null check (
    approval_class in (
      'none', 'external_write_reversible', 'external_communication',
      'calendar_write', 'destructive'
    )
  ),
  claim_request_id uuid not null,
  claim_id uuid not null,
  fencing_token bigint not null default
    pg_catalog.nextval('connected_app_private.action_fencing_token_seq'::regclass)
    check (fencing_token >= 1),
  lease_expires_at timestamptz not null,
  execution_deadline timestamptz not null,
  access_phase text check (access_phase is null or access_phase in ('read', 'preobserve')),
  read_use_nonce uuid,
  read_credential_expires_at timestamptz,
  read_consumed_at timestamptz,
  preobserve_use_nonce uuid,
  preobserve_credential_expires_at timestamptz,
  preobserve_consumed_at timestamptz,
  access_started_at timestamptz,
  effect_use_nonce uuid,
  effect_credential_expires_at timestamptz,
  effect_consumed_at timestamptz,
  effect_started_at timestamptz,
  postobserve_use_nonce uuid,
  postobserve_started_at timestamptz,
  postobserve_expires_at timestamptz,
  postobserve_consumed_at timestamptz,
  postobserve_impossible boolean not null default false,
  terminal_outcome text check (terminal_outcome is null or terminal_outcome in ('read', 'succeeded', 'ambiguous', 'failed')),
  terminal_binding_sha256 text check (terminal_binding_sha256 is null or terminal_binding_sha256 ~ '^[0-9a-f]{64}$'),
  provider_request_id_sha256 text check (provider_request_id_sha256 is null or provider_request_id_sha256 ~ '^[0-9a-f]{64}$'),
  provider_resource_id_sha256 text check (provider_resource_id_sha256 is null or provider_resource_id_sha256 ~ '^[0-9a-f]{64}$'),
  observed_at timestamptz,
  terminal_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_app_action_deadline_check check (execution_deadline > created_at),
  constraint connected_app_action_authority_shape check (
    (not mutates_external_state and approval_class = 'none')
    or (mutates_external_state and approval_class <> 'none')
  ),
  constraint connected_app_action_postobserve_shape check (
    not postobserve_impossible
    or (
      status = 'terminal'
      and mutates_external_state
      and terminal_outcome = 'ambiguous'
      and postobserve_use_nonce is null
      and postobserve_started_at is null
      and postobserve_expires_at is null
    )
  ),
  constraint connected_app_action_credential_use_shape check (
    (read_use_nonce is null) = (read_credential_expires_at is null)
    and (preobserve_use_nonce is null) = (preobserve_credential_expires_at is null)
    and (effect_use_nonce is null) = (effect_credential_expires_at is null)
    and (postobserve_use_nonce is null) = (postobserve_expires_at is null)
    and (read_consumed_at is null or read_use_nonce is not null)
    and (preobserve_consumed_at is null or preobserve_use_nonce is not null)
    and (effect_consumed_at is null or effect_use_nonce is not null)
    and (postobserve_consumed_at is null or postobserve_use_nonce is not null)
  ),
  constraint connected_app_action_state_shape check (
    (status = 'claimed' and read_use_nonce is null and preobserve_use_nonce is null
      and effect_use_nonce is null and terminal_at is null)
    or (status = 'access_granted' and access_phase = 'read'
      and read_use_nonce is not null and preobserve_use_nonce is null
      and read_credential_expires_at is not null
      and access_started_at is not null and effect_use_nonce is null and terminal_at is null)
    or (status = 'access_granted' and access_phase = 'preobserve'
      and read_use_nonce is null and preobserve_use_nonce is not null
      and preobserve_credential_expires_at is not null
      and access_started_at is not null and effect_use_nonce is null and terminal_at is null)
    or (status = 'effect_possible' and access_phase = 'preobserve'
      and preobserve_use_nonce is not null and effect_use_nonce is not null
      and effect_credential_expires_at is not null
      and effect_started_at is not null and terminal_at is null)
    or (status = 'terminal' and terminal_outcome is not null and terminal_binding_sha256 is not null and terminal_at is not null)
  )
);
comment on table connected_app_private.action_ledger is 'ASK_CRUMP_CONNECTED_APP_ACTION_LEDGER_V1_CONTENT_FREE';
comment on column connected_app_private.action_ledger.parameters_sha256 is
  'ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PAYLOAD_COMMITMENT_V1_NOT_PLAINTEXT_REQUEST_DIGEST';
create unique index if not exists connected_app_action_idempotency_idx
  on connected_app_private.action_ledger(owner_id, connection_id, idempotency_key_sha256);
create unique index if not exists connected_app_action_claim_idx
  on connected_app_private.action_ledger(claim_id, fencing_token);
create index if not exists connected_app_action_grant_idx
  on connected_app_private.action_ledger(grant_id, operation_id);
create index if not exists connected_app_action_access_recovery_idx
  on connected_app_private.action_ledger(lease_expires_at, operation_id)
  where status = 'access_granted';
create index if not exists connected_app_action_effect_reconcile_idx
  on connected_app_private.action_ledger(execution_deadline, operation_id)
  where status = 'effect_possible';
create index if not exists connected_app_action_connection_fk_idx
  on connected_app_private.action_ledger(connection_id, operation_id);

create table if not exists connected_app_private.schedules (
  schedule_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  connection_id uuid not null references connected_app_private.connections(id) on delete cascade,
  task_id uuid not null,
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  action text not null,
  action_template_ref uuid not null,
  parameters_sha256 text not null check (parameters_sha256 ~ '^[0-9a-f]{64}$'),
  task_state_revision bigint not null check (task_state_revision >= 1),
  time_zone text not null check (length(time_zone) between 1 and 100),
  cadence_seconds integer not null check (cadence_seconds between 60 and 2678400),
  quiet_start_minute integer check (quiet_start_minute between 0 and 1439),
  quiet_end_minute integer check (quiet_end_minute between 0 and 1439),
  requires_approval_every_run boolean not null,
  status text not null default 'active' check (status in ('active', 'paused', 'cancelled')),
  next_run_at timestamptz,
  claim_id uuid,
  claim_expires_at timestamptz,
  completed_claim_id uuid,
  completed_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_app_schedule_quiet_shape check (
    (quiet_start_minute is null and quiet_end_minute is null)
    or (quiet_start_minute is not null and quiet_end_minute is not null)
  ),
  constraint connected_app_schedule_claim_shape check (
    (claim_id is null and claim_expires_at is null)
    or (claim_id is not null and claim_expires_at is not null)
  ),
  constraint connected_app_schedule_completion_shape check (
    (completed_claim_id is null and completed_at is null)
    or (completed_claim_id is not null and completed_at is not null)
  ),
  constraint connected_app_schedule_status_shape check (
    (status = 'active' and next_run_at is not null)
    or (status in ('paused', 'cancelled') and next_run_at is null)
  )
);
comment on table connected_app_private.schedules is 'ASK_CRUMP_CONNECTED_APP_SCHEDULES_V1_PAYLOAD_REFERENCE_ONLY';
comment on column connected_app_private.schedules.parameters_sha256 is
  'ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PAYLOAD_COMMITMENT_V1_NOT_PLAINTEXT_REQUEST_DIGEST';
create index if not exists connected_app_schedule_ready_idx
  on connected_app_private.schedules(next_run_at, schedule_id)
  where status = 'active';
create unique index if not exists connected_app_schedule_claim_id_idx
  on connected_app_private.schedules(claim_id) where claim_id is not null;
create index if not exists connected_app_schedules_owner_fk_idx
  on connected_app_private.schedules(owner_id, schedule_id);
create index if not exists connected_app_schedules_connection_fk_idx
  on connected_app_private.schedules(connection_id, schedule_id);

-- Idempotent owner commands retain only exact command/result identities.  A
-- command never stores provider payload, OAuth state/code, or customer text.
create table if not exists connected_app_private.operator_commands (
  request_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  command_kind text not null check (
    command_kind in ('disconnect', 'schedule_create', 'schedule_transition')
  ),
  subject_id uuid not null,
  session_binding_sha256 text not null check (session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  command_binding_sha256 text not null check (command_binding_sha256 ~ '^[0-9a-f]{64}$'),
  requested_at timestamptz not null,
  completed_at timestamptz not null,
  unique(owner_id, command_kind, subject_id, request_id)
);
comment on table connected_app_private.operator_commands is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_COMMANDS_V1_CONTENT_FREE_IDEMPOTENCY';
create index if not exists connected_app_operator_commands_owner_idx
  on connected_app_private.operator_commands(owner_id, command_kind, request_id);

do $rls$
declare
  table_name text;
begin
  foreach table_name in array array[
    'action_authority', 'action_preparations', 'connections',
    'oauth_flows', 'oauth_exchange_permits',
    'credential_cleanup_outbox', 'credential_ref_tombstones', 'task_grants', 'approvals',
    'approval_reviews', 'action_ledger', 'schedules', 'operator_commands'
  ] loop
    execute pg_catalog.format(
      'alter table connected_app_private.%I enable row level security',
      table_name
    );
    execute pg_catalog.format(
      'alter table connected_app_private.%I force row level security',
      table_name
    );
    execute pg_catalog.format(
      'revoke all on table connected_app_private.%I from public, anon, authenticated, service_role',
      table_name
    );
  end loop;
end;
$rls$;

revoke all on all sequences in schema connected_app_private from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema connected_app_private
  revoke all on tables from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema connected_app_private
  revoke all on sequences from public, anon, authenticated, service_role;

create or replace function connected_app_private.owner_lock_v1(p_owner_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $fn$
begin
  if p_owner_id is null then
    raise exception 'owner id is required' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_owner_id::text, 606232723337443413::bigint)
  );
end;
$fn$;
comment on function connected_app_private.owner_lock_v1(uuid) is
  'ASK_CRUMP_CONNECTED_APP_OWNER_LOCK_V1_INTERNAL';
revoke all on function connected_app_private.owner_lock_v1(uuid)
  from public, anon, authenticated, service_role;

create or replace function public.connected_app_get_binding_v1(
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
  where connection.id = p_connection_id
    and connection.owner_id = p_owner_id;

  if not found then
    return null;
  end if;

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
    'granted_actions', connection_row.granted_actions,
    'granted_actions_sha256', connection_row.granted_actions_sha256,
    'granted_scopes_sha256', connection_row.granted_scopes_sha256,
    'external_account_id_sha256', connection_row.external_account_id_sha256,
    'broker_credential_ref', connection_row.broker_credential_ref,
    'current_flow_nonce_sha256', connection_row.current_flow_nonce_sha256,
    'authorization_expires_at', connection_row.authorization_expires_at,
    'revoked_at', connection_row.revoked_at
  );
end;
$fn$;
comment on function public.connected_app_get_binding_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_GET_BINDING_V1_SERVICE_ROLE_ONLY';

create or replace function public.connected_app_oauth_create_pending_v1(
  p_flow_id uuid,
  p_nonce_id uuid,
  p_owner_id uuid,
  p_connection_id uuid,
  p_connection_incarnation_id uuid,
  p_expected_base_revision bigint,
  p_current_flow_nonce_sha256 text,
  p_session_binding_sha256 text,
  p_provider text,
  p_resource text,
  p_account_kind text,
  p_actions text[],
  p_actions_sha256 text,
  p_requested_scopes_sha256 text,
  p_state_sha256 text,
  p_pkce_challenge text,
  p_redirect_uri_sha256 text,
  p_flow_binding_sha256 text,
  p_broker_start_receipt_sha256 text,
  p_created_at timestamptz,
  p_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  existing_row connected_app_private.oauth_flows%rowtype;
  result_row connected_app_private.oauth_flows%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_flow_id is null or p_nonce_id is null or p_owner_id is null
     or p_connection_id is null or p_connection_incarnation_id is null
     or pg_catalog.cardinality(p_actions) not between 1 and 16
     or exists (
       select 1 from pg_catalog.unnest(p_actions) as requested(action_name)
       left join connected_app_private.action_authority as authority
         on authority.action = requested.action_name
       where requested.action_name is null
          or authority.action is null
          or authority.resource <> p_resource
     )
     or (select pg_catalog.count(distinct requested.action_name)
         from pg_catalog.unnest(p_actions) as requested(action_name))
        <> pg_catalog.cardinality(p_actions)
     or p_created_at is null or p_expires_at is null
     or p_expires_at <= p_created_at or p_expires_at > p_created_at + interval '10 minutes'
     or p_created_at > now_at + interval '1 minute'
     or p_expires_at <= now_at then
    raise exception 'invalid OAuth pending-flow bounds' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id
    and connection.owner_id = p_owner_id
  for update;
  if not found
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> p_connection_incarnation_id
     or connection_row.authorization_revision <> p_expected_base_revision
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or connection_row.account_kind <> p_account_kind then
    raise exception 'OAuth connection authority changed' using errcode = '55000';
  end if;

  select flow.* into existing_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = p_flow_id
  for update;
  if found then
    if existing_row.owner_id <> p_owner_id
       or existing_row.connection_id <> p_connection_id
       or existing_row.connection_incarnation_id <> p_connection_incarnation_id
       or existing_row.expected_base_revision <> p_expected_base_revision
       or existing_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256
       or existing_row.actions is distinct from p_actions
       or existing_row.actions_sha256 <> p_actions_sha256
       or existing_row.flow_binding_sha256 <> p_flow_binding_sha256
       or existing_row.broker_start_receipt_sha256 <> p_broker_start_receipt_sha256
       or existing_row.status <> 'pending'
       or connection_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256 then
      raise exception 'OAuth pending-flow replay drifted' using errcode = '55000';
    end if;
    return pg_catalog.to_jsonb(existing_row);
  end if;

  update connected_app_private.oauth_flows as older
  set status = 'invalidated', updated_at = now_at
  where older.connection_id = p_connection_id
    and older.status = 'pending';

  update connected_app_private.connections as connection
  set current_flow_nonce_sha256 = p_current_flow_nonce_sha256,
      updated_at = now_at
  where connection.id = p_connection_id;

  insert into connected_app_private.oauth_flows (
    flow_id, nonce_id, owner_id, connection_id, connection_incarnation_id,
    expected_base_revision, current_flow_nonce_sha256, session_binding_sha256,
    provider, resource, account_kind, actions, actions_sha256, requested_scopes_sha256,
    state_sha256, pkce_challenge, redirect_uri_sha256, flow_binding_sha256,
    broker_start_receipt_sha256, created_at, expires_at
  ) values (
    p_flow_id, p_nonce_id, p_owner_id, p_connection_id,
    p_connection_incarnation_id, p_expected_base_revision,
    p_current_flow_nonce_sha256, p_session_binding_sha256, p_provider,
    p_resource, p_account_kind, p_actions, p_actions_sha256,
    p_requested_scopes_sha256, p_state_sha256, p_pkce_challenge,
    p_redirect_uri_sha256, p_flow_binding_sha256,
    p_broker_start_receipt_sha256, p_created_at, p_expires_at
  ) returning * into result_row;
  return pg_catalog.to_jsonb(result_row);
end;
$fn$;
comment on function public.connected_app_oauth_create_pending_v1(
  uuid,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text[],text,text,text,text,text,text,text,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_OAUTH_CREATE_PENDING_V1_SERVICE_ROLE_ONLY';

create or replace function public.connected_app_oauth_consume_pending_v1(
  p_flow_id uuid,
  p_consumption_id uuid,
  p_owner_id uuid,
  p_connection_id uuid,
  p_connection_incarnation_id uuid,
  p_expected_base_revision bigint,
  p_current_flow_nonce_sha256 text,
  p_session_binding_sha256 text,
  p_flow_binding_sha256 text,
  p_consume_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = p_flow_id and flow.connection_id = p_connection_id
  for update;

  if connection_row.id is null or flow_row.flow_id is null
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> p_connection_incarnation_id
     or connection_row.authorization_revision <> p_expected_base_revision
     or connection_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256
     or flow_row.owner_id <> p_owner_id
     or flow_row.connection_incarnation_id <> p_connection_incarnation_id
     or flow_row.expected_base_revision <> p_expected_base_revision
     or flow_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256
     or flow_row.session_binding_sha256 <> p_session_binding_sha256
     or flow_row.flow_binding_sha256 <> p_flow_binding_sha256
     or flow_row.expires_at <= now_at then
    raise exception 'OAuth flow is stale or unavailable' using errcode = '55000';
  end if;

  if flow_row.status <> 'pending' then
    if flow_row.consumption_id = p_consumption_id
       and flow_row.consume_binding_sha256 = p_consume_binding_sha256 then
      return pg_catalog.to_jsonb(flow_row);
    end if;
    raise exception 'OAuth flow was already consumed differently' using errcode = '55000';
  end if;

  update connected_app_private.oauth_flows as flow
  set status = 'consumed',
      consumption_id = p_consumption_id,
      consume_binding_sha256 = p_consume_binding_sha256,
      consumed_at = now_at,
      updated_at = now_at
  where flow.flow_id = p_flow_id
  returning * into flow_row;
  return pg_catalog.to_jsonb(flow_row);
end;
$fn$;
comment on function public.connected_app_oauth_consume_pending_v1(
  uuid,uuid,uuid,uuid,uuid,bigint,text,text,text,text
) is 'ASK_CRUMP_CONNECTED_APP_OAUTH_CONSUME_PENDING_V1_SERVICE_ROLE_ONLY';

create or replace function public.connected_app_oauth_issue_permit_v1(
  p_permit_id uuid,
  p_flow_id uuid,
  p_connection_id uuid,
  p_exchange_id uuid,
  p_capability_sha256 text,
  p_permit_binding_sha256 text,
  p_exchange_binding_sha256 text,
  p_issued_at timestamptz,
  p_deadline_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
  permit_row connected_app_private.oauth_exchange_permits%rowtype;
begin
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
  if connection_row.id is null or flow_row.flow_id is null
     or flow_row.connection_id <> p_connection_id
     or flow_row.status <> 'consumed'
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> flow_row.connection_incarnation_id
     or connection_row.authorization_revision <> flow_row.expected_base_revision
     or connection_row.current_flow_nonce_sha256 <> flow_row.current_flow_nonce_sha256
     or p_issued_at < pg_catalog.clock_timestamp() - interval '1 minute'
     or p_issued_at > pg_catalog.clock_timestamp() + interval '1 minute'
     or p_deadline_at <= p_issued_at
     or p_deadline_at <= pg_catalog.clock_timestamp()
     or p_deadline_at > flow_row.expires_at then
    raise exception 'OAuth permit authority changed' using errcode = '55000';
  end if;

  select permit.* into permit_row
  from connected_app_private.oauth_exchange_permits as permit
  where permit.exchange_id = p_exchange_id
    and permit.exchange_binding_sha256 = p_exchange_binding_sha256
  for update;
  if found then
    if permit_row.permit_id <> p_permit_id
       or permit_row.flow_id <> p_flow_id
       or permit_row.connection_id <> p_connection_id
       or permit_row.exchange_id <> p_exchange_id
       or permit_row.capability_sha256 <> p_capability_sha256
       or permit_row.permit_binding_sha256 <> p_permit_binding_sha256
       or permit_row.exchange_binding_sha256 <> p_exchange_binding_sha256
       or permit_row.issued_at <> p_issued_at
       or permit_row.deadline_at <> p_deadline_at then
      raise exception 'OAuth permit replay drifted' using errcode = '55000';
    end if;
    return pg_catalog.to_jsonb(permit_row) - 'capability_sha256';
  end if;

  insert into connected_app_private.oauth_exchange_permits (
    permit_id, flow_id, connection_id, exchange_id, capability_sha256,
    permit_binding_sha256, exchange_binding_sha256, issued_at, deadline_at
  ) values (
    p_permit_id, p_flow_id, p_connection_id, p_exchange_id,
    p_capability_sha256, p_permit_binding_sha256,
    p_exchange_binding_sha256, p_issued_at, p_deadline_at
  ) returning * into permit_row;
  return pg_catalog.to_jsonb(permit_row) - 'capability_sha256';
end;
$fn$;
comment on function public.connected_app_oauth_issue_permit_v1(
  uuid,uuid,uuid,uuid,text,text,text,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_OAUTH_ISSUE_PERMIT_V1_DIGEST_ONLY';

create or replace function public.connected_app_oauth_consume_permit_v1(
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
    if permit_row.dispatch_fence_id = p_dispatch_fence_id then
      return pg_catalog.to_jsonb(permit_row) - 'capability_sha256';
    end if;
    raise exception 'OAuth exchange permit already consumed' using errcode = '55000';
  end if;
  if now_at >= permit_row.deadline_at then
    update connected_app_private.oauth_exchange_permits as permit
    set status = 'expired', dispatch_fence_id = p_dispatch_fence_id
    where permit.permit_id = p_permit_id
    returning * into permit_row;
    -- Persist the request fence and return the committed terminal transition.
    -- An exact response-loss retry therefore reads the same expired row while
    -- a different fence remains rejected above.
    return pg_catalog.to_jsonb(permit_row) - 'capability_sha256';
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
  return pg_catalog.to_jsonb(permit_row) - 'capability_sha256';
end;
$fn$;
comment on function public.connected_app_oauth_consume_permit_v1(
  uuid,uuid,uuid,uuid,text,text,text,uuid
) is 'ASK_CRUMP_CONNECTED_APP_OAUTH_CONSUME_PERMIT_V1_ATOMIC_LIVE_FENCE';

create or replace function public.connected_app_record_credential_cleanup_v1(
  p_cleanup_id uuid,
  p_broker_credential_ref uuid,
  p_credential_ref_sha256 text,
  p_provider text,
  p_reason text,
  p_cleanup_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  cleanup_row connected_app_private.credential_cleanup_outbox%rowtype;
  tombstone_provider text;
begin
  if p_cleanup_id is null or p_broker_credential_ref is null
     or p_credential_ref_sha256 is null
     or p_credential_ref_sha256 !~ '^[0-9a-f]{64}$'
     or p_cleanup_binding_sha256 is null
     or p_cleanup_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_provider not in ('google', 'microsoft')
     or p_reason not in ('stale_connection', 'connection_revoked', 'owner_deleted', 'rotation') then
    raise exception 'credential cleanup requires exact canonical bindings'
      using errcode = '22023';
  end if;

  -- Serialize cleanup recording, activation, and worker claim for this opaque
  -- credential reference.  The SHA-256 value is already trusted-boundary
  -- material; no raw broker secret is used as an advisory-lock key.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_credential_ref_sha256, 81424519024640287::bigint)
  );
  select tombstone.provider into tombstone_provider
  from connected_app_private.credential_ref_tombstones as tombstone
  where tombstone.credential_ref_sha256 = p_credential_ref_sha256
  for update;
  if found and tombstone_provider <> p_provider then
    raise exception 'credential tombstone provider drifted' using errcode = '55000';
  end if;
  if not found then
    insert into connected_app_private.credential_ref_tombstones (
      credential_ref_sha256, provider
    ) values (p_credential_ref_sha256, p_provider);
  end if;

  select cleanup.* into cleanup_row
  from connected_app_private.credential_cleanup_outbox as cleanup
  where cleanup.cleanup_id = p_cleanup_id
     or cleanup.cleanup_binding_sha256 = p_cleanup_binding_sha256
  for update;
  if found then
    if cleanup_row.cleanup_id <> p_cleanup_id
       or cleanup_row.cleanup_binding_sha256 <> p_cleanup_binding_sha256
       or cleanup_row.broker_credential_ref <> p_broker_credential_ref
       or cleanup_row.credential_ref_sha256 <> p_credential_ref_sha256
       or cleanup_row.provider <> p_provider
       or cleanup_row.reason <> p_reason then
      raise exception 'credential cleanup replay drifted' using errcode = '55000';
    end if;
    return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
  end if;

  insert into connected_app_private.credential_cleanup_outbox (
    cleanup_id, broker_credential_ref, credential_ref_sha256,
    provider, reason, cleanup_binding_sha256
  ) values (
    p_cleanup_id, p_broker_credential_ref, p_credential_ref_sha256,
    p_provider, p_reason, p_cleanup_binding_sha256
  ) returning * into cleanup_row;
  return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
end;
$fn$;
comment on function public.connected_app_record_credential_cleanup_v1(
  uuid,uuid,text,text,text,text
) is 'ASK_CRUMP_CONNECTED_APP_RECORD_CREDENTIAL_CLEANUP_V1_IDEMPOTENT';

create or replace function public.connected_app_oauth_finalize_v1(
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
  p_authorization_expires_at timestamptz,
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
  connection_row connected_app_private.connections%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  permit_row connected_app_private.oauth_exchange_permits%rowtype;
  cleanup_result jsonb;
  duplicate_connection_id uuid;
  next_revision bigint;
  snapshot_sha256 text;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_flow_id is null or p_consumption_id is null or p_exchange_id is null
     or p_dispatch_fence_id is null
     or p_owner_id is null or p_connection_id is null
     or p_connection_incarnation_id is null or p_completion_id is null
     or p_cleanup_id is null
     or p_broker_credential_ref is null
     or p_credential_ref_sha256 is null
     or p_credential_ref_sha256 !~ '^[0-9a-f]{64}$'
     or p_completion_binding_sha256 is null
     or p_completion_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_cleanup_binding_sha256 is null
     or p_cleanup_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'OAuth completion requires exact prehashed identifiers'
      using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = p_flow_id
  for update;
  select permit.* into permit_row
  from connected_app_private.oauth_exchange_permits as permit
  where permit.exchange_id = p_exchange_id
    and permit.exchange_binding_sha256 = p_exchange_binding_sha256
  for update;

  -- Terminal replay is bound to the original completion record, not to the
  -- connection's current-flow fence.  A later authorization flow may have
  -- advanced that fence or rotated the live credential.
  if flow_row.flow_id is not null and permit_row.permit_id is not null
     and flow_row.status = 'completed'
     and flow_row.owner_id = p_owner_id
     and flow_row.connection_id = p_connection_id
     and flow_row.connection_incarnation_id = p_connection_incarnation_id
     and flow_row.expected_base_revision = p_expected_base_revision
     and flow_row.current_flow_nonce_sha256 = p_current_flow_nonce_sha256
     and flow_row.consumption_id = p_consumption_id
     and flow_row.provider = p_provider
     and flow_row.resource = p_resource
     and flow_row.account_kind = p_account_kind
     and flow_row.completion_id = p_completion_id
     and flow_row.completion_binding_sha256 = p_completion_binding_sha256
     and flow_row.completion_broker_credential_ref = p_broker_credential_ref
     and flow_row.completion_credential_ref_sha256 = p_credential_ref_sha256
     and flow_row.completion_authorization_revision = p_expected_base_revision + 1
     and flow_row.completion_external_account_id_sha256 = p_external_account_id_sha256
     and flow_row.completion_granted_actions is not distinct from flow_row.actions
     and flow_row.completion_granted_actions_sha256 = flow_row.actions_sha256
     and flow_row.completion_granted_scopes_sha256 = p_granted_scopes_sha256
     and flow_row.completion_authorization_expires_at is not distinct from p_authorization_expires_at
     and permit_row.status = 'terminal'
     and permit_row.flow_id = p_flow_id
     and permit_row.connection_id = p_connection_id
     and permit_row.exchange_id = p_exchange_id
     and permit_row.exchange_binding_sha256 = p_exchange_binding_sha256
     and permit_row.dispatch_fence_id = p_dispatch_fence_id
     and permit_row.terminal_sha256 = p_completion_binding_sha256
     and permit_row.terminal_completion_id = p_completion_id
     and permit_row.terminal_flow_id = p_flow_id
     and permit_row.terminal_connection_id = p_connection_id
     and permit_row.terminal_broker_credential_ref = p_broker_credential_ref
     and permit_row.terminal_credential_ref_sha256 = p_credential_ref_sha256
     and permit_row.terminal_authorization_revision = p_expected_base_revision + 1 then
    return pg_catalog.jsonb_build_object(
      'completed', true,
      'active', connection_row.id is not null
        and connection_row.authorization_state = 'active'
        and connection_row.authorization_revision = flow_row.completion_authorization_revision
        and connection_row.broker_credential_ref = flow_row.completion_broker_credential_ref,
      'owner_id', flow_row.owner_id,
      'connection_id', flow_row.connection_id,
      'connection_incarnation_id', flow_row.connection_incarnation_id,
      'completion_id', flow_row.completion_id,
      'authorization_revision', flow_row.completion_authorization_revision,
      'authorization_snapshot_sha256', flow_row.completion_authorization_snapshot_sha256,
      'granted_actions', flow_row.completion_granted_actions,
      'granted_actions_sha256', flow_row.completion_granted_actions_sha256,
      'granted_scopes_sha256', flow_row.completion_granted_scopes_sha256,
      'external_account_id_sha256', flow_row.completion_external_account_id_sha256,
      'broker_credential_ref', flow_row.completion_broker_credential_ref,
      'credential_ref_sha256', flow_row.completion_credential_ref_sha256,
      'authorization_expires_at', flow_row.completion_authorization_expires_at
    );
  end if;

  -- Serialize activation against every cleanup/tombstone transition for this
  -- opaque credential reference.  This closes both cleanup/activation winner
  -- orders without relying on a provider promise that handle IDs are unique.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_credential_ref_sha256, 81424519024640287::bigint)
  );

  -- Never enqueue cleanup for a credential that is already live elsewhere;
  -- doing so could revoke unrelated current authority.  This check is under
  -- the same credential lock used by record/claim.
  if exists (
    select 1
    from connected_app_private.connections as live_connection
    where live_connection.authorization_state = 'active'
      and live_connection.id <> p_connection_id
      and (
        live_connection.broker_credential_ref = p_broker_credential_ref
        or live_connection.credential_ref_sha256 = p_credential_ref_sha256
      )
  ) then
    return pg_catalog.jsonb_build_object(
      'completed', false, 'active', false, 'cleanup_enqueued', false,
      'current_live_credential', true
    );
  end if;

  if connection_row.id is null or flow_row.flow_id is null or permit_row.permit_id is null
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> p_connection_incarnation_id
     or connection_row.authorization_revision <> p_expected_base_revision
     or connection_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256
     or flow_row.owner_id <> p_owner_id
     or flow_row.connection_id <> p_connection_id
     or flow_row.connection_incarnation_id <> p_connection_incarnation_id
     or flow_row.expected_base_revision <> p_expected_base_revision
     or flow_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256
     or flow_row.consumption_id <> p_consumption_id
     or flow_row.status <> 'exchanged'
     or flow_row.provider <> p_provider
     or flow_row.resource <> p_resource
     or flow_row.account_kind <> p_account_kind
     or permit_row.flow_id <> p_flow_id
     or permit_row.connection_id <> p_connection_id
     or permit_row.exchange_id <> p_exchange_id
     or permit_row.exchange_binding_sha256 <> p_exchange_binding_sha256
     or permit_row.dispatch_fence_id <> p_dispatch_fence_id
     or permit_row.status <> 'attempt_fenced'
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or connection_row.account_kind <> p_account_kind
     or (
       p_expected_base_revision > 0
       and connection_row.external_account_id_sha256 is distinct from p_external_account_id_sha256
     ) then
    -- A stale completion must never revoke a credential that is live on any
    -- current connection.  Return a content-free refusal instead.
    if exists (
      select 1
      from connected_app_private.connections as live_connection
      where live_connection.authorization_state = 'active'
        and live_connection.broker_credential_ref = p_broker_credential_ref
    ) then
      return pg_catalog.jsonb_build_object(
        'completed', false,
        'active', false,
        'cleanup_enqueued', false,
        'current_live_credential', true
      );
    end if;
    cleanup_result := public.connected_app_record_credential_cleanup_v1(
      p_cleanup_id, p_broker_credential_ref, p_credential_ref_sha256,
      p_provider, 'stale_connection', p_cleanup_binding_sha256
    );
    return pg_catalog.jsonb_build_object(
      'completed', false,
      'active', false,
      'cleanup_enqueued', true,
      'cleanup_id', cleanup_result ->> 'cleanup_id',
      'cleanup_binding_sha256', p_cleanup_binding_sha256
    );
  end if;

  -- A retired credential handle may never become live again.  This point is
  -- reached only after the exact flow/permit/connection fences above pass.
  -- Re-enqueue the newly observed broker instance so provider-side handle
  -- reuse is cleaned up without attaching it to the connection.
  if exists (
    select 1
    from connected_app_private.credential_ref_tombstones as tombstone
    where tombstone.credential_ref_sha256 = p_credential_ref_sha256
  ) then
    cleanup_result := public.connected_app_record_credential_cleanup_v1(
      p_cleanup_id, p_broker_credential_ref, p_credential_ref_sha256,
      p_provider, 'stale_connection', p_cleanup_binding_sha256
    );
    return pg_catalog.jsonb_build_object(
      'completed', false, 'active', false, 'cleanup_enqueued', true,
      'credential_retired', true,
      'cleanup_id', cleanup_result ->> 'cleanup_id',
      'cleanup_binding_sha256', p_cleanup_binding_sha256
    );
  end if;

  -- Refuse a fresh connection for an external identity that is already active
  -- on another connection.  Handle the provisional credential through the
  -- durable cleanup outbox before the partial unique index can raise and roll
  -- the whole transaction back.
  select live_connection.id into duplicate_connection_id
  from connected_app_private.connections as live_connection
  where live_connection.owner_id = p_owner_id
    and live_connection.provider = p_provider
    and live_connection.resource = p_resource
    and live_connection.external_account_id_sha256 = p_external_account_id_sha256
    and live_connection.authorization_state = 'active'
    and live_connection.id <> p_connection_id
  limit 1;
  if duplicate_connection_id is not null then
    cleanup_result := public.connected_app_record_credential_cleanup_v1(
      p_cleanup_id, p_broker_credential_ref, p_credential_ref_sha256,
      p_provider, 'stale_connection', p_cleanup_binding_sha256
    );
    return pg_catalog.jsonb_build_object(
      'completed', false, 'active', false, 'cleanup_enqueued', true,
      'duplicate_active_identity', true,
      'cleanup_id', cleanup_result ->> 'cleanup_id',
      'cleanup_binding_sha256', p_cleanup_binding_sha256
    );
  end if;

  next_revision := connection_row.authorization_revision + 1;
  -- All digest material is prehashed at the trusted broker boundary.  The
  -- database does not assume pgcrypto lives in public (or any fixed schema).
  snapshot_sha256 := p_completion_binding_sha256;

  if connection_row.broker_credential_ref is not null
     and connection_row.broker_credential_ref <> p_broker_credential_ref then
    perform public.connected_app_record_credential_cleanup_v1(
      pg_catalog.gen_random_uuid(),
      connection_row.broker_credential_ref,
      connection_row.credential_ref_sha256,
      p_provider,
      'rotation',
      connection_row.credential_ref_sha256
    );
  end if;

  update connected_app_private.connections as connection
  set authorization_revision = next_revision,
      authorization_state = 'active',
      authorization_snapshot_sha256 = snapshot_sha256,
      granted_actions = flow_row.actions,
      granted_actions_sha256 = flow_row.actions_sha256,
      granted_scopes_sha256 = p_granted_scopes_sha256,
      external_account_id_sha256 = p_external_account_id_sha256,
      broker_credential_ref = p_broker_credential_ref,
      credential_ref_sha256 = p_credential_ref_sha256,
      authorization_expires_at = p_authorization_expires_at,
      revoked_at = null,
      updated_at = now_at
  where connection.id = p_connection_id
  returning * into connection_row;

  update connected_app_private.oauth_flows as flow
  set status = 'completed',
      completion_id = p_completion_id,
      completion_binding_sha256 = p_completion_binding_sha256,
      completion_broker_credential_ref = p_broker_credential_ref,
      completion_credential_ref_sha256 = p_credential_ref_sha256,
      completion_authorization_revision = next_revision,
      completion_authorization_snapshot_sha256 = snapshot_sha256,
      completion_external_account_id_sha256 = p_external_account_id_sha256,
      completion_granted_actions = flow_row.actions,
      completion_granted_actions_sha256 = flow_row.actions_sha256,
      completion_granted_scopes_sha256 = p_granted_scopes_sha256,
      completion_authorization_expires_at = p_authorization_expires_at,
      updated_at = now_at
  where flow.flow_id = p_flow_id;
  update connected_app_private.oauth_exchange_permits as permit
  set status = 'terminal',
      terminal_sha256 = p_completion_binding_sha256,
      terminal_completion_id = p_completion_id,
      terminal_flow_id = p_flow_id,
      terminal_connection_id = p_connection_id,
      terminal_broker_credential_ref = p_broker_credential_ref,
      terminal_credential_ref_sha256 = p_credential_ref_sha256,
      terminal_authorization_revision = next_revision
  where permit.permit_id = permit_row.permit_id;

  return pg_catalog.jsonb_build_object(
    'completed', true,
    'active', true,
    'owner_id', connection_row.owner_id,
    'connection_id', connection_row.id,
    'connection_incarnation_id', connection_row.connection_incarnation_id,
    'completion_id', p_completion_id,
    'authorization_revision', connection_row.authorization_revision,
    'authorization_snapshot_sha256', connection_row.authorization_snapshot_sha256,
    'granted_actions', connection_row.granted_actions,
    'granted_actions_sha256', connection_row.granted_actions_sha256,
    'granted_scopes_sha256', connection_row.granted_scopes_sha256,
    'external_account_id_sha256', connection_row.external_account_id_sha256,
    'broker_credential_ref', connection_row.broker_credential_ref,
    'credential_ref_sha256', connection_row.credential_ref_sha256,
    'authorization_expires_at', connection_row.authorization_expires_at
  );
end;
$fn$;
comment on function public.connected_app_oauth_finalize_v1(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamptz,uuid,text,uuid,text
) is 'ASK_CRUMP_CONNECTED_APP_OAUTH_FINALIZE_V1_TERMINAL_COMPLETION_REPLAY';

create or replace function public.connected_app_revoke_connection_v1(
  p_owner_id uuid,
  p_connection_id uuid,
  p_cleanup_id uuid,
  p_credential_ref_sha256 text,
  p_cleanup_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id
  for update;
  if not found then
    return null;
  end if;
  if connection_row.authorization_state = 'revoked' then
    return pg_catalog.to_jsonb(connection_row) - 'broker_credential_ref';
  end if;
  if connection_row.broker_credential_ref is not null then
    if p_credential_ref_sha256 is distinct from connection_row.credential_ref_sha256
       or p_cleanup_binding_sha256 is null
       or p_cleanup_binding_sha256 !~ '^[0-9a-f]{64}$' then
      raise exception 'connection cleanup binding is stale' using errcode = '55000';
    end if;
    perform public.connected_app_record_credential_cleanup_v1(
      p_cleanup_id, connection_row.broker_credential_ref,
      p_credential_ref_sha256, connection_row.provider,
      'connection_revoked', p_cleanup_binding_sha256
    );
  end if;

  update connected_app_private.connections as connection
  set authorization_revision = connection.authorization_revision + 1,
      authorization_state = 'revoked',
      broker_credential_ref = null,
      credential_ref_sha256 = null,
      current_flow_nonce_sha256 = null,
      authorization_expires_at = null,
      revoked_at = now_at,
      updated_at = now_at
  where connection.id = p_connection_id
  returning * into connection_row;
  update connected_app_private.oauth_flows
  set status = 'invalidated', updated_at = now_at
  where connection_id = p_connection_id and status <> 'completed';
  return pg_catalog.to_jsonb(connection_row) - 'broker_credential_ref';
end;
$fn$;
comment on function public.connected_app_revoke_connection_v1(uuid,uuid,uuid,text,text) is
  'ASK_CRUMP_CONNECTED_APP_REVOKE_CONNECTION_V1_WITH_CLEANUP_OUTBOX';

create or replace function public.connected_app_claim_cleanup_v1(
  p_lease_id uuid,
  p_lease_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  cleanup_row connected_app_private.credential_cleanup_outbox%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_lease_id is null or p_lease_seconds not between 30 and 300 then
    raise exception 'invalid cleanup lease' using errcode = '22023';
  end if;
  select cleanup.* into cleanup_row
  from connected_app_private.credential_cleanup_outbox as cleanup
  where cleanup.lease_id = p_lease_id
     or cleanup.terminal_lease_id = p_lease_id
  for update;
  if found and cleanup_row.status in ('completed', 'failed_permanent') then
    return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
  end if;
  if found and cleanup_row.lease_expires_at > now_at then
    return pg_catalog.to_jsonb(cleanup_row);
  end if;
  if found then
    if cleanup_row.status <> 'leased' then
      raise exception 'cleanup lease replay drifted' using errcode = '55000';
    end if;
    -- Exact retry of an expired lease must reclaim that same row, never select
    -- a second row while the unique lease ID is still stored on the first.
    -- Use a nonblocking credential lock while holding the row lock to avoid a
    -- lock-order cycle with finalize/record cleanup.
    if not pg_catalog.pg_try_advisory_xact_lock(
      pg_catalog.hashtextextended(
        cleanup_row.credential_ref_sha256, 81424519024640287::bigint
      )
    ) then
      return null;
    end if;
    if not exists (
      select 1
      from connected_app_private.credential_ref_tombstones as tombstone
      where tombstone.credential_ref_sha256 = cleanup_row.credential_ref_sha256
        and tombstone.provider = cleanup_row.provider
    ) then
      raise exception 'cleanup credential tombstone is missing' using errcode = '55000';
    end if;
    if exists (
      select 1
      from connected_app_private.connections as live_connection
      where live_connection.authorization_state = 'active'
        and (
          live_connection.broker_credential_ref = cleanup_row.broker_credential_ref
          or live_connection.credential_ref_sha256 = cleanup_row.credential_ref_sha256
        )
    ) then
      update connected_app_private.credential_cleanup_outbox as cleanup
      set status = 'failed_permanent',
          terminal_lease_id = p_lease_id, terminal_at = now_at,
          lease_id = null, lease_expires_at = null, updated_at = now_at
      where cleanup.cleanup_id = cleanup_row.cleanup_id
      returning * into cleanup_row;
      return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
    end if;
    if cleanup_row.attempts >= 8 then
      update connected_app_private.credential_cleanup_outbox as cleanup
      set status = 'failed_permanent',
          terminal_lease_id = cleanup.lease_id,
          terminal_at = now_at,
          lease_id = null,
          lease_expires_at = null,
          updated_at = now_at
      where cleanup.cleanup_id = cleanup_row.cleanup_id
      returning * into cleanup_row;
      return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
    end if;
    update connected_app_private.credential_cleanup_outbox as cleanup
    set status = 'leased', attempts = cleanup.attempts + 1,
        lease_id = p_lease_id,
        lease_expires_at = now_at + pg_catalog.make_interval(secs => p_lease_seconds),
        updated_at = now_at
    where cleanup.cleanup_id = cleanup_row.cleanup_id
    returning * into cleanup_row;
    return pg_catalog.to_jsonb(cleanup_row);
  end if;
  -- A worker may crash after receiving the eighth (last) lease.  Convert
  -- that expired lease to an explicit, observable terminal row before
  -- looking for more work; never attempt an overflow to attempts = 9.
  select cleanup.* into cleanup_row
  from connected_app_private.credential_cleanup_outbox as cleanup
  where cleanup.status = 'leased'
    and cleanup.lease_expires_at <= now_at
    and cleanup.attempts >= 8
  order by cleanup.lease_expires_at, cleanup.cleanup_id
  for update skip locked
  limit 1;
  if found then
    update connected_app_private.credential_cleanup_outbox as cleanup
    set status = 'failed_permanent',
        terminal_lease_id = cleanup.lease_id,
        terminal_at = now_at,
        lease_id = null,
        lease_expires_at = null,
        updated_at = now_at
    where cleanup.cleanup_id = cleanup_row.cleanup_id
    returning * into cleanup_row;
    return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
  end if;
  select cleanup.* into cleanup_row
  from connected_app_private.credential_cleanup_outbox as cleanup
  where (
      cleanup.status = 'queued' and cleanup.next_attempt_at <= now_at
      and cleanup.attempts < 8
    ) or (
      cleanup.status = 'leased' and cleanup.lease_expires_at <= now_at
      and cleanup.attempts < 8
    )
  order by cleanup.next_attempt_at, cleanup.created_at, cleanup.cleanup_id
  for update skip locked
  limit 1;
  if not found then
    return null;
  end if;
  if not pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended(
      cleanup_row.credential_ref_sha256, 81424519024640287::bigint
    )
  ) then
    return null;
  end if;
  if not exists (
    select 1
    from connected_app_private.credential_ref_tombstones as tombstone
    where tombstone.credential_ref_sha256 = cleanup_row.credential_ref_sha256
      and tombstone.provider = cleanup_row.provider
  ) then
    raise exception 'cleanup credential tombstone is missing' using errcode = '55000';
  end if;
  if exists (
    select 1
    from connected_app_private.connections as live_connection
    where live_connection.authorization_state = 'active'
      and (
        live_connection.broker_credential_ref = cleanup_row.broker_credential_ref
        or live_connection.credential_ref_sha256 = cleanup_row.credential_ref_sha256
      )
  ) then
    update connected_app_private.credential_cleanup_outbox as cleanup
    set status = 'failed_permanent',
        terminal_lease_id = p_lease_id, terminal_at = now_at,
        lease_id = null, lease_expires_at = null, updated_at = now_at
    where cleanup.cleanup_id = cleanup_row.cleanup_id
    returning * into cleanup_row;
    return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
  end if;
  update connected_app_private.credential_cleanup_outbox as cleanup
  set status = 'leased', attempts = cleanup.attempts + 1,
      lease_id = p_lease_id,
      lease_expires_at = now_at + pg_catalog.make_interval(secs => p_lease_seconds),
      updated_at = now_at
  where cleanup.cleanup_id = cleanup_row.cleanup_id
  returning * into cleanup_row;
  return pg_catalog.to_jsonb(cleanup_row);
end;
$fn$;
comment on function public.connected_app_claim_cleanup_v1(uuid,integer) is
  'ASK_CRUMP_CONNECTED_APP_CLAIM_CLEANUP_V1_SERVICE_ROLE_ONLY';

create or replace function public.connected_app_finish_cleanup_v1(
  p_cleanup_id uuid,
  p_lease_id uuid,
  p_completed boolean,
  p_retry_after_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  cleanup_row connected_app_private.credential_cleanup_outbox%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  select cleanup.* into cleanup_row
  from connected_app_private.credential_cleanup_outbox as cleanup
  where cleanup.cleanup_id = p_cleanup_id
  for update;
  if found and cleanup_row.status in ('completed', 'failed_permanent')
     and cleanup_row.terminal_lease_id = p_lease_id then
    return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
  end if;
  if not found or cleanup_row.status <> 'leased' or cleanup_row.lease_id <> p_lease_id then
    raise exception 'cleanup lease is stale' using errcode = '55000';
  end if;
  if p_completed then
    update connected_app_private.credential_cleanup_outbox as cleanup
    set status = 'completed', lease_id = null, lease_expires_at = null,
        terminal_lease_id = p_lease_id, terminal_at = now_at,
        delete_after = least(cleanup.delete_after, now_at + interval '24 hours'),
        updated_at = now_at
    where cleanup.cleanup_id = p_cleanup_id
    returning * into cleanup_row;
  elsif cleanup_row.attempts >= 8 then
    update connected_app_private.credential_cleanup_outbox as cleanup
    set status = 'failed_permanent', lease_id = null, lease_expires_at = null,
        terminal_lease_id = p_lease_id, terminal_at = now_at, updated_at = now_at
    where cleanup.cleanup_id = p_cleanup_id
    returning * into cleanup_row;
  else
    update connected_app_private.credential_cleanup_outbox as cleanup
    set status = 'queued', lease_id = null, lease_expires_at = null,
        next_attempt_at = now_at + pg_catalog.make_interval(
          secs => greatest(30, least(3600, coalesce(p_retry_after_seconds, 60)))
        ), updated_at = now_at
    where cleanup.cleanup_id = p_cleanup_id
    returning * into cleanup_row;
  end if;
  return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
end;
$fn$;
comment on function public.connected_app_finish_cleanup_v1(uuid,uuid,boolean,integer) is
  'ASK_CRUMP_CONNECTED_APP_FINISH_CLEANUP_V1_IDEMPOTENT_LEASE';

create or replace function public.connected_app_recover_cleanup_v1(
  p_cleanup_id uuid,
  p_recovery_id uuid,
  p_next_attempt_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  cleanup_row connected_app_private.credential_cleanup_outbox%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_cleanup_id is null or p_recovery_id is null then
    raise exception 'invalid cleanup recovery bounds' using errcode = '22023';
  end if;
  select cleanup.* into cleanup_row
  from connected_app_private.credential_cleanup_outbox as cleanup
  where cleanup.cleanup_id = p_cleanup_id
  for update;
  if not found then
    return null;
  end if;
  if cleanup_row.recovery_id = p_recovery_id
     and cleanup_row.status in ('queued', 'leased', 'completed', 'failed_permanent') then
    return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
  end if;
  if p_next_attempt_at < now_at
     or p_next_attempt_at > now_at + interval '1 hour' then
    raise exception 'invalid cleanup recovery bounds' using errcode = '22023';
  end if;
  if cleanup_row.status <> 'failed_permanent'
     or cleanup_row.delete_after <= now_at
     or cleanup_row.recovery_count >= 8 then
    raise exception 'cleanup is not recoverable' using errcode = '55000';
  end if;
  update connected_app_private.credential_cleanup_outbox as cleanup
  set status = 'queued', attempts = 0,
      next_attempt_at = p_next_attempt_at,
      terminal_lease_id = null, terminal_at = null,
      recovery_id = p_recovery_id,
      recovery_count = cleanup.recovery_count + 1,
      updated_at = now_at
  where cleanup.cleanup_id = p_cleanup_id
  returning * into cleanup_row;
  return pg_catalog.to_jsonb(cleanup_row) - 'broker_credential_ref';
end;
$fn$;
comment on function public.connected_app_recover_cleanup_v1(uuid,uuid,timestamptz) is
  'ASK_CRUMP_CONNECTED_APP_RECOVER_CLEANUP_V1_EXPLICIT_FAILED_PERMANENT_RECOVERY';

create or replace function public.connected_app_create_task_grant_v1(
  p_grant_id uuid,
  p_owner_id uuid,
  p_task_id uuid,
  p_turn_id uuid,
  p_connection_id uuid,
  p_provider text,
  p_resource text,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_actions text[],
  p_actions_sha256 text,
  p_task_state_revision bigint,
  p_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  grant_row connected_app_private.task_grants%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_grant_id is null or p_owner_id is null or p_task_id is null
     or p_turn_id is null or p_connection_id is null
     or p_task_state_revision < 1
     or pg_catalog.cardinality(p_actions) not between 1 and 16
     or exists (
       select 1 from pg_catalog.unnest(p_actions) as requested(action_name)
       left join connected_app_private.action_authority as authority
         on authority.action = requested.action_name
       where requested.action_name is null
          or pg_catalog.length(requested.action_name) not between 1 and 100
          or authority.action is null
          or authority.resource <> p_resource
     )
     or (select pg_catalog.count(distinct requested.action_name)
         from pg_catalog.unnest(p_actions) as requested(action_name))
        <> pg_catalog.cardinality(p_actions)
     or p_expires_at <= now_at
     or p_expires_at > now_at + interval '24 hours' then
    raise exception 'invalid task grant bounds' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id
  for update;
  if not found
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or connection_row.granted_actions is null
     or exists (
       select 1 from pg_catalog.unnest(p_actions) as requested(action_name)
       where not (requested.action_name = any(connection_row.granted_actions))
     )
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at) then
    raise exception 'task grant authority changed' using errcode = '55000';
  end if;

  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = p_grant_id
  for update;
  if found then
    if grant_row.owner_id <> p_owner_id
       or grant_row.task_id <> p_task_id
       or grant_row.turn_id <> p_turn_id
       or grant_row.connection_id <> p_connection_id
       or grant_row.authorization_revision <> p_authorization_revision
       or grant_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
       or grant_row.actions is distinct from p_actions
       or grant_row.actions_sha256 <> p_actions_sha256
       or grant_row.task_state_revision <> p_task_state_revision
       or grant_row.expires_at <> p_expires_at then
      raise exception 'task grant replay drifted' using errcode = '55000';
    end if;
    return pg_catalog.to_jsonb(grant_row);
  end if;

  insert into connected_app_private.task_grants (
    grant_id, owner_id, task_id, turn_id, connection_id, provider, resource,
    authorization_revision, authorization_snapshot_sha256, actions,
    actions_sha256, task_state_revision, expires_at
  ) values (
    p_grant_id, p_owner_id, p_task_id, p_turn_id, p_connection_id,
    p_provider, p_resource, p_authorization_revision,
    p_authorization_snapshot_sha256, p_actions, p_actions_sha256,
    p_task_state_revision, p_expires_at
  ) returning * into grant_row;
  return pg_catalog.to_jsonb(grant_row);
end;
$fn$;
comment on function public.connected_app_create_task_grant_v1(
  uuid,uuid,uuid,uuid,uuid,text,text,bigint,text,text[],text,bigint,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_CREATE_TASK_GRANT_V1_LIVE_AUTHORITY';

create or replace function public.connected_app_revoke_task_grant_v1(
  p_owner_id uuid,
  p_grant_id uuid,
  p_task_id uuid,
  p_turn_id uuid,
  p_task_state_revision bigint
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  grant_row connected_app_private.task_grants%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_owner_id is null or p_grant_id is null or p_task_id is null
     or p_turn_id is null or p_task_state_revision < 1 then
    raise exception 'invalid task-grant revocation bounds' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = p_grant_id
    and task_grant.owner_id = p_owner_id
  for update;
  if not found then
    return null;
  end if;
  if grant_row.task_id <> p_task_id or grant_row.turn_id <> p_turn_id then
    raise exception 'task-grant revocation identity drifted' using errcode = '55000';
  end if;
  if grant_row.revoked_at is not null then
    if grant_row.task_state_revision = p_task_state_revision then
      return pg_catalog.to_jsonb(grant_row);
    end if;
    raise exception 'task-grant revocation replay drifted' using errcode = '55000';
  end if;
  if p_task_state_revision <= grant_row.task_state_revision then
    raise exception 'task-grant revocation revision is stale' using errcode = '55000';
  end if;
  update connected_app_private.task_grants as task_grant
  set revoked_at = now_at, task_state_revision = p_task_state_revision
  where task_grant.grant_id = p_grant_id
  returning * into grant_row;
  update connected_app_private.schedules as schedule
  set status = 'paused', task_state_revision = p_task_state_revision,
      next_run_at = null, claim_id = null, claim_expires_at = null, updated_at = now_at
  where schedule.owner_id = p_owner_id
    and schedule.task_id = p_task_id
    and schedule.task_state_revision < p_task_state_revision
    and schedule.status = 'active';
  return pg_catalog.to_jsonb(grant_row);
end;
$fn$;
comment on function public.connected_app_revoke_task_grant_v1(uuid,uuid,uuid,uuid,bigint) is
  'ASK_CRUMP_CONNECTED_APP_REVOKE_TASK_GRANT_V1_MONOTONIC_TASK_FENCE';

create or replace function public.connected_app_create_approval_v1(
  p_approval_id uuid,
  p_action_id uuid,
  p_owner_id uuid,
  p_task_id uuid,
  p_turn_id uuid,
  p_connection_id uuid,
  p_provider text,
  p_resource text,
  p_action text,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_approval_class text,
  p_parameters_sha256 text,
  p_resource_version_sha256 text,
  p_approval_binding_sha256 text,
  p_approved_at timestamptz,
  p_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  approval_row connected_app_private.approvals%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_approval_id is null or p_action_id is null or p_owner_id is null
     or p_task_id is null or p_turn_id is null or p_connection_id is null
     or p_approved_at < now_at - interval '5 minutes'
     or p_approved_at > now_at + interval '1 minute'
     or p_expires_at <= now_at
     or p_expires_at > p_approved_at + interval '15 minutes' then
    raise exception 'invalid approval bounds' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action = p_action;
  if not found or authority_row.resource <> p_resource
     or not authority_row.mutates_external_state
     or authority_row.approval_class <> p_approval_class then
    raise exception 'approval action is unsupported or misclassified'
      using errcode = '55000';
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id
  for update;
  if not found
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or not (p_action = any(connection_row.granted_actions))
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at) then
    raise exception 'approval authority changed' using errcode = '55000';
  end if;

  select approval.* into approval_row
  from connected_app_private.approvals as approval
  where approval.approval_binding_sha256 = p_approval_binding_sha256
  for update;
  if found then
    if approval_row.approval_id <> p_approval_id
       or approval_row.action_id <> p_action_id
       or approval_row.owner_id <> p_owner_id
       or approval_row.task_id <> p_task_id
       or approval_row.turn_id <> p_turn_id
       or approval_row.connection_id <> p_connection_id
       or approval_row.provider <> p_provider
       or approval_row.resource <> p_resource
       or approval_row.action <> p_action
       or approval_row.authorization_revision <> p_authorization_revision
       or approval_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
       or approval_row.approval_class <> p_approval_class
       or approval_row.parameters_sha256 <> p_parameters_sha256
       or approval_row.resource_version_sha256 is distinct from p_resource_version_sha256
       or approval_row.approved_at <> p_approved_at
       or approval_row.expires_at <> p_expires_at then
      raise exception 'approval replay drifted' using errcode = '55000';
    end if;
    return pg_catalog.to_jsonb(approval_row);
  end if;

  insert into connected_app_private.approvals (
    approval_id, action_id, owner_id, task_id, turn_id, connection_id,
    provider, resource, action, authorization_revision,
    authorization_snapshot_sha256, approval_class, parameters_sha256,
    resource_version_sha256, approval_binding_sha256, approved_at, expires_at
  ) values (
    p_approval_id, p_action_id, p_owner_id, p_task_id, p_turn_id,
    p_connection_id, p_provider, p_resource, p_action,
    p_authorization_revision, p_authorization_snapshot_sha256,
    p_approval_class, p_parameters_sha256, p_resource_version_sha256,
    p_approval_binding_sha256, p_approved_at, p_expires_at
  ) returning * into approval_row;
  return pg_catalog.to_jsonb(approval_row);
end;
$fn$;
comment on function public.connected_app_create_approval_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_CREATE_APPROVAL_V1_EXACT_BOUNDING';

create or replace function public.connected_app_claim_action_v1(
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
     or p_lease_seconds not between 30 and 300
     or p_execution_deadline <= now_at
     or p_execution_deadline > now_at + interval '1 hour' then
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
    task_state_revision, mutates_external_state, approval_class,
    claim_request_id, claim_id,
    lease_expires_at, execution_deadline
  ) values (
    p_operation_id, p_action_id, p_owner_id, p_task_id, p_turn_id,
    p_connection_id, p_grant_id, p_provider, p_resource, p_action,
    p_authorization_revision, p_authorization_snapshot_sha256,
    p_granted_actions_sha256, p_granted_scopes_sha256, p_parameters_sha256,
    p_resource_version_sha256,
    p_authority_sha256, p_idempotency_key_sha256, p_task_state_revision,
    authority_row.mutates_external_state, authority_row.approval_class,
    p_claim_request_id, p_claim_id,
    now_at + pg_catalog.make_interval(secs => p_lease_seconds),
    p_execution_deadline
  ) returning * into action_row;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_claim_action_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,bigint,uuid,uuid,integer,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_CLAIM_ACTION_V1_DATABASE_ALLOWLIST_AND_FENCING';

create or replace function public.connected_app_begin_access_v1(
  p_operation_id uuid,
  p_owner_id uuid,
  p_claim_id uuid,
  p_fencing_token bigint,
  p_granted_actions_sha256 text,
  p_access_phase text,
  p_access_use_nonce uuid,
  p_credential_expires_at timestamptz
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
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_access_phase is null or p_access_phase not in ('read', 'preobserve')
     or p_access_use_nonce is null or p_credential_expires_at is null
     or p_credential_expires_at <= now_at
     or p_granted_actions_sha256 is null
     or p_granted_actions_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid access phase' using errcode = '22023';
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
  where connection.id = action_row.connection_id and connection.owner_id = p_owner_id
  for update;
  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = action_row.grant_id
  for update;
  if connection_row.id is null or grant_row.grant_id is null
     or connection_row.authorization_state <> 'active'
     or connection_row.authorization_revision <> action_row.authorization_revision
     or connection_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> action_row.granted_actions_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or not (action_row.action = any(connection_row.granted_actions))
     or connection_row.granted_scopes_sha256 <> action_row.granted_scopes_sha256
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at)
     or (connection_row.authorization_expires_at is not null
         and p_credential_expires_at > connection_row.authorization_expires_at)
     or grant_row.revoked_at is not null or grant_row.expires_at <= now_at
     or p_credential_expires_at > grant_row.expires_at
     or grant_row.task_state_revision <> action_row.task_state_revision
     or action_row.claim_id <> p_claim_id
     or action_row.fencing_token <> p_fencing_token
     or action_row.lease_expires_at <= now_at
     or p_credential_expires_at > action_row.lease_expires_at
     or action_row.execution_deadline <= now_at
     or p_credential_expires_at > action_row.execution_deadline
     or (action_row.mutates_external_state and p_access_phase <> 'preobserve')
     or (not action_row.mutates_external_state and p_access_phase <> 'read') then
    raise exception 'action access authority changed' using errcode = '55000';
  end if;
  if action_row.status <> 'claimed' then
    if action_row.status = 'access_granted'
       and action_row.access_phase = p_access_phase
       and (
         (p_access_phase = 'read' and action_row.read_use_nonce = p_access_use_nonce)
         or (p_access_phase = 'preobserve'
             and action_row.preobserve_use_nonce = p_access_use_nonce)
        )
       and (
         (p_access_phase = 'read'
          and action_row.read_credential_expires_at = p_credential_expires_at)
         or (p_access_phase = 'preobserve'
             and action_row.preobserve_credential_expires_at = p_credential_expires_at)
       ) then
      return pg_catalog.to_jsonb(action_row);
    end if;
    raise exception 'action access already began differently' using errcode = '55000';
  end if;
  update connected_app_private.action_ledger as ledger
  set status = 'access_granted', access_phase = p_access_phase,
      lease_expires_at = p_credential_expires_at,
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
comment on function public.connected_app_begin_access_v1(uuid,uuid,uuid,bigint,text,text,uuid,timestamptz) is
  'ASK_CRUMP_CONNECTED_APP_BEGIN_ACCESS_V1_READ_OR_PREOBSERVE_NONCE';

create or replace function public.connected_app_recover_access_v1(
  p_operation_id uuid,
  p_owner_id uuid,
  p_recovery_request_id uuid,
  p_claim_id uuid,
  p_lease_seconds integer,
  p_granted_actions_sha256 text,
  p_access_use_nonce uuid,
  p_credential_expires_at timestamptz
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
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_recovery_request_id is null or p_claim_id is null
     or p_access_use_nonce is null or p_lease_seconds not between 30 and 300
     or p_credential_expires_at is null or p_credential_expires_at <= now_at
     or p_credential_expires_at > now_at + pg_catalog.make_interval(secs => p_lease_seconds)
     or p_granted_actions_sha256 is null
     or p_granted_actions_sha256 !~ '^[0-9a-f]{64}$' then
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
  where connection.id = action_row.connection_id and connection.owner_id = p_owner_id
  for update;
  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = action_row.grant_id
  for update;
  if action_row.status = 'access_granted'
     and action_row.claim_request_id = p_recovery_request_id
     and action_row.claim_id = p_claim_id
     and (
       (action_row.access_phase = 'read'
        and action_row.read_use_nonce = p_access_use_nonce)
       or (action_row.access_phase = 'preobserve'
           and action_row.preobserve_use_nonce = p_access_use_nonce)
     )
     and action_row.lease_expires_at > now_at
     and connection_row.id is not null
     and connection_row.authorization_state = 'active'
     and connection_row.authorization_revision = action_row.authorization_revision
     and connection_row.authorization_snapshot_sha256 = action_row.authorization_snapshot_sha256
     and connection_row.granted_actions_sha256 = action_row.granted_actions_sha256
     and connection_row.granted_actions_sha256 = p_granted_actions_sha256
     and action_row.action = any(connection_row.granted_actions)
     and connection_row.granted_scopes_sha256 = action_row.granted_scopes_sha256
     and (connection_row.authorization_expires_at is null
          or connection_row.authorization_expires_at > now_at)
      and (connection_row.authorization_expires_at is null
           or p_credential_expires_at <= connection_row.authorization_expires_at)
     and grant_row.grant_id is not null and grant_row.revoked_at is null
      and grant_row.expires_at > now_at
      and p_credential_expires_at <= grant_row.expires_at
      and action_row.lease_expires_at = p_credential_expires_at then
    return pg_catalog.to_jsonb(action_row);
  end if;
  if action_row.status <> 'access_granted'
     or action_row.effect_use_nonce is not null
     or action_row.lease_expires_at > now_at
     or action_row.execution_deadline <= now_at
     or connection_row.id is null
     or connection_row.authorization_state <> 'active'
     or connection_row.authorization_revision <> action_row.authorization_revision
     or connection_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> action_row.granted_actions_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or not (action_row.action = any(connection_row.granted_actions))
     or connection_row.granted_scopes_sha256 <> action_row.granted_scopes_sha256
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at)
     or (connection_row.authorization_expires_at is not null
         and p_credential_expires_at > connection_row.authorization_expires_at)
     or grant_row.grant_id is null or grant_row.revoked_at is not null
     or grant_row.expires_at <= now_at
     or p_credential_expires_at > grant_row.expires_at
     or grant_row.task_state_revision <> action_row.task_state_revision then
    raise exception 'action access is not recoverable' using errcode = '55000';
  end if;
  update connected_app_private.action_ledger as ledger
  set claim_request_id = p_recovery_request_id,
      claim_id = p_claim_id,
      fencing_token = pg_catalog.nextval(
        'connected_app_private.action_fencing_token_seq'::regclass
      ),
      lease_expires_at = p_credential_expires_at,
      read_use_nonce = case when action_row.access_phase = 'read'
        then p_access_use_nonce else null end,
      read_credential_expires_at = case when action_row.access_phase = 'read'
        then p_credential_expires_at else null end,
      read_consumed_at = null,
      preobserve_use_nonce = case when action_row.access_phase = 'preobserve'
        then p_access_use_nonce else null end,
      preobserve_credential_expires_at = case when action_row.access_phase = 'preobserve'
        then p_credential_expires_at else null end,
      preobserve_consumed_at = null,
      access_started_at = now_at,
      updated_at = now_at
  where ledger.operation_id = p_operation_id
  returning * into action_row;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_recover_access_v1(uuid,uuid,uuid,uuid,integer,text,uuid,timestamptz) is
  'ASK_CRUMP_CONNECTED_APP_RECOVER_ACCESS_V1_NEVER_AFTER_EFFECT';

create or replace function public.connected_app_consume_approval_v1(
  p_approval_id uuid,
  p_operation_id uuid,
  p_owner_id uuid,
  p_claim_id uuid,
  p_fencing_token bigint,
  p_approval_binding_sha256 text
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
  approval_row connected_app_private.approvals%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id and ledger.owner_id = p_owner_id
  for update;
  if not found then
    raise exception 'action not found' using errcode = '55000';
  end if;
  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action = action_row.action;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = action_row.connection_id and connection.owner_id = p_owner_id
  for update;
  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = action_row.grant_id
  for update;
  select approval.* into approval_row
  from connected_app_private.approvals as approval
  where approval.approval_id = p_approval_id
  for update;
  if connection_row.id is null or approval_row.approval_id is null
     or authority_row.action is null
     or authority_row.resource <> action_row.resource
     or authority_row.mutates_external_state <> action_row.mutates_external_state
     or authority_row.approval_class <> action_row.approval_class
     or action_row.status <> 'access_granted'
     or not action_row.mutates_external_state
     or action_row.access_phase <> 'preobserve'
     or action_row.preobserve_consumed_at is null
     or action_row.claim_id <> p_claim_id
     or action_row.fencing_token <> p_fencing_token
     or action_row.lease_expires_at <= now_at
     or action_row.execution_deadline <= now_at
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> action_row.provider
     or connection_row.resource <> action_row.resource
     or connection_row.authorization_revision <> action_row.authorization_revision
     or connection_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> action_row.granted_actions_sha256
     or not (action_row.action = any(connection_row.granted_actions))
     or connection_row.granted_scopes_sha256 <> action_row.granted_scopes_sha256
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at)
     or grant_row.grant_id is null
     or grant_row.owner_id <> action_row.owner_id
     or grant_row.task_id <> action_row.task_id
     or grant_row.turn_id <> action_row.turn_id
     or grant_row.connection_id <> action_row.connection_id
     or grant_row.provider <> action_row.provider
     or grant_row.resource <> action_row.resource
     or grant_row.authorization_revision <> action_row.authorization_revision
     or grant_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256
     or grant_row.task_state_revision <> action_row.task_state_revision
     or grant_row.revoked_at is not null
     or grant_row.expires_at <= now_at
     or not (action_row.action = any(grant_row.actions))
     or approval_row.action_id <> action_row.action_id
     or approval_row.owner_id <> p_owner_id
     or approval_row.task_id <> action_row.task_id
     or approval_row.turn_id <> action_row.turn_id
     or approval_row.connection_id <> action_row.connection_id
     or approval_row.provider <> action_row.provider
     or approval_row.resource <> action_row.resource
     or approval_row.action <> action_row.action
     or approval_row.approval_class <> action_row.approval_class
     or approval_row.authorization_revision <> action_row.authorization_revision
     or approval_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256
     or approval_row.parameters_sha256 <> action_row.parameters_sha256
     or approval_row.resource_version_sha256 is distinct from action_row.resource_version_sha256
     or approval_row.approval_binding_sha256 <> p_approval_binding_sha256 then
    raise exception 'approval is stale or mismatched' using errcode = '55000';
  end if;
  if approval_row.consumed_at is not null then
    if approval_row.consumed_by_operation_id = p_operation_id then
      return pg_catalog.to_jsonb(approval_row);
    end if;
    raise exception 'approval already consumed by another operation' using errcode = '55000';
  end if;
  if approval_row.expires_at <= now_at then
    raise exception 'approval expired before consumption' using errcode = '55000';
  end if;
  update connected_app_private.approvals as approval
  set consumed_at = now_at, consumed_by_operation_id = p_operation_id
  where approval.approval_id = p_approval_id
  returning * into approval_row;
  return pg_catalog.to_jsonb(approval_row);
end;
$fn$;
comment on function public.connected_app_consume_approval_v1(uuid,uuid,uuid,uuid,bigint,text) is
  'ASK_CRUMP_CONNECTED_APP_CONSUME_APPROVAL_V1_ONE_OPERATION_ONLY';

create or replace function public.connected_app_begin_effect_v1(
  p_operation_id uuid,
  p_owner_id uuid,
  p_claim_id uuid,
  p_fencing_token bigint,
  p_granted_actions_sha256 text,
  p_approval_id uuid,
  p_effect_use_nonce uuid,
  p_credential_expires_at timestamptz
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
  approval_row connected_app_private.approvals%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_effect_use_nonce is null or p_credential_expires_at is null
     or p_credential_expires_at <= now_at
     or p_granted_actions_sha256 is null
     or p_granted_actions_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'effect nonce is required' using errcode = '22023';
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
  where connection.id = action_row.connection_id and connection.owner_id = p_owner_id
  for update;
  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = action_row.grant_id
  for update;
  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action = action_row.action;
  select approval.* into approval_row
  from connected_app_private.approvals as approval
  where approval.approval_id = p_approval_id
  for update;
  if action_row.status = 'effect_possible'
     and action_row.effect_use_nonce is distinct from p_effect_use_nonce then
    raise exception 'effect already began with another nonce' using errcode = '55000';
  end if;
  if action_row.status not in ('access_granted', 'effect_possible')
     or not action_row.mutates_external_state
     or action_row.access_phase <> 'preobserve'
     or action_row.preobserve_consumed_at is null
     or action_row.claim_id <> p_claim_id
     or action_row.fencing_token <> p_fencing_token
     or action_row.lease_expires_at <= now_at
     or p_credential_expires_at > action_row.lease_expires_at
     or action_row.execution_deadline <= now_at
     or p_credential_expires_at > action_row.execution_deadline
     or authority_row.action is null
     or authority_row.resource <> action_row.resource
     or authority_row.mutates_external_state <> action_row.mutates_external_state
     or authority_row.approval_class <> action_row.approval_class
     or connection_row.id is null
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> action_row.provider
     or connection_row.resource <> action_row.resource
     or connection_row.authorization_revision <> action_row.authorization_revision
     or connection_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> action_row.granted_actions_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or not (action_row.action = any(connection_row.granted_actions))
     or connection_row.granted_scopes_sha256 <> action_row.granted_scopes_sha256
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at)
     or (connection_row.authorization_expires_at is not null
         and p_credential_expires_at > connection_row.authorization_expires_at)
     or grant_row.grant_id is null
     or grant_row.owner_id <> action_row.owner_id
     or grant_row.task_id <> action_row.task_id
     or grant_row.turn_id <> action_row.turn_id
     or grant_row.connection_id <> action_row.connection_id
     or grant_row.provider <> action_row.provider
     or grant_row.resource <> action_row.resource
     or grant_row.authorization_revision <> action_row.authorization_revision
     or grant_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256
     or grant_row.task_state_revision <> action_row.task_state_revision
     or grant_row.revoked_at is not null
     or grant_row.expires_at <= now_at
     or p_credential_expires_at > grant_row.expires_at
     or not (action_row.action = any(grant_row.actions))
     or approval_row.approval_id is null
     or approval_row.action_id <> action_row.action_id
     or approval_row.owner_id <> p_owner_id
     or approval_row.task_id <> action_row.task_id
     or approval_row.turn_id <> action_row.turn_id
     or approval_row.connection_id <> action_row.connection_id
     or approval_row.provider <> action_row.provider
     or approval_row.resource <> action_row.resource
     or approval_row.action <> action_row.action
     or approval_row.approval_class <> action_row.approval_class
     or approval_row.authorization_revision <> action_row.authorization_revision
     or approval_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256
     or approval_row.parameters_sha256 <> action_row.parameters_sha256
     or approval_row.resource_version_sha256 is distinct from action_row.resource_version_sha256
     or approval_row.expires_at <= now_at
     or approval_row.consumed_by_operation_id is distinct from p_operation_id then
    raise exception 'effect authority changed' using errcode = '55000';
  end if;
  if action_row.status = 'effect_possible' then
    if action_row.effect_credential_expires_at <> p_credential_expires_at then
      raise exception 'effect replay expiry drifted' using errcode = '55000';
    end if;
    return pg_catalog.to_jsonb(action_row);
  end if;
  update connected_app_private.action_ledger as ledger
  set status = 'effect_possible', effect_use_nonce = p_effect_use_nonce,
      effect_credential_expires_at = p_credential_expires_at,
      effect_consumed_at = null,
      lease_expires_at = p_credential_expires_at,
      effect_started_at = now_at, updated_at = now_at
  where ledger.operation_id = p_operation_id
  returning * into action_row;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_begin_effect_v1(uuid,uuid,uuid,bigint,text,uuid,uuid,timestamptz) is
  'ASK_CRUMP_CONNECTED_APP_BEGIN_EFFECT_V1_NEVER_AUTORETRY';

create or replace function public.connected_app_begin_postobserve_v1(
  p_operation_id uuid,
  p_owner_id uuid,
  p_effect_use_nonce uuid,
  p_postobserve_use_nonce uuid,
  p_credential_expires_at timestamptz,
  p_granted_actions_sha256 text
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
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_postobserve_use_nonce is null
     or p_credential_expires_at is null or p_credential_expires_at <= now_at
     or p_credential_expires_at > now_at + interval '5 minutes'
     or p_granted_actions_sha256 is null
     or p_granted_actions_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid postobserve bounds' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id and ledger.owner_id = p_owner_id
  for update;
  if found then
    select connection.* into connection_row
    from connected_app_private.connections as connection
    where connection.id = action_row.connection_id and connection.owner_id = p_owner_id
    for update;
    select task_grant.* into grant_row
    from connected_app_private.task_grants as task_grant
    where task_grant.grant_id = action_row.grant_id
    for update;
  end if;
  if not found or action_row.status <> 'effect_possible'
     or action_row.effect_use_nonce is distinct from p_effect_use_nonce
     or action_row.effect_consumed_at is null
     or connection_row.id is null
     or connection_row.authorization_state <> 'active'
     or connection_row.authorization_revision <> action_row.authorization_revision
     or connection_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> action_row.granted_actions_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or not (action_row.action = any(connection_row.granted_actions))
     or connection_row.granted_scopes_sha256 <> action_row.granted_scopes_sha256
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at)
     or (connection_row.authorization_expires_at is not null
         and p_credential_expires_at > connection_row.authorization_expires_at)
     or grant_row.grant_id is null
     or grant_row.revoked_at is not null
     or grant_row.expires_at <= now_at
     or p_credential_expires_at > grant_row.expires_at
     or grant_row.task_state_revision <> action_row.task_state_revision
     or not (action_row.action = any(grant_row.actions))
     or action_row.execution_deadline + interval '24 hours' <= now_at
     or p_credential_expires_at > action_row.execution_deadline + interval '24 hours' then
    raise exception 'effect is not postobservable' using errcode = '55000';
  end if;
  if action_row.postobserve_use_nonce is not null then
    if action_row.postobserve_use_nonce = p_postobserve_use_nonce
       and action_row.postobserve_expires_at = p_credential_expires_at then
      return pg_catalog.to_jsonb(action_row);
    end if;
    if action_row.postobserve_expires_at > now_at then
      raise exception 'postobserve already began with another live nonce'
        using errcode = '55000';
    end if;
  end if;
  update connected_app_private.action_ledger as ledger
  set postobserve_use_nonce = p_postobserve_use_nonce,
      postobserve_started_at = now_at,
      postobserve_expires_at = p_credential_expires_at,
      postobserve_consumed_at = null,
      updated_at = now_at
  where ledger.operation_id = p_operation_id
  returning * into action_row;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_begin_postobserve_v1(uuid,uuid,uuid,uuid,timestamptz,text) is
  'ASK_CRUMP_CONNECTED_APP_BEGIN_POSTOBSERVE_V1_DISTINCT_NONCE';

create or replace function public.connected_app_consume_credential_lease_v1(
  p_operation_id uuid,
  p_owner_id uuid,
  p_connection_id uuid,
  p_action_id uuid,
  p_action text,
  p_claim_id uuid,
  p_fencing_token bigint,
  p_phase text,
  p_use_nonce uuid,
  p_credential_expires_at timestamptz,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,
  p_authority_sha256 text,
  p_task_state_revision bigint
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
  expected_nonce uuid;
  expected_expires_at timestamptz;
  already_consumed_at timestamptz;
  phase_state_valid boolean;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_operation_id is null or p_owner_id is null or p_connection_id is null
     or p_action_id is null or p_action is null or p_claim_id is null
     or p_use_nonce is null or p_fencing_token is null or p_fencing_token < 1
     or p_phase is null
     or p_phase not in ('read', 'preobserve', 'effect', 'postobserve')
     or p_credential_expires_at is null or p_credential_expires_at <= now_at
     or p_authorization_revision is null or p_authorization_revision < 1
     or p_task_state_revision is null or p_task_state_revision < 1
     or p_authorization_snapshot_sha256 is null
     or p_authorization_snapshot_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_actions_sha256 is null
     or p_granted_actions_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_scopes_sha256 is null
     or p_granted_scopes_sha256 !~ '^[0-9a-f]{64}$'
     or p_authority_sha256 is null
     or p_authority_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid credential lease consumption bounds'
      using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id and ledger.owner_id = p_owner_id
  for update;
  if not found then
    raise exception 'credential lease action not found' using errcode = '55000';
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = action_row.connection_id and connection.owner_id = p_owner_id
  for update;
  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = action_row.grant_id
  for update;

  if p_phase = 'read' then
    expected_nonce := action_row.read_use_nonce;
    expected_expires_at := action_row.read_credential_expires_at;
    already_consumed_at := action_row.read_consumed_at;
    phase_state_valid := action_row.status = 'access_granted'
      and action_row.access_phase = 'read' and not action_row.mutates_external_state;
  elsif p_phase = 'preobserve' then
    expected_nonce := action_row.preobserve_use_nonce;
    expected_expires_at := action_row.preobserve_credential_expires_at;
    already_consumed_at := action_row.preobserve_consumed_at;
    phase_state_valid := action_row.status = 'access_granted'
      and action_row.access_phase = 'preobserve' and action_row.mutates_external_state;
  elsif p_phase = 'effect' then
    expected_nonce := action_row.effect_use_nonce;
    expected_expires_at := action_row.effect_credential_expires_at;
    already_consumed_at := action_row.effect_consumed_at;
    phase_state_valid := action_row.status = 'effect_possible'
      and action_row.mutates_external_state
      and action_row.preobserve_consumed_at is not null;
  else
    expected_nonce := action_row.postobserve_use_nonce;
    expected_expires_at := action_row.postobserve_expires_at;
    already_consumed_at := action_row.postobserve_consumed_at;
    phase_state_valid := action_row.status = 'effect_possible'
      and action_row.mutates_external_state
      and action_row.effect_consumed_at is not null;
  end if;

  if connection_row.id is null or grant_row.grant_id is null
     or not phase_state_valid
     or action_row.connection_id <> p_connection_id
     or action_row.action_id <> p_action_id
     or action_row.action <> p_action
     or action_row.claim_id <> p_claim_id
     or action_row.fencing_token <> p_fencing_token
     or action_row.authorization_revision <> p_authorization_revision
     or action_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or action_row.granted_actions_sha256 <> p_granted_actions_sha256
     or action_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or action_row.authority_sha256 <> p_authority_sha256
     or action_row.task_state_revision <> p_task_state_revision
     or expected_nonce is distinct from p_use_nonce
     or expected_expires_at is distinct from p_credential_expires_at
     or action_row.execution_deadline <= now_at
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> action_row.provider
     or connection_row.resource <> action_row.resource
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or not (p_action = any(connection_row.granted_actions))
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at)
     or (connection_row.authorization_expires_at is not null
         and p_credential_expires_at > connection_row.authorization_expires_at)
     or grant_row.owner_id <> p_owner_id
     or grant_row.task_id <> action_row.task_id
     or grant_row.turn_id <> action_row.turn_id
     or grant_row.connection_id <> p_connection_id
     or grant_row.provider <> action_row.provider
     or grant_row.resource <> action_row.resource
     or grant_row.authorization_revision <> p_authorization_revision
     or grant_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or grant_row.task_state_revision <> p_task_state_revision
     or grant_row.revoked_at is not null or grant_row.expires_at <= now_at
     or p_credential_expires_at > grant_row.expires_at
     or not (p_action = any(grant_row.actions)) then
    raise exception 'credential lease authority changed' using errcode = '55000';
  end if;
  if already_consumed_at is not null then
    raise exception 'credential lease already consumed' using errcode = '55000';
  end if;

  if p_phase = 'read' then
    update connected_app_private.action_ledger as ledger
    set read_consumed_at = now_at, updated_at = now_at
    where ledger.operation_id = p_operation_id and ledger.read_consumed_at is null;
  elsif p_phase = 'preobserve' then
    update connected_app_private.action_ledger as ledger
    set preobserve_consumed_at = now_at, updated_at = now_at
    where ledger.operation_id = p_operation_id and ledger.preobserve_consumed_at is null;
  elsif p_phase = 'effect' then
    update connected_app_private.action_ledger as ledger
    set effect_consumed_at = now_at, updated_at = now_at
    where ledger.operation_id = p_operation_id and ledger.effect_consumed_at is null;
  else
    update connected_app_private.action_ledger as ledger
    set postobserve_consumed_at = now_at, updated_at = now_at
    where ledger.operation_id = p_operation_id and ledger.postobserve_consumed_at is null;
  end if;
  if not found then
    raise exception 'credential lease consumption lost its fence' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'operation_id', p_operation_id,
    'action_id', p_action_id,
    'phase', p_phase,
    'consumed', true,
    'consumed_at', now_at
  );
end;
$fn$;
comment on function public.connected_app_consume_credential_lease_v1(
  uuid,uuid,uuid,uuid,text,uuid,bigint,text,uuid,timestamptz,bigint,text,text,text,text,bigint
) is 'ASK_CRUMP_CONNECTED_APP_CONSUME_CREDENTIAL_LEASE_V1_ONE_USE_PHASE_FENCE';

create or replace function public.connected_app_settle_action_v1(
  p_operation_id uuid,
  p_owner_id uuid,
  p_access_use_nonce uuid,
  p_effect_use_nonce uuid,
  p_postobserve_use_nonce uuid,
  p_postobserve_impossible boolean,
  p_terminal_outcome text,
  p_terminal_binding_sha256 text,
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
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_postobserve_impossible is null
     or p_terminal_outcome is null
     or p_terminal_outcome not in ('read', 'succeeded', 'ambiguous', 'failed')
     or p_terminal_binding_sha256 is null then
    raise exception 'invalid terminal action result' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id = p_operation_id and ledger.owner_id = p_owner_id
  for update;
  if not found then
    raise exception 'action not found' using errcode = '55000';
  end if;
  if action_row.status = 'terminal' then
    if action_row.terminal_binding_sha256 = p_terminal_binding_sha256
       and action_row.terminal_outcome = p_terminal_outcome
       and action_row.postobserve_impossible = p_postobserve_impossible then
      return pg_catalog.to_jsonb(action_row);
    end if;
    raise exception 'terminal action replay drifted' using errcode = '55000';
  end if;
  if p_observed_at is null
     or p_observed_at < action_row.created_at
     or p_observed_at > now_at + interval '1 minute' then
    raise exception 'action observation timestamp is invalid' using errcode = '22023';
  end if;
  if (
       not action_row.mutates_external_state
       and (
         action_row.status <> 'access_granted'
         or action_row.access_phase <> 'read'
         or action_row.read_use_nonce is distinct from p_access_use_nonce
          or action_row.read_consumed_at is null
         or p_effect_use_nonce is not null
         or p_postobserve_use_nonce is not null
         or p_postobserve_impossible
         or p_terminal_outcome <> 'read'
       )
     ) or (
       action_row.mutates_external_state
       and (
         action_row.status <> 'effect_possible'
         or action_row.access_phase <> 'preobserve'
         or action_row.preobserve_use_nonce is null
         or action_row.preobserve_use_nonce is distinct from p_access_use_nonce
          or action_row.preobserve_consumed_at is null
         or action_row.effect_use_nonce is null
         or action_row.effect_use_nonce is distinct from p_effect_use_nonce
          or action_row.effect_consumed_at is null
         or p_terminal_outcome = 'read'
         or (
           p_postobserve_impossible
           and (
             p_terminal_outcome <> 'ambiguous'
             or action_row.postobserve_use_nonce is not null
             or p_postobserve_use_nonce is not null
           )
         )
         or (
           not p_postobserve_impossible
            and not (
              (
                p_terminal_outcome = 'succeeded'
                and action_row.action in (
                  'mail.create_draft', 'mail.send', 'mail.reply', 'calendar.create'
                )
                and action_row.postobserve_use_nonce is null
                and p_postobserve_use_nonce is null
                and p_provider_request_id_sha256 is not null
                and p_provider_resource_id_sha256 is not null
                and action_row.effect_started_at is not null
                and p_observed_at >= action_row.effect_started_at
              )
              or (
                action_row.postobserve_use_nonce is not null
                and p_postobserve_use_nonce is not null
                and action_row.postobserve_use_nonce = p_postobserve_use_nonce
                and action_row.postobserve_started_at is not null
                and action_row.postobserve_consumed_at is not null
                and p_observed_at >= action_row.postobserve_started_at
              )
            )
         )
       )
     ) then
    raise exception 'action phase receipt mismatch' using errcode = '55000';
  end if;
  update connected_app_private.action_ledger as ledger
  set status = 'terminal', terminal_outcome = p_terminal_outcome,
      terminal_binding_sha256 = p_terminal_binding_sha256,
      provider_request_id_sha256 = p_provider_request_id_sha256,
      provider_resource_id_sha256 = p_provider_resource_id_sha256,
      observed_at = p_observed_at,
      postobserve_impossible = p_postobserve_impossible,
      terminal_at = now_at,
      updated_at = now_at
  where ledger.operation_id = p_operation_id
  returning * into action_row;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_settle_action_v1(
  uuid,uuid,uuid,uuid,uuid,boolean,text,text,text,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_SETTLE_ACTION_V1_POSTOBSERVE_OR_EXPLICIT_IMPOSSIBLE';

create or replace function public.connected_app_read_action_v1(
  p_owner_id uuid,
  p_operation_id uuid,
  p_idempotency_key_sha256 text
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
     or p_idempotency_key_sha256 is null then
    raise exception 'action readback keys are required' using errcode = '22023';
  end if;
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.owner_id = p_owner_id
    and ledger.operation_id = p_operation_id
    and ledger.idempotency_key_sha256 = p_idempotency_key_sha256;
  if not found then
    if exists (
      select 1 from connected_app_private.action_ledger as ledger
      where ledger.owner_id = p_owner_id
        and (
          ledger.operation_id = p_operation_id
          or ledger.idempotency_key_sha256 = p_idempotency_key_sha256
        )
    ) then
      raise exception 'action readback keys refer to different rows'
        using errcode = '55000';
    end if;
    return null;
  end if;
  return pg_catalog.to_jsonb(action_row);
end;
$fn$;
comment on function public.connected_app_read_action_v1(uuid,uuid,text) is
  'ASK_CRUMP_CONNECTED_APP_READ_ACTION_V1_RESPONSE_LOSS_READBACK';

create or replace function public.connected_app_claim_schedule_v1(
  p_claim_id uuid,
  p_lease_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  candidate record;
  schedule_row connected_app_private.schedules%rowtype;
  connection_row connected_app_private.connections%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
  local_minute integer;
begin
  if p_claim_id is null or p_lease_seconds not between 30 and 300 then
    raise exception 'invalid schedule lease' using errcode = '22023';
  end if;
  select schedule.schedule_id, schedule.owner_id
    into candidate
  from connected_app_private.schedules as schedule
  where schedule.claim_id = p_claim_id;
  if found then
    perform connected_app_private.owner_lock_v1(candidate.owner_id);
    select schedule.* into schedule_row
    from connected_app_private.schedules as schedule
    where schedule.schedule_id = candidate.schedule_id
      and schedule.claim_id = p_claim_id
    for update;
    if found then
      select connection.* into connection_row
      from connected_app_private.connections as connection
      where connection.id = schedule_row.connection_id
        and connection.owner_id = candidate.owner_id
      for update;
      select authority.* into authority_row
      from connected_app_private.action_authority as authority
      where authority.action = schedule_row.action;
      if connection_row.id is not null
         and connection_row.authorization_state = 'active'
         and connection_row.provider = schedule_row.provider
         and connection_row.resource = schedule_row.resource
         and schedule_row.action = any(connection_row.granted_actions)
         and (connection_row.authorization_expires_at is null
              or connection_row.authorization_expires_at > now_at)
         and authority_row.action is not null
         and authority_row.resource = schedule_row.resource
         and (not authority_row.mutates_external_state
              or schedule_row.requires_approval_every_run) then
        return pg_catalog.to_jsonb(schedule_row);
      end if;
      update connected_app_private.schedules as schedule
      set status = 'paused', next_run_at = null,
          claim_id = null, claim_expires_at = null,
          updated_at = now_at
      where schedule.schedule_id = candidate.schedule_id;
      return null;
    end if;
  end if;
  -- Scan a bounded set so one revoked, expired, quiet, concurrently locked,
  -- or owner-busy schedule cannot starve all later eligible work.  A
  -- nonblocking owner advisory lock is acquired before row locks; busy owners
  -- are skipped rather than blocking the entire scheduler claim.
  for candidate in
    select schedule.schedule_id, schedule.owner_id
    from connected_app_private.schedules as schedule
    where schedule.status = 'active'
      and schedule.next_run_at <= now_at
      and (schedule.claim_id is null or schedule.claim_expires_at <= now_at)
    order by schedule.next_run_at, schedule.schedule_id
    limit 32
  loop
    if not pg_catalog.pg_try_advisory_xact_lock(
      pg_catalog.hashtextextended(
        candidate.owner_id::text, 606232723337443413::bigint
      )
    ) then
      continue;
    end if;
    select schedule.* into schedule_row
    from connected_app_private.schedules as schedule
    where schedule.schedule_id = candidate.schedule_id
      and schedule.owner_id = candidate.owner_id
      and schedule.status = 'active'
      and schedule.next_run_at <= now_at
      and (schedule.claim_id is null or schedule.claim_expires_at <= now_at)
    for update skip locked;
    if not found then
      continue;
    end if;

    select connection.* into connection_row
    from connected_app_private.connections as connection
    where connection.id = schedule_row.connection_id
      and connection.owner_id = candidate.owner_id
    for update;
    if not found or connection_row.authorization_state <> 'active'
       or connection_row.provider <> schedule_row.provider
       or connection_row.resource <> schedule_row.resource
       or not (schedule_row.action = any(connection_row.granted_actions))
       or (connection_row.authorization_expires_at is not null
           and connection_row.authorization_expires_at <= now_at) then
      update connected_app_private.schedules as schedule
      set status = 'paused', next_run_at = null,
          claim_id = null, claim_expires_at = null,
          updated_at = now_at
      where schedule.schedule_id = candidate.schedule_id;
      continue;
    end if;

    select authority.* into authority_row
    from connected_app_private.action_authority as authority
    where authority.action = schedule_row.action;
    if not found or authority_row.resource <> schedule_row.resource
       or (authority_row.mutates_external_state
           and not schedule_row.requires_approval_every_run) then
      update connected_app_private.schedules as schedule
      set status = 'paused', next_run_at = null,
          claim_id = null, claim_expires_at = null,
          updated_at = now_at
      where schedule.schedule_id = candidate.schedule_id;
      continue;
    end if;

    if schedule_row.quiet_start_minute is not null then
      local_minute := (
        extract(hour from pg_catalog.timezone(schedule_row.time_zone, now_at))::integer * 60
        + extract(minute from pg_catalog.timezone(schedule_row.time_zone, now_at))::integer
      );
      if (
        schedule_row.quiet_start_minute < schedule_row.quiet_end_minute
        and local_minute >= schedule_row.quiet_start_minute
        and local_minute < schedule_row.quiet_end_minute
      ) or (
        schedule_row.quiet_start_minute > schedule_row.quiet_end_minute
        and (local_minute >= schedule_row.quiet_start_minute
             or local_minute < schedule_row.quiet_end_minute)
      ) or schedule_row.quiet_start_minute = schedule_row.quiet_end_minute then
        update connected_app_private.schedules as schedule
        set next_run_at = greatest(
              schedule.next_run_at
                + pg_catalog.make_interval(secs => schedule.cadence_seconds),
              now_at + interval '60 seconds'
            ),
            claim_id = null, claim_expires_at = null, updated_at = now_at
        where schedule.schedule_id = candidate.schedule_id;
        continue;
      end if;
    end if;

    update connected_app_private.schedules as schedule
    set claim_id = p_claim_id,
        claim_expires_at = now_at + pg_catalog.make_interval(secs => p_lease_seconds),
        updated_at = now_at
    where schedule.schedule_id = candidate.schedule_id
    returning * into schedule_row;
    return pg_catalog.to_jsonb(schedule_row);
  end loop;
  return null;
end;
$fn$;
comment on function public.connected_app_claim_schedule_v1(uuid,integer) is
  'ASK_CRUMP_CONNECTED_APP_CLAIM_SCHEDULE_V1_BOUNDED_SKIP_LOCKED_SCAN';

create or replace function public.connected_app_finish_schedule_v1(
  p_schedule_id uuid,
  p_owner_id uuid,
  p_claim_id uuid,
  p_next_run_at timestamptz,
  p_task_state_revision bigint
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  schedule_row connected_app_private.schedules%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_next_run_at < now_at + interval '60 seconds'
     or p_next_run_at > now_at + interval '31 days'
     or p_task_state_revision < 1 then
    raise exception 'invalid schedule completion bounds' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select schedule.* into schedule_row
  from connected_app_private.schedules as schedule
  where schedule.schedule_id = p_schedule_id and schedule.owner_id = p_owner_id
  for update;
  if found and schedule_row.claim_id is null
     and schedule_row.completed_claim_id = p_claim_id
     and schedule_row.next_run_at = p_next_run_at
     and schedule_row.task_state_revision = p_task_state_revision then
    return pg_catalog.to_jsonb(schedule_row);
  end if;
  if not found or schedule_row.claim_id <> p_claim_id
     or schedule_row.claim_expires_at <= now_at
     or schedule_row.task_state_revision <> p_task_state_revision then
    raise exception 'schedule claim is stale' using errcode = '55000';
  end if;
  update connected_app_private.schedules as schedule
  set claim_id = null, claim_expires_at = null,
      completed_claim_id = p_claim_id, completed_at = now_at,
      next_run_at = p_next_run_at, updated_at = now_at
  where schedule.schedule_id = p_schedule_id
  returning * into schedule_row;
  return pg_catalog.to_jsonb(schedule_row);
end;
$fn$;
comment on function public.connected_app_finish_schedule_v1(uuid,uuid,uuid,timestamptz,bigint) is
  'ASK_CRUMP_CONNECTED_APP_FINISH_SCHEDULE_V1_EXACT_CLAIM';

create or replace function public.connected_app_put_schedule_v1(
  p_schedule_id uuid, p_owner_id uuid, p_connection_id uuid, p_task_id uuid,
  p_provider text, p_resource text, p_action text, p_action_template_ref uuid,
  p_parameters_sha256 text, p_task_state_revision bigint, p_time_zone text,
  p_cadence_seconds integer, p_quiet_start_minute integer,
  p_quiet_end_minute integer, p_requires_approval_every_run boolean,
  p_status text, p_next_run_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  schedule_row connected_app_private.schedules%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_schedule_id is null or p_owner_id is null or p_connection_id is null
     or p_task_id is null or p_action_template_ref is null
     or p_requires_approval_every_run is null
     or p_task_state_revision < 1
     or not exists (
       select 1 from pg_catalog.pg_timezone_names as zone_row
       where zone_row.name = p_time_zone
     )
     or p_next_run_at < now_at - interval '1 minute'
     or p_next_run_at > now_at + interval '31 days' then
    raise exception 'invalid schedule bounds' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action = p_action;
  if not found or authority_row.resource <> p_resource
     or (authority_row.mutates_external_state
         and not p_requires_approval_every_run) then
    raise exception 'schedule action is not in the database allowlist'
      using errcode = '55000';
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id
  for update;
  if not found or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or not (p_action = any(connection_row.granted_actions))
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at) then
    raise exception 'schedule connection authority changed' using errcode = '55000';
  end if;
  select schedule.* into schedule_row
  from connected_app_private.schedules as schedule
  where schedule.schedule_id = p_schedule_id
  for update;
  if found then
    if schedule_row.owner_id <> p_owner_id
       or schedule_row.connection_id <> p_connection_id
       or schedule_row.task_id <> p_task_id
       or schedule_row.provider <> p_provider
       or schedule_row.resource <> p_resource
       or schedule_row.action <> p_action
       or schedule_row.action_template_ref <> p_action_template_ref
       or schedule_row.parameters_sha256 <> p_parameters_sha256
       or schedule_row.requires_approval_every_run <> p_requires_approval_every_run
       or schedule_row.task_state_revision > p_task_state_revision
       or schedule_row.claim_id is not null then
      raise exception 'schedule update drifted or is claimed' using errcode = '55000';
    end if;
    if schedule_row.task_state_revision = p_task_state_revision then
      if schedule_row.time_zone <> p_time_zone
         or schedule_row.cadence_seconds <> p_cadence_seconds
         or schedule_row.quiet_start_minute is distinct from p_quiet_start_minute
         or schedule_row.quiet_end_minute is distinct from p_quiet_end_minute
         or schedule_row.requires_approval_every_run <> p_requires_approval_every_run
         or schedule_row.status <> p_status
         or schedule_row.next_run_at <> p_next_run_at then
        raise exception 'same-revision schedule replay drifted'
          using errcode = '55000';
      end if;
      return pg_catalog.to_jsonb(schedule_row);
    end if;
    update connected_app_private.schedules as schedule
    set task_state_revision = p_task_state_revision, time_zone = p_time_zone,
        cadence_seconds = p_cadence_seconds,
        quiet_start_minute = p_quiet_start_minute,
        quiet_end_minute = p_quiet_end_minute,
        requires_approval_every_run = p_requires_approval_every_run,
        status = p_status,
        next_run_at = p_next_run_at, updated_at = now_at
    where schedule.schedule_id = p_schedule_id
    returning * into schedule_row;
    return pg_catalog.to_jsonb(schedule_row);
  end if;
  insert into connected_app_private.schedules (
    schedule_id, owner_id, connection_id, task_id, provider, resource,
    action, action_template_ref, parameters_sha256, task_state_revision,
    time_zone, cadence_seconds, quiet_start_minute, quiet_end_minute,
    requires_approval_every_run, status, next_run_at
  ) values (
    p_schedule_id, p_owner_id, p_connection_id, p_task_id, p_provider,
    p_resource, p_action, p_action_template_ref, p_parameters_sha256,
    p_task_state_revision, p_time_zone, p_cadence_seconds,
    p_quiet_start_minute, p_quiet_end_minute, p_requires_approval_every_run,
    p_status, p_next_run_at
  ) returning * into schedule_row;
  return pg_catalog.to_jsonb(schedule_row);
end;
$fn$;
comment on function public.connected_app_put_schedule_v1(
  uuid,uuid,uuid,uuid,text,text,text,uuid,text,bigint,text,integer,integer,integer,boolean,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_PUT_SCHEDULE_V1_MONOTONIC_TASK_REVISION';

create or replace function connected_app_private.enqueue_owner_cleanup_before_delete_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  credential_hash text;
  cleanup_binding text;
begin
  -- The trigger is the first connected-app participant in account deletion.
  -- Acquire the same owner advisory lock used by OAuth, actions, and revoke
  -- before snapshotting connection rows or enqueueing unlinked cleanup work.
  perform connected_app_private.owner_lock_v1(old.id);
  for connection_row in
    select connection.*
    from connected_app_private.connections as connection
    where connection.owner_id = old.id
      and connection.broker_credential_ref is not null
    order by connection.id
    for update
  loop
    credential_hash := connection_row.credential_ref_sha256;
    cleanup_binding := connection_row.credential_ref_sha256;
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(credential_hash, 81424519024640287::bigint)
    );
    insert into connected_app_private.credential_ref_tombstones (
      credential_ref_sha256, provider
    ) values (
      credential_hash, connection_row.provider
    ) on conflict (credential_ref_sha256) do nothing;
    if exists (
      select 1
      from connected_app_private.credential_ref_tombstones as tombstone
      where tombstone.credential_ref_sha256 = credential_hash
        and tombstone.provider <> connection_row.provider
    ) then
      raise exception 'credential tombstone provider drifted' using errcode = '55000';
    end if;
    insert into connected_app_private.credential_cleanup_outbox (
      cleanup_id, broker_credential_ref, credential_ref_sha256,
      provider, reason, cleanup_binding_sha256
    ) values (
      pg_catalog.gen_random_uuid(), connection_row.broker_credential_ref,
      credential_hash, connection_row.provider, 'owner_deleted', cleanup_binding
    ) on conflict (cleanup_binding_sha256) do nothing;
  end loop;
  return old;
end;
$fn$;
comment on function connected_app_private.enqueue_owner_cleanup_before_delete_v1() is
  'ASK_CRUMP_CONNECTED_APP_OWNER_DELETE_CLEANUP_V1_NO_IDENTITY_OR_CONTENT';
revoke all on function connected_app_private.enqueue_owner_cleanup_before_delete_v1()
  from public, anon, authenticated, service_role;

create or replace trigger connected_app_owner_delete_cleanup_v1
before delete on public.users
for each row execute function connected_app_private.enqueue_owner_cleanup_before_delete_v1();
comment on trigger connected_app_owner_delete_cleanup_v1 on public.users is
  'ASK_CRUMP_CONNECTED_APP_OWNER_DELETE_CLEANUP_V1_EXPLICIT_ATTESTED_TRIGGER';

create or replace function public.connected_app_create_connection_v1(
  p_connection_id uuid,
  p_owner_id uuid,
  p_provider text,
  p_resource text,
  p_account_kind text,
  p_connection_incarnation_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
begin
  if p_connection_id is null or p_owner_id is null
     or p_connection_incarnation_id is null then
    raise exception 'connection identifiers are required' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id
  for update;
  if found then
    if connection_row.owner_id <> p_owner_id
       or connection_row.provider <> p_provider
       or connection_row.resource <> p_resource
       or connection_row.account_kind <> p_account_kind
       or connection_row.connection_incarnation_id <> p_connection_incarnation_id then
      raise exception 'connection replay drifted' using errcode = '55000';
    end if;
    return pg_catalog.to_jsonb(connection_row) - 'broker_credential_ref';
  end if;
  insert into connected_app_private.connections (
    id, owner_id, provider, resource, account_kind,
    connection_incarnation_id
  ) values (
    p_connection_id, p_owner_id, p_provider, p_resource, p_account_kind,
    p_connection_incarnation_id
  ) returning * into connection_row;
  return pg_catalog.to_jsonb(connection_row) - 'broker_credential_ref';
end;
$fn$;
comment on function public.connected_app_create_connection_v1(uuid,uuid,text,text,text,uuid) is
  'ASK_CRUMP_CONNECTED_APP_CREATE_CONNECTION_V1_PENDING_ONLY';

create or replace function public.connected_app_purge_cleanup_v1(
  p_cutoff timestamptz,
  p_max_rows integer
)
returns integer
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  deleted_rows integer;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_cutoff is null or p_cutoff > now_at
     or p_cutoff < now_at - interval '24 hours'
     or p_max_rows not between 1 and 500 then
    raise exception 'invalid cleanup purge bounds' using errcode = '22023';
  end if;
  with expired as (
    select cleanup.cleanup_id
    from connected_app_private.credential_cleanup_outbox as cleanup
    where cleanup.status in ('completed', 'failed_permanent')
      and cleanup.delete_after <= p_cutoff
    order by cleanup.delete_after, cleanup.cleanup_id
    for update skip locked
    limit p_max_rows
  )
  delete from connected_app_private.credential_cleanup_outbox as cleanup
  using expired
  where cleanup.cleanup_id = expired.cleanup_id;
  get diagnostics deleted_rows = row_count;
  return deleted_rows;
end;
$fn$;
comment on function public.connected_app_purge_cleanup_v1(timestamptz,integer) is
  'ASK_CRUMP_CONNECTED_APP_PURGE_CLEANUP_V1_BOUNDED_TERMINAL_RETENTION';

create or replace function connected_app_private.connection_view_v1(
  p_owner_id uuid, p_connection_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'connection_id', connection.id,
    'provider', connection.provider,
    'resource', connection.resource,
    'account_kind', connection.account_kind,
    'granted_actions', connection.granted_actions,
    'authorization_state', connection.authorization_state,
    'authorization_revision', connection.authorization_revision,
    'authorization_snapshot_sha256', connection.authorization_snapshot_sha256,
    'authorization_expires_at', connection.authorization_expires_at,
    'updated_at', connection.updated_at
  )
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id
    and connection.id = p_connection_id
    and connection.authorization_state in ('active', 'revoked')
$fn$;
comment on function connected_app_private.connection_view_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_CONNECTION_VIEW_V1_CONTENT_FREE';

create or replace function connected_app_private.schedule_view_v1(
  p_owner_id uuid, p_schedule_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'schedule_id', schedule.schedule_id,
    'connection_id', schedule.connection_id,
    'task_id', schedule.task_id,
    'provider', schedule.provider,
    'resource', schedule.resource,
    'action', schedule.action,
    'action_template_ref', schedule.action_template_ref,
    'parameters_sha256', schedule.parameters_sha256,
    'task_state_revision', schedule.task_state_revision,
    'time_zone', schedule.time_zone,
    'cadence_seconds', schedule.cadence_seconds,
    'quiet_start_minute', schedule.quiet_start_minute,
    'quiet_end_minute', schedule.quiet_end_minute,
    'requires_approval_every_run', schedule.requires_approval_every_run,
    'status', schedule.status,
    'next_run_at', schedule.next_run_at,
    'updated_at', schedule.updated_at
  )
  from connected_app_private.schedules as schedule
  where schedule.owner_id = p_owner_id and schedule.schedule_id = p_schedule_id
$fn$;
comment on function connected_app_private.schedule_view_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_SCHEDULE_VIEW_V1_CONTENT_FREE';

create or replace function connected_app_private.action_view_v1(
  p_owner_id uuid, p_action_id uuid
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $fn$
declare
  review_row connected_app_private.approval_reviews%rowtype;
  ledger_row connected_app_private.action_ledger%rowtype;
  public_status text;
begin
  select review.* into review_row
  from connected_app_private.approval_reviews as review
  where review.owner_id = p_owner_id and review.action_id = p_action_id;

  -- One logical action may have more than one operation attempt.  The
  -- operator projection is deliberately singular and follows the newest.
  select ledger.* into ledger_row
  from connected_app_private.action_ledger as ledger
  where ledger.owner_id = p_owner_id and ledger.action_id = p_action_id
  order by ledger.updated_at desc, ledger.operation_id desc
  limit 1;

  if review_row.approval_id is null and ledger_row.operation_id is null then
    return null;
  end if;
  if review_row.approval_id is not null and ledger_row.operation_id is not null
     and (
       review_row.connection_id <> ledger_row.connection_id
       or review_row.task_id <> ledger_row.task_id
       or review_row.turn_id <> ledger_row.turn_id
       or review_row.provider <> ledger_row.provider
       or review_row.resource <> ledger_row.resource
       or review_row.action <> ledger_row.action
       or review_row.authorization_revision <> ledger_row.authorization_revision
       or review_row.authorization_snapshot_sha256
          <> ledger_row.authorization_snapshot_sha256
       or review_row.granted_scopes_sha256 <> ledger_row.granted_scopes_sha256
       or review_row.parameters_sha256 <> ledger_row.parameters_sha256
       or review_row.resource_version_sha256
          is distinct from ledger_row.resource_version_sha256
     ) then
    raise exception 'public action projection binding drifted'
      using errcode = '55000';
  end if;

  public_status := case
    when review_row.status = 'pending' then 'pending_approval'
    when review_row.status = 'denied' then 'cancelled'
    when ledger_row.status = 'terminal'
      and ledger_row.terminal_outcome in ('succeeded', 'read') then 'succeeded'
    when ledger_row.status = 'terminal'
      and ledger_row.terminal_outcome = 'ambiguous' then 'ambiguous'
    when ledger_row.status = 'terminal'
      and ledger_row.terminal_outcome = 'failed' then 'failed'
    when ledger_row.status in ('access_granted', 'effect_possible') then 'running'
    else 'claimed'
  end;
  return pg_catalog.jsonb_build_object(
    'action_id', coalesce(review_row.action_id, ledger_row.action_id),
    'connection_id', coalesce(review_row.connection_id, ledger_row.connection_id),
    'task_id', coalesce(review_row.task_id, ledger_row.task_id),
    'turn_id', coalesce(review_row.turn_id, ledger_row.turn_id),
    'provider', coalesce(review_row.provider, ledger_row.provider),
    'resource', coalesce(review_row.resource, ledger_row.resource),
    'action', coalesce(review_row.action, ledger_row.action),
    'authorization_revision', coalesce(
      review_row.authorization_revision, ledger_row.authorization_revision
    ),
    'authorization_snapshot_sha256', coalesce(
      review_row.authorization_snapshot_sha256,
      ledger_row.authorization_snapshot_sha256
    ),
    'granted_scopes_sha256', coalesce(
      review_row.granted_scopes_sha256, ledger_row.granted_scopes_sha256
    ),
    'policy_version', coalesce(review_row.policy_version, 'connected-app-policy-v1'),
    'action_revision', coalesce(review_row.action_revision, 1::bigint),
    'status', public_status,
    'parameters_sha256', coalesce(
      review_row.parameters_sha256, ledger_row.parameters_sha256
    ),
    'resource_version_sha256', coalesce(
      review_row.resource_version_sha256, ledger_row.resource_version_sha256
    ),
    'preview_sha256', review_row.preview_sha256,
    'updated_at', greatest(
      coalesce(review_row.updated_at, '-infinity'::timestamptz),
      coalesce(ledger_row.updated_at, '-infinity'::timestamptz)
    )
  );
end;
$fn$;
comment on function connected_app_private.action_view_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_ACTION_VIEW_V1_CONTENT_FREE';

create or replace function connected_app_private.approval_view_v1(
  p_owner_id uuid, p_approval_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'approval_id', review.approval_id,
    'action_id', review.action_id,
    'connection_id', review.connection_id,
    'task_id', review.task_id,
    'turn_id', review.turn_id,
    'provider', review.provider,
    'resource', review.resource,
    'action', review.action,
    'authorization_revision', review.authorization_revision,
    'authorization_snapshot_sha256', review.authorization_snapshot_sha256,
    'granted_scopes_sha256', review.granted_scopes_sha256,
    'policy_version', review.policy_version,
    'action_revision', review.action_revision,
    'status', case when review.status = 'pending'
                         and review.expires_at <= pg_catalog.statement_timestamp()
                    then 'expired' else review.status end,
    'approval_binding_sha256', review.approval_binding_sha256,
    'parameters_sha256', review.parameters_sha256,
    'resource_version_sha256', review.resource_version_sha256,
    'preview_sha256', review.preview_sha256,
    'review_payload_ref', review.review_payload_ref,
    'decision_id', review.decision_id,
    'decision_session_binding_sha256', review.decision_session_binding_sha256,
    'expires_at', review.expires_at,
    'decided_at', review.decided_at
  )
  from connected_app_private.approval_reviews as review
  where review.owner_id = p_owner_id and review.approval_id = p_approval_id
$fn$;
comment on function connected_app_private.approval_view_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_APPROVAL_VIEW_V1_PAYLOAD_REFERENCE_ONLY';

create or replace function connected_app_private.action_preparation_view_v1(
  p_owner_id uuid, p_request_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'request_id', preparation.request_id,
    'owner_id', preparation.owner_id,
    'command_binding_sha256', preparation.command_binding_sha256,
    'grant_id', preparation.grant_id,
    'action_id', preparation.action_id,
    'task_id', preparation.task_id,
    'turn_id', preparation.turn_id,
    'connection_id', preparation.connection_id,
    'provider', preparation.provider,
    'resource', preparation.resource,
    'action', preparation.action,
    'authorization_revision', preparation.authorization_revision,
    'authorization_snapshot_sha256', preparation.authorization_snapshot_sha256,
    'granted_actions_sha256', preparation.granted_actions_sha256,
    'granted_scopes_sha256', preparation.granted_scopes_sha256,
    'grant_actions_sha256', preparation.grant_actions_sha256,
    'task_state_revision', preparation.task_state_revision,
    'payload_id', preparation.payload_id,
    'payload_reference_binding_sha256', preparation.payload_reference_binding_sha256,
    'parameters_sha256', preparation.parameters_sha256,
    'resource_version_sha256', preparation.resource_version_sha256,
    'policy_version', preparation.policy_version,
    'mutates_external_state', preparation.mutates_external_state,
    'approval_class', preparation.approval_class,
    'status', preparation.status,
    'approval_id', preparation.approval_id,
    'approval_binding_sha256', preparation.approval_binding_sha256,
    'preview_payload_id', preparation.preview_payload_id,
    'preview_reference_binding_sha256', preparation.preview_reference_binding_sha256,
    'preview_sha256', preparation.preview_sha256,
    'requested_at', preparation.requested_at,
    'expires_at', preparation.expires_at
  )
  from connected_app_private.action_preparations as preparation
  where preparation.owner_id = p_owner_id
    and preparation.request_id = p_request_id
$fn$;
comment on function connected_app_private.action_preparation_view_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_ACTION_PREPARATION_VIEW_V1_CONTENT_FREE';

create or replace function public.connected_app_operator_prepare_action_v1(
  p_request_id uuid,
  p_owner_id uuid,
  p_session_id uuid,
  p_session_binding_sha256 text,
  p_command_binding_sha256 text,
  p_grant_id uuid,
  p_action_id uuid,
  p_task_id uuid,
  p_turn_id uuid,
  p_connection_id uuid,
  p_provider text,
  p_resource text,
  p_action text,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,
  p_task_state_revision bigint,
  p_payload_id uuid,
  p_payload_reference_binding_sha256 text,
  p_parameters_sha256 text,
  p_resource_version_sha256 text,
  p_policy_version text,
  p_approval_id uuid,
  p_approval_binding_sha256 text,
  p_preview_payload_id uuid,
  p_preview_reference_binding_sha256 text,
  p_preview_sha256 text,
  p_requested_at timestamptz,
  p_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  preparation_row connected_app_private.action_preparations%rowtype;
  session_row public.sessions%rowtype;
  connection_row connected_app_private.connections%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  grant_row connected_app_private.task_grants%rowtype;
  identity_value uuid;
  grant_actions_sha256 text;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_request_id is null or p_owner_id is null or p_session_id is null
     or p_grant_id is null
     or p_action_id is null or p_task_id is null or p_turn_id is null
     or p_connection_id is null or p_payload_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_command_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_authorization_revision < 1 or p_task_state_revision < 1
     or p_authorization_snapshot_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_actions_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_scopes_sha256 !~ '^[0-9a-f]{64}$'
     or p_payload_reference_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_parameters_sha256 !~ '^[0-9a-f]{64}$'
     or (p_resource_version_sha256 is not null
         and p_resource_version_sha256 !~ '^[0-9a-f]{64}$')
     or p_policy_version <> 'connected-app-policy-v1'
     or p_requested_at < now_at - interval '5 minutes'
     or p_requested_at > now_at + interval '1 minute'
     or p_expires_at <= now_at
     or p_expires_at <= p_requested_at
     or p_expires_at > p_requested_at + interval '15 minutes' then
    raise exception 'invalid action preparation bounds' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  -- Close the authenticate-request/prepare TOCTOU window.  The raw session ID
  -- is used only for this row lock and is never retained or returned.
  select session.* into session_row
  from public.sessions as session
  where session.id = p_session_id and session.user_id = p_owner_id
  for share;
  if not found or session_row.revoked_at is not null
     or session_row.expires_at <= now_at then
    raise exception 'authenticated session authority changed'
      using errcode = '55000';
  end if;
  -- Owner lock is always first.  Canonically ordered identity locks then make
  -- adversarial UUID reuse deterministic even across different owners.
  for identity_value in
    select identity_row.identity_value
    from pg_catalog.unnest(array[
      p_request_id, p_grant_id, p_action_id, p_payload_id,
      p_approval_id, p_preview_payload_id
    ]::uuid[]) as identity_row(identity_value)
    where identity_row.identity_value is not null
    order by identity_row.identity_value
  loop
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(
        identity_value::text, 729105384609243177::bigint
      )
    );
  end loop;

  select preparation.* into preparation_row
  from connected_app_private.action_preparations as preparation
  where preparation.request_id = p_request_id
  for update;
  if found then
    if preparation_row.owner_id <> p_owner_id
       or preparation_row.session_binding_sha256 <> p_session_binding_sha256
       or preparation_row.command_binding_sha256 <> p_command_binding_sha256
       or preparation_row.grant_id <> p_grant_id
       or preparation_row.action_id <> p_action_id
       or preparation_row.task_id <> p_task_id
       or preparation_row.turn_id <> p_turn_id
       or preparation_row.connection_id <> p_connection_id
       or preparation_row.provider <> p_provider
       or preparation_row.resource <> p_resource
       or preparation_row.action <> p_action
       or preparation_row.authorization_revision <> p_authorization_revision
       or preparation_row.authorization_snapshot_sha256
          <> p_authorization_snapshot_sha256
       or preparation_row.granted_actions_sha256 <> p_granted_actions_sha256
       or preparation_row.granted_scopes_sha256 <> p_granted_scopes_sha256
       or preparation_row.task_state_revision <> p_task_state_revision
       or preparation_row.payload_id <> p_payload_id
       or preparation_row.payload_reference_binding_sha256
          <> p_payload_reference_binding_sha256
       or preparation_row.parameters_sha256 <> p_parameters_sha256
       or preparation_row.resource_version_sha256
          is distinct from p_resource_version_sha256
       or preparation_row.policy_version <> p_policy_version
       or preparation_row.approval_id is distinct from p_approval_id
       or preparation_row.approval_binding_sha256
          is distinct from p_approval_binding_sha256
       or preparation_row.preview_payload_id is distinct from p_preview_payload_id
       or preparation_row.preview_reference_binding_sha256
          is distinct from p_preview_reference_binding_sha256
       or preparation_row.preview_sha256 is distinct from p_preview_sha256
       or preparation_row.requested_at <> p_requested_at
       or preparation_row.expires_at <> p_expires_at then
      raise exception 'action preparation replay drifted' using errcode = '55000';
    end if;
    return connected_app_private.action_preparation_view_v1(
      p_owner_id, p_request_id
    );
  end if;

  if exists (
    select 1
    from connected_app_private.action_preparations as preparation
    where preparation.command_binding_sha256 = p_command_binding_sha256
       or preparation.grant_id = p_grant_id
       or preparation.action_id = p_action_id
       or preparation.payload_id = p_payload_id
       or (p_approval_id is not null and preparation.approval_id = p_approval_id)
       or (p_preview_payload_id is not null
           and preparation.preview_payload_id = p_preview_payload_id)
  ) or exists (
    select 1 from connected_app_private.action_ledger as ledger
    where ledger.action_id = p_action_id
  ) then
    raise exception 'action preparation identity already belongs to a sibling action'
      using errcode = '55000';
  end if;

  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action = p_action;
  if not found or authority_row.resource <> p_resource then
    raise exception 'action is not in the database allowlist'
      using errcode = '55000';
  end if;

  if authority_row.mutates_external_state then
    if p_approval_id is null or p_approval_binding_sha256 is null
       or p_approval_binding_sha256 !~ '^[0-9a-f]{64}$'
       or p_preview_payload_id is null
       or p_preview_payload_id = p_payload_id
       or p_preview_reference_binding_sha256 is null
       or p_preview_reference_binding_sha256 !~ '^[0-9a-f]{64}$'
       or p_preview_sha256 is null
       or p_preview_sha256 !~ '^[0-9a-f]{64}$' then
      raise exception 'write preparation requires an exact encrypted review'
        using errcode = '22023';
    end if;
  elsif p_approval_id is not null or p_approval_binding_sha256 is not null
        or p_preview_payload_id is not null
        or p_preview_reference_binding_sha256 is not null
        or p_preview_sha256 is not null then
    raise exception 'read preparation cannot carry approval state'
      using errcode = '22023';
  end if;

  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = p_connection_id and connection.owner_id = p_owner_id
  for update;
  if not found
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256
        <> p_authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or connection_row.granted_actions is null
     or not (p_action = any(connection_row.granted_actions))
     or connection_row.authorization_expires_at is null
     or connection_row.authorization_expires_at <= now_at
     or p_expires_at > connection_row.authorization_expires_at then
    raise exception 'action preparation authority changed' using errcode = '55000';
  end if;

  grant_actions_sha256 := case p_action
    when 'mail.search' then 'f473d165be25833664f95fb9567791f21d69bd70c6e97fb4bfb9c50c3117db28'
    when 'mail.get' then 'cf3c5f14bfb4fdaf65b7be317e91db19e678d58f1ac1e114defa9af82f7f40ac'
    when 'mail.create_draft' then '417b5fc443bfab936bbcf99deb2f2caf63a8fdcaeef58ae94c450d7f0e8ab555'
    when 'mail.send' then '6561b088a5f972c0750c22a1dbd43a2bafeb551fb94f575fb5dddd3d13faf457'
    when 'mail.reply' then '33097149f536568ca98a9bfeaee4db8c48ff6d0277e50f70d2a37ac45da0a225'
    when 'calendar.list' then 'edfb7ef1d7de7d45a997ac779c16478798809f4c195d15dbaa9a783383c900a5'
    when 'calendar.get' then 'c2baacb1b196e947ab293e04fdf3baf96bca3fd8e3dbec20d43e1be891e004a5'
    when 'calendar.free_busy' then '64855b4524f62f74930ccbb8846bf1b24513616dad137fbe8ef404c885c8f08a'
    when 'calendar.create' then '31d87433562192490c9ae032675ed31bb09db1bbf2941b0eb12c017f7d77a52a'
    when 'calendar.update' then '15c6da0646f79e3b2409906fbbbad96c2c3d463cab2920211d9c44c26b32fda8'
    when 'calendar.cancel' then '9114e5237c49ef53d3bc53bb651bc65517220385e42e34cd7b47e14ac02411e3'
    else null
  end;
  if grant_actions_sha256 is null then
    raise exception 'action grant hash is not database-authored'
      using errcode = '55000';
  end if;

  select task_grant.* into grant_row
  from connected_app_private.task_grants as task_grant
  where task_grant.grant_id = p_grant_id
  for update;
  if found then
    raise exception 'task grant identity already belongs to a sibling action'
      using errcode = '55000';
  end if;
  if exists (
    select 1 from connected_app_private.approval_reviews as review
    where review.action_id = p_action_id
       or (p_approval_id is not null and review.approval_id = p_approval_id)
       or (p_approval_binding_sha256 is not null
           and review.approval_binding_sha256 = p_approval_binding_sha256)
  ) then
    raise exception 'approval identity already belongs to a sibling action'
      using errcode = '55000';
  end if;

  insert into connected_app_private.task_grants (
    grant_id, owner_id, task_id, turn_id, connection_id, provider, resource,
    authorization_revision, authorization_snapshot_sha256, actions,
    actions_sha256, task_state_revision, expires_at
  ) values (
    p_grant_id, p_owner_id, p_task_id, p_turn_id, p_connection_id,
    p_provider, p_resource, p_authorization_revision,
    p_authorization_snapshot_sha256, array[p_action], grant_actions_sha256,
    p_task_state_revision, p_expires_at
  );

  if authority_row.mutates_external_state then
    insert into connected_app_private.approval_reviews (
      approval_id, action_id, owner_id, task_id, turn_id, connection_id,
      provider, resource, action, authorization_revision,
      authorization_snapshot_sha256, granted_scopes_sha256, policy_version,
      action_revision, approval_class, approval_binding_sha256,
      parameters_sha256, resource_version_sha256, preview_sha256,
      review_payload_ref, expires_at, created_at, updated_at
    ) values (
      p_approval_id, p_action_id, p_owner_id, p_task_id, p_turn_id,
      p_connection_id, p_provider, p_resource, p_action,
      p_authorization_revision, p_authorization_snapshot_sha256,
      p_granted_scopes_sha256, p_policy_version, 1,
      authority_row.approval_class, p_approval_binding_sha256,
      p_parameters_sha256, p_resource_version_sha256, p_preview_sha256,
      p_preview_payload_id, p_expires_at, p_requested_at, now_at
    );
  end if;

  insert into connected_app_private.action_preparations (
    request_id, owner_id, session_binding_sha256, command_binding_sha256,
    grant_id, action_id, task_id, turn_id, connection_id,
    provider, resource, action, authorization_revision,
    authorization_snapshot_sha256, granted_actions_sha256,
    granted_scopes_sha256, grant_actions_sha256, task_state_revision,
    payload_id, payload_reference_binding_sha256, parameters_sha256,
    resource_version_sha256, policy_version, mutates_external_state,
    approval_class, status, approval_id, approval_binding_sha256,
    preview_payload_id, preview_reference_binding_sha256, preview_sha256,
    requested_at, expires_at
  ) values (
    p_request_id, p_owner_id, p_session_binding_sha256,
    p_command_binding_sha256, p_grant_id, p_action_id, p_task_id,
    p_turn_id, p_connection_id, p_provider, p_resource, p_action,
    p_authorization_revision, p_authorization_snapshot_sha256,
    p_granted_actions_sha256, p_granted_scopes_sha256,
    grant_actions_sha256, p_task_state_revision, p_payload_id,
    p_payload_reference_binding_sha256, p_parameters_sha256,
    p_resource_version_sha256, p_policy_version,
    authority_row.mutates_external_state, authority_row.approval_class,
    case when authority_row.mutates_external_state
      then 'pending_approval' else 'ready' end,
    p_approval_id, p_approval_binding_sha256, p_preview_payload_id,
    p_preview_reference_binding_sha256, p_preview_sha256,
    p_requested_at, p_expires_at
  );

  return connected_app_private.action_preparation_view_v1(
    p_owner_id, p_request_id
  );
end;
$fn$;
comment on function public.connected_app_operator_prepare_action_v1(
  uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,
  bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_OPERATOR_PREPARE_ACTION_V1_ATOMIC_NO_EXECUTION';

create or replace function public.connected_app_operator_read_action_preparation_v1(
  p_owner_id uuid, p_request_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select connected_app_private.action_preparation_view_v1(
    p_owner_id, p_request_id
  )
$fn$;
comment on function public.connected_app_operator_read_action_preparation_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_READ_ACTION_PREPARATION_V1_OWNER_REQUEST_ID';

create or replace function public.connected_app_operator_list_connections_v1(p_owner_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select coalesce(
    pg_catalog.jsonb_agg(
      connected_app_private.connection_view_v1(connection.owner_id, connection.id)
      order by connection.updated_at desc, connection.id
    ),
    '[]'::jsonb
  )
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id
    and connection.authorization_state in ('active', 'revoked')
$fn$;
comment on function public.connected_app_operator_list_connections_v1(uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_LIST_CONNECTIONS_V1_OWNER_SCOPED';

create or replace function public.connected_app_operator_get_connection_authority_v1(
  p_owner_id uuid, p_connection_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'connection_id', connection.id,
    'provider', connection.provider,
    'resource', connection.resource,
    'authorization_state', connection.authorization_state,
    'authorization_revision', connection.authorization_revision,
    'authorization_snapshot_sha256', connection.authorization_snapshot_sha256,
    'granted_scopes_sha256', connection.granted_scopes_sha256,
    'granted_actions', connection.granted_actions,
    'authorization_expires_at', connection.authorization_expires_at
  )
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id
    and connection.id = p_connection_id
    and connection.authorization_state = 'active'
    and connection.authorization_expires_at > pg_catalog.statement_timestamp()
$fn$;
comment on function public.connected_app_operator_get_connection_authority_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_GET_AUTHORITY_V1_OWNER_SCOPED';

create or replace function public.connected_app_operator_list_schedules_v1(p_owner_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select coalesce(
    pg_catalog.jsonb_agg(
      connected_app_private.schedule_view_v1(schedule.owner_id, schedule.schedule_id)
      order by schedule.updated_at desc, schedule.schedule_id
    ),
    '[]'::jsonb
  )
  from connected_app_private.schedules as schedule
  where schedule.owner_id = p_owner_id
$fn$;
comment on function public.connected_app_operator_list_schedules_v1(uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_LIST_SCHEDULES_V1_OWNER_SCOPED';

create or replace function public.connected_app_operator_get_schedule_v1(
  p_owner_id uuid, p_schedule_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select connected_app_private.schedule_view_v1(p_owner_id, p_schedule_id)
$fn$;
comment on function public.connected_app_operator_get_schedule_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_GET_SCHEDULE_V1_OWNER_SCOPED';

create or replace function public.connected_app_operator_list_actions_v1(p_owner_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  with identities as (
    select review.action_id, review.updated_at
    from connected_app_private.approval_reviews as review
    where review.owner_id = p_owner_id
    union
    select ledger.action_id, ledger.updated_at
    from connected_app_private.action_ledger as ledger
    where ledger.owner_id = p_owner_id
  ), newest as (
    select identity.action_id, max(identity.updated_at) as updated_at
    from identities as identity
    group by identity.action_id
    order by max(identity.updated_at) desc, identity.action_id
    limit 100
  )
  select coalesce(
    pg_catalog.jsonb_agg(
      connected_app_private.action_view_v1(p_owner_id, newest.action_id)
      order by newest.updated_at desc, newest.action_id
    ),
    '[]'::jsonb
  ) from newest
$fn$;
comment on function public.connected_app_operator_list_actions_v1(uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_LIST_ACTIONS_V1_OWNER_SCOPED_BOUNDED';

create or replace function public.connected_app_operator_get_action_v1(
  p_owner_id uuid, p_action_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select connected_app_private.action_view_v1(p_owner_id, p_action_id)
$fn$;
comment on function public.connected_app_operator_get_action_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_GET_ACTION_V1_OWNER_SCOPED';

create or replace function public.connected_app_operator_list_approvals_v1(p_owner_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select coalesce(
    pg_catalog.jsonb_agg(
      connected_app_private.approval_view_v1(review.owner_id, review.approval_id)
      order by review.updated_at desc, review.approval_id
    ),
    '[]'::jsonb
  )
  from (
    select approval_review.*
    from connected_app_private.approval_reviews as approval_review
    where approval_review.owner_id = p_owner_id
    order by approval_review.updated_at desc, approval_review.approval_id
    limit 50
  ) as review
$fn$;
comment on function public.connected_app_operator_list_approvals_v1(uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_LIST_APPROVALS_V1_OWNER_SCOPED_BOUNDED';

create or replace function public.connected_app_operator_get_approval_v1(
  p_owner_id uuid, p_approval_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select connected_app_private.approval_view_v1(p_owner_id, p_approval_id)
$fn$;
comment on function public.connected_app_operator_get_approval_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_GET_APPROVAL_V1_OWNER_SCOPED';

create or replace function public.connected_app_operator_disconnect_v1(
  p_request_id uuid, p_owner_id uuid, p_session_binding_sha256 text,
  p_connection_id uuid, p_cleanup_id uuid, p_command_binding_sha256 text,
  p_requested_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  command_row connected_app_private.operator_commands%rowtype;
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_request_id is null or p_owner_id is null or p_connection_id is null
     or p_cleanup_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_command_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_requested_at < now_at - interval '5 minutes'
     or p_requested_at > now_at + interval '1 minute' then
    raise exception 'invalid disconnect command' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select command.* into command_row
  from connected_app_private.operator_commands as command
  where command.request_id = p_request_id
  for update;
  if found then
    if command_row.owner_id <> p_owner_id
       or command_row.command_kind <> 'disconnect'
       or command_row.subject_id <> p_connection_id
       or command_row.session_binding_sha256 <> p_session_binding_sha256
       or command_row.command_binding_sha256 <> p_command_binding_sha256
       or command_row.requested_at <> p_requested_at then
      raise exception 'disconnect replay drifted' using errcode = '55000';
    end if;
    return connected_app_private.connection_view_v1(p_owner_id, p_connection_id);
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id and connection.id = p_connection_id
  for update;
  if not found or connection_row.authorization_state <> 'active' then
    raise exception 'disconnect authority is not active' using errcode = '55000';
  end if;
  perform public.connected_app_revoke_connection_v1(
    p_owner_id, p_connection_id, p_cleanup_id,
    connection_row.credential_ref_sha256,
    p_command_binding_sha256
  );
  update connected_app_private.task_grants as grant_row
  set revoked_at = now_at,
      task_state_revision = grant_row.task_state_revision + 1
  where grant_row.owner_id = p_owner_id
    and grant_row.connection_id = p_connection_id
    and grant_row.revoked_at is null;
  update connected_app_private.schedules as schedule
  set status = 'cancelled', next_run_at = null,
      claim_id = null, claim_expires_at = null,
      task_state_revision = schedule.task_state_revision + 1,
      updated_at = now_at
  where schedule.owner_id = p_owner_id
    and schedule.connection_id = p_connection_id
    and schedule.status <> 'cancelled';
  insert into connected_app_private.operator_commands (
    request_id, owner_id, command_kind, subject_id,
    session_binding_sha256, command_binding_sha256,
    requested_at, completed_at
  ) values (
    p_request_id, p_owner_id, 'disconnect', p_connection_id,
    p_session_binding_sha256, p_command_binding_sha256,
    p_requested_at, now_at
  );
  return connected_app_private.connection_view_v1(p_owner_id, p_connection_id);
end;
$fn$;
comment on function public.connected_app_operator_disconnect_v1(
  uuid,uuid,text,uuid,uuid,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_OPERATOR_DISCONNECT_V1_ATOMIC_INVALIDATION';

create or replace function public.connected_app_operator_read_disconnect_v1(
  p_owner_id uuid, p_connection_id uuid, p_request_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select connected_app_private.connection_view_v1(p_owner_id, p_connection_id)
  from connected_app_private.operator_commands as command
  where command.request_id = p_request_id
    and command.owner_id = p_owner_id
    and command.command_kind = 'disconnect'
    and command.subject_id = p_connection_id
$fn$;
comment on function public.connected_app_operator_read_disconnect_v1(uuid,uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_READ_DISCONNECT_V1_EXACT_REQUEST';

create or replace function public.connected_app_operator_create_schedule_v1(
  p_request_id uuid, p_schedule_id uuid, p_owner_id uuid,
  p_session_binding_sha256 text, p_command_binding_sha256 text,
  p_connection_id uuid, p_task_id uuid, p_provider text, p_resource text,
  p_action text, p_action_template_ref uuid, p_parameters_sha256 text,
  p_time_zone text, p_cadence_seconds integer,
  p_quiet_start_minute integer, p_quiet_end_minute integer,
  p_requires_approval_every_run boolean, p_requested_at timestamptz,
  p_next_run_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  command_row connected_app_private.operator_commands%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_request_id is null or p_schedule_id is null or p_owner_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_command_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_requested_at < now_at - interval '5 minutes'
     or p_requested_at > now_at + interval '1 minute'
     or p_next_run_at <= p_requested_at
     or p_next_run_at > p_requested_at
        + pg_catalog.make_interval(secs => p_cadence_seconds)
        + interval '24 hours' then
    raise exception 'invalid schedule-create command' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select command.* into command_row
  from connected_app_private.operator_commands as command
  where command.request_id = p_request_id
  for update;
  if found then
    if command_row.owner_id <> p_owner_id
       or command_row.command_kind <> 'schedule_create'
       or command_row.subject_id <> p_schedule_id
       or command_row.session_binding_sha256 <> p_session_binding_sha256
       or command_row.command_binding_sha256 <> p_command_binding_sha256
       or command_row.requested_at <> p_requested_at then
      raise exception 'schedule-create replay drifted' using errcode = '55000';
    end if;
    return connected_app_private.schedule_view_v1(p_owner_id, p_schedule_id);
  end if;
  perform public.connected_app_put_schedule_v1(
    p_schedule_id, p_owner_id, p_connection_id, p_task_id,
    p_provider, p_resource, p_action, p_action_template_ref,
    p_parameters_sha256, 1, p_time_zone, p_cadence_seconds,
    p_quiet_start_minute, p_quiet_end_minute,
    p_requires_approval_every_run, 'active', p_next_run_at
  );
  insert into connected_app_private.operator_commands (
    request_id, owner_id, command_kind, subject_id,
    session_binding_sha256, command_binding_sha256,
    requested_at, completed_at
  ) values (
    p_request_id, p_owner_id, 'schedule_create', p_schedule_id,
    p_session_binding_sha256, p_command_binding_sha256,
    p_requested_at, now_at
  );
  return connected_app_private.schedule_view_v1(p_owner_id, p_schedule_id);
end;
$fn$;
comment on function public.connected_app_operator_create_schedule_v1(
  uuid,uuid,uuid,text,text,uuid,uuid,text,text,text,uuid,text,text,integer,integer,integer,boolean,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_OPERATOR_CREATE_SCHEDULE_V1_EXACT_REQUEST';

create or replace function public.connected_app_operator_read_schedule_create_v1(
  p_owner_id uuid, p_request_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select connected_app_private.schedule_view_v1(p_owner_id, command.subject_id)
  from connected_app_private.operator_commands as command
  where command.request_id = p_request_id
    and command.owner_id = p_owner_id
    and command.command_kind = 'schedule_create'
$fn$;
comment on function public.connected_app_operator_read_schedule_create_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_READ_SCHEDULE_CREATE_V1_EXACT_REQUEST';

create or replace function public.connected_app_operator_transition_schedule_v1(
  p_request_id uuid, p_owner_id uuid,
  p_session_binding_sha256 text, p_command_binding_sha256 text,
  p_schedule_id uuid, p_expected_task_state_revision bigint,
  p_expected_status text, p_target_status text, p_requested_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  command_row connected_app_private.operator_commands%rowtype;
  schedule_row connected_app_private.schedules%rowtype;
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_request_id is null or p_owner_id is null or p_schedule_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_command_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_expected_task_state_revision < 1
     or (p_expected_status, p_target_status) not in (
       ('active', 'paused'), ('paused', 'active'),
       ('active', 'cancelled'), ('paused', 'cancelled')
     )
     or p_requested_at < now_at - interval '5 minutes'
     or p_requested_at > now_at + interval '1 minute' then
    raise exception 'invalid schedule-transition command' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select command.* into command_row
  from connected_app_private.operator_commands as command
  where command.request_id = p_request_id
  for update;
  if found then
    if command_row.owner_id <> p_owner_id
       or command_row.command_kind <> 'schedule_transition'
       or command_row.subject_id <> p_schedule_id
       or command_row.session_binding_sha256 <> p_session_binding_sha256
       or command_row.command_binding_sha256 <> p_command_binding_sha256
       or command_row.requested_at <> p_requested_at then
      raise exception 'schedule-transition replay drifted' using errcode = '55000';
    end if;
    return connected_app_private.schedule_view_v1(p_owner_id, p_schedule_id);
  end if;
  select schedule.* into schedule_row
  from connected_app_private.schedules as schedule
  where schedule.owner_id = p_owner_id and schedule.schedule_id = p_schedule_id
  for update;
  if not found or schedule_row.status <> p_expected_status
     or schedule_row.task_state_revision <> p_expected_task_state_revision
     or schedule_row.claim_id is not null then
    raise exception 'schedule transition authority changed' using errcode = '55000';
  end if;
  if p_target_status = 'active' then
    select connection.* into connection_row
    from connected_app_private.connections as connection
    where connection.owner_id = p_owner_id
      and connection.id = schedule_row.connection_id
    for update;
    if not found or connection_row.authorization_state <> 'active'
       or connection_row.authorization_revision < 1
       or not (schedule_row.action = any(connection_row.granted_actions))
       or (connection_row.authorization_expires_at is not null
           and connection_row.authorization_expires_at <= now_at) then
      raise exception 'schedule resume authority changed' using errcode = '55000';
    end if;
  end if;
  update connected_app_private.schedules as schedule
  set task_state_revision = schedule.task_state_revision + 1,
      status = p_target_status,
      next_run_at = case when p_target_status = 'active'
        then p_requested_at + pg_catalog.make_interval(secs => schedule.cadence_seconds)
        else null end,
      claim_id = null, claim_expires_at = null,
      updated_at = now_at
  where schedule.schedule_id = p_schedule_id
  returning * into schedule_row;
  insert into connected_app_private.operator_commands (
    request_id, owner_id, command_kind, subject_id,
    session_binding_sha256, command_binding_sha256,
    requested_at, completed_at
  ) values (
    p_request_id, p_owner_id, 'schedule_transition', p_schedule_id,
    p_session_binding_sha256, p_command_binding_sha256,
    p_requested_at, now_at
  );
  return connected_app_private.schedule_view_v1(p_owner_id, p_schedule_id);
end;
$fn$;
comment on function public.connected_app_operator_transition_schedule_v1(
  uuid,uuid,text,text,uuid,bigint,text,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_OPERATOR_TRANSITION_SCHEDULE_V1_MONOTONIC';

create or replace function public.connected_app_operator_read_schedule_transition_v1(
  p_owner_id uuid, p_schedule_id uuid, p_request_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select connected_app_private.schedule_view_v1(p_owner_id, p_schedule_id)
  from connected_app_private.operator_commands as command
  where command.request_id = p_request_id
    and command.owner_id = p_owner_id
    and command.command_kind = 'schedule_transition'
    and command.subject_id = p_schedule_id
$fn$;
comment on function public.connected_app_operator_read_schedule_transition_v1(uuid,uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_READ_SCHEDULE_TRANSITION_V1_EXACT_REQUEST';

create or replace function public.connected_app_operator_put_approval_review_v1(
  p_approval_id uuid, p_action_id uuid, p_owner_id uuid,
  p_task_id uuid, p_turn_id uuid, p_connection_id uuid,
  p_provider text, p_resource text, p_action text,
  p_authorization_revision bigint, p_authorization_snapshot_sha256 text,
  p_granted_scopes_sha256 text, p_policy_version text,
  p_action_revision bigint, p_approval_class text,
  p_approval_binding_sha256 text, p_parameters_sha256 text,
  p_resource_version_sha256 text, p_preview_sha256 text,
  p_review_payload_ref uuid, p_created_at timestamptz, p_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  review_row connected_app_private.approval_reviews%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_approval_id is null or p_action_id is null or p_owner_id is null
     or p_task_id is null or p_turn_id is null or p_connection_id is null
     or p_review_payload_ref is null
     or p_authorization_revision < 1 or p_action_revision < 1
     or p_authorization_snapshot_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_scopes_sha256 !~ '^[0-9a-f]{64}$'
     or p_approval_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_parameters_sha256 !~ '^[0-9a-f]{64}$'
     or p_preview_sha256 !~ '^[0-9a-f]{64}$'
     or p_created_at < now_at - interval '5 minutes'
     or p_created_at > now_at + interval '1 minute'
     or p_expires_at <= now_at
     or p_expires_at > p_created_at + interval '15 minutes' then
    raise exception 'invalid approval-review bounds' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action = p_action;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id and connection.id = p_connection_id
  for update;
  if authority_row.action is null or connection_row.id is null
     or not authority_row.mutates_external_state
     or authority_row.resource <> p_resource
     or authority_row.approval_class <> p_approval_class
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or not (p_action = any(connection_row.granted_actions))
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at) then
    raise exception 'approval-review authority changed' using errcode = '55000';
  end if;
  select review.* into review_row
  from connected_app_private.approval_reviews as review
  where review.approval_id = p_approval_id
     or review.action_id = p_action_id
     or review.approval_binding_sha256 = p_approval_binding_sha256
  for update;
  if found then
    if review_row.approval_id <> p_approval_id
       or review_row.action_id <> p_action_id
       or review_row.owner_id <> p_owner_id
       or review_row.task_id <> p_task_id
       or review_row.turn_id <> p_turn_id
       or review_row.connection_id <> p_connection_id
       or review_row.provider <> p_provider
       or review_row.resource <> p_resource
       or review_row.action <> p_action
       or review_row.authorization_revision <> p_authorization_revision
       or review_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
       or review_row.granted_scopes_sha256 <> p_granted_scopes_sha256
       or review_row.policy_version <> p_policy_version
       or review_row.action_revision <> p_action_revision
       or review_row.approval_class <> p_approval_class
       or review_row.parameters_sha256 <> p_parameters_sha256
       or review_row.resource_version_sha256 is distinct from p_resource_version_sha256
       or review_row.preview_sha256 <> p_preview_sha256
       or review_row.review_payload_ref <> p_review_payload_ref
       or review_row.created_at <> p_created_at
       or review_row.expires_at <> p_expires_at then
      raise exception 'approval-review replay drifted' using errcode = '55000';
    end if;
    return connected_app_private.approval_view_v1(p_owner_id, p_approval_id);
  end if;
  insert into connected_app_private.approval_reviews (
    approval_id, action_id, owner_id, task_id, turn_id, connection_id,
    provider, resource, action, authorization_revision,
    authorization_snapshot_sha256, granted_scopes_sha256,
    policy_version, action_revision, approval_class,
    approval_binding_sha256, parameters_sha256, resource_version_sha256,
    preview_sha256, review_payload_ref, created_at, expires_at
  ) values (
    p_approval_id, p_action_id, p_owner_id, p_task_id, p_turn_id,
    p_connection_id, p_provider, p_resource, p_action,
    p_authorization_revision, p_authorization_snapshot_sha256,
    p_granted_scopes_sha256, p_policy_version, p_action_revision,
    p_approval_class, p_approval_binding_sha256, p_parameters_sha256,
    p_resource_version_sha256, p_preview_sha256, p_review_payload_ref,
    p_created_at, p_expires_at
  );
  return connected_app_private.approval_view_v1(p_owner_id, p_approval_id);
end;
$fn$;
comment on function public.connected_app_operator_put_approval_review_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,text,text,text,text,text,uuid,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_OPERATOR_PUT_APPROVAL_REVIEW_V1_EXACT_ENCRYPTED_REFERENCE';

create or replace function public.connected_app_operator_decide_approval_v1(
  p_decision_id uuid, p_owner_id uuid, p_session_binding_sha256 text,
  p_approval_id uuid, p_action_id uuid, p_connection_id uuid,
  p_task_id uuid, p_turn_id uuid, p_provider text, p_resource text,
  p_action text, p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text, p_granted_scopes_sha256 text,
  p_policy_version text, p_action_revision bigint,
  p_approval_binding_sha256 text, p_parameters_sha256 text,
  p_resource_version_sha256 text, p_preview_sha256 text,
  p_decision text, p_decided_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  review_row connected_app_private.approval_reviews%rowtype;
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_decision_id is null or p_owner_id is null or p_approval_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_decision not in ('approved', 'denied')
     or p_decided_at < now_at - interval '5 minutes'
     or p_decided_at > now_at + interval '1 minute' then
    raise exception 'invalid approval decision' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select review.* into review_row
  from connected_app_private.approval_reviews as review
  where review.owner_id = p_owner_id and review.approval_id = p_approval_id
  for update;
  if not found then
    return null;
  end if;
  if review_row.status <> 'pending' then
    if review_row.decision_id = p_decision_id
       and review_row.decision_session_binding_sha256 = p_session_binding_sha256
       and review_row.status = p_decision then
      return connected_app_private.approval_view_v1(p_owner_id, p_approval_id);
    end if;
    raise exception 'approval was already decided' using errcode = '55000';
  end if;
  if review_row.action_id <> p_action_id
     or review_row.connection_id <> p_connection_id
     or review_row.task_id <> p_task_id
     or review_row.turn_id <> p_turn_id
     or review_row.provider <> p_provider
     or review_row.resource <> p_resource
     or review_row.action <> p_action
     or review_row.authorization_revision <> p_authorization_revision
     or review_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or review_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or review_row.policy_version <> p_policy_version
     or review_row.action_revision <> p_action_revision
     or review_row.approval_binding_sha256 <> p_approval_binding_sha256
     or review_row.parameters_sha256 <> p_parameters_sha256
     or review_row.resource_version_sha256 is distinct from p_resource_version_sha256
     or review_row.preview_sha256 <> p_preview_sha256
     or review_row.expires_at <= now_at
     or p_decided_at > review_row.expires_at then
    raise exception 'approval decision binding changed' using errcode = '55000';
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id and connection.id = p_connection_id
  for update;
  if not found or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or not (p_action = any(connection_row.granted_actions))
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at <= now_at) then
    raise exception 'approval connection authority changed' using errcode = '55000';
  end if;
  if p_decision = 'approved' then
    perform public.connected_app_create_approval_v1(
      review_row.approval_id, review_row.action_id, review_row.owner_id,
      review_row.task_id, review_row.turn_id, review_row.connection_id,
      review_row.provider, review_row.resource, review_row.action,
      review_row.authorization_revision,
      review_row.authorization_snapshot_sha256,
      review_row.approval_class, review_row.parameters_sha256,
      review_row.resource_version_sha256,
      review_row.approval_binding_sha256, p_decided_at,
      review_row.expires_at
    );
  end if;
  update connected_app_private.approval_reviews as review
  set status = p_decision, decision_id = p_decision_id,
      decision_session_binding_sha256 = p_session_binding_sha256,
      decided_at = p_decided_at, updated_at = now_at
  where review.approval_id = p_approval_id;
  return connected_app_private.approval_view_v1(p_owner_id, p_approval_id);
end;
$fn$;
comment on function public.connected_app_operator_decide_approval_v1(
  uuid,uuid,text,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,text,text,text,text,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_APP_OPERATOR_DECIDE_APPROVAL_V1_ATOMIC_EXACT_BINDING';

create or replace function public.connected_app_operator_read_approval_decision_v1(
  p_owner_id uuid, p_approval_id uuid, p_decision_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select connected_app_private.approval_view_v1(p_owner_id, p_approval_id)
  from connected_app_private.approval_reviews as review
  where review.owner_id = p_owner_id
    and review.approval_id = p_approval_id
    and review.decision_id = p_decision_id
$fn$;
comment on function public.connected_app_operator_read_approval_decision_v1(uuid,uuid,uuid) is
  'ASK_CRUMP_CONNECTED_APP_OPERATOR_READ_APPROVAL_DECISION_V1_EXACT_DECISION';

alter function connected_app_private.owner_lock_v1(uuid) owner to postgres;
alter function connected_app_private.enqueue_owner_cleanup_before_delete_v1()
  owner to postgres;
alter sequence connected_app_private.action_fencing_token_seq owner to postgres;
revoke all on sequence connected_app_private.action_fencing_token_seq
  from public, anon, authenticated, service_role;

-- Global/default grants can name roles unknown to this migration.  Remove
-- privileges from every non-owner role rather than relying on a fixed API-role
-- list; later postflight inspects raw ACL grantees with aclexplode.
do $private_acl$
declare
  object_row record;
  role_name text;
  signature text;
begin
  execute 'revoke all on schema connected_app_private from public';
  for role_name in
    select role_row.rolname
    from pg_catalog.pg_roles as role_row
    where role_row.rolname <> 'postgres'
    order by role_row.rolname
  loop
    execute pg_catalog.format(
      'revoke all on schema connected_app_private from %I', role_name
    );
    execute pg_catalog.format(
      'alter default privileges for role postgres in schema connected_app_private revoke all on tables from %I',
      role_name
    );
    execute pg_catalog.format(
      'alter default privileges for role postgres in schema connected_app_private revoke all on sequences from %I',
      role_name
    );
    execute pg_catalog.format(
      'alter default privileges for role postgres in schema connected_app_private revoke all on functions from %I',
      role_name
    );
  end loop;
  alter default privileges for role postgres in schema connected_app_private
    revoke all on tables from public;
  alter default privileges for role postgres in schema connected_app_private
    revoke all on sequences from public;
  alter default privileges for role postgres in schema connected_app_private
    revoke all on functions from public;

  for object_row in
    select class_row.relname, class_row.relkind
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relkind in ('r', 'S')
  loop
    execute pg_catalog.format(
      'revoke all on %s connected_app_private.%I from public',
      case when object_row.relkind = 'S' then 'sequence' else 'table' end,
      object_row.relname
    );
    for role_name in
      select role_row.rolname
      from pg_catalog.pg_roles as role_row
      where role_row.rolname <> 'postgres'
    loop
      execute pg_catalog.format(
        'revoke all on %s connected_app_private.%I from %I',
        case when object_row.relkind = 'S' then 'sequence' else 'table' end,
        object_row.relname, role_name
      );
    end loop;
  end loop;

  for object_row in
    select proc_row.oid, proc_row.proname,
           pg_catalog.pg_get_function_identity_arguments(proc_row.oid) as identity_arguments
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'connected_app_private'
  loop
    signature := pg_catalog.format(
      'connected_app_private.%I(%s)', object_row.proname,
      object_row.identity_arguments
    );
    execute 'revoke all on function ' || signature || ' from public';
    for role_name in
      select role_row.rolname
      from pg_catalog.pg_roles as role_row
      where role_row.rolname <> 'postgres'
    loop
      execute 'revoke all on function ' || signature || ' from '
        || pg_catalog.quote_ident(role_name);
    end loop;
  end loop;
end;
$private_acl$;

do $rpc_acl$
declare
  function_row record;
  role_name text;
  signature text;
begin
  for function_row in
    select proc_row.oid, namespace_row.nspname, proc_row.proname,
           pg_catalog.pg_get_function_identity_arguments(proc_row.oid) as identity_arguments
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname like 'connected_app\_%' escape '\'
    order by proc_row.proname, proc_row.oid
  loop
    signature := pg_catalog.format(
      '%I.%I(%s)', function_row.nspname, function_row.proname,
      function_row.identity_arguments
    );
    execute 'alter function ' || signature || ' owner to postgres';
    execute 'revoke all on function ' || signature || ' from public';
    for role_name in
      select role_row.rolname
      from pg_catalog.pg_roles as role_row
      where role_row.rolname <> 'postgres'
    loop
      execute 'revoke all on function ' || signature || ' from '
        || pg_catalog.quote_ident(role_name);
    end loop;
    execute 'grant execute on function ' || signature || ' to service_role';
  end loop;
end;
$rpc_acl$;

do $postflight$
declare
  expected_tables constant text[] := array[
    'action_authority', 'action_ledger', 'action_preparations',
    'approval_reviews', 'approvals', 'connections',
    'credential_cleanup_outbox', 'credential_ref_tombstones',
    'oauth_exchange_permits', 'oauth_flows',
    'operator_commands', 'schedules', 'task_grants'
  ];
  expected_functions constant text[] := array[
    'connected_app_begin_access_v1',
    'connected_app_begin_effect_v1',
    'connected_app_begin_postobserve_v1',
    'connected_app_claim_action_v1',
    'connected_app_claim_cleanup_v1',
    'connected_app_claim_schedule_v1',
    'connected_app_consume_approval_v1',
    'connected_app_consume_credential_lease_v1',
    'connected_app_create_approval_v1',
    'connected_app_create_connection_v1',
    'connected_app_create_task_grant_v1',
    'connected_app_finish_cleanup_v1',
    'connected_app_finish_schedule_v1',
    'connected_app_get_binding_v1',
    'connected_app_oauth_consume_pending_v1',
    'connected_app_oauth_consume_permit_v1',
    'connected_app_oauth_create_pending_v1',
    'connected_app_oauth_finalize_v1',
    'connected_app_oauth_issue_permit_v1',
    'connected_app_operator_create_schedule_v1',
    'connected_app_operator_decide_approval_v1',
    'connected_app_operator_disconnect_v1',
    'connected_app_operator_get_action_v1',
    'connected_app_operator_get_approval_v1',
    'connected_app_operator_get_connection_authority_v1',
    'connected_app_operator_get_schedule_v1',
    'connected_app_operator_list_actions_v1',
    'connected_app_operator_list_approvals_v1',
    'connected_app_operator_list_connections_v1',
    'connected_app_operator_list_schedules_v1',
    'connected_app_operator_prepare_action_v1',
    'connected_app_operator_put_approval_review_v1',
    'connected_app_operator_read_action_preparation_v1',
    'connected_app_operator_read_approval_decision_v1',
    'connected_app_operator_read_disconnect_v1',
    'connected_app_operator_read_schedule_create_v1',
    'connected_app_operator_read_schedule_transition_v1',
    'connected_app_operator_transition_schedule_v1',
    'connected_app_purge_cleanup_v1',
    'connected_app_put_schedule_v1',
    'connected_app_read_action_v1',
    'connected_app_record_credential_cleanup_v1',
    'connected_app_recover_access_v1',
    'connected_app_recover_cleanup_v1',
    'connected_app_revoke_connection_v1',
    'connected_app_revoke_task_grant_v1',
    'connected_app_settle_action_v1'
  ];
  found_tables text[];
  found_functions text[];
  table_row record;
  function_row record;
  trigger_oid oid;
  owner_delete_function_oid oid;
begin
  select pg_catalog.array_agg(class_row.relname order by class_row.relname)
    into found_tables
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_app_private'
    and class_row.relkind = 'r';
  if found_tables is distinct from expected_tables then
    raise exception 'connected-app table manifest drifted at postflight'
      using errcode = '55000';
  end if;

  if (
    select pg_catalog.array_agg(
      authority.action || '|' || authority.resource || '|'
      || authority.mutates_external_state::text || '|' || authority.approval_class
      order by authority.action
    )
    from connected_app_private.action_authority as authority
  ) is distinct from array[
    'calendar.cancel|calendar|true|calendar_write',
    'calendar.create|calendar|true|calendar_write',
    'calendar.free_busy|calendar|false|none',
    'calendar.get|calendar|false|none',
    'calendar.list|calendar|false|none',
    'calendar.update|calendar|true|calendar_write',
    'mail.create_draft|mail|true|external_write_reversible',
    'mail.get|mail|false|none',
    'mail.reply|mail|true|external_communication',
    'mail.search|mail|false|none',
    'mail.send|mail|true|external_communication'
  ]::text[] then
    raise exception 'connected-app action authority allowlist drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.array_agg(proc_row.proname order by proc_row.proname)
    into found_functions
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname like 'connected_app\_%' escape '\';
  if found_functions is distinct from expected_functions then
    raise exception 'connected-app public RPC manifest drifted at postflight'
      using errcode = '55000';
  end if;

  if pg_catalog.pg_get_userbyid(
       (select namespace_row.nspowner from pg_catalog.pg_namespace as namespace_row
        where namespace_row.nspname = 'connected_app_private')
     ) <> 'postgres'
     or exists (
       select 1
       from pg_catalog.pg_namespace as namespace_row
       cross join lateral pg_catalog.aclexplode(
         coalesce(
           namespace_row.nspacl,
           pg_catalog.acldefault('n', namespace_row.nspowner)
         )
       ) as acl_row
       where namespace_row.nspname = 'connected_app_private'
         and acl_row.grantee <> namespace_row.nspowner
     ) then
    raise exception 'connected-app private schema authority drifted'
      using errcode = '55000';
  end if;

  for table_row in
    select class_row.oid, class_row.relname, class_row.relrowsecurity,
           class_row.relforcerowsecurity, class_row.relowner
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relkind = 'r'
  loop
    if table_row.relrowsecurity is not true
       or table_row.relforcerowsecurity is not true
       or pg_catalog.pg_get_userbyid(table_row.relowner) <> 'postgres'
       or exists (
         select 1
         from pg_catalog.aclexplode(
           coalesce(
             (select class_row.relacl from pg_catalog.pg_class as class_row
              where class_row.oid = table_row.oid),
             pg_catalog.acldefault('r', table_row.relowner)
           )
         ) as acl_row
         where acl_row.grantee <> table_row.relowner
       ) then
      raise exception 'connected-app private table authority drifted: %', table_row.relname
        using errcode = '55000';
    end if;
  end loop;

  if exists (
    select 1 from pg_catalog.pg_policy as policy_row
    join pg_catalog.pg_class as class_row on class_row.oid = policy_row.polrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
  ) or exists (
    select 1 from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid = trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and not trigger_row.tgisinternal
  ) or exists (
    select 1 from pg_catalog.pg_rewrite as rule_row
    join pg_catalog.pg_class as class_row on class_row.oid = rule_row.ev_class
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and rule_row.rulename <> '_RETURN'
  ) then
    raise exception 'connected-app hidden policy/trigger/rule drifted'
      using errcode = '55000';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row on class_row.oid = attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relkind = 'r'
      and attribute_row.attnum > 0
      and not attribute_row.attisdropped
      and pg_catalog.lower(attribute_row.attname) in (
        'access_token', 'refresh_token', 'authorization_code', 'pkce_verifier',
        'oauth_state', 'email', 'email_address', 'subject', 'body',
        'recipient', 'event_text', 'message', 'prompt', 'content'
      )
  ) then
    raise exception 'connected-app forbidden secret/content column exists'
      using errcode = '55000';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row on class_row.oid = attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relkind = 'r'
      and attribute_row.attnum > 0
      and not attribute_row.attisdropped
      and attribute_row.attacl is not null
  ) then
    raise exception 'connected-app private column ACL drifted'
      using errcode = '55000';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_attribute as attribute_row
    where attribute_row.attrelid = 'connected_app_private.credential_cleanup_outbox'::regclass
      and attribute_row.attnum > 0 and not attribute_row.attisdropped
      and attribute_row.attname in (
        'owner_id', 'user_id', 'connection_id', 'task_id', 'turn_id', 'action_id'
      )
  ) then
    raise exception 'credential cleanup queue is identity-linked'
      using errcode = '55000';
  end if;

  for function_row in
    select proc_row.oid, proc_row.proname, proc_row.proowner,
           proc_row.prosecdef, proc_row.proconfig
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname like 'connected_app\_%' escape '\'
  loop
    if pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
       or function_row.prosecdef is not true
       or function_row.proconfig is distinct from array['search_path=""']::text[]
       or not exists (
         select 1
         from pg_catalog.aclexplode(
           coalesce(
             (select proc_row.proacl from pg_catalog.pg_proc as proc_row
              where proc_row.oid = function_row.oid),
             pg_catalog.acldefault('f', function_row.proowner)
           )
         ) as acl_row
         where acl_row.grantee = (
           select role_row.oid from pg_catalog.pg_roles as role_row
           where role_row.rolname = 'service_role'
         )
           and acl_row.privilege_type = 'EXECUTE'
           and not acl_row.is_grantable
       )
       or exists (
         select 1
         from pg_catalog.aclexplode(
           coalesce(
             (select proc_row.proacl from pg_catalog.pg_proc as proc_row
              where proc_row.oid = function_row.oid),
             pg_catalog.acldefault('f', function_row.proowner)
           )
         ) as acl_row
         where acl_row.grantee <> function_row.proowner
           and acl_row.grantee <> (
             select role_row.oid from pg_catalog.pg_roles as role_row
             where role_row.rolname = 'service_role'
           )
       ) then
      raise exception 'connected-app RPC authority drifted: %', function_row.proname
        using errcode = '55000';
    end if;
  end loop;

  if pg_catalog.pg_get_userbyid(
       (select class_row.relowner
        from pg_catalog.pg_class as class_row
        where class_row.oid = 'connected_app_private.action_fencing_token_seq'::regclass)
     ) <> 'postgres'
     or exists (
       select 1
       from pg_catalog.pg_class as class_row
       cross join lateral pg_catalog.aclexplode(
         coalesce(class_row.relacl, pg_catalog.acldefault('S', class_row.relowner))
       ) as acl_row
       where class_row.oid = 'connected_app_private.action_fencing_token_seq'::regclass
         and acl_row.grantee <> class_row.relowner
     ) then
    raise exception 'connected-app fencing sequence authority drifted'
      using errcode = '55000';
  end if;

  for function_row in
    select proc_row.oid, proc_row.proname, proc_row.proowner,
           proc_row.prosecdef, proc_row.proconfig
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'connected_app_private'
      and proc_row.proname in (
        'owner_lock_v1', 'enqueue_owner_cleanup_before_delete_v1',
        'connection_view_v1', 'schedule_view_v1',
        'action_view_v1', 'approval_view_v1', 'action_preparation_view_v1'
      )
  loop
    if pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
       or function_row.prosecdef is not true
       or function_row.proconfig is distinct from array['search_path=""']::text[]
       or exists (
         select 1
         from pg_catalog.aclexplode(
           coalesce(
             (select proc_row.proacl from pg_catalog.pg_proc as proc_row
              where proc_row.oid = function_row.oid),
             pg_catalog.acldefault('f', function_row.proowner)
           )
         ) as acl_row
         where acl_row.grantee <> function_row.proowner
       ) then
      raise exception 'connected-app private function authority drifted: %', function_row.proname
        using errcode = '55000';
    end if;
  end loop;

  if (
    select pg_catalog.count(*)
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'connected_app_private'
  ) <> 7 then
    raise exception 'connected-app private function manifest drifted'
      using errcode = '55000';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_default_acl as default_acl
    cross join lateral pg_catalog.aclexplode(default_acl.defaclacl) as acl_row
    where default_acl.defaclnamespace = pg_catalog.to_regnamespace('connected_app_private')
      and acl_row.grantee <> default_acl.defaclrole
  ) then
    raise exception 'connected-app private default privileges drifted'
      using errcode = '55000';
  end if;

  if exists (select 1 from pg_catalog.pg_publication where puballtables)
     or exists (
       select 1
       from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row on class_row.oid = publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
       where namespace_row.nspname = 'connected_app_private'
     ) then
    raise exception 'connected-app private state is publication-exposed'
      using errcode = '55000';
  end if;

  owner_delete_function_oid := pg_catalog.to_regprocedure(
    'connected_app_private.enqueue_owner_cleanup_before_delete_v1()'
  );
  select trigger_row.oid into trigger_oid
  from pg_catalog.pg_trigger as trigger_row
  where trigger_row.tgrelid = 'public.users'::regclass
    and trigger_row.tgname = 'connected_app_owner_delete_cleanup_v1'
    and not trigger_row.tgisinternal
    and trigger_row.tgenabled = 'O'
    and trigger_row.tgtype = 11
    and trigger_row.tgfoid = owner_delete_function_oid;
  if trigger_oid is null or (
    select pg_catalog.count(*)
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid = 'public.users'::regclass
      and trigger_row.tgname like 'connected_app\_%' escape '\'
      and not trigger_row.tgisinternal
  ) <> 1 then
    raise exception 'connected-app account-delete cleanup trigger drifted'
      using errcode = '55000';
  end if;
end;
$postflight$;

commit;

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
