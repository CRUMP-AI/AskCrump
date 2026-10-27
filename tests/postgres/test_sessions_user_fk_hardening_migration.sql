\set ON_ERROR_STOP on

do $$
declare
  v_users_id_attnum smallint;
  v_sessions_user_id_attnum smallint;
  v_constraint_oid oid;
begin
  select attnum into v_users_id_attnum
    from pg_catalog.pg_attribute
   where attrelid = 'public.users'::regclass
     and attname = 'id'
     and attisdropped is false;

  select attnum into v_sessions_user_id_attnum
    from pg_catalog.pg_attribute
   where attrelid = 'public.sessions'::regclass
     and attname = 'user_id'
     and attisdropped is false;

  if (
    select pg_catalog.count(*)
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = 'public.sessions'::regclass
       and constraint_row.conname = 'sessions_user_id_fkey'
       and constraint_row.contype = 'f'
       and constraint_row.confrelid = 'public.users'::regclass
       and constraint_row.conkey = array[v_sessions_user_id_attnum]::smallint[]
       and constraint_row.confkey = array[v_users_id_attnum]::smallint[]
       and constraint_row.confupdtype = 'a'
       and constraint_row.confdeltype = 'c'
       and constraint_row.confmatchtype = 's'
       and constraint_row.condeferrable is false
       and constraint_row.condeferred is false
       and constraint_row.convalidated
       and constraint_row.conparentid = 0
  ) <> 1 then
    raise exception 'Expected exact validated sessions-user cascade FK.';
  end if;

  select constraint_row.oid
    into v_constraint_oid
    from pg_catalog.pg_constraint as constraint_row
   where constraint_row.conrelid = 'public.sessions'::regclass
     and constraint_row.conname = 'sessions_user_id_fkey';

  if not (
    select pg_catalog.count(*) = 4
       and pg_catalog.count(*) filter (
             where trigger_row.tgisinternal
               and trigger_row.tgenabled = 'O'
               and trigger_row.tgparentid = 0
           ) = 4
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = 'public.sessions'::regclass
               and trigger_row.tgtype in (5, 17)
           ) = 2
       and pg_catalog.count(*) filter (
             where trigger_row.tgrelid = 'public.users'::regclass
               and trigger_row.tgtype in (9, 17)
           ) = 2
      from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgconstraint = v_constraint_oid
  ) then
    raise exception 'Expected four enabled internal sessions-user RI triggers.';
  end if;

  if (
    select pg_catalog.count(*)
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = 'public.sessions'::regclass
       and constraint_row.contype = 'f'
       and v_sessions_user_id_attnum = any(constraint_row.conkey)
  ) <> 1 then
    raise exception 'Unexpected duplicate sessions.user_id foreign key.';
  end if;

  if not exists (
    select 1
      from pg_catalog.pg_class as relation_row
     where relation_row.oid = 'public.users'::regclass
       and relation_row.relrowsecurity
       and pg_catalog.pg_get_userbyid(relation_row.relowner) = 'postgres'
  ) or not exists (
    select 1
      from pg_catalog.pg_class as relation_row
     where relation_row.oid = 'public.sessions'::regclass
       and relation_row.relrowsecurity
       and pg_catalog.pg_get_userbyid(relation_row.relowner) = 'postgres'
  ) then
    raise exception 'Migration changed table owner or RLS state.';
  end if;

  if not pg_catalog.has_table_privilege(
    'sessions_fk_observer', 'public.users', 'SELECT'
  ) or not pg_catalog.has_table_privilege(
    'sessions_fk_observer', 'public.sessions', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'sessions_fk_observer', 'public.users', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'sessions_fk_observer', 'public.sessions', 'INSERT'
  ) then
    raise exception 'Migration changed table grants.';
  end if;
end;
$$;

-- The exact intended ON DELETE action must remove the child row atomically.
delete from public.users
 where id = '81000000-0000-4000-8000-000000000001';

do $$
begin
  if exists (
    select 1 from public.sessions
     where id = '82000000-0000-4000-8000-000000000001'
  ) then
    raise exception 'ON DELETE CASCADE did not remove the child session.';
  end if;
end;
$$;
