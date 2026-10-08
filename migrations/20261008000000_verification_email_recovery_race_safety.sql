-- Ask Crump 5.9.76
-- Release-blocking race-safety follow-up for the still source-locked
-- verification-email recovery path. No production enablement is performed.

begin;

set local lock_timeout = '5s';
set local statement_timeout = '20s';

create or replace function private.verification_recovery_outcome_rank(
  p_outcome text
)
returns integer
language sql
immutable
strict
set search_path = ''
as $function$
  select case p_outcome
    when 'accepted' then 10
    when 'transient' then 20
    when 'delivered' then 80
    when 'failed' then 100
    when 'permanent' then 110
    when 'suppressed' then 120
    when 'complaint' then 130
    else 0
  end
$function$;

alter table private.verification_email_recovery_attempts
  drop constraint verification_email_recovery_state_check,
  drop constraint verification_email_recovery_claim_check,
  drop constraint verification_email_recovery_retry_identity_check;

alter table private.verification_email_recovery_attempts
  add column outcome_class text not null default 'accepted',
  add column recovery_token_hash text,
  add column recovery_token_expires_at timestamptz,
  add column dispatch_authorized_at timestamptz;

-- The feature has never been source-released. Fail closed if a fixture or an
-- abandoned local run left a legacy post-prepare row behind.
update private.verification_email_recovery_attempts
set state = 'cancelled',
    attempt_count = 0,
    retry_provider_email_hash = null,
    claim_token = null,
    lease_expires_at = null,
    updated_at = pg_catalog.clock_timestamp()
where attempt_count = 1;

alter table private.verification_email_recovery_attempts
  add constraint verification_email_recovery_token_hash_check check (
    recovery_token_hash is null
    or recovery_token_hash ~ '^[0-9a-f]{64}$'
  ),
  add constraint verification_email_recovery_outcome_check check (
    outcome_class in (
      'accepted', 'transient', 'delivered', 'permanent',
      'failed', 'suppressed', 'complaint'
    )
  ),
  add constraint verification_email_recovery_state_check check (
    state in (
      'sent', 'eligible', 'claimed', 'prepared', 'dispatch_authorized',
      'retry_sent', 'delivered', 'terminal', 'exhausted', 'send_failed',
      'cancelled', 'verified'
    )
  ),
  add constraint verification_email_recovery_claim_check check (
    (
      state in ('claimed', 'prepared', 'dispatch_authorized')
      and claim_token is not null
      and lease_expires_at is not null
    )
    or (
      state not in ('claimed', 'prepared', 'dispatch_authorized')
      and claim_token is null
      and lease_expires_at is null
    )
  ),
  add constraint verification_email_recovery_preparation_check check (
    (
      attempt_count = 0
      and recovery_token_hash is null
      and recovery_token_expires_at is null
      and dispatch_authorized_at is null
    )
    or (
      attempt_count = 1
      and recovery_token_hash is not null
      and recovery_token_expires_at is not null
    )
  ),
  add constraint verification_email_recovery_dispatch_check check (
    dispatch_authorized_at is null
    or state in (
      'dispatch_authorized', 'retry_sent', 'delivered', 'terminal',
      'exhausted', 'send_failed', 'cancelled', 'verified'
    )
  ),
  add constraint verification_email_recovery_retry_identity_check check (
    retry_provider_email_hash is null
    or (
      attempt_count = 1
      and state in (
        'retry_sent', 'delivered', 'terminal', 'exhausted',
        'cancelled', 'verified'
      )
    )
  );

drop index private.verification_email_recovery_due_idx;
drop index private.verification_email_recovery_one_active_user_idx;
create index verification_email_recovery_due_idx
  on private.verification_email_recovery_attempts (
    environment, state, retry_after, created_at
  )
  where state in ('eligible', 'claimed', 'prepared', 'dispatch_authorized');
create unique index verification_email_recovery_one_active_user_idx
  on private.verification_email_recovery_attempts (user_id, environment)
  where state in (
    'sent', 'eligible', 'claimed', 'prepared',
    'dispatch_authorized', 'retry_sent'
  );

comment on table private.verification_email_recovery_attempts is
  'Service-only, content-free one-shot verification retry state. Provider identities and the high-entropy recovery token use one-way SHA-256 digests; raw IDs, addresses, recipient-derived hashes, message content, URLs, and tokens are prohibited.';
