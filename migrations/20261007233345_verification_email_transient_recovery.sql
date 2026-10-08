-- Ask Crump 5.9.76
-- Default-off, one-shot recovery for verification messages with a signed,
-- transient provider delivery failure. No address, recipient hash, message
-- content, token, raw provider ID, URL, header, IP, or payload is retained.

begin;

set local lock_timeout = '5s';
set local statement_timeout = '20s';

create schema if not exists private;
revoke all on schema private from public, anon, authenticated, service_role;

create table if not exists private.verification_email_recovery_attempts (
  provider_email_hash text primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  environment text not null,
  message_kind text not null default 'verification',
  attempt_count smallint not null default 0,
  token_expires_at timestamptz not null,
  state text not null default 'sent',
  retry_after timestamptz,
  retry_provider_email_hash text unique,
  claim_token uuid,
  lease_expires_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint verification_email_recovery_provider_hash_check check (
    provider_email_hash ~ '^[0-9a-f]{64}$'
  ),
  constraint verification_email_recovery_retry_hash_check check (
    retry_provider_email_hash is null
    or retry_provider_email_hash ~ '^[0-9a-f]{64}$'
  ),
  constraint verification_email_recovery_environment_check check (
    environment in ('production', 'preview', 'development', 'test')
  ),
  constraint verification_email_recovery_kind_check check (
    message_kind = 'verification'
  ),
  constraint verification_email_recovery_attempt_count_check check (
    attempt_count in (0, 1)
  ),
  constraint verification_email_recovery_state_check check (
    state in (
      'sent', 'eligible', 'claimed', 'sending', 'retry_sent',
      'delivered', 'terminal', 'exhausted', 'send_failed', 'cancelled'
    )
  ),
  constraint verification_email_recovery_claim_check check (
    (
      state in ('claimed', 'sending')
      and claim_token is not null
      and lease_expires_at is not null
    )
    or (
      state not in ('claimed', 'sending')
      and claim_token is null
      and lease_expires_at is null
    )
  ),
  constraint verification_email_recovery_retry_identity_check check (
    retry_provider_email_hash is null
    or (
      attempt_count = 1
      and state in (
        'retry_sent', 'delivered', 'terminal', 'exhausted', 'cancelled'
      )
    )
  )
);

create index if not exists verification_email_recovery_user_idx
  on private.verification_email_recovery_attempts (user_id);

create index if not exists verification_email_recovery_due_idx
  on private.verification_email_recovery_attempts (
    state,
    retry_after,
    created_at
  )
  where state in ('eligible', 'claimed');

create unique index if not exists verification_email_recovery_one_active_user_idx
  on private.verification_email_recovery_attempts (user_id)
  where state in ('sent', 'eligible', 'claimed', 'sending', 'retry_sent');

alter table private.verification_email_recovery_attempts enable row level security;
alter table private.verification_email_recovery_attempts force row level security;
revoke all on table private.verification_email_recovery_attempts
  from public, anon, authenticated, service_role;

comment on table private.verification_email_recovery_attempts is
  'Service-only, content-free state for at most one delayed verification-email retry. Provider identities are lowercase SHA-256 values and raw identities, addresses, recipient hashes, content, URLs, and tokens are prohibited.';

