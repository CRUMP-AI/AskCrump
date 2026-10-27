-- Restore the sessions -> users ownership invariant that fresh Ask Crump
-- installs have always declared.  Some legacy installs predated the inline
-- foreign key and the original compatibility path added columns without
-- reconciling the constraint.
--
-- The production migration runner owns the transaction boundary.  Lock both
-- relations before inspecting existing rows so the orphan check, NOT VALID
-- install, and validation are one race-free operation.

set local lock_timeout = '5s';
set local statement_timeout = '30s';
set local search_path = pg_catalog;

do $preflight$
declare
  v_users regclass := pg_catalog.to_regclass('public.users');
  v_sessions regclass := pg_catalog.to_regclass('public.sessions');
begin
  if current_user <> 'postgres' then
    raise exception 'Sessions-user FK migration must run as postgres.'
      using errcode = '42501';
  end if;

  if v_users is null or v_sessions is null then
    raise exception 'Sessions-user FK prerequisite tables are missing.'
      using errcode = '55000';
  end if;
end;
$preflight$;

lock table public.users, public.sessions in share row exclusive mode;

do $locked_preflight$
declare
  v_users regclass := 'public.users'::regclass;
  v_sessions regclass := 'public.sessions'::regclass;
  v_users_id_attnum smallint;
  v_sessions_id_attnum smallint;
  v_sessions_user_id_attnum smallint;
  v_constraint_oid oid;
  v_support_index_oid oid;
