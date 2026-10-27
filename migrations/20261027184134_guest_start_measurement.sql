-- Forward-only, database-authoritative guest-start measurement.
--
-- Existing accounts receive no synthetic timing. A nullable tracking-version
-- cutover distinguishes future accounts from legacy guests whose first start
-- is unknowable. Future starts are recorded only after a session row actually
-- inserts or changes owner, and the public report exposes counts only.

begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

-- A reapply is a verification pass, not permission to normalize unexpected
-- live state. Once any contract object exists, require the complete reviewed
-- shape before later idempotent DDL refreshes function definitions.
do $migration$
declare
  v_existing_columns integer;
  v_existing_functions integer;
  v_existing_triggers integer;
  v_existing_relations integer;
  v_private_acl_ok boolean;
  v_report_acl_ok boolean;
  v_index_keys text[];
  v_index_opclasses text[];
  v_index_collations oid[];
  v_index_options smallint[];
  v_index_predicate text;
  v_index_exact boolean;
begin
  if not (
    select users_relation.relrowsecurity
      and sessions_relation.relrowsecurity
    from pg_catalog.pg_class as users_relation
    cross join pg_catalog.pg_class as sessions_relation
    where users_relation.oid = 'public.users'::regclass
      and sessions_relation.oid = 'public.sessions'::regclass
  ) then
    raise exception
      'Guest-start users/sessions RLS prerequisite drift exists; refusing migration.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.unnest(
        array['anon', 'authenticated']::text[]
      ) as role_row(role_name)
      cross join pg_catalog.unnest(
        array['public.users', 'public.sessions']::text[]
      ) as table_row(table_name)
      cross join pg_catalog.unnest(
        array[
          'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
          'REFERENCES', 'TRIGGER', 'MAINTAIN'
        ]::text[]
      ) as privilege_row(privilege_name)
     where has_table_privilege(
       role_row.role_name,
       table_row.table_name,
       privilege_row.privilege_name
     )
  ) or exists (
    select 1
      from pg_catalog.unnest(
        array['anon', 'authenticated']::text[]
      ) as role_row(role_name)
      cross join pg_catalog.unnest(
        array['public.users', 'public.sessions']::text[]
      ) as table_row(table_name)
      cross join pg_catalog.unnest(
        array['SELECT', 'INSERT', 'UPDATE', 'REFERENCES']::text[]
      ) as privilege_row(privilege_name)
     where has_any_column_privilege(
       role_row.role_name,
       table_row.table_name,
       privilege_row.privilege_name
     )
  ) then
    raise exception
      'Guest-start users/sessions ACL prerequisite drift exists; refusing migration.'
      using errcode = '55000';
  end if;

  select pg_catalog.count(*)
    into v_existing_columns
    from pg_catalog.pg_attribute as attribute_row
   where attribute_row.attrelid = 'public.users'::regclass
     and attribute_row.attname in (
       'guest_start_tracking_version',
       'guest_started_at',
       'guest_start_environment'
     )
     and not attribute_row.attisdropped;

  select pg_catalog.count(*)
    into v_existing_functions
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = function_row.pronamespace
   where namespace_row.nspname = 'public'
     and function_row.proname in (
       'enforce_guest_start_immutability_v1',
       'lock_guest_start_owner_before_session_v1',
       'stamp_guest_start_from_session_v1',
       'product_guest_start_funnel_snapshot'
     );

  select pg_catalog.count(*)
    into v_existing_triggers
    from pg_catalog.pg_trigger as trigger_row
   where trigger_row.tgrelid in (
       'public.users'::regclass,
       'public.sessions'::regclass
     )
     and trigger_row.tgname in (
       'users_guest_start_immutability_v1',
       'a_guest_start_owner_lock_v1',
       'sessions_guest_start_stamp_v1'
     )
     and not trigger_row.tgisinternal;

  select pg_catalog.count(*)
    into v_existing_relations
    from pg_catalog.pg_class as relation_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = relation_row.relnamespace
   where namespace_row.nspname = 'public'
     and relation_row.relname = 'users_guest_start_cohort_idx';

  v_existing_relations := v_existing_relations + (
    select pg_catalog.count(*)
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = 'public.users'::regclass
       and constraint_row.conname = 'users_guest_start_boundary_check'
  );

  if v_existing_columns + v_existing_functions
       + v_existing_triggers + v_existing_relations = 0 then
    return;
  end if;

  if v_existing_columns <> 3
     or v_existing_functions <> 4
     or v_existing_triggers <> 3
     or v_existing_relations <> 2 then
    raise exception
      'Partial guest-start measurement state exists; refusing migration.'
      using errcode = '55000';
  end if;

  if not exists (
    select 1
      from pg_catalog.pg_attribute as tracking_column
      join pg_catalog.pg_attrdef as default_row
        on default_row.adrelid = tracking_column.attrelid
       and default_row.adnum = tracking_column.attnum
     where tracking_column.attrelid = 'public.users'::regclass
       and tracking_column.attname = 'guest_start_tracking_version'
       and tracking_column.atttypid = 'smallint'::regtype
       and not tracking_column.attnotnull
       and pg_catalog.pg_get_expr(
             default_row.adbin, default_row.adrelid, false
           ) = '1'
  ) or exists (
    select 1
      from pg_catalog.pg_attribute as measured_column
     where measured_column.attrelid = 'public.users'::regclass
       and measured_column.attname in (
         'guest_started_at', 'guest_start_environment'
       )
       and (
         measured_column.attnotnull
         or measured_column.atthasdef
         or (
           measured_column.attname = 'guest_started_at'
           and measured_column.atttypid <> 'timestamptz'::regtype
         )
         or (
           measured_column.attname = 'guest_start_environment'
           and measured_column.atttypid <> 'text'::regtype
         )
       )
  ) then
    raise exception
      'Guest-start column/default drift exists; refusing migration.'
      using errcode = '55000';
  end if;

  if not exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = 'public.users'::regclass
       and constraint_row.conname = 'users_guest_start_boundary_check'
       and constraint_row.contype = 'c'
       and constraint_row.convalidated
  ) then
    raise exception
      'Guest-start boundary constraint drift exists; refusing migration.'
      using errcode = '55000';
  end if;

  select
    pg_catalog.array_agg(attribute_row.attname order by key_row.ordinality),
    pg_catalog.array_agg(
      opclass_namespace.nspname || '.' || opclass_row.opcname
      order by key_row.ordinality
    ),
    pg_catalog.array_agg(collation_row.collation_oid order by key_row.ordinality),
    pg_catalog.array_agg(option_row.option_value order by key_row.ordinality),
    pg_catalog.pg_get_expr(index_row.indpred, index_row.indrelid, false),
    pg_catalog.bool_and(
      index_row.indrelid = 'public.users'::regclass
      and access_method.amname = 'btree'
      and index_relation.relkind = 'i'
      and index_relation.relpersistence = 'p'
      and index_relation.reloptions is null
      and index_row.indnkeyatts = 3
      and index_row.indnatts = 3
      and index_row.indexprs is null
      and index_row.indisvalid
      and index_row.indisready
      and index_row.indislive
      and not index_row.indisunique
      and not index_row.indisprimary
      and not index_row.indisexclusion
      and not index_row.indisclustered
      and not index_row.indisreplident
      and not index_row.indnullsnotdistinct
      and not index_row.indcheckxmin
      and not exists (
        select 1
          from pg_catalog.pg_constraint as index_constraint
         where index_constraint.conindid = index_row.indexrelid
      )
    )
    into
      v_index_keys,
      v_index_opclasses,
      v_index_collations,
      v_index_options,
      v_index_predicate,
      v_index_exact
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as index_relation
      on index_relation.oid = index_row.indexrelid
    join pg_catalog.pg_am as access_method
      on access_method.oid = index_relation.relam
    join lateral pg_catalog.unnest(index_row.indkey)
      with ordinality as key_row(attnum, ordinality)
      on key_row.ordinality <= index_row.indnkeyatts
    join pg_catalog.pg_attribute as attribute_row
      on attribute_row.attrelid = index_row.indrelid
     and attribute_row.attnum = key_row.attnum
    join lateral pg_catalog.unnest(index_row.indclass)
      with ordinality as class_key(opclass_oid, ordinality)
      on class_key.ordinality = key_row.ordinality
    join pg_catalog.pg_opclass as opclass_row
      on opclass_row.oid = class_key.opclass_oid
    join pg_catalog.pg_namespace as opclass_namespace
      on opclass_namespace.oid = opclass_row.opcnamespace
    join lateral pg_catalog.unnest(index_row.indcollation)
      with ordinality as collation_row(collation_oid, ordinality)
      on collation_row.ordinality = key_row.ordinality
    join lateral pg_catalog.unnest(index_row.indoption)
      with ordinality as option_row(option_value, ordinality)
      on option_row.ordinality = key_row.ordinality
   where index_relation.oid = 'public.users_guest_start_cohort_idx'::regclass
   group by index_row.indpred, index_row.indrelid;

  if v_index_exact is not true
     or v_index_keys is distinct from array[
       'guest_start_environment', 'guest_started_at', 'id'
     ]::text[]
     or v_index_opclasses is distinct from array[
       'pg_catalog.text_ops',
       'pg_catalog.timestamptz_ops',
       'pg_catalog.uuid_ops'
     ]::text[]
     or v_index_collations is distinct from array[
       (
         select attribute_row.attcollation
           from pg_catalog.pg_attribute as attribute_row
          where attribute_row.attrelid = 'public.users'::regclass
            and attribute_row.attname = 'guest_start_environment'
       ),
       0::oid,
       0::oid
     ]::oid[]
     or v_index_options is distinct from array[0, 0, 0]::smallint[]
     or v_index_predicate is distinct from '(guest_started_at IS NOT NULL)' then
    raise exception 'Guest-start cohort index drift exists; refusing migration.'
      using errcode = '55000';
  end if;

  if not (
    select function_row.proowner = current_user::regrole::oid
      and language_row.lanname = 'plpgsql'
      and function_row.prokind = 'f'
      and function_row.prorettype = 'trigger'::regtype
      and function_row.provolatile = 'v'
      and function_row.prosecdef is false
      and function_row.proisstrict is false
      and function_row.proleakproof is false
      and function_row.proparallel = 'u'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.md5(function_row.prosrc) =
        '295ae12afaa71900aabde7d5502a14e2'
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_language as language_row
      on language_row.oid = function_row.prolang
    where function_row.oid =
      'public.enforce_guest_start_immutability_v1()'::regprocedure
  ) or not (
    select function_row.proowner = current_user::regrole::oid
      and language_row.lanname = 'plpgsql'
      and function_row.prokind = 'f'
      and function_row.prorettype = 'trigger'::regtype
      and function_row.provolatile = 'v'
      and function_row.prosecdef is true
      and function_row.proisstrict is false
      and function_row.proleakproof is false
      and function_row.proparallel = 'u'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.md5(function_row.prosrc) =
        'ac2f6822a109add3b3189a4e0db8a606'
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_language as language_row
      on language_row.oid = function_row.prolang
    where function_row.oid =
      'public.lock_guest_start_owner_before_session_v1()'::regprocedure
  ) or not (
    select function_row.proowner = current_user::regrole::oid
      and language_row.lanname = 'plpgsql'
      and function_row.prokind = 'f'
      and function_row.prorettype = 'trigger'::regtype
      and function_row.provolatile = 'v'
      and function_row.prosecdef is true
      and function_row.proisstrict is false
      and function_row.proleakproof is false
      and function_row.proparallel = 'u'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.md5(function_row.prosrc) =
        'f812b2e7d9828929a6267c894148b549'
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_language as language_row
      on language_row.oid = function_row.prolang
    where function_row.oid =
      'public.stamp_guest_start_from_session_v1()'::regprocedure
  ) or not (
    select function_row.proowner = current_user::regrole::oid
      and language_row.lanname = 'plpgsql'
      and function_row.prokind = 'f'
      and function_row.provolatile = 's'
      and function_row.prosecdef is false
      and function_row.proisstrict is false
      and function_row.proleakproof is false
      and function_row.proparallel = 'u'
      and function_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.pg_get_function_result(function_row.oid) =
        'TABLE(stage_order smallint, metric text, accounts bigint, eligible bigint, rate_pct numeric)'
      and pg_catalog.pg_get_function_arguments(function_row.oid) =
        $arguments$p_since timestamp with time zone, p_until timestamp with time zone DEFAULT now(), p_environment text DEFAULT 'production'::text, p_include_internal boolean DEFAULT false$arguments$
      and pg_catalog.md5(function_row.prosrc) =
        '24b9351b22511f827e259b94d7c1d67d'
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_language as language_row
      on language_row.oid = function_row.prolang
    where function_row.oid =
      'public.product_guest_start_funnel_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure
  ) then
    raise exception 'Guest-start function contract drift exists; refusing migration.'
      using errcode = '55000';
  end if;

  select not exists (
    select 1
      from pg_catalog.pg_proc as function_row
      cross join lateral pg_catalog.aclexplode(
        coalesce(
          function_row.proacl,
          pg_catalog.acldefault('f', function_row.proowner)
        )
      ) as acl_row
     where function_row.oid in (
       'public.enforce_guest_start_immutability_v1()'::regprocedure,
       'public.lock_guest_start_owner_before_session_v1()'::regprocedure,
       'public.stamp_guest_start_from_session_v1()'::regprocedure
     )
       and acl_row.grantee <> function_row.proowner
  ) into v_private_acl_ok;

  select not exists (
    select 1
      from pg_catalog.pg_proc as function_row
      cross join lateral pg_catalog.aclexplode(
        coalesce(
          function_row.proacl,
          pg_catalog.acldefault('f', function_row.proowner)
        )
      ) as acl_row
     where function_row.oid =
       'public.product_guest_start_funnel_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure
       and (
         acl_row.grantee not in (
           function_row.proowner,
           'service_role'::regrole::oid
         )
         or acl_row.privilege_type <> 'EXECUTE'
         or acl_row.is_grantable
       )
  ) and has_function_privilege(
    'service_role',
    'public.product_guest_start_funnel_snapshot(timestamptz,timestamptz,text,boolean)',
    'EXECUTE'
  ) into v_report_acl_ok;

  if not v_private_acl_ok or not v_report_acl_ok then
    raise exception 'Guest-start function ACL drift exists; refusing migration.'
      using errcode = '55000';
  end if;

  if not exists (
    select 1
      from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid = 'public.users'::regclass
       and trigger_row.tgname = 'users_guest_start_immutability_v1'
       and trigger_row.tgfoid =
         'public.enforce_guest_start_immutability_v1()'::regprocedure
       and trigger_row.tgtype = 23
       and trigger_row.tgenabled = 'O'
       and trigger_row.tgqual is null
       and pg_catalog.cardinality(trigger_row.tgattr::smallint[]) = 3
       and trigger_row.tgattr[0] = (
         select attribute_row.attnum
           from pg_catalog.pg_attribute as attribute_row
          where attribute_row.attrelid = 'public.users'::regclass
            and attribute_row.attname = 'guest_start_tracking_version'
       )
       and trigger_row.tgattr[1] = (
         select attribute_row.attnum
           from pg_catalog.pg_attribute as attribute_row
          where attribute_row.attrelid = 'public.users'::regclass
            and attribute_row.attname = 'guest_started_at'
       )
       and trigger_row.tgattr[2] = (
         select attribute_row.attnum
           from pg_catalog.pg_attribute as attribute_row
          where attribute_row.attrelid = 'public.users'::regclass
            and attribute_row.attname = 'guest_start_environment'
       )
       and not trigger_row.tgisinternal
  ) or not exists (
    select 1
      from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid = 'public.sessions'::regclass
       and trigger_row.tgname = 'a_guest_start_owner_lock_v1'
       and trigger_row.tgfoid =
         'public.lock_guest_start_owner_before_session_v1()'::regprocedure
       and trigger_row.tgtype = 7
       and trigger_row.tgenabled = 'O'
       and trigger_row.tgqual is null
       and pg_catalog.cardinality(trigger_row.tgattr::smallint[]) = 0
       and not trigger_row.tgisinternal
  ) or not exists (
    select 1
      from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid = 'public.sessions'::regclass
       and trigger_row.tgname = 'sessions_guest_start_stamp_v1'
       and trigger_row.tgfoid =
         'public.stamp_guest_start_from_session_v1()'::regprocedure
       and trigger_row.tgtype = 21
       and trigger_row.tgenabled = 'O'
       and trigger_row.tgqual is null
       and pg_catalog.cardinality(trigger_row.tgattr::smallint[]) = 1
       and trigger_row.tgattr[0] = (
         select attribute_row.attnum
           from pg_catalog.pg_attribute as attribute_row
          where attribute_row.attrelid = 'public.sessions'::regclass
            and attribute_row.attname = 'user_id'
       )
       and not trigger_row.tgisinternal
  ) then
    raise exception 'Guest-start trigger contract drift exists; refusing migration.'
      using errcode = '55000';
  end if;