create or replace function public.register_verification_email_recovery_attempt(
  p_provider_email_hash text,
  p_user_id uuid,
  p_environment text,
  p_token_expires_at timestamptz
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $function$
declare
  existing private.verification_email_recovery_attempts%rowtype;
  candidate_user public.users%rowtype;
begin
  if coalesce(p_provider_email_hash, '') !~ '^[0-9a-f]{64}$'
     or p_user_id is null
     or coalesce(p_environment, '') not in (
       'production', 'preview', 'development', 'test'
     )
     or p_token_expires_at is null
     or p_token_expires_at <= pg_catalog.clock_timestamp()
     or p_token_expires_at > pg_catalog.clock_timestamp() + interval '25 hours'
  then
    raise exception 'Invalid verification recovery registration.'
      using errcode = '22023';
  end if;

  select attempts.* into existing
  from private.verification_email_recovery_attempts as attempts
  where attempts.provider_email_hash = p_provider_email_hash;

  if found then
    if existing.user_id = p_user_id
       and existing.environment = p_environment
       and existing.message_kind = 'verification'
       and existing.token_expires_at = p_token_expires_at
    then
      return false;
    end if;
    raise exception 'Verification recovery identity conflict.'
      using errcode = '22023';
  end if;

  if exists (
    select 1
    from private.verification_email_recovery_attempts as attempts
    where attempts.retry_provider_email_hash = p_provider_email_hash
  ) then
    raise exception 'Verification recovery identity conflict.'
      using errcode = '22023';
  end if;

  select users.* into candidate_user
  from public.users as users
  where users.id = p_user_id
  for update;

  if not found
     or candidate_user.is_verified
     or candidate_user.verification_token_hash is null
     or candidate_user.verification_token_expires is distinct from p_token_expires_at
  then
    raise exception 'Verification recovery account is not eligible.'
      using errcode = '22023';
  end if;

  update private.verification_email_recovery_attempts as attempts
  set state = 'cancelled',
      claim_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where attempts.user_id = p_user_id
    and attempts.state in ('sent', 'eligible', 'claimed', 'sending', 'retry_sent');

  insert into private.verification_email_recovery_attempts (
    provider_email_hash,
    user_id,
    environment,
    message_kind,
    attempt_count,
    token_expires_at,
    state
  ) values (
    p_provider_email_hash,
    p_user_id,
    p_environment,
    'verification',
    0,
    p_token_expires_at,
    'sent'
  );
  return true;
end;
$function$;

create or replace function public.record_resend_delivery_event_and_recovery(
  p_provider_event_hash text,
  p_provider_email_hash text,
  p_payload_fingerprint text,
  p_environment text,
  p_message_kind text,
  p_event_type text,
  p_outcome_class text,
  p_occurred_at timestamptz
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $function$
declare
  inserted boolean;
  signed_event private.resend_delivery_events%rowtype;
  attempt private.verification_email_recovery_attempts%rowtype;
  account_verified boolean;
begin
  inserted := public.record_resend_delivery_event(
    p_provider_event_hash,
    p_provider_email_hash,
    p_payload_fingerprint,
    p_environment,
    p_message_kind,
    p_event_type,
    p_outcome_class,
    p_occurred_at
  );

  select events.* into strict signed_event
  from private.resend_delivery_events as events
  where events.provider_event_hash = p_provider_event_hash;

  if signed_event.message_kind <> 'verification' then
    return inserted;
  end if;

  select attempts.* into attempt
  from private.verification_email_recovery_attempts as attempts
  where attempts.environment = signed_event.environment
    and (
      attempts.provider_email_hash = signed_event.provider_email_hash
      or attempts.retry_provider_email_hash = signed_event.provider_email_hash
    )
  for update;

  if not found then
    return inserted;
  end if;

  select users.is_verified into account_verified
  from public.users as users
  where users.id = attempt.user_id;

  if account_verified is distinct from false
     or attempt.token_expires_at <= pg_catalog.clock_timestamp()
  then
    update private.verification_email_recovery_attempts
    set state = 'cancelled',
        claim_token = null,
        lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash;
    return inserted;
  end if;

  if signed_event.outcome_class = 'delivered' then
    update private.verification_email_recovery_attempts
    set state = 'delivered',
        claim_token = null,
        lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash;
  elsif signed_event.outcome_class in (
    'permanent', 'failed', 'suppressed', 'complaint'
  ) then
    update private.verification_email_recovery_attempts
    set state = 'terminal',
        claim_token = null,
        lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash;
  elsif signed_event.outcome_class = 'transient'
        and signed_event.provider_email_hash = attempt.provider_email_hash
        and attempt.attempt_count = 0
        and attempt.state = 'sent'
  then
    update private.verification_email_recovery_attempts
    set state = 'eligible',
        retry_after = greatest(
          pg_catalog.clock_timestamp() + interval '10 minutes',
          signed_event.occurred_at + interval '10 minutes'
        ),
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash;
  elsif signed_event.outcome_class = 'transient'
        and signed_event.provider_email_hash = attempt.retry_provider_email_hash
        and attempt.attempt_count = 1
        and attempt.state = 'retry_sent'
  then
    update private.verification_email_recovery_attempts
    set state = 'exhausted',
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash;
  end if;

  return inserted;
end;
$function$;

create or replace function public.claim_verification_email_recovery(
  p_claim_token uuid
)
returns table (
  provider_email_hash text,
  user_id uuid,
  claim_token uuid,
  previous_token_hash text,
  previous_token_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if p_claim_token is null then
    raise exception 'A recovery claim token is required.' using errcode = '22023';
  end if;

  update private.verification_email_recovery_attempts as attempts
  set state = 'cancelled',
      claim_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  from public.users as users
  where users.id = attempts.user_id
    and attempts.state in ('sent', 'eligible', 'claimed')
    and (
      users.is_verified
      or users.verification_token_hash is null
      or users.verification_token_expires is null
      or users.verification_token_expires <= pg_catalog.clock_timestamp()
      or users.verification_token_expires is distinct from attempts.token_expires_at
    );

  update private.verification_email_recovery_attempts as attempts
  set state = 'eligible',
      claim_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where attempts.state = 'claimed'
    and attempts.attempt_count = 0
    and attempts.lease_expires_at <= pg_catalog.clock_timestamp();

  update private.verification_email_recovery_attempts as attempts
  set state = 'send_failed',
      claim_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where attempts.state = 'sending'
    and attempts.attempt_count = 1
    and attempts.lease_expires_at <= pg_catalog.clock_timestamp();

  return query
  with candidate as (
    select attempts.provider_email_hash
    from private.verification_email_recovery_attempts as attempts
    join public.users as users on users.id = attempts.user_id
    where attempts.state = 'eligible'
      and attempts.attempt_count = 0
      and attempts.retry_after <= pg_catalog.clock_timestamp()
      and attempts.token_expires_at > pg_catalog.clock_timestamp()
      and not users.is_verified
      and users.verification_token_hash is not null
      and users.verification_token_expires = attempts.token_expires_at
    order by attempts.retry_after, attempts.created_at
    limit 1
    for update of attempts skip locked
  )
  update private.verification_email_recovery_attempts as attempts
  set state = 'claimed',
      claim_token = p_claim_token,
      lease_expires_at = pg_catalog.clock_timestamp() + interval '2 minutes',
      updated_at = pg_catalog.clock_timestamp()
  from public.users as users
  where attempts.provider_email_hash = (
      select candidate.provider_email_hash from candidate
    )
    and users.id = attempts.user_id
  returning
    attempts.provider_email_hash,
    attempts.user_id,
    p_claim_token,
    users.verification_token_hash,
    users.verification_token_expires;
end;
$function$;

create or replace function public.prepare_verification_email_recovery(
  p_provider_email_hash text,
  p_claim_token uuid,
  p_previous_token_hash text,
  p_previous_token_expires_at timestamptz,
  p_new_token_hash text,
  p_new_token_expires_at timestamptz
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $function$
declare
  attempt private.verification_email_recovery_attempts%rowtype;
  candidate_user public.users%rowtype;
begin
  if coalesce(p_provider_email_hash, '') !~ '^[0-9a-f]{64}$'
     or p_claim_token is null
     or coalesce(p_previous_token_hash, '') !~ '^[0-9a-f]{64}$'
     or p_previous_token_expires_at is null
     or coalesce(p_new_token_hash, '') !~ '^[0-9a-f]{64}$'
     or p_new_token_expires_at is null
     or p_new_token_expires_at <= pg_catalog.clock_timestamp()
     or p_new_token_expires_at > pg_catalog.clock_timestamp() + interval '25 hours'
  then
    raise exception 'Invalid recovery preparation.' using errcode = '22023';
  end if;

  select attempts.* into attempt
  from private.verification_email_recovery_attempts as attempts
  where attempts.provider_email_hash = p_provider_email_hash
  for update;

  if not found
     or attempt.state <> 'claimed'
     or attempt.attempt_count <> 0
     or attempt.claim_token <> p_claim_token
     or attempt.lease_expires_at <= pg_catalog.clock_timestamp()
  then
    return false;
  end if;

  select users.* into candidate_user
  from public.users as users
  where users.id = attempt.user_id
  for update;

  if not found
     or candidate_user.is_verified
     or candidate_user.verification_token_hash is distinct from p_previous_token_hash
     or candidate_user.verification_token_expires is distinct from p_previous_token_expires_at
  then
    update private.verification_email_recovery_attempts
    set state = 'cancelled',
        claim_token = null,
        lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = p_provider_email_hash;
    return false;
  end if;

  update public.users
  set verification_token_hash = p_new_token_hash,
      verification_token_expires = p_new_token_expires_at,
      updated_at = pg_catalog.clock_timestamp()
  where id = attempt.user_id;

  update private.verification_email_recovery_attempts
  set state = 'sending',
      attempt_count = 1,
      token_expires_at = p_new_token_expires_at,
      lease_expires_at = pg_catalog.clock_timestamp() + interval '2 minutes',
      updated_at = pg_catalog.clock_timestamp()
  where provider_email_hash = p_provider_email_hash;
  return true;
end;
$function$;

create or replace function public.complete_verification_email_recovery(
  p_provider_email_hash text,
  p_claim_token uuid,
  p_retry_provider_email_hash text,
  p_new_token_expires_at timestamptz
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $function$
declare
  attempt private.verification_email_recovery_attempts%rowtype;
begin
  if coalesce(p_provider_email_hash, '') !~ '^[0-9a-f]{64}$'
     or coalesce(p_retry_provider_email_hash, '') !~ '^[0-9a-f]{64}$'
     or p_provider_email_hash = p_retry_provider_email_hash
     or p_claim_token is null
     or p_new_token_expires_at is null
  then
    raise exception 'Invalid recovery completion.' using errcode = '22023';
  end if;

  select attempts.* into attempt
  from private.verification_email_recovery_attempts as attempts
  where attempts.provider_email_hash = p_provider_email_hash
  for update;

  if found
     and attempt.state = 'retry_sent'
     and attempt.retry_provider_email_hash = p_retry_provider_email_hash
     and attempt.token_expires_at = p_new_token_expires_at
  then
    return false;
  end if;

  if not found
     or attempt.state <> 'sending'
     or attempt.attempt_count <> 1
     or attempt.claim_token <> p_claim_token
     or attempt.lease_expires_at <= pg_catalog.clock_timestamp()
     or attempt.token_expires_at <> p_new_token_expires_at
  then
    return false;
  end if;

  if exists (
    select 1
    from private.verification_email_recovery_attempts as other_attempts
    where other_attempts.provider_email_hash <> p_provider_email_hash
      and (
        other_attempts.provider_email_hash = p_retry_provider_email_hash
        or other_attempts.retry_provider_email_hash = p_retry_provider_email_hash
      )
  ) then
    raise exception 'Verification recovery retry identity conflict.'
      using errcode = '22023';
  end if;

  update private.verification_email_recovery_attempts
  set state = 'retry_sent',
      retry_provider_email_hash = p_retry_provider_email_hash,
      claim_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where provider_email_hash = p_provider_email_hash;
  return true;
end;
$function$;

create or replace function public.fail_verification_email_recovery(
  p_provider_email_hash text,
  p_claim_token uuid,
  p_expected_token_hash text,
  p_previous_token_hash text,
  p_previous_token_expires_at timestamptz
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $function$
declare
  attempt private.verification_email_recovery_attempts%rowtype;
begin
  if coalesce(p_provider_email_hash, '') !~ '^[0-9a-f]{64}$'
     or p_claim_token is null
     or coalesce(p_expected_token_hash, '') !~ '^[0-9a-f]{64}$'
     or coalesce(p_previous_token_hash, '') !~ '^[0-9a-f]{64}$'
     or p_previous_token_expires_at is null
  then
    raise exception 'Invalid recovery failure rollback.' using errcode = '22023';
  end if;

  select attempts.* into attempt
  from private.verification_email_recovery_attempts as attempts
  where attempts.provider_email_hash = p_provider_email_hash
  for update;

  if found and attempt.state = 'send_failed' then
    return false;
  end if;

  if not found
     or attempt.state <> 'sending'
     or attempt.attempt_count <> 1
     or attempt.claim_token <> p_claim_token
  then
    return false;
  end if;

  update public.users
  set verification_token_hash = p_previous_token_hash,
      verification_token_expires = p_previous_token_expires_at,
      updated_at = pg_catalog.clock_timestamp()
  where id = attempt.user_id
    and not is_verified
    and verification_token_hash = p_expected_token_hash;

  update private.verification_email_recovery_attempts
  set state = 'send_failed',
      claim_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where provider_email_hash = p_provider_email_hash;
  return true;
end;
$function$;

revoke all on function public.register_verification_email_recovery_attempt(
  text, uuid, text, timestamptz
) from public, anon, authenticated, service_role;
revoke all on function public.record_resend_delivery_event_and_recovery(
  text, text, text, text, text, text, text, timestamptz
) from public, anon, authenticated, service_role;
revoke all on function public.claim_verification_email_recovery(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.prepare_verification_email_recovery(
  text, uuid, text, timestamptz, text, timestamptz
) from public, anon, authenticated, service_role;
revoke all on function public.complete_verification_email_recovery(
  text, uuid, text, timestamptz
) from public, anon, authenticated, service_role;
revoke all on function public.fail_verification_email_recovery(
  text, uuid, text, text, timestamptz
) from public, anon, authenticated, service_role;

grant execute on function public.register_verification_email_recovery_attempt(
  text, uuid, text, timestamptz
) to service_role;
grant execute on function public.record_resend_delivery_event_and_recovery(
  text, text, text, text, text, text, text, timestamptz
) to service_role;
grant execute on function public.claim_verification_email_recovery(uuid)
  to service_role;
grant execute on function public.prepare_verification_email_recovery(
  text, uuid, text, timestamptz, text, timestamptz
) to service_role;
grant execute on function public.complete_verification_email_recovery(
  text, uuid, text, timestamptz
) to service_role;
grant execute on function public.fail_verification_email_recovery(
  text, uuid, text, text, timestamptz
) to service_role;

comment on function public.register_verification_email_recovery_attempt(
  text, uuid, text, timestamptz
) is 'Service-only registration of an accepted verification message using only a provider-message SHA-256 correlation.';
comment on function public.record_resend_delivery_event_and_recovery(
  text, text, text, text, text, text, text, timestamptz
) is 'Service-only atomic signed-event receipt and default-off verification recovery state transition.';
comment on function public.claim_verification_email_recovery(uuid)
  is 'Service-only SKIP LOCKED claim for one due, unverified, unexpired verification recovery.';
comment on function public.prepare_verification_email_recovery(
  text, uuid, text, timestamptz, text, timestamptz
) is 'Service-only fenced token rotation after a successful recovery claim.';
comment on function public.complete_verification_email_recovery(
  text, uuid, text, timestamptz
) is 'Service-only completion that binds the one retry to a hashed provider message identity.';
comment on function public.fail_verification_email_recovery(
  text, uuid, text, text, timestamptz
) is 'Service-only fenced rollback after the sole provider retry fails.';

commit;
