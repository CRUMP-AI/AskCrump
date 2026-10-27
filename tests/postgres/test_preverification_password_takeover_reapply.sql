\set ON_ERROR_STOP on

-- A later idempotent migration reapply must not invalidate passwords that were
-- established through inbox proof after the first rollout.
do $$
begin
  if exists (
    select 1
      from public.users as account
     where account.id in (
       '70000000-0000-4000-8000-000000000003',
       '70000000-0000-4000-8000-000000000010',
       '70000000-0000-4000-8000-000000000020'
     )
       and (
         account.password_setup_required is not false
         or account.password_inbox_bound_at is null
         or account.password_hash = '!pending-inbox-password-setup-v1!'
       )
  ) then
    raise exception 'Migration reapply invalidated an inbox-bound password.';
  end if;

  if not exists (
    select 1
      from public.sessions as session
     where session.id = '71000000-0000-4000-8000-000000000012'
       and session.revoked_at is null
  ) or not exists (
    select 1
      from public.sessions as session
     where session.id = '71000000-0000-4000-8000-000000000022'
       and session.revoked_at is null
  ) then
    raise exception 'Migration reapply revoked a post-proof login session.';
  end if;

  if exists (
    select 1
      from public.users as account
     where account.id in (
       '70000000-0000-4000-8000-000000000001',
       '70000000-0000-4000-8000-000000000002'
     )
       and (
         account.password_setup_required is not true
         or account.password_inbox_bound_at is not null
         or account.password_hash <> '!pending-inbox-password-setup-v1!'
       )
  ) then
    raise exception 'Migration reapply reopened a pending credential.';
  end if;
end;
$$;
