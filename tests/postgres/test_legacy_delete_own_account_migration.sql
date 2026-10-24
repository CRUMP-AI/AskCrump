\set ON_ERROR_STOP on

create or replace function pg_temp.assert_true(
  condition boolean,
  failure_message text
)
returns void
language plpgsql
as $$
begin
  if condition is not true then
    raise exception 'PostgreSQL migration gate failed: %', failure_message;
  end if;
end;
$$;

select pg_temp.assert_true(
  (
    select
      before_state.oid = function_row.oid
      and before_state.prosrc = function_row.prosrc
      and before_state.identity_arguments = pg_get_function_identity_arguments(function_row.oid)
      and before_state.result_type = pg_get_function_result(function_row.oid)
      and before_state.proowner = function_row.proowner
      and before_state.prolang = function_row.prolang
      and before_state.prosecdef = function_row.prosecdef
      and function_row.prosecdef
    from legacy_delete_fixture.before_state as before_state
    cross join pg_catalog.pg_proc as function_row
    where function_row.oid = 'public.delete_own_account()'::regprocedure
  ),
  'legacy function identity, body, owner, language, result, or definer setting changed'
);

select pg_temp.assert_true(
  (
    select function_row.proconfig = array['search_path=""']::text[]
    from pg_catalog.pg_proc as function_row
    where function_row.oid = 'public.delete_own_account()'::regprocedure
  ),
  'legacy function search_path was not pinned to empty'
);

select pg_temp.assert_true(
  not has_function_privilege('anon', 'public.delete_own_account()', 'EXECUTE')
  and has_function_privilege('authenticated', 'public.delete_own_account()', 'EXECUTE')
  and has_function_privilege('service_role', 'public.delete_own_account()', 'EXECUTE'),
  'legacy function effective role privileges are not exact'
);

select pg_temp.assert_true(
  not exists (
    select 1
    from pg_catalog.pg_proc as function_row
    cross join lateral aclexplode(
      coalesce(function_row.proacl, acldefault('f', function_row.proowner))
    ) as acl_row
    where function_row.oid = 'public.delete_own_account()'::regprocedure
      and acl_row.privilege_type = 'EXECUTE'
      and acl_row.grantee in (
        0::oid,
        (select oid from pg_catalog.pg_roles where rolname = 'anon')
      )
  ),
  'PUBLIC or anon retained a direct EXECUTE grant'
);

select pg_temp.assert_true(
  (
    select count(*) = 3
      and bool_and(
        acl_row.grantee in (
          function_row.proowner,
          (select oid from pg_catalog.pg_roles where rolname = 'authenticated'),
          (select oid from pg_catalog.pg_roles where rolname = 'service_role')
        )
      )
    from pg_catalog.pg_proc as function_row
    cross join lateral pg_catalog.aclexplode(function_row.proacl) as acl_row
    where function_row.oid = 'public.delete_own_account()'::regprocedure
      and acl_row.privilege_type = 'EXECUTE'
  ),
  'legacy function has an unexpected direct EXECUTE grantee'
);

select pg_temp.assert_true(
  (
    select count(*) = 2
    from pg_catalog.pg_proc as function_row
    cross join lateral pg_catalog.aclexplode(function_row.proacl) as acl_row
    where function_row.oid = 'public.delete_own_account()'::regprocedure
      and acl_row.privilege_type = 'EXECUTE'
      and not acl_row.is_grantable
      and acl_row.grantee in (
        (select oid from pg_catalog.pg_roles where rolname = 'authenticated'),
        (select oid from pg_catalog.pg_roles where rolname = 'service_role')
      )
  ),
  'authenticated or service_role lacks an explicit non-grantable EXECUTE ACL'
);

select pg_temp.assert_true(
  not has_function_privilege('anon', 'public.delete_user_account(uuid)', 'EXECUTE')
  and not has_function_privilege('authenticated', 'public.delete_user_account(uuid)', 'EXECUTE')
  and has_function_privilege('service_role', 'public.delete_user_account(uuid)', 'EXECUTE')
  and not has_function_privilege('anon', 'public.delete_user_account(uuid,text)', 'EXECUTE')
  and not has_function_privilege('authenticated', 'public.delete_user_account(uuid,text)', 'EXECUTE')
  and has_function_privilege('service_role', 'public.delete_user_account(uuid,text)', 'EXECUTE'),
  'a current service-only deletion overload ACL changed'
);

select pg_temp.assert_true(
  not exists (
    select 1
    from legacy_delete_fixture.service_overload_before as before_state
    join pg_catalog.pg_proc as function_row
      on function_row.oid = before_state.oid
    where function_row.prosrc is distinct from before_state.prosrc
       or function_row.proowner <> before_state.proowner
       or function_row.prosecdef is distinct from before_state.prosecdef
       or function_row.proconfig is distinct from before_state.proconfig
       or function_row.proacl is distinct from before_state.proacl
       or pg_get_function_identity_arguments(function_row.oid)
          is distinct from before_state.identity_arguments
       or pg_get_function_result(function_row.oid)
          is distinct from before_state.result_type
  )
  and (
    select count(*) = 2
    from legacy_delete_fixture.service_overload_before
  ),
  'a current service-only deletion overload definition or ACL drifted'
);

select pg_temp.assert_true(
  not has_table_privilege('authenticated', 'auth.users', 'DELETE'),
  'authenticated unexpectedly received direct auth.users deletion access'
);

-- Exercise a real anonymous invocation and retain its SQLSTATE before psql
-- resets the role. Expected permission failures are kept out of a transaction
-- so they cannot invalidate later assertions.
\set ON_ERROR_STOP off
set role anon;
select public.delete_own_account();
\set anon_call_sqlstate :SQLSTATE
reset role;
\set ON_ERROR_STOP on

select pg_temp.assert_true(
  :'anon_call_sqlstate' = '42501',
  'anonymous invocation did not fail with SQLSTATE 42501'
);

select pg_temp.assert_true(
  (select count(*) = 2 from auth.users),
  'anonymous invocation changed a synthetic user'
);

select set_config(
  'request.jwt.claim.sub',
  '10000000-0000-4000-8000-000000000001',
  false
);

\set ON_ERROR_STOP off
set role authenticated;
delete from auth.users
where id = '10000000-0000-4000-8000-000000000001';
\set direct_delete_sqlstate :SQLSTATE
reset role;
\set ON_ERROR_STOP on

select pg_temp.assert_true(
  :'direct_delete_sqlstate' = '42501',
  'authenticated direct deletion did not fail with SQLSTATE 42501'
);

select pg_temp.assert_true(
  (select count(*) = 2 from auth.users),
  'authenticated direct deletion changed a synthetic user'
);

select set_config('request.jwt.claim.sub', '', false);
set role authenticated;
select public.delete_own_account();
reset role;

select pg_temp.assert_true(
  (select count(*) = 2 from auth.users),
  'a missing authenticated subject deleted a synthetic user'
);

select set_config(
  'request.jwt.claim.sub',
  '10000000-0000-4000-8000-000000000001',
  false
);
set role authenticated;
select public.delete_own_account();
select public.delete_own_account();
reset role;

select pg_temp.assert_true(
  not exists (
    select 1 from auth.users
    where id = '10000000-0000-4000-8000-000000000001'
  )
  and exists (
    select 1 from auth.users
    where id = '10000000-0000-4000-8000-000000000002'
  ),
  'self-delete was not idempotent and isolated to synthetic subject A'
);
