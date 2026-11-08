begin;

set local search_path = pg_catalog, public;
set local quote_all_identifiers = off;

-- Pin the entire reviewed post-63000 connected-operator catalog, while
-- deliberately excluding only this migration's own target objects.  Runtime
-- rows are not part of the digest; immutable action-authority seed rows are.
create or replace function pg_temp.connected_oauth_operator_predecessor_fingerprint()
returns text
language sql
stable
set search_path = ''
as $fingerprint$
  select pg_catalog.md5(pg_catalog.jsonb_build_object(
    'schemas', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname,
        pg_catalog.pg_get_userbyid(namespace_row.nspowner),
        namespace_row.nspacl::text,
        pg_catalog.obj_description(namespace_row.oid, 'pg_namespace')
      ) order by namespace_row.nspname collate pg_catalog."C")
      from pg_catalog.pg_namespace namespace_row
      where namespace_row.nspname in (
        'connected_app_private', 'connected_plan_private'
      )
    ),
    'relations', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, class_row.relname, class_row.relkind,
        class_row.relpersistence, coalesce(relation_access_method.amname, ''),
        coalesce(relation_tablespace.spcname, ''),
        class_row.relreplident, class_row.reloptions,
        pg_catalog.pg_get_userbyid(class_row.relowner),
        class_row.relrowsecurity, class_row.relforcerowsecurity,
        class_row.relacl::text,
        case when class_row.relkind in ('v', 'm')
          then pg_catalog.pg_get_viewdef(class_row.oid, true) else null end,
        pg_catalog.obj_description(class_row.oid, 'pg_class')
      ) order by namespace_row.nspname collate pg_catalog."C",
        class_row.relname collate pg_catalog."C")
      from pg_catalog.pg_class class_row
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      left join pg_catalog.pg_am relation_access_method
        on relation_access_method.oid = class_row.relam
      left join pg_catalog.pg_tablespace relation_tablespace
        on relation_tablespace.oid = class_row.reltablespace
      where namespace_row.nspname in (
          'connected_app_private', 'connected_plan_private'
        )
        and class_row.relname not in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
        and not exists (
          select 1
          from pg_catalog.pg_index target_index
          join pg_catalog.pg_class target_table
            on target_table.oid = target_index.indrelid
          where target_index.indexrelid = class_row.oid
            and target_table.relname in (
              'oauth_operator_starts', 'oauth_callback_requests'
            )
        )
    ),
    'columns', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, class_row.relname,
        attribute_row.attnum, attribute_row.attname,
        pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod),
        attribute_row.attnotnull, attribute_row.attidentity,
        attribute_row.attgenerated, attribute_row.attcompression,
        attribute_row.attstorage, attribute_row.attstattarget,
        attribute_row.atthasmissing, attribute_row.attmissingval,
        attribute_row.attinhcount, attribute_row.attislocal,
        attribute_row.attacl::text,
        coalesce(collation_namespace.nspname || '.', '')
          || coalesce(collation_row.collname, ''),
        pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid),
        pg_catalog.col_description(
          attribute_row.attrelid, attribute_row.attnum
        )
      ) order by namespace_row.nspname collate pg_catalog."C",
        class_row.relname collate pg_catalog."C",
        attribute_row.attnum)
      from pg_catalog.pg_attribute attribute_row
      join pg_catalog.pg_class class_row
        on class_row.oid = attribute_row.attrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      left join pg_catalog.pg_attrdef default_row
        on default_row.adrelid = attribute_row.attrelid
       and default_row.adnum = attribute_row.attnum
      left join pg_catalog.pg_collation collation_row
        on collation_row.oid = attribute_row.attcollation
      left join pg_catalog.pg_namespace collation_namespace
        on collation_namespace.oid = collation_row.collnamespace
      where namespace_row.nspname in (
          'connected_app_private', 'connected_plan_private'
        )
        and class_row.relname not in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
        and not exists (
          select 1
          from pg_catalog.pg_index target_index
          join pg_catalog.pg_class target_table
            on target_table.oid = target_index.indrelid
          where target_index.indexrelid = class_row.oid
            and target_table.relname in (
              'oauth_operator_starts', 'oauth_callback_requests'
            )
        )
        and attribute_row.attnum > 0 and not attribute_row.attisdropped
    ),
    'constraints', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, class_row.relname,
        constraint_row.conname, constraint_row.contype,
        constraint_row.condeferrable, constraint_row.condeferred,
        constraint_row.convalidated, constraint_row.connoinherit,
        pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
      ) order by namespace_row.nspname collate pg_catalog."C",
        class_row.relname collate pg_catalog."C",
        constraint_row.conname collate pg_catalog."C")
      from pg_catalog.pg_constraint constraint_row
      join pg_catalog.pg_class class_row
        on class_row.oid = constraint_row.conrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname in (
          'connected_app_private', 'connected_plan_private'
        )
        and class_row.relname not in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
    ),
    'indexes', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, table_row.relname, index_row.relname,
        index_row.relpersistence, coalesce(index_access_method.amname, ''),
        coalesce(index_tablespace.spcname, ''),
        index_row.reloptions, pg_catalog.pg_get_userbyid(index_row.relowner),
        index_link.indisunique, index_link.indisprimary,
        index_link.indisexclusion, index_link.indimmediate,
        index_link.indisclustered, index_link.indisvalid,
        index_link.indcheckxmin, index_link.indisready,
        index_link.indislive, index_link.indisreplident,
        index_link.indnkeyatts, index_link.indnatts,
        index_link.indnullsnotdistinct, index_link.indkey::text,
        (
          select pg_catalog.array_agg(
            coalesce(index_collation_namespace.nspname || '.', '')
              || coalesce(index_collation_row.collname, '')
            order by index_collation.position
          )::text
          from pg_catalog.unnest(index_link.indcollation::oid[])
            with ordinality as index_collation(collation_oid, position)
          left join pg_catalog.pg_collation index_collation_row
            on index_collation_row.oid = index_collation.collation_oid
          left join pg_catalog.pg_namespace index_collation_namespace
            on index_collation_namespace.oid = index_collation_row.collnamespace
        ),
        (
          select pg_catalog.array_agg(
            coalesce(index_opclass_namespace.nspname || '.', '')
              || coalesce(index_opclass_row.opcname, '')
            order by index_opclass.position
          )::text
          from pg_catalog.unnest(index_link.indclass::oid[])
            with ordinality as index_opclass(opclass_oid, position)
          left join pg_catalog.pg_opclass index_opclass_row
            on index_opclass_row.oid = index_opclass.opclass_oid
          left join pg_catalog.pg_namespace index_opclass_namespace
            on index_opclass_namespace.oid = index_opclass_row.opcnamespace
        ),
        index_link.indoption::text,
        pg_catalog.pg_get_indexdef(index_row.oid)
      ) order by namespace_row.nspname collate pg_catalog."C",
        table_row.relname collate pg_catalog."C",
        index_row.relname collate pg_catalog."C")
      from pg_catalog.pg_index index_link
      join pg_catalog.pg_class table_row
        on table_row.oid = index_link.indrelid
      join pg_catalog.pg_class index_row
        on index_row.oid = index_link.indexrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = table_row.relnamespace
      left join pg_catalog.pg_am index_access_method
        on index_access_method.oid = index_row.relam
      left join pg_catalog.pg_tablespace index_tablespace
        on index_tablespace.oid = index_row.reltablespace
      where namespace_row.nspname in (
          'connected_app_private', 'connected_plan_private'
        )
        and table_row.relname not in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
    ),
    'sequences', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, class_row.relname,
        pg_catalog.format_type(sequence_row.seqtypid, null),
        sequence_row.seqstart, sequence_row.seqincrement,
        sequence_row.seqmax, sequence_row.seqmin,
        sequence_row.seqcache, sequence_row.seqcycle,
        pg_catalog.pg_get_serial_sequence(
          dependency_namespace.nspname || '.' || dependency_table.relname,
          dependency_attribute.attname
        )
      ) order by namespace_row.nspname collate pg_catalog."C",
        class_row.relname collate pg_catalog."C")
      from pg_catalog.pg_sequence sequence_row
      join pg_catalog.pg_class class_row on class_row.oid = sequence_row.seqrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      left join pg_catalog.pg_depend dependency_row
        on dependency_row.classid = 'pg_catalog.pg_class'::regclass
       and dependency_row.objid = class_row.oid
       and dependency_row.deptype in ('a', 'i')
      left join pg_catalog.pg_class dependency_table
        on dependency_table.oid = dependency_row.refobjid
      left join pg_catalog.pg_namespace dependency_namespace
        on dependency_namespace.oid = dependency_table.relnamespace
      left join pg_catalog.pg_attribute dependency_attribute
        on dependency_attribute.attrelid = dependency_row.refobjid
       and dependency_attribute.attnum = dependency_row.refobjsubid
      where namespace_row.nspname in (
        'connected_app_private', 'connected_plan_private'
      )
    ),
    'types', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, type_row.typname, type_row.typtype,
        type_row.typcategory, type_row.typispreferred,
        type_row.typnotnull,
        case when type_row.typbasetype = 0 then ''
          else pg_catalog.format_type(type_row.typbasetype, type_row.typtypmod) end,
        type_row.typtypmod,
        coalesce(type_collation_namespace.nspname || '.', '')
          || coalesce(type_collation_row.collname, ''),
        type_row.typdefaultbin, type_row.typdefault,
        pg_catalog.pg_get_userbyid(type_row.typowner), type_row.typacl::text,
        pg_catalog.obj_description(type_row.oid, 'pg_type')
      ) order by namespace_row.nspname collate pg_catalog."C",
        type_row.typname collate pg_catalog."C")
      from pg_catalog.pg_type type_row
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = type_row.typnamespace
      left join pg_catalog.pg_collation type_collation_row
        on type_collation_row.oid = type_row.typcollation
      left join pg_catalog.pg_namespace type_collation_namespace
        on type_collation_namespace.oid = type_collation_row.collnamespace
      where namespace_row.nspname in (
          'connected_app_private', 'connected_plan_private'
        )
        and type_row.typname not in (
          'oauth_operator_starts', '_oauth_operator_starts',
          'oauth_callback_requests', '_oauth_callback_requests'
        )
    ),
    'functions', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, proc_row.proname,
        pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
        pg_catalog.pg_get_userbyid(proc_row.proowner), proc_row.prosecdef,
        proc_row.proleakproof, proc_row.proisstrict, proc_row.proretset,
        proc_row.provolatile, proc_row.proparallel,
        proc_row.procost, proc_row.prorows, language_row.lanname,
        proc_row.proconfig, proc_row.proacl::text,
        pg_catalog.obj_description(proc_row.oid, 'pg_proc'),
        pg_catalog.pg_get_functiondef(proc_row.oid)
      ) order by namespace_row.nspname collate pg_catalog."C",
        proc_row.proname collate pg_catalog."C",
        pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
          collate pg_catalog."C")
      from pg_catalog.pg_proc proc_row
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = proc_row.pronamespace
      join pg_catalog.pg_language language_row
        on language_row.oid = proc_row.prolang
      where (
          namespace_row.nspname in (
            'connected_app_private', 'connected_plan_private'
          )
          or (
            namespace_row.nspname = 'public'
            and proc_row.proname like 'connected\_app\_%' escape '\'
          )
        )
        and proc_row.proname not in (
          'connected_app_operator_prepare_oauth_start_v1',
          'connected_app_operator_read_oauth_start_v1',
          'connected_app_operator_prepare_oauth_callback_v1',
          'connected_app_operator_accept_oauth_callback_v1',
          'connected_app_operator_read_oauth_callback_v1',
          'oauth_operator_target_fingerprint_v1'
        )
    ),
    'triggers', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, class_row.relname, trigger_row.tgname,
        trigger_row.tgenabled,
        pg_catalog.pg_get_triggerdef(trigger_row.oid, true)
      ) order by namespace_row.nspname collate pg_catalog."C",
        class_row.relname collate pg_catalog."C",
        trigger_row.tgname collate pg_catalog."C")
      from pg_catalog.pg_trigger trigger_row
      join pg_catalog.pg_class class_row
        on class_row.oid = trigger_row.tgrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname in (
          'connected_app_private', 'connected_plan_private'
        )
        and class_row.relname not in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
        and not trigger_row.tgisinternal
    ),
    'rules', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, class_row.relname, rewrite_row.rulename,
        rewrite_row.ev_enabled, rewrite_row.is_instead,
        pg_catalog.pg_get_ruledef(rewrite_row.oid, true)
      ) order by namespace_row.nspname collate pg_catalog."C",
        class_row.relname collate pg_catalog."C",
        rewrite_row.rulename collate pg_catalog."C")
      from pg_catalog.pg_rewrite rewrite_row
      join pg_catalog.pg_class class_row on class_row.oid = rewrite_row.ev_class
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname in (
          'connected_app_private', 'connected_plan_private'
        )
        and class_row.relname not in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
        and rewrite_row.rulename <> '_RETURN'
    ),
    'policies', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, class_row.relname, policy_row.polname,
        policy_row.polpermissive, policy_row.polcmd,
        (
          select pg_catalog.array_agg(
            case when policy_role.role_oid = 0 then 'public'::text
              else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end
            order by (case when policy_role.role_oid = 0 then 'public'::text
              else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end)
              collate pg_catalog."C"
          )
          from pg_catalog.unnest(policy_row.polroles)
            as policy_role(role_oid)
        ),
        pg_catalog.pg_get_expr(policy_row.polqual, policy_row.polrelid),
        pg_catalog.pg_get_expr(policy_row.polwithcheck, policy_row.polrelid)
      ) order by namespace_row.nspname collate pg_catalog."C",
        class_row.relname collate pg_catalog."C",
        policy_row.polname collate pg_catalog."C")
      from pg_catalog.pg_policy policy_row
      join pg_catalog.pg_class class_row on class_row.oid = policy_row.polrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname in (
          'connected_app_private', 'connected_plan_private'
        )
        and class_row.relname not in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
    ),
    'default_acls', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        namespace_row.nspname, pg_catalog.pg_get_userbyid(default_acl.defaclrole),
        default_acl.defaclobjtype, default_acl.defaclacl::text
      ) order by namespace_row.nspname collate pg_catalog."C",
        pg_catalog.pg_get_userbyid(default_acl.defaclrole)
          collate pg_catalog."C",
        default_acl.defaclobjtype::text collate pg_catalog."C")
      from pg_catalog.pg_default_acl default_acl
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = default_acl.defaclnamespace
      where namespace_row.nspname in (
        'connected_app_private', 'connected_plan_private'
      )
    ),
    'roles', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        role_row.rolname, role_row.rolsuper, role_row.rolinherit,
        role_row.rolcreaterole, role_row.rolcreatedb, role_row.rolcanlogin,
        role_row.rolreplication, role_row.rolbypassrls, role_row.rolconnlimit,
        role_row.rolconfig
      ) order by role_row.rolname collate pg_catalog."C")
      from pg_catalog.pg_roles role_row
      where role_row.rolname in (
        'postgres', 'service_role', 'authenticated', 'anon', 'authenticator'
      )
    ),
    'memberships', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        member_role.rolname, granted_role.rolname,
        membership.admin_option, membership.inherit_option,
        membership.set_option
      ) order by member_role.rolname collate pg_catalog."C",
        granted_role.rolname collate pg_catalog."C")
      from pg_catalog.pg_auth_members membership
      join pg_catalog.pg_roles member_role on member_role.oid = membership.member
      join pg_catalog.pg_roles granted_role on granted_role.oid = membership.roleid
      where member_role.rolname in (
          'postgres', 'service_role', 'authenticated', 'anon', 'authenticator'
        )
         or granted_role.rolname in (
          'postgres', 'service_role', 'authenticated', 'anon', 'authenticator'
        )
    ),
    'action_authority', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        authority.action, authority.resource,
        authority.mutates_external_state, authority.approval_class
      ) order by authority.action collate pg_catalog."C")
      from connected_app_private.action_authority authority
    ),
    'all_table_publications', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        publication_row.pubname, publication_row.puballtables,
        publication_row.pubinsert, publication_row.pubupdate,
        publication_row.pubdelete, publication_row.pubtruncate,
        publication_row.pubviaroot
      ) order by publication_row.pubname collate pg_catalog."C")
      from pg_catalog.pg_publication publication_row
      where publication_row.puballtables
    ),
    'schema_publications', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        publication_row.pubname, namespace_row.nspname
      ) order by publication_row.pubname collate pg_catalog."C",
        namespace_row.nspname collate pg_catalog."C")
      from pg_catalog.pg_publication_namespace publication_namespace
      join pg_catalog.pg_publication publication_row
        on publication_row.oid = publication_namespace.pnpubid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = publication_namespace.pnnspid
      where namespace_row.nspname in (
        'connected_app_private', 'connected_plan_private'
      )
    ),
    'direct_publications', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        publication_row.pubname, namespace_row.nspname, class_row.relname
      ) order by publication_row.pubname collate pg_catalog."C",
        namespace_row.nspname collate pg_catalog."C",
        class_row.relname collate pg_catalog."C")
      from pg_catalog.pg_publication_rel publication_relation
      join pg_catalog.pg_publication publication_row
        on publication_row.oid = publication_relation.prpubid
      join pg_catalog.pg_class class_row
        on class_row.oid = publication_relation.prrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname in (
        'connected_app_private', 'connected_plan_private'
      )
    )
  )::text);