end
$migration$;

-- Add the eligibility marker without a default first. Existing rows therefore
-- stay permanently outside the forward cohort, including a legacy orphan guest
-- that creates a new-device session after this migration.
alter table public.users
  add column if not exists guest_start_tracking_version smallint;
alter table public.users
  add column if not exists guest_started_at timestamptz;
alter table public.users
  add column if not exists guest_start_environment text;

alter table public.users
  alter column guest_start_tracking_version set default 1;

comment on column public.users.guest_start_tracking_version is
  'Forward guest-start eligibility. Null means the account predates measurement; 1 means a future account eligible for database-authoritative stamping. Immutable.';
comment on column public.users.guest_started_at is
  'First successful active guest-session persistence observed by the database. Null means no forward-observed start or legacy timing unavailable; immutable.';
comment on column public.users.guest_start_environment is
  'Immutable exact environment captured with guest_started_at. Null iff guest_started_at is null.';

do $migration$
declare
  v_compatible_columns integer;
begin
  select pg_catalog.count(*)
    into v_compatible_columns
    from pg_catalog.pg_attribute as attribute_row
   where attribute_row.attrelid = 'public.users'::regclass
     and attribute_row.attname in (
       'guest_start_tracking_version',
       'guest_started_at',
       'guest_start_environment'
     )
     and not attribute_row.attisdropped
     and not attribute_row.attnotnull
     and (
       (
         attribute_row.attname = 'guest_start_tracking_version'
         and attribute_row.atttypid = 'smallint'::regtype
       )
       or (
         attribute_row.attname = 'guest_started_at'
         and attribute_row.atttypid = 'timestamptz'::regtype
       )
       or (
         attribute_row.attname = 'guest_start_environment'
         and attribute_row.atttypid = 'text'::regtype
       )
     );

  if v_compatible_columns <> 3 then
    raise exception
      'Guest-start columns have incompatible type or nullability; refusing migration.'
      using errcode = '55000';
  end if;
