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
  has_function_privilege(
    'rogue_executor',
    'public.delete_own_account()',
    'EXECUTE'
  ),
  'ACL-drift refusal did not preserve the pre-migration rogue grant'
);

select pg_temp.assert_true(
  (
    select function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
    from pg_catalog.pg_proc as function_row
    where function_row.oid = 'public.delete_own_account()'::regprocedure
  ),
  'ACL-drift refusal changed the reviewed hardened definition'
);

select pg_temp.assert_true(
  exists (
    select 1 from auth.users
    where id = '10000000-0000-4000-8000-000000000002'
  ),
  'ACL-drift refusal changed synthetic user B'
);
