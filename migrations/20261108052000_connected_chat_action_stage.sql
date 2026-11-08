\set ON_ERROR_STOP on

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
select pg_catalog.set_config('quote_all_identifiers', 'off', false);

do $preflight$
declare
  target_any boolean;
  predecessor_turns text;
  predecessor_plan text;
  predecessor_preparations text;
  predecessor_jobs text;
  predecessor_sessions text;
  target_fingerprint text;
begin
  target_any :=
    pg_catalog.to_regprocedure(
      'public.connected_operator_prepare_chat_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamp with time zone,timestamp with time zone)'
    ) is not null
    or pg_catalog.to_regprocedure(
      'public.connected_operator_begin_chat_read_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text)'
    ) is not null
    or exists (
      select 1
      from pg_catalog.pg_attribute as attribute
      where attribute.attrelid = pg_catalog.to_regclass('connected_chat_private.turns')
        and attribute.attname in ('execution_request_id', 'schedule_request_id', 'schedule_id')
        and attribute.attnum > 0
        and not attribute.attisdropped
    );

  if target_any then
    select pg_catalog.md5(pg_catalog.string_agg(
      item, E'\n' order by item collate pg_catalog."C"
    ))
      into target_fingerprint
    from (
      select pg_catalog.concat_ws(
        '|', 'function', procedure.oid::pg_catalog.regprocedure::text,
        pg_catalog.pg_get_userbyid(procedure.proowner), procedure.prosecdef,
        procedure.provolatile, coalesce(procedure.proconfig::text, ''),
        coalesce(procedure.proacl::text, ''),
        coalesce(description.description, ''),
        pg_catalog.md5(pg_catalog.pg_get_functiondef(procedure.oid))
      ) as item
      from pg_catalog.pg_proc as procedure
      left join pg_catalog.pg_description as description
        on description.objoid = procedure.oid and description.objsubid = 0
      where procedure.oid in (
        pg_catalog.to_regprocedure(
          'public.connected_operator_prepare_chat_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamp with time zone,timestamp with time zone)'
        ),
        pg_catalog.to_regprocedure(
          'public.connected_operator_begin_chat_read_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text)'
        )
      )
      union all
      select pg_catalog.concat_ws(
        '|', 'relation', class.oid::pg_catalog.regclass::text,
        class.relkind, class.relrowsecurity, class.relforcerowsecurity,
        pg_catalog.pg_get_userbyid(class.relowner),
        coalesce(class.relacl::text, '')
      )
      from pg_catalog.pg_class as class
      where class.oid = pg_catalog.to_regclass('connected_chat_private.turns')
      union all
      select pg_catalog.concat_ws(
        '|', 'column', attribute.attnum, attribute.attname,
        pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
        attribute.attnotnull,
        coalesce(
          pg_catalog.pg_get_expr(default_value.adbin, default_value.adrelid), ''
        )
      )
      from pg_catalog.pg_attribute as attribute
      left join pg_catalog.pg_attrdef as default_value
        on default_value.adrelid = attribute.attrelid
       and default_value.adnum = attribute.attnum
      where attribute.attrelid = pg_catalog.to_regclass('connected_chat_private.turns')
        and attribute.attnum > 0 and not attribute.attisdropped
      union all
      select pg_catalog.concat_ws(
        '|', 'constraint', constraint_row.conname, constraint_row.contype,
        pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
      )
      from pg_catalog.pg_constraint as constraint_row
      where constraint_row.conrelid = pg_catalog.to_regclass('connected_chat_private.turns')
      union all
      select pg_catalog.concat_ws(
        '|', 'index', index_class.relname,
        pg_catalog.pg_get_indexdef(index_class.oid)
      )
      from pg_catalog.pg_class as index_class
      join pg_catalog.pg_index as index_row
        on index_row.indexrelid = index_class.oid
      where index_row.indrelid = pg_catalog.to_regclass('connected_chat_private.turns')
      union all
      select pg_catalog.concat_ws(
        '|', 'trigger', trigger_row.tgname,
        pg_catalog.pg_get_triggerdef(trigger_row.oid, true)
      )
      from pg_catalog.pg_trigger as trigger_row
      where trigger_row.tgrelid = pg_catalog.to_regclass('connected_chat_private.turns')
        and not trigger_row.tgisinternal
      union all
      select pg_catalog.concat_ws(
        '|', 'rule', rule_row.rulename,
        pg_catalog.pg_get_ruledef(rule_row.oid, true)
      )
      from pg_catalog.pg_rewrite as rule_row
      where rule_row.ev_class = pg_catalog.to_regclass('connected_chat_private.turns')
        and rule_row.rulename <> '_RETURN'
    ) as manifest;

    if target_fingerprint <> '423a6b0bd7f659ba37c729170c424dfc' then
      raise exception 'connected chat action-stage target drifted'
        using errcode = '55000';
    end if;
    return;
  end if;

  if pg_catalog.to_regclass('connected_chat_private.turns') is null
     or pg_catalog.to_regclass('connected_plan_private.operations') is null
     or pg_catalog.to_regclass('connected_app_private.action_preparations') is null
     or pg_catalog.to_regclass('public.chat_jobs') is null
     or pg_catalog.to_regclass('public.sessions') is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'connected_plan_private.lock_operation_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamp with time zone,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_prepare_action_v1(uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamp with time zone,timestamp with time zone)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'
     ) is null then
    raise exception 'connected chat action-stage predecessor is incomplete'
      using errcode = '55000';
  end if;

  if (
    select pg_catalog.md5(pg_catalog.pg_get_functiondef(procedure.oid))
    from pg_catalog.pg_proc as procedure
    where procedure.oid = 'connected_app_private.owner_lock_v1(uuid)'::pg_catalog.regprocedure
  ) <> 'd87239d86d46c32227ca4ec18eb1a767'
  or (
    select pg_catalog.md5(pg_catalog.pg_get_functiondef(procedure.oid))
    from pg_catalog.pg_proc as procedure
    where procedure.oid =
      'connected_plan_private.lock_operation_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,timestamp with time zone,timestamp with time zone)'::pg_catalog.regprocedure
  ) <> '62fcd73a42b03a42a26d9c619326182b'
  or (
    select pg_catalog.md5(pg_catalog.pg_get_functiondef(procedure.oid))
    from pg_catalog.pg_proc as procedure
    where procedure.oid =
      'public.connected_app_operator_prepare_action_v1(uuid,uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamp with time zone,timestamp with time zone)'::pg_catalog.regprocedure
  ) <> 'bf7882b5a29de81b9c7662e5d5a96864'
  or (
    select pg_catalog.md5(pg_catalog.pg_get_functiondef(procedure.oid))
    from pg_catalog.pg_proc as procedure
    where procedure.oid =
      'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'::pg_catalog.regprocedure
  ) <> '84cab781cb567453302359db9985204f' then
    raise exception 'connected chat action-stage predecessor function drifted'
      using errcode = '55000';
  end if;

  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
    into predecessor_turns
  from (
    select pg_catalog.concat_ws('|','rel',class.relkind,class.relrowsecurity,
      class.relforcerowsecurity,pg_catalog.pg_get_userbyid(class.relowner),
      coalesce(class.relacl::text,'')) as item
    from pg_catalog.pg_class as class
    where class.oid='connected_chat_private.turns'::pg_catalog.regclass
    union all
    select pg_catalog.concat_ws('|','col',attribute.attnum,attribute.attname,
      pg_catalog.format_type(attribute.atttypid,attribute.atttypmod),
      attribute.attnotnull,coalesce(
        pg_catalog.pg_get_expr(default_value.adbin,default_value.adrelid),''))
    from pg_catalog.pg_attribute as attribute
    left join pg_catalog.pg_attrdef as default_value
      on default_value.adrelid=attribute.attrelid and default_value.adnum=attribute.attnum
    where attribute.attrelid='connected_chat_private.turns'::pg_catalog.regclass
      and attribute.attnum>0 and not attribute.attisdropped
    union all
    select pg_catalog.concat_ws('|','con',constraint_row.conname,constraint_row.contype,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid='connected_chat_private.turns'::pg_catalog.regclass
    union all
    select pg_catalog.concat_ws('|','idx',index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid))
    from pg_catalog.pg_class as index_class
    join pg_catalog.pg_index as index_row on index_row.indexrelid=index_class.oid
    where index_row.indrelid='connected_chat_private.turns'::pg_catalog.regclass
    union all
    select pg_catalog.concat_ws('|','trg',trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid='connected_chat_private.turns'::pg_catalog.regclass
      and not trigger_row.tgisinternal
    union all
    select pg_catalog.concat_ws('|','rule',rule_row.rulename,
      pg_catalog.pg_get_ruledef(rule_row.oid,true))
    from pg_catalog.pg_rewrite as rule_row
    where rule_row.ev_class='connected_chat_private.turns'::pg_catalog.regclass
      and rule_row.rulename<>'_RETURN'
  ) as manifest;

  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
    into predecessor_plan
  from (
    select pg_catalog.concat_ws('|','rel',class.relkind,class.relrowsecurity,
      class.relforcerowsecurity,pg_catalog.pg_get_userbyid(class.relowner),
      coalesce(class.relacl::text,'')) as item
    from pg_catalog.pg_class as class
    where class.oid='connected_plan_private.operations'::pg_catalog.regclass
    union all
    select pg_catalog.concat_ws('|','col',attribute.attnum,attribute.attname,
      pg_catalog.format_type(attribute.atttypid,attribute.atttypmod),
      attribute.attnotnull,coalesce(
        pg_catalog.pg_get_expr(default_value.adbin,default_value.adrelid),''))
    from pg_catalog.pg_attribute as attribute
    left join pg_catalog.pg_attrdef as default_value
      on default_value.adrelid=attribute.attrelid and default_value.adnum=attribute.attnum
    where attribute.attrelid='connected_plan_private.operations'::pg_catalog.regclass
      and attribute.attnum>0 and not attribute.attisdropped
    union all
    select pg_catalog.concat_ws('|','con',constraint_row.conname,constraint_row.contype,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid='connected_plan_private.operations'::pg_catalog.regclass
    union all
    select pg_catalog.concat_ws('|','idx',index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid))
    from pg_catalog.pg_class as index_class
    join pg_catalog.pg_index as index_row on index_row.indexrelid=index_class.oid
    where index_row.indrelid='connected_plan_private.operations'::pg_catalog.regclass
    union all
    select pg_catalog.concat_ws('|','trg',trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid='connected_plan_private.operations'::pg_catalog.regclass
      and not trigger_row.tgisinternal
    union all
    select pg_catalog.concat_ws('|','rule',rule_row.rulename,
      pg_catalog.pg_get_ruledef(rule_row.oid,true))
    from pg_catalog.pg_rewrite as rule_row
    where rule_row.ev_class='connected_plan_private.operations'::pg_catalog.regclass
      and rule_row.rulename<>'_RETURN'
  ) as manifest;

  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
    into predecessor_preparations
  from (
    select pg_catalog.concat_ws('|','rel',class.relkind,class.relrowsecurity,
      class.relforcerowsecurity,pg_catalog.pg_get_userbyid(class.relowner),
      coalesce(class.relacl::text,'')) as item
    from pg_catalog.pg_class as class
    where class.oid='connected_app_private.action_preparations'::pg_catalog.regclass
    union all
    select pg_catalog.concat_ws('|','col',attribute.attnum,attribute.attname,
      pg_catalog.format_type(attribute.atttypid,attribute.atttypmod),
      attribute.attnotnull,coalesce(
        pg_catalog.pg_get_expr(default_value.adbin,default_value.adrelid),''))
    from pg_catalog.pg_attribute as attribute
    left join pg_catalog.pg_attrdef as default_value
      on default_value.adrelid=attribute.attrelid and default_value.adnum=attribute.attnum
    where attribute.attrelid='connected_app_private.action_preparations'::pg_catalog.regclass
      and attribute.attnum>0 and not attribute.attisdropped
    union all
    select pg_catalog.concat_ws('|','con',constraint_row.conname,constraint_row.contype,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid='connected_app_private.action_preparations'::pg_catalog.regclass
    union all
    select pg_catalog.concat_ws('|','idx',index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid))
    from pg_catalog.pg_class as index_class
    join pg_catalog.pg_index as index_row on index_row.indexrelid=index_class.oid
    where index_row.indrelid='connected_app_private.action_preparations'::pg_catalog.regclass
    union all
    select pg_catalog.concat_ws('|','trg',trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid='connected_app_private.action_preparations'::pg_catalog.regclass
      and not trigger_row.tgisinternal
    union all
    select pg_catalog.concat_ws('|','rule',rule_row.rulename,
      pg_catalog.pg_get_ruledef(rule_row.oid,true))
    from pg_catalog.pg_rewrite as rule_row
    where rule_row.ev_class='connected_app_private.action_preparations'::pg_catalog.regclass
      and rule_row.rulename<>'_RETURN'
  ) as manifest;

  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
    into predecessor_jobs
  from (
    select pg_catalog.concat_ws('|','rel',class.relkind,class.relrowsecurity,
      class.relforcerowsecurity,pg_catalog.pg_get_userbyid(class.relowner),
      coalesce(class.relacl::text,'')) as item
    from pg_catalog.pg_class as class where class.oid='public.chat_jobs'::pg_catalog.regclass
    union all select pg_catalog.concat_ws('|','col',attribute.attnum,attribute.attname,
      pg_catalog.format_type(attribute.atttypid,attribute.atttypmod),attribute.attnotnull,
      coalesce(pg_catalog.pg_get_expr(default_value.adbin,default_value.adrelid),''))
    from pg_catalog.pg_attribute as attribute left join pg_catalog.pg_attrdef as default_value
      on default_value.adrelid=attribute.attrelid and default_value.adnum=attribute.attnum
    where attribute.attrelid='public.chat_jobs'::pg_catalog.regclass
      and attribute.attnum>0 and not attribute.attisdropped
    union all select pg_catalog.concat_ws('|','con',constraint_row.conname,constraint_row.contype,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid='public.chat_jobs'::pg_catalog.regclass
    union all select pg_catalog.concat_ws('|','idx',index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid))
    from pg_catalog.pg_class as index_class join pg_catalog.pg_index as index_row
      on index_row.indexrelid=index_class.oid
    where index_row.indrelid='public.chat_jobs'::pg_catalog.regclass
    union all select pg_catalog.concat_ws('|','trg',trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid='public.chat_jobs'::pg_catalog.regclass and not trigger_row.tgisinternal
    union all select pg_catalog.concat_ws('|','rule',rule_row.rulename,
      pg_catalog.pg_get_ruledef(rule_row.oid,true))
    from pg_catalog.pg_rewrite as rule_row
    where rule_row.ev_class='public.chat_jobs'::pg_catalog.regclass and rule_row.rulename<>'_RETURN'
  ) as manifest;

  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
    into predecessor_sessions
  from (
    select pg_catalog.concat_ws('|','rel',class.relkind,class.relrowsecurity,
      class.relforcerowsecurity,pg_catalog.pg_get_userbyid(class.relowner),
      coalesce(class.relacl::text,'')) as item
    from pg_catalog.pg_class as class where class.oid='public.sessions'::pg_catalog.regclass
    union all select pg_catalog.concat_ws('|','col',attribute.attnum,attribute.attname,
      pg_catalog.format_type(attribute.atttypid,attribute.atttypmod),attribute.attnotnull,
      coalesce(pg_catalog.pg_get_expr(default_value.adbin,default_value.adrelid),''))
    from pg_catalog.pg_attribute as attribute left join pg_catalog.pg_attrdef as default_value
      on default_value.adrelid=attribute.attrelid and default_value.adnum=attribute.attnum
    where attribute.attrelid='public.sessions'::pg_catalog.regclass
      and attribute.attnum>0 and not attribute.attisdropped
    union all select pg_catalog.concat_ws('|','con',constraint_row.conname,constraint_row.contype,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid='public.sessions'::pg_catalog.regclass
    union all select pg_catalog.concat_ws('|','idx',index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid))
    from pg_catalog.pg_class as index_class join pg_catalog.pg_index as index_row
      on index_row.indexrelid=index_class.oid
    where index_row.indrelid='public.sessions'::pg_catalog.regclass
    union all select pg_catalog.concat_ws('|','trg',trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid='public.sessions'::pg_catalog.regclass and not trigger_row.tgisinternal
    union all select pg_catalog.concat_ws('|','rule',rule_row.rulename,
      pg_catalog.pg_get_ruledef(rule_row.oid,true))
    from pg_catalog.pg_rewrite as rule_row
    where rule_row.ev_class='public.sessions'::pg_catalog.regclass and rule_row.rulename<>'_RETURN'
  ) as manifest;

  if predecessor_turns <> '8360df01e00b0ae419a033bcd3513c40'
     or predecessor_plan <> '75e9c0dcc65ff8d3d5fea19715f46816'
     or predecessor_preparations <> '0a4e963ecb19d77aa2dadfeb2531a418'
     or predecessor_jobs <> '99254eac3be4d204280d0238a400c32d'
     or predecessor_sessions <> '384d6146c49e8362ad7abb8ff99af714' then
    raise exception 'connected chat action-stage predecessor catalog drifted'
      using errcode = '55000';
  end if;
end;
$preflight$;

begin;

alter table connected_chat_private.turns
  add column if not exists execution_request_id uuid,
  add column if not exists schedule_request_id uuid,
  add column if not exists schedule_id uuid;

create unique index if not exists connected_chat_turns_execution_request_id_key
  on connected_chat_private.turns(execution_request_id)
  where execution_request_id is not null;
create unique index if not exists connected_chat_turns_schedule_request_id_key
  on connected_chat_private.turns(schedule_request_id)
  where schedule_request_id is not null;
create unique index if not exists connected_chat_turns_schedule_id_key
  on connected_chat_private.turns(schedule_id)
  where schedule_id is not null;

do $constraints$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid='connected_chat_private.turns'::pg_catalog.regclass
      and conname='connected_chat_turns_action_binding_check'
  ) then
    alter table connected_chat_private.turns
      add constraint connected_chat_turns_action_binding_check check (
        (preparation_request_id is null) = (action_id is null)
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid='connected_chat_private.turns'::pg_catalog.regclass
      and conname='connected_chat_turns_schedule_binding_check'
  ) then
    alter table connected_chat_private.turns
      add constraint connected_chat_turns_schedule_binding_check check (
        (schedule_request_id is null) = (schedule_id is null)
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid='connected_chat_private.turns'::pg_catalog.regclass
      and conname='connected_chat_turns_single_work_binding_check'
  ) then
    alter table connected_chat_private.turns
      add constraint connected_chat_turns_single_work_binding_check check (
        not (action_id is not null and schedule_id is not null)
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid='connected_chat_private.turns'::pg_catalog.regclass
      and conname='connected_chat_turns_stage_binding_check'
  ) then
    alter table connected_chat_private.turns
      add constraint connected_chat_turns_stage_binding_check check (
        stage not in ('prepared','executing')
        or action_id is not null
        or schedule_id is not null
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid='connected_chat_private.turns'::pg_catalog.regclass
      and conname='connected_chat_turns_execution_binding_check'
  ) then
    alter table connected_chat_private.turns
      add constraint connected_chat_turns_execution_binding_check check (
        (execution_request_id is null and stage <> 'executing')
        or (
          execution_request_id is not null
          and action_id is not null
          and stage in ('executing','terminal','effect_unknown')
        )
      );
  end if;
end;
$constraints$;

comment on column connected_chat_private.turns.execution_request_id is
  'ASK_CRUMP_CONNECTED_CHAT_READ_EXECUTION_FENCE_CONTENT_FREE';
comment on column connected_chat_private.turns.schedule_request_id is
  'ASK_CRUMP_CONNECTED_CHAT_SCHEDULE_COMMAND_BINDING_CONTENT_FREE';
comment on column connected_chat_private.turns.schedule_id is
  'ASK_CRUMP_CONNECTED_CHAT_DURABLE_SCHEDULE_BINDING_CONTENT_FREE';

create or replace function public.connected_operator_prepare_chat_action_v1(
  p_owner_id uuid,
  p_session_id uuid,
  p_chat_id uuid,
  p_message_id uuid,
  p_turn_id uuid,
  p_claim_token uuid,
  p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text,
  p_request_id uuid,
  p_session_binding_sha256 text,
  p_command_binding_sha256 text,
  p_grant_id uuid,
  p_action_id uuid,
  p_task_id uuid,
  p_connection_id uuid,
  p_payload_id uuid,
  p_payload_reference_binding_sha256 text,
  p_provider text,
  p_resource text,
  p_action text,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,
  p_task_state_revision bigint,
  p_parameters_payload_id uuid,
  p_parameters_reference_binding_sha256 text,
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
  now_at timestamptz := pg_catalog.clock_timestamp();
  session_row public.sessions%rowtype;
  job_row public.chat_jobs%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  operation_row connected_plan_private.operations%rowtype;
  preparation jsonb;
begin
  if p_owner_id is null or p_session_id is null or p_chat_id is null
     or p_message_id is null or p_turn_id is null or p_claim_token is null
     or p_request_id is null or p_action_id is null
     or p_origin_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_request_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid connected chat action preparation binding'
      using errcode='22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select session.* into session_row
  from public.sessions as session
  where session.id=p_session_id and session.user_id=p_owner_id
  for share;
  if not found or session_row.revoked_at is not null or session_row.expires_at<=now_at then
    raise exception 'connected chat action session changed' using errcode='55000';
  end if;

  select job.* into job_row
  from public.chat_jobs as job
  where job.user_id=p_owner_id and job.message_id=p_message_id
  for update;
  if not found or job_row.chat_id<>p_chat_id or job_row.status<>'processing'
     or job_row.claim_token<>p_claim_token then
    raise exception 'connected chat action claim changed' using errcode='55000';
  end if;

  select turn.* into turn_row
  from connected_chat_private.turns as turn
  where turn.turn_id=p_turn_id and turn.job_id=job_row.id
  for update;
  if not found or turn_row.owner_id<>p_owner_id or turn_row.chat_id<>p_chat_id
     or turn_row.message_id<>p_message_id
     or turn_row.origin_session_binding_sha256<>p_origin_session_binding_sha256
     or turn_row.request_binding_sha256<>p_request_binding_sha256
     or turn_row.stage not in ('planned','prepared','executing')
     or (turn_row.stage in ('prepared','executing') and (
       turn_row.preparation_request_id is distinct from p_request_id
       or turn_row.action_id is distinct from p_action_id
     )) then
    raise exception 'connected chat action turn changed' using errcode='55000';
  end if;

  select operation.* into operation_row
  from connected_plan_private.operations as operation
  where operation.planning_id=turn_row.planning_id and operation.turn_id=p_turn_id
  for update;
  if not found or operation_row.state<>'settled'
     or operation_row.disposition<>'action'
     or operation_row.owner_id<>p_owner_id or operation_row.session_id<>p_session_id
     or operation_row.chat_id<>p_chat_id or operation_row.message_id<>p_message_id
     or operation_row.claim_token<>p_claim_token
     or operation_row.origin_session_binding_sha256<>p_origin_session_binding_sha256
     or operation_row.request_binding_sha256<>p_request_binding_sha256
     or operation_row.connection_id is distinct from p_connection_id
     or operation_row.provider is distinct from p_provider
     or operation_row.resource is distinct from p_resource
     or operation_row.action is distinct from p_action
     or operation_row.payload_id is distinct from turn_row.plan_payload_id
     or operation_row.payload_sha256 is distinct from turn_row.plan_payload_sha256
     or operation_row.payload_reference_binding_sha256
        is distinct from turn_row.plan_reference_binding_sha256
     or operation_row.expires_at<=now_at or p_expires_at>operation_row.expires_at then
    raise exception 'connected chat settled plan changed' using errcode='55000';
  end if;

  if p_payload_id<>operation_row.payload_id then
    raise exception 'connected chat plan payload changed' using errcode='55000';
  end if;

  preparation := public.connected_app_operator_prepare_action_v1(
    p_request_id, p_owner_id, p_session_id, p_session_binding_sha256,
    p_command_binding_sha256, p_grant_id, p_action_id, p_task_id,
    p_turn_id, p_connection_id, p_provider, p_resource, p_action,
    p_authorization_revision, p_authorization_snapshot_sha256,
    p_granted_actions_sha256, p_granted_scopes_sha256,
    p_task_state_revision, p_parameters_payload_id,
    p_parameters_reference_binding_sha256, p_parameters_sha256,
    p_resource_version_sha256, p_policy_version, p_approval_id,
    p_approval_binding_sha256, p_preview_payload_id,
    p_preview_reference_binding_sha256, p_preview_sha256,
    p_requested_at, p_expires_at
  );

  if preparation->>'request_id'<>p_request_id::text
     or preparation->>'action_id'<>p_action_id::text
     or preparation->>'turn_id'<>p_turn_id::text
     or preparation->>'connection_id'<>p_connection_id::text
     or preparation->>'command_binding_sha256'<>p_command_binding_sha256 then
    raise exception 'connected chat action preparation result drifted'
      using errcode='55000';
  end if;

  if turn_row.stage='planned' then
    update connected_chat_private.turns as turn
    set stage='prepared', preparation_request_id=p_request_id,
        action_id=p_action_id, updated_at=now_at
    where turn.turn_id=p_turn_id and turn.stage='planned'
      and turn.preparation_request_id is null and turn.action_id is null;
    if not found then
      raise exception 'connected chat action lost its turn fence'
        using errcode='55000';
    end if;
  end if;

  return preparation;
end;
$fn$;

comment on function public.connected_operator_prepare_chat_action_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,
  text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,
  text,text,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_CHAT_PLAN_TO_PREPARATION_V1_ATOMIC_EXACT_BINDING';

create or replace function public.connected_operator_begin_chat_read_v1(
  p_execution_request_id uuid,
  p_owner_id uuid,
  p_session_id uuid,
  p_chat_id uuid,
  p_message_id uuid,
  p_turn_id uuid,
  p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text,
  p_claim_token uuid,
  p_preparation_request_id uuid,
  p_action_id uuid,
  p_command_binding_sha256 text
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
  preparation_row connected_app_private.action_preparations%rowtype;
begin
  if p_execution_request_id is null or p_owner_id is null or p_session_id is null
     or p_chat_id is null or p_message_id is null or p_turn_id is null
     or p_claim_token is null or p_preparation_request_id is null or p_action_id is null
     or p_origin_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_request_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_command_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid connected chat read-execution binding'
      using errcode='22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select session.* into session_row
  from public.sessions as session
  where session.id=p_session_id and session.user_id=p_owner_id
  for share;
  if not found or session_row.revoked_at is not null or session_row.expires_at<=now_at then
    raise exception 'connected chat read session changed' using errcode='55000';
  end if;
  select job.* into job_row
  from public.chat_jobs as job
  where job.user_id=p_owner_id and job.message_id=p_message_id
  for update;
  if not found or job_row.chat_id<>p_chat_id or job_row.status<>'processing'
     or job_row.claim_token<>p_claim_token then
    raise exception 'connected chat read claim changed' using errcode='55000';
  end if;
  select turn.* into turn_row
  from connected_chat_private.turns as turn
  where turn.turn_id=p_turn_id and turn.job_id=job_row.id
  for update;
  if not found or turn_row.owner_id<>p_owner_id or turn_row.chat_id<>p_chat_id
     or turn_row.message_id<>p_message_id
     or turn_row.origin_session_binding_sha256<>p_origin_session_binding_sha256
     or turn_row.request_binding_sha256<>p_request_binding_sha256
     or turn_row.stage not in ('prepared','executing')
     or turn_row.preparation_request_id is distinct from p_preparation_request_id
     or turn_row.action_id is distinct from p_action_id
     or (turn_row.stage='executing'
         and turn_row.execution_request_id is distinct from p_execution_request_id) then
    raise exception 'connected chat read turn changed' using errcode='55000';
  end if;
  select preparation.* into preparation_row
  from connected_app_private.action_preparations as preparation
  where preparation.request_id=p_preparation_request_id
  for update;
  if not found or preparation_row.owner_id<>p_owner_id
     or preparation_row.turn_id<>p_turn_id or preparation_row.action_id<>p_action_id
     or preparation_row.session_binding_sha256<>turn_row.origin_session_binding_sha256
     or preparation_row.command_binding_sha256<>p_command_binding_sha256
     or preparation_row.status<>'ready' or preparation_row.mutates_external_state
     or preparation_row.expires_at<=now_at then
    raise exception 'connected chat read preparation changed' using errcode='55000';
  end if;

  if turn_row.stage='prepared' then
    update connected_chat_private.turns as turn
    set stage='executing', execution_request_id=p_execution_request_id,
        updated_at=now_at
    where turn.turn_id=p_turn_id and turn.stage='prepared'
      and turn.execution_request_id is null;
    if not found then
      raise exception 'connected chat read lost its turn fence'
        using errcode='55000';
    end if;
  end if;
  return pg_catalog.jsonb_build_object(
    'stage','executing',
    'execution_request_id',p_execution_request_id,
    'preparation_request_id',p_preparation_request_id,
    'action_id',p_action_id,
    'updated_at',now_at
  );
end;
$fn$;

comment on function public.connected_operator_begin_chat_read_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text
) is 'ASK_CRUMP_CONNECTED_CHAT_PREPARED_TO_EXECUTING_V1_NO_PROVIDER_EFFECT';

revoke all on function public.connected_operator_prepare_chat_action_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,
  text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,
  text,text,timestamptz,timestamptz
) from public,anon,authenticated;
revoke all on function public.connected_operator_begin_chat_read_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text
) from public,anon,authenticated;
grant execute on function public.connected_operator_prepare_chat_action_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,
  text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,
  text,text,timestamptz,timestamptz
) to service_role;
grant execute on function public.connected_operator_begin_chat_read_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text
) to service_role;

do $postflight$
declare
  target_fingerprint text;
begin
  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
    into target_fingerprint
  from (
    select pg_catalog.concat_ws('|','function',procedure.oid::pg_catalog.regprocedure::text,
      pg_catalog.pg_get_userbyid(procedure.proowner),procedure.prosecdef,
      procedure.provolatile,coalesce(procedure.proconfig::text,''),
      coalesce(procedure.proacl::text,''),
      coalesce(description.description,''),
      pg_catalog.md5(pg_catalog.pg_get_functiondef(procedure.oid))) as item
    from pg_catalog.pg_proc as procedure
    left join pg_catalog.pg_description as description
      on description.objoid=procedure.oid and description.objsubid=0
    where procedure.oid in (
      'public.connected_operator_prepare_chat_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamp with time zone,timestamp with time zone)'::pg_catalog.regprocedure,
      'public.connected_operator_begin_chat_read_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,uuid,text)'::pg_catalog.regprocedure
    )
    union all select pg_catalog.concat_ws('|','relation',class.oid::pg_catalog.regclass::text,
      class.relkind,class.relrowsecurity,class.relforcerowsecurity,
      pg_catalog.pg_get_userbyid(class.relowner),coalesce(class.relacl::text,''))
    from pg_catalog.pg_class as class where class.oid='connected_chat_private.turns'::pg_catalog.regclass
    union all select pg_catalog.concat_ws('|','column',attribute.attnum,attribute.attname,
      pg_catalog.format_type(attribute.atttypid,attribute.atttypmod),attribute.attnotnull,
      coalesce(pg_catalog.pg_get_expr(default_value.adbin,default_value.adrelid),''))
    from pg_catalog.pg_attribute as attribute left join pg_catalog.pg_attrdef as default_value
      on default_value.adrelid=attribute.attrelid and default_value.adnum=attribute.attnum
    where attribute.attrelid='connected_chat_private.turns'::pg_catalog.regclass
      and attribute.attnum>0 and not attribute.attisdropped
    union all select pg_catalog.concat_ws('|','constraint',constraint_row.conname,
      constraint_row.contype,pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid='connected_chat_private.turns'::pg_catalog.regclass
    union all select pg_catalog.concat_ws('|','index',index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid))
    from pg_catalog.pg_class as index_class join pg_catalog.pg_index as index_row
      on index_row.indexrelid=index_class.oid
    where index_row.indrelid='connected_chat_private.turns'::pg_catalog.regclass
    union all select pg_catalog.concat_ws('|','trigger',trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid='connected_chat_private.turns'::pg_catalog.regclass
      and not trigger_row.tgisinternal
    union all select pg_catalog.concat_ws('|','rule',rule_row.rulename,
      pg_catalog.pg_get_ruledef(rule_row.oid,true))
    from pg_catalog.pg_rewrite as rule_row
    where rule_row.ev_class='connected_chat_private.turns'::pg_catalog.regclass
      and rule_row.rulename<>'_RETURN'
  ) as manifest;

  if target_fingerprint <> '423a6b0bd7f659ba37c729170c424dfc'
     or pg_catalog.has_function_privilege(
       'public','public.connected_operator_prepare_chat_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamp with time zone,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'anon','public.connected_operator_prepare_chat_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamp with time zone,timestamp with time zone)','execute')
     or pg_catalog.has_function_privilege(
       'authenticated','public.connected_operator_prepare_chat_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamp with time zone,timestamp with time zone)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_operator_prepare_chat_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,bigint,uuid,text,text,text,text,uuid,text,uuid,text,text,timestamp with time zone,timestamp with time zone)','execute') then
    raise exception 'connected chat action-stage postflight drifted'
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