end
$migration$;

do $migration$
begin
  if not exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = 'public.users'::regclass
       and constraint_row.conname = 'users_guest_start_boundary_check'
  ) then
    alter table public.users
      add constraint users_guest_start_boundary_check check (
        (
          guest_start_tracking_version is null
          and guest_started_at is null
          and guest_start_environment is null
        )
        or (
          guest_start_tracking_version = 1
          and (
            (
              guest_started_at is null
              and guest_start_environment is null
            )
            or (
              guest_started_at is not null
              and guest_start_environment in (
                'production', 'preview', 'development'
              )
            )
          )
        )
      ) not valid;
  end if;
end
$migration$;

alter table public.users
  validate constraint users_guest_start_boundary_check;

-- Compare the installed expression with an independently parsed copy. This
-- keeps idempotent reapply from accepting a same-name weakened constraint and
-- avoids search-path-sensitive text reconstruction.
drop table if exists pg_temp.guest_start_boundary_contract;
create temporary table guest_start_boundary_contract (
  guest_start_tracking_version smallint,
  guest_started_at timestamptz,
  guest_start_environment text,
  constraint guest_start_boundary_contract_check check (
    (
      guest_start_tracking_version is null
      and guest_started_at is null
      and guest_start_environment is null
    )
    or (
      guest_start_tracking_version = 1
      and (
        (
          guest_started_at is null
          and guest_start_environment is null
        )
        or (
          guest_started_at is not null
          and guest_start_environment in (
            'production', 'preview', 'development'
          )
        )
      )
    )
  )
) on commit drop;

