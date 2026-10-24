\set ON_ERROR_STOP on

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_roles
    where rolname = 'unexpected_verification_executor'
  ) then
    create role unexpected_verification_executor nologin;
  end if;
end;
$$;

grant execute on function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) to unexpected_verification_executor;
