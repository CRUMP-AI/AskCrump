\set ON_ERROR_STOP on

do $$
begin
  if pg_catalog.to_regprocedure(
       'public.consume_password_reset_v1(text,text)'
     ) is null
     or pg_catalog.to_regclass(
       'public.users_password_reset_token_hash_unique'
     ) is null
     or not pg_catalog.has_function_privilege(
       'unexpected_reset_executor',
       'public.consume_password_reset_v1(text,text)',
       'EXECUTE'
     ) then
    raise exception 'ACL-drift refusal changed existing password-reset state.';
  end if;
end;
$$;

revoke execute on function public.consume_password_reset_v1(text, text)
  from unexpected_reset_executor;
drop role unexpected_reset_executor;

do $$
begin
  if pg_catalog.has_function_privilege(
       'anon',
       'public.consume_password_reset_v1(text,text)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'authenticated',
       'public.consume_password_reset_v1(text,text)',
       'EXECUTE'
     )
     or not pg_catalog.has_function_privilege(
       'service_role',
       'public.consume_password_reset_v1(text,text)',
       'EXECUTE'
     ) then
    raise exception 'Password-reset ACL cleanup disturbed expected roles.';
  end if;
end;
$$;
