begin;

select pg_catalog.set_config('search_path', 'pg_catalog,public', true);
select pg_catalog.set_config('quote_all_identifiers', 'off', true);

-- Refuse a missing, partial, or drifted encrypted-store predecessor. The
-- fingerprint is dependency-scoped: it pins the exact relations, comments,
-- function bodies, owner-lock protocol, and service-role authority this layer
-- calls. It intentionally does not try to repair predecessor drift.
do $preflight$
declare
  target_count integer;
  target_function_count integer;
  target_trigger_count integer;
  predecessor_fingerprint text;
  observed_target_fingerprint text;
begin
  select pg_catalog.count(*) into target_count
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_app_private'
    and class_row.relname in (
      'oauth_secret_custody', 'oauth_secret_tombstones',
      'oauth_provisional_credentials', 'oauth_provisional_tombstones'
    );
  select pg_catalog.count(*) into target_function_count
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname in ('public', 'connected_app_private')
    and proc_row.proname in (
      'oauth_secret_flow_json_v1', 'oauth_provisional_json_v1',
      'oauth_secret_tombstone_before_delete_v1',
      'oauth_provisional_tombstone_before_delete_v1',
      'connected_app_oauth_secret_begin_v1',
      'connected_app_oauth_secret_read_flow_v1',
      'connected_app_oauth_secret_fence_v1',
      'connected_app_oauth_secret_grant_v1',
      'connected_app_oauth_secret_ambiguous_v1',
      'connected_app_oauth_secret_read_exchange_v1',
      'connected_app_oauth_provisional_read_v1',
      'connected_app_oauth_provisional_erase_v1',
      'connected_app_oauth_secret_abort_v1'
    );
  select pg_catalog.count(*) into target_trigger_count
  from pg_catalog.pg_trigger as trigger_row
  join pg_catalog.pg_class as class_row on class_row.oid = trigger_row.tgrelid
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where not trigger_row.tgisinternal
    and namespace_row.nspname = 'connected_app_private'
    and class_row.relname in (
      'oauth_secret_custody', 'oauth_secret_tombstones',
      'oauth_provisional_credentials', 'oauth_provisional_tombstones'
    );

  -- Every statement below is syntactically idempotent only after this exact
  -- target attestation succeeds. A partial, mixed, overloaded, exposed, or
  -- drifted target is rejected before any IF NOT EXISTS / CREATE OR REPLACE
  -- statement can repair it. The manifest also pins the exact predecessor
  -- dependencies consumed by this layer and stays stable under later layers.
  if target_count <> 0 or target_function_count <> 0
     or target_trigger_count <> 0 then
    select pg_catalog.md5(
      pg_catalog.string_agg(
        item.value::text,
        E'\n' order by item.value::text collate pg_catalog."C"
      )
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
          'credential_refresh_quarantines', 'oauth_secret_custody',
          'oauth_secret_tombstones', 'oauth_provisional_credentials',
          'oauth_provisional_tombstones'
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
          'credential_refresh_quarantines', 'oauth_secret_custody',
          'oauth_secret_tombstones', 'oauth_provisional_credentials',
          'oauth_provisional_tombstones'
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
          'credential_refresh_quarantines', 'oauth_secret_custody',
          'oauth_secret_tombstones', 'oauth_provisional_credentials',
          'oauth_provisional_tombstones'
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
          'credential_refresh_quarantines', 'oauth_secret_custody',
          'oauth_secret_tombstones', 'oauth_provisional_credentials',
          'oauth_provisional_tombstones'
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
          'credential_refresh_quarantines', 'oauth_secret_custody',
          'oauth_secret_tombstones', 'oauth_provisional_credentials',
          'oauth_provisional_tombstones'
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
          'credential_refresh_quarantines', 'oauth_secret_custody',
          'oauth_secret_tombstones', 'oauth_provisional_credentials',
          'oauth_provisional_tombstones'
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
          'owner_lock_v1', 'oauth_secret_flow_json_v1',
          'oauth_provisional_json_v1',
          'oauth_secret_tombstone_before_delete_v1',
          'oauth_provisional_tombstone_before_delete_v1'
        )
      ) or (
        namespace_row.nspname = 'public'
        and proc_row.proname in (
          'connected_app_credential_create_v1',
          'connected_app_credential_quarantine_refresh_v1',
          'connected_app_oauth_secret_begin_v1',
          'connected_app_oauth_secret_read_flow_v1',
          'connected_app_oauth_secret_fence_v1',
          'connected_app_oauth_secret_grant_v1',
          'connected_app_oauth_secret_ambiguous_v1',
          'connected_app_oauth_secret_read_exchange_v1',
          'connected_app_oauth_provisional_read_v1',
          'connected_app_oauth_provisional_erase_v1',
          'connected_app_oauth_secret_abort_v1'
        )
      )

      union all
      select pg_catalog.jsonb_build_array(
        'trigger', class_row.relname, trigger_row.tgname,
        trigger_row.tgenabled, trigger_row.tgtype,
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
        and class_row.relname in (
          'oauth_secret_custody', 'oauth_secret_tombstones',
          'oauth_provisional_credentials', 'oauth_provisional_tombstones'
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
          'oauth_secret_custody', 'oauth_secret_tombstones',
          'oauth_provisional_credentials', 'oauth_provisional_tombstones'
        )
        and rule_row.rulename <> '_RETURN'

      union all
      select pg_catalog.jsonb_build_array(
        'policy', class_row.relname, policy_row.polname,
        policy_row.polpermissive, policy_row.polcmd,
        (
          select pg_catalog.array_agg(
            case when policy_role.role_oid = 0 then 'public'::text
              else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end
            order by (case when policy_role.role_oid = 0 then 'public'::text
              else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end)
              collate pg_catalog."C"
          )::text
          from pg_catalog.unnest(policy_row.polroles)
            as policy_role(role_oid)
        ),
        pg_catalog.pg_get_expr(policy_row.polqual, policy_row.polrelid),
        pg_catalog.pg_get_expr(policy_row.polwithcheck, policy_row.polrelid)
      )
      from pg_catalog.pg_policy as policy_row
      join pg_catalog.pg_class as class_row on class_row.oid = policy_row.polrelid
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'oauth_secret_custody', 'oauth_secret_tombstones',
          'oauth_provisional_credentials', 'oauth_provisional_tombstones'
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
          'credential_refresh_quarantines', 'oauth_secret_custody',
          'oauth_secret_tombstones', 'oauth_provisional_credentials',
          'oauth_provisional_tombstones'
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
          'oauth_secret_custody', 'oauth_secret_tombstones',
          'oauth_provisional_credentials', 'oauth_provisional_tombstones'
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
          'oauth_secret_custody', 'oauth_secret_tombstones',
          'oauth_provisional_credentials', 'oauth_provisional_tombstones'
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
          'owner_lock_v1', 'oauth_secret_flow_json_v1',
          'oauth_provisional_json_v1',
          'oauth_secret_tombstone_before_delete_v1',
          'oauth_provisional_tombstone_before_delete_v1'
        )
      ) or (
        namespace_row.nspname = 'public'
        and proc_row.proname in (
          'connected_app_credential_create_v1',
          'connected_app_credential_quarantine_refresh_v1',
          'connected_app_oauth_secret_begin_v1',
          'connected_app_oauth_secret_read_flow_v1',
          'connected_app_oauth_secret_fence_v1',
          'connected_app_oauth_secret_grant_v1',
          'connected_app_oauth_secret_ambiguous_v1',
          'connected_app_oauth_secret_read_exchange_v1',
          'connected_app_oauth_provisional_read_v1',
          'connected_app_oauth_provisional_erase_v1',
          'connected_app_oauth_secret_abort_v1'
        )
      )
    ) as item;

    if observed_target_fingerprint <>
       '15a55a3a38c8fe732729e6d38c79c880' then
      raise exception
        'partial or drifted connected-app OAuth secret target; refusing repair; observed=%',
        observed_target_fingerprint using errcode = '55000';
    end if;

    return;
  end if;

  if exists (
    select 1 from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname in ('public', 'connected_app_private')
      and (
        proc_row.proname like 'connected_app_oauth_secret_%'
        or proc_row.proname like 'connected_app_oauth_provisional_%'
      )
  ) then
    raise exception 'partial connected-app OAuth secret target; refusing repair'
      using errcode = '55000';
  end if;

  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    pg_catalog.obj_description(
      pg_catalog.to_regclass('connected_app_private.credential_envelopes'), 'pg_class'
    ),
    pg_catalog.obj_description(
      pg_catalog.to_regclass('connected_app_private.credential_refresh_quarantines'), 'pg_class'
    ),
    pg_catalog.pg_get_functiondef(
      pg_catalog.to_regprocedure('connected_app_private.owner_lock_v1(uuid)')
    ),
    pg_catalog.pg_get_functiondef(
      pg_catalog.to_regprocedure('public.connected_app_credential_create_v1(uuid,uuid,text,text,uuid,text,text,bigint,text,text,text,text,timestamptz,bigint,timestamptz,timestamptz,text,text,text,text,text,text,text,text)')
    ),
    pg_catalog.pg_get_functiondef(
      pg_catalog.to_regprocedure('public.connected_app_credential_quarantine_refresh_v1(text,uuid,text)')
    ),
    (select pg_catalog.string_agg(
       class_row.relname,
       ',' order by class_row.relname collate pg_catalog."C"
     )
     from pg_catalog.pg_class as class_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = class_row.relnamespace
     where namespace_row.nspname = 'connected_app_private'
       and class_row.relkind = 'r'),
    (select pg_catalog.string_agg(
       proc_row.proname || '(' ||
         pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || ')',
       ',' order by proc_row.proname collate pg_catalog."C",
         pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
           collate pg_catalog."C")
     from pg_catalog.pg_proc as proc_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = proc_row.pronamespace
     where namespace_row.nspname = 'public'
       and proc_row.proname like 'connected_app_%')
  )) into predecessor_fingerprint;

  -- Exact dependency-scoped fingerprint of reviewed 19:00 + 23:00 targets.
  if predecessor_fingerprint <> '03b28d375bdb0f819bb70fbc2dff1819'
     or pg_catalog.obj_description(
       pg_catalog.to_regclass('connected_app_private.credential_envelopes'), 'pg_class'
     ) is distinct from
       'ASK_CRUMP_CONNECTED_CREDENTIAL_ENVELOPES_V1_ENCRYPTED_REFRESH_ONLY'
     or pg_catalog.obj_description(
       pg_catalog.to_regclass('connected_app_private.credential_refresh_quarantines'), 'pg_class'
     ) is distinct from
       'ASK_CRUMP_CONNECTED_CREDENTIAL_REFRESH_QUARANTINES_V1_PERMANENT_CONTENT_FREE'
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null then
    raise exception 'connected-app OAuth secret predecessor drifted'
      using errcode = '55000';
  end if;
