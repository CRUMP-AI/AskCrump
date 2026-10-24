\set ON_ERROR_STOP on

do $$
begin
  if pg_catalog.to_regprocedure(
       'public.consume_password_reset_v1(text,text)'
     ) is not null
     or pg_catalog.to_regclass(
       'public.users_password_reset_token_hash_unique'
     ) is not null then
    raise exception 'Refused password-reset migration left partial schema state.';
  end if;

  if (
    select count(*)
    from public.users
    where password_reset_token_hash = repeat('9', 64)
  ) <> 2 then
    raise exception 'Refused password-reset migration changed fixture users.';
  end if;
end;
$$;

update public.users
   set password_reset_token_hash = null,
       password_reset_expires = null
 where password_reset_token_hash = repeat('9', 64);
