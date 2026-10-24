\set ON_ERROR_STOP on

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_roles
    where rolname = 'unexpected_reset_executor'
  ) then
    create role unexpected_reset_executor nologin;
  end if;
end;
$$;

grant execute on function public.consume_password_reset_v1(text, text)
  to unexpected_reset_executor;

do $$
begin
  if not pg_catalog.has_function_privilege(
    'unexpected_reset_executor',
    'public.consume_password_reset_v1(text,text)',
    'EXECUTE'
  ) then
    raise exception 'Password-reset ACL drift fixture was not installed.';
  end if;
end;
$$;