begin
  if exists (
    select 1
      from pg_catalog.pg_class as relation_row
     where relation_row.oid in (v_users, v_sessions)
       and (
         relation_row.relkind <> 'r'
         or pg_catalog.pg_get_userbyid(relation_row.relowner) <> 'postgres'
         or relation_row.relrowsecurity is not true
       )
  ) then
    raise exception 'Sessions-user FK table ownership, kind, or RLS drifted.'
      using errcode = '55000';
  end if;

  if (
    select pg_catalog.count(*)
      from information_schema.columns
     where table_schema = 'public'
       and (
         (
           table_name = 'users'
           and column_name = 'id'
           and data_type = 'uuid'
           and is_nullable = 'NO'
         )
         or (
           table_name = 'sessions'
           and column_name = 'id'
           and data_type = 'uuid'
           and is_nullable = 'NO'
         )
         or (
           table_name = 'sessions'
           and column_name = 'user_id'
           and data_type = 'uuid'
           and is_nullable = 'NO'
         )
       )
  ) <> 3 then
    raise exception 'Sessions-user FK prerequisite columns are missing or drifted.'
      using errcode = '55000';
  end if;

  select attribute_row.attnum
    into v_users_id_attnum
    from pg_catalog.pg_attribute as attribute_row
   where attribute_row.attrelid = v_users
     and attribute_row.attname = 'id'
     and attribute_row.attisdropped is false;

  select attribute_row.attnum
    into v_sessions_id_attnum
    from pg_catalog.pg_attribute as attribute_row
   where attribute_row.attrelid = v_sessions
     and attribute_row.attname = 'id'
     and attribute_row.attisdropped is false;

  select attribute_row.attnum
    into v_sessions_user_id_attnum
    from pg_catalog.pg_attribute as attribute_row
   where attribute_row.attrelid = v_sessions
     and attribute_row.attname = 'user_id'
     and attribute_row.attisdropped is false;

  if not exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
      join pg_catalog.pg_index as index_row
        on index_row.indexrelid = constraint_row.conindid
     where constraint_row.conrelid = v_users
       and constraint_row.conname = 'users_pkey'
       and constraint_row.contype = 'p'
       and constraint_row.conkey = array[v_users_id_attnum]::smallint[]
       and constraint_row.convalidated
       and index_row.indrelid = v_users
       and index_row.indisprimary
       and index_row.indisunique
       and index_row.indisvalid
       and index_row.indisready
  ) or not exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
      join pg_catalog.pg_index as index_row
        on index_row.indexrelid = constraint_row.conindid
     where constraint_row.conrelid = v_sessions
       and constraint_row.conname = 'sessions_pkey'
       and constraint_row.contype = 'p'
       and constraint_row.conkey = array[v_sessions_id_attnum]::smallint[]
       and constraint_row.convalidated
       and index_row.indrelid = v_sessions
       and index_row.indisprimary
       and index_row.indisunique
       and index_row.indisvalid
       and index_row.indisready
  ) then
    raise exception 'Sessions-user FK prerequisite primary keys are missing or drifted.'
      using errcode = '55000';
  end if;

  select constraint_row.oid
    into v_constraint_oid
    from pg_catalog.pg_constraint as constraint_row
   where constraint_row.conrelid = v_sessions
     and constraint_row.conname = 'sessions_user_id_fkey';

  v_support_index_oid := pg_catalog.to_regclass(
    'public.sessions_user_id_fk_idx'
  );

  if v_support_index_oid is not null and coalesce((
    select index_row.indrelid <> v_sessions
      or index_row.indisvalid is not true
      or index_row.indisready is not true
      or index_row.indislive is not true
      or index_row.indisunique is true
      or index_row.indisprimary is true
      or index_row.indisexclusion is true
      or index_row.indnkeyatts <> 1
      or index_row.indnatts <> 1
      or index_row.indpred is not null
      or index_row.indexprs is not null
      or access_method.amname <> 'btree'
      or pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true)
           <> 'user_id'
      from pg_catalog.pg_index as index_row
      join pg_catalog.pg_class as index_class
        on index_class.oid = index_row.indexrelid
      join pg_catalog.pg_am as access_method
        on access_method.oid = index_class.relam
     where index_row.indexrelid = v_support_index_oid
  ), true) then
    raise exception 'Sessions-user FK support index exists with conflicting semantics.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_sessions
       and constraint_row.conname = 'sessions_user_id_fkey'
       and (
         constraint_row.contype <> 'f'
         or constraint_row.confrelid <> v_users
         or constraint_row.conkey
              <> array[v_sessions_user_id_attnum]::smallint[]
         or constraint_row.confkey <> array[v_users_id_attnum]::smallint[]
         or constraint_row.confupdtype <> 'a'
         or constraint_row.confdeltype <> 'c'
         or constraint_row.confmatchtype <> 's'
         or constraint_row.condeferrable
         or constraint_row.condeferred
         or constraint_row.conparentid <> 0
       )
  ) then
    raise exception 'Named sessions-user FK exists with conflicting semantics.'
      using errcode = '55000';
  end if;

  if v_constraint_oid is not null and not (
    select pg_catalog.count(*) = 4
       and pg_catalog.count(*) filter (
             where trigger_row.tgisinternal
               and trigger_row.tgenabled = 'O'
               and trigger_row.tgparentid = 0
           ) = 4
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = v_sessions
               and trigger_row.tgtype = 5
               and function_row.pronamespace = 'pg_catalog'::regnamespace
               and function_row.proname = 'RI_FKey_check_ins'
           ) = 1
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = v_sessions
               and trigger_row.tgtype = 17
               and function_row.pronamespace = 'pg_catalog'::regnamespace
               and function_row.proname = 'RI_FKey_check_upd'
           ) = 1
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = v_users
               and trigger_row.tgtype = 9
               and function_row.pronamespace = 'pg_catalog'::regnamespace
               and function_row.proname = 'RI_FKey_cascade_del'
           ) = 1
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = v_users
               and trigger_row.tgtype = 17
               and function_row.pronamespace = 'pg_catalog'::regnamespace
               and function_row.proname = 'RI_FKey_noaction_upd'
           ) = 1
      from pg_catalog.pg_trigger as trigger_row
      join pg_catalog.pg_proc as function_row
        on function_row.oid = trigger_row.tgfoid
     where trigger_row.tgconstraint = v_constraint_oid
  ) then
    raise exception 'Sessions-user FK enforcement triggers are missing or disabled.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_sessions
       and constraint_row.contype = 'f'
       and v_sessions_user_id_attnum = any(constraint_row.conkey)
       and constraint_row.conname <> 'sessions_user_id_fkey'
  ) then
    raise exception 'A conflicting sessions.user_id foreign key already exists.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from public.sessions as session_row
      left join public.users as user_row
        on user_row.id = session_row.user_id
     where user_row.id is null
  ) then
    raise exception 'Orphan sessions must be remediated before FK installation.'
      using errcode = '23503';
  end if;
end;
$locked_preflight$;

do $install_support_index$
begin
  if pg_catalog.to_regclass('public.sessions_user_id_fk_idx') is null then
    create index sessions_user_id_fk_idx
      on public.sessions using btree (user_id);
  end if;
end;
$install_support_index$;

do $install$
begin
  if not exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = 'public.sessions'::regclass
       and constraint_row.conname = 'sessions_user_id_fkey'
  ) then
    alter table public.sessions
      add constraint sessions_user_id_fkey
      foreign key (user_id)
      references public.users (id)
      on delete cascade
      not valid;
  end if;
end;
$install$;

do $validate$
begin
  if exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = 'public.sessions'::regclass
       and constraint_row.conname = 'sessions_user_id_fkey'
       and constraint_row.convalidated is false
  ) then
    alter table public.sessions
      validate constraint sessions_user_id_fkey;
  end if;
end;
$validate$;