$fingerprint$;

do $preflight$
declare
  present_count integer;
  target_fingerprint text;
  helper_fingerprint text;
  predecessor_fingerprint text;
begin
  if pg_catalog.to_regnamespace('connected_app_private') is null
     or pg_catalog.to_regclass('connected_app_private.connections') is null
     or pg_catalog.to_regclass('connected_app_private.oauth_flows') is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_oauth_create_pending_v1(uuid,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text[],text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_oauth_finalize_v2(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,uuid,text,timestamp with time zone,timestamp with time zone,text,uuid,text,uuid,text)'
     ) is null then
    raise exception 'connected OAuth operator bridge predecessor is absent'
      using errcode = '55000';
  end if;

  predecessor_fingerprint :=
    pg_temp.connected_oauth_operator_predecessor_fingerprint();
  if predecessor_fingerprint <> 'aea97e8570dd3521ca7dc9da4476a321' then
    raise exception 'connected OAuth operator composed predecessor drifted: %',
      predecessor_fingerprint
      using errcode = '55000';
  end if;

  if exists (
       select 1 from pg_catalog.pg_publication publication_row
       where publication_row.puballtables
     ) or exists (
       select 1
       from pg_catalog.pg_publication_namespace publication_namespace
       where publication_namespace.pnnspid =
         pg_catalog.to_regnamespace('connected_app_private')
     ) or exists (
       select 1
       from pg_catalog.pg_publication_rel publication_relation
       join pg_catalog.pg_class class_row
         on class_row.oid = publication_relation.prrelid
       join pg_catalog.pg_namespace namespace_row
         on namespace_row.oid = class_row.relnamespace
       where namespace_row.nspname = 'connected_app_private'
         and class_row.relname in (
           'oauth_operator_starts', 'oauth_callback_requests'
         )
     ) then
    raise exception 'connected OAuth operator private state is logically published'
      using errcode = '55000';
  end if;

  select pg_catalog.count(*) into present_count
  from (
    values
      (pg_catalog.to_regclass('connected_app_private.oauth_operator_starts') is not null),
      (pg_catalog.to_regclass('connected_app_private.oauth_callback_requests') is not null),
      (pg_catalog.to_regprocedure(
        'public.connected_app_operator_prepare_oauth_start_v1(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)'
      ) is not null),
      (pg_catalog.to_regprocedure(
        'public.connected_app_operator_read_oauth_start_v1(uuid,uuid)'
      ) is not null),
      (pg_catalog.to_regprocedure(
        'public.connected_app_operator_prepare_oauth_callback_v1(text,text,text,timestamp with time zone)'
      ) is not null),
      (pg_catalog.to_regprocedure(
        'public.connected_app_operator_accept_oauth_callback_v1(text,text,text,timestamp with time zone,uuid,uuid,uuid,uuid,bigint,text,text,text,text)'
      ) is not null),
      (pg_catalog.to_regprocedure(
        'public.connected_app_operator_read_oauth_callback_v1(text,text)'
      ) is not null),
      (pg_catalog.to_regprocedure(
        'connected_app_private.oauth_operator_target_fingerprint_v1()'
      ) is not null)
  ) as target_object(is_present)
  where target_object.is_present;

  if present_count not in (0, 8) then
    raise exception 'connected OAuth operator bridge is partial or drifted'
      using errcode = '55000';
  end if;
  if present_count = 8 then
    select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
      pg_catalog.pg_get_functiondef(proc.oid),
      pg_catalog.obj_description(proc.oid, 'pg_proc'),
      pg_catalog.pg_get_userbyid(proc.proowner), proc.prosecdef::text,
      proc.provolatile::text, proc.proconfig::text, proc.proacl::text
    )) into helper_fingerprint
    from pg_catalog.pg_proc proc
    where proc.oid = pg_catalog.to_regprocedure(
      'connected_app_private.oauth_operator_target_fingerprint_v1()'
    );
    if helper_fingerprint <> '8301bd9a80009d13127f3b0c65361ec4' then
      raise exception 'connected OAuth operator fingerprint helper drifted'
        using errcode = '55000';
    end if;
    select connected_app_private.oauth_operator_target_fingerprint_v1()
      into target_fingerprint;
    if target_fingerprint <> '42ca512dbff523dbc0f4f15736854789' then
      raise exception 'connected OAuth operator bridge target drifted'
        using errcode = '55000';
    end if;
  end if;