do $migration$
declare
  v_actual text;
  v_expected text;
begin
  select pg_catalog.pg_get_expr(
           constraint_row.conbin,
           constraint_row.conrelid,
           false
         )
    into strict v_actual
    from pg_catalog.pg_constraint as constraint_row
   where constraint_row.conrelid = 'public.users'::regclass
     and constraint_row.conname = 'users_guest_start_boundary_check'
     and constraint_row.contype = 'c'
     and constraint_row.convalidated;

  select pg_catalog.pg_get_expr(
           constraint_row.conbin,
           constraint_row.conrelid,
           false
         )
    into strict v_expected
    from pg_catalog.pg_constraint as constraint_row
   where constraint_row.conrelid =
           'pg_temp.guest_start_boundary_contract'::regclass
     and constraint_row.conname = 'guest_start_boundary_contract_check';

  if v_actual is distinct from v_expected then
    raise exception
      'Guest-start boundary constraint drifted; refusing migration.'
      using errcode = '55000';
  end if;
end
$migration$;

drop table pg_temp.guest_start_boundary_contract;

create index if not exists users_guest_start_cohort_idx
  on public.users(guest_start_environment, guest_started_at, id)
  where guest_started_at is not null;

-- Caller-supplied tracking state is never accepted. The private session
-- trigger runs as its owner; that is the only path allowed to populate the
-- boundary. A database owner remains able to repair schema by definition.
create or replace function public.enforce_guest_start_immutability_v1()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_stamp_owner name;
begin
  -- guest-start-contract:immutability-v1
  if tg_op = 'INSERT' then
    new.guest_start_tracking_version := 1;
    new.guest_started_at := null;
    new.guest_start_environment := null;
    return new;
  end if;

  new.guest_start_tracking_version := old.guest_start_tracking_version;

  if old.guest_started_at is not null then
    new.guest_started_at := old.guest_started_at;
    new.guest_start_environment := old.guest_start_environment;
    return new;
  end if;

  if new.guest_started_at is null then
    new.guest_start_environment := null;
    return new;
  end if;

  select pg_catalog.pg_get_userbyid(function_row.proowner)
    into strict v_stamp_owner
    from pg_catalog.pg_proc as function_row
   where function_row.oid =
     'public.stamp_guest_start_from_session_v1()'::regprocedure;

  if current_user <> v_stamp_owner
     or old.guest_start_tracking_version is distinct from 1
     or old.is_guest is not true
     or new.is_guest is not true then
    new.guest_started_at := null;
    new.guest_start_environment := null;
    return new;
  end if;

  if new.guest_start_environment not in (
    'production', 'preview', 'development'
  ) then
    raise exception 'Guest-start environment is required and must be exact.'
      using errcode = '23514';
  end if;

  -- The private session trigger sampled this database clock only after
  -- obtaining the owner lock and rechecking expiry. Preserve that authorized
  -- time exactly. created_at and registration_submitted_at are app-supplied
  -- clocks, so they must never reject or rewrite a valid persisted session.

  return new;