comment on column private.verification_email_recovery_attempts.recovery_token_hash is
  'One-way SHA-256 digest of a high-entropy recovery token, retained only so an authorized send remains verifiable after an ambiguous HTTP/completion boundary.';

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
  prior_event private.resend_delivery_events%rowtype;
  initial_state text := 'sent';
  initial_outcome text := 'accepted';
  initial_retry_after timestamptz;
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

  -- Serialize registration with the signed-event wrapper for this exact
  -- environment/message pair. Hash collisions only create extra serialization.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'verification-email-recovery:' || p_environment || ':'
        || p_provider_email_hash,
      0
    )
  );

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
    select 1 from private.verification_email_recovery_attempts as attempts
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

  -- Atomically reconcile a signed callback that committed before registration.
  select events.* into prior_event
  from private.resend_delivery_events as events
  where events.provider_email_hash = p_provider_email_hash
    and events.environment = p_environment
    and events.message_kind = 'verification'
  order by
    private.verification_recovery_outcome_rank(events.outcome_class) desc,
    events.occurred_at desc,
    events.received_at desc
  limit 1;
  if found then
    initial_outcome := prior_event.outcome_class;
    if initial_outcome = 'transient' then
      initial_state := 'eligible';
      initial_retry_after := greatest(
        pg_catalog.clock_timestamp() + interval '10 minutes',
        prior_event.occurred_at + interval '10 minutes'
      );
    elsif initial_outcome = 'delivered' then
      initial_state := 'delivered';
    elsif initial_outcome in ('permanent', 'failed', 'suppressed', 'complaint') then
      initial_state := 'terminal';
    end if;
  end if;

  update private.verification_email_recovery_attempts as attempts
  set state = 'cancelled', claim_token = null, lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where attempts.user_id = p_user_id
    and attempts.environment = p_environment
    and attempts.state in (
      'sent', 'eligible', 'claimed', 'prepared',
      'dispatch_authorized', 'retry_sent'
    );

  insert into private.verification_email_recovery_attempts (
    provider_email_hash, user_id, environment, message_kind,
    attempt_count, token_expires_at, state, outcome_class, retry_after
  ) values (
    p_provider_email_hash, p_user_id, p_environment, 'verification',
    0, p_token_expires_at, initial_state, initial_outcome, initial_retry_after
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
    p_provider_event_hash, p_provider_email_hash, p_payload_fingerprint,
    p_environment, p_message_kind, p_event_type, p_outcome_class,
    p_occurred_at
  );

  -- Use the same lock as registration. If the event insert preceded a waiting
  -- registration, this wrapper observes the new attempt after the lock; if
  -- registration won, it observes the committed event while holding the lock.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'verification-email-recovery:' || p_environment || ':'
        || p_provider_email_hash,
      0
    )
  );

  -- Provider replays can preserve signed bytes while changing the event ID.
  select events.* into signed_event
  from private.resend_delivery_events as events
  where events.provider_event_hash = p_provider_event_hash
     or events.payload_fingerprint = p_payload_fingerprint
  order by (events.provider_event_hash = p_provider_event_hash) desc
  limit 1;
  if not found
     or signed_event.payload_fingerprint <> p_payload_fingerprint
     or signed_event.provider_email_hash <> p_provider_email_hash
     or signed_event.environment <> p_environment
     or signed_event.message_kind <> p_message_kind
     or signed_event.event_type <> p_event_type
     or signed_event.outcome_class <> p_outcome_class
     or signed_event.occurred_at <> p_occurred_at
  then
    raise exception 'Resend event replay mismatch.' using errcode = '22023';
  end if;

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
    set state = 'cancelled', claim_token = null, lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash
      and environment = signed_event.environment;
    return inserted;
  end if;

  -- Outcome is monotonic. Complaint/permanent/suppression/failed can never be
  -- downgraded by a late delivered or transient replay.
  if private.verification_recovery_outcome_rank(signed_event.outcome_class)
     <= private.verification_recovery_outcome_rank(attempt.outcome_class)
  then
    return inserted;
  end if;
  update private.verification_email_recovery_attempts
  set outcome_class = signed_event.outcome_class,
      updated_at = pg_catalog.clock_timestamp()
  where provider_email_hash = attempt.provider_email_hash
    and environment = signed_event.environment;

  -- Before authorization, original delivery or terminal state wins. After the
  -- authorization commit, the external HTTP send wins; only outcome advances.
  if signed_event.outcome_class = 'delivered'
     and attempt.state <> 'dispatch_authorized'
     and attempt.state not in ('cancelled', 'verified')
  then
    update private.verification_email_recovery_attempts
    set state = 'delivered', claim_token = null, lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash
      and environment = signed_event.environment;
  elsif signed_event.outcome_class in (
    'permanent', 'failed', 'suppressed', 'complaint'
  )
     and attempt.state <> 'dispatch_authorized'
     and attempt.state not in ('cancelled', 'verified')
  then
    update private.verification_email_recovery_attempts
    set state = 'terminal', claim_token = null, lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash
      and environment = signed_event.environment;
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
    where provider_email_hash = attempt.provider_email_hash
      and environment = signed_event.environment;
  elsif signed_event.outcome_class = 'transient'
        and signed_event.provider_email_hash = attempt.retry_provider_email_hash
        and attempt.attempt_count = 1
        and attempt.state = 'retry_sent'
  then
    update private.verification_email_recovery_attempts
    set state = 'exhausted', updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash
      and environment = signed_event.environment;
  end if;
  return inserted;
