\set ON_ERROR_STOP on

revoke execute on function public.finalize_password_login_v1(
  uuid, text, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) from unexpected_login_executor;

drop role unexpected_login_executor;
