begin;

select pg_catalog.set_config('search_path', 'pg_catalog,public', true);
select pg_catalog.set_config('quote_all_identifiers', 'off', true);

-- Reproduce 061000's complete owned-state fingerprint.  Its pg_temp helper
-- is session-local and cannot be assumed to survive a migration runner, so
-- this successor carries the same scoped catalog manifest independently.
create or replace function pg_temp.connected_schedule_cleanup_predecessor_fingerprint()
returns text language sql stable set search_path='' as $fingerprint$
  select pg_catalog.md5(
    pg_catalog.string_agg(item.value::text,E'\n' order by item.value::text)
  )
  from (
    select pg_catalog.jsonb_build_array(
      'schema',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),
      pg_catalog.obj_description(namespace_row.oid,'pg_namespace')
    ) as value
    from pg_catalog.pg_namespace as namespace_row
    where namespace_row.nspname='connected_app_private'

    union all
    select pg_catalog.jsonb_build_array(
      'relation',namespace_row.nspname,class_row.relname,class_row.relkind,
      class_row.relpersistence,class_row.relrowsecurity,
      class_row.relforcerowsecurity,class_row.relreplident,
      pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text,''),coalesce(class_row.reloptions::text,''),
      pg_catalog.obj_description(class_row.oid,'pg_class'))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'credential_refresh_lease_history','provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history')

    union all
    select pg_catalog.jsonb_build_array(
      'column',class_row.relname,attribute_row.attnum,attribute_row.attname,
      pg_catalog.format_type(attribute_row.atttypid,attribute_row.atttypmod),
      attribute_row.attnotnull,attribute_row.attidentity,
      attribute_row.attgenerated,attribute_row.attstorage,
      attribute_row.attcompression,attribute_row.attstattarget,
      coalesce(attribute_row.attoptions::text,''),
      coalesce(pg_catalog.pg_get_expr(default_row.adbin,default_row.adrelid),''),
      coalesce(attribute_row.attacl::text,''),
      pg_catalog.col_description(class_row.oid,attribute_row.attnum))
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row on class_row.oid=attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_row
      on default_row.adrelid=attribute_row.attrelid
     and default_row.adnum=attribute_row.attnum
    where namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'credential_refresh_lease_history','provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history')
      and attribute_row.attnum>0 and not attribute_row.attisdropped

    union all
    select pg_catalog.jsonb_build_array(
      'constraint',class_row.relname,constraint_row.conname,
      constraint_row.contype,constraint_row.condeferrable,
      constraint_row.condeferred,constraint_row.convalidated,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_class as class_row on class_row.oid=constraint_row.conrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'credential_refresh_lease_history','provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history')

    union all
    select pg_catalog.jsonb_build_array(
      'index',table_row.relname,index_row.relname,index_meta.indisunique,
      index_meta.indisprimary,index_meta.indisvalid,index_meta.indisready,
      index_meta.indislive,pg_catalog.pg_get_indexdef(index_row.oid))
    from pg_catalog.pg_index as index_meta
    join pg_catalog.pg_class as index_row on index_row.oid=index_meta.indexrelid
    join pg_catalog.pg_class as table_row on table_row.oid=index_meta.indrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=table_row.relnamespace
    where namespace_row.nspname='connected_app_private'
      and table_row.relname in (
        'credential_refresh_lease_history','provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history')

    union all
    select pg_catalog.jsonb_build_array(
      'function',namespace_row.nspname,procedure_row.proname,
      pg_catalog.pg_get_function_identity_arguments(procedure_row.oid),
      pg_catalog.pg_get_userbyid(procedure_row.proowner),procedure_row.prosecdef,
      procedure_row.provolatile,procedure_row.proparallel,
      coalesce(procedure_row.proconfig::text,''),
      coalesce(procedure_row.proacl::text,''),
      pg_catalog.obj_description(procedure_row.oid,'pg_proc'),
      pg_catalog.pg_get_functiondef(procedure_row.oid))
    from pg_catalog.pg_proc as procedure_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=procedure_row.pronamespace
    where namespace_row.nspname in ('public','connected_app_private')
      and procedure_row.proname in (
        'cleanup_digest_uuid_v1','queue_credential_cleanup_v1',
        'queue_provisional_cleanup_v1','flag_owner_cleanup_v1',
        'connected_app_credential_claim_refresh_v1',
        'connected_app_credential_finish_refresh_v1',
        'connected_app_credential_quarantine_refresh_v1',
        'connected_app_credential_claim_refresh_v2',
        'connected_app_credential_finish_refresh_v2',
        'connected_app_credential_commit_refresh_v2',
        'connected_app_credential_quarantine_refresh_v2',
        'connected_app_provider_cleanup_begin_v1',
        'connected_app_provider_cleanup_attach_v1',
        'connected_app_provider_cleanup_release_v1',
        'connected_app_provider_cleanup_release_recover_v1',
        'connected_app_provider_cleanup_claim_v1',
        'connected_app_provider_cleanup_recover_v1',
        'connected_app_provider_cleanup_finish_v1')

    union all
    select pg_catalog.jsonb_build_array(
      'trigger',namespace_row.nspname,class_row.relname,trigger_row.tgname,
      trigger_row.tgenabled,pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid=trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where not trigger_row.tgisinternal and (
      (namespace_row.nspname='connected_app_private'
       and class_row.relname in (
         'credential_refresh_lease_history','provider_grant_cleanup_jobs',
         'provider_grant_cleanup_claim_history','credential_envelopes',
         'oauth_provisional_credentials'))
      or (namespace_row.nspname='public' and class_row.relname='users'
          and trigger_row.tgname='connected_cleanup_owner_before_delete'))

    union all
    select pg_catalog.jsonb_build_array(
      'policy',schemaname,tablename,policyname,permissive,roles::text,
      cmd,coalesce(qual,''),coalesce(with_check,''))
    from pg_catalog.pg_policies
    where schemaname='connected_app_private'
      and tablename in (
        'credential_refresh_lease_history','provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history')

    union all
    select pg_catalog.jsonb_build_array(
      'rule',namespace_row.nspname,class_row.relname,rewrite_row.rulename,
      rewrite_row.ev_enabled,pg_catalog.pg_get_ruledef(rewrite_row.oid,true))
    from pg_catalog.pg_rewrite as rewrite_row
    join pg_catalog.pg_class as class_row on class_row.oid=rewrite_row.ev_class
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'credential_refresh_lease_history','provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history')
      and rewrite_row.rulename<>'_RETURN'

    union all
    select pg_catalog.jsonb_build_array(
      'publication',publication_row.pubname,publication_row.puballtables,
      publication_row.pubinsert,publication_row.pubupdate,
      publication_row.pubdelete,publication_row.pubtruncate,
      coalesce(namespace_row.nspname,''),coalesce(class_row.relname,''))
    from pg_catalog.pg_publication as publication_row
    left join pg_catalog.pg_publication_rel as publication_rel
      on publication_rel.prpubid=publication_row.oid
    left join pg_catalog.pg_class as class_row
      on class_row.oid=publication_rel.prrelid
    left join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where publication_row.puballtables or (
      namespace_row.nspname='connected_app_private'
      and class_row.relname in (
        'credential_refresh_lease_history','provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history'))

    union all
    select pg_catalog.jsonb_build_array(
      'role',role_row.rolname,role_row.rolsuper,role_row.rolcreaterole,
      role_row.rolcreatedb,role_row.rolcanlogin,role_row.rolreplication,
      role_row.rolbypassrls)
    from pg_catalog.pg_roles as role_row
    where role_row.rolname in ('postgres','service_role','authenticated','anon')

    union all
    select pg_catalog.jsonb_build_array(
      'membership',member_role.rolname,granted_role.rolname,
      membership.admin_option,membership.inherit_option,membership.set_option,
      grantor_role.rolname)
    from pg_catalog.pg_auth_members as membership
    join pg_catalog.pg_roles as member_role on member_role.oid=membership.member
    join pg_catalog.pg_roles as granted_role on granted_role.oid=membership.roleid
    join pg_catalog.pg_roles as grantor_role on grantor_role.oid=membership.grantor
    where member_role.rolname in ('postgres','service_role','authenticated','anon')
       or granted_role.rolname in ('postgres','service_role','authenticated','anon')
  ) as item
$fingerprint$;

-- Refuse every partial, mixed, or unknown predecessor.  This successor relies
-- on the invocation-bound runtime, permanent credential cleanup fences, and
-- owner-bound encrypted read-result surface.  It never repairs those layers.
do $preflight$
declare
  runtime_fingerprint text;
  read_surface_fingerprint text;
  target_relation_count integer;
  target_proc_count integer;
  target_fingerprint text;
