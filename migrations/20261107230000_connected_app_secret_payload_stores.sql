begin;

select pg_catalog.set_config('search_path', 'pg_catalog,public', true);
select pg_catalog.set_config('quote_all_identifiers', 'off', true);

-- Refuse a missing, partial, or unreviewed predecessor.  This migration never
-- creates or repairs the connected-app control plane that owns these stores.
-- Exact reviewed predecessor source SHA256:
-- E7CA1FB4AD5CD5BE19109CEAE76A1B19535BD3B05D2D7750E49BE8B86EE48678
-- Exact dependency-scoped catalog fingerprint (manifest/body/authority v1):
-- 8052016e79f8049ccdab9785409c7820
do $preflight$
declare
  target_relations integer;
  target_functions integer;
  target_triggers integer;
  predecessor_fingerprint text;
  observed_target_fingerprint text;
begin
  select pg_catalog.count(*) into target_relations
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_app_private'
    and class_row.relname in (
      'credential_envelopes', 'credential_refresh_leases',
      'credential_refresh_quarantines',
      'credential_secret_tombstones', 'payload_envelopes',
      'payload_tombstones'
    );
  select pg_catalog.count(*) into target_functions
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname in ('public', 'connected_app_private')
    and proc_row.proname in (
      'connected_app_payload_put_v1', 'connected_app_payload_read_v1',
      'connected_app_payload_delete_v1', 'connected_app_payload_reference_get_v1',
      'connected_app_credential_create_v1', 'connected_app_credential_read_v1',
      'connected_app_credential_replace_v1', 'connected_app_credential_delete_v1',
      'connected_app_credential_claim_refresh_v1',
      'connected_app_credential_quarantine_refresh_v1',
      'connected_app_credential_finish_refresh_v1',
      'payload_tombstone_before_delete_v1',
      'credential_tombstone_before_delete_v1',
      'credential_retire_after_connection_update_v1'
    );
  select pg_catalog.count(*) into target_triggers
  from pg_catalog.pg_trigger as trigger_row
  join pg_catalog.pg_class as class_row on class_row.oid = trigger_row.tgrelid
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where not trigger_row.tgisinternal
    and namespace_row.nspname = 'connected_app_private'
    and (
      class_row.relname in (
        'credential_envelopes', 'credential_refresh_leases',
        'credential_refresh_quarantines', 'credential_secret_tombstones',
        'payload_envelopes', 'payload_tombstones'
      )
      or (
        class_row.relname = 'connections'
        and trigger_row.tgname =
          'connected_credential_retire_after_connection_update_v1'
      )
    );

  -- Every statement below is syntactically idempotent only after this exact
  -- target attestation succeeds.  A partial, mixed, overloaded, exposed, or
  -- drifted target is rejected before any IF NOT EXISTS / CREATE OR REPLACE
  -- statement can repair it.  The manifest also pins the predecessor objects
  -- directly consumed by this layer while remaining stable under later layers.
  if target_relations <> 0 or target_functions <> 0 or target_triggers <> 0 then
    select pg_catalog.md5(
      pg_catalog.string_agg(item.value::text, E'\n' order by item.value::text)
    ) into observed_target_fingerprint
    from (
      select pg_catalog.jsonb_build_array(
        'schema', namespace_row.nspname,
        pg_catalog.pg_get_userbyid(namespace_row.nspowner),
        coalesce(namespace_row.nspacl::text, ''),
        pg_catalog.obj_description(namespace_row.oid, 'pg_namespace')
      ) as value
      from pg_catalog.pg_namespace as namespace_row
      where namespace_row.nspname = 'connected_app_private'

      union all
      select pg_catalog.jsonb_build_array(
        'relation', class_row.relname, class_row.relkind,
        class_row.relpersistence, class_row.relrowsecurity,
        class_row.relforcerowsecurity, class_row.relreplident,
        pg_catalog.pg_get_userbyid(class_row.relowner),
        coalesce(class_row.relacl::text, ''),
        coalesce(class_row.reloptions::text, ''),
        coalesce(tablespace_row.spcname, ''),
        pg_catalog.obj_description(class_row.oid, 'pg_class')
      )
      from pg_catalog.pg_class as class_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      left join pg_catalog.pg_tablespace as tablespace_row
        on tablespace_row.oid = class_row.reltablespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'connections', 'credential_envelopes',
          'credential_refresh_leases', 'credential_refresh_quarantines',
          'credential_secret_tombstones', 'payload_envelopes',
          'payload_tombstones'
        )

      union all
      select pg_catalog.jsonb_build_array(
        'column', class_row.relname, attribute_row.attnum,
        attribute_row.attname,
        pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod),
        attribute_row.attnotnull, attribute_row.attidentity,
        attribute_row.attgenerated, attribute_row.attstorage,
        attribute_row.attcompression, attribute_row.attstattarget,
        coalesce(attribute_row.attoptions::text, ''),
        coalesce(attribute_row.attfdwoptions::text, ''),
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
        and class_row.relname in (
          'connections', 'credential_envelopes',
          'credential_refresh_leases', 'credential_refresh_quarantines',
          'credential_secret_tombstones', 'payload_envelopes',
          'payload_tombstones'
        )
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
        and class_row.relname in (
          'connections', 'credential_envelopes',
          'credential_refresh_leases', 'credential_refresh_quarantines',
          'credential_secret_tombstones', 'payload_envelopes',
          'payload_tombstones'
        )

      union all
      select pg_catalog.jsonb_build_array(
        'index', table_row.relname, index_class.relname,
        index_row.indisunique, index_row.indnullsnotdistinct,
        index_row.indisprimary, index_row.indisexclusion,
        index_row.indimmediate, index_row.indisclustered,
        index_row.indisvalid, index_row.indisready, index_row.indislive,
        index_row.indisreplident, pg_catalog.pg_get_indexdef(index_row.indexrelid),
        pg_catalog.pg_get_userbyid(index_class.relowner),
        coalesce(index_class.relacl::text, ''),
        coalesce(index_class.reloptions::text, ''),
        pg_catalog.obj_description(index_class.oid, 'pg_class')
      )
      from pg_catalog.pg_index as index_row
      join pg_catalog.pg_class as table_row on table_row.oid = index_row.indrelid
      join pg_catalog.pg_class as index_class
        on index_class.oid = index_row.indexrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = table_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and table_row.relname in (
          'connections', 'credential_envelopes',
          'credential_refresh_leases', 'credential_refresh_quarantines',
          'credential_secret_tombstones', 'payload_envelopes',
          'payload_tombstones'
        )

      union all
      select pg_catalog.jsonb_build_array(
        'sequence', sequence_namespace.nspname, sequence_class.relname,
        pg_catalog.pg_get_userbyid(sequence_class.relowner),
        coalesce(sequence_class.relacl::text, ''),
        sequence_row.seqstart, sequence_row.seqincrement,
        sequence_row.seqmax, sequence_row.seqmin, sequence_row.seqcache,
        sequence_row.seqcycle,
        pg_catalog.obj_description(sequence_class.oid, 'pg_class')
      )
      from pg_catalog.pg_sequence as sequence_row
      join pg_catalog.pg_class as sequence_class
        on sequence_class.oid = sequence_row.seqrelid
      join pg_catalog.pg_namespace as sequence_namespace
        on sequence_namespace.oid = sequence_class.relnamespace
      join pg_catalog.pg_depend as dependency_row
        on dependency_row.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
       and dependency_row.objid = sequence_class.oid
       and dependency_row.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass
       and dependency_row.deptype in ('a', 'i')
      join pg_catalog.pg_class as owner_table
        on owner_table.oid = dependency_row.refobjid
      where sequence_namespace.nspname = 'connected_app_private'
        and owner_table.relname in (
          'connections', 'credential_envelopes',
          'credential_refresh_leases', 'credential_refresh_quarantines',
          'credential_secret_tombstones', 'payload_envelopes',
          'payload_tombstones'
        )

      union all
      select pg_catalog.jsonb_build_array(
        'type', type_row.typname, type_row.typtype, type_row.typcategory,
        type_row.typnotnull, type_row.typalign, type_row.typstorage,
        pg_catalog.pg_get_userbyid(type_row.typowner),
        coalesce(type_row.typacl::text, ''),
        coalesce(pg_catalog.format_type(type_row.typbasetype, type_row.typtypmod), ''),
        pg_catalog.obj_description(type_row.oid, 'pg_type')
      )
      from pg_catalog.pg_type as type_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = type_row.typnamespace
      join pg_catalog.pg_class as class_row on class_row.oid = type_row.typrelid
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'connections', 'credential_envelopes',
          'credential_refresh_leases', 'credential_refresh_quarantines',
          'credential_secret_tombstones', 'payload_envelopes',
          'payload_tombstones'
        )

      union all
      select pg_catalog.jsonb_build_array(
        'function', namespace_row.nspname, proc_row.proname,
        pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
        pg_catalog.pg_get_function_result(proc_row.oid), language_row.lanname,
        proc_row.prokind, proc_row.provolatile, proc_row.proparallel,
        proc_row.proisstrict, proc_row.prosecdef, proc_row.proleakproof,
        proc_row.proretset, proc_row.pronargs, proc_row.pronargdefaults,
        coalesce(proc_row.proargnames::text, ''),
        coalesce(proc_row.proargmodes::text, ''),
        coalesce(proc_row.proconfig::text, ''), proc_row.procost, proc_row.prorows,
        pg_catalog.pg_get_userbyid(proc_row.proowner),
        coalesce(proc_row.proacl::text, ''),
        pg_catalog.md5(pg_catalog.pg_get_functiondef(proc_row.oid)),
        pg_catalog.obj_description(proc_row.oid, 'pg_proc')
      )
      from pg_catalog.pg_proc as proc_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = proc_row.pronamespace
      join pg_catalog.pg_language as language_row
        on language_row.oid = proc_row.prolang
      where (
        namespace_row.nspname = 'connected_app_private'
        and proc_row.proname in (
          'owner_lock_v1', 'payload_tombstone_before_delete_v1',
          'credential_tombstone_before_delete_v1',
          'credential_retire_after_connection_update_v1'
        )
      ) or (
        namespace_row.nspname = 'public'
        and proc_row.proname in (
          'connected_app_get_binding_v1',
          'connected_app_payload_put_v1', 'connected_app_payload_read_v1',
          'connected_app_payload_delete_v1',
          'connected_app_payload_reference_get_v1',
          'connected_app_credential_create_v1',
          'connected_app_credential_read_v1',
          'connected_app_credential_replace_v1',
          'connected_app_credential_delete_v1',
          'connected_app_credential_claim_refresh_v1',
          'connected_app_credential_quarantine_refresh_v1',
          'connected_app_credential_finish_refresh_v1'
        )
      )

      union all
      select pg_catalog.jsonb_build_array(
        'trigger', namespace_row.nspname, class_row.relname,
        trigger_row.tgname, trigger_row.tgenabled, trigger_row.tgtype,
        trigger_function_namespace.nspname, trigger_function.proname,
        pg_catalog.pg_get_function_identity_arguments(trigger_function.oid),
        pg_catalog.encode(trigger_row.tgargs, 'hex'),
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
        and namespace_row.nspname = 'connected_app_private'
        and (
          class_row.relname in (
            'credential_envelopes', 'credential_refresh_leases',
            'credential_refresh_quarantines', 'credential_secret_tombstones',
            'payload_envelopes', 'payload_tombstones'
          )
          or (
            class_row.relname = 'connections'
            and (
              trigger_row.tgname like 'connected_credential_%'
              or trigger_function.proname in (
                'payload_tombstone_before_delete_v1',
                'credential_tombstone_before_delete_v1',
                'credential_retire_after_connection_update_v1'
              )
            )
          )
        )

      union all
      select pg_catalog.jsonb_build_array(
        'rule', class_row.relname, rule_row.rulename, rule_row.ev_enabled,
        pg_catalog.pg_get_ruledef(rule_row.oid, true),
        pg_catalog.obj_description(rule_row.oid, 'pg_rewrite')
      )
      from pg_catalog.pg_rewrite as rule_row
      join pg_catalog.pg_class as class_row on class_row.oid = rule_row.ev_class
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'credential_envelopes', 'credential_refresh_leases',
          'credential_refresh_quarantines', 'credential_secret_tombstones',
          'payload_envelopes', 'payload_tombstones'
        )
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
        and class_row.relname in (
          'credential_envelopes', 'credential_refresh_leases',
          'credential_refresh_quarantines', 'credential_secret_tombstones',
          'payload_envelopes', 'payload_tombstones'
        )

      union all
      select pg_catalog.jsonb_build_array(
        'default_acl', pg_catalog.pg_get_userbyid(default_acl.defaclrole),
        default_acl.defaclobjtype, coalesce(default_acl.defaclacl::text, '')
      )
      from pg_catalog.pg_default_acl as default_acl
      where default_acl.defaclnamespace =
        pg_catalog.to_regnamespace('connected_app_private')

      union all
      select pg_catalog.jsonb_build_array(
        'allowlist', authority.action, authority.resource,
        authority.mutates_external_state, authority.approval_class
      )
      from connected_app_private.action_authority as authority

      union all
      select pg_catalog.jsonb_build_array(
        'publication_all_tables', publication_row.pubname,
        publication_row.puballtables, publication_row.pubinsert,
        publication_row.pubupdate, publication_row.pubdelete,
        publication_row.pubtruncate, publication_row.pubviaroot
      )
      from pg_catalog.pg_publication as publication_row
      where publication_row.puballtables

      union all
      select pg_catalog.jsonb_build_array(
        'publication_private', publication_row.pubname, class_row.relname,
        publication_row.pubinsert, publication_row.pubupdate,
        publication_row.pubdelete, publication_row.pubtruncate,
        publication_row.pubviaroot
      )
      from pg_catalog.pg_publication_rel as publication_relation
      join pg_catalog.pg_publication as publication_row
        on publication_row.oid = publication_relation.prpubid
      join pg_catalog.pg_class as class_row
        on class_row.oid = publication_relation.prrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'connections', 'credential_envelopes',
          'credential_refresh_leases', 'credential_refresh_quarantines',
          'credential_secret_tombstones', 'payload_envelopes',
          'payload_tombstones'
        )

      union all
      select pg_catalog.jsonb_build_array(
        'effective_schema', role_name,
        coalesce(pg_catalog.has_schema_privilege(
          role_name, 'connected_app_private', 'USAGE'
        ), false),
        coalesce(pg_catalog.has_schema_privilege(
          role_name, 'connected_app_private', 'CREATE'
        ), false),
        coalesce(pg_catalog.pg_has_role(role_name, 'service_role', 'MEMBER'), false),
        coalesce(pg_catalog.pg_has_role(role_name, 'postgres', 'USAGE'), false)
      )
      from pg_catalog.unnest(
        array['anon', 'authenticated', 'service_role']
      ) as role_name

      union all
      select pg_catalog.jsonb_build_array(
        'effective_table', role_name, class_row.relname,
        pg_catalog.has_table_privilege(role_name, class_row.oid, 'SELECT'),
        pg_catalog.has_table_privilege(role_name, class_row.oid, 'INSERT'),
        pg_catalog.has_table_privilege(role_name, class_row.oid, 'UPDATE'),
        pg_catalog.has_table_privilege(role_name, class_row.oid, 'DELETE'),
        pg_catalog.has_table_privilege(role_name, class_row.oid, 'TRUNCATE'),
        pg_catalog.has_table_privilege(role_name, class_row.oid, 'REFERENCES'),
        pg_catalog.has_table_privilege(role_name, class_row.oid, 'TRIGGER')
      )
      from pg_catalog.unnest(
        array['anon', 'authenticated', 'service_role']
      ) as role_name
      cross join pg_catalog.pg_class as class_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'credential_envelopes', 'credential_refresh_leases',
          'credential_refresh_quarantines', 'credential_secret_tombstones',
          'payload_envelopes', 'payload_tombstones'
        )

      union all
      select pg_catalog.jsonb_build_array(
        'effective_column', role_name, class_row.relname,
        attribute_row.attname,
        pg_catalog.has_column_privilege(
          role_name, class_row.oid, attribute_row.attnum, 'SELECT'
        ),
        pg_catalog.has_column_privilege(
          role_name, class_row.oid, attribute_row.attnum, 'INSERT'
        ),
        pg_catalog.has_column_privilege(
          role_name, class_row.oid, attribute_row.attnum, 'UPDATE'
        ),
        pg_catalog.has_column_privilege(
          role_name, class_row.oid, attribute_row.attnum, 'REFERENCES'
        )
      )
      from pg_catalog.unnest(
        array['anon', 'authenticated', 'service_role']
      ) as role_name
      cross join pg_catalog.pg_attribute as attribute_row
      join pg_catalog.pg_class as class_row
        on class_row.oid = attribute_row.attrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'credential_envelopes', 'credential_refresh_leases',
          'credential_refresh_quarantines', 'credential_secret_tombstones',
          'payload_envelopes', 'payload_tombstones'
        )
        and attribute_row.attnum > 0
        and not attribute_row.attisdropped

      union all
      select pg_catalog.jsonb_build_array(
        'effective_function', role_name, namespace_row.nspname,
        proc_row.proname,
        pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
        pg_catalog.has_function_privilege(role_name, proc_row.oid, 'EXECUTE')
      )
      from pg_catalog.unnest(
        array['anon', 'authenticated', 'service_role']
      ) as role_name
      cross join pg_catalog.pg_proc as proc_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = proc_row.pronamespace
      where (
        namespace_row.nspname = 'connected_app_private'
        and proc_row.proname in (
          'owner_lock_v1', 'payload_tombstone_before_delete_v1',
          'credential_tombstone_before_delete_v1',
          'credential_retire_after_connection_update_v1'
        )
      ) or (
        namespace_row.nspname = 'public'
        and proc_row.proname in (
          'connected_app_get_binding_v1',
          'connected_app_payload_put_v1', 'connected_app_payload_read_v1',
          'connected_app_payload_delete_v1',
          'connected_app_payload_reference_get_v1',
          'connected_app_credential_create_v1',
          'connected_app_credential_read_v1',
          'connected_app_credential_replace_v1',
          'connected_app_credential_delete_v1',
          'connected_app_credential_claim_refresh_v1',
          'connected_app_credential_quarantine_refresh_v1',
          'connected_app_credential_finish_refresh_v1'
        )
      )
    ) as item;

    if observed_target_fingerprint <>
       'f250e5f3e93732daabde65b3e3942f71' then
      raise exception
        'partial or drifted connected-app encrypted-store target; refusing repair; observed=%',
        observed_target_fingerprint using errcode = '55000';
    end if;

    return;
  end if;

  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    pg_catalog.obj_description(
      pg_catalog.to_regnamespace('connected_app_private'), 'pg_namespace'
    ),
    pg_catalog.obj_description(
      pg_catalog.to_regclass('connected_app_private.connections'), 'pg_class'
    ),
    pg_catalog.pg_get_functiondef(
      pg_catalog.to_regprocedure('connected_app_private.owner_lock_v1(uuid)')
    ),
    pg_catalog.pg_get_functiondef(
      pg_catalog.to_regprocedure('public.connected_app_get_binding_v1(uuid,uuid)')
    ),
    (select pg_catalog.string_agg(
       attribute_row.attname || ':'
         || pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod)
         || ':' || attribute_row.attnotnull::text,
       ',' order by attribute_row.attnum
     )
     from pg_catalog.pg_attribute as attribute_row
     where attribute_row.attrelid =
       pg_catalog.to_regclass('connected_app_private.connections')
       and attribute_row.attnum > 0 and not attribute_row.attisdropped),
    (select pg_catalog.string_agg(
       constraint_row.conname || ':'
         || pg_catalog.pg_get_constraintdef(constraint_row.oid, true),
       ',' order by constraint_row.conname
     )
     from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid =
       pg_catalog.to_regclass('connected_app_private.connections')),
    (select pg_catalog.string_agg(authority.action, ',' order by authority.action)
     from connected_app_private.action_authority as authority),
    (select pg_catalog.string_agg(class_row.relname, ',' order by class_row.relname)
     from pg_catalog.pg_class as class_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = class_row.relnamespace
     where namespace_row.nspname = 'connected_app_private'
       and class_row.relkind = 'r'),
    (select pg_catalog.string_agg(
       proc_row.proname || '('
         || pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || ')',
       ',' order by proc_row.proname,
         pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
     )
     from pg_catalog.pg_proc as proc_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = proc_row.pronamespace
     where namespace_row.nspname = 'connected_app_private'),
    (select pg_catalog.string_agg(
       proc_row.proname || '('
         || pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || ')',
       ',' order by proc_row.proname,
         pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
     )
     from pg_catalog.pg_proc as proc_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = proc_row.pronamespace
     where namespace_row.nspname = 'public'
       and proc_row.proname like 'connected_app_%')
  )) into predecessor_fingerprint;

  if predecessor_fingerprint <> '8052016e79f8049ccdab9785409c7820'
     or pg_catalog.obj_description(
       pg_catalog.to_regclass('connected_app_private.connections'), 'pg_class'
     ) is distinct from 'ASK_CRUMP_CONNECTED_APP_CONNECTIONS_V1_CONTENT_FREE'
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_get_binding_v1(uuid,uuid)'
     ) is null
     or not exists (
       select 1
       from pg_catalog.pg_constraint as constraint_row
       where constraint_row.conrelid =
         pg_catalog.to_regclass('connected_app_private.connections')
         and constraint_row.conname = 'connected_app_connections_authority_shape'
     )
     or (
       select pg_catalog.array_agg(
         authority.action order by authority.action
       )
       from connected_app_private.action_authority as authority
     ) is distinct from array[
       'calendar.cancel', 'calendar.create', 'calendar.free_busy',
       'calendar.get', 'calendar.list', 'calendar.update',
       'mail.create_draft', 'mail.get', 'mail.reply', 'mail.search', 'mail.send'
     ]::text[] then
    raise exception 'connected-app encrypted-store predecessor drifted'
      using errcode = '55000';
  end if;

