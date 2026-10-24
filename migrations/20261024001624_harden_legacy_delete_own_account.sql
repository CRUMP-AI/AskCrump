-- Harden the legacy self-delete RPC without replacing or rerouting it.
--
-- Some installations no longer carry this no-argument function. The migration
-- is intentionally a clean no-op there. Where it still exists, ALTER and ACL
-- statements preserve its OID, body, signature, owner, language, return type,
-- and SECURITY DEFINER setting.

do $migration$
declare
  target_oid oid := pg_catalog.to_regprocedure('public.delete_own_account()');
  before_state record;
  after_state record;
  expected_unhardened_definition_md5 constant text :=
    'e8e18f430f5911f16824ff7b2ec36068';
  expected_hardened_definition_md5 constant text :=
    '22f067b67e8e0209a3ef29bc3c28e37d';
  expected_body constant text :=
    ' begin   delete from auth.users where id = auth.uid(); end ';
begin
  if target_oid is null then
    return;
  end if;

  select
    function_row.oid,
    function_row.proowner,
    pg_catalog.pg_get_userbyid(function_row.proowner) as owner_name,
    function_row.prosecdef,
    function_row.prolang,
    language_row.lanname as language_name,
    function_row.prokind,
    function_row.prorettype,
    function_row.proretset,
    function_row.proargtypes,
    function_row.proallargtypes,
    function_row.proargmodes,
    function_row.proargnames,
    function_row.prosrc,
    function_row.probin,
    function_row.prosqlbody::text as prosqlbody,
    function_row.provolatile,
    function_row.proisstrict,
    function_row.proparallel,
    function_row.proconfig,
    function_row.proacl,
    pg_catalog.pg_get_function_identity_arguments(function_row.oid) as identity_arguments,
    pg_catalog.pg_get_function_result(function_row.oid) as result_type,
    pg_catalog.md5(pg_catalog.pg_get_functiondef(function_row.oid)) as definition_md5
  into strict before_state
  from pg_catalog.pg_proc as function_row
  join pg_catalog.pg_language as language_row
    on language_row.oid = function_row.prolang
  where function_row.oid = target_oid;

  -- The first hash is bound to the fresh production readback immediately
  -- before this migration was authored. The second is the same PostgreSQL 17
  -- definition with only the reviewed empty search_path setting applied. This
  -- keeps reapplication idempotent without accepting volatility or other
  -- definition drift.
  if before_state.owner_name <> 'postgres'
     or before_state.prosecdef is not true
     or before_state.language_name <> 'plpgsql'
     or before_state.prokind <> 'f'
     or before_state.identity_arguments <> ''
     or before_state.result_type <> 'void'
     or before_state.prosrc <> expected_body
     or before_state.definition_md5 not in (
       expected_unhardened_definition_md5,
       expected_hardened_definition_md5
     ) then
    raise exception
      'Unexpected public.delete_own_account() definition; refusing hardening.'
      using errcode = '55000';
  end if;

  if before_state.definition_md5 = expected_unhardened_definition_md5 then
    if (
      select count(*) <> 3
        or bool_or(
          acl_row.grantee not in (
            0::oid,
            before_state.proowner,
            (select oid from pg_catalog.pg_roles where rolname = 'service_role')
          )
        )
        or bool_or(
          acl_row.grantee in (
            0::oid,
            (select oid from pg_catalog.pg_roles where rolname = 'service_role')
          )
          and acl_row.is_grantable
        )
      from pg_catalog.aclexplode(
        coalesce(
          before_state.proacl,
          pg_catalog.acldefault('f', before_state.proowner)
        )
      ) as acl_row
      where acl_row.privilege_type = 'EXECUTE'
    ) then
      raise exception
        'Unexpected public.delete_own_account() ACL; refusing hardening.'
        using errcode = '55000';
    end if;
  else
    if (
      select count(*) <> 3
        or bool_or(
          acl_row.grantee not in (
            before_state.proowner,
            (select oid from pg_catalog.pg_roles where rolname = 'authenticated'),
            (select oid from pg_catalog.pg_roles where rolname = 'service_role')
          )
        )
        or bool_or(
          acl_row.grantee in (
            (select oid from pg_catalog.pg_roles where rolname = 'authenticated'),
            (select oid from pg_catalog.pg_roles where rolname = 'service_role')
          )
          and acl_row.is_grantable
        )
      from pg_catalog.aclexplode(
        coalesce(
          before_state.proacl,
          pg_catalog.acldefault('f', before_state.proowner)
        )
      ) as acl_row
      where acl_row.privilege_type = 'EXECUTE'
    ) then
      raise exception
        'Unexpected public.delete_own_account() ACL; refusing hardening.'
        using errcode = '55000';
    end if;
  end if;

  execute 'alter function public.delete_own_account() set search_path = ''''';
  execute 'revoke execute on function public.delete_own_account() from public, anon';
  execute 'grant execute on function public.delete_own_account() to authenticated, service_role';

  select
    function_row.oid,
    function_row.proowner,
    function_row.prosecdef,
    function_row.prolang,
    function_row.prokind,
    function_row.prorettype,
    function_row.proretset,
    function_row.proargtypes,
    function_row.proallargtypes,
    function_row.proargmodes,
    function_row.proargnames,
    function_row.prosrc,
    function_row.probin,
    function_row.prosqlbody::text as prosqlbody,
    function_row.provolatile,
    function_row.proisstrict,
    function_row.proparallel,
    function_row.proconfig,
    function_row.proacl,
    pg_catalog.pg_get_function_identity_arguments(function_row.oid) as identity_arguments,
    pg_catalog.pg_get_function_result(function_row.oid) as result_type
  into strict after_state
  from pg_catalog.pg_proc as function_row
  where function_row.oid = target_oid;

  if after_state.oid <> before_state.oid
     or after_state.proowner <> before_state.proowner
     or after_state.prosecdef is distinct from before_state.prosecdef
     or after_state.prolang <> before_state.prolang
     or after_state.prokind <> before_state.prokind
     or after_state.prorettype <> before_state.prorettype
     or after_state.proretset is distinct from before_state.proretset
     or after_state.proargtypes <> before_state.proargtypes
     or after_state.proallargtypes is distinct from before_state.proallargtypes
     or after_state.proargmodes is distinct from before_state.proargmodes
     or after_state.proargnames is distinct from before_state.proargnames
     or after_state.prosrc is distinct from before_state.prosrc
     or after_state.probin is distinct from before_state.probin
     or after_state.prosqlbody is distinct from before_state.prosqlbody
     or after_state.provolatile <> before_state.provolatile
     or after_state.proisstrict is distinct from before_state.proisstrict
     or after_state.proparallel <> before_state.proparallel
     or after_state.identity_arguments <> before_state.identity_arguments
     or after_state.result_type <> before_state.result_type then
    raise exception
      'public.delete_own_account() identity or implementation drifted.'
      using errcode = '55000';
  end if;

  if after_state.proconfig <> array['search_path=""']::text[]
     or pg_catalog.has_function_privilege('anon', target_oid, 'EXECUTE')
     or not pg_catalog.has_function_privilege('authenticated', target_oid, 'EXECUTE')
     or not pg_catalog.has_function_privilege('service_role', target_oid, 'EXECUTE')
     or (
       select count(*) <> 3
         or bool_or(
           acl_row.grantee not in (
             after_state.proowner,
             (select oid from pg_catalog.pg_roles where rolname = 'authenticated'),
             (select oid from pg_catalog.pg_roles where rolname = 'service_role')
           )
         )
         or bool_or(
           acl_row.grantee in (
             (select oid from pg_catalog.pg_roles where rolname = 'authenticated'),
             (select oid from pg_catalog.pg_roles where rolname = 'service_role')
           )
           and acl_row.is_grantable
         )
       from pg_catalog.aclexplode(
         coalesce(
           after_state.proacl,
           pg_catalog.acldefault('f', after_state.proowner)
         )
       ) as acl_row
       where acl_row.privilege_type = 'EXECUTE'
     )
     or exists (
       select 1
       from pg_catalog.aclexplode(
         coalesce(
           after_state.proacl,
           pg_catalog.acldefault('f', after_state.proowner)
         )
       ) as acl_row
       where acl_row.privilege_type = 'EXECUTE'
         and acl_row.grantee in (
           0::oid,
           (select oid from pg_catalog.pg_roles where rolname = 'anon')
         )
     ) then
    raise exception
      'public.delete_own_account() configuration or ACL is incorrect.'
      using errcode = '55000';
  end if;
end;
$migration$;
