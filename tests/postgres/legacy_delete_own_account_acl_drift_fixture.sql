\set ON_ERROR_STOP on

-- Return the earlier definition-drift fixture to the exact reviewed hardened
-- definition, then introduce an unexpected direct executor. The migration
-- must refuse the ACL drift instead of silently preserving it.
alter function public.delete_own_account() volatile;

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'rogue_executor'
  ) then
    create role rogue_executor nologin;
  end if;
end;
$$;

grant execute on function public.delete_own_account() to rogue_executor;