begin
  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    (select pg_catalog.string_agg(
       attribute_row.attname || ':'
         || pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod)
         || ':' || attribute_row.attnotnull::text
         || ':' || coalesce(pg_catalog.col_description(
              attribute_row.attrelid, attribute_row.attnum), ''),
       ',' order by attribute_row.attnum)
     from pg_catalog.pg_attribute as attribute_row
     where attribute_row.attrelid =
         pg_catalog.to_regclass('connected_app_private.action_ledger')
       and attribute_row.attname in (
         'invocation_binding_sha256', 'terminal_resource_version_sha256'
       ) and attribute_row.attnum > 0 and not attribute_row.attisdropped),
    (select pg_catalog.string_agg(
       pg_catalog.pg_get_functiondef(proc_row.oid), E'\n'
       order by proc_row.proname,
                pg_catalog.pg_get_function_identity_arguments(proc_row.oid))
     from pg_catalog.pg_proc as proc_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = proc_row.pronamespace
     where namespace_row.nspname = 'public'
       and proc_row.proname in (
         'connected_app_claim_action_v2', 'connected_app_read_action_v2',
         'connected_app_recover_access_v2', 'connected_app_settle_action_v2'
       )),
    (select pg_catalog.string_agg(
       proc_row.proname || ':' || proc_row.proacl::text,
       ',' order by proc_row.proname)
     from pg_catalog.pg_proc as proc_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = proc_row.pronamespace
     where namespace_row.nspname = 'public'
       and proc_row.proname in (
         'connected_app_claim_action_v1', 'connected_app_read_action_v1',
         'connected_app_recover_access_v1', 'connected_app_settle_action_v1',
         'connected_app_claim_action_v2', 'connected_app_read_action_v2',
         'connected_app_recover_access_v2', 'connected_app_settle_action_v2'
       ))
  )) into runtime_fingerprint;

  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    pg_catalog.pg_get_functiondef(proc.oid),
    pg_catalog.obj_description(proc.oid, 'pg_proc'),
    pg_catalog.pg_get_userbyid(proc.proowner), proc.prosecdef::text,
    proc.provolatile::text, proc.proconfig::text, proc.proacl::text
  )) into read_surface_fingerprint
  from pg_catalog.pg_proc as proc
  where proc.oid=pg_catalog.to_regprocedure(
    'public.connected_app_open_read_result_v1(uuid,uuid)'
  );

  if runtime_fingerprint <> '192b3c7abb884d47736df936c1820bc9'
     or pg_temp.connected_schedule_cleanup_predecessor_fingerprint()
        <> 'e90e794c75b45084d89d6b1247d3287e'
     or read_surface_fingerprint <> 'f03f8f3204e5623fd950ad1ffb9fd430'
     or pg_catalog.obj_description(
          pg_catalog.to_regprocedure(
            'public.connected_app_open_read_result_v1(uuid,uuid)'
          ), 'pg_proc'
        ) is distinct from
          'ASK_CRUMP_CONNECTED_OPEN_READ_RESULT_V1_OWNER_BOUND_CONTENT_FREE_INDEX'
     or not pg_catalog.has_function_privilege(
          'service_role',
          'public.connected_app_open_read_result_v1(uuid,uuid)', 'EXECUTE'
        )
     or pg_catalog.has_function_privilege(
          'authenticated',
          'public.connected_app_open_read_result_v1(uuid,uuid)', 'EXECUTE'
        )
     or pg_catalog.obj_description(
          pg_catalog.to_regclass(
            'connected_app_private.credential_refresh_lease_history'
          ), 'pg_class'
        ) is distinct from
          'ASK_CRUMP_CONNECTED_REFRESH_LEASE_HISTORY_V2_PERMANENT_REPLAY_FENCE'
     or pg_catalog.obj_description(
          pg_catalog.to_regclass(
            'connected_app_private.provider_grant_cleanup_jobs'
          ), 'pg_class'
        ) is distinct from
          'ASK_CRUMP_CONNECTED_PROVIDER_GRANT_CLEANUP_V1_ENCRYPTED_DURABLE_OUTBOX'
     or pg_catalog.obj_description(
          pg_catalog.to_regprocedure(
            'public.connected_app_provider_cleanup_claim_v1(uuid,integer)'
          ), 'pg_proc'
        ) is distinct from
          'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_CLAIM_V1_ONE_WINNER'
     or pg_catalog.to_regclass('connected_plan_private.operations') is null
     or pg_catalog.to_regclass('connected_chat_private.turns') is null
     or pg_catalog.to_regclass('connected_app_private.schedules') is null
     or pg_catalog.obj_description(
          pg_catalog.to_regprocedure(
            'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'
          ), 'pg_proc'
        ) is distinct from
          'ASK_CRUMP_CONNECTED_CHAT_COMPLETION_V1_ATOMIC_REPLY_JOB_TURN_RECEIPT'
     or pg_catalog.obj_description(
          pg_catalog.to_regclass('connected_plan_private.operations'), 'pg_class'
        ) is null then
    raise exception 'connected schedule-template predecessor drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.count(*) into target_relation_count
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_schedule_private'
    and class_row.relname in ('templates', 'run_completions')
    and class_row.relkind = 'r';

  select pg_catalog.count(*) into target_proc_count
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where (namespace_row.nspname, proc_row.proname) in (
    ('connected_schedule_private', 'template_view_v2'),
    ('connected_schedule_private', 'chat_schedule_view_v2'),
    ('connected_schedule_private', 'claim_view_v2'),
    ('connected_schedule_private', 'completion_view_v2'),
    ('connected_schedule_private', 'scrub_cancelled_template_v2'),
    ('public', 'connected_operator_create_chat_schedule_v2'),
    ('public', 'connected_operator_read_chat_schedule_v2'),
    ('public', 'connected_app_claim_schedule_v2'),
    ('public', 'connected_app_read_schedule_claim_v2'),
    ('public', 'connected_app_finish_schedule_v2'),
    ('public', 'connected_app_read_schedule_finish_v2'),
    ('public', 'connected_app_read_schedule_template_v2')
  );

  if target_relation_count = 0 and target_proc_count = 0 then
    if pg_catalog.to_regnamespace('connected_schedule_private') is not null then
      raise exception 'connected schedule-template namespace collision'
        using errcode = '55000';
    end if;
    if exists (select 1 from connected_app_private.schedules) then
      raise exception 'legacy schedule rows cannot be safely backfilled'
        using errcode = '55000';
    end if;
  elsif target_relation_count = 2 and target_proc_count = 12 then
    if exists (
      select 1 from pg_catalog.pg_class as class_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid=class_row.relnamespace
      where namespace_row.nspname='connected_schedule_private'
        and class_row.relkind in ('r','p','v','m','S','f')
        and class_row.relname not in ('templates','run_completions')
    ) or exists (
      select 1 from pg_catalog.pg_proc as proc_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid=proc_row.pronamespace
      where namespace_row.nspname='connected_schedule_private'
        and proc_row.proname not in (
          'template_view_v2','chat_schedule_view_v2','claim_view_v2',
          'completion_view_v2','scrub_cancelled_template_v2'
        )
    ) then
      raise exception 'connected schedule-template target contains unknown objects'
        using errcode='55000';
    end if;
    select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
      (select namespace_row.nspname || '|owner=' ||
         pg_catalog.pg_get_userbyid(namespace_row.nspowner) || '|acl=' ||
         coalesce(namespace_row.nspacl::text,'')
       from pg_catalog.pg_namespace as namespace_row
       where namespace_row.nspname='connected_schedule_private'),
      (select pg_catalog.string_agg(
         namespace_row.nspname || '.' || class_row.relname || '|' ||
         pg_catalog.obj_description(class_row.oid, 'pg_class') || '|' ||
         class_row.relrowsecurity::text || '|' || class_row.relforcerowsecurity::text ||
         '|owner=' || pg_catalog.pg_get_userbyid(class_row.relowner) ||
         '|acl=' || coalesce(class_row.relacl::text,''),
         E'\n' order by namespace_row.nspname, class_row.relname)
       from pg_catalog.pg_class as class_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid = class_row.relnamespace
       where namespace_row.nspname = 'connected_schedule_private'
         and class_row.relname in ('templates', 'run_completions')),
      (select pg_catalog.string_agg(
         namespace_row.nspname || '.' || class_row.relname || '.' ||
         attribute_row.attname || ':' ||
         pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) || ':' ||
         attribute_row.attnotnull::text || ':' ||
         coalesce(pg_catalog.pg_get_expr(
           default_row.adbin, default_row.adrelid), '') || ':' ||
         coalesce(pg_catalog.col_description(
           attribute_row.attrelid,attribute_row.attnum),''),
         E'\n' order by namespace_row.nspname, class_row.relname,
           attribute_row.attnum)
       from pg_catalog.pg_attribute as attribute_row
       join pg_catalog.pg_class as class_row on class_row.oid=attribute_row.attrelid
       join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
       left join pg_catalog.pg_attrdef as default_row
         on default_row.adrelid=attribute_row.attrelid
        and default_row.adnum=attribute_row.attnum
       where namespace_row.nspname='connected_schedule_private'
         and class_row.relname in ('templates','run_completions')
         and attribute_row.attnum>0 and not attribute_row.attisdropped),
      (select pg_catalog.string_agg(
         namespace_row.nspname || '.' || proc_row.proname || '(' ||
         pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || ')|' ||
         pg_catalog.pg_get_functiondef(proc_row.oid) || '|' ||
         coalesce(pg_catalog.obj_description(proc_row.oid,'pg_proc'),'') || '|' ||
         pg_catalog.pg_get_userbyid(proc_row.proowner) || '|' ||
         proc_row.prosecdef::text || '|' || proc_row.provolatile::text || '|' ||
         coalesce(proc_row.proconfig::text,'') || '|' || proc_row.proacl::text,
         E'\n' order by namespace_row.nspname, proc_row.proname,
           pg_catalog.pg_get_function_identity_arguments(proc_row.oid))
       from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=proc_row.pronamespace
       where (namespace_row.nspname, proc_row.proname) in (
         ('connected_schedule_private','template_view_v2'),
         ('connected_schedule_private','chat_schedule_view_v2'),
         ('connected_schedule_private','claim_view_v2'),
         ('connected_schedule_private','completion_view_v2'),
         ('connected_schedule_private','scrub_cancelled_template_v2'),
         ('public','connected_operator_create_chat_schedule_v2'),
         ('public','connected_operator_read_chat_schedule_v2'),
         ('public','connected_app_claim_schedule_v2'),
         ('public','connected_app_read_schedule_claim_v2'),
         ('public','connected_app_finish_schedule_v2'),
         ('public','connected_app_read_schedule_finish_v2'),
         ('public','connected_app_read_schedule_template_v2')
       )),
      (select coalesce(pg_catalog.string_agg(
         index_namespace.nspname || '.' || index_class.relname || '|' ||
         pg_catalog.pg_get_indexdef(index_row.indexrelid) || '|' ||
         index_row.indisunique::text || '|' || index_row.indisvalid::text || '|' ||
         index_row.indisready::text,
         E'\n' order by index_namespace.nspname,index_class.relname),'NONE')
       from pg_catalog.pg_index as index_row
       join pg_catalog.pg_class as table_class
         on table_class.oid=index_row.indrelid
       join pg_catalog.pg_namespace as table_namespace
         on table_namespace.oid=table_class.relnamespace
       join pg_catalog.pg_class as index_class
         on index_class.oid=index_row.indexrelid
       join pg_catalog.pg_namespace as index_namespace
         on index_namespace.oid=index_class.relnamespace
       where table_namespace.nspname='connected_schedule_private'
         and table_class.relname in ('templates','run_completions')),
      (select pg_catalog.string_agg(
         constraint_row.conname || '|' ||
         pg_catalog.pg_get_constraintdef(constraint_row.oid, true),
         E'\n' order by constraint_row.conname)
       from pg_catalog.pg_constraint as constraint_row
       where constraint_row.conrelid in (
         pg_catalog.to_regclass('connected_schedule_private.templates'),
         pg_catalog.to_regclass('connected_schedule_private.run_completions'),
         pg_catalog.to_regclass('connected_app_private.schedules')
       ) and (
         constraint_row.conrelid <> pg_catalog.to_regclass('connected_app_private.schedules')
         or constraint_row.conname='connected_app_schedules_template_v2_fkey'
       )),
      (select pg_catalog.string_agg(
         trigger_row.tgname || '|' || pg_catalog.pg_get_triggerdef(trigger_row.oid,true),
         E'\n' order by trigger_row.tgname)
       from pg_catalog.pg_trigger as trigger_row
       where trigger_row.tgrelid=pg_catalog.to_regclass('connected_app_private.schedules')
         and trigger_row.tgname='connected_schedule_scrub_cancelled_template_v2'
         and not trigger_row.tgisinternal),
      (select pg_catalog.concat_ws('|',
         'policies=' || pg_catalog.count(*) filter (
           where catalog_row.kind='policy'),
         'rules=' || pg_catalog.count(*) filter (
           where catalog_row.kind='rule'),
         'triggers=' || pg_catalog.count(*) filter (
           where catalog_row.kind='trigger'))
       from (
         select 'policy'::text as kind from pg_catalog.pg_policy as policy_row
         where policy_row.polrelid in (
           pg_catalog.to_regclass('connected_schedule_private.templates'),
           pg_catalog.to_regclass('connected_schedule_private.run_completions'))
         union all
         select 'rule'::text from pg_catalog.pg_rewrite as rule_row
         where rule_row.ev_class in (
           pg_catalog.to_regclass('connected_schedule_private.templates'),
           pg_catalog.to_regclass('connected_schedule_private.run_completions'))
           and rule_row.rulename<>'_RETURN'
         union all
         select 'trigger'::text from pg_catalog.pg_trigger as trigger_row
         where trigger_row.tgrelid in (
           pg_catalog.to_regclass('connected_schedule_private.templates'),
           pg_catalog.to_regclass('connected_schedule_private.run_completions'))
           and not trigger_row.tgisinternal
       ) as catalog_row),
      (select pg_catalog.concat_ws('|',
         'all_tables=' || (select pg_catalog.count(*)
           from pg_catalog.pg_publication as publication
           where publication.puballtables),
         'explicit=' || (select pg_catalog.count(*)
           from pg_catalog.pg_publication_rel as publication_relation
           where publication_relation.prrelid in (
             pg_catalog.to_regclass('connected_schedule_private.templates'),
             pg_catalog.to_regclass('connected_schedule_private.run_completions'))))),
      (select pg_catalog.string_agg(proc_row.proname || '|' || proc_row.proacl::text,
         E'\n' order by proc_row.proname)
       from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=proc_row.pronamespace
       where namespace_row.nspname='public' and proc_row.proname in (
         'connected_app_put_schedule_v1','connected_app_claim_schedule_v1',
         'connected_app_finish_schedule_v1','connected_app_operator_create_schedule_v1'
       ))
    )) into target_fingerprint;
    if target_fingerprint <> '4b004a4a403058b443be9dac3c331950' then
      raise exception 'connected schedule-template target drifted: %', target_fingerprint
        using errcode = '55000';
    end if;
  else
    raise exception 'connected schedule-template state is partial or mixed'
      using errcode = '55000';
  end if;