end;
$preflight$;

create table if not exists connected_app_private.oauth_secret_custody (
  flow_id uuid primary key,
  nonce_id uuid not null,
  owner_id uuid not null references public.users(id) on delete cascade,
  connection_id uuid not null,
  connection_incarnation_id uuid not null,
  expected_base_revision bigint not null check (expected_base_revision >= 0),
  current_flow_nonce_sha256 text not null check (current_flow_nonce_sha256 ~ '^[0-9a-f]{64}$'),
  session_binding_sha256 text not null check (session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  account_kind text not null check (account_kind in ('personal', 'work_school')),
  actions text[] not null check (cardinality(actions) between 1 and 16),
  actions_sha256 text not null check (actions_sha256 ~ '^[0-9a-f]{64}$'),
  requested_scopes text[] not null check (cardinality(requested_scopes) between 1 and 64),
  requested_scopes_sha256 text not null check (requested_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  state_sha256 text not null check (state_sha256 ~ '^[0-9a-f]{64}$'),
  pkce_challenge text not null check (pkce_challenge ~ '^[A-Za-z0-9_-]{43}$'),
  redirect_uri text not null check (pg_catalog.length(redirect_uri) between 16 and 2048),
  created_at timestamptz not null,
  expires_at timestamptz not null,
  flow_binding_sha256 text not null unique check (flow_binding_sha256 ~ '^[0-9a-f]{64}$'),
  accepted_at timestamptz not null default pg_catalog.clock_timestamp(),
  status text not null default 'pending'
    check (status in (
      'pending', 'attempt_fenced', 'granted', 'ambiguous',
      'deadline_expired', 'erased'
    )),
  exchange_id uuid,
  exchange_binding_sha256 text
    check (exchange_binding_sha256 is null or exchange_binding_sha256 ~ '^[0-9a-f]{64}$'),
  attempt_id uuid,
  terminal_at timestamptz,
  credential_handle_sha256 text
    check (credential_handle_sha256 is null or credential_handle_sha256 ~ '^[0-9a-f]{64}$'),
  external_account_id_hash text
    check (external_account_id_hash is null or external_account_id_hash ~ '^[0-9a-f]{64}$'),
  actual_scopes text[],
  actual_scopes_sha256 text
    check (actual_scopes_sha256 is null or actual_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  grant_issued_at timestamptz,
  grant_expires_at timestamptz,
  secret_key_id text not null check (secret_key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  secret_wrapped_key_nonce text not null check (secret_wrapped_key_nonce ~ '^[A-Za-z0-9_-]{16}$'),
  secret_wrapped_key_ciphertext text not null check (secret_wrapped_key_ciphertext ~ '^[A-Za-z0-9_-]{64}$'),
  secret_nonce text not null check (secret_nonce ~ '^[A-Za-z0-9_-]{16}$'),
  secret_ciphertext text not null check (
    pg_catalog.length(secret_ciphertext) between 23 and 131072
    and secret_ciphertext ~ '^[A-Za-z0-9_-]+$'
  ),
  secret_record_binding_sha256 text not null check (secret_record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  constraint connected_oauth_secret_owner_connection_fk
    foreign key (owner_id, connection_id)
    references connected_app_private.connections(owner_id, id)
    on delete cascade,
  constraint connected_oauth_secret_lifetime check (
    expires_at > created_at and expires_at <= created_at + interval '10 minutes'
  ),
  constraint connected_oauth_secret_status_shape check (
    (status = 'pending' and exchange_id is null and exchange_binding_sha256 is null
      and attempt_id is null and terminal_at is null
      and credential_handle_sha256 is null and external_account_id_hash is null
      and actual_scopes is null and actual_scopes_sha256 is null
      and grant_issued_at is null and grant_expires_at is null)
    or (status in ('attempt_fenced', 'ambiguous', 'deadline_expired')
      and exchange_id is not null and exchange_binding_sha256 is not null
      and attempt_id is not null and terminal_at is not null
      and credential_handle_sha256 is null and external_account_id_hash is null
      and actual_scopes is null and actual_scopes_sha256 is null
      and grant_issued_at is null and grant_expires_at is null)
    or (status = 'granted'
      and exchange_id is not null and exchange_binding_sha256 is not null
      and attempt_id is not null and terminal_at is not null
      and credential_handle_sha256 is not null
      and external_account_id_hash is not null
      and actual_scopes is not null and cardinality(actual_scopes) between 1 and 64
      and actual_scopes_sha256 is not null
      and grant_issued_at is not null and grant_expires_at > grant_issued_at)
    or status = 'erased'
  )
);
comment on table connected_app_private.oauth_secret_custody is
  'ASK_CRUMP_CONNECTED_OAUTH_SECRET_CUSTODY_V1_ENCRYPTED_STATE_PKCE_OR_HANDLE_ONLY';
create index if not exists connected_oauth_secret_owner_idx
  on connected_app_private.oauth_secret_custody(owner_id, connection_id, flow_id);
create unique index if not exists connected_oauth_secret_exchange_idx
  on connected_app_private.oauth_secret_custody(exchange_id)
  where exchange_id is not null;
create index if not exists connected_oauth_secret_expiry_idx
  on connected_app_private.oauth_secret_custody(expires_at, flow_id)
  where status in ('pending', 'attempt_fenced');

create table if not exists connected_app_private.oauth_secret_tombstones (
  flow_id uuid primary key,
  flow_binding_sha256 text not null check (flow_binding_sha256 ~ '^[0-9a-f]{64}$'),
  record_existed boolean not null,
  reason text not null check (reason in ('denied', 'expired', 'aborted', 'stale', 'owner_deleted', 'connection_deleted')),
  erased_at timestamptz not null
);
comment on table connected_app_private.oauth_secret_tombstones is
  'ASK_CRUMP_CONNECTED_OAUTH_SECRET_TOMBSTONES_V1_PERMANENT_CONTENT_FREE';

create table if not exists connected_app_private.oauth_provisional_credentials (
  provisional_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  connection_id uuid not null,
  connection_incarnation_id uuid not null,
  flow_id uuid not null,
  exchange_id uuid not null,
  provider text not null check (provider in ('google', 'microsoft')),
  account_kind text not null check (account_kind in ('personal', 'work_school')),
  status text not null check (status in ('provisional', 'quarantined')),
  credential_handle_sha256 text not null unique
    check (credential_handle_sha256 ~ '^[0-9a-f]{64}$'),
  oauth_client_id_sha256 text not null check (oauth_client_id_sha256 ~ '^[0-9a-f]{64}$'),
  external_account_id_hash text not null check (external_account_id_hash ~ '^[0-9a-f]{64}$'),
  granted_scopes text[] not null check (cardinality(granted_scopes) between 1 and 64),
  granted_scopes_sha256 text not null check (granted_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  exchange_binding_sha256 text not null check (exchange_binding_sha256 ~ '^[0-9a-f]{64}$'),
  issued_at timestamptz not null,
  expires_at timestamptz not null,
  authority_binding_sha256 text not null unique check (authority_binding_sha256 ~ '^[0-9a-f]{64}$'),
  key_id text not null check (key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  wrapped_key_nonce text not null check (wrapped_key_nonce ~ '^[A-Za-z0-9_-]{16}$'),
  wrapped_key_ciphertext text not null check (wrapped_key_ciphertext ~ '^[A-Za-z0-9_-]{64}$'),
  secret_nonce text not null check (secret_nonce ~ '^[A-Za-z0-9_-]{16}$'),
  secret_ciphertext text not null check (
    pg_catalog.length(secret_ciphertext) between 23 and 131072
    and secret_ciphertext ~ '^[A-Za-z0-9_-]+$'
  ),
  record_binding_sha256 text not null check (record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  constraint connected_oauth_provisional_owner_connection_fk
    foreign key (owner_id, connection_id)
    references connected_app_private.connections(owner_id, id)
    on delete cascade,
  constraint connected_oauth_provisional_lifetime check (expires_at > issued_at),
  constraint connected_oauth_provisional_quarantine_shape check (
    (status = 'provisional' and external_account_id_hash <> repeat('0', 64))
    or (status = 'quarantined' and external_account_id_hash = repeat('0', 64))
  )
);
comment on table connected_app_private.oauth_provisional_credentials is
  'ASK_CRUMP_CONNECTED_OAUTH_PROVISIONAL_CREDENTIALS_V1_ENCRYPTED_REFRESH_ONLY';
create index if not exists connected_oauth_provisional_owner_idx
  on connected_app_private.oauth_provisional_credentials(owner_id, connection_id, provisional_id);
create index if not exists connected_oauth_provisional_flow_idx
  on connected_app_private.oauth_provisional_credentials(flow_id, exchange_id);

create table if not exists connected_app_private.oauth_provisional_tombstones (
  credential_handle_sha256 text primary key
    check (credential_handle_sha256 ~ '^[0-9a-f]{64}$'),
  record_binding_sha256 text not null check (record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  record_existed boolean not null,
  erased_at timestamptz not null
);
comment on table connected_app_private.oauth_provisional_tombstones is
  'ASK_CRUMP_CONNECTED_OAUTH_PROVISIONAL_TOMBSTONES_V1_PERMANENT_CONTENT_FREE';

alter table connected_app_private.oauth_secret_custody enable row level security;
alter table connected_app_private.oauth_secret_custody force row level security;
alter table connected_app_private.oauth_secret_tombstones enable row level security;
alter table connected_app_private.oauth_secret_tombstones force row level security;
alter table connected_app_private.oauth_provisional_credentials enable row level security;
alter table connected_app_private.oauth_provisional_credentials force row level security;
alter table connected_app_private.oauth_provisional_tombstones enable row level security;
alter table connected_app_private.oauth_provisional_tombstones force row level security;

create or replace function connected_app_private.oauth_secret_flow_json_v1(
  p_row connected_app_private.oauth_secret_custody
) returns jsonb
language sql
immutable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'flow_id', p_row.flow_id, 'nonce_id', p_row.nonce_id,
    'owner_id', p_row.owner_id, 'connection_id', p_row.connection_id,
    'connection_incarnation_id', p_row.connection_incarnation_id,
    'expected_base_revision', p_row.expected_base_revision,
    'current_flow_nonce_sha256', p_row.current_flow_nonce_sha256,
    'session_binding_sha256', p_row.session_binding_sha256,
    'provider', p_row.provider, 'resource', p_row.resource,
    'account_kind', p_row.account_kind, 'actions', p_row.actions,
    'actions_sha256', p_row.actions_sha256,
    'requested_scopes', p_row.requested_scopes,
    'requested_scopes_sha256', p_row.requested_scopes_sha256,
    'state_sha256', p_row.state_sha256, 'pkce_challenge', p_row.pkce_challenge,
    'redirect_uri', p_row.redirect_uri, 'created_at', p_row.created_at,
    'expires_at', p_row.expires_at, 'flow_binding_sha256', p_row.flow_binding_sha256,
    'accepted_at', p_row.accepted_at, 'status', p_row.status,
    'exchange_id', p_row.exchange_id,
    'exchange_binding_sha256', p_row.exchange_binding_sha256,
    'attempt_id', p_row.attempt_id, 'terminal_at', p_row.terminal_at,
    'secret_key_id', p_row.secret_key_id,
    'secret_wrapped_key_nonce', p_row.secret_wrapped_key_nonce,
    'secret_wrapped_key_ciphertext', p_row.secret_wrapped_key_ciphertext,
    'secret_nonce', p_row.secret_nonce,
    'secret_ciphertext', p_row.secret_ciphertext,
    'secret_record_binding_sha256', p_row.secret_record_binding_sha256
  );
$fn$;

create or replace function connected_app_private.oauth_provisional_json_v1(
  p_row connected_app_private.oauth_provisional_credentials
) returns jsonb
language sql
immutable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'provisional_id', p_row.provisional_id, 'owner_id', p_row.owner_id,
    'connection_id', p_row.connection_id,
    'connection_incarnation_id', p_row.connection_incarnation_id,
    'flow_id', p_row.flow_id, 'exchange_id', p_row.exchange_id,
    'provider', p_row.provider, 'account_kind', p_row.account_kind,
    'status', p_row.status,
    'credential_handle_sha256', p_row.credential_handle_sha256,
    'oauth_client_id_sha256', p_row.oauth_client_id_sha256,
    'external_account_id_hash', p_row.external_account_id_hash,
    'granted_scopes', p_row.granted_scopes,
    'granted_scopes_sha256', p_row.granted_scopes_sha256,
    'exchange_binding_sha256', p_row.exchange_binding_sha256,
    'issued_at', p_row.issued_at, 'expires_at', p_row.expires_at,
    'key_id', p_row.key_id, 'wrapped_key_nonce', p_row.wrapped_key_nonce,
    'wrapped_key_ciphertext', p_row.wrapped_key_ciphertext,
    'secret_nonce', p_row.secret_nonce, 'secret_ciphertext', p_row.secret_ciphertext,
    'record_binding_sha256', p_row.record_binding_sha256
  );
$fn$;

create or replace function connected_app_private.oauth_secret_tombstone_before_delete_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
begin
  insert into connected_app_private.oauth_secret_tombstones (
    flow_id, flow_binding_sha256, record_existed, reason, erased_at
  ) values (
    old.flow_id, old.flow_binding_sha256, true, 'connection_deleted',
    pg_catalog.clock_timestamp()
  ) on conflict (flow_id) do update set record_existed = true
  where connected_app_private.oauth_secret_tombstones.flow_binding_sha256 = excluded.flow_binding_sha256;
  if not found then
    raise exception 'OAuth secret tombstone identity mismatch' using errcode = '55000';
  end if;
  return old;
end;
$fn$;

create or replace function connected_app_private.oauth_provisional_tombstone_before_delete_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
begin
  insert into connected_app_private.oauth_provisional_tombstones (
    credential_handle_sha256, record_binding_sha256, record_existed, erased_at
  ) values (
    old.credential_handle_sha256, old.record_binding_sha256, true,
    pg_catalog.clock_timestamp()
  ) on conflict (credential_handle_sha256) do update set record_existed = true
  where connected_app_private.oauth_provisional_tombstones.record_binding_sha256 = excluded.record_binding_sha256;
  if not found then
    raise exception 'OAuth provisional tombstone identity mismatch' using errcode = '55000';
  end if;
  return old;
end;
$fn$;

create or replace trigger connected_oauth_secret_tombstone_before_delete
before delete on connected_app_private.oauth_secret_custody
for each row execute function connected_app_private.oauth_secret_tombstone_before_delete_v1();
create or replace trigger connected_oauth_provisional_tombstone_before_delete
before delete on connected_app_private.oauth_provisional_credentials
for each row execute function connected_app_private.oauth_provisional_tombstone_before_delete_v1();

create or replace function public.connected_app_oauth_secret_begin_v1(
  p_flow_id uuid, p_nonce_id uuid, p_owner_id uuid, p_connection_id uuid,
  p_connection_incarnation_id uuid, p_expected_base_revision bigint,
  p_current_flow_nonce_sha256 text, p_session_binding_sha256 text,
  p_provider text, p_resource text, p_account_kind text,
  p_actions text[], p_actions_sha256 text,
  p_requested_scopes text[], p_requested_scopes_sha256 text,
  p_state_sha256 text, p_pkce_challenge text, p_redirect_uri text,
  p_created_at timestamptz, p_expires_at timestamptz,
  p_flow_binding_sha256 text, p_secret_key_id text,
  p_secret_wrapped_key_nonce text, p_secret_wrapped_key_ciphertext text,
  p_secret_nonce text, p_secret_ciphertext text,
  p_secret_record_binding_sha256 text
) returns jsonb
language plpgsql security definer set search_path = ''
as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  secret_row connected_app_private.oauth_secret_custody%rowtype;
begin
  if p_flow_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_secret_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_created_at >= p_expires_at
     or p_expires_at > p_created_at + interval '10 minutes' then
    raise exception 'invalid OAuth secret begin' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select * into connection_row from connected_app_private.connections
  where owner_id = p_owner_id and id = p_connection_id for update;
  if not found or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> p_connection_incarnation_id
     or connection_row.authorization_revision <> p_expected_base_revision
     or connection_row.current_flow_nonce_sha256
       <> p_current_flow_nonce_sha256
     or connection_row.provider <> p_provider
     or connection_row.resource <> p_resource
     or connection_row.account_kind <> p_account_kind then
    raise exception 'OAuth secret begin authority mismatch' using errcode = '55000';
  end if;
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id for update;
  if found then
    if secret_row.flow_binding_sha256 <> p_flow_binding_sha256
       or secret_row.secret_record_binding_sha256 <> p_secret_record_binding_sha256 then
      raise exception 'OAuth secret begin replay mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'status', 'present',
      'record', connected_app_private.oauth_secret_flow_json_v1(secret_row)
    );
  end if;
  if exists (select 1 from connected_app_private.oauth_secret_tombstones
             where flow_id = p_flow_id) then
    raise exception 'OAuth secret flow retired' using errcode = '55000';
  end if;
  insert into connected_app_private.oauth_secret_custody (
    flow_id, nonce_id, owner_id, connection_id, connection_incarnation_id,
    expected_base_revision, current_flow_nonce_sha256, session_binding_sha256,
    provider, resource, account_kind, actions, actions_sha256,
    requested_scopes, requested_scopes_sha256, state_sha256, pkce_challenge,
    redirect_uri, created_at, expires_at, flow_binding_sha256,
    secret_key_id, secret_wrapped_key_nonce, secret_wrapped_key_ciphertext,
    secret_nonce, secret_ciphertext, secret_record_binding_sha256
  ) values (
    p_flow_id, p_nonce_id, p_owner_id, p_connection_id, p_connection_incarnation_id,
    p_expected_base_revision, p_current_flow_nonce_sha256, p_session_binding_sha256,
    p_provider, p_resource, p_account_kind, p_actions, p_actions_sha256,
    p_requested_scopes, p_requested_scopes_sha256, p_state_sha256, p_pkce_challenge,
    p_redirect_uri, p_created_at, p_expires_at, p_flow_binding_sha256,
    p_secret_key_id, p_secret_wrapped_key_nonce, p_secret_wrapped_key_ciphertext,
    p_secret_nonce, p_secret_ciphertext, p_secret_record_binding_sha256
  ) returning * into secret_row;
  return pg_catalog.jsonb_build_object(
    'status', 'present',
    'record', connected_app_private.oauth_secret_flow_json_v1(secret_row)
  );
end;
$fn$;

create or replace function public.connected_app_oauth_secret_read_flow_v1(
  p_flow_id uuid, p_owner_id uuid, p_connection_id uuid,
  p_connection_incarnation_id uuid, p_expected_base_revision bigint,
  p_current_flow_nonce_sha256 text
) returns jsonb
language plpgsql security definer set search_path = ''
as $fn$
declare
  secret_row connected_app_private.oauth_secret_custody%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  if exists (select 1 from connected_app_private.oauth_secret_tombstones
             where flow_id = p_flow_id) then
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'absent', 'record', null);
  end if;
  if secret_row.owner_id <> p_owner_id or secret_row.connection_id <> p_connection_id
     or secret_row.connection_incarnation_id <> p_connection_incarnation_id
     or secret_row.expected_base_revision <> p_expected_base_revision
     or secret_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256 then
    raise exception 'OAuth secret read binding mismatch' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id
    and connection.id = p_connection_id
  for update;
  if not found
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id
       <> p_connection_incarnation_id
     or connection_row.authorization_revision <> p_expected_base_revision
     or connection_row.current_flow_nonce_sha256
       <> p_current_flow_nonce_sha256 then
    raise exception 'OAuth secret read authority mismatch' using errcode = '55000';
  end if;
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id for update;
  if not found then
    if exists (
      select 1 from connected_app_private.oauth_secret_tombstones
      where flow_id = p_flow_id
    ) then
      return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
    end if;
    return pg_catalog.jsonb_build_object('status', 'absent', 'record', null);
  end if;
  if secret_row.owner_id <> p_owner_id
     or secret_row.connection_id <> p_connection_id
     or secret_row.connection_incarnation_id <> p_connection_incarnation_id
     or secret_row.expected_base_revision <> p_expected_base_revision
     or secret_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256 then
    raise exception 'OAuth secret read binding changed' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'status', 'present',
    'record', connected_app_private.oauth_secret_flow_json_v1(secret_row)
  );
end;
$fn$;

create or replace function public.connected_app_oauth_secret_fence_v1(
  p_flow_id uuid, p_exchange_id uuid, p_exchange_binding_sha256 text,
  p_flow_binding_sha256 text, p_attempt_id uuid, p_deadline_at timestamptz
) returns jsonb
language plpgsql security definer set search_path = ''
as $fn$
declare
  secret_row connected_app_private.oauth_secret_custody%rowtype;
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
  next_status text;
begin
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id;
  if not found or secret_row.flow_binding_sha256 <> p_flow_binding_sha256 then
    raise exception 'OAuth secret fence binding mismatch' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(secret_row.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = secret_row.owner_id
    and connection.id = secret_row.connection_id
  for update;
  if not found
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id
       <> secret_row.connection_incarnation_id
     or connection_row.authorization_revision
       <> secret_row.expected_base_revision
     or connection_row.current_flow_nonce_sha256
       <> secret_row.current_flow_nonce_sha256 then
    raise exception 'OAuth secret fence authority mismatch' using errcode = '55000';
  end if;
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id for update;
  if not found or secret_row.flow_binding_sha256 <> p_flow_binding_sha256 then
    raise exception 'OAuth secret fence binding mismatch' using errcode = '55000';
  end if;
  if secret_row.status = 'pending' then
    next_status := case when now_at >= p_deadline_at or now_at >= secret_row.expires_at
      then 'deadline_expired' else 'attempt_fenced' end;
    update connected_app_private.oauth_secret_custody set
      status = next_status, exchange_id = p_exchange_id,
      exchange_binding_sha256 = p_exchange_binding_sha256,
      attempt_id = p_attempt_id, terminal_at = now_at
    where flow_id = p_flow_id returning * into secret_row;
    return pg_catalog.jsonb_build_object(
      'status', case when next_status = 'deadline_expired'
        then 'deadline_expired' else 'claimed' end,
      'flow_id', secret_row.flow_id, 'exchange_id', secret_row.exchange_id,
      'exchange_binding_sha256', secret_row.exchange_binding_sha256,
      'attempt_id', secret_row.attempt_id, 'recorded_at', secret_row.terminal_at,
      'fresh', true
    );
  end if;
  if secret_row.exchange_id <> p_exchange_id
     or secret_row.exchange_binding_sha256 <> p_exchange_binding_sha256 then
    raise exception 'OAuth secret exchange identity mismatch' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'status', case when secret_row.status = 'deadline_expired'
      then 'deadline_expired' else 'fenced' end,
    'flow_id', secret_row.flow_id, 'exchange_id', secret_row.exchange_id,
    'exchange_binding_sha256', secret_row.exchange_binding_sha256,
    'attempt_id', secret_row.attempt_id, 'recorded_at', secret_row.terminal_at,
    'fresh', secret_row.attempt_id = p_attempt_id
      and secret_row.status = 'attempt_fenced'
  );
end;
$fn$;

create or replace function public.connected_app_oauth_secret_grant_v1(
  p_flow_id uuid, p_exchange_id uuid, p_exchange_binding_sha256 text,
  p_attempt_id uuid, p_credential_handle_sha256 text,
  p_external_account_id_hash text, p_actual_scopes text[],
  p_actual_scopes_sha256 text, p_issued_at timestamptz, p_expires_at timestamptz,
  p_provisional_id uuid, p_oauth_client_id_sha256 text,
  p_provisional_binding_sha256 text,
  p_terminal_key_id text, p_terminal_wrapped_key_nonce text,
  p_terminal_wrapped_key_ciphertext text, p_terminal_secret_nonce text,
  p_terminal_secret_ciphertext text, p_terminal_record_binding_sha256 text,
  p_provisional_key_id text, p_provisional_wrapped_key_nonce text,
  p_provisional_wrapped_key_ciphertext text, p_provisional_secret_nonce text,
  p_provisional_secret_ciphertext text,
  p_provisional_record_binding_sha256 text
) returns jsonb
language plpgsql security definer set search_path = ''
as $fn$
declare
  secret_row connected_app_private.oauth_secret_custody%rowtype;
  provisional_row connected_app_private.oauth_provisional_credentials%rowtype;
  connection_row connected_app_private.connections%rowtype;
  result_record jsonb;
begin
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id;
  if not found or secret_row.exchange_id <> p_exchange_id
     or secret_row.exchange_binding_sha256 <> p_exchange_binding_sha256
     or secret_row.attempt_id <> p_attempt_id then
    raise exception 'OAuth secret grant binding mismatch' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(secret_row.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = secret_row.owner_id
    and connection.id = secret_row.connection_id
  for update;
  if not found
     or connection_row.connection_incarnation_id
       <> secret_row.connection_incarnation_id
     or connection_row.provider <> secret_row.provider
     or connection_row.resource <> secret_row.resource
     or connection_row.account_kind <> secret_row.account_kind then
    raise exception 'OAuth secret grant connection disappeared'
      using errcode = '55000';
  end if;
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id for update;
  if not found or secret_row.exchange_id <> p_exchange_id
     or secret_row.exchange_binding_sha256 <> p_exchange_binding_sha256
     or secret_row.attempt_id <> p_attempt_id then
    raise exception 'OAuth secret grant binding mismatch' using errcode = '55000';
  end if;
  if secret_row.status = 'granted' then
    select * into provisional_row
    from connected_app_private.oauth_provisional_credentials
    where credential_handle_sha256 = secret_row.credential_handle_sha256;
    if not found or provisional_row.record_binding_sha256
       <> p_provisional_record_binding_sha256
       or secret_row.secret_record_binding_sha256
       <> p_terminal_record_binding_sha256 then
      raise exception 'OAuth secret grant replay mismatch' using errcode = '55000';
    end if;
  else
    if secret_row.status <> 'attempt_fenced'
       or p_external_account_id_hash = repeat('0', 64)
       or p_actual_scopes is distinct from secret_row.requested_scopes
       or p_actual_scopes_sha256
         is distinct from secret_row.requested_scopes_sha256
       or p_expires_at <= p_issued_at
       or exists (select 1 from connected_app_private.oauth_provisional_tombstones
                  where credential_handle_sha256 = p_credential_handle_sha256) then
      raise exception 'OAuth secret grant is not activatable' using errcode = '55000';
    end if;
    insert into connected_app_private.oauth_provisional_credentials (
      provisional_id, owner_id, connection_id, connection_incarnation_id,
      flow_id, exchange_id, provider, account_kind, status,
      credential_handle_sha256, oauth_client_id_sha256,
      external_account_id_hash, granted_scopes, granted_scopes_sha256,
      exchange_binding_sha256, issued_at, expires_at, authority_binding_sha256,
      key_id, wrapped_key_nonce, wrapped_key_ciphertext, secret_nonce,
      secret_ciphertext, record_binding_sha256
    ) values (
      p_provisional_id, secret_row.owner_id, secret_row.connection_id,
      secret_row.connection_incarnation_id, secret_row.flow_id, p_exchange_id,
      secret_row.provider, secret_row.account_kind, 'provisional',
      p_credential_handle_sha256, p_oauth_client_id_sha256,
      p_external_account_id_hash, p_actual_scopes, p_actual_scopes_sha256,
      p_exchange_binding_sha256, p_issued_at, p_expires_at,
      p_provisional_binding_sha256, p_provisional_key_id,
      p_provisional_wrapped_key_nonce, p_provisional_wrapped_key_ciphertext,
      p_provisional_secret_nonce, p_provisional_secret_ciphertext,
      p_provisional_record_binding_sha256
    ) returning * into provisional_row;
    update connected_app_private.oauth_secret_custody set
      status = 'granted', terminal_at = pg_catalog.clock_timestamp(),
      credential_handle_sha256 = p_credential_handle_sha256,
      external_account_id_hash = p_external_account_id_hash,
      actual_scopes = p_actual_scopes,
      actual_scopes_sha256 = p_actual_scopes_sha256,
      grant_issued_at = p_issued_at, grant_expires_at = p_expires_at,
      secret_key_id = p_terminal_key_id,
      secret_wrapped_key_nonce = p_terminal_wrapped_key_nonce,
      secret_wrapped_key_ciphertext = p_terminal_wrapped_key_ciphertext,
      secret_nonce = p_terminal_secret_nonce,
      secret_ciphertext = p_terminal_secret_ciphertext,
      secret_record_binding_sha256 = p_terminal_record_binding_sha256
    where flow_id = p_flow_id returning * into secret_row;
  end if;
  result_record := pg_catalog.jsonb_build_object(
    'flow', connected_app_private.oauth_secret_flow_json_v1(secret_row),
    'credential_handle_sha256', secret_row.credential_handle_sha256,
    'external_account_id_hash', secret_row.external_account_id_hash,
    'actual_scopes', secret_row.actual_scopes,
    'issued_at', secret_row.grant_issued_at,
    'expires_at', secret_row.grant_expires_at,
    'provisional', connected_app_private.oauth_provisional_json_v1(provisional_row)
  );
  return pg_catalog.jsonb_build_object('status', 'granted', 'record', result_record);
end;
$fn$;

create or replace function public.connected_app_oauth_secret_ambiguous_v1(
  p_flow_id uuid, p_exchange_id uuid, p_exchange_binding_sha256 text,
  p_attempt_id uuid, p_observed_at timestamptz, p_quarantine boolean,
  p_provisional_id uuid default null, p_credential_handle_sha256 text default null,
  p_oauth_client_id_sha256 text default null,
  p_external_account_id_hash text default null,
  p_actual_scopes text[] default null, p_actual_scopes_sha256 text default null,
  p_issued_at timestamptz default null, p_expires_at timestamptz default null,
  p_provisional_binding_sha256 text default null,
  p_provisional_key_id text default null,
  p_provisional_wrapped_key_nonce text default null,
  p_provisional_wrapped_key_ciphertext text default null,
  p_provisional_secret_nonce text default null,
  p_provisional_secret_ciphertext text default null,
  p_provisional_record_binding_sha256 text default null
) returns jsonb
language plpgsql security definer set search_path = ''
as $fn$
declare
  secret_row connected_app_private.oauth_secret_custody%rowtype;
  provisional_row connected_app_private.oauth_provisional_credentials%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  if p_quarantine and (
       p_provisional_id is null or p_credential_handle_sha256 is null
       or p_oauth_client_id_sha256 is null
       or p_external_account_id_hash is null
       or p_external_account_id_hash <> repeat('0', 64)
       or p_actual_scopes is null or p_actual_scopes_sha256 is null
       or p_issued_at is null or p_expires_at is null
       or p_expires_at <= p_issued_at
       or p_provisional_binding_sha256 is null
       or p_provisional_key_id is null
       or p_provisional_wrapped_key_nonce is null
       or p_provisional_wrapped_key_ciphertext is null
       or p_provisional_secret_nonce is null
       or p_provisional_secret_ciphertext is null
       or p_provisional_record_binding_sha256 is null
     ) then
    raise exception 'OAuth ambiguous quarantine is incomplete'
      using errcode = '22023';
  elsif not p_quarantine and (
       p_provisional_id is not null or p_credential_handle_sha256 is not null
       or p_oauth_client_id_sha256 is not null
       or p_external_account_id_hash is not null
       or p_actual_scopes is not null or p_actual_scopes_sha256 is not null
       or p_issued_at is not null or p_expires_at is not null
       or p_provisional_binding_sha256 is not null
       or p_provisional_key_id is not null
       or p_provisional_wrapped_key_nonce is not null
       or p_provisional_wrapped_key_ciphertext is not null
       or p_provisional_secret_nonce is not null
       or p_provisional_secret_ciphertext is not null
       or p_provisional_record_binding_sha256 is not null
     ) then
    raise exception 'OAuth ambiguous quarantine shape drifted'
      using errcode = '22023';
  end if;
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id;
  if not found or secret_row.exchange_id <> p_exchange_id
     or secret_row.exchange_binding_sha256 <> p_exchange_binding_sha256
     or secret_row.attempt_id <> p_attempt_id then
    raise exception 'OAuth ambiguous binding mismatch' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(secret_row.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = secret_row.owner_id
    and connection.id = secret_row.connection_id
  for update;
  if not found
     or connection_row.connection_incarnation_id
       <> secret_row.connection_incarnation_id
     or connection_row.provider <> secret_row.provider
     or connection_row.resource <> secret_row.resource
     or connection_row.account_kind <> secret_row.account_kind then
    raise exception 'OAuth ambiguous connection disappeared'
      using errcode = '55000';
  end if;
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id for update;
  if not found or secret_row.exchange_id <> p_exchange_id
     or secret_row.exchange_binding_sha256 <> p_exchange_binding_sha256
     or secret_row.attempt_id <> p_attempt_id
     or secret_row.status not in ('attempt_fenced', 'ambiguous') then
    raise exception 'OAuth ambiguous binding mismatch' using errcode = '55000';
  end if;
  if secret_row.status = 'attempt_fenced' then
    if p_quarantine then
      if p_actual_scopes is distinct from secret_row.requested_scopes
         or p_actual_scopes_sha256
           is distinct from secret_row.requested_scopes_sha256 then
        raise exception 'OAuth ambiguous quarantine scope mismatch'
          using errcode = '55000';
      end if;
      insert into connected_app_private.oauth_provisional_credentials (
        provisional_id, owner_id, connection_id, connection_incarnation_id,
        flow_id, exchange_id, provider, account_kind, status,
        credential_handle_sha256, oauth_client_id_sha256,
        external_account_id_hash, granted_scopes, granted_scopes_sha256,
        exchange_binding_sha256, issued_at, expires_at, authority_binding_sha256,
        key_id, wrapped_key_nonce, wrapped_key_ciphertext, secret_nonce,
        secret_ciphertext, record_binding_sha256
      ) values (
        p_provisional_id, secret_row.owner_id, secret_row.connection_id,
        secret_row.connection_incarnation_id, secret_row.flow_id, p_exchange_id,
        secret_row.provider, secret_row.account_kind, 'quarantined',
        p_credential_handle_sha256, p_oauth_client_id_sha256,
        repeat('0', 64), p_actual_scopes, p_actual_scopes_sha256,
        p_exchange_binding_sha256, p_issued_at, p_expires_at,
        p_provisional_binding_sha256, p_provisional_key_id,
        p_provisional_wrapped_key_nonce, p_provisional_wrapped_key_ciphertext,
        p_provisional_secret_nonce, p_provisional_secret_ciphertext,
        p_provisional_record_binding_sha256
      );
    end if;
    update connected_app_private.oauth_secret_custody set
      status = 'ambiguous', terminal_at = p_observed_at
    where flow_id = p_flow_id returning * into secret_row;
  elsif p_quarantine then
    select * into provisional_row
    from connected_app_private.oauth_provisional_credentials
    where credential_handle_sha256 = p_credential_handle_sha256;
    if not found
       or provisional_row.status <> 'quarantined'
       or provisional_row.flow_id <> p_flow_id
       or provisional_row.exchange_id <> p_exchange_id
       or provisional_row.record_binding_sha256
         <> p_provisional_record_binding_sha256 then
      raise exception 'OAuth ambiguous quarantine replay mismatch'
        using errcode = '55000';
    end if;
  end if;
  return pg_catalog.jsonb_build_object(
    'status', 'ambiguous', 'exchange_id', secret_row.exchange_id,
    'exchange_binding_sha256', secret_row.exchange_binding_sha256,
    'observed_at', secret_row.terminal_at
  );
end;
$fn$;

create or replace function public.connected_app_oauth_secret_read_exchange_v1(
  p_flow_id uuid, p_exchange_id uuid, p_exchange_binding_sha256 text
) returns jsonb
language plpgsql stable security definer set search_path = ''
as $fn$
declare
  secret_row connected_app_private.oauth_secret_custody%rowtype;
  provisional_row connected_app_private.oauth_provisional_credentials%rowtype;
  result_record jsonb;
begin
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id;
  if not found or secret_row.status = 'pending' then
    return pg_catalog.jsonb_build_object('status', 'absent', 'record', null);
  end if;
  if secret_row.exchange_id <> p_exchange_id
     or secret_row.exchange_binding_sha256 <> p_exchange_binding_sha256 then
    raise exception 'OAuth exchange read binding mismatch' using errcode = '55000';
  end if;
  if secret_row.status = 'granted' then
    select * into provisional_row
    from connected_app_private.oauth_provisional_credentials
    where credential_handle_sha256 = secret_row.credential_handle_sha256;
    if not found then
      -- Activation erased the provisional refresh token, but the encrypted
      -- terminal handle remains sufficient for exchange-terminal recovery.
      select * into provisional_row
      from connected_app_private.oauth_provisional_credentials where false;
    end if;
    result_record := pg_catalog.jsonb_build_object(
      'flow', connected_app_private.oauth_secret_flow_json_v1(secret_row),
      'credential_handle_sha256', secret_row.credential_handle_sha256,
      'external_account_id_hash', secret_row.external_account_id_hash,
      'actual_scopes', secret_row.actual_scopes,
      'issued_at', secret_row.grant_issued_at,
      'expires_at', secret_row.grant_expires_at,
      'provisional', case when provisional_row.provisional_id is null
        then null else connected_app_private.oauth_provisional_json_v1(provisional_row) end
    );
    return pg_catalog.jsonb_build_object('status', 'granted', 'record', result_record);
  end if;
  return pg_catalog.jsonb_build_object(
    'status', secret_row.status,
    'record', pg_catalog.jsonb_build_object(
      'exchange_id', secret_row.exchange_id,
      'exchange_binding_sha256', secret_row.exchange_binding_sha256,
      'recorded_at', secret_row.terminal_at
    )
  );
end;
$fn$;

create or replace function public.connected_app_oauth_provisional_read_v1(
  p_credential_handle_sha256 text
) returns jsonb
language plpgsql stable security definer set search_path = ''
as $fn$
declare provisional_row connected_app_private.oauth_provisional_credentials%rowtype;
begin
  if exists (select 1 from connected_app_private.oauth_provisional_tombstones
             where credential_handle_sha256 = p_credential_handle_sha256) then
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  select * into provisional_row
  from connected_app_private.oauth_provisional_credentials
  where credential_handle_sha256 = p_credential_handle_sha256;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'absent', 'record', null);
  end if;
  return pg_catalog.jsonb_build_object(
    'status', provisional_row.status,
    'record', connected_app_private.oauth_provisional_json_v1(provisional_row)
  );
end;
$fn$;

create or replace function public.connected_app_oauth_provisional_erase_v1(
  p_credential_handle_sha256 text,
  p_expected_record_binding_sha256 text
) returns jsonb
language plpgsql security definer set search_path = ''
as $fn$
declare
  provisional_row connected_app_private.oauth_provisional_credentials%rowtype;
  tombstone_row connected_app_private.oauth_provisional_tombstones%rowtype;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-oauth-provisional:' || p_credential_handle_sha256, 0)
  );
  select * into tombstone_row
  from connected_app_private.oauth_provisional_tombstones
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if found then
    if tombstone_row.record_binding_sha256 <> p_expected_record_binding_sha256 then
      raise exception 'OAuth provisional erase replay mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'status', 'erased', 'record_existed', tombstone_row.record_existed
    );
  end if;
  select * into provisional_row
  from connected_app_private.oauth_provisional_credentials
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if found and provisional_row.record_binding_sha256
     <> p_expected_record_binding_sha256 then
    raise exception 'OAuth provisional erase CAS mismatch' using errcode = '55000';
  end if;
  insert into connected_app_private.oauth_provisional_tombstones (
    credential_handle_sha256, record_binding_sha256, record_existed, erased_at
  ) values (
    p_credential_handle_sha256, p_expected_record_binding_sha256, found,
    pg_catalog.clock_timestamp()
  ) returning * into tombstone_row;
  if found then
    delete from connected_app_private.oauth_provisional_credentials
    where credential_handle_sha256 = p_credential_handle_sha256;
  end if;
  return pg_catalog.jsonb_build_object(
    'status', 'erased', 'record_existed', tombstone_row.record_existed
  );
end;
$fn$;

create or replace function public.connected_app_oauth_secret_abort_v1(
  p_flow_id uuid, p_flow_binding_sha256 text, p_reason text
) returns jsonb
language plpgsql security definer set search_path = ''
as $fn$
declare
  secret_row connected_app_private.oauth_secret_custody%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  if p_reason not in ('denied', 'expired', 'aborted', 'stale') then
    raise exception 'invalid OAuth secret abort reason' using errcode = '22023';
  end if;
  select * into secret_row from connected_app_private.oauth_secret_custody
  where flow_id = p_flow_id;
  if found and secret_row.flow_binding_sha256 <> p_flow_binding_sha256 then
    raise exception 'OAuth secret abort binding mismatch' using errcode = '55000';
  end if;
  if found then
    perform connected_app_private.owner_lock_v1(secret_row.owner_id);
    select connection.* into connection_row
    from connected_app_private.connections as connection
    where connection.owner_id = secret_row.owner_id
      and connection.id = secret_row.connection_id
    for update;
    if not found then
      if exists (
        select 1 from connected_app_private.oauth_secret_tombstones
        where flow_id = p_flow_id
          and flow_binding_sha256 = p_flow_binding_sha256
      ) then
        return pg_catalog.jsonb_build_object('status', 'erased');
      end if;
      raise exception 'OAuth secret abort connection disappeared'
        using errcode = '55000';
    end if;
    select * into secret_row from connected_app_private.oauth_secret_custody
    where flow_id = p_flow_id for update;
    if not found then
      if exists (
        select 1 from connected_app_private.oauth_secret_tombstones
        where flow_id = p_flow_id
          and flow_binding_sha256 = p_flow_binding_sha256
      ) then
        return pg_catalog.jsonb_build_object('status', 'erased');
      end if;
      raise exception 'OAuth secret abort record disappeared'
        using errcode = '55000';
    end if;
    if secret_row.flow_binding_sha256 <> p_flow_binding_sha256 then
      raise exception 'OAuth secret abort binding changed' using errcode = '55000';
    end if;
  end if;
  insert into connected_app_private.oauth_secret_tombstones (
    flow_id, flow_binding_sha256, record_existed, reason, erased_at
  ) values (
    p_flow_id, p_flow_binding_sha256, found, p_reason,
    pg_catalog.clock_timestamp()
  ) on conflict (flow_id) do update set record_existed =
    connected_app_private.oauth_secret_tombstones.record_existed or excluded.record_existed
  where connected_app_private.oauth_secret_tombstones.flow_binding_sha256 = excluded.flow_binding_sha256;
  if not found then
    raise exception 'OAuth secret abort replay mismatch' using errcode = '55000';
  end if;
  if secret_row.flow_id is not null then
    -- Denial/expiry/abort also retires any provisional or quarantined refresh
    -- material created after a provider exchange.  The delete trigger installs
    -- a permanent handle+binding tombstone before ciphertext is removed.
    delete from connected_app_private.oauth_provisional_credentials
    where flow_id = p_flow_id;
    delete from connected_app_private.oauth_secret_custody where flow_id = p_flow_id;
  end if;
  return pg_catalog.jsonb_build_object('status', 'erased');
end;
$fn$;

do $acl$
declare object_row record; role_name text; signature text;
begin
  for object_row in
    select class_row.relname from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname in (
        'oauth_secret_custody', 'oauth_secret_tombstones',
        'oauth_provisional_credentials', 'oauth_provisional_tombstones'
      )
  loop
    execute pg_catalog.format(
      'alter table connected_app_private.%I owner to postgres', object_row.relname
    );
    execute pg_catalog.format(
      'revoke all on table connected_app_private.%I from public', object_row.relname
    );
    for role_name in select rolname from pg_catalog.pg_roles where rolname <> 'postgres'
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
      and (proc_row.proname like 'connected_app_oauth_secret_%'
        or proc_row.proname like 'connected_app_oauth_provisional_%'))
      or (namespace_row.nspname = 'connected_app_private'
        and proc_row.proname in (
          'oauth_secret_flow_json_v1', 'oauth_provisional_json_v1',
          'oauth_secret_tombstone_before_delete_v1',
          'oauth_provisional_tombstone_before_delete_v1'
        ))
  loop
    signature := pg_catalog.format(
      '%I.%I(%s)', object_row.nspname, object_row.proname, object_row.arguments
    );
    execute 'alter function ' || signature || ' owner to postgres';
    execute 'revoke all on function ' || signature || ' from public';
    for role_name in select rolname from pg_catalog.pg_roles where rolname <> 'postgres'
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
declare relation_names text[]; function_names text[]; object_row record;
begin
  select pg_catalog.array_agg(
    class_row.relname order by class_row.relname collate pg_catalog."C")
  into relation_names
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_app_private'
    and class_row.relname in (
      'oauth_secret_custody', 'oauth_secret_tombstones',
      'oauth_provisional_credentials', 'oauth_provisional_tombstones'
    );
  if relation_names is distinct from array[
    'oauth_provisional_credentials', 'oauth_provisional_tombstones',
    'oauth_secret_custody', 'oauth_secret_tombstones'
  ]::text[] then
    raise exception 'OAuth secret relation manifest drifted' using errcode = '55000';
  end if;
  select pg_catalog.array_agg(
    proc_row.proname order by proc_row.proname collate pg_catalog."C")
  into function_names
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and (proc_row.proname like 'connected_app_oauth_secret_%'
      or proc_row.proname like 'connected_app_oauth_provisional_%');
  if function_names is distinct from array[
    'connected_app_oauth_provisional_erase_v1',
    'connected_app_oauth_provisional_read_v1',
    'connected_app_oauth_secret_abort_v1',
    'connected_app_oauth_secret_ambiguous_v1',
    'connected_app_oauth_secret_begin_v1',
    'connected_app_oauth_secret_fence_v1',
    'connected_app_oauth_secret_grant_v1',
    'connected_app_oauth_secret_read_exchange_v1',
    'connected_app_oauth_secret_read_flow_v1'
  ]::text[] then
    raise exception 'OAuth secret RPC manifest drifted' using errcode = '55000';
  end if;
  for object_row in
    select class_row.oid, class_row.relname, class_row.relowner,
      class_row.relrowsecurity, class_row.relforcerowsecurity
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname = any(relation_names)
  loop
    if pg_catalog.pg_get_userbyid(object_row.relowner) <> 'postgres'
       or not object_row.relrowsecurity or not object_row.relforcerowsecurity
       or exists (
         select 1 from pg_catalog.aclexplode(coalesce(
           (select relacl from pg_catalog.pg_class where oid = object_row.oid),
           pg_catalog.acldefault('r', object_row.relowner)
         )) as acl_row where acl_row.grantee <> object_row.relowner
       ) then
      raise exception 'OAuth secret table authority drifted: %', object_row.relname
        using errcode = '55000';
    end if;
  end loop;
  for object_row in
    select proc_row.oid, proc_row.proname, proc_row.proowner,
      proc_row.prosecdef, proc_row.proconfig
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname = any(function_names)
  loop
    if pg_catalog.pg_get_userbyid(object_row.proowner) <> 'postgres'
       or not object_row.prosecdef
       or object_row.proconfig is distinct from array['search_path=""']::text[]
       or not exists (
         select 1 from pg_catalog.aclexplode(coalesce(
           (select proacl from pg_catalog.pg_proc where oid = object_row.oid),
           pg_catalog.acldefault('f', object_row.proowner)
         )) as acl_row
         where acl_row.grantee = (
           select oid from pg_catalog.pg_roles where rolname = 'service_role'
         ) and acl_row.privilege_type = 'EXECUTE'
       ) then
      raise exception 'OAuth secret RPC authority drifted: %', object_row.proname
        using errcode = '55000';
    end if;
  end loop;
  if exists (
    select 1 from pg_catalog.pg_policy as policy_row
    join pg_catalog.pg_class as class_row on class_row.oid = policy_row.polrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname = any(relation_names)
  ) or exists (select 1 from pg_catalog.pg_publication where puballtables)
  or exists (
    select 1 from pg_catalog.pg_publication_rel as publication_relation
    join pg_catalog.pg_class as class_row on class_row.oid = publication_relation.prrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname = any(relation_names)
  ) then
    raise exception 'OAuth secret exposure drifted' using errcode = '55000';
  end if;
end;
$postflight$;

commit;

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