do $postflight$
declare
  v_users regclass := 'public.users'::regclass;
  v_sessions regclass := 'public.sessions'::regclass;
  v_users_id_attnum smallint;
  v_sessions_user_id_attnum smallint;
  v_constraint_oid oid;
  v_support_index_oid oid;
begin
  select attribute_row.attnum
    into v_users_id_attnum
    from pg_catalog.pg_attribute as attribute_row
   where attribute_row.attrelid = v_users
     and attribute_row.attname = 'id'
     and attribute_row.attisdropped is false;

  select attribute_row.attnum
    into v_sessions_user_id_attnum
    from pg_catalog.pg_attribute as attribute_row
   where attribute_row.attrelid = v_sessions
     and attribute_row.attname = 'user_id'
     and attribute_row.attisdropped is false;

  if (
    select pg_catalog.count(*)
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_sessions
       and constraint_row.contype = 'f'
       and v_sessions_user_id_attnum = any(constraint_row.conkey)
       and constraint_row.conname = 'sessions_user_id_fkey'
       and constraint_row.confrelid = v_users
       and constraint_row.conkey
            = array[v_sessions_user_id_attnum]::smallint[]
       and constraint_row.confkey = array[v_users_id_attnum]::smallint[]
       and constraint_row.confupdtype = 'a'
       and constraint_row.confdeltype = 'c'
       and constraint_row.confmatchtype = 's'
       and constraint_row.condeferrable is false
       and constraint_row.condeferred is false
       and constraint_row.convalidated
       and constraint_row.conparentid = 0
  ) <> 1 then
    raise exception 'Sessions-user FK postflight semantics are incomplete or drifted.'
      using errcode = '55000';
  end if;

  select constraint_row.oid
    into v_constraint_oid
    from pg_catalog.pg_constraint as constraint_row
   where constraint_row.conrelid = v_sessions
     and constraint_row.conname = 'sessions_user_id_fkey';

  v_support_index_oid := pg_catalog.to_regclass(
    'public.sessions_user_id_fk_idx'
  );

  if v_support_index_oid is null or coalesce((
    select index_row.indrelid <> v_sessions
      or index_row.indisvalid is not true
      or index_row.indisready is not true
      or index_row.indislive is not true
      or index_row.indisunique is true
      or index_row.indisprimary is true
      or index_row.indisexclusion is true
      or index_row.indnkeyatts <> 1
      or index_row.indnatts <> 1
      or index_row.indpred is not null
      or index_row.indexprs is not null
      or access_method.amname <> 'btree'
      or pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true)
           <> 'user_id'
      from pg_catalog.pg_index as index_row
      join pg_catalog.pg_class as index_class
        on index_class.oid = index_row.indexrelid
      join pg_catalog.pg_am as access_method
        on access_method.oid = index_class.relam
     where index_row.indexrelid = v_support_index_oid
  ), true) then
    raise exception 'Sessions-user FK support index postflight is incomplete or drifted.'
      using errcode = '55000';
  end if;

  if not (
    select pg_catalog.count(*) = 4
       and pg_catalog.count(*) filter (
             where trigger_row.tgisinternal
               and trigger_row.tgenabled = 'O'
               and trigger_row.tgparentid = 0
           ) = 4
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = v_sessions
               and trigger_row.tgtype = 5
               and function_row.pronamespace = 'pg_catalog'::regnamespace
               and function_row.proname = 'RI_FKey_check_ins'
           ) = 1
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = v_sessions
               and trigger_row.tgtype = 17
               and function_row.pronamespace = 'pg_catalog'::regnamespace
               and function_row.proname = 'RI_FKey_check_upd'
           ) = 1
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = v_users
               and trigger_row.tgtype = 9
               and function_row.pronamespace = 'pg_catalog'::regnamespace
               and function_row.proname = 'RI_FKey_cascade_del'
           ) = 1
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = v_users
               and trigger_row.tgtype = 17
               and function_row.pronamespace = 'pg_catalog'::regnamespace
               and function_row.proname = 'RI_FKey_noaction_upd'
           ) = 1
      from pg_catalog.pg_trigger as trigger_row
      join pg_catalog.pg_proc as function_row
        on function_row.oid = trigger_row.tgfoid
     where trigger_row.tgconstraint = v_constraint_oid
  ) then
    raise exception 'Sessions-user FK postflight triggers are incomplete or disabled.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_class as relation_row
     where relation_row.oid in (v_users, v_sessions)
       and (
         pg_catalog.pg_get_userbyid(relation_row.relowner) <> 'postgres'
         or relation_row.relrowsecurity is not true
       )
  ) then
    raise exception 'Sessions-user FK migration changed table owner or RLS state.'
      using errcode = '55000';
  end if;
end;
$postflight$;