end;
$preflight$;

create schema if not exists connected_schedule_private;
alter schema connected_schedule_private owner to postgres;
revoke all on schema connected_schedule_private from public, anon, authenticated, service_role;

create table if not exists connected_schedule_private.templates (
  template_id uuid primary key,
  schedule_id uuid not null unique,
  owner_id uuid not null references public.users(id) on delete cascade,
  turn_id uuid not null unique,
  connection_id uuid not null
    references connected_app_private.connections(id) on delete cascade,
  task_id uuid not null,
  plan_payload_id uuid not null,
  plan_reference_binding_sha256 text not null
    check (plan_reference_binding_sha256 ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google','microsoft')),
  resource text not null check (resource in ('mail','calendar')),
  action text not null,
  authorization_revision bigint not null check (authorization_revision >= 1),
  authorization_snapshot_sha256 text not null
    check (authorization_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  granted_actions_sha256 text not null
    check (granted_actions_sha256 ~ '^[0-9a-f]{64}$'),
  granted_scopes_sha256 text not null
    check (granted_scopes_sha256 ~ '^[0-9a-f]{64}$'),
  commitment_key_id text not null
    check (commitment_key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  parameters_sha256 text not null
    check (parameters_sha256 ~ '^[0-9a-f]{64}$'),
  resource_version_sha256 text
    check (resource_version_sha256 is null or resource_version_sha256 ~ '^[0-9a-f]{64}$'),
  reference_binding_sha256 text not null unique
    check (reference_binding_sha256 ~ '^[0-9a-f]{64}$'),
  key_id text not null check (key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
  wrapped_key_nonce text,
  wrapped_key_ciphertext text,
  payload_nonce text,
  payload_ciphertext text,
  record_binding_sha256 text not null unique
    check (record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  record_state text not null default 'live' check (record_state in ('live','deleted')),
  created_at timestamptz not null,
  deleted_at timestamptz,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_schedule_template_ciphertext_shape check (
    (record_state='live' and wrapped_key_nonce is not null
      and wrapped_key_ciphertext is not null and payload_nonce is not null
      and payload_ciphertext is not null and deleted_at is null)
    or (record_state='deleted' and wrapped_key_nonce is null
      and wrapped_key_ciphertext is null and payload_nonce is null
      and payload_ciphertext is null and deleted_at is not null)
  ),
  constraint connected_schedule_template_ciphertext_bounds check (
    (wrapped_key_nonce is null or
      (wrapped_key_nonce ~ '^[A-Za-z0-9_-]+$' and length(wrapped_key_nonce) between 16 and 24))
    and (wrapped_key_ciphertext is null or
      (wrapped_key_ciphertext ~ '^[A-Za-z0-9_-]+$' and length(wrapped_key_ciphertext) between 64 and 96))
    and (payload_nonce is null or
      (payload_nonce ~ '^[A-Za-z0-9_-]+$' and length(payload_nonce) between 16 and 24))
    and (payload_ciphertext is null or
      (payload_ciphertext ~ '^[A-Za-z0-9_-]+$' and length(payload_ciphertext) between 24 and 131072))
  ),
  constraint connected_schedule_template_time_order check (
    updated_at >= created_at and (deleted_at is null or deleted_at >= created_at)
  )
);
comment on table connected_schedule_private.templates is
  'ASK_CRUMP_CONNECTED_SCHEDULE_TEMPLATES_V2_SERVER_OWNED_ENCRYPTED_TYPED_REQUESTS';
comment on column connected_schedule_private.templates.parameters_sha256 is
  'ASK_CRUMP_KEYED_HMAC_SCHEDULE_TEMPLATE_COMMITMENT_NOT_PLAINTEXT_DIGEST';
comment on column connected_schedule_private.templates.payload_ciphertext is
  'ASK_CRUMP_AES_GCM_TYPED_CONNECTED_ACTION_PAYLOAD_ENVELOPE_SERVER_CUSTODY';
create index if not exists connected_schedule_templates_owner_idx
  on connected_schedule_private.templates(owner_id, template_id);
create index if not exists connected_schedule_templates_connection_idx
  on connected_schedule_private.templates(connection_id, template_id);
alter table connected_schedule_private.templates enable row level security;
alter table connected_schedule_private.templates force row level security;

create table if not exists connected_schedule_private.run_completions (
  completion_id uuid primary key,
  schedule_id uuid not null
    references connected_app_private.schedules(schedule_id) on delete cascade,
  owner_id uuid not null references public.users(id) on delete cascade,
  claim_id uuid not null,
  task_state_revision bigint not null check (task_state_revision >= 1),
  outcome text not null check (outcome in (
    'read','succeeded','ambiguous','waiting_approval','invalid_template',
    'failed_no_retry','cancelled_unknown'
  )),
  operation_id uuid,
  next_run_at timestamptz not null,
  finished_at timestamptz not null,
  recorded_at timestamptz not null default pg_catalog.clock_timestamp(),
  unique(schedule_id, claim_id),
  constraint connected_schedule_completion_operation_shape check (
    (outcome in ('waiting_approval','invalid_template') and operation_id is null)
    or (outcome not in ('waiting_approval','invalid_template') and operation_id is not null)
  ),
  constraint connected_schedule_completion_time_order check (
    next_run_at >= finished_at + interval '60 seconds'
    and next_run_at <= finished_at + interval '31 days'
    and recorded_at >= finished_at
  )
);
comment on table connected_schedule_private.run_completions is
  'ASK_CRUMP_CONNECTED_SCHEDULE_RUN_COMPLETIONS_V2_PER_CLAIM_DURABLE_LEDGER';
create index if not exists connected_schedule_completions_owner_idx
  on connected_schedule_private.run_completions(owner_id, recorded_at desc);
alter table connected_schedule_private.run_completions enable row level security;
alter table connected_schedule_private.run_completions force row level security;

do $schedule_fk$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid=pg_catalog.to_regclass('connected_app_private.schedules')
      and conname='connected_app_schedules_template_v2_fkey'
  ) then
    alter table connected_app_private.schedules
      add constraint connected_app_schedules_template_v2_fkey
      foreign key(action_template_ref)
      references connected_schedule_private.templates(template_id)
      on delete cascade;
  end if;
end;
$schedule_fk$;

create or replace function connected_schedule_private.template_view_v2(
  p_template_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'template_id', template.template_id,
    'schedule_id', template.schedule_id,
    'owner_id', template.owner_id,
    'turn_id', template.turn_id,
    'connection_id', template.connection_id,
    'task_id', template.task_id,
    'plan_payload_id', template.plan_payload_id,
    'plan_reference_binding_sha256', template.plan_reference_binding_sha256,
    'provider', template.provider,
    'resource', template.resource,
    'action', template.action,
    'authorization_revision', template.authorization_revision,
    'authorization_snapshot_sha256', template.authorization_snapshot_sha256,
    'granted_actions_sha256', template.granted_actions_sha256,
    'granted_scopes_sha256', template.granted_scopes_sha256,
    'commitment_key_id', template.commitment_key_id,
    'parameters_sha256', template.parameters_sha256,
    'resource_version_sha256', template.resource_version_sha256,
    'reference_binding_sha256', template.reference_binding_sha256,
    'created_at', template.created_at,
    'key_id', template.key_id,
    'wrapped_key_nonce', template.wrapped_key_nonce,
    'wrapped_key_ciphertext', template.wrapped_key_ciphertext,
    'payload_nonce', template.payload_nonce,
    'payload_ciphertext', template.payload_ciphertext,
    'record_binding_sha256', template.record_binding_sha256
  ) from connected_schedule_private.templates as template
  where template.template_id=p_template_id and template.record_state='live'
$fn$;

create or replace function connected_schedule_private.chat_schedule_view_v2(
  p_owner_id uuid, p_request_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'request_id', command.request_id,
    'schedule_id', schedule.schedule_id,
    'template_id', template.template_id,
    'owner_id', schedule.owner_id,
    'turn_id', template.turn_id,
    'task_id', schedule.task_id,
    'connection_id', schedule.connection_id,
    'plan_payload_id', template.plan_payload_id,
    'plan_reference_binding_sha256', template.plan_reference_binding_sha256,
    'provider', schedule.provider,
    'resource', schedule.resource,
    'action', schedule.action,
    'parameters_sha256', schedule.parameters_sha256,
    'template_reference_binding_sha256', template.reference_binding_sha256,
    'next_run_at', schedule.next_run_at,
    'created_at', schedule.created_at
  )
  from connected_app_private.operator_commands as command
  join connected_app_private.schedules as schedule
    on schedule.schedule_id=command.subject_id
  join connected_schedule_private.templates as template
    on template.template_id=schedule.action_template_ref
  where command.request_id=p_request_id and command.owner_id=p_owner_id
    and command.command_kind='schedule_create'
    and schedule.owner_id=p_owner_id and template.owner_id=p_owner_id
$fn$;

create or replace function connected_schedule_private.claim_view_v2(
  p_claim_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'schedule_id', schedule.schedule_id,
    'owner_id', schedule.owner_id,
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
    'scheduled_for', schedule.next_run_at,
    'claim_id', schedule.claim_id,
    'claimed_at', schedule.updated_at,
    'claim_expires_at', schedule.claim_expires_at,
    'turn_id', template.turn_id,
    'grant_id', grant_row.grant_id,
    'plan_payload_id', template.plan_payload_id,
    'plan_reference_binding_sha256', template.plan_reference_binding_sha256,
    'authorization_revision', template.authorization_revision,
    'authorization_snapshot_sha256', template.authorization_snapshot_sha256,
    'granted_actions_sha256', template.granted_actions_sha256,
    'granted_scopes_sha256', template.granted_scopes_sha256,
    'template_reference_binding_sha256', template.reference_binding_sha256,
    'resource_version_sha256', template.resource_version_sha256
  )
  from connected_app_private.schedules as schedule
  join connected_schedule_private.templates as template
    on template.template_id=schedule.action_template_ref
  join connected_app_private.task_grants as grant_row
    on grant_row.grant_id=schedule.claim_id
  where schedule.claim_id=p_claim_id and template.record_state='live'
    and grant_row.revoked_at is null
$fn$;

create or replace function connected_schedule_private.completion_view_v2(
  p_schedule_id uuid, p_claim_id uuid, p_completion_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'completion_id', completion.completion_id,
    'schedule_id', completion.schedule_id,
    'owner_id', completion.owner_id,
    'claim_id', completion.claim_id,
    'task_state_revision', completion.task_state_revision,
    'outcome', completion.outcome,
    'operation_id', completion.operation_id,
    'next_run_at', completion.next_run_at,
    'finished_at', completion.finished_at,
    'recorded_at', completion.recorded_at
  ) from connected_schedule_private.run_completions as completion
  where completion.schedule_id=p_schedule_id and completion.claim_id=p_claim_id
    and completion.completion_id=p_completion_id
$fn$;

create or replace function public.connected_operator_create_chat_schedule_v2(
  p_owner_id uuid, p_session_id uuid, p_chat_id uuid, p_message_id uuid,
  p_turn_id uuid, p_claim_token uuid,
  p_origin_session_binding_sha256 text, p_request_binding_sha256 text,
  p_planning_id uuid, p_plan_payload_id uuid, p_request_id uuid,
  p_schedule_id uuid, p_template_id uuid, p_task_id uuid,
  p_connection_id uuid, p_provider text, p_resource text, p_action text,
  p_authorization_revision bigint, p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text, p_granted_scopes_sha256 text,
  p_commitment_key_id text, p_parameters_sha256 text,
  p_resource_version_sha256 text, p_template_reference_binding_sha256 text,
  p_key_id text, p_wrapped_key_nonce text, p_wrapped_key_ciphertext text,
  p_payload_nonce text, p_payload_ciphertext text,
  p_record_binding_sha256 text, p_time_zone text, p_cadence_seconds integer,
  p_quiet_start_minute integer, p_quiet_end_minute integer,
  p_requires_approval_every_run boolean, p_created_at timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  session_row public.sessions%rowtype;
  job_row public.chat_jobs%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  operation_row connected_plan_private.operations%rowtype;
  connection_row connected_app_private.connections%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
  command_row connected_app_private.operator_commands%rowtype;
  template_row connected_schedule_private.templates%rowtype;
  next_at timestamptz;
begin
  if p_owner_id is null or p_session_id is null or p_chat_id is null
     or p_message_id is null or p_turn_id is null or p_claim_token is null
     or p_planning_id is null or p_plan_payload_id is null
     or p_request_id is null or p_schedule_id is null or p_template_id is null
     or p_task_id is null or p_connection_id is null
     or p_action not in (
       'mail.search','mail.get','mail.create_draft','mail.send','mail.reply',
       'calendar.list','calendar.get','calendar.free_busy',
       'calendar.create','calendar.update','calendar.cancel'
     )
     or p_origin_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_request_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_authorization_revision < 1
     or p_authorization_snapshot_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_actions_sha256 !~ '^[0-9a-f]{64}$'
     or p_granted_scopes_sha256 !~ '^[0-9a-f]{64}$'
     or p_commitment_key_id !~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
     or p_parameters_sha256 !~ '^[0-9a-f]{64}$'
     or (p_resource_version_sha256 is not null
       and p_resource_version_sha256 !~ '^[0-9a-f]{64}$')
     or p_template_reference_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_key_id !~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
     or p_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_cadence_seconds not between 60 and 2678400
     or (p_quiet_start_minute is null) <> (p_quiet_end_minute is null)
     or (p_quiet_start_minute is not null and
       (p_quiet_start_minute not between 0 and 1439
        or p_quiet_end_minute not between 0 and 1439
        or p_quiet_start_minute=p_quiet_end_minute))
     or p_requires_approval_every_run is null
     or p_created_at < now_at - interval '30 minutes'
     or p_created_at > now_at + interval '1 minute'
     or not exists (select 1 from pg_catalog.pg_timezone_names as zone
       where zone.name=p_time_zone) then
    raise exception 'invalid connected chat schedule command'
      using errcode='22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select session.* into session_row from public.sessions as session
  where session.id=p_session_id and session.user_id=p_owner_id for share;
  if not found or session_row.revoked_at is not null or session_row.expires_at<=now_at then
    raise exception 'connected schedule session authority changed' using errcode='55000';
  end if;
  select job.* into job_row from public.chat_jobs as job
  where job.user_id=p_owner_id and job.message_id=p_message_id for update;
  if not found or job_row.chat_id<>p_chat_id then
    raise exception 'connected schedule chat job drifted' using errcode='55000';
  end if;
  select turn.* into turn_row from connected_chat_private.turns as turn
  where turn.turn_id=p_turn_id for update;
  if not found or turn_row.job_id<>job_row.id or turn_row.owner_id<>p_owner_id
     or turn_row.chat_id<>p_chat_id or turn_row.message_id<>p_message_id
     or turn_row.origin_session_binding_sha256<>p_origin_session_binding_sha256
     or turn_row.request_binding_sha256<>p_request_binding_sha256 then
    raise exception 'connected schedule turn drifted' using errcode='55000';
  end if;
  select operation.* into operation_row
  from connected_plan_private.operations as operation
  where operation.planning_id=p_planning_id for update;
  if not found or operation_row.owner_id<>p_owner_id
     or operation_row.turn_id<>p_turn_id or operation_row.chat_id<>p_chat_id
     or operation_row.message_id<>p_message_id or operation_row.session_id<>p_session_id
     or operation_row.claim_token<>p_claim_token
     or operation_row.origin_session_binding_sha256<>p_origin_session_binding_sha256
     or operation_row.request_binding_sha256<>p_request_binding_sha256
     or operation_row.payload_id<>p_plan_payload_id
     or operation_row.state<>'settled' or operation_row.disposition<>'schedule'
     or operation_row.connection_id<>p_connection_id
     or operation_row.provider<>p_provider or operation_row.resource<>p_resource
     or operation_row.action<>p_action
     or operation_row.payload_reference_binding_sha256 is null
     or operation_row.expires_at<=now_at then
    raise exception 'connected schedule settled plan changed' using errcode='55000';
  end if;

  select command.* into command_row
  from connected_app_private.operator_commands as command
  where command.request_id=p_request_id for update;
  if found then
    if command_row.owner_id<>p_owner_id or command_row.command_kind<>'schedule_create'
       or command_row.subject_id<>p_schedule_id
       or command_row.session_binding_sha256<>p_origin_session_binding_sha256
       or command_row.command_binding_sha256<>p_template_reference_binding_sha256 then
      raise exception 'connected chat schedule replay drifted' using errcode='55000';
    end if;
    return connected_schedule_private.chat_schedule_view_v2(p_owner_id,p_request_id);
  end if;

  if job_row.status<>'processing' or job_row.claim_token<>p_claim_token
     or turn_row.stage<>'planned' or turn_row.planning_id<>p_planning_id
     or turn_row.schedule_request_id is not null or turn_row.schedule_id is not null
     or turn_row.action_id is not null then
    raise exception 'connected schedule turn is not stageable' using errcode='55000';
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id=p_connection_id and connection.owner_id=p_owner_id for update;
  if not found or connection_row.authorization_state<>'active'
     or connection_row.revoked_at is not null
     or connection_row.provider<>p_provider or connection_row.resource<>p_resource
     or connection_row.authorization_revision<>p_authorization_revision
     or connection_row.authorization_snapshot_sha256<>p_authorization_snapshot_sha256
     or connection_row.granted_actions_sha256<>p_granted_actions_sha256
     or connection_row.granted_scopes_sha256<>p_granted_scopes_sha256
     or connection_row.authorization_expires_at is null
     or connection_row.authorization_expires_at<=now_at
     or not (p_action=any(connection_row.granted_actions)) then
    raise exception 'connected schedule connection authority changed' using errcode='55000';
  end if;
  select authority.* into authority_row
  from connected_app_private.action_authority as authority
  where authority.action=p_action;
  if not found or authority_row.resource<>p_resource
     or authority_row.mutates_external_state<>p_requires_approval_every_run then
    raise exception 'connected schedule action authority changed' using errcode='55000';
  end if;

  select template.* into template_row
  from connected_schedule_private.templates as template
  where template.template_id=p_template_id or template.schedule_id=p_schedule_id
     or template.turn_id=p_turn_id for update;
  if found then
    if template_row.template_id<>p_template_id or template_row.schedule_id<>p_schedule_id
       or template_row.owner_id<>p_owner_id or template_row.turn_id<>p_turn_id
       or template_row.connection_id<>p_connection_id or template_row.task_id<>p_task_id
       or template_row.plan_payload_id<>p_plan_payload_id
       or template_row.plan_reference_binding_sha256<>
          operation_row.payload_reference_binding_sha256
       or template_row.provider<>p_provider or template_row.resource<>p_resource
       or template_row.action<>p_action
       or template_row.authorization_revision<>p_authorization_revision
       or template_row.authorization_snapshot_sha256<>p_authorization_snapshot_sha256
       or template_row.granted_actions_sha256<>p_granted_actions_sha256
       or template_row.granted_scopes_sha256<>p_granted_scopes_sha256
       or template_row.commitment_key_id<>p_commitment_key_id
       or template_row.parameters_sha256<>p_parameters_sha256
       or template_row.resource_version_sha256 is distinct from p_resource_version_sha256
       or template_row.reference_binding_sha256<>p_template_reference_binding_sha256
       or template_row.record_state<>'live' or template_row.created_at<>p_created_at then
      raise exception 'connected schedule template identity drifted' using errcode='55000';
    end if;
  else
    insert into connected_schedule_private.templates(
      template_id,schedule_id,owner_id,turn_id,connection_id,task_id,
      plan_payload_id,plan_reference_binding_sha256,provider,resource,action,
      authorization_revision,authorization_snapshot_sha256,
      granted_actions_sha256,granted_scopes_sha256,commitment_key_id,
      parameters_sha256,resource_version_sha256,reference_binding_sha256,
      key_id,wrapped_key_nonce,wrapped_key_ciphertext,payload_nonce,
      payload_ciphertext,record_binding_sha256,record_state,created_at,updated_at
    ) values (
      p_template_id,p_schedule_id,p_owner_id,p_turn_id,p_connection_id,p_task_id,
      p_plan_payload_id,operation_row.payload_reference_binding_sha256,
      p_provider,p_resource,p_action,p_authorization_revision,
      p_authorization_snapshot_sha256,p_granted_actions_sha256,
      p_granted_scopes_sha256,p_commitment_key_id,p_parameters_sha256,
      p_resource_version_sha256,p_template_reference_binding_sha256,
      p_key_id,p_wrapped_key_nonce,p_wrapped_key_ciphertext,p_payload_nonce,
      p_payload_ciphertext,p_record_binding_sha256,'live',p_created_at,now_at
    );
  end if;

  next_at := greatest(
    now_at + interval '60 seconds',
    p_created_at + pg_catalog.make_interval(secs=>p_cadence_seconds)
  );
  perform public.connected_app_put_schedule_v1(
    p_schedule_id,p_owner_id,p_connection_id,p_task_id,p_provider,p_resource,
    p_action,p_template_id,p_parameters_sha256,1,p_time_zone,p_cadence_seconds,
    p_quiet_start_minute,p_quiet_end_minute,p_requires_approval_every_run,
    'active',next_at
  );
  insert into connected_app_private.operator_commands(
    request_id,owner_id,command_kind,subject_id,session_binding_sha256,
    command_binding_sha256,requested_at,completed_at
  ) values (
    p_request_id,p_owner_id,'schedule_create',p_schedule_id,
    p_origin_session_binding_sha256,p_template_reference_binding_sha256,
    p_created_at,now_at
  );
  update connected_chat_private.turns as turn
  set stage='prepared',schedule_request_id=p_request_id,
      schedule_id=p_schedule_id,updated_at=now_at
  where turn.turn_id=p_turn_id and turn.stage='planned';
  if not found then
    raise exception 'connected schedule lost turn fence' using errcode='55000';
  end if;
  return connected_schedule_private.chat_schedule_view_v2(p_owner_id,p_request_id);
end;
$fn$;
comment on function public.connected_operator_create_chat_schedule_v2(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,uuid,
  uuid,text,text,text,bigint,text,text,text,text,text,text,text,text,text,text,
  text,text,text,text,integer,integer,integer,boolean,timestamptz
) is 'ASK_CRUMP_CONNECTED_CHAT_SCHEDULE_V2_ATOMIC_SETTLED_PLAN_ENCRYPTED_TEMPLATE';

create or replace function public.connected_operator_read_chat_schedule_v2(
  p_owner_id uuid,p_request_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_schedule_private.chat_schedule_view_v2(p_owner_id,p_request_id)
$fn$;
comment on function public.connected_operator_read_chat_schedule_v2(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_CHAT_SCHEDULE_READ_V2_RESPONSE_LOSS_RECOVERY';

create or replace function public.connected_app_claim_schedule_v2(
  p_claim_id uuid,p_lease_seconds integer
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  claimed jsonb;
  schedule_row connected_app_private.schedules%rowtype;
  template_row connected_schedule_private.templates%rowtype;
  connection_row connected_app_private.connections%rowtype;
  grant_row connected_app_private.task_grants%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
  grant_actions_sha256 text;
begin
  if p_claim_id is null or p_lease_seconds not between 30 and 300 then
    raise exception 'invalid schedule v2 lease' using errcode='22023';
  end if;
  claimed := public.connected_app_claim_schedule_v1(p_claim_id,p_lease_seconds);
  -- V1 can reject several due schedules before finding a valid one.  It owns
  -- every such row update in this transaction and retains the corresponding
  -- owner advisory locks.  Retire capabilities only for schedules whose
  -- pause was written by this exact transaction; never sweep unrelated rows.
  update connected_app_private.task_grants as prior_grant
  set revoked_at=now_at
  from connected_app_private.schedules as paused_schedule
  where paused_schedule.status='paused' and paused_schedule.claim_id is null
    and paused_schedule.xmin::text=pg_catalog.pg_current_xact_id()::text
    and prior_grant.owner_id=paused_schedule.owner_id
    and prior_grant.task_id=paused_schedule.task_id
    and prior_grant.revoked_at is null;
  if claimed is null then
    return null;
  end if;
  select schedule.* into schedule_row
  from connected_app_private.schedules as schedule
  where schedule.claim_id=p_claim_id for update;
  if not found then return null; end if;
  perform connected_app_private.owner_lock_v1(schedule_row.owner_id);
  select template.* into template_row
  from connected_schedule_private.templates as template
  where template.template_id=schedule_row.action_template_ref for update;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id=schedule_row.connection_id
    and connection.owner_id=schedule_row.owner_id for update;
  if template_row.template_id is null or template_row.record_state<>'live'
     or template_row.schedule_id<>schedule_row.schedule_id
     or template_row.owner_id<>schedule_row.owner_id
     or template_row.connection_id<>schedule_row.connection_id
     or template_row.task_id<>schedule_row.task_id
     or template_row.provider<>schedule_row.provider
     or template_row.resource<>schedule_row.resource
     or template_row.action<>schedule_row.action
     or template_row.parameters_sha256<>schedule_row.parameters_sha256
     or connection_row.id is null or connection_row.authorization_state<>'active'
     or connection_row.revoked_at is not null
     or connection_row.provider<>template_row.provider
     or connection_row.resource<>template_row.resource
     or connection_row.authorization_revision<>template_row.authorization_revision
     or connection_row.authorization_snapshot_sha256<>
        template_row.authorization_snapshot_sha256
     or connection_row.granted_actions_sha256<>template_row.granted_actions_sha256
     or connection_row.granted_scopes_sha256<>template_row.granted_scopes_sha256
     or connection_row.authorization_expires_at is null
     or connection_row.authorization_expires_at<=schedule_row.claim_expires_at
     or not (template_row.action=any(connection_row.granted_actions)) then
    update connected_app_private.schedules set status='paused',next_run_at=null,
      claim_id=null,claim_expires_at=null,updated_at=now_at
    where schedule_id=schedule_row.schedule_id;
    update connected_app_private.task_grants set revoked_at=now_at
    where owner_id=schedule_row.owner_id and task_id=schedule_row.task_id
      and revoked_at is null;
    return null;
  end if;
  grant_actions_sha256 := case schedule_row.action
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
    else null end;
  if grant_actions_sha256 is null then
    raise exception 'schedule action grant hash unavailable' using errcode='55000';
  end if;
  select grant_value.* into grant_row
  from connected_app_private.task_grants as grant_value
  where grant_value.grant_id=p_claim_id for update;
  if found then
    if grant_row.owner_id<>schedule_row.owner_id
       or grant_row.task_id<>schedule_row.task_id
       or grant_row.turn_id<>template_row.turn_id
       or grant_row.connection_id<>schedule_row.connection_id
       or grant_row.authorization_revision<>template_row.authorization_revision
       or grant_row.authorization_snapshot_sha256<>
          template_row.authorization_snapshot_sha256
       or grant_row.actions is distinct from array[schedule_row.action]
       or grant_row.actions_sha256<>grant_actions_sha256
       or grant_row.task_state_revision<>schedule_row.task_state_revision
       or grant_row.expires_at<>schedule_row.claim_expires_at
       or grant_row.revoked_at is not null then
      raise exception 'schedule claim grant replay drifted' using errcode='55000';
    end if;
  else
    insert into connected_app_private.task_grants(
      grant_id,owner_id,task_id,turn_id,connection_id,provider,resource,
      authorization_revision,authorization_snapshot_sha256,actions,
      actions_sha256,task_state_revision,expires_at
    ) values (
      p_claim_id,schedule_row.owner_id,schedule_row.task_id,template_row.turn_id,
      schedule_row.connection_id,schedule_row.provider,schedule_row.resource,
      template_row.authorization_revision,template_row.authorization_snapshot_sha256,
      array[schedule_row.action],grant_actions_sha256,
      schedule_row.task_state_revision,schedule_row.claim_expires_at
    );
  end if;
  return connected_schedule_private.claim_view_v2(p_claim_id);
end;
$fn$;
comment on function public.connected_app_claim_schedule_v2(uuid,integer) is
  'ASK_CRUMP_CONNECTED_SCHEDULE_CLAIM_V2_TEMPLATE_AUTHORITY_AND_GRANT_ATOMIC';

create or replace function public.connected_app_read_schedule_claim_v2(
  p_claim_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_schedule_private.claim_view_v2(p_claim_id)
$fn$;
comment on function public.connected_app_read_schedule_claim_v2(uuid) is
  'ASK_CRUMP_CONNECTED_SCHEDULE_CLAIM_READ_V2_EXACT_RESPONSE_LOSS_RECOVERY';

create or replace function public.connected_app_finish_schedule_v2(
  p_completion_id uuid,p_schedule_id uuid,p_owner_id uuid,p_claim_id uuid,
  p_task_state_revision bigint,p_outcome text,p_operation_id uuid,
  p_next_run_at timestamptz,p_finished_at timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  schedule_row connected_app_private.schedules%rowtype;
  completion_row connected_schedule_private.run_completions%rowtype;
begin
  if p_completion_id is null or p_schedule_id is null or p_owner_id is null
     or p_claim_id is null or p_task_state_revision<1
     or p_outcome not in ('read','succeeded','ambiguous','waiting_approval',
       'invalid_template','failed_no_retry','cancelled_unknown')
     or ((p_outcome in ('waiting_approval','invalid_template'))<>(p_operation_id is null))
     or p_finished_at<now_at-interval '5 minutes'
     or p_finished_at>now_at+interval '1 minute'
     or p_next_run_at<p_finished_at+interval '60 seconds'
     or p_next_run_at>p_finished_at+interval '31 days' then
    raise exception 'invalid schedule completion v2' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select completion.* into completion_row
  from connected_schedule_private.run_completions as completion
  where completion.completion_id=p_completion_id
     or (completion.schedule_id=p_schedule_id and completion.claim_id=p_claim_id)
  order by completion.completion_id limit 1 for update;
  if found then
    if completion_row.completion_id<>p_completion_id
       or completion_row.schedule_id<>p_schedule_id
       or completion_row.owner_id<>p_owner_id
       or completion_row.claim_id<>p_claim_id
       or completion_row.task_state_revision<>p_task_state_revision
       or completion_row.outcome<>p_outcome
       or completion_row.operation_id is distinct from p_operation_id
       or completion_row.next_run_at<>p_next_run_at
       or completion_row.finished_at<>p_finished_at then
      raise exception 'schedule completion replay drifted' using errcode='55000';
    end if;
    return connected_schedule_private.completion_view_v2(
      p_schedule_id,p_claim_id,p_completion_id);
  end if;
  select schedule.* into schedule_row
  from connected_app_private.schedules as schedule
  where schedule.schedule_id=p_schedule_id and schedule.owner_id=p_owner_id for update;
  if not found or schedule_row.status<>'active' or schedule_row.claim_id<>p_claim_id
     or schedule_row.claim_expires_at<=now_at
     or schedule_row.task_state_revision<>p_task_state_revision then
    raise exception 'schedule completion claim is stale' using errcode='55000';
  end if;
  insert into connected_schedule_private.run_completions(
    completion_id,schedule_id,owner_id,claim_id,task_state_revision,outcome,
    operation_id,next_run_at,finished_at,recorded_at
  ) values (
    p_completion_id,p_schedule_id,p_owner_id,p_claim_id,p_task_state_revision,
    p_outcome,p_operation_id,p_next_run_at,p_finished_at,now_at
  );
  update connected_app_private.schedules as schedule set
    claim_id=null,claim_expires_at=null,completed_claim_id=p_claim_id,
    completed_at=now_at,
    status=case when p_outcome='invalid_template' then 'paused' else 'active' end,
    next_run_at=case when p_outcome='invalid_template' then null else p_next_run_at end,
    updated_at=now_at
  where schedule.schedule_id=p_schedule_id;
  update connected_app_private.task_grants set revoked_at=now_at
  where grant_id=p_claim_id and revoked_at is null;
  return connected_schedule_private.completion_view_v2(
    p_schedule_id,p_claim_id,p_completion_id);
end;
$fn$;
comment on function public.connected_app_finish_schedule_v2(
  uuid,uuid,uuid,uuid,bigint,text,uuid,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_SCHEDULE_FINISH_V2_DURABLE_EXACT_COMPLETION_LEDGER';

create or replace function public.connected_app_read_schedule_finish_v2(
  p_schedule_id uuid,p_claim_id uuid,p_completion_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_schedule_private.completion_view_v2(
    p_schedule_id,p_claim_id,p_completion_id)
$fn$;
comment on function public.connected_app_read_schedule_finish_v2(uuid,uuid,uuid) is
  'ASK_CRUMP_CONNECTED_SCHEDULE_FINISH_READ_V2_EXACT_RESPONSE_LOSS_RECOVERY';

create or replace function public.connected_app_read_schedule_template_v2(
  p_template_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_schedule_private.template_view_v2(p_template_id)
$fn$;
comment on function public.connected_app_read_schedule_template_v2(uuid) is
  'ASK_CRUMP_CONNECTED_SCHEDULE_TEMPLATE_READ_V2_SERVICE_ROLE_ENCRYPTED_ONLY';

create or replace function connected_schedule_private.scrub_cancelled_template_v2()
returns trigger language plpgsql security definer set search_path='' as $fn$
begin
  if old.status<>'cancelled' and new.status='cancelled' then
    update connected_schedule_private.templates as template set
      wrapped_key_nonce=null,wrapped_key_ciphertext=null,payload_nonce=null,
      payload_ciphertext=null,record_state='deleted',
      deleted_at=pg_catalog.clock_timestamp(),updated_at=pg_catalog.clock_timestamp()
    where template.template_id=new.action_template_ref and template.record_state='live';
  end if;
  return new;
end;
$fn$;
comment on function connected_schedule_private.scrub_cancelled_template_v2() is
  'ASK_CRUMP_CONNECTED_SCHEDULE_CANCEL_V2_ERASES_ENCRYPTED_TEMPLATE_CIPHERTEXT';
drop trigger if exists connected_schedule_scrub_cancelled_template_v2
  on connected_app_private.schedules;
create trigger connected_schedule_scrub_cancelled_template_v2
after update of status on connected_app_private.schedules
for each row execute function connected_schedule_private.scrub_cancelled_template_v2();
comment on trigger connected_schedule_scrub_cancelled_template_v2
  on connected_app_private.schedules is
  'ASK_CRUMP_CONNECTED_SCHEDULE_CANCEL_V2_CIPHERTEXT_ERASURE_FENCE';

alter table connected_schedule_private.templates owner to postgres;
alter table connected_schedule_private.run_completions owner to postgres;
revoke all on table connected_schedule_private.templates
  from public,anon,authenticated,service_role;
revoke all on table connected_schedule_private.run_completions
  from public,anon,authenticated,service_role;

do $private_acl$
declare signature text;
begin
  foreach signature in array array[
    'connected_schedule_private.template_view_v2(uuid)',
    'connected_schedule_private.chat_schedule_view_v2(uuid,uuid)',
    'connected_schedule_private.claim_view_v2(uuid)',
    'connected_schedule_private.completion_view_v2(uuid,uuid,uuid)',
    'connected_schedule_private.scrub_cancelled_template_v2()'
  ] loop
    execute 'alter function '||signature||' owner to postgres';
    execute 'revoke all on function '||signature||' from public,anon,authenticated,service_role';
  end loop;
end;
$private_acl$;

-- Disable every legacy service-role path that could accept a caller-authored
-- template reference or bypass the v2 completion ledger.  The v2 definer
-- functions may call the v1 implementation internally as postgres.
revoke all on function public.connected_app_put_schedule_v1(
  uuid,uuid,uuid,uuid,text,text,text,uuid,text,bigint,text,integer,integer,
  integer,boolean,text,timestamptz
) from service_role;
revoke all on function public.connected_app_claim_schedule_v1(uuid,integer)
  from service_role;
revoke all on function public.connected_app_finish_schedule_v1(
  uuid,uuid,uuid,timestamptz,bigint
) from service_role;
revoke all on function public.connected_app_operator_create_schedule_v1(
  uuid,uuid,uuid,text,text,uuid,uuid,text,text,text,uuid,text,text,integer,
  integer,integer,boolean,timestamptz,timestamptz
) from service_role;

do $public_acl$
declare signature text;
begin
  foreach signature in array array[
    'public.connected_operator_create_chat_schedule_v2(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,text,text,text,text,text,text,text,integer,integer,integer,boolean,timestamp with time zone)',
    'public.connected_operator_read_chat_schedule_v2(uuid,uuid)',
    'public.connected_app_claim_schedule_v2(uuid,integer)',
    'public.connected_app_read_schedule_claim_v2(uuid)',
    'public.connected_app_finish_schedule_v2(uuid,uuid,uuid,uuid,bigint,text,uuid,timestamp with time zone,timestamp with time zone)',
    'public.connected_app_read_schedule_finish_v2(uuid,uuid,uuid)',
    'public.connected_app_read_schedule_template_v2(uuid)'
  ] loop
    execute 'alter function '||signature||' owner to postgres';
    execute 'revoke all on function '||signature||' from public,anon,authenticated';
    execute 'grant execute on function '||signature||' to service_role';
  end loop;
end;
$public_acl$;

do $postflight$
declare
  target_fingerprint text;
begin
  if not exists (select 1 from pg_catalog.pg_namespace as namespace_row
       join pg_catalog.pg_roles as owner_role
         on owner_role.oid=namespace_row.nspowner
       where namespace_row.nspname='connected_schedule_private'
         and owner_role.rolname='postgres')
     or exists (select 1 from pg_catalog.pg_class as class_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname='connected_schedule_private'
         and class_row.relkind in ('r','p','v','m','S','f')
         and class_row.relname not in ('templates','run_completions'))
     or exists (select 1 from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=proc_row.pronamespace
       where namespace_row.nspname='connected_schedule_private'
         and proc_row.proname not in (
           'template_view_v2','chat_schedule_view_v2','claim_view_v2',
           'completion_view_v2','scrub_cancelled_template_v2'))
     or exists (select 1 from pg_catalog.pg_namespace as namespace_row
       cross join lateral pg_catalog.aclexplode(coalesce(
         namespace_row.nspacl,
         pg_catalog.acldefault('n',namespace_row.nspowner))) as privilege_row
       where namespace_row.nspname='connected_schedule_private'
         and privilege_row.grantee=0
         and privilege_row.privilege_type in ('USAGE','CREATE'))
     or pg_catalog.has_schema_privilege(
       'anon','connected_schedule_private','USAGE')
     or pg_catalog.has_schema_privilege(
       'anon','connected_schedule_private','CREATE')
     or pg_catalog.has_schema_privilege(
       'authenticated','connected_schedule_private','USAGE')
     or pg_catalog.has_schema_privilege(
       'authenticated','connected_schedule_private','CREATE')
     or pg_catalog.has_schema_privilege(
       'service_role','connected_schedule_private','USAGE')
     or pg_catalog.has_schema_privilege(
       'service_role','connected_schedule_private','CREATE')
     or exists (select 1 from pg_catalog.pg_class as class_row
       join pg_catalog.pg_roles as owner_role on owner_role.oid=class_row.relowner
       where class_row.oid in (
         pg_catalog.to_regclass('connected_schedule_private.templates'),
         pg_catalog.to_regclass('connected_schedule_private.run_completions'))
         and owner_role.rolname<>'postgres')
     or exists (select 1 from pg_catalog.pg_policy as policy
      where policy.polrelid in (
        pg_catalog.to_regclass('connected_schedule_private.templates'),
        pg_catalog.to_regclass('connected_schedule_private.run_completions')))
     or exists (select 1 from pg_catalog.pg_rewrite as rule_row
       where rule_row.ev_class in (
         pg_catalog.to_regclass('connected_schedule_private.templates'),
         pg_catalog.to_regclass('connected_schedule_private.run_completions'))
         and rule_row.rulename<>'_RETURN')
     or exists (select 1 from pg_catalog.pg_trigger as trigger_row
       where trigger_row.tgrelid in (
         pg_catalog.to_regclass('connected_schedule_private.templates'),
         pg_catalog.to_regclass('connected_schedule_private.run_completions'))
         and not trigger_row.tgisinternal)
     or exists (select 1 from pg_catalog.pg_publication as publication
       where publication.puballtables)
     or exists (select 1 from pg_catalog.pg_publication_rel as publication_relation
       where publication_relation.prrelid in (
         pg_catalog.to_regclass('connected_schedule_private.templates'),
         pg_catalog.to_regclass('connected_schedule_private.run_completions')))
     or not (select class_row.relrowsecurity and class_row.relforcerowsecurity
       from pg_catalog.pg_class as class_row
       where class_row.oid=pg_catalog.to_regclass('connected_schedule_private.templates'))
     or not (select class_row.relrowsecurity and class_row.relforcerowsecurity
       from pg_catalog.pg_class as class_row
       where class_row.oid=pg_catalog.to_regclass('connected_schedule_private.run_completions'))
     or pg_catalog.has_function_privilege('service_role',
       'public.connected_app_operator_create_schedule_v1(uuid,uuid,uuid,text,text,uuid,uuid,text,text,text,uuid,text,text,integer,integer,integer,boolean,timestamp with time zone,timestamp with time zone)','EXECUTE')
     or pg_catalog.has_function_privilege('service_role',
       'public.connected_app_claim_schedule_v1(uuid,integer)','EXECUTE')
     or not pg_catalog.has_function_privilege('service_role',
       'public.connected_app_claim_schedule_v2(uuid,integer)','EXECUTE')
     or pg_catalog.has_function_privilege('anon',
       'public.connected_app_claim_schedule_v2(uuid,integer)','EXECUTE')
     or not exists (select 1 from pg_catalog.pg_trigger as trigger_row
       where trigger_row.tgrelid=pg_catalog.to_regclass('connected_app_private.schedules')
         and trigger_row.tgname='connected_schedule_scrub_cancelled_template_v2'
         and not trigger_row.tgisinternal) then
    raise exception 'connected schedule-template authority postflight failed'
      using errcode='55000';
  end if;

  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    (select namespace_row.nspname || '|owner=' ||
       pg_catalog.pg_get_userbyid(namespace_row.nspowner) || '|acl=' ||
       coalesce(namespace_row.nspacl::text,'')
     from pg_catalog.pg_namespace as namespace_row
     where namespace_row.nspname='connected_schedule_private'),
    (select pg_catalog.string_agg(
       namespace_row.nspname || '.' || class_row.relname || '|' ||
       pg_catalog.obj_description(class_row.oid, 'pg_class') || '|' ||
       class_row.relrowsecurity::text || '|' || class_row.relforcerowsecurity::text ||
       '|owner=' || pg_catalog.pg_get_userbyid(class_row.relowner) ||
       '|acl=' || coalesce(class_row.relacl::text,''),
       E'\n' order by namespace_row.nspname, class_row.relname)
     from pg_catalog.pg_class as class_row
     join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
     where namespace_row.nspname='connected_schedule_private'
       and class_row.relname in ('templates','run_completions')),
    (select pg_catalog.string_agg(
       namespace_row.nspname || '.' || class_row.relname || '.' ||
       attribute_row.attname || ':' ||
       pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) || ':' ||
       attribute_row.attnotnull::text || ':' ||
       coalesce(pg_catalog.pg_get_expr(default_row.adbin,default_row.adrelid),'') || ':' ||
       coalesce(pg_catalog.col_description(
         attribute_row.attrelid,attribute_row.attnum),''),
       E'\n' order by namespace_row.nspname,class_row.relname,attribute_row.attnum)
     from pg_catalog.pg_attribute as attribute_row
     join pg_catalog.pg_class as class_row on class_row.oid=attribute_row.attrelid
     join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
     left join pg_catalog.pg_attrdef as default_row
       on default_row.adrelid=attribute_row.attrelid and default_row.adnum=attribute_row.attnum
     where namespace_row.nspname='connected_schedule_private'
       and class_row.relname in ('templates','run_completions')
       and attribute_row.attnum>0 and not attribute_row.attisdropped),
    (select pg_catalog.string_agg(
       namespace_row.nspname || '.' || proc_row.proname || '(' ||
       pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || ')|' ||
       pg_catalog.pg_get_functiondef(proc_row.oid) || '|' ||
       coalesce(pg_catalog.obj_description(proc_row.oid,'pg_proc'),'') || '|' ||
       pg_catalog.pg_get_userbyid(proc_row.proowner) || '|' ||
       proc_row.prosecdef::text || '|' || proc_row.provolatile::text || '|' ||
       coalesce(proc_row.proconfig::text,'') || '|' || proc_row.proacl::text,
       E'\n' order by namespace_row.nspname,proc_row.proname,
         pg_catalog.pg_get_function_identity_arguments(proc_row.oid))
     from pg_catalog.pg_proc as proc_row
     join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=proc_row.pronamespace
     where (namespace_row.nspname,proc_row.proname) in (
       ('connected_schedule_private','template_view_v2'),
       ('connected_schedule_private','chat_schedule_view_v2'),
       ('connected_schedule_private','claim_view_v2'),
       ('connected_schedule_private','completion_view_v2'),
       ('connected_schedule_private','scrub_cancelled_template_v2'),
       ('public','connected_operator_create_chat_schedule_v2'),
       ('public','connected_operator_read_chat_schedule_v2'),
       ('public','connected_app_claim_schedule_v2'),
       ('public','connected_app_read_schedule_claim_v2'),
       ('public','connected_app_finish_schedule_v2'),
       ('public','connected_app_read_schedule_finish_v2'),
       ('public','connected_app_read_schedule_template_v2'))),
    (select coalesce(pg_catalog.string_agg(
       index_namespace.nspname || '.' || index_class.relname || '|' ||
       pg_catalog.pg_get_indexdef(index_row.indexrelid) || '|' ||
       index_row.indisunique::text || '|' || index_row.indisvalid::text || '|' ||
       index_row.indisready::text,
       E'\n' order by index_namespace.nspname,index_class.relname),'NONE')
     from pg_catalog.pg_index as index_row
     join pg_catalog.pg_class as table_class
       on table_class.oid=index_row.indrelid
     join pg_catalog.pg_namespace as table_namespace
       on table_namespace.oid=table_class.relnamespace
     join pg_catalog.pg_class as index_class
       on index_class.oid=index_row.indexrelid
     join pg_catalog.pg_namespace as index_namespace
       on index_namespace.oid=index_class.relnamespace
     where table_namespace.nspname='connected_schedule_private'
       and table_class.relname in ('templates','run_completions')),
    (select pg_catalog.string_agg(constraint_row.conname || '|' ||
       pg_catalog.pg_get_constraintdef(constraint_row.oid,true),
       E'\n' order by constraint_row.conname)
     from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid in (
       pg_catalog.to_regclass('connected_schedule_private.templates'),
       pg_catalog.to_regclass('connected_schedule_private.run_completions'),
       pg_catalog.to_regclass('connected_app_private.schedules'))
       and (constraint_row.conrelid<>
         pg_catalog.to_regclass('connected_app_private.schedules')
         or constraint_row.conname='connected_app_schedules_template_v2_fkey')),
    (select pg_catalog.string_agg(trigger_row.tgname || '|' ||
       pg_catalog.pg_get_triggerdef(trigger_row.oid,true),E'\n' order by trigger_row.tgname)
     from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid=pg_catalog.to_regclass('connected_app_private.schedules')
       and trigger_row.tgname='connected_schedule_scrub_cancelled_template_v2'
       and not trigger_row.tgisinternal),
    (select pg_catalog.concat_ws('|',
       'policies=' || pg_catalog.count(*) filter (
         where catalog_row.kind='policy'),
       'rules=' || pg_catalog.count(*) filter (
         where catalog_row.kind='rule'),
       'triggers=' || pg_catalog.count(*) filter (
         where catalog_row.kind='trigger'))
     from (
       select 'policy'::text as kind from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid in (
         pg_catalog.to_regclass('connected_schedule_private.templates'),
         pg_catalog.to_regclass('connected_schedule_private.run_completions'))
       union all
       select 'rule'::text from pg_catalog.pg_rewrite as rule_row
       where rule_row.ev_class in (
         pg_catalog.to_regclass('connected_schedule_private.templates'),
         pg_catalog.to_regclass('connected_schedule_private.run_completions'))
         and rule_row.rulename<>'_RETURN'
       union all
       select 'trigger'::text from pg_catalog.pg_trigger as trigger_row
       where trigger_row.tgrelid in (
         pg_catalog.to_regclass('connected_schedule_private.templates'),
         pg_catalog.to_regclass('connected_schedule_private.run_completions'))
         and not trigger_row.tgisinternal
     ) as catalog_row),
    (select pg_catalog.concat_ws('|',
       'all_tables=' || (select pg_catalog.count(*)
         from pg_catalog.pg_publication as publication
         where publication.puballtables),
       'explicit=' || (select pg_catalog.count(*)
         from pg_catalog.pg_publication_rel as publication_relation
         where publication_relation.prrelid in (
           pg_catalog.to_regclass('connected_schedule_private.templates'),
           pg_catalog.to_regclass('connected_schedule_private.run_completions'))))),
    (select pg_catalog.string_agg(proc_row.proname || '|' || proc_row.proacl::text,
       E'\n' order by proc_row.proname)
     from pg_catalog.pg_proc as proc_row
     join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=proc_row.pronamespace
     where namespace_row.nspname='public' and proc_row.proname in (
       'connected_app_put_schedule_v1','connected_app_claim_schedule_v1',
       'connected_app_finish_schedule_v1','connected_app_operator_create_schedule_v1'))
  )) into target_fingerprint;
  if target_fingerprint <> '4b004a4a403058b443be9dac3c331950' then
    raise exception 'connected schedule-template postflight fingerprint: %',target_fingerprint
      using errcode='55000';
  end if;
end;
$postflight$;

commit;

select pg_catalog.set_config('search_path','pg_catalog,public',false);