end;
$$;

-- Exclusively acquire an eligible unstamped owner before PostgreSQL checks the
-- device/session uniqueness conflict. The a_ trigger name intentionally sorts
-- before the existing enforce_guest_mode_on_session_v1 trigger. Concurrent
-- first starts for one guest therefore serialize on the user before either can
-- own a session conflict. Failed inserts and DO NOTHING branches still produce
-- no stamp because stamping is AFTER.
create or replace function public.lock_guest_start_owner_before_session_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  -- guest-start-contract:owner-lock-v1
  if new.revoked_at is null
     and new.expires_at > pg_catalog.clock_timestamp() then
    perform 1
      from public.users as account
     where account.id = new.user_id
       and account.is_guest is true
       and account.guest_start_tracking_version = 1
       and account.guest_started_at is null
       and account.deleted_at is null
     for update;
  end if;

  return new;
end;
$$;

create or replace function public.stamp_guest_start_from_session_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_is_guest boolean;
  v_tracking_version smallint;
  v_started_at timestamptz;
  v_environment text;
  v_stamp_at timestamptz;
begin
  -- guest-start-contract:stamp-v1
  if new.revoked_at is not null
     or new.expires_at <= pg_catalog.clock_timestamp() then
    return new;
  end if;

  if tg_op = 'UPDATE'
     and new.user_id is not distinct from old.user_id then
    return new;
  end if;

  -- Avoid taking an owner lock at all for registered, legacy, deleted, or
  -- already-measured accounts. In particular, a later session for an already
  -- stamped guest must not reintroduce a session -> user lock edge.
  select
    account.is_guest,
    account.guest_start_tracking_version,
    account.guest_started_at,
    account.registration_environment
    into v_is_guest, v_tracking_version, v_started_at, v_environment
    from public.users as account
   where account.id = new.user_id
     and account.deleted_at is null;

  if not found
     or v_is_guest is not true
     or v_tracking_version is distinct from 1
     or v_started_at is not null then
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- A direct UPDATE already owns the session tuple. Never wait behind a
    -- verification transaction that may own the user and need that tuple.
    -- Supported INSERT ... ON CONFLICT upserts already hold the user lock
    -- from the BEFORE INSERT trigger and can reuse it here.
    begin
      select
        account.is_guest,
        account.guest_start_tracking_version,
        account.guest_started_at,
        account.registration_environment
        into v_is_guest, v_tracking_version, v_started_at, v_environment
        from public.users as account
       where account.id = new.user_id
         and account.deleted_at is null
       for update nowait;
    exception when lock_not_available then
      raise exception using
        errcode = 'GX004',
        message = 'Guest session owner is changing; retry the session write.';
    end;
  else
    select
      account.is_guest,
      account.guest_start_tracking_version,
      account.guest_started_at,
      account.registration_environment
      into v_is_guest, v_tracking_version, v_started_at, v_environment
      from public.users as account
     where account.id = new.user_id
       and account.deleted_at is null
     for update;
  end if;

  -- Re-evaluate after locking because a prior transaction may have completed
  -- verification or the first stamp while this write waited at the owner.
  if not found
     or v_is_guest is not true
     or v_tracking_version is distinct from 1
     or v_started_at is not null then
    return new;
  end if;

  -- Sample the security clock only after the owner lock. A session that was
  -- active when its statement began but expired while waiting is not a start.
  v_stamp_at := pg_catalog.clock_timestamp();
  if new.expires_at <= v_stamp_at then
    return new;
  end if;

  if v_environment not in ('production', 'preview', 'development') then
    raise exception 'Guest-start environment is required and must be exact.'
      using errcode = '23514';
  end if;

  update public.users as account
     set guest_started_at = v_stamp_at,
         guest_start_environment = v_environment
   where account.id = new.user_id
     and account.is_guest is true
     and account.guest_start_tracking_version = 1
     and account.guest_started_at is null
     and account.deleted_at is null;

  return new;