end;
$preflight$;

create table if not exists connected_app_private.oauth_operator_starts (
  request_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  session_binding_sha256 text not null
    check (session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  command_binding_sha256 text not null unique
    check (command_binding_sha256 ~ '^[0-9a-f]{64}$'),
  requested_connection_id uuid,
  flow_id uuid not null unique,
  nonce_id uuid not null,
  connection_id uuid not null
    references connected_app_private.connections(id) on delete cascade,
  connection_incarnation_id uuid not null,
  expected_base_revision bigint not null check (expected_base_revision >= 0),
  current_flow_nonce_sha256 text not null
    check (current_flow_nonce_sha256 ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google', 'microsoft')),
  resource text not null check (resource in ('mail', 'calendar')),
  account_kind text not null check (account_kind in ('personal', 'work_school')),
  actions text[] not null check (cardinality(actions) between 1 and 16),
  actions_sha256 text not null check (actions_sha256 ~ '^[0-9a-f]{64}$'),
  redirect_uri_sha256 text not null check (redirect_uri_sha256 ~ '^[0-9a-f]{64}$'),
  requested_at timestamptz not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_oauth_operator_start_lifetime_v1
    check (expires_at = requested_at + interval '10 minutes'),
  constraint connected_oauth_operator_requested_connection_v1
    check (requested_connection_id is null or requested_connection_id = connection_id)
);
comment on table connected_app_private.oauth_operator_starts is
  'ASK_CRUMP_CONNECTED_OAUTH_OPERATOR_STARTS_V1_CONTENT_FREE_EXPLICIT_USER_ACTION';
comment on column connected_app_private.oauth_operator_starts.command_binding_sha256 is
  'ASK_CRUMP_CONNECTED_OAUTH_OPERATOR_START_EXACT_COMMAND_BINDING_V1';
create unique index if not exists connected_oauth_operator_start_owner_request_v1
  on connected_app_private.oauth_operator_starts(owner_id, request_id);
create index if not exists connected_oauth_operator_start_connection_v1
  on connected_app_private.oauth_operator_starts(connection_id, requested_at desc);

create table if not exists connected_app_private.oauth_callback_requests (
  callback_binding_sha256 text primary key
    check (callback_binding_sha256 ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google', 'microsoft')),
  state_sha256 text not null check (state_sha256 ~ '^[0-9a-f]{64}$'),
  flow_id uuid not null unique
    references connected_app_private.oauth_flows(flow_id) on delete cascade,
  received_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  unique(provider, state_sha256)
);
comment on table connected_app_private.oauth_callback_requests is
  'ASK_CRUMP_CONNECTED_OAUTH_CALLBACK_REQUESTS_V1_HASHES_ONLY_NO_CODE_STATE_OR_TOKEN';

alter table connected_app_private.oauth_operator_starts enable row level security;
alter table connected_app_private.oauth_operator_starts force row level security;
alter table connected_app_private.oauth_callback_requests enable row level security;
alter table connected_app_private.oauth_callback_requests force row level security;
revoke all on table connected_app_private.oauth_operator_starts
  from public, anon, authenticated, service_role;
revoke all on table connected_app_private.oauth_callback_requests
  from public, anon, authenticated, service_role;

create or replace function public.connected_app_operator_prepare_oauth_start_v1(
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
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
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
     or p_provider not in ('google', 'microsoft')
     or p_resource not in ('mail', 'calendar')
     or p_account_kind not in ('personal', 'work_school')
     or pg_catalog.cardinality(p_actions) not between 1 and 16
     or p_actions is distinct from array(
       select requested.action_name
       from pg_catalog.unnest(p_actions) as requested(action_name)
       order by requested.action_name
     )
     or exists (
       select 1
       from pg_catalog.unnest(p_actions) as requested(action_name)
       left join connected_app_private.action_authority as authority
         on authority.action = requested.action_name
       where requested.action_name is null
          or authority.action is null
          or authority.resource <> p_resource
     )
     or p_requested_at is null
     or p_requested_at < now_at - interval '5 minutes'
     or p_requested_at > now_at + interval '1 minute'
     or p_expires_at <> p_requested_at + interval '10 minutes' then
    raise exception 'invalid connected OAuth start command' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select start_command.* into start_row
  from connected_app_private.oauth_operator_starts as start_command
  where start_command.request_id = p_request_id
  for update;
  if found then
    if start_row.owner_id <> p_owner_id
       or start_row.session_binding_sha256 <> p_session_binding_sha256
       or start_row.command_binding_sha256 <> p_command_binding_sha256
       or start_row.requested_connection_id is distinct from p_requested_connection_id
       or start_row.flow_id <> p_proposed_flow_id
       or start_row.nonce_id <> p_proposed_nonce_id
       or start_row.connection_id <> p_proposed_connection_id
       or (
         p_requested_connection_id is null
         and start_row.connection_incarnation_id <> p_proposed_connection_incarnation_id
       )
       or start_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256
       or start_row.provider <> p_provider
       or start_row.resource <> p_resource
       or start_row.account_kind <> p_account_kind
       or start_row.actions is distinct from p_actions
       or start_row.actions_sha256 <> p_actions_sha256
       or start_row.redirect_uri_sha256 <> p_redirect_uri_sha256 then
      raise exception 'connected OAuth start replay drifted' using errcode = '55000';
    end if;
    return pg_catalog.to_jsonb(start_row) - 'created_at';
  end if;

  if p_requested_connection_id is not null then
    if p_proposed_connection_id <> p_requested_connection_id then
      raise exception 'requested connection identity drifted' using errcode = '55000';
    end if;
    select connection.* into connection_row
    from connected_app_private.connections as connection
    where connection.id = p_requested_connection_id
      and connection.owner_id = p_owner_id
    for update;
    if not found or connection_row.authorization_state = 'revoked'
       or connection_row.provider <> p_provider
       or connection_row.resource <> p_resource
       or connection_row.account_kind <> p_account_kind then
      raise exception 'requested connection authority is unavailable' using errcode = '55000';
    end if;
  else
    select connection.* into connection_row
    from connected_app_private.connections as connection
    where connection.id = p_proposed_connection_id
    for update;
    if found then
      raise exception 'proposed connection identity already exists' using errcode = '55000';
    end if;
    insert into connected_app_private.connections (
      id, owner_id, provider, resource, account_kind, connection_incarnation_id
    ) values (
      p_proposed_connection_id, p_owner_id, p_provider, p_resource,
      p_account_kind, p_proposed_connection_incarnation_id
    ) returning * into connection_row;
  end if;

  insert into connected_app_private.oauth_operator_starts (
    request_id, owner_id, session_binding_sha256, command_binding_sha256,
    requested_connection_id, flow_id, nonce_id, connection_id,
    connection_incarnation_id, expected_base_revision,
    current_flow_nonce_sha256, provider, resource, account_kind,
    actions, actions_sha256, redirect_uri_sha256, requested_at, expires_at
  ) values (
    p_request_id, p_owner_id, p_session_binding_sha256, p_command_binding_sha256,
    p_requested_connection_id, p_proposed_flow_id, p_proposed_nonce_id,
    connection_row.id, connection_row.connection_incarnation_id,
    connection_row.authorization_revision, p_current_flow_nonce_sha256,
    p_provider, p_resource, p_account_kind, p_actions, p_actions_sha256,
    p_redirect_uri_sha256, p_requested_at, p_expires_at
  ) returning * into start_row;
  return pg_catalog.to_jsonb(start_row) - 'created_at';
end;
$fn$;
comment on function public.connected_app_operator_prepare_oauth_start_v1(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_OAUTH_OPERATOR_PREPARE_START_V1_EXPLICIT_USER_ACTION_EXACT_REPLAY';

create or replace function public.connected_app_operator_read_oauth_start_v1(
  p_owner_id uuid,
  p_request_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.to_jsonb(start_command) - 'created_at'
  from connected_app_private.oauth_operator_starts as start_command
  where start_command.owner_id = p_owner_id
    and start_command.request_id = p_request_id
$fn$;
comment on function public.connected_app_operator_read_oauth_start_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_OAUTH_OPERATOR_READ_START_V1_OWNER_REQUEST_SCOPED';

create or replace function public.connected_app_operator_prepare_oauth_callback_v1(
  p_provider text,
  p_state_sha256 text,
  p_callback_binding_sha256 text,
  p_received_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  callback_row connected_app_private.oauth_callback_requests%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
  effective_received_at timestamptz;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_provider not in ('google', 'microsoft')
     or p_state_sha256 !~ '^[0-9a-f]{64}$'
     or p_callback_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_received_at is null
     or p_received_at > now_at + interval '1 minute' then
    raise exception 'invalid connected OAuth callback binding' using errcode = '22023';
  end if;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.provider = p_provider and flow.state_sha256 = p_state_sha256;
  if not found then
    raise exception 'OAuth callback flow is unavailable' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(flow_row.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = flow_row.connection_id
    and connection.owner_id = flow_row.owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = flow_row.flow_id
  for update;
  select callback.* into callback_row
  from connected_app_private.oauth_callback_requests as callback
  where callback.provider = p_provider and callback.state_sha256 = p_state_sha256
  for update;
  if found then
    if callback_row.callback_binding_sha256 <> p_callback_binding_sha256
       or callback_row.flow_id <> flow_row.flow_id then
      raise exception 'OAuth callback replay drifted' using errcode = '55000';
    end if;
    effective_received_at := callback_row.received_at;
  else
    effective_received_at := p_received_at;
  end if;
  if connection_row.id is null
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> flow_row.connection_incarnation_id
     or connection_row.authorization_revision <> flow_row.expected_base_revision
     or connection_row.current_flow_nonce_sha256 <> flow_row.current_flow_nonce_sha256
     or flow_row.provider <> p_provider
     or flow_row.state_sha256 <> p_state_sha256
     or flow_row.status not in ('pending', 'consumed', 'exchanged', 'completed')
     or effective_received_at < flow_row.created_at
     or effective_received_at >= flow_row.expires_at then
    raise exception 'OAuth callback live authority changed' using errcode = '55000';
  end if;
  if callback_row.callback_binding_sha256 is null
     and (flow_row.status <> 'pending' or now_at >= flow_row.expires_at) then
    raise exception 'OAuth callback was not durably accepted in time'
      using errcode = '55000';
  end if;
  if callback_row.callback_binding_sha256 is not null
     and flow_row.status = 'pending' then
    raise exception 'OAuth callback receipt exists without atomic consumption'
      using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'flow', pg_catalog.jsonb_build_object(
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
    ),
    'callback_received_at', effective_received_at
  );
end;
$fn$;
comment on function public.connected_app_operator_prepare_oauth_callback_v1(
  text,text,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_OAUTH_OPERATOR_PREPARE_CALLBACK_V1_READ_ONLY_HASHES_ONLY';

create or replace function public.connected_app_operator_accept_oauth_callback_v1(
  p_provider text,
  p_state_sha256 text,
  p_callback_binding_sha256 text,
  p_received_at timestamptz,
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
  callback_row connected_app_private.oauth_callback_requests%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
  effective_received_at timestamptz;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_provider not in ('google', 'microsoft')
     or p_state_sha256 !~ '^[0-9a-f]{64}$'
     or p_callback_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_current_flow_nonce_sha256 !~ '^[0-9a-f]{64}$'
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_flow_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_consume_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_received_at is null or p_received_at > now_at + interval '1 minute'
     or p_consumption_id is null or p_owner_id is null
     or p_connection_id is null or p_connection_incarnation_id is null
     or p_expected_base_revision < 0 then
    raise exception 'invalid connected OAuth callback acceptance'
      using errcode = '22023';
  end if;

  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.provider = p_provider and flow.state_sha256 = p_state_sha256;
  if not found or flow_row.owner_id <> p_owner_id
     or flow_row.connection_id <> p_connection_id then
    raise exception 'OAuth callback flow is unavailable' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(flow_row.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = flow_row.connection_id
    and connection.owner_id = flow_row.owner_id
  for update;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = flow_row.flow_id
  for update;
  select callback.* into callback_row
  from connected_app_private.oauth_callback_requests as callback
  where callback.provider = p_provider and callback.state_sha256 = p_state_sha256
  for update;

  if found then
    if callback_row.callback_binding_sha256 <> p_callback_binding_sha256
       or callback_row.flow_id <> flow_row.flow_id then
      raise exception 'OAuth callback replay drifted' using errcode = '55000';
    end if;
    if flow_row.status = 'pending' then
      raise exception 'OAuth callback receipt exists without atomic consumption'
        using errcode = '55000';
    end if;
    effective_received_at := callback_row.received_at;
  else
    if flow_row.status <> 'pending' or now_at >= flow_row.expires_at then
      raise exception 'OAuth callback was not durably accepted in time'
        using errcode = '55000';
    end if;
    effective_received_at := p_received_at;
  end if;

  if connection_row.id is null
     or connection_row.authorization_state = 'revoked'
     or connection_row.connection_incarnation_id <> p_connection_incarnation_id
     or connection_row.authorization_revision <> p_expected_base_revision
     or connection_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256
     or flow_row.owner_id <> p_owner_id
     or flow_row.connection_id <> p_connection_id
     or flow_row.connection_incarnation_id <> p_connection_incarnation_id
     or flow_row.expected_base_revision <> p_expected_base_revision
     or flow_row.current_flow_nonce_sha256 <> p_current_flow_nonce_sha256
     or flow_row.session_binding_sha256 <> p_session_binding_sha256
     or flow_row.flow_binding_sha256 <> p_flow_binding_sha256
     or flow_row.provider <> p_provider
     or flow_row.state_sha256 <> p_state_sha256
     or p_consumption_id <> flow_row.flow_id
     or effective_received_at < flow_row.created_at
     or effective_received_at >= flow_row.expires_at then
    raise exception 'OAuth callback acceptance authority changed'
      using errcode = '55000';
  end if;

  if callback_row.callback_binding_sha256 is null then
    insert into connected_app_private.oauth_callback_requests (
      callback_binding_sha256, provider, state_sha256, flow_id, received_at
    ) values (
      p_callback_binding_sha256, p_provider, p_state_sha256,
      flow_row.flow_id, effective_received_at
    ) returning * into callback_row;
  end if;

  if flow_row.status = 'pending' then
    update connected_app_private.oauth_flows as flow
    set status = 'consumed',
        consumption_id = p_consumption_id,
        consume_binding_sha256 = p_consume_binding_sha256,
        consumed_at = effective_received_at,
        updated_at = now_at
    where flow.flow_id = flow_row.flow_id
    returning * into flow_row;
  elsif flow_row.status not in ('consumed', 'exchanged', 'completed')
     or flow_row.consumption_id <> p_consumption_id
     or flow_row.consume_binding_sha256 <> p_consume_binding_sha256
     or flow_row.consumed_at <> effective_received_at then
    raise exception 'OAuth callback consumption replay drifted'
      using errcode = '55000';
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
comment on function public.connected_app_operator_accept_oauth_callback_v1(
  text,text,text,timestamptz,uuid,uuid,uuid,uuid,bigint,text,text,text,text
) is 'ASK_CRUMP_CONNECTED_OAUTH_OPERATOR_ACCEPT_CALLBACK_V1_ATOMIC_RECEIPT_AND_CONSUMPTION';

create or replace function public.connected_app_operator_read_oauth_callback_v1(
  p_provider text,
  p_callback_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  callback_row connected_app_private.oauth_callback_requests%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  if p_provider not in ('google', 'microsoft')
     or p_callback_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid OAuth callback read binding' using errcode = '22023';
  end if;
  select callback.* into callback_row
  from connected_app_private.oauth_callback_requests as callback
  where callback.provider = p_provider
    and callback.callback_binding_sha256 = p_callback_binding_sha256;
  if not found then return null; end if;
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = callback_row.flow_id;
  if not found then return null; end if;
  perform connected_app_private.owner_lock_v1(flow_row.owner_id);
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id = callback_row.flow_id
  for update;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id = flow_row.connection_id
    and connection.owner_id = flow_row.owner_id
  for update;
  if flow_row.status <> 'completed'
     or connection_row.id is null
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.connection_incarnation_id <> flow_row.connection_incarnation_id
     or connection_row.authorization_revision <> flow_row.completion_authorization_revision
     or connection_row.authorization_snapshot_sha256 <>
        flow_row.completion_authorization_snapshot_sha256
     or connection_row.authorization_issued_at <>
        flow_row.completion_authorization_issued_at
     or connection_row.current_flow_nonce_sha256 <> flow_row.current_flow_nonce_sha256
     or connection_row.external_account_id_sha256 <>
        flow_row.completion_external_account_id_sha256
     or connection_row.broker_credential_ref <>
        flow_row.completion_broker_credential_ref
     or connection_row.credential_ref_sha256 <>
        flow_row.completion_credential_ref_sha256 then
    return null;
  end if;
  return connected_app_private.connection_view_v1(
    flow_row.owner_id, flow_row.connection_id
  );
end;
$fn$;
comment on function public.connected_app_operator_read_oauth_callback_v1(text,text) is
  'ASK_CRUMP_CONNECTED_OAUTH_OPERATOR_READ_CALLBACK_V1_EXACT_ACTIVE_COMPLETION';

create or replace function connected_app_private.oauth_operator_target_fingerprint_v1()
returns text
language sql
stable
set search_path = ''
as $fn$
  select pg_catalog.md5(pg_catalog.jsonb_build_object(
    'relations', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        class_row.relname, class_row.relkind, class_row.relpersistence,
        class_row.relreplident, coalesce(relation_access_method.amname, ''),
        coalesce(relation_tablespace.spcname, ''),
        class_row.reloptions,
        pg_catalog.pg_get_userbyid(class_row.relowner),
        class_row.relrowsecurity, class_row.relforcerowsecurity,
        class_row.relacl::text,
        pg_catalog.obj_description(class_row.oid, 'pg_class')
      ) order by class_row.relname collate pg_catalog."C")
      from pg_catalog.pg_class class_row
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      left join pg_catalog.pg_am relation_access_method
        on relation_access_method.oid = class_row.relam
      left join pg_catalog.pg_tablespace relation_tablespace
        on relation_tablespace.oid = class_row.reltablespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
    ),
    'columns', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        class_row.relname, attribute_row.attnum, attribute_row.attname,
        pg_catalog.format_type(
          attribute_row.atttypid, attribute_row.atttypmod
        ), attribute_row.attnotnull, attribute_row.attidentity,
        attribute_row.attgenerated, attribute_row.attcompression,
        attribute_row.attstorage, attribute_row.attstattarget,
        attribute_row.atthasmissing, attribute_row.attmissingval,
        attribute_row.attinhcount, attribute_row.attislocal,
        attribute_row.attacl,
        coalesce(collation_namespace.nspname || '.', '')
          || coalesce(collation_row.collname, ''),
        coalesce(collation_namespace.nspname || '.', '')
          || coalesce(collation_row.collname, ''),
        pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid),
        pg_catalog.col_description(
          attribute_row.attrelid, attribute_row.attnum
        )
      ) order by class_row.relname collate pg_catalog."C",
        attribute_row.attnum)
      from pg_catalog.pg_attribute attribute_row
      join pg_catalog.pg_class class_row
        on class_row.oid = attribute_row.attrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      left join pg_catalog.pg_attrdef default_row
        on default_row.adrelid = attribute_row.attrelid
       and default_row.adnum = attribute_row.attnum
      left join pg_catalog.pg_collation collation_row
        on collation_row.oid = attribute_row.attcollation
      left join pg_catalog.pg_namespace collation_namespace
        on collation_namespace.oid = collation_row.collnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
        and attribute_row.attnum > 0 and not attribute_row.attisdropped
    ),
    'constraints', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        class_row.relname, constraint_row.conname, constraint_row.contype,
        constraint_row.condeferrable, constraint_row.condeferred,
        constraint_row.convalidated, constraint_row.connoinherit,
        pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
      ) order by class_row.relname collate pg_catalog."C",
        constraint_row.conname collate pg_catalog."C")
      from pg_catalog.pg_constraint constraint_row
      join pg_catalog.pg_class class_row
        on class_row.oid = constraint_row.conrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
    ),
    'indexes', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        table_row.relname, index_row.relname,
        index_row.relpersistence, index_row.reloptions,
        coalesce(index_tablespace.spcname, ''),
        pg_catalog.pg_get_userbyid(index_row.relowner),
        index_link.indisunique, index_link.indisprimary,
        index_link.indisexclusion, index_link.indimmediate,
        index_link.indisclustered, index_link.indisvalid,
        index_link.indcheckxmin, index_link.indisready,
        index_link.indislive, index_link.indisreplident,
        index_link.indnkeyatts, index_link.indnatts,
        index_link.indnullsnotdistinct, index_link.indkey::text,
        (
          select pg_catalog.array_agg(
            coalesce(index_collation_namespace.nspname || '.', '')
              || coalesce(index_collation_row.collname, '')
            order by index_collation.position
          )::text
          from pg_catalog.unnest(index_link.indcollation::oid[])
            with ordinality as index_collation(collation_oid, position)
          left join pg_catalog.pg_collation index_collation_row
            on index_collation_row.oid = index_collation.collation_oid
          left join pg_catalog.pg_namespace index_collation_namespace
            on index_collation_namespace.oid = index_collation_row.collnamespace
        ),
        (
          select pg_catalog.array_agg(
            coalesce(index_opclass_namespace.nspname || '.', '')
              || coalesce(index_opclass_row.opcname, '')
            order by index_opclass.position
          )::text
          from pg_catalog.unnest(index_link.indclass::oid[])
            with ordinality as index_opclass(opclass_oid, position)
          left join pg_catalog.pg_opclass index_opclass_row
            on index_opclass_row.oid = index_opclass.opclass_oid
          left join pg_catalog.pg_namespace index_opclass_namespace
            on index_opclass_namespace.oid = index_opclass_row.opcnamespace
        ),
        index_link.indoption::text,
        pg_catalog.pg_get_indexdef(index_row.oid)
      ) order by table_row.relname collate pg_catalog."C",
        index_row.relname collate pg_catalog."C")
      from pg_catalog.pg_index index_link
      join pg_catalog.pg_class table_row
        on table_row.oid = index_link.indrelid
      join pg_catalog.pg_class index_row
        on index_row.oid = index_link.indexrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = table_row.relnamespace
      left join pg_catalog.pg_tablespace index_tablespace
        on index_tablespace.oid = index_row.reltablespace
      where namespace_row.nspname = 'connected_app_private'
        and table_row.relname in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
    ),
    'functions', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        proc_row.proname,
        pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
        pg_catalog.pg_get_userbyid(proc_row.proowner), proc_row.prosecdef,
        proc_row.proleakproof, proc_row.proisstrict, proc_row.proretset,
        proc_row.provolatile, proc_row.proparallel,
        proc_row.procost, proc_row.prorows,
        language_row.lanname, proc_row.proconfig, proc_row.proacl::text,
        pg_catalog.obj_description(proc_row.oid, 'pg_proc'),
        pg_catalog.pg_get_functiondef(proc_row.oid)
      ) order by proc_row.proname collate pg_catalog."C",
        pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
          collate pg_catalog."C")
      from pg_catalog.pg_proc proc_row
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = proc_row.pronamespace
      join pg_catalog.pg_language language_row
        on language_row.oid = proc_row.prolang
      where namespace_row.nspname = 'public'
        and proc_row.proname in (
          'connected_app_operator_prepare_oauth_start_v1',
          'connected_app_operator_read_oauth_start_v1',
          'connected_app_operator_prepare_oauth_callback_v1',
          'connected_app_operator_accept_oauth_callback_v1',
          'connected_app_operator_read_oauth_callback_v1'
        )
    ),
    'triggers', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        class_row.relname, trigger_row.tgname,
        trigger_row.tgenabled,
        pg_catalog.pg_get_triggerdef(trigger_row.oid, true)
      ) order by class_row.relname collate pg_catalog."C",
        trigger_row.tgname collate pg_catalog."C")
      from pg_catalog.pg_trigger trigger_row
      join pg_catalog.pg_class class_row
        on class_row.oid = trigger_row.tgrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'oauth_operator_starts', 'oauth_callback_requests'
        ) and not trigger_row.tgisinternal
    ),
    'rules', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        class_row.relname, rewrite_row.rulename,
        rewrite_row.ev_enabled, rewrite_row.is_instead,
        pg_catalog.pg_get_ruledef(rewrite_row.oid, true)
      ) order by class_row.relname collate pg_catalog."C",
        rewrite_row.rulename collate pg_catalog."C")
      from pg_catalog.pg_rewrite rewrite_row
      join pg_catalog.pg_class class_row
        on class_row.oid = rewrite_row.ev_class
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'oauth_operator_starts', 'oauth_callback_requests'
        ) and rewrite_row.rulename <> '_RETURN'
    ),
    'policies', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        class_row.relname, policy_row.polname, policy_row.polpermissive,
        policy_row.polcmd,
        (
          select pg_catalog.array_agg(
            case when policy_role.role_oid = 0 then 'public'::text
              else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end
            order by (case when policy_role.role_oid = 0 then 'public'::text
              else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end)
              collate pg_catalog."C"
          )
          from pg_catalog.unnest(policy_row.polroles)
            as policy_role(role_oid)
        ),
        pg_catalog.pg_get_expr(policy_row.polqual, policy_row.polrelid),
        pg_catalog.pg_get_expr(policy_row.polwithcheck, policy_row.polrelid)
      ) order by class_row.relname collate pg_catalog."C",
        policy_row.polname collate pg_catalog."C")
      from pg_catalog.pg_policy policy_row
      join pg_catalog.pg_class class_row
        on class_row.oid = policy_row.polrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
    ),
    'all_table_publications', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        publication_row.pubname, publication_row.puballtables,
        publication_row.pubinsert, publication_row.pubupdate,
        publication_row.pubdelete, publication_row.pubtruncate,
        publication_row.pubviaroot
      ) order by publication_row.pubname collate pg_catalog."C")
      from pg_catalog.pg_publication publication_row
      where publication_row.puballtables
    ),
    'schema_publications', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        publication_row.pubname, namespace_row.nspname
      ) order by publication_row.pubname collate pg_catalog."C",
        namespace_row.nspname collate pg_catalog."C")
      from pg_catalog.pg_publication_namespace publication_namespace
      join pg_catalog.pg_publication publication_row
        on publication_row.oid = publication_namespace.pnpubid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = publication_namespace.pnnspid
      where namespace_row.nspname = 'connected_app_private'
    ),
    'direct_publications', (
      select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
        publication_row.pubname, namespace_row.nspname, class_row.relname
      ) order by publication_row.pubname collate pg_catalog."C",
        class_row.relname collate pg_catalog."C")
      from pg_catalog.pg_publication_rel publication_link
      join pg_catalog.pg_publication publication_row
        on publication_row.oid = publication_link.prpubid
      join pg_catalog.pg_class class_row
        on class_row.oid = publication_link.prrelid
      join pg_catalog.pg_namespace namespace_row
        on namespace_row.oid = class_row.relnamespace
      where namespace_row.nspname = 'connected_app_private'
        and class_row.relname in (
          'oauth_operator_starts', 'oauth_callback_requests'
        )
    )
  )::text);
