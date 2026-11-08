-- Disposable current-main substrate for account lifecycle/connected-chat lock gates.
\set ON_ERROR_STOP on

\ir registration_growth_cohort_baseline.sql
\ir account_lifecycle_connected_owner_lock_prerequisites.sql

begin;
\ir ../../migrations/002_server_authoritative_chat_sync.sql
commit;
\ir ../../migrations/20260908134343_durable_growth_measurement.sql
begin;
\ir ../../migrations/20260913192512_clarify_optional_profile_growth_metric.sql
commit;
begin;
\ir ../../migrations/20260924210000_durable_account_storage_deletion.sql
commit;
\ir ../../migrations/20261001084000_project_artifact_continuity_aggregate.sql
begin;
\ir ../../migrations/20261021003000_guest_mode.sql
commit;
begin;
\ir ../../migrations/20261021020000_guest_message_receipts.sql
commit;
begin;
\ir ../../migrations/20261021030000_guest_sync_admission.sql
commit;
begin;
\ir ../../migrations/20261021040000_guest_mode_control.sql
commit;
\ir ../../migrations/20261023191029_registration_submission_cohorts.sql
\ir ../../migrations/20261024043331_email_verification_measurement.sql
begin;
\ir ../../migrations/20261024051228_atomic_password_reset.sql
commit;

set role service_role;
select * from public.set_guest_mode_enabled_v1(true);
reset role;
\ir preverification_password_takeover_fixture.sql
begin;
\ir ../../migrations/20261027013000_preverification_password_takeover_fix.sql
commit;

-- The production claim migration also touches unrelated manuscript/billing
-- surfaces. Reproduce only its exact chat prerequisite here.
alter table public.chat_jobs
  add column if not exists chat_id uuid,
  add column if not exists message_id uuid,
  add column if not exists response_data jsonb,
  add column if not exists error_code text,
  add column if not exists claim_token uuid;
create unique index if not exists chat_jobs_user_message_key
  on public.chat_jobs(user_id, message_id);
create or replace function public.claim_chat_job_v2(
  p_user_id uuid, p_chat_id uuid, p_message_id uuid
)
returns table(job_state text, response_data jsonb, claim_token uuid)
language plpgsql security definer set search_path = public
as $function$
declare
  current_job public.chat_jobs%rowtype;
  next_claim_token uuid := gen_random_uuid();
begin
  insert into public.chat_jobs(user_id, chat_id, message_id, status, claim_token)
  values (p_user_id, p_chat_id, p_message_id, 'processing', next_claim_token)
  on conflict (user_id, message_id) do nothing returning * into current_job;
  if found then
    return query select 'claimed'::text, null::jsonb, current_job.claim_token;
    return;
  end if;
  select * into current_job from public.chat_jobs
   where user_id = p_user_id and message_id = p_message_id for update;
  if current_job.status = 'completed' then
    return query select 'completed'::text, current_job.response_data, null::uuid;
    return;
  end if;
  if current_job.status = 'processing'
     and current_job.updated_at > now() - interval '8 minutes' then
    return query select 'busy'::text, null::jsonb, null::uuid;
    return;
  end if;
  update public.chat_jobs set status='processing', chat_id=p_chat_id,
    response_data=null, error_code=null, claim_token=next_claim_token,
    updated_at=now() where id=current_job.id returning * into current_job;
  return query select 'claimed'::text, null::jsonb, current_job.claim_token;
end;
$function$;
revoke all on function public.claim_chat_job_v2(uuid,uuid,uuid)
  from public, anon, authenticated;
grant execute on function public.claim_chat_job_v2(uuid,uuid,uuid) to service_role;

\ir ../../migrations/20261107190000_connected_app_control_plane.sql
\ir ../../migrations/20261107230000_connected_app_secret_payload_stores.sql
\ir ../../migrations/20261107231500_connected_app_oauth_secret_custody.sql
\ir ../../migrations/20261107233000_connected_app_encrypted_read_results.sql
\ir ../../migrations/20261108020000_connected_chat_turn_binding.sql
\ir ../../migrations/20261108023000_connected_plan_once.sql
\ir ../../migrations/20261108040000_connected_operator_chat_completion.sql
\ir ../../migrations/20261108043000_connected_dispatch_execution_outbox.sql
\ir ../../migrations/20261108050000_connected_oauth_runtime_authority.sql
\ir ../../migrations/20261108052000_connected_chat_action_stage.sql