end;
$$;

drop trigger if exists users_guest_start_immutability_v1
  on public.users;
create trigger users_guest_start_immutability_v1
before insert or update of
  guest_start_tracking_version,
  guest_started_at,
  guest_start_environment
on public.users
for each row
execute function public.enforce_guest_start_immutability_v1();

drop trigger if exists a_guest_start_owner_lock_v1
  on public.sessions;
create trigger a_guest_start_owner_lock_v1
before insert
on public.sessions
for each row
execute function public.lock_guest_start_owner_before_session_v1();

drop trigger if exists sessions_guest_start_stamp_v1
  on public.sessions;
create trigger sessions_guest_start_stamp_v1
after insert or update of user_id
on public.sessions
for each row
execute function public.stamp_guest_start_from_session_v1();

revoke all on function public.enforce_guest_start_immutability_v1()
  from public, anon, authenticated, service_role;
revoke all on function public.lock_guest_start_owner_before_session_v1()
  from public, anon, authenticated, service_role;
revoke all on function public.stamp_guest_start_from_session_v1()
  from public, anon, authenticated, service_role;

create or replace function public.product_guest_start_funnel_snapshot(
  p_since timestamptz,
  p_until timestamptz default pg_catalog.now(),
  p_environment text default 'production',
  p_include_internal boolean default false
)
returns table(
  stage_order smallint,
  metric text,
  accounts bigint,
  eligible bigint,
  rate_pct numeric
)
language plpgsql
stable
security invoker
set search_path = ''
as $$
begin
  -- guest-start-contract:aggregate-v1
  if p_since is null or p_until is null or p_since >= p_until then
    raise exception 'Guest-start window must be a non-empty half-open interval.'
      using errcode = '22023';
  end if;

  if p_environment is null
     or p_environment not in ('production', 'preview', 'development') then
    raise exception 'Guest-start environment is invalid.'
      using errcode = '22023';
  end if;

  return query
  with cohort as (
    select
      account.id,
      account.guest_started_at,
      account.registration_submitted_at,
      account.email_verified_at
    from public.users as account
    where account.guest_start_tracking_version = 1
      and account.guest_started_at >= p_since
      and account.guest_started_at < p_until
      and account.guest_start_environment = p_environment
      and account.deleted_at is null
      and (
        p_include_internal
        or coalesce(account.internal_tier, '') = ''
      )
  ), registered as (
    select
      cohort_row.*,
      case
        when cohort_row.registration_submitted_at is null then null::timestamptz
        else greatest(
          cohort_row.guest_started_at,
          cohort_row.registration_submitted_at
        )
      end as registration_reached_at
    from cohort as cohort_row
  ), verified as (
    select
      registered_row.*,
      (
        registered_row.registration_reached_at is not null
        and registered_row.registration_reached_at < p_until
      ) as reached_registration,
      case
        when registered_row.registration_reached_at is null
          or registered_row.email_verified_at is null then null::timestamptz
        else greatest(
          registered_row.registration_reached_at,
          registered_row.email_verified_at
        )
      end as verification_reached_at
    from registered as registered_row
  ), stage_state as (
    select
      verified_row.*,
      (
        verified_row.reached_registration
        and verified_row.verification_reached_at is not null
        and verified_row.verification_reached_at < p_until
      ) as reached_verification
    from verified as verified_row
  ), journey as (
    select
      stage_row.*,
      (
        stage_row.reached_verification
        and (
          exists (
            select 1
            from public.product_events as event
            where event.user_id = stage_row.id
              and event.event_name = 'ActivationReached'
              and event.created_at >= stage_row.verification_reached_at
              and event.created_at < p_until
          )
          or exists (
            select 1
            from public.chat_jobs as job
            where job.user_id = stage_row.id
              and job.status = 'completed'
              and job.created_at >= stage_row.verification_reached_at
              and job.updated_at >= stage_row.verification_reached_at
              and job.updated_at < p_until
          )
        )
      ) as reached_activation
    from stage_state as stage_row
  ), counts as (
    select
      pg_catalog.count(*)::bigint as guest_started,
      pg_catalog.count(*) filter (
        where journey_row.reached_registration
      )::bigint as registration_submitted,
      pg_catalog.count(*) filter (
        where journey_row.reached_verification
      )::bigint as email_verified,
      pg_catalog.count(*) filter (
        where journey_row.reached_activation
      )::bigint as activation_reached
    from journey as journey_row
  ), stage_rows(stage_order, metric, accounts, eligible) as (
    select 1::smallint, 'guest_started'::text,
           counts.guest_started, counts.guest_started
      from counts
    union all
    select 2::smallint, 'registration_submitted'::text,
           counts.registration_submitted, counts.guest_started
      from counts
    union all
    select 3::smallint, 'email_verified'::text,
           counts.email_verified, counts.registration_submitted
      from counts
    union all
    select 4::smallint, 'activation_reached'::text,
           counts.activation_reached, counts.email_verified
      from counts
  )
  select
    stage_rows.stage_order,
    stage_rows.metric,
    stage_rows.accounts,
    stage_rows.eligible,
    case
      when stage_rows.eligible = 0 then null::numeric
      else pg_catalog.round(
        100.0 * stage_rows.accounts::numeric / stage_rows.eligible::numeric,
        2
      )
    end as rate_pct
  from stage_rows
  order by stage_rows.stage_order;
end;
$$;

comment on function public.product_guest_start_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free forward acquisition cohort selected by exact immutable guest-start environment, then followed through durable registration, verification, and activation on any later surface. Soft-deleted and hard-deleted accounts are excluded. Legacy timing remains unavailable.';

revoke all on function public.product_guest_start_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated, service_role;
grant execute on function public.product_guest_start_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) to service_role;

commit;