$fn$;
comment on function connected_app_private.oauth_operator_target_fingerprint_v1() is
  'ASK_CRUMP_CONNECTED_OAUTH_OPERATOR_TARGET_FINGERPRINT_V1_PRIVATE_ATTESTATION';
alter function connected_app_private.oauth_operator_target_fingerprint_v1()
  owner to postgres;
revoke all on function connected_app_private.oauth_operator_target_fingerprint_v1()
  from public, anon, authenticated, service_role;

revoke all on function public.connected_app_operator_prepare_oauth_start_v1(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) from public, anon, authenticated;
revoke all on function public.connected_app_operator_read_oauth_start_v1(uuid,uuid)
  from public, anon, authenticated;
revoke all on function public.connected_app_operator_prepare_oauth_callback_v1(
  text,text,text,timestamptz
) from public, anon, authenticated;
revoke all on function public.connected_app_operator_accept_oauth_callback_v1(
  text,text,text,timestamptz,uuid,uuid,uuid,uuid,bigint,text,text,text,text
) from public, anon, authenticated;
revoke all on function public.connected_app_operator_read_oauth_callback_v1(text,text)
  from public, anon, authenticated;
grant execute on function public.connected_app_operator_prepare_oauth_start_v1(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) to service_role;
grant execute on function public.connected_app_operator_read_oauth_start_v1(uuid,uuid)
  to service_role;
