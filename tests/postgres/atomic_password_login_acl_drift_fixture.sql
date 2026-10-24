\set ON_ERROR_STOP on

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'unexpected_login_executor'
  ) then
    create role unexpected_login_executor nologin;
  end if;
end;
$$;

grant execute on function public.finalize_password_login_v1(
  uuid, text, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) to unexpected_login_executor;
