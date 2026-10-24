\set ON_ERROR_STOP on

update public.users
   set password_reset_token_hash = repeat('9', 64),
       password_reset_expires = pg_catalog.clock_timestamp() + interval '1 hour'
 where id in (
   '10000000-0000-4000-8000-000000000001',
   '10000000-0000-4000-8000-000000000002'
 );

do $$
begin
  if (
    select count(*)
    from public.users
    where password_reset_token_hash = repeat('9', 64)
  ) <> 2 then
    raise exception 'Duplicate password-reset refusal fixture was not installed.';
  end if;
end;
$$;