grant execute on function public.connected_app_operator_prepare_oauth_callback_v1(
  text,text,text,timestamptz
) to service_role;
grant execute on function public.connected_app_operator_accept_oauth_callback_v1(
  text,text,text,timestamptz,uuid,uuid,uuid,uuid,bigint,text,text,text,text
) to service_role;
grant execute on function public.connected_app_operator_read_oauth_callback_v1(text,text)
  to service_role;

do $postflight$
declare
  relation_name text;
  function_name text;
  target_fingerprint text;
  helper_fingerprint text;
begin
  foreach relation_name in array array[
    'connected_app_private.oauth_operator_starts',
    'connected_app_private.oauth_callback_requests'
  ] loop
    if pg_catalog.to_regclass(relation_name) is null then
      raise exception 'connected OAuth operator bridge relation is absent'
        using errcode = '55000';
    end if;
  end loop;
  foreach function_name in array array[
    'public.connected_app_operator_prepare_oauth_start_v1(uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,timestamp with time zone,timestamp with time zone)',
    'public.connected_app_operator_read_oauth_start_v1(uuid,uuid)',
    'public.connected_app_operator_prepare_oauth_callback_v1(text,text,text,timestamp with time zone)',
    'public.connected_app_operator_accept_oauth_callback_v1(text,text,text,timestamp with time zone,uuid,uuid,uuid,uuid,bigint,text,text,text,text)',
    'public.connected_app_operator_read_oauth_callback_v1(text,text)'
  ] loop
    if pg_catalog.to_regprocedure(function_name) is null then
      raise exception 'connected OAuth operator bridge function is absent'
        using errcode = '55000';
    end if;
  end loop;
  if pg_catalog.to_regprocedure(
       'connected_app_private.oauth_operator_target_fingerprint_v1()'
     ) is null
     or pg_catalog.has_function_privilege(
       'service_role',
       'connected_app_private.oauth_operator_target_fingerprint_v1()',
       'EXECUTE'
     ) then
    raise exception 'connected OAuth operator fingerprint authority drifted'
      using errcode = '55000';
  end if;
  if not (
    select class.relrowsecurity and class.relforcerowsecurity
    from pg_catalog.pg_class as class
    where class.oid = 'connected_app_private.oauth_operator_starts'::regclass
  ) or not (
    select class.relrowsecurity and class.relforcerowsecurity
    from pg_catalog.pg_class as class
    where class.oid = 'connected_app_private.oauth_callback_requests'::regclass
  ) then
    raise exception 'connected OAuth operator bridge RLS is not forced'
      using errcode = '55000';
  end if;
  if exists (
       select 1 from pg_catalog.pg_publication publication_row
       where publication_row.puballtables
     ) or exists (
       select 1
       from pg_catalog.pg_publication_namespace publication_namespace
       where publication_namespace.pnnspid =
         pg_catalog.to_regnamespace('connected_app_private')
     ) or exists (
       select 1
       from pg_catalog.pg_publication_rel publication_relation
       join pg_catalog.pg_class class_row
         on class_row.oid = publication_relation.prrelid
       where class_row.oid in (
         'connected_app_private.oauth_operator_starts'::regclass,
         'connected_app_private.oauth_callback_requests'::regclass
       )
     ) then
    raise exception 'connected OAuth operator private state is logically published'
      using errcode = '55000';
  end if;
  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    pg_catalog.pg_get_functiondef(proc.oid),
    pg_catalog.obj_description(proc.oid, 'pg_proc'),
    pg_catalog.pg_get_userbyid(proc.proowner), proc.prosecdef::text,
    proc.provolatile::text, proc.proconfig::text, proc.proacl::text
  )) into helper_fingerprint
  from pg_catalog.pg_proc proc
  where proc.oid = pg_catalog.to_regprocedure(
    'connected_app_private.oauth_operator_target_fingerprint_v1()'
  );
  select connected_app_private.oauth_operator_target_fingerprint_v1()
    into target_fingerprint;
  if helper_fingerprint <> '8301bd9a80009d13127f3b0c65361ec4'
     or target_fingerprint <> '42ca512dbff523dbc0f4f15736854789' then
    raise exception 'connected OAuth operator bridge exact target failed'
      using errcode = '55000',
        detail = pg_catalog.format(
          'helper=%s target=%s', helper_fingerprint, target_fingerprint
        );
  end if;
end;
$postflight$;

commit;
