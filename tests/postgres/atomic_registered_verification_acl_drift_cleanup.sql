\set ON_ERROR_STOP on

revoke execute on function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) from unexpected_verification_executor;

drop role unexpected_verification_executor;
