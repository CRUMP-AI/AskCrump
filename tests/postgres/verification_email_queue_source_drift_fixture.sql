create or replace function public.claim_verification_email_job_v1(
  p_claim_token uuid,
  p_lease_seconds integer default 120
)
returns table (job_id uuid, lease_token uuid, attempts integer)
language plpgsql
volatile
security definer
set search_path = ''
as $$
begin
  -- ASK_CRUMP_VERIFICATION_EMAIL_QUEUE_V1
  -- Deliberately wrong while preserving the marker and execution attributes.
  return query select null::uuid, null::uuid, null::integer where false;
end;
$$;

alter function public.claim_verification_email_job_v1(uuid, integer) owner to postgres;
revoke all on function public.claim_verification_email_job_v1(uuid, integer)
  from public, anon, authenticated, service_role;
grant execute on function public.claim_verification_email_job_v1(uuid, integer)
  to service_role;