end;
$function$;

drop function public.claim_verification_email_recovery(uuid);
create function public.claim_verification_email_recovery(
  p_claim_token uuid,
  p_environment text
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
  if p_claim_token is null
     or coalesce(p_environment, '') not in (
       'production', 'preview', 'development', 'test'
     )
  then
    raise exception 'A valid recovery claim scope is required.'
      using errcode = '22023';
  end if;

  -- Eventual repair for the historical/lost-race state: a signed transient
  -- receipt may exist while registration remains `sent`. This makes the next
  -- environment-scoped claim reconcile it before selecting work.
  with authoritative as (
    select distinct on (attempts.provider_email_hash)
      attempts.provider_email_hash,
      events.outcome_class,
      events.occurred_at
    from private.verification_email_recovery_attempts as attempts
    join private.resend_delivery_events as events
      on events.provider_email_hash = attempts.provider_email_hash
     and events.environment = attempts.environment
     and events.message_kind = attempts.message_kind
    where attempts.environment = p_environment
      and attempts.state = 'sent'
      and attempts.attempt_count = 0
    order by attempts.provider_email_hash,
      private.verification_recovery_outcome_rank(events.outcome_class) desc,
      events.occurred_at desc,
      events.received_at desc
  )
  update private.verification_email_recovery_attempts as attempts
  set outcome_class = authoritative.outcome_class,
      state = case
        when authoritative.outcome_class = 'transient' then 'eligible'
        when authoritative.outcome_class = 'delivered' then 'delivered'
        when authoritative.outcome_class in (
          'permanent', 'failed', 'suppressed', 'complaint'
        ) then 'terminal'
        else attempts.state
      end,
      retry_after = case
        when authoritative.outcome_class = 'transient' then greatest(
          pg_catalog.clock_timestamp() + interval '10 minutes',
          authoritative.occurred_at + interval '10 minutes'
        )
        else attempts.retry_after
      end,
      updated_at = pg_catalog.clock_timestamp()
  from authoritative
  where attempts.provider_email_hash = authoritative.provider_email_hash
    and attempts.environment = p_environment
    and private.verification_recovery_outcome_rank(
      authoritative.outcome_class
    ) > private.verification_recovery_outcome_rank(attempts.outcome_class);

  update private.verification_email_recovery_attempts as attempts
  set state = 'cancelled', claim_token = null, lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  from public.users as users
  where users.id = attempts.user_id
    and attempts.environment = p_environment
    and attempts.state in (
      'sent', 'eligible', 'claimed', 'prepared', 'dispatch_authorized'
    )
    and (
      users.is_verified
      or users.verification_token_hash is null
      or users.verification_token_expires is null
      or users.verification_token_expires <= pg_catalog.clock_timestamp()
      or users.verification_token_expires is distinct from attempts.token_expires_at
    );

  update private.verification_email_recovery_attempts as attempts
  set state = 'eligible', claim_token = null, lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where attempts.environment = p_environment
    and attempts.state = 'claimed'
    and attempts.attempt_count = 0
    and attempts.lease_expires_at <= pg_catalog.clock_timestamp();
  update private.verification_email_recovery_attempts as attempts
  set state = 'send_failed', claim_token = null, lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where attempts.environment = p_environment
    and attempts.state = 'prepared'
    and attempts.attempt_count = 1
    and attempts.lease_expires_at <= pg_catalog.clock_timestamp();
  update private.verification_email_recovery_attempts as attempts
  set state = 'exhausted', claim_token = null, lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where attempts.environment = p_environment
    and attempts.state = 'dispatch_authorized'
    and attempts.attempt_count = 1
    and attempts.lease_expires_at <= pg_catalog.clock_timestamp();

  return query
  with candidate as (
    select attempts.provider_email_hash
    from private.verification_email_recovery_attempts as attempts
    join public.users as users on users.id = attempts.user_id
    where attempts.environment = p_environment
      and attempts.state = 'eligible'
      and attempts.outcome_class = 'transient'
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
  set state = 'claimed', claim_token = p_claim_token,
      lease_expires_at = pg_catalog.clock_timestamp() + interval '2 minutes',
      updated_at = pg_catalog.clock_timestamp()
  from public.users as users
  where attempts.provider_email_hash = (
      select candidate.provider_email_hash from candidate
    )
    and attempts.environment = p_environment
    and users.id = attempts.user_id
  returning attempts.provider_email_hash, attempts.user_id, p_claim_token,
    users.verification_token_hash, users.verification_token_expires;
end;
$function$;

drop function public.prepare_verification_email_recovery(
  text, uuid, text, timestamptz, text, timestamptz
);
create function public.prepare_verification_email_recovery(
  p_provider_email_hash text,
  p_claim_token uuid,
  p_previous_token_hash text,
  p_previous_token_expires_at timestamptz,
  p_new_token_hash text,
  p_new_token_expires_at timestamptz,
  p_environment text
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
     or coalesce(p_environment, '') not in (
       'production', 'preview', 'development', 'test'
     )
  then
    raise exception 'Invalid recovery preparation.' using errcode = '22023';
  end if;

  select attempts.* into attempt
  from private.verification_email_recovery_attempts as attempts
  where attempts.provider_email_hash = p_provider_email_hash
    and attempts.environment = p_environment
  for update;
  -- Exact replay after a committed-but-lost response is success-equivalent.
  if found
     and attempt.state = 'prepared'
     and attempt.attempt_count = 1
     and attempt.claim_token = p_claim_token
     and attempt.recovery_token_hash = p_new_token_hash
     and attempt.recovery_token_expires_at = p_new_token_expires_at
  then
    return true;
  end if;
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
    set state = 'cancelled', claim_token = null, lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = p_provider_email_hash
      and environment = p_environment;
    return false;
  end if;

  -- Preparation never rotates the user token. Both crash and terminal-event
  -- races therefore preserve the original delivered link.
  update private.verification_email_recovery_attempts
  set state = 'prepared', attempt_count = 1,
      recovery_token_hash = p_new_token_hash,
      recovery_token_expires_at = p_new_token_expires_at,
      lease_expires_at = pg_catalog.clock_timestamp() + interval '2 minutes',
      updated_at = pg_catalog.clock_timestamp()
  where provider_email_hash = p_provider_email_hash
    and environment = p_environment;
  return true;
end;
$function$;

create function public.authorize_verification_email_recovery_dispatch(
  p_provider_email_hash text,
  p_claim_token uuid,
  p_environment text,
  p_previous_token_hash text,
  p_previous_token_expires_at timestamptz,
  p_recovery_token_hash text
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
     or coalesce(p_environment, '') not in (
       'production', 'preview', 'development', 'test'
     )
     or coalesce(p_previous_token_hash, '') !~ '^[0-9a-f]{64}$'
     or p_previous_token_expires_at is null
     or coalesce(p_recovery_token_hash, '') !~ '^[0-9a-f]{64}$'
  then
    raise exception 'Invalid recovery dispatch authorization.'
      using errcode = '22023';
  end if;

  select attempts.* into attempt
  from private.verification_email_recovery_attempts as attempts
  where attempts.provider_email_hash = p_provider_email_hash
    and attempts.environment = p_environment
  for update;
  if found
     and attempt.state = 'dispatch_authorized'
     and attempt.claim_token = p_claim_token
     and attempt.recovery_token_hash = p_recovery_token_hash
  then
    return true;
  end if;
  if not found
     or attempt.state <> 'prepared'
     or attempt.attempt_count <> 1
     or attempt.claim_token <> p_claim_token
     or attempt.lease_expires_at <= pg_catalog.clock_timestamp()
     or attempt.recovery_token_hash <> p_recovery_token_hash
     or attempt.outcome_class in (
       'delivered', 'permanent', 'failed', 'suppressed', 'complaint'
     )
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
    set state = 'cancelled', claim_token = null, lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = p_provider_email_hash
      and environment = p_environment;
    return false;
  end if;

  -- This commit is the linearization point immediately before external I/O.
  update private.verification_email_recovery_attempts
  set state = 'dispatch_authorized',
      dispatch_authorized_at = pg_catalog.clock_timestamp(),
      lease_expires_at = pg_catalog.clock_timestamp() + interval '2 minutes',
      updated_at = pg_catalog.clock_timestamp()
  where provider_email_hash = p_provider_email_hash
    and environment = p_environment;
  return true;
end;
$function$;

drop function public.complete_verification_email_recovery(
  text, uuid, text, timestamptz
);
create function public.complete_verification_email_recovery(
  p_provider_email_hash text,
  p_claim_token uuid,
  p_retry_provider_email_hash text,
  p_environment text,
  p_recovery_token_hash text,
  p_recovery_token_expires_at timestamptz
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
     or coalesce(p_environment, '') not in (
       'production', 'preview', 'development', 'test'
     )
     or coalesce(p_recovery_token_hash, '') !~ '^[0-9a-f]{64}$'
     or p_recovery_token_expires_at is null
  then
    raise exception 'Invalid recovery completion.' using errcode = '22023';
  end if;

  select attempts.* into attempt
  from private.verification_email_recovery_attempts as attempts
  where attempts.provider_email_hash = p_provider_email_hash
    and attempts.environment = p_environment
  for update;
  if found
     and attempt.state in ('retry_sent', 'delivered', 'terminal')
     and attempt.retry_provider_email_hash = p_retry_provider_email_hash
     and attempt.recovery_token_hash = p_recovery_token_hash
     and attempt.recovery_token_expires_at = p_recovery_token_expires_at
  then
    return true;
  end if;
  if not found
     or attempt.state <> 'dispatch_authorized'
     or attempt.attempt_count <> 1
     or attempt.claim_token <> p_claim_token
     or attempt.lease_expires_at <= pg_catalog.clock_timestamp()
     or attempt.recovery_token_hash <> p_recovery_token_hash
     or attempt.recovery_token_expires_at <> p_recovery_token_expires_at
  then
    return false;
  end if;

  if exists (
    select 1 from private.verification_email_recovery_attempts as other_attempts
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
      claim_token = null, lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where provider_email_hash = p_provider_email_hash
    and environment = p_environment;
  return true;
end;
$function$;

drop function public.fail_verification_email_recovery(
  text, uuid, text, text, timestamptz
);
create function public.fail_verification_email_recovery(
  p_provider_email_hash text,
  p_claim_token uuid,
  p_environment text,
  p_recovery_token_hash text
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
     or coalesce(p_environment, '') not in (
       'production', 'preview', 'development', 'test'
     )
     or coalesce(p_recovery_token_hash, '') !~ '^[0-9a-f]{64}$'
  then
    raise exception 'Invalid recovery send failure.' using errcode = '22023';
  end if;

  select attempts.* into attempt
  from private.verification_email_recovery_attempts as attempts
  where attempts.provider_email_hash = p_provider_email_hash
    and attempts.environment = p_environment
  for update;
  if found
     and attempt.state = 'send_failed'
     and attempt.recovery_token_hash = p_recovery_token_hash
  then
    return true;
  end if;
  if not found
     or attempt.state <> 'dispatch_authorized'
     or attempt.attempt_count <> 1
     or attempt.claim_token <> p_claim_token
     or attempt.recovery_token_hash <> p_recovery_token_hash
  then
    return false;
  end if;

  -- The user token never changed before I/O; failure closes only this attempt.
  update private.verification_email_recovery_attempts
  set state = 'send_failed', claim_token = null, lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where provider_email_hash = p_provider_email_hash
    and environment = p_environment;
  return true;
end;
$function$;

create function public.consume_verification_email_recovery_token(
  p_recovery_token_hash text,
  p_environment text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $function$
declare
  attempt private.verification_email_recovery_attempts%rowtype;
  candidate_user public.users%rowtype;
  handoff_expires_at timestamptz;
begin
  if coalesce(p_recovery_token_hash, '') !~ '^[0-9a-f]{64}$'
     or coalesce(p_environment, '') not in (
       'production', 'preview', 'development', 'test'
     )
  then
    raise exception 'Invalid recovery verification token scope.'
      using errcode = '22023';
  end if;

  select attempts.* into attempt
  from private.verification_email_recovery_attempts as attempts
  where attempts.environment = p_environment
    and attempts.recovery_token_hash = p_recovery_token_hash
    and attempts.recovery_token_expires_at > pg_catalog.clock_timestamp()
    and attempts.dispatch_authorized_at is not null
    and attempts.state in (
      'dispatch_authorized', 'retry_sent', 'delivered', 'terminal',
      'exhausted', 'send_failed', 'verified'
    )
  for update;
  if not found then
    return null;
  end if;

  select users.* into candidate_user
  from public.users as users
  where users.id = attempt.user_id
  for update;
  if not found then
    return null;
  end if;
  if candidate_user.is_verified then
    if candidate_user.verification_token_expires is null
       or candidate_user.verification_token_expires <= pg_catalog.clock_timestamp()
    then
      return null;
    end if;
    handoff_expires_at := least(
      attempt.recovery_token_expires_at,
      candidate_user.verification_token_expires
    );
    update private.verification_email_recovery_attempts
    set state = 'verified',
        recovery_token_expires_at = handoff_expires_at,
        claim_token = null,
        lease_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where provider_email_hash = attempt.provider_email_hash
      and environment = p_environment;
    return attempt.user_id;
  end if;

  handoff_expires_at := least(
    attempt.recovery_token_expires_at,
    pg_catalog.clock_timestamp() + interval '15 minutes'
  );

  update public.users
  set is_verified = true,
      -- Preserve the original digest so both delivered links work regardless
      -- of which one verifies first.
      verification_token_expires = handoff_expires_at,
      updated_at = pg_catalog.clock_timestamp()
  where id = attempt.user_id;
  update private.verification_email_recovery_attempts
  set state = 'verified',
      recovery_token_expires_at = handoff_expires_at,
      claim_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where provider_email_hash = attempt.provider_email_hash
    and environment = p_environment;
  return attempt.user_id;
end;
$function$;

revoke all on function private.verification_recovery_outcome_rank(text)
  from public, anon, authenticated, service_role;
revoke all on function public.register_verification_email_recovery_attempt(
  text, uuid, text, timestamptz
) from public, anon, authenticated, service_role;
revoke all on function public.record_resend_delivery_event_and_recovery(
  text, text, text, text, text, text, text, timestamptz
) from public, anon, authenticated, service_role;
revoke all on function public.claim_verification_email_recovery(uuid, text)
  from public, anon, authenticated, service_role;
revoke all on function public.prepare_verification_email_recovery(
  text, uuid, text, timestamptz, text, timestamptz, text
) from public, anon, authenticated, service_role;
revoke all on function public.authorize_verification_email_recovery_dispatch(
  text, uuid, text, text, timestamptz, text
) from public, anon, authenticated, service_role;
revoke all on function public.complete_verification_email_recovery(
  text, uuid, text, text, text, timestamptz
) from public, anon, authenticated, service_role;
revoke all on function public.fail_verification_email_recovery(
  text, uuid, text, text
) from public, anon, authenticated, service_role;
revoke all on function public.consume_verification_email_recovery_token(
  text, text
) from public, anon, authenticated, service_role;

grant execute on function public.register_verification_email_recovery_attempt(
  text, uuid, text, timestamptz
) to service_role;
grant execute on function public.record_resend_delivery_event_and_recovery(
  text, text, text, text, text, text, text, timestamptz
) to service_role;
grant execute on function public.claim_verification_email_recovery(uuid, text)
  to service_role;
grant execute on function public.prepare_verification_email_recovery(
  text, uuid, text, timestamptz, text, timestamptz, text
) to service_role;
grant execute on function public.authorize_verification_email_recovery_dispatch(
  text, uuid, text, text, timestamptz, text
) to service_role;
grant execute on function public.complete_verification_email_recovery(
  text, uuid, text, text, text, timestamptz
) to service_role;
grant execute on function public.fail_verification_email_recovery(
  text, uuid, text, text
) to service_role;
grant execute on function public.consume_verification_email_recovery_token(
  text, text
) to service_role;

comment on function public.prepare_verification_email_recovery(
  text, uuid, text, timestamptz, text, timestamptz, text
) is 'Replay-safe preparation stores a one-way recovery digest without invalidating the original token.';
comment on function public.authorize_verification_email_recovery_dispatch(
  text, uuid, text, text, timestamptz, text
) is 'Dispatch linearization: terminal/delivered/verified commits before it win; after it external HTTP wins.';
comment on function public.consume_verification_email_recovery_token(text, text)
  is 'Atomically consumes an authorized recovery digest after ambiguous provider or completion boundaries.';

commit;