end;
$preflight$;

create table if not exists connected_app_private.payload_envelopes (
  payload_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  connection_id uuid not null,
  action_id uuid not null,
  provider text not null check (provider in ('google', 'microsoft')),
  action text not null,
  commitment_key_id text not null
    check (commitment_key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null,
  expires_at timestamptz not null,
  identity_sha256 text not null check (identity_sha256 ~ '^[0-9a-f]{64}$'),
  reference_binding_sha256 text not null
    check (reference_binding_sha256 ~ '^[0-9a-f]{64}$'),
  key_id text not null check (key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  wrapped_key_nonce text not null check (wrapped_key_nonce ~ '^[A-Za-z0-9_-]{16}$'),
  wrapped_key_ciphertext text not null
    check (wrapped_key_ciphertext ~ '^[A-Za-z0-9_-]{64}$'),
  payload_nonce text not null check (payload_nonce ~ '^[A-Za-z0-9_-]{16}$'),
  payload_ciphertext text not null
    check (
      pg_catalog.length(payload_ciphertext) between 23 and 699999
      and payload_ciphertext ~ '^[A-Za-z0-9_-]+$'
    ),
  record_binding_sha256 text not null
    check (record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  constraint connected_payload_lifetime check (
    expires_at > created_at and expires_at <= created_at + interval '7 days'
  ),
  constraint connected_payload_owner_connection_fk
    foreign key (owner_id, connection_id)
    references connected_app_private.connections(owner_id, id)
    on delete cascade,
  constraint connected_payload_action_authority_fk
    foreign key (action) references connected_app_private.action_authority(action)
);
comment on table connected_app_private.payload_envelopes is
  'ASK_CRUMP_CONNECTED_PAYLOAD_ENVELOPES_V1_ENCRYPTED_ONLY';
create index if not exists connected_payload_expiry_idx
  on connected_app_private.payload_envelopes(expires_at, payload_id);
create index if not exists connected_payload_owner_fk_idx
  on connected_app_private.payload_envelopes(owner_id, connection_id, payload_id);
create index if not exists connected_payload_action_fk_idx
  on connected_app_private.payload_envelopes(action, payload_id);

create table if not exists connected_app_private.payload_tombstones (
  payload_id uuid primary key,
  identity_sha256 text not null check (identity_sha256 ~ '^[0-9a-f]{64}$'),
  record_existed boolean not null,
  erased_at timestamptz not null
);
comment on table connected_app_private.payload_tombstones is
  'ASK_CRUMP_CONNECTED_PAYLOAD_TOMBSTONES_V1_PERMANENT_CONTENT_FREE';

create table if not exists connected_app_private.credential_envelopes (
  credential_handle_sha256 text primary key
    check (credential_handle_sha256 ~ '^[0-9a-f]{64}$'),
  owner_id uuid not null references public.users(id) on delete cascade,
  connection_id uuid not null,
  provider text not null check (provider in ('google', 'microsoft')),
  connection_incarnation_id uuid not null,
  oauth_client_id_sha256 text not null
    check (oauth_client_id_sha256 ~ '^[0-9a-f]{64}$'),
  account_kind text not null check (account_kind in ('personal', 'work_school')),
  authorization_revision bigint not null check (authorization_revision >= 1),
  authorization_snapshot_sha256 text not null
    check (authorization_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  granted_actions_sha256 text not null check (granted_actions_sha256 ~ '^[0-9a-f]{64}$'),
  granted_scopes_sha256 text not null check (granted_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  external_account_id_hash text not null check (external_account_id_hash ~ '^[0-9a-f]{64}$'),
  authorization_expires_at timestamptz not null,
  secret_revision bigint not null check (secret_revision >= 1),
  created_at timestamptz not null,
  updated_at timestamptz not null,
  authority_binding_sha256 text not null check (authority_binding_sha256 ~ '^[0-9a-f]{64}$'),
  metadata_binding_sha256 text not null check (metadata_binding_sha256 ~ '^[0-9a-f]{64}$'),
  key_id text not null check (key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  wrapped_key_nonce text not null check (wrapped_key_nonce ~ '^[A-Za-z0-9_-]{16}$'),
  wrapped_key_ciphertext text not null
    check (wrapped_key_ciphertext ~ '^[A-Za-z0-9_-]{64}$'),
  secret_nonce text not null check (secret_nonce ~ '^[A-Za-z0-9_-]{16}$'),
  secret_ciphertext text not null
    check (
      pg_catalog.length(secret_ciphertext) between 23 and 65536
      and secret_ciphertext ~ '^[A-Za-z0-9_-]+$'
    ),
  record_binding_sha256 text not null check (record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  constraint connected_credential_times check (
    updated_at >= created_at and authorization_expires_at > created_at
  ),
  constraint connected_credential_owner_connection_fk
    foreign key (owner_id, connection_id)
    references connected_app_private.connections(owner_id, id)
    on delete cascade
);
comment on table connected_app_private.credential_envelopes is
  'ASK_CRUMP_CONNECTED_CREDENTIAL_ENVELOPES_V1_ENCRYPTED_REFRESH_ONLY';
create unique index if not exists connected_credential_owner_connection_idx
  on connected_app_private.credential_envelopes(owner_id, connection_id);

create table if not exists connected_app_private.credential_secret_tombstones (
  credential_handle_sha256 text primary key
    check (credential_handle_sha256 ~ '^[0-9a-f]{64}$'),
  record_existed boolean not null,
  erased_at timestamptz not null
);
comment on table connected_app_private.credential_secret_tombstones is
  'ASK_CRUMP_CONNECTED_CREDENTIAL_TOMBSTONES_V1_PERMANENT_UNLINKED';

create table if not exists connected_app_private.credential_refresh_leases (
  credential_handle_sha256 text primary key
    references connected_app_private.credential_envelopes(credential_handle_sha256)
    on delete cascade,
  lease_id uuid not null unique,
  expected_record_binding_sha256 text not null
    check (expected_record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  issued_at timestamptz not null,
  expires_at timestamptz not null,
  constraint connected_refresh_lease_lifetime check (
    expires_at > issued_at and expires_at <= issued_at + interval '30 seconds'
  )
);
comment on table connected_app_private.credential_refresh_leases is
  'ASK_CRUMP_CONNECTED_CREDENTIAL_REFRESH_LEASES_V1_CONTENT_FREE';
create index if not exists connected_credential_refresh_expiry_idx
  on connected_app_private.credential_refresh_leases(expires_at, credential_handle_sha256);

-- A provider may rotate/consume a refresh token even when its response is
-- lost. This unlinked content-free fence survives credential/account deletion
-- and permanently prevents the possibly consumed generation being retried.
create table if not exists connected_app_private.credential_refresh_quarantines (
  credential_handle_sha256 text primary key
    check (credential_handle_sha256 ~ '^[0-9a-f]{64}$'),
  lease_id uuid not null unique,
  expected_record_binding_sha256 text not null
    check (expected_record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  quarantined_at timestamptz not null
);
comment on table connected_app_private.credential_refresh_quarantines is
  'ASK_CRUMP_CONNECTED_CREDENTIAL_REFRESH_QUARANTINES_V1_PERMANENT_CONTENT_FREE';

alter table connected_app_private.payload_envelopes enable row level security;
alter table connected_app_private.payload_envelopes force row level security;
alter table connected_app_private.payload_tombstones enable row level security;
alter table connected_app_private.payload_tombstones force row level security;
alter table connected_app_private.credential_envelopes enable row level security;
alter table connected_app_private.credential_envelopes force row level security;
alter table connected_app_private.credential_secret_tombstones enable row level security;
alter table connected_app_private.credential_secret_tombstones force row level security;
alter table connected_app_private.credential_refresh_leases enable row level security;
alter table connected_app_private.credential_refresh_leases force row level security;
alter table connected_app_private.credential_refresh_quarantines enable row level security;
alter table connected_app_private.credential_refresh_quarantines force row level security;

create or replace function connected_app_private.payload_tombstone_before_delete_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
begin
  insert into connected_app_private.payload_tombstones (
    payload_id, identity_sha256, record_existed, erased_at
  ) values (
    old.payload_id, old.identity_sha256, true, pg_catalog.clock_timestamp()
  ) on conflict (payload_id) do update
    set record_existed = true
  where connected_app_private.payload_tombstones.identity_sha256 = excluded.identity_sha256;
  if not found then
    raise exception 'payload tombstone identity mismatch' using errcode = '55000';
  end if;
  return old;
end;
$fn$;

create or replace function connected_app_private.credential_tombstone_before_delete_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
begin
  insert into connected_app_private.credential_secret_tombstones (
    credential_handle_sha256, record_existed, erased_at
  ) values (
    old.credential_handle_sha256, true, pg_catalog.clock_timestamp()
  ) on conflict (credential_handle_sha256) do update
    set record_existed = true;
  return old;
end;
$fn$;

-- The control-plane revoke RPC already holds the canonical owner advisory
-- lock and the connection row lock.  Retire local custody in the same
-- transaction, after the connection has crossed out of ACTIVE authority but
-- before the revoke can commit.  The permanent tombstone also fences a
-- delayed credential-create response from resurrecting the retired handle.
create or replace function connected_app_private.credential_retire_after_connection_update_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  existed boolean;
begin
  if old.credential_ref_sha256 is not null
     and (
       new.authorization_state <> 'active'
       or new.credential_ref_sha256 is distinct from old.credential_ref_sha256
     ) then
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(
        'connected-credential:' || old.credential_ref_sha256, 0
      )
    );
    select exists (
      select 1
      from connected_app_private.credential_envelopes as envelope
      where envelope.credential_handle_sha256 = old.credential_ref_sha256
    ) into existed;
    insert into connected_app_private.credential_secret_tombstones (
      credential_handle_sha256, record_existed, erased_at
    ) values (
      old.credential_ref_sha256, existed, pg_catalog.clock_timestamp()
    ) on conflict (credential_handle_sha256) do update
      set record_existed =
        connected_app_private.credential_secret_tombstones.record_existed
        or excluded.record_existed;
    delete from connected_app_private.credential_envelopes as envelope
    where envelope.credential_handle_sha256 = old.credential_ref_sha256;
  end if;
  return new;
end;
$fn$;

create or replace trigger connected_payload_tombstone_before_delete_v1
before delete on connected_app_private.payload_envelopes
for each row execute function connected_app_private.payload_tombstone_before_delete_v1();
create or replace trigger connected_credential_tombstone_before_delete_v1
before delete on connected_app_private.credential_envelopes
for each row execute function connected_app_private.credential_tombstone_before_delete_v1();
create or replace trigger connected_credential_retire_after_connection_update_v1
after update of authorization_state, credential_ref_sha256
on connected_app_private.connections
for each row execute function connected_app_private.credential_retire_after_connection_update_v1();

create or replace function public.connected_app_payload_read_v1(
  p_payload_id uuid,
  p_identity_sha256 text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.payload_envelopes%rowtype;
  tombstone connected_app_private.payload_tombstones%rowtype;
begin
  if p_identity_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid payload identity' using errcode = '22023';
  end if;
  select * into tombstone
  from connected_app_private.payload_tombstones
  where payload_id = p_payload_id;
  if found then
    if tombstone.identity_sha256 <> p_identity_sha256 then
      raise exception 'payload identity mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  select * into envelope
  from connected_app_private.payload_envelopes
  where payload_id = p_payload_id;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'absent', 'record', null);
  end if;
  if envelope.identity_sha256 <> p_identity_sha256 then
    raise exception 'payload identity mismatch' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object('status', 'present', 'record', pg_catalog.to_jsonb(envelope));
end;
$fn$;

create or replace function public.connected_app_payload_put_v1(
  p_payload_id uuid,
  p_owner_id uuid,
  p_connection_id uuid,
  p_action_id uuid,
  p_provider text,
  p_action text,
  p_commitment_key_id text,
  p_payload_sha256 text,
  p_created_at timestamptz,
  p_expires_at timestamptz,
  p_identity_sha256 text,
  p_reference_binding_sha256 text,
  p_key_id text,
  p_wrapped_key_nonce text,
  p_wrapped_key_ciphertext text,
  p_payload_nonce text,
  p_payload_ciphertext text,
  p_record_binding_sha256 text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.payload_envelopes%rowtype;
  tombstone connected_app_private.payload_tombstones%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-payload:' || p_payload_id::text, 0)
  );
  select * into tombstone from connected_app_private.payload_tombstones
  where payload_id = p_payload_id;
  if found then
    if tombstone.identity_sha256 <> p_identity_sha256 then
      raise exception 'payload identity mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  select * into envelope from connected_app_private.payload_envelopes
  where payload_id = p_payload_id for update;
  if found then
    if envelope.identity_sha256 <> p_identity_sha256 then
      raise exception 'payload identity mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object('status', 'present', 'record', pg_catalog.to_jsonb(envelope));
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select * into connection_row from connected_app_private.connections
  where owner_id = p_owner_id and id = p_connection_id for update;
  if not found or connection_row.provider <> p_provider
     or connection_row.authorization_state <> 'active'
     or connection_row.authorization_expires_at <= p_created_at
     or not (p_action = any(connection_row.granted_actions))
     or not exists (
       select 1 from connected_app_private.action_authority as authority
       where authority.action = p_action
     ) then
    raise exception 'payload authority mismatch' using errcode = '55000';
  end if;
  insert into connected_app_private.payload_envelopes (
    payload_id, owner_id, connection_id, action_id, provider, action,
    commitment_key_id, payload_sha256, created_at, expires_at,
    identity_sha256, reference_binding_sha256, key_id, wrapped_key_nonce,
    wrapped_key_ciphertext, payload_nonce, payload_ciphertext,
    record_binding_sha256
  ) values (
    p_payload_id, p_owner_id, p_connection_id, p_action_id, p_provider, p_action,
    p_commitment_key_id, p_payload_sha256, p_created_at, p_expires_at,
    p_identity_sha256, p_reference_binding_sha256, p_key_id, p_wrapped_key_nonce,
    p_wrapped_key_ciphertext, p_payload_nonce, p_payload_ciphertext,
    p_record_binding_sha256
  ) returning * into envelope;
  return pg_catalog.jsonb_build_object('status', 'present', 'record', pg_catalog.to_jsonb(envelope));
end;
$fn$;

create or replace function public.connected_app_payload_reference_get_v1(
  p_owner_id uuid,
  p_payload_id uuid,
  p_connection_id uuid,
  p_action_id uuid,
  p_provider text,
  p_action text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.payload_envelopes%rowtype;
begin
  if p_provider not in ('google', 'microsoft')
     or not exists (
       select 1 from connected_app_private.action_authority as authority
       where authority.action = p_action
     ) then
    raise exception 'invalid payload reference lookup' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-payload:' || p_payload_id::text, 0)
  );
  if exists (
    select 1 from connected_app_private.payload_tombstones
    where payload_id = p_payload_id
  ) then
    return pg_catalog.jsonb_build_object('status', 'erased', 'reference', null);
  end if;
  select * into envelope from connected_app_private.payload_envelopes
  where payload_id = p_payload_id;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'absent', 'reference', null);
  end if;
  if envelope.owner_id <> p_owner_id
     or envelope.connection_id <> p_connection_id
     or envelope.action_id <> p_action_id
     or envelope.provider <> p_provider
     or envelope.action <> p_action then
    raise exception 'payload reference lookup binding mismatch' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'status', 'present',
    'reference', pg_catalog.jsonb_build_object(
      'payload_id', envelope.payload_id,
      'owner_id', envelope.owner_id,
      'connection_id', envelope.connection_id,
      'action_id', envelope.action_id,
      'provider', envelope.provider,
      'action', envelope.action,
      'commitment_key_id', envelope.commitment_key_id,
      'payload_sha256', envelope.payload_sha256,
      'created_at', envelope.created_at,
      'expires_at', envelope.expires_at,
      'identity_sha256', envelope.identity_sha256,
      'reference_binding_sha256', envelope.reference_binding_sha256
    )
  );
end;
$fn$;

create or replace function public.connected_app_payload_delete_v1(
  p_payload_id uuid,
  p_identity_sha256 text,
  p_erased_at timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.payload_envelopes%rowtype;
  tombstone connected_app_private.payload_tombstones%rowtype;
  existed boolean := false;
begin
  if p_identity_sha256 !~ '^[0-9a-f]{64}$'
     or p_erased_at > pg_catalog.clock_timestamp() + interval '1 minute' then
    raise exception 'invalid payload erase' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-payload:' || p_payload_id::text, 0)
  );
  select * into tombstone from connected_app_private.payload_tombstones
  where payload_id = p_payload_id for update;
  if found then
    if tombstone.identity_sha256 <> p_identity_sha256 then
      raise exception 'payload identity mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'status', 'erased', 'record_existed', tombstone.record_existed
    );
  end if;
  select * into envelope from connected_app_private.payload_envelopes
  where payload_id = p_payload_id for update;
  if found and envelope.identity_sha256 <> p_identity_sha256 then
    raise exception 'payload identity mismatch' using errcode = '55000';
  end if;
  existed := found;
  insert into connected_app_private.payload_tombstones (
    payload_id, identity_sha256, record_existed, erased_at
  ) values (p_payload_id, p_identity_sha256, existed, p_erased_at);
  if existed then
    delete from connected_app_private.payload_envelopes
    where payload_id = p_payload_id;
  end if;
  return pg_catalog.jsonb_build_object(
    'status', 'erased', 'record_existed', existed
  );
end;
$fn$;

create or replace function public.connected_app_credential_read_v1(
  p_credential_handle_sha256 text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.credential_envelopes%rowtype;
  connection_row connected_app_private.connections%rowtype;
  connection_found boolean;
begin
  if p_credential_handle_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid credential handle' using errcode = '22023';
  end if;
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'absent', 'record', null);
  end if;
  perform connected_app_private.owner_lock_v1(envelope.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = envelope.owner_id
    and connection.id = envelope.connection_id
  for update;
  connection_found := found;
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  if not connection_found
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> envelope.provider
     or connection_row.connection_incarnation_id
       <> envelope.connection_incarnation_id
     or connection_row.account_kind <> envelope.account_kind
     or connection_row.authorization_revision
       <> envelope.authorization_revision
     or connection_row.authorization_snapshot_sha256
       <> envelope.authorization_snapshot_sha256
     or connection_row.granted_actions_sha256
       <> envelope.granted_actions_sha256
     or connection_row.granted_scopes_sha256
       <> envelope.granted_scopes_sha256
     or connection_row.external_account_id_sha256
       <> envelope.external_account_id_hash
     or connection_row.authorization_expires_at
       <> envelope.authorization_expires_at
     or connection_row.authorization_expires_at <= pg_catalog.clock_timestamp()
     or connection_row.credential_ref_sha256
       <> p_credential_handle_sha256 then
    raise exception 'credential authority mismatch' using errcode = '55000';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'connected-credential:' || p_credential_handle_sha256, 0
    )
  );
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  if envelope.owner_id <> connection_row.owner_id
     or envelope.connection_id <> connection_row.id
     or envelope.provider <> connection_row.provider
     or envelope.connection_incarnation_id
       <> connection_row.connection_incarnation_id
     or envelope.account_kind <> connection_row.account_kind
     or envelope.authorization_revision
       <> connection_row.authorization_revision
     or envelope.authorization_snapshot_sha256
       <> connection_row.authorization_snapshot_sha256
     or envelope.granted_actions_sha256
       <> connection_row.granted_actions_sha256
     or envelope.granted_scopes_sha256
       <> connection_row.granted_scopes_sha256
     or envelope.external_account_id_hash
       <> connection_row.external_account_id_sha256
     or envelope.authorization_expires_at
       <> connection_row.authorization_expires_at
     or envelope.credential_handle_sha256
       <> connection_row.credential_ref_sha256 then
    raise exception 'credential authority changed' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object('status', 'present', 'record', pg_catalog.to_jsonb(envelope));
end;
$fn$;

create or replace function public.connected_app_credential_create_v1(
  p_owner_id uuid,
  p_connection_id uuid,
  p_provider text,
  p_credential_handle_sha256 text,
  p_connection_incarnation_id uuid,
  p_oauth_client_id_sha256 text,
  p_account_kind text,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,
  p_external_account_id_hash text,
  p_authorization_expires_at timestamptz,
  p_secret_revision bigint,
  p_created_at timestamptz,
  p_updated_at timestamptz,
  p_authority_binding_sha256 text,
  p_metadata_binding_sha256 text,
  p_key_id text,
  p_wrapped_key_nonce text,
  p_wrapped_key_ciphertext text,
  p_secret_nonce text,
  p_secret_ciphertext text,
  p_record_binding_sha256 text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.credential_envelopes%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select * into connection_row from connected_app_private.connections
  where owner_id = p_owner_id and id = p_connection_id for update;
  if not found or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.connection_incarnation_id <> p_connection_incarnation_id
     or connection_row.account_kind <> p_account_kind
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or connection_row.external_account_id_sha256 <> p_external_account_id_hash
     or connection_row.authorization_expires_at <> p_authorization_expires_at
     or connection_row.authorization_expires_at <= pg_catalog.clock_timestamp()
     or connection_row.credential_ref_sha256 <> p_credential_handle_sha256
     or p_secret_revision <> 1 then
    raise exception 'credential authority mismatch' using errcode = '55000';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    raise exception 'credential handle retired' using errcode = '55000';
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if found then
    if envelope.record_binding_sha256 <> p_record_binding_sha256 then
      raise exception 'credential binding mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object('status', 'present', 'record', pg_catalog.to_jsonb(envelope));
  end if;
  insert into connected_app_private.credential_envelopes (
    credential_handle_sha256, owner_id, connection_id, provider,
    connection_incarnation_id, oauth_client_id_sha256, account_kind,
    authorization_revision, authorization_snapshot_sha256,
    granted_actions_sha256, granted_scopes_sha256, external_account_id_hash,
    authorization_expires_at, secret_revision, created_at, updated_at,
    authority_binding_sha256, metadata_binding_sha256, key_id,
    wrapped_key_nonce, wrapped_key_ciphertext, secret_nonce,
    secret_ciphertext, record_binding_sha256
  ) values (
    p_credential_handle_sha256, p_owner_id, p_connection_id, p_provider,
    p_connection_incarnation_id, p_oauth_client_id_sha256, p_account_kind,
    p_authorization_revision, p_authorization_snapshot_sha256,
    p_granted_actions_sha256, p_granted_scopes_sha256, p_external_account_id_hash,
    p_authorization_expires_at, p_secret_revision, p_created_at, p_updated_at,
    p_authority_binding_sha256, p_metadata_binding_sha256, p_key_id,
    p_wrapped_key_nonce, p_wrapped_key_ciphertext, p_secret_nonce,
    p_secret_ciphertext, p_record_binding_sha256
  ) returning * into envelope;
  return pg_catalog.jsonb_build_object('status', 'present', 'record', pg_catalog.to_jsonb(envelope));
end;
$fn$;

create or replace function public.connected_app_credential_replace_v1(
  p_owner_id uuid,
  p_connection_id uuid,
  p_provider text,
  p_credential_handle_sha256 text,
  p_connection_incarnation_id uuid,
  p_oauth_client_id_sha256 text,
  p_account_kind text,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,
  p_external_account_id_hash text,
  p_authorization_expires_at timestamptz,
  p_secret_revision bigint,
  p_created_at timestamptz,
  p_updated_at timestamptz,
  p_authority_binding_sha256 text,
  p_metadata_binding_sha256 text,
  p_key_id text,
  p_wrapped_key_nonce text,
  p_wrapped_key_ciphertext text,
  p_secret_nonce text,
  p_secret_ciphertext text,
  p_record_binding_sha256 text,
  p_expected_record_binding_sha256 text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.credential_envelopes%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id
    and connection.id = p_connection_id
  for update;
  if not found
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.connection_incarnation_id
       <> p_connection_incarnation_id
     or connection_row.account_kind <> p_account_kind
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256
       <> p_authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or connection_row.external_account_id_sha256
       <> p_external_account_id_hash
     or connection_row.authorization_expires_at
       <> p_authorization_expires_at
     or connection_row.authorization_expires_at <= pg_catalog.clock_timestamp()
     or connection_row.credential_ref_sha256
       <> p_credential_handle_sha256 then
    raise exception 'credential authority mismatch' using errcode = '55000';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    raise exception 'credential handle retired' using errcode = '55000';
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if not found
     or envelope.record_binding_sha256 <> p_expected_record_binding_sha256
     or envelope.owner_id <> p_owner_id
     or envelope.connection_id <> p_connection_id
     or envelope.provider <> p_provider
     or envelope.connection_incarnation_id <> p_connection_incarnation_id
     or envelope.oauth_client_id_sha256 <> p_oauth_client_id_sha256
     or envelope.account_kind <> p_account_kind
     or envelope.authorization_revision <> p_authorization_revision
     or envelope.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or envelope.granted_actions_sha256 <> p_granted_actions_sha256
     or envelope.granted_scopes_sha256 <> p_granted_scopes_sha256
     or envelope.external_account_id_hash <> p_external_account_id_hash
     or envelope.authorization_expires_at <> p_authorization_expires_at
     or envelope.created_at <> p_created_at
     or p_secret_revision <> envelope.secret_revision + 1
     or p_updated_at <= envelope.updated_at then
    raise exception 'credential CAS mismatch' using errcode = '55000';
  end if;
  update connected_app_private.credential_envelopes set
    secret_revision = p_secret_revision,
    updated_at = p_updated_at,
    authority_binding_sha256 = p_authority_binding_sha256,
    metadata_binding_sha256 = p_metadata_binding_sha256,
    key_id = p_key_id,
    wrapped_key_nonce = p_wrapped_key_nonce,
    wrapped_key_ciphertext = p_wrapped_key_ciphertext,
    secret_nonce = p_secret_nonce,
    secret_ciphertext = p_secret_ciphertext,
    record_binding_sha256 = p_record_binding_sha256
  where credential_handle_sha256 = p_credential_handle_sha256
  returning * into envelope;
  return pg_catalog.jsonb_build_object('status', 'present', 'record', pg_catalog.to_jsonb(envelope));
end;
$fn$;

create or replace function public.connected_app_credential_delete_v1(
  p_credential_handle_sha256 text,
  p_expected_record_binding_sha256 text,
  p_erased_at timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.credential_envelopes%rowtype;
  tombstone connected_app_private.credential_secret_tombstones%rowtype;
  existed boolean := false;
begin
  if p_credential_handle_sha256 !~ '^[0-9a-f]{64}$'
     or p_expected_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_erased_at > pg_catalog.clock_timestamp() + interval '1 minute' then
    raise exception 'invalid credential erase' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  select * into tombstone from connected_app_private.credential_secret_tombstones
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if found then
    return pg_catalog.jsonb_build_object(
      'status', 'erased', 'record_existed', tombstone.record_existed
    );
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if found and envelope.record_binding_sha256 <> p_expected_record_binding_sha256 then
    raise exception 'credential CAS mismatch' using errcode = '55000';
  end if;
  existed := found;
  insert into connected_app_private.credential_secret_tombstones (
    credential_handle_sha256, record_existed, erased_at
  ) values (p_credential_handle_sha256, existed, p_erased_at);
  if existed then
    delete from connected_app_private.credential_envelopes
    where credential_handle_sha256 = p_credential_handle_sha256;
  end if;
  return pg_catalog.jsonb_build_object(
    'status', 'erased', 'record_existed', existed
  );
end;
$fn$;

create or replace function public.connected_app_credential_claim_refresh_v1(
  p_credential_handle_sha256 text,
  p_expected_record_binding_sha256 text,
  p_lease_id uuid,
  p_lease_seconds integer
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.credential_envelopes%rowtype;
  lease connected_app_private.credential_refresh_leases%rowtype;
  connection_row connected_app_private.connections%rowtype;
  database_now timestamptz := pg_catalog.clock_timestamp();
begin
  if p_credential_handle_sha256 !~ '^[0-9a-f]{64}$'
     or p_expected_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_lease_seconds < 1 or p_lease_seconds > 30 then
    raise exception 'invalid credential refresh lease' using errcode = '22023';
  end if;
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    raise exception 'credential refresh generation quarantined' using errcode = '55000';
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256;
  if not found then
    raise exception 'credential refresh authority mismatch' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(envelope.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = envelope.owner_id
    and connection.id = envelope.connection_id
  for update;
  if not found
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> envelope.provider
     or connection_row.connection_incarnation_id
       <> envelope.connection_incarnation_id
     or connection_row.account_kind <> envelope.account_kind
     or connection_row.authorization_revision
       <> envelope.authorization_revision
     or connection_row.authorization_snapshot_sha256
       <> envelope.authorization_snapshot_sha256
     or connection_row.granted_actions_sha256
       <> envelope.granted_actions_sha256
     or connection_row.granted_scopes_sha256
       <> envelope.granted_scopes_sha256
     or connection_row.external_account_id_sha256
       <> envelope.external_account_id_hash
     or connection_row.authorization_expires_at
       <> envelope.authorization_expires_at
     or connection_row.authorization_expires_at <= database_now
     or connection_row.credential_ref_sha256
       <> p_credential_handle_sha256 then
    raise exception 'credential refresh authority mismatch' using errcode = '55000';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    raise exception 'credential refresh generation quarantined' using errcode = '55000';
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if not found
     or envelope.record_binding_sha256 <> p_expected_record_binding_sha256
     or envelope.owner_id <> connection_row.owner_id
     or envelope.connection_id <> connection_row.id
     or envelope.provider <> connection_row.provider
     or envelope.connection_incarnation_id
       <> connection_row.connection_incarnation_id
     or envelope.account_kind <> connection_row.account_kind
     or envelope.authorization_revision
       <> connection_row.authorization_revision
     or envelope.authorization_snapshot_sha256
       <> connection_row.authorization_snapshot_sha256
     or envelope.granted_actions_sha256
       <> connection_row.granted_actions_sha256
     or envelope.granted_scopes_sha256
       <> connection_row.granted_scopes_sha256
     or envelope.external_account_id_hash
       <> connection_row.external_account_id_sha256
     or envelope.authorization_expires_at
       <> connection_row.authorization_expires_at
     or envelope.credential_handle_sha256
       <> connection_row.credential_ref_sha256 then
    raise exception 'credential refresh authority mismatch' using errcode = '55000';
  end if;
  select * into lease from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if found and lease.lease_id = p_lease_id then
    return pg_catalog.jsonb_build_object(
      'status', 'claimed',
      'credential_handle_sha256', lease.credential_handle_sha256,
      'lease_id', lease.lease_id,
      'expected_record_binding_sha256', lease.expected_record_binding_sha256,
      'issued_at', lease.issued_at,
      'expires_at', lease.expires_at
    );
  end if;
  if found and lease.expires_at > database_now then
    return pg_catalog.jsonb_build_object(
      'status', 'busy',
      'credential_handle_sha256', lease.credential_handle_sha256,
      'lease_id', lease.lease_id,
      'expected_record_binding_sha256', lease.expected_record_binding_sha256,
      'issued_at', lease.issued_at,
      'expires_at', lease.expires_at
    );
  end if;
  insert into connected_app_private.credential_refresh_leases (
    credential_handle_sha256, lease_id, expected_record_binding_sha256,
    issued_at, expires_at
  ) values (
    p_credential_handle_sha256, p_lease_id, p_expected_record_binding_sha256,
    database_now, database_now + pg_catalog.make_interval(secs => p_lease_seconds)
  ) on conflict (credential_handle_sha256) do update set
    lease_id = excluded.lease_id,
    expected_record_binding_sha256 = excluded.expected_record_binding_sha256,
    issued_at = excluded.issued_at,
    expires_at = excluded.expires_at
  returning * into lease;
  return pg_catalog.jsonb_build_object(
    'status', 'claimed',
    'credential_handle_sha256', lease.credential_handle_sha256,
    'lease_id', lease.lease_id,
    'expected_record_binding_sha256', lease.expected_record_binding_sha256,
    'issued_at', lease.issued_at,
    'expires_at', lease.expires_at
  );
end;
$fn$;

create or replace function public.connected_app_credential_quarantine_refresh_v1(
  p_credential_handle_sha256 text,
  p_lease_id uuid,
  p_expected_record_binding_sha256 text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  lease connected_app_private.credential_refresh_leases%rowtype;
  quarantine connected_app_private.credential_refresh_quarantines%rowtype;
  database_now timestamptz := pg_catalog.clock_timestamp();
begin
  if p_credential_handle_sha256 !~ '^[0-9a-f]{64}$'
     or p_expected_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_lease_id is null then
    raise exception 'invalid credential refresh quarantine' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  select * into quarantine
  from connected_app_private.credential_refresh_quarantines
  where credential_handle_sha256 = p_credential_handle_sha256
  for update;
  if found then
    if quarantine.lease_id <> p_lease_id
       or quarantine.expected_record_binding_sha256
         <> p_expected_record_binding_sha256 then
      raise exception 'credential refresh quarantine replay mismatch'
        using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'status', 'quarantined',
      'credential_handle_sha256', quarantine.credential_handle_sha256,
      'lease_id', quarantine.lease_id,
      'expected_record_binding_sha256', quarantine.expected_record_binding_sha256,
      'quarantined_at', quarantine.quarantined_at
    );
  end if;
  select * into lease
  from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256
  for update;
  if not found or lease.lease_id <> p_lease_id
     or lease.expected_record_binding_sha256
       <> p_expected_record_binding_sha256 then
    raise exception 'credential refresh quarantine lease mismatch'
      using errcode = '55000';
  end if;
  insert into connected_app_private.credential_refresh_quarantines (
    credential_handle_sha256, lease_id,
    expected_record_binding_sha256, quarantined_at
  ) values (
    p_credential_handle_sha256, p_lease_id,
    p_expected_record_binding_sha256, database_now
  ) returning * into quarantine;
  delete from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256
    and lease_id = p_lease_id;
  return pg_catalog.jsonb_build_object(
    'status', 'quarantined',
    'credential_handle_sha256', quarantine.credential_handle_sha256,
    'lease_id', quarantine.lease_id,
    'expected_record_binding_sha256', quarantine.expected_record_binding_sha256,
    'quarantined_at', quarantine.quarantined_at
  );
end;
$fn$;

create or replace function public.connected_app_credential_finish_refresh_v1(
  p_credential_handle_sha256 text,
  p_lease_id uuid
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  deleted_rows integer;
begin
  if p_credential_handle_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid credential refresh finish' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  delete from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256
    and lease_id = p_lease_id;
  get diagnostics deleted_rows = row_count;
  if deleted_rows = 0 and exists (
    select 1 from connected_app_private.credential_refresh_leases
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    raise exception 'credential refresh lease mismatch' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object('status', 'finished', 'lease_id', p_lease_id);
end;
$fn$;

alter function connected_app_private.payload_tombstone_before_delete_v1() owner to postgres;
alter function connected_app_private.credential_tombstone_before_delete_v1() owner to postgres;
alter function connected_app_private.credential_retire_after_connection_update_v1()
  owner to postgres;

do $acl$
declare
  object_row record;
  role_name text;
  signature text;
begin
  for object_row in
    select class_row.relname
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname in (
        'credential_envelopes', 'credential_refresh_leases',
        'credential_refresh_quarantines',
        'credential_secret_tombstones', 'payload_envelopes', 'payload_tombstones'
      )
  loop
    execute pg_catalog.format(
      'alter table connected_app_private.%I owner to postgres', object_row.relname
    );
    execute pg_catalog.format(
      'revoke all on table connected_app_private.%I from public', object_row.relname
    );
    for role_name in
      select role_row.rolname from pg_catalog.pg_roles as role_row
      where role_row.rolname <> 'postgres'
    loop
      execute pg_catalog.format(
        'revoke all on table connected_app_private.%I from %I',
        object_row.relname, role_name
      );
    end loop;
  end loop;

  for object_row in
    select proc_row.oid, namespace_row.nspname, proc_row.proname,
           pg_catalog.pg_get_function_identity_arguments(proc_row.oid) as arguments
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where (namespace_row.nspname = 'public'
      and proc_row.proname in (
        'connected_app_payload_put_v1', 'connected_app_payload_read_v1',
        'connected_app_payload_delete_v1', 'connected_app_payload_reference_get_v1',
        'connected_app_credential_create_v1', 'connected_app_credential_read_v1',
        'connected_app_credential_replace_v1', 'connected_app_credential_delete_v1',
        'connected_app_credential_claim_refresh_v1',
        'connected_app_credential_quarantine_refresh_v1',
        'connected_app_credential_finish_refresh_v1'
      )) or (namespace_row.nspname = 'connected_app_private'
      and proc_row.proname in (
        'payload_tombstone_before_delete_v1',
        'credential_tombstone_before_delete_v1',
        'credential_retire_after_connection_update_v1'
      ))
  loop
    signature := pg_catalog.format(
      '%I.%I(%s)', object_row.nspname, object_row.proname, object_row.arguments
    );
    execute 'alter function ' || signature || ' owner to postgres';
    execute 'revoke all on function ' || signature || ' from public';
    for role_name in
      select role_row.rolname from pg_catalog.pg_roles as role_row
      where role_row.rolname <> 'postgres'
    loop
      execute 'revoke all on function ' || signature || ' from '
        || pg_catalog.quote_ident(role_name);
    end loop;
    if object_row.nspname = 'public' then
      execute 'grant execute on function ' || signature || ' to service_role';
    end if;
  end loop;
end;
$acl$;

do $postflight$
declare
  relation_names text[];
  function_names text[];
  private_function_names text[];
  relation_row record;
  function_row record;
begin
  select pg_catalog.array_agg(class_row.relname order by class_row.relname)
  into relation_names
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_app_private'
    and class_row.relname in (
      'credential_envelopes', 'credential_refresh_leases',
      'credential_refresh_quarantines',
      'credential_secret_tombstones', 'payload_envelopes', 'payload_tombstones'
    );
  if relation_names is distinct from array[
    'credential_envelopes', 'credential_refresh_leases',
    'credential_refresh_quarantines',
    'credential_secret_tombstones', 'payload_envelopes', 'payload_tombstones'
  ]::text[] then
    raise exception 'connected-app encrypted-store relation manifest drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.array_agg(proc_row.proname order by proc_row.proname)
  into function_names
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname in (
      'connected_app_payload_put_v1', 'connected_app_payload_read_v1',
      'connected_app_payload_delete_v1', 'connected_app_payload_reference_get_v1',
      'connected_app_credential_create_v1', 'connected_app_credential_read_v1',
      'connected_app_credential_replace_v1', 'connected_app_credential_delete_v1',
      'connected_app_credential_claim_refresh_v1',
      'connected_app_credential_quarantine_refresh_v1',
      'connected_app_credential_finish_refresh_v1'
    );
  if function_names is distinct from array[
    'connected_app_credential_claim_refresh_v1',
    'connected_app_credential_create_v1',
    'connected_app_credential_delete_v1',
    'connected_app_credential_finish_refresh_v1',
    'connected_app_credential_quarantine_refresh_v1',
    'connected_app_credential_read_v1',
    'connected_app_credential_replace_v1',
    'connected_app_payload_delete_v1',
    'connected_app_payload_put_v1',
    'connected_app_payload_read_v1',
    'connected_app_payload_reference_get_v1'
  ]::text[] then
    raise exception 'connected-app encrypted-store RPC manifest drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.array_agg(proc_row.proname order by proc_row.proname)
  into private_function_names
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'connected_app_private'
    and proc_row.proname in (
      'credential_retire_after_connection_update_v1',
      'credential_tombstone_before_delete_v1',
      'payload_tombstone_before_delete_v1'
    );
  if private_function_names is distinct from array[
    'credential_retire_after_connection_update_v1',
    'credential_tombstone_before_delete_v1',
    'payload_tombstone_before_delete_v1'
  ]::text[] or not exists (
    select 1
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid =
      pg_catalog.to_regclass('connected_app_private.connections')
      and trigger_row.tgname =
        'connected_credential_retire_after_connection_update_v1'
      and not trigger_row.tgisinternal
      and trigger_row.tgenabled = 'O'
      and trigger_row.tgfoid = pg_catalog.to_regprocedure(
        'connected_app_private.credential_retire_after_connection_update_v1()'
      )
  ) then
    raise exception 'connected-app encrypted-store retirement manifest drifted'
      using errcode = '55000';
  end if;

  for relation_row in
    select class_row.oid, class_row.relname, class_row.relowner,
           class_row.relrowsecurity, class_row.relforcerowsecurity
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname = any(relation_names)
  loop
    if pg_catalog.pg_get_userbyid(relation_row.relowner) <> 'postgres'
       or not relation_row.relrowsecurity or not relation_row.relforcerowsecurity
       or exists (
         select 1 from pg_catalog.aclexplode(
           coalesce(
             (select class_row.relacl from pg_catalog.pg_class as class_row
              where class_row.oid = relation_row.oid),
             pg_catalog.acldefault('r', relation_row.relowner)
           )
         ) as acl_row where acl_row.grantee <> relation_row.relowner
       ) then
      raise exception 'connected-app encrypted-store table authority drifted: %',
        relation_row.relname using errcode = '55000';
    end if;
  end loop;

  for function_row in
    select proc_row.oid, proc_row.proname, proc_row.proowner,
           proc_row.prosecdef, proc_row.proconfig
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname = any(function_names)
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
      raise exception 'connected-app encrypted-store function authority drifted: %',
        function_row.proname using errcode = '55000';
    end if;
  end loop;

  if exists (
    select 1 from pg_catalog.pg_policy as policy_row
    join pg_catalog.pg_class as class_row on class_row.oid = policy_row.polrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname = any(relation_names)
  ) or exists (
    select 1 from pg_catalog.pg_publication where puballtables
  ) or exists (
    select 1 from pg_catalog.pg_publication_rel as publication_relation
    join pg_catalog.pg_class as class_row on class_row.oid = publication_relation.prrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname = any(relation_names)
  ) then
    raise exception 'connected-app encrypted-store exposure drifted'
      using errcode = '55000';
  end if;
end;
$postflight$;

commit;

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
