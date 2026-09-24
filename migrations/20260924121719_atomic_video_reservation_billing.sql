-- Crash-safe Ask Crump video billing and provider-launch state machine.
--
-- The browser never calls these functions. The authenticated Python backend
-- uses the service role after it has validated ownership, the request shape,
-- the signed credit quote, and the request fingerprint. Keeping quota/credit
-- consumption and receipt binding in one transaction closes the gap where a
-- process could charge a customer and lose the durable media-job receipt.

begin;

alter table public.media_jobs
  add column if not exists request_fingerprint text,
  add column if not exists video_phase text not null default 'legacy',
  add column if not exists lease_token uuid,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists finalization_started_at timestamptz,
  add column if not exists provider_started_at timestamptz,
  add column if not exists sweep_retry_after timestamptz not null
    default '-infinity'::timestamptz;

alter table public.media_jobs
  drop constraint if exists media_jobs_request_fingerprint_check,
  add constraint media_jobs_request_fingerprint_check
    check (
      request_fingerprint is null
      or request_fingerprint ~ '^[0-9a-f]{64}$'
    ),
  drop constraint if exists media_jobs_video_phase_check,
  add constraint media_jobs_video_phase_check
    check (
      video_phase in (
        'legacy',
        'reserved_unbilled',
        'ready_to_launch',
        'launching',
        'processing',
        'finalizing',
        'ready',
        'failed'
      )
    );

create index if not exists media_jobs_video_phase_lease_idx
  on public.media_jobs(user_id, video_phase, lease_expires_at)
  where status in ('queued', 'processing');

create index if not exists media_jobs_video_lease_sweep_idx
  on public.media_jobs(lease_expires_at, id)
  where kind = 'video'
    and lease_expires_at is not null
    and video_phase in (
      'reserved_unbilled', 'ready_to_launch', 'launching', 'finalizing'
    );

create index if not exists media_jobs_video_stale_processing_idx
  on public.media_jobs(updated_at, id)
  include (user_id)
  where kind = 'video'
    and status = 'processing'
    and video_phase = 'processing';

create index if not exists media_jobs_video_processing_deadline_idx
  on public.media_jobs(provider_started_at, sweep_retry_after, id)
  include (user_id)
  where kind = 'video'
    and status = 'processing'
    and video_phase = 'processing';

create index if not exists media_jobs_video_finalization_deadline_idx
  on public.media_jobs(finalization_started_at, lease_expires_at, id)
  include (user_id)
  where kind = 'video'
    and status = 'processing'
    and video_phase = 'finalizing';

create index if not exists media_jobs_video_compat_refund_sweep_idx
  on public.media_jobs(sweep_retry_after, updated_at, id)
  include (user_id)
  where kind = 'video'
    and status = 'failed'
    and video_phase = 'failed'
    and not billing_refunded
    and billing_receipt <> '{}'::jsonb
    and coalesce(metadata ->> 'compatibilityOrigin', '') = 'pre-atomic';

create index if not exists media_jobs_video_global_daily_budget_idx
  on public.media_jobs(created_at)
  include (estimated_provider_cost_cents, video_phase, lease_expires_at)
  where kind = 'video';

create index if not exists media_jobs_video_user_daily_budget_idx
  on public.media_jobs(user_id, created_at)
  include (estimated_provider_cost_cents, video_phase, lease_expires_at)
  where kind = 'video';

create index if not exists media_jobs_video_runway_monthly_budget_idx
  on public.media_jobs(created_at)
  include (estimated_provider_cost_cents, video_phase, lease_expires_at)
  where kind = 'video' and provider = 'runway';

-- Rolling-deploy compatibility for a pre-atomic application instance.
--
-- The previous application version charged before inserting its durable video
-- row and did not know about video_phase, lease_token, or
-- request_fingerprint. PostgreSQL applies column defaults before a BEFORE
-- trigger, so video_phase = 'legacy' is the narrow, server-authoritative signal
-- that an old instance wrote the row. Compatibility rows are fenced with an
-- identity derived only from their database UUID; prompts, file names,
-- reference URLs, and every other customer-content field are deliberately
-- excluded from the fingerprint.
--
-- Reconciliation can happen on the next create/status request or through the
-- bounded service-role lease sweeper defined later in this migration. An
-- unconfirmed billed pre-atomic launch gets a 15-minute grace window (well
-- beyond the old provider HTTP timeout and normal deployment propagation),
-- after which either path refunds the customer and makes the row terminal
-- without relaunching the provider. Unbilled placeholders expire after five
-- minutes and are deleted without consuming allowance or credits.
create or replace function public.normalize_pre_atomic_video_job()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  is_compatibility_row boolean;
  is_rolling_deploy_insert boolean := false;
  is_explicit_phase_transition boolean := false;
  is_fenced_finalization_operation boolean := false;
  is_finalization_terminal_transition boolean := false;
  is_finalization_lease_operation boolean := false;
  has_pending_provider_id boolean;
  requested_sweep_retry_after timestamptz;
  compatibility_key text;
  compatibility_key_attempts integer := 0;
  legacy_ack_payment_source text;
  legacy_ack_event_id text;
  legacy_ack_valid boolean := false;
  is_migration_classifier boolean := false;
begin
  if new.kind <> 'video' then
    return new;
  end if;

  -- Serialize every compatibility write that can change an owner's billable
  -- video state with the in-transaction entitlement decision. The previous
  -- application cannot acquire this lock before its row write, so owner
  -- settlement uses SKIP LOCKED plus a remaining-row check and fails closed
  -- until that writer commits. Modern billing takes the same owner lock
  -- before consuming allowance or credits.
  is_migration_classifier := tg_op = 'UPDATE'
    and old.video_phase = 'legacy'
    and new.video_phase = 'legacy'
    and new is not distinct from old;
  if not is_migration_classifier
     and (
       new.video_phase = 'legacy'
       or coalesce(new.metadata ->> 'compatibilityOrigin', '') = 'pre-atomic'
       or (
         tg_op = 'UPDATE'
         and coalesce(old.metadata ->> 'compatibilityOrigin', '') = 'pre-atomic'
       )
     )
  then
    perform pg_advisory_xact_lock(
      hashtextextended(
        'askcrump-video-owner-billing-v1:' || new.user_id::text,
        0
      )
    );
  end if;

  -- The provider-processing horizon is database-owned and monotonic. A stale
  -- old application PATCH may omit or replace newer columns, but it must
  -- never move an already-established provider start time.
  if tg_op = 'UPDATE' and old.provider_started_at is not null then
    new.provider_started_at := old.provider_started_at;
  end if;

  -- A pre-release backend PATCH does not know the atomic columns. Once any
  -- row is finalizing, reject every update that leaves the phase/token fence
  -- untouched (including stale processing, ready, failed, or metadata-only
  -- writes). Modern RPC terminal transitions clear the exact lease fence;
  -- modern reclaims/quarantine updates change its token or expiry. Preserve
  -- the immutable outcome/refund/deadline metadata during same-phase lease
  -- operations so an old metadata replacement cannot erase settlement truth.
  if tg_op = 'UPDATE' and old.video_phase = 'finalizing' then
    is_finalization_terminal_transition :=
      old.lease_token is not null
      and new.video_phase in ('ready', 'failed')
      and new.status = new.video_phase
      and new.lease_token is null
      and new.lease_expires_at is null
      and new.finalization_started_at is null;
    is_finalization_lease_operation :=
      old.lease_token is not null
      and new.video_phase = 'finalizing'
      and new.status = 'processing'
      and new.lease_token is not null
      and new.lease_expires_at is not null
      and new.finalization_started_at is not distinct from
        old.finalization_started_at
      and (
        new.lease_token is distinct from old.lease_token
        or new.lease_expires_at is distinct from old.lease_expires_at
        or new.sweep_retry_after is distinct from old.sweep_retry_after
      );
    is_fenced_finalization_operation :=
      is_finalization_terminal_transition
      or is_finalization_lease_operation;
    if not is_fenced_finalization_operation then
      return old;
    end if;
    if is_finalization_lease_operation then
      new.metadata := (
        coalesce(new.metadata, '{}'::jsonb)
        - 'finalizationOutcome'
        - 'finalizationRefundEligible'
        - 'finalizationStartedAt'
        - 'finalizationExpiresAt'
      ) || jsonb_build_object(
        'finalizationOutcome', old.metadata -> 'finalizationOutcome',
        'finalizationRefundEligible',
          old.metadata -> 'finalizationRefundEligible',
        'finalizationStartedAt', old.metadata -> 'finalizationStartedAt',
        'finalizationExpiresAt', old.metadata -> 'finalizationExpiresAt'
      );
    end if;
  end if;

  -- Old application updates can replace metadata wholesale. Recover the
  -- database-owned compatibility identity from OLD before deciding whether
  -- this row belongs to the rolling-deploy state machine.
  if tg_op = 'UPDATE'
     and coalesce(old.metadata ->> 'compatibilityOrigin', '') = 'pre-atomic'
  then
    new.idempotency_key := old.idempotency_key;
    new.request_fingerprint := old.request_fingerprint;
    new.metadata := coalesce(new.metadata, '{}'::jsonb)
      || jsonb_build_object(
        'compatibilityOrigin', 'pre-atomic',
        'compatibilityRequestIdentity', 'database-row-uuid-v1'
      );
  end if;

  -- A delayed response from any old application instance must never regress
  -- or rewrite an atomic terminal row. The previous release updates by
  -- id/user only, including metadata-only progress and terminal writes, so
  -- compare authoritative OLD state rather than trusting NEW fields. Preserve
  -- at most the exact failed-row refund acknowledgement after an external
  -- refund has already completed.
  if tg_op = 'UPDATE' then
    if old.video_phase in ('ready', 'failed')
       and old.status = old.video_phase
    then
      if old.video_phase = 'failed'
         and not old.billing_refunded
         and new.billing_refunded
      then
        legacy_ack_payment_source := lower(trim(coalesce(
          old.billing_receipt ->> 'paymentSource',
          ''
        )));
        legacy_ack_event_id := nullif(trim(coalesce(
          old.billing_receipt ->> 'eventId',
          ''
        )), '');
        legacy_ack_valid :=
          coalesce(old.metadata ->> 'compatibilityOrigin', '') = 'pre-atomic'
          and (
            (
              legacy_ack_payment_source = 'credits'
              and legacy_ack_event_id ~* (
                '^credit:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
                || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
              )
            )
            or (
              legacy_ack_payment_source = 'included'
              and legacy_ack_event_id ~* (
                '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
                || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
              )
            )
            or (
              legacy_ack_payment_source in ('internal', 'subscription')
              and legacy_ack_event_id is null
            )
          );
        if legacy_ack_valid then
          new := old;
          new.billing_refunded := true;
          new.updated_at := now();
          return new;
        end if;

        -- A legacy route may report success after a no-op refund attempt. Do
        -- not turn malformed receipt data into a permanent acknowledgement.
        -- Preserve the unpaid state and surface it through the same bounded
        -- review/quarantine channel as the atomic sweep.
        new := old;
        new.sweep_retry_after := greatest(
          old.sweep_retry_after,
          now() + interval '24 hours'
        );
        new.metadata := old.metadata || jsonb_build_object(
          'sweepNeedsReview', true,
          'sweepRetryAfter', to_jsonb(new.sweep_retry_after),
          'sweepReviewReason', 'invalid-legacy-refund-ack'
        );
        new.updated_at := now();
        return new;
      end if;
      if old.video_phase = 'failed'
         and not old.billing_refunded
         and coalesce(old.metadata ->> 'compatibilityOrigin', '') = 'pre-atomic'
         and new.video_phase = 'failed'
         and new.status = 'failed'
         and new.sweep_retry_after is distinct from old.sweep_retry_after
      then
        requested_sweep_retry_after := new.sweep_retry_after;
        new := old;
        new.sweep_retry_after := greatest(
          old.sweep_retry_after,
          requested_sweep_retry_after
        );
        new.metadata := old.metadata || jsonb_build_object(
          'sweepNeedsReview', true,
          'sweepRetryAfter', to_jsonb(new.sweep_retry_after)
        );
        new.updated_at := now();
        return new;
      end if;
      return old;
    end if;
  end if;

  is_compatibility_row := new.video_phase = 'legacy'
    or coalesce(new.metadata ->> 'compatibilityOrigin', '') = 'pre-atomic'
    or (
      tg_op = 'UPDATE'
      and coalesce(old.metadata ->> 'compatibilityOrigin', '') = 'pre-atomic'
    );
  if not is_compatibility_row then
    return new;
  end if;

  -- These untouched defaults are the narrow signal that a still-running old
  -- application inserted the row after this migration landed. This lets that
  -- instance replay its original 121-160 character key without widening the
  -- modern public request boundary.
  is_rolling_deploy_insert := tg_op = 'INSERT'
    and new.video_phase = 'legacy'
    and new.request_fingerprint is null
    and new.lease_token is null
    and new.lease_expires_at is null
    and coalesce(new.metadata ->> 'compatibilityOrigin', '') = '';

  if new.id is null then
    raise exception 'A pre-atomic video job requires an id'
      using errcode = '23502';
  end if;

  -- Preserve the original identity on compatibility-row updates. Backfilled
  -- rows and narrowly identified rolling-deploy inserts retain a nonblank key
  -- through 160 characters; other compatibility inserts above the modern
  -- public 120-character boundary receive a database-owned identity instead.
  if tg_op = 'UPDATE'
     and new.idempotency_key is distinct from old.idempotency_key
  then
    new.idempotency_key := old.idempotency_key;
  end if;
  if trim(coalesce(new.idempotency_key, '')) = ''
     or length(trim(new.idempotency_key)) > 160
     or (
       tg_op = 'INSERT'
       and length(trim(new.idempotency_key)) > 120
       and not is_rolling_deploy_insert
     )
  then
    -- Do not derive the fallback from a public row UUID: an older caller
    -- could have pre-seeded that predictable value on another row and made
    -- the unique (user_id, idempotency_key) backfill fail transactionally.
    loop
      compatibility_key_attempts := compatibility_key_attempts + 1;
      compatibility_key := 'pre-atomic-video:' || gen_random_uuid()::text;
      exit when not exists (
        select 1
        from public.media_jobs as candidate
        where candidate.user_id = new.user_id
          and candidate.id <> new.id
          and candidate.idempotency_key = compatibility_key
      );
      if compatibility_key_attempts >= 8 then
        raise exception 'Could not allocate a compatibility request identity'
          using errcode = '23505';
      end if;
    end loop;
    new.idempotency_key := compatibility_key;
  end if;
  new.request_fingerprint :=
    md5('askcrump-pre-atomic-a:' || new.id::text)
    || md5('askcrump-pre-atomic-b:' || new.id::text);
  new.metadata := coalesce(new.metadata, '{}'::jsonb)
    || jsonb_build_object(
      'compatibilityOrigin', 'pre-atomic',
      'compatibilityRequestIdentity', 'database-row-uuid-v1'
    );

  if tg_op = 'UPDATE' then
    is_explicit_phase_transition :=
      is_fenced_finalization_operation
      or (
        new.video_phase is distinct from old.video_phase
        and new.video_phase <> 'legacy'
      );
  end if;

  -- Modern RPCs may settle an already-tagged compatibility row. Preserve
  -- their explicit fenced transition instead of replacing their lease token.
  if is_explicit_phase_transition then
    new.metadata := new.metadata
      || jsonb_build_object('videoPhase', new.video_phase);
    return new;
  end if;

  has_pending_provider_id := trim(coalesce(new.provider_job_id, '')) = ''
    or lower(trim(new.provider_job_id)) like 'pending:%';

  if new.status = 'ready' then
    new.video_phase := 'ready';
    new.lease_token := null;
    new.lease_expires_at := null;
  elsif new.status = 'failed' then
    new.video_phase := 'failed';
    new.lease_token := null;
    new.lease_expires_at := null;
  elsif not has_pending_provider_id
        and new.status in ('queued', 'processing') then
    -- The old provider call returned before its grace lease was reconciled.
    new.status := 'processing';
    new.video_phase := 'processing';
    new.lease_token := null;
    new.lease_expires_at := null;
    if new.provider_started_at is null then
      if tg_op = 'UPDATE' and old.video_phase = 'legacy' then
        -- Migration backfill uses the original database-owned creation time,
        -- not a recent progress poll that could extend an ancient job.
        new.provider_started_at := coalesce(new.created_at, now());
      else
        -- A live old instance has just bound the provider task after launch.
        new.provider_started_at := now();
      end if;
    end if;
  elsif new.billing_receipt <> '{}'::jsonb then
    -- Billing already happened in the old process. Treat the provider launch
    -- as acceptance-unknown and never issue a second provider request.
    new.status := 'queued';
    new.video_phase := 'launching';
    new.lease_token := coalesce(new.lease_token, gen_random_uuid());
    new.lease_expires_at := coalesce(
      new.lease_expires_at,
      now() + interval '15 minutes'
    );
  else
    new.status := 'queued';
    new.video_phase := 'reserved_unbilled';
    new.lease_token := coalesce(new.lease_token, gen_random_uuid());
    new.lease_expires_at := coalesce(
      new.lease_expires_at,
      now() + interval '5 minutes'
    );
  end if;

  new.metadata := (
      new.metadata
      - 'reservationToken'
      - 'reservationExpiresAt'
      - 'launchToken'
      - 'launchExpiresAt'
      - 'launchReadyExpiresAt'
    )
    || jsonb_build_object(
      'videoPhase', new.video_phase,
      'compatibilityOrigin', 'pre-atomic'
    );
  return new;
end;
$$;

revoke all on function public.normalize_pre_atomic_video_job()
  from public, anon, authenticated;
grant execute on function public.normalize_pre_atomic_video_job()
  to service_role;

drop trigger if exists media_jobs_pre_atomic_video_compatibility
  on public.media_jobs;
create trigger media_jobs_pre_atomic_video_compatibility
before insert or update on public.media_jobs
for each row execute function public.normalize_pre_atomic_video_job();

-- Run every existing video row through the same compatibility classifier.
-- The later no-legacy constraint makes an incomplete backfill fail closed.
update public.media_jobs
set video_phase = video_phase
where kind = 'video' and video_phase = 'legacy';

alter table public.media_jobs
  drop constraint if exists media_jobs_video_no_legacy_check,
  add constraint media_jobs_video_no_legacy_check
    check (kind <> 'video' or video_phase <> 'legacy'),
  drop constraint if exists media_jobs_video_request_identity_check,
  add constraint media_jobs_video_request_identity_check
    check (
      kind <> 'video'
      or (
        request_fingerprint is not null
        and request_fingerprint ~ '^[0-9a-f]{64}$'
        and idempotency_key is not null
        and trim(idempotency_key) <> ''
        and (
          length(trim(idempotency_key)) <= 120
          or (
            length(trim(idempotency_key)) <= 160
            and coalesce(metadata ->> 'compatibilityOrigin', '') = 'pre-atomic'
            and coalesce(
              metadata ->> 'compatibilityRequestIdentity', ''
            ) = 'database-row-uuid-v1'
            and request_fingerprint = (
              md5('askcrump-pre-atomic-a:' || id::text)
              || md5('askcrump-pre-atomic-b:' || id::text)
            )
          )
        )
      )
    ),
  drop constraint if exists media_jobs_video_phase_consistency_check,
  add constraint media_jobs_video_phase_consistency_check
    check (
      kind <> 'video'
      or (
        (
          video_phase = 'reserved_unbilled'
          and status = 'queued'
          and provider_job_id like 'pending:%'
          and billing_receipt = '{}'::jsonb
          and lease_token is not null
          and lease_expires_at is not null
        )
        or (
          video_phase = 'ready_to_launch'
          and status = 'queued'
          and provider_job_id like 'pending:%'
          and billing_receipt <> '{}'::jsonb
          and lease_token is null
          and lease_expires_at is not null
        )
        or (
          video_phase = 'launching'
          and status = 'queued'
          and provider_job_id like 'pending:%'
          and billing_receipt <> '{}'::jsonb
          and lease_token is not null
          and lease_expires_at is not null
        )
        or (
          video_phase = 'processing'
          and status = 'processing'
          and provider_job_id is not null
          and trim(provider_job_id) <> ''
          and provider_job_id not like 'pending:%'
          and lease_token is null
          and lease_expires_at is null
          and provider_started_at is not null
        )
        or (
          video_phase = 'finalizing'
          and status = 'processing'
          and provider_job_id is not null
          and trim(provider_job_id) <> ''
          and provider_job_id not like 'pending:%'
          and billing_receipt <> '{}'::jsonb
          and lease_token is not null
          and lease_expires_at is not null
          and finalization_started_at is not null
          and provider_started_at is not null
        )
        or (
          video_phase = 'ready'
          and status = 'ready'
          and lease_token is null
          and lease_expires_at is null
        )
        or (
          video_phase = 'failed'
          and status = 'failed'
          and lease_token is null
          and lease_expires_at is null
        )
      )
    );

comment on function public.normalize_pre_atomic_video_job() is
  'Invoker compatibility fence for old-app video rows; UUID-only identity, no provider relaunch, and terminal non-resurrection.';
comment on constraint media_jobs_video_no_legacy_check
  on public.media_jobs is
  'All video rows must be classified into the atomic billing and launch state machine.';
comment on constraint media_jobs_video_request_identity_check
  on public.media_jobs is
  'Every video row requires a bounded idempotency key and immutable lowercase 64-hex request identity.';
comment on constraint media_jobs_video_phase_consistency_check
  on public.media_jobs is
  'Keeps authoritative video phases, provider identity, billing receipt, and lease fields mutually consistent.';

create or replace function public.authorize_video_reservation_capacity(
  p_user_id uuid,
  p_job_id uuid,
  p_idempotency_key text,
  p_request_fingerprint text,
  p_reservation_token text,
  p_max_active_jobs integer,
  p_global_daily_budget_cents integer,
  p_user_daily_budget_cents integer,
  p_runway_monthly_budget_cents integer,
  p_bypass_user_budget boolean default false
)
returns table(
  outcome text,
  job jsonb,
  active_jobs integer,
  global_estimate_cents bigint,
  user_estimate_cents bigint,
  runway_estimate_cents bigint
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  updated_row public.media_jobs%rowtype;
  normalized_key text := trim(coalesce(p_idempotency_key, ''));
  normalized_fingerprint text := lower(trim(coalesce(p_request_fingerprint, '')));
  reservation_token uuid;
  decision text := 'authorized';
  active_total integer := 0;
  global_total bigint := 0;
  user_total bigint := 0;
  runway_total bigint := 0;
  day_start timestamptz := (
    date_trunc('day', now() at time zone 'UTC') at time zone 'UTC'
  );
  month_start timestamptz := (
    date_trunc('month', now() at time zone 'UTC') at time zone 'UTC'
  );
begin
  if p_user_id is null or p_job_id is null then
    raise exception 'Video capacity identity is required' using errcode = '22023';
  end if;
  if normalized_key = '' or length(normalized_key) > 160 then
    raise exception 'Video idempotency key is invalid' using errcode = '22023';
  end if;
  if normalized_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'Video request fingerprint is invalid' using errcode = '22023';
  end if;
  begin
    reservation_token := trim(coalesce(p_reservation_token, ''))::uuid;
  exception when invalid_text_representation then
    raise exception 'Video reservation token is invalid' using errcode = '22023';
  end;
  if reservation_token is null then
    raise exception 'Video reservation token is required' using errcode = '22023';
  end if;
  if coalesce(p_max_active_jobs, 0) < 1 or p_max_active_jobs > 3 then
    raise exception 'Video active-job limit is invalid' using errcode = '22023';
  end if;
  if coalesce(p_global_daily_budget_cents, -1) < 0
     or p_global_daily_budget_cents > 1000000000
     or coalesce(p_user_daily_budget_cents, -1) < 0
     or p_user_daily_budget_cents > 1000000000
     or coalesce(p_runway_monthly_budget_cents, -1) < 0
     or p_runway_monthly_budget_cents > 1000000000
  then
    raise exception 'Video provider budget limit is invalid' using errcode = '22023';
  end if;

  -- Every capacity decision uses the same transaction-scoped lock. A request
  -- inserts its unbilled reservation before entering here, so the serialized
  -- count always includes the caller's provider-cost estimate.
  perform pg_advisory_xact_lock(
    hashtextextended('askcrump-video-capacity-v1', 0)
  );

  select * into job_row
  from public.media_jobs as current_job
  where current_job.id = p_job_id
    and current_job.user_id = p_user_id
  for update;
  if not found then
    return query select 'reservation_missing'::text, '{}'::jsonb,
      0, 0::bigint, 0::bigint, 0::bigint;
    return;
  end if;

  if job_row.idempotency_key is distinct from normalized_key
     or job_row.request_fingerprint is distinct from normalized_fingerprint then
    return query select 'request_conflict'::text, to_jsonb(job_row),
      0, 0::bigint, 0::bigint, 0::bigint;
    return;
  end if;

  if coalesce(job_row.metadata ->> 'capacityAuthorized', 'false') = 'true'
     and job_row.video_phase in (
       'reserved_unbilled', 'ready_to_launch', 'launching', 'processing',
       'finalizing', 'ready', 'failed'
     ) then
    return query select 'existing'::text, to_jsonb(job_row),
      0, 0::bigint, 0::bigint, 0::bigint;
    return;
  end if;

  if job_row.status <> 'queued'
     or job_row.provider_job_id not like 'pending:%'
     or job_row.video_phase <> 'reserved_unbilled'
     or job_row.lease_token is distinct from reservation_token
     or job_row.billing_receipt <> '{}'::jsonb
     or job_row.lease_expires_at is null
     or job_row.lease_expires_at <= now()
  then
    return query select 'reservation_conflict'::text, to_jsonb(job_row),
      0, 0::bigint, 0::bigint, 0::bigint;
    return;
  end if;

  select count(*)::integer into active_total
  from public.media_jobs as candidate
  where candidate.user_id = p_user_id
    and candidate.kind = 'video'
    and (
      (
        candidate.video_phase = 'processing'
        and candidate.provider_started_at > now() - interval '24 hours'
      )
      or (
        candidate.video_phase = 'finalizing'
        and candidate.finalization_started_at > now() - interval '1 hour'
      )
      or (
        candidate.video_phase in (
          'reserved_unbilled', 'ready_to_launch', 'launching'
        )
        and candidate.lease_expires_at > now()
      )
    );

  select coalesce(sum(candidate.estimated_provider_cost_cents), 0)::bigint
  into global_total
  from public.media_jobs as candidate
  where candidate.kind = 'video'
    and candidate.created_at >= day_start
    and not (
      candidate.video_phase = 'reserved_unbilled'
      and candidate.lease_expires_at <= now()
    );

  select coalesce(sum(candidate.estimated_provider_cost_cents), 0)::bigint
  into user_total
  from public.media_jobs as candidate
  where candidate.kind = 'video'
    and candidate.user_id = p_user_id
    and candidate.created_at >= day_start
    and not (
      candidate.video_phase = 'reserved_unbilled'
      and candidate.lease_expires_at <= now()
    );

  select coalesce(sum(candidate.estimated_provider_cost_cents), 0)::bigint
  into runway_total
  from public.media_jobs as candidate
  where candidate.kind = 'video'
    and candidate.provider = 'runway'
    and candidate.created_at >= month_start
    and not (
      candidate.video_phase = 'reserved_unbilled'
      and candidate.lease_expires_at <= now()
    );

  if active_total > p_max_active_jobs then
    decision := 'concurrency_limit';
  elsif p_global_daily_budget_cents > 0
        and global_total > p_global_daily_budget_cents then
    decision := 'global_budget';
  elsif not coalesce(p_bypass_user_budget, false)
        and p_user_daily_budget_cents > 0
        and user_total > p_user_daily_budget_cents then
    decision := 'user_budget';
  elsif job_row.provider = 'runway'
        and p_runway_monthly_budget_cents > 0
        and runway_total > p_runway_monthly_budget_cents then
    decision := 'runway_budget';
  end if;

  if decision <> 'authorized' then
    -- A denial releases only the exact caller-owned, still-unbilled fence.
    delete from public.media_jobs as current_job
    where current_job.id = p_job_id
      and current_job.user_id = p_user_id
      and current_job.idempotency_key = normalized_key
      and current_job.request_fingerprint = normalized_fingerprint
      and current_job.video_phase = 'reserved_unbilled'
      and current_job.lease_token = reservation_token
      and current_job.billing_receipt = '{}'::jsonb;
    if not found then
      raise exception 'Video reservation changed during capacity denial'
        using errcode = '40001';
    end if;
    return query select decision, to_jsonb(job_row), active_total,
      global_total, user_total, runway_total;
    return;
  end if;

  update public.media_jobs as current_job
  set metadata = current_job.metadata || jsonb_build_object(
        'capacityAuthorized', true,
        'capacityAuthorizedAt', to_jsonb(now()),
        'capacityPolicy', 'serialized-v1'
      ),
      updated_at = now()
  where current_job.id = p_job_id
    and current_job.user_id = p_user_id
    and current_job.idempotency_key = normalized_key
    and current_job.request_fingerprint = normalized_fingerprint
    and current_job.video_phase = 'reserved_unbilled'
    and current_job.lease_token = reservation_token
    and current_job.billing_receipt = '{}'::jsonb
  returning * into updated_row;
  if updated_row.id is null then
    raise exception 'Video reservation changed during capacity authorization'
      using errcode = '40001';
  end if;

  return query select 'authorized'::text, to_jsonb(updated_row), active_total,
    global_total, user_total, runway_total;
end;
$$;

create or replace function public.consume_video_reservation(
  p_user_id uuid,
  p_job_id uuid,
  p_idempotency_key text,
  p_request_fingerprint text,
  p_reservation_token text,
  p_feature text,
  p_payment_source text,
  p_event_type text,
  p_included_limit integer,
  p_credit_cost integer,
  p_credit_reason text,
  p_credit_action_key text,
  p_credit_component text,
  p_confirmed_max integer,
  p_approved_feature_max integer,
  p_metadata jsonb default '{}'::jsonb
)
returns table(
  outcome text,
  receipt jsonb,
  balance bigint,
  used integer,
  duplicate boolean
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  updated_row public.media_jobs%rowtype;
  normalized_key text := trim(coalesce(p_idempotency_key, ''));
  normalized_fingerprint text := lower(trim(coalesce(p_request_fingerprint, '')));
  normalized_source text := lower(trim(coalesce(p_payment_source, '')));
  reservation_token uuid;
  reservation_expires_at timestamptz;
  usage_event_id uuid;
  usage_used integer := 0;
  usage_allowed boolean := false;
  credit_ledger_id uuid;
  credit_balance bigint := 0;
  credit_allowed boolean := false;
  credit_duplicate boolean := false;
  credit_limit_exceeded boolean := false;
  bound_receipt jsonb;
  bound_metadata jsonb;
  settlement_outcome text;
  settlement_scanned integer := 0;
  settlement_errors integer := 0;
begin
  if p_user_id is null or p_job_id is null then
    raise exception 'Video reservation identity is required' using errcode = '22023';
  end if;
  if normalized_key = '' or length(normalized_key) > 160 then
    raise exception 'Video idempotency key is invalid' using errcode = '22023';
  end if;
  if normalized_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'Video request fingerprint is invalid' using errcode = '22023';
  end if;
  begin
    reservation_token := trim(coalesce(p_reservation_token, ''))::uuid;
  exception when invalid_text_representation then
    raise exception 'Video reservation token is invalid' using errcode = '22023';
  end;
  if reservation_token is null then
    raise exception 'Video reservation token is required' using errcode = '22023';
  end if;
  if trim(coalesce(p_feature, '')) = '' then
    raise exception 'Video feature is required' using errcode = '22023';
  end if;
  if normalized_source not in ('internal', 'subscription', 'metered') then
    raise exception 'Video payment source is invalid' using errcode = '22023';
  end if;

  -- This settlement and the entitlement decision share one transaction and
  -- one owner lock. A prior included use cannot become refundable between
  -- this check and consume_usage_event/spend_credits_confirmed.
  select settled.outcome, settled.scanned, settled.errors
  into settlement_outcome, settlement_scanned, settlement_errors
  from public.sweep_expired_video_leases(500, p_user_id, null) as settled;
  if settlement_outcome is distinct from 'completed'
     or coalesce(settlement_errors, 0) > 0
  then
    return query select 'settlement_pending'::text, '{}'::jsonb,
      0::bigint, 0, false;
    return;
  end if;

  if not pg_try_advisory_xact_lock(
    hashtextextended('video-billing:' || p_job_id::text, 0)
  ) then
    return query select 'settlement_pending'::text, '{}'::jsonb,
      0::bigint, 0, false;
    return;
  end if;

  select *
  into job_row
  from public.media_jobs as job
  where job.id = p_job_id
    and job.user_id = p_user_id
  for update skip locked;

  if not found then
    if exists (
      select 1 from public.media_jobs as visible_job
      where visible_job.id = p_job_id and visible_job.user_id = p_user_id
    ) then
      return query select 'settlement_pending'::text, '{}'::jsonb,
        0::bigint, 0, false;
    else
      return query select 'reservation_missing'::text, '{}'::jsonb,
        0::bigint, 0, false;
    end if;
    return;
  end if;

  if job_row.idempotency_key is distinct from normalized_key
     or job_row.request_fingerprint is distinct from normalized_fingerprint then
    return query select 'request_conflict'::text, '{}'::jsonb, 0::bigint, 0, false;
    return;
  end if;

  if job_row.billing_receipt <> '{}'::jsonb
     and job_row.video_phase in (
       'ready_to_launch', 'launching', 'processing', 'finalizing', 'ready',
       'failed'
     ) then
    return query select
      'existing'::text,
      job_row.billing_receipt,
      coalesce((job_row.billing_receipt ->> 'creditBalance')::bigint, 0),
      coalesce((job_row.billing_receipt ->> 'used')::integer, 0),
      true;
    return;
  end if;

  if job_row.status <> 'queued'
     or job_row.provider_job_id not like 'pending:%'
     or job_row.video_phase <> 'reserved_unbilled'
     or job_row.lease_token is distinct from reservation_token
     or coalesce(job_row.metadata ->> 'capacityAuthorized', 'false') <> 'true'
  then
    return query select
      case
        when coalesce(job_row.metadata ->> 'capacityAuthorized', 'false') <> 'true'
          then 'capacity_not_authorized'
        else 'reservation_conflict'
      end,
      '{}'::jsonb, 0::bigint, 0, false;
    return;
  end if;

  reservation_expires_at := job_row.lease_expires_at;

  if reservation_expires_at is null or reservation_expires_at <= now() then
    delete from public.media_jobs as job
    where job.id = p_job_id
      and job.user_id = p_user_id
      and job.idempotency_key = normalized_key
      and job.request_fingerprint = normalized_fingerprint
      and job.video_phase = 'reserved_unbilled'
      and job.lease_token = reservation_token
      and (
        job.lease_expires_at is null
        or job.lease_expires_at <= now()
      );
    return query select 'reservation_expired'::text, '{}'::jsonb, 0::bigint, 0, false;
    return;
  end if;

  select coalesce(account.balance, 0)
  into credit_balance
  from public.credit_accounts as account
  where account.user_id = p_user_id;
  credit_balance := coalesce(credit_balance, 0);

  if normalized_source = 'internal' then
    bound_receipt := jsonb_build_object(
      'feature', lower(trim(p_feature)),
      'paymentSource', 'internal',
      'eventId', null,
      'creditBalance', credit_balance,
      'creditsSpent', 0,
      'internalAccess', true
    );
  elsif normalized_source = 'subscription' then
    bound_receipt := jsonb_build_object(
      'feature', lower(trim(p_feature)),
      'paymentSource', 'subscription',
      'eventId', null,
      'creditBalance', credit_balance,
      'creditsSpent', 0
    );
  else
    select consumed.event_id, consumed.used, consumed.allowed
    into usage_event_id, usage_used, usage_allowed
    from public.consume_usage_event(
      p_user_id,
      p_event_type,
      p_included_limit,
      coalesce(p_metadata, '{}'::jsonb)
    ) as consumed;

    if usage_allowed then
      select coalesce(account.balance, 0)
      into credit_balance
      from public.credit_accounts as account
      where account.user_id = p_user_id;
      credit_balance := coalesce(credit_balance, 0);
      bound_receipt := jsonb_build_object(
        'feature', lower(trim(p_feature)),
        'paymentSource', 'included',
        'eventId', usage_event_id::text,
        'creditBalance', credit_balance,
        'creditsSpent', 0,
        'used', usage_used,
        'limit', p_included_limit
      );
    else
      if coalesce(p_credit_cost, 0) <= 0 then
        return query select 'allowance_exhausted'::text, '{}'::jsonb,
          credit_balance, coalesce(usage_used, 0), false;
        return;
      end if;
      if coalesce(p_confirmed_max, 0) <= 0
         or p_credit_cost > coalesce(p_approved_feature_max, 0) then
        return query select 'confirmation_required'::text, '{}'::jsonb,
          credit_balance, coalesce(usage_used, 0), false;
        return;
      end if;

      select spent.ledger_id, spent.balance, spent.allowed,
             spent.duplicate, spent.limit_exceeded
      into credit_ledger_id, credit_balance, credit_allowed,
           credit_duplicate, credit_limit_exceeded
      from public.spend_credits_confirmed(
        p_user_id,
        p_credit_cost,
        p_credit_reason,
        p_credit_action_key,
        p_credit_component,
        p_confirmed_max,
        coalesce(p_metadata, '{}'::jsonb)
      ) as spent;

      if credit_limit_exceeded then
        return query select 'credit_limit_exceeded'::text, '{}'::jsonb,
          coalesce(credit_balance, 0), coalesce(usage_used, 0), false;
        return;
      end if;
      if not credit_allowed then
        return query select 'credits_required'::text, '{}'::jsonb,
          coalesce(credit_balance, 0), coalesce(usage_used, 0), false;
        return;
      end if;

      bound_receipt := jsonb_build_object(
        'feature', lower(trim(p_feature)),
        'paymentSource', 'credits',
        'eventId', case
          when credit_ledger_id is null then null
          else 'credit:' || credit_ledger_id::text
        end,
        'creditBalance', coalesce(credit_balance, 0),
        'creditsSpent', case when credit_duplicate then 0 else p_credit_cost end,
        'idempotentReplay', credit_duplicate
      );
    end if;
  end if;

  bound_metadata := (job_row.metadata - 'reservationToken' - 'reservationExpiresAt')
    || jsonb_build_object(
      'billingPending', false,
      'billingBoundAt', to_jsonb(now()),
      'videoPhase', 'ready_to_launch',
      'launchReadyExpiresAt', to_jsonb(now() + interval '10 minutes')
    );

  update public.media_jobs as job
  set billing_receipt = bound_receipt,
      billing_refunded = false,
      video_phase = 'ready_to_launch',
      lease_token = null,
      lease_expires_at = now() + interval '10 minutes',
      metadata = bound_metadata,
      updated_at = now()
  where job.id = p_job_id
    and job.user_id = p_user_id
    and job.idempotency_key = normalized_key
    and job.request_fingerprint = normalized_fingerprint
    and job.video_phase = 'reserved_unbilled'
    and job.lease_token = reservation_token
  returning * into updated_row;

  if updated_row.id is null then
    raise exception 'Video reservation changed during billing'
      using errcode = '40001';
  end if;

  return query select 'bound'::text, updated_row.billing_receipt,
    coalesce((updated_row.billing_receipt ->> 'creditBalance')::bigint, 0),
    coalesce((updated_row.billing_receipt ->> 'used')::integer, 0), false;
end;
$$;

create or replace function public.claim_video_provider_launch(
  p_user_id uuid,
  p_job_id uuid,
  p_idempotency_key text,
  p_request_fingerprint text,
  p_launch_token text,
  p_lease_seconds integer,
  p_claim_ready boolean default true
)
returns table(outcome text, job jsonb)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  normalized_key text := trim(coalesce(p_idempotency_key, ''));
  normalized_fingerprint text := lower(trim(coalesce(p_request_fingerprint, '')));
  launch_token uuid;
  phase text;
  lease_expires_at timestamptz;
  event_id text;
  payment_source text;
  refunded boolean := false;
  updated_row public.media_jobs%rowtype;
begin
  if p_user_id is null or p_job_id is null then
    raise exception 'Video launch identity is required' using errcode = '22023';
  end if;
  if normalized_key = '' or length(normalized_key) > 160 then
    raise exception 'Video idempotency key is invalid' using errcode = '22023';
  end if;
  if normalized_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'Video request fingerprint is invalid' using errcode = '22023';
  end if;
  if p_claim_ready then
    begin
      launch_token := trim(coalesce(p_launch_token, ''))::uuid;
    exception when invalid_text_representation then
      raise exception 'Video launch token is invalid' using errcode = '22023';
    end;
    if launch_token is null then
      raise exception 'Video launch token is required' using errcode = '22023';
    end if;
    if coalesce(p_lease_seconds, 0) < 30 or p_lease_seconds > 600 then
      raise exception 'Video launch lease is invalid' using errcode = '22023';
    end if;
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(
      'askcrump-video-owner-billing-v1:' || p_user_id::text,
      0
    )
  );

  if not pg_try_advisory_xact_lock(
    hashtextextended('video-launch:' || p_job_id::text, 0)
  ) then
    return query select 'busy'::text, '{}'::jsonb;
    return;
  end if;
  select * into job_row
  from public.media_jobs as current_job
  where current_job.id = p_job_id
    and current_job.user_id = p_user_id
  for update skip locked;

  if not found then
    if exists (
      select 1 from public.media_jobs as visible_job
      where visible_job.id = p_job_id and visible_job.user_id = p_user_id
    ) then
      return query select 'busy'::text, '{}'::jsonb;
    else
      return query select 'missing'::text, '{}'::jsonb;
    end if;
    return;
  end if;

  if job_row.idempotency_key is distinct from normalized_key
     or job_row.request_fingerprint is distinct from normalized_fingerprint then
    return query select 'request_conflict'::text, to_jsonb(job_row);
    return;
  end if;

  if job_row.video_phase in ('processing', 'ready', 'failed')
     or job_row.status in ('processing', 'ready', 'failed')
     or job_row.provider_job_id not like 'pending:%' then
    return query select 'current'::text, to_jsonb(job_row);
    return;
  end if;

  phase := job_row.video_phase;
  lease_expires_at := job_row.lease_expires_at;
  if phase = 'reserved_unbilled' then
    if lease_expires_at is not null and lease_expires_at > now() then
      return query select 'waiting_for_billing'::text, to_jsonb(job_row);
      return;
    end if;

    delete from public.media_jobs as current_job
    where current_job.id = p_job_id
      and current_job.user_id = p_user_id
      and current_job.idempotency_key = normalized_key
      and current_job.request_fingerprint = normalized_fingerprint
      and current_job.video_phase = 'reserved_unbilled'
      and (
        current_job.lease_expires_at is null
        or current_job.lease_expires_at <= now()
      );
    return query select 'expired_unbilled'::text,
      to_jsonb(job_row)
        || jsonb_build_object(
          'status', 'failed',
          'video_phase', 'failed',
          'lease_token', null,
          'lease_expires_at', null,
          'error_message',
            'This video request expired before any allowance or credits were used. Start it again.',
          'estimated_provider_cost_cents', 0,
          'metadata',
            (job_row.metadata - 'reservationToken' - 'reservationExpiresAt')
              || jsonb_build_object(
                'videoPhase', 'failed',
                'billingPending', false,
                'providerAccepted', false,
                'providerAcceptance', 'not-started',
                'refundEligible', false,
                'providerFailureCode', 'VIDEO_RESERVATION_EXPIRED'
              ),
          'updated_at', to_jsonb(now())
        );
    return;
  end if;

  if phase = 'ready_to_launch' then
    if job_row.billing_receipt = '{}'::jsonb
       or job_row.billing_refunded
       or job_row.lease_token is not null then
      return query select 'phase_conflict'::text, to_jsonb(job_row);
      return;
    end if;
    if lease_expires_at is null or lease_expires_at <= now() then
      event_id := nullif(trim(coalesce(
        job_row.billing_receipt ->> 'eventId', ''
      )), '');
      payment_source := lower(trim(coalesce(
        job_row.billing_receipt ->> 'paymentSource', ''
      )));
      if not job_row.billing_refunded then
        if payment_source = 'credits' then
          if coalesce(event_id, '') !~* (
            '^credit:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
            || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
          ) then
            raise exception 'Video launch credit receipt is invalid'
              using errcode = '22023';
          end if;
          perform 1 from public.refund_credit_spend(
            p_user_id,
            substring(event_id from 8)::uuid,
            jsonb_build_object(
              'reason', 'video_launch_not_started',
              'mediaJobId', p_job_id
            )
          );
          refunded := true;
        elsif payment_source = 'included' then
          if coalesce(event_id, '') !~* (
            '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
            || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
          ) then
            raise exception 'Video launch usage receipt is invalid'
              using errcode = '22023';
          end if;
          delete from public.usage_events as usage
          where usage.id = event_id::uuid and usage.user_id = p_user_id;
          refunded := true;
        elsif payment_source in ('internal', 'subscription')
              and event_id is null then
          refunded := false;
        else
          raise exception 'Video launch payment source is invalid'
            using errcode = '22023';
        end if;
      end if;
      update public.media_jobs as current_job
      set status = 'failed',
          error_message = 'Ask Crump could not start the provider before the safety window closed. No credits or included use remain charged.',
          estimated_provider_cost_cents = 0,
          billing_refunded = current_job.billing_refunded or refunded,
          video_phase = 'failed',
          lease_token = null,
          lease_expires_at = null,
          metadata = (
              current_job.metadata
              - 'launchReadyExpiresAt'
              - 'launchToken'
              - 'launchExpiresAt'
            )
            || jsonb_build_object(
              'videoPhase', 'failed',
              'providerAccepted', false,
              'providerAcceptance', 'not-started',
              'refundEligible', false,
              'providerFailureCode', 'VIDEO_PROVIDER_LAUNCH_NOT_STARTED'
            ),
          updated_at = now()
      where current_job.id = p_job_id
        and current_job.user_id = p_user_id
        and current_job.idempotency_key = normalized_key
        and current_job.request_fingerprint = normalized_fingerprint
        and current_job.video_phase = 'ready_to_launch'
        and (
          current_job.lease_expires_at is null
          or current_job.lease_expires_at <= now()
        )
      returning * into updated_row;
      if updated_row.id is null then
        raise exception 'Video launch deadline changed during settlement'
          using errcode = '40001';
      end if;
      return query select 'ready_expired'::text, to_jsonb(updated_row);
      return;
    end if;
    if not p_claim_ready then
      return query select 'ready'::text, to_jsonb(job_row);
      return;
    end if;
    update public.media_jobs as current_job
    set video_phase = 'launching',
        lease_token = launch_token,
        lease_expires_at = now() + make_interval(secs => p_lease_seconds),
        metadata = (
          current_job.metadata
          - 'launchReadyExpiresAt'
          - 'launchToken'
          - 'launchExpiresAt'
        )
          || jsonb_build_object(
            'videoPhase', 'launching',
            'launchStartedAt', to_jsonb(now()),
            'providerAccepted', false,
            'providerAcceptance', 'unconfirmed'
          ),
        updated_at = now()
    where current_job.id = p_job_id
      and current_job.user_id = p_user_id
      and current_job.idempotency_key = normalized_key
      and current_job.request_fingerprint = normalized_fingerprint
      and current_job.video_phase = 'ready_to_launch'
      and current_job.lease_expires_at > now()
    returning * into updated_row;
    if updated_row.id is null then
      raise exception 'Video launch readiness changed during claim'
        using errcode = '40001';
    end if;
    return query select 'claimed'::text, to_jsonb(updated_row);
    return;
  end if;

  if phase = 'launching' then
    if job_row.billing_receipt = '{}'::jsonb then
      return query select 'phase_conflict'::text, to_jsonb(job_row);
      return;
    end if;
    if lease_expires_at is not null and lease_expires_at > now() then
      if job_row.lease_token = launch_token then
        -- The first claim may have committed while its HTTP response was
        -- lost. Retrying the same RPC with the same caller-generated token
        -- must return the lease so that exactly that caller can still launch.
        return query select 'claimed'::text, to_jsonb(job_row);
      else
        return query select 'launch_in_progress'::text, to_jsonb(job_row);
      end if;
      return;
    end if;

    event_id := nullif(trim(coalesce(
      job_row.billing_receipt ->> 'eventId', ''
    )), '');
    payment_source := lower(trim(coalesce(
      job_row.billing_receipt ->> 'paymentSource', ''
    )));
    if not job_row.billing_refunded then
      if payment_source = 'credits' then
        if coalesce(event_id, '') !~* (
          '^credit:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
          || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        ) then
          raise exception 'Video launch credit receipt is invalid'
            using errcode = '22023';
        end if;
        perform 1 from public.refund_credit_spend(
          p_user_id,
          substring(event_id from 8)::uuid,
          jsonb_build_object(
            'reason', 'ambiguous_video_provider_launch',
            'mediaJobId', p_job_id
          )
        );
        refunded := true;
      elsif payment_source = 'included' then
        if coalesce(event_id, '') !~* (
          '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
          || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        ) then
          raise exception 'Video launch usage receipt is invalid'
            using errcode = '22023';
        end if;
        delete from public.usage_events as usage
        where usage.id = event_id::uuid and usage.user_id = p_user_id;
        refunded := true;
      elsif payment_source in ('internal', 'subscription')
            and event_id is null then
        refunded := false;
      else
        raise exception 'Video launch payment source is invalid'
          using errcode = '22023';
      end if;
    end if;

    update public.media_jobs as current_job
    set status = 'failed',
        error_message = 'Ask Crump could not confirm the provider launch. The generation was not retried, and your Ask Crump charge was returned.',
        billing_refunded = current_job.billing_refunded or refunded,
        video_phase = 'failed',
        lease_token = null,
        lease_expires_at = null,
        metadata = (current_job.metadata - 'launchToken' - 'launchExpiresAt')
          || jsonb_build_object(
            'videoPhase', 'failed',
            'providerAccepted', false,
            'providerAcceptance', 'unknown',
            'refundEligible', false,
            'providerFailureCode', 'VIDEO_PROVIDER_LAUNCH_UNCONFIRMED'
          ),
        updated_at = now()
    where current_job.id = p_job_id
      and current_job.user_id = p_user_id
      and current_job.idempotency_key = normalized_key
      and current_job.request_fingerprint = normalized_fingerprint
      and current_job.video_phase = 'launching'
      and (
        current_job.lease_expires_at is null
        or current_job.lease_expires_at <= now()
      )
    returning * into updated_row;
    if updated_row.id is null then
      raise exception 'Video launch lease changed during recovery'
        using errcode = '40001';
    end if;
    return query select 'ambiguous_failed'::text, to_jsonb(updated_row);
    return;
  end if;

  return query select 'phase_conflict'::text, to_jsonb(job_row);
end;
$$;

create or replace function public.release_video_reservation(
  p_user_id uuid,
  p_job_id uuid,
  p_idempotency_key text,
  p_request_fingerprint text,
  p_reservation_token text,
  p_message text
)
returns table(outcome text, job jsonb)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  normalized_key text := trim(coalesce(p_idempotency_key, ''));
  normalized_fingerprint text := lower(trim(coalesce(p_request_fingerprint, '')));
  reservation_token uuid;
begin
  if p_user_id is null or p_job_id is null then
    raise exception 'Video reservation release identity is required'
      using errcode = '22023';
  end if;
  if normalized_key = '' or length(normalized_key) > 160 then
    raise exception 'Video idempotency key is invalid' using errcode = '22023';
  end if;
  if normalized_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'Video request fingerprint is invalid' using errcode = '22023';
  end if;
  begin
    reservation_token := trim(coalesce(p_reservation_token, ''))::uuid;
  exception when invalid_text_representation then
    raise exception 'Video reservation token is invalid' using errcode = '22023';
  end;
  if reservation_token is null then
    raise exception 'Video reservation token is required' using errcode = '22023';
  end if;
  perform pg_advisory_xact_lock(
    hashtextextended(
      'askcrump-video-owner-billing-v1:' || p_user_id::text,
      0
    )
  );
  if not pg_try_advisory_xact_lock(
    hashtextextended('video-billing:' || p_job_id::text, 0)
  ) then
    return query select 'busy'::text, '{}'::jsonb;
    return;
  end if;
  select * into job_row
  from public.media_jobs as current_job
  where current_job.id = p_job_id and current_job.user_id = p_user_id
  for update skip locked;
  if not found then
    if exists (
      select 1 from public.media_jobs as visible_job
      where visible_job.id = p_job_id and visible_job.user_id = p_user_id
    ) then
      return query select 'busy'::text, '{}'::jsonb;
    else
      return query select 'missing'::text, '{}'::jsonb;
    end if;
    return;
  end if;

  if job_row.idempotency_key is distinct from normalized_key
     or job_row.request_fingerprint is distinct from normalized_fingerprint then
    return query select 'request_conflict'::text, to_jsonb(job_row);
    return;
  end if;

  if job_row.status <> 'queued'
     or job_row.provider_job_id not like 'pending:%'
     or job_row.billing_receipt <> '{}'::jsonb
     or job_row.video_phase <> 'reserved_unbilled'
     or job_row.lease_token is distinct from reservation_token
  then
    return query select 'release_conflict'::text, to_jsonb(job_row);
    return;
  end if;

  delete from public.media_jobs as current_job
  where current_job.id = p_job_id
    and current_job.user_id = p_user_id
    and current_job.idempotency_key = normalized_key
    and current_job.request_fingerprint = normalized_fingerprint
    and current_job.video_phase = 'reserved_unbilled'
    and current_job.lease_token = reservation_token;
  return query select 'released'::text,
    to_jsonb(job_row)
      || jsonb_build_object(
        'status', 'failed',
        'video_phase', 'failed',
        'lease_token', null,
        'lease_expires_at', null,
        'error_message', left(
          coalesce(nullif(trim(p_message), ''),
            'This video request stopped before billing.'),
          500
        ),
        'estimated_provider_cost_cents', 0,
        'metadata',
          (job_row.metadata - 'reservationToken' - 'reservationExpiresAt')
            || jsonb_build_object(
              'videoPhase', 'failed',
              'billingPending', false,
              'providerAccepted', false,
              'providerAcceptance', 'not-started',
              'refundEligible', false,
              'providerFailureCode', 'VIDEO_RESERVATION_RELEASED'
            ),
        'updated_at', to_jsonb(now())
      );
end;
$$;

create or replace function public.complete_video_provider_launch(
  p_user_id uuid,
  p_job_id uuid,
  p_idempotency_key text,
  p_request_fingerprint text,
  p_launch_token text,
  p_provider_job_id text
)
returns table(outcome text, job jsonb)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  normalized_key text := trim(coalesce(p_idempotency_key, ''));
  normalized_fingerprint text := lower(trim(coalesce(p_request_fingerprint, '')));
  normalized_provider_job_id text := left(trim(coalesce(p_provider_job_id, '')), 500);
  launch_token uuid;
  updated_row public.media_jobs%rowtype;
begin
  if p_user_id is null or p_job_id is null then
    raise exception 'Completed video launch identity is required' using errcode = '22023';
  end if;
  if normalized_key = '' or length(normalized_key) > 160 then
    raise exception 'Video idempotency key is invalid' using errcode = '22023';
  end if;
  if normalized_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'Video request fingerprint is invalid' using errcode = '22023';
  end if;
  begin
    launch_token := trim(coalesce(p_launch_token, ''))::uuid;
  exception when invalid_text_representation then
    raise exception 'Video launch token is invalid' using errcode = '22023';
  end;
  if launch_token is null then
    raise exception 'Video launch token is required' using errcode = '22023';
  end if;
  if normalized_provider_job_id = ''
     or normalized_provider_job_id like 'pending:%' then
    raise exception 'Provider video job identity is invalid' using errcode = '22023';
  end if;
  perform pg_advisory_xact_lock(
    hashtextextended(
      'askcrump-video-owner-billing-v1:' || p_user_id::text,
      0
    )
  );
  if not pg_try_advisory_xact_lock(
    hashtextextended('video-launch:' || p_job_id::text, 0)
  ) then
    return query select 'busy'::text, '{}'::jsonb;
    return;
  end if;
  select * into job_row
  from public.media_jobs as current_job
  where current_job.id = p_job_id and current_job.user_id = p_user_id
  for update skip locked;
  if not found then
    if exists (
      select 1 from public.media_jobs as visible_job
      where visible_job.id = p_job_id and visible_job.user_id = p_user_id
    ) then
      return query select 'busy'::text, '{}'::jsonb;
    else
      return query select 'missing'::text, '{}'::jsonb;
    end if;
    return;
  end if;

  if job_row.idempotency_key is distinct from normalized_key
     or job_row.request_fingerprint is distinct from normalized_fingerprint then
    return query select 'request_conflict'::text, to_jsonb(job_row);
    return;
  end if;

  if job_row.video_phase in ('processing', 'ready')
     and job_row.status in ('processing', 'ready')
     and job_row.provider_job_id = normalized_provider_job_id then
    return query select 'existing'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.status <> 'queued'
     or job_row.provider_job_id not like 'pending:%'
     or job_row.video_phase <> 'launching'
     or job_row.lease_token is distinct from launch_token
     or job_row.billing_receipt = '{}'::jsonb
  then
    return query select 'launch_conflict'::text, to_jsonb(job_row);
    return;
  end if;

  update public.media_jobs as current_job
  set provider_job_id = normalized_provider_job_id,
      status = 'processing',
      video_phase = 'processing',
      lease_token = null,
      lease_expires_at = null,
      provider_started_at = coalesce(current_job.provider_started_at, now()),
      sweep_retry_after = '-infinity'::timestamptz,
      metadata = (current_job.metadata - 'launchToken' - 'launchExpiresAt')
        || jsonb_build_object(
          'videoPhase', 'processing',
          'providerAccepted', true,
          'providerAcceptance', 'confirmed',
          'providerAcceptedAt', to_jsonb(now())
        ),
      updated_at = now()
  where current_job.id = p_job_id
    and current_job.user_id = p_user_id
    and current_job.idempotency_key = normalized_key
    and current_job.request_fingerprint = normalized_fingerprint
    and current_job.video_phase = 'launching'
    and current_job.lease_token = launch_token
  returning * into updated_row;
  if updated_row.id is null then
    raise exception 'Video provider launch changed during completion'
      using errcode = '40001';
  end if;
  return query select 'completed'::text, to_jsonb(updated_row);
end;
$$;

create or replace function public.fail_video_provider_launch(
  p_user_id uuid,
  p_job_id uuid,
  p_idempotency_key text,
  p_request_fingerprint text,
  p_launch_token text,
  p_message text,
  p_failure_code text,
  p_refund_eligible boolean,
  p_provider_acceptance text
)
returns table(outcome text, job jsonb)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  updated_row public.media_jobs%rowtype;
  normalized_key text := trim(coalesce(p_idempotency_key, ''));
  normalized_fingerprint text := lower(trim(coalesce(p_request_fingerprint, '')));
  launch_token uuid;
  acceptance text := lower(trim(coalesce(p_provider_acceptance, 'unknown')));
  event_id text;
  payment_source text;
  refunded boolean := false;
begin
  if p_user_id is null or p_job_id is null then
    raise exception 'Failed video launch identity is required' using errcode = '22023';
  end if;
  if normalized_key = '' or length(normalized_key) > 160 then
    raise exception 'Video idempotency key is invalid' using errcode = '22023';
  end if;
  if normalized_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'Video request fingerprint is invalid' using errcode = '22023';
  end if;
  begin
    launch_token := trim(coalesce(p_launch_token, ''))::uuid;
  exception when invalid_text_representation then
    raise exception 'Video launch token is invalid' using errcode = '22023';
  end;
  if launch_token is null then
    raise exception 'Video launch token is required' using errcode = '22023';
  end if;
  if acceptance not in ('rejected', 'unknown') then
    raise exception 'Video provider acceptance state is invalid' using errcode = '22023';
  end if;
  perform pg_advisory_xact_lock(
    hashtextextended(
      'askcrump-video-owner-billing-v1:' || p_user_id::text,
      0
    )
  );
  if not pg_try_advisory_xact_lock(
    hashtextextended('video-launch:' || p_job_id::text, 0)
  ) then
    return query select 'busy'::text, '{}'::jsonb;
    return;
  end if;
  select * into job_row
  from public.media_jobs as current_job
  where current_job.id = p_job_id and current_job.user_id = p_user_id
  for update skip locked;
  if not found then
    if exists (
      select 1 from public.media_jobs as visible_job
      where visible_job.id = p_job_id and visible_job.user_id = p_user_id
    ) then
      return query select 'busy'::text, '{}'::jsonb;
    else
      return query select 'missing'::text, '{}'::jsonb;
    end if;
    return;
  end if;

  if job_row.idempotency_key is distinct from normalized_key
     or job_row.request_fingerprint is distinct from normalized_fingerprint then
    return query select 'request_conflict'::text, to_jsonb(job_row);
    return;
  end if;

  if job_row.video_phase = 'failed' and job_row.status = 'failed' then
    return query select 'existing'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.status <> 'queued'
     or job_row.provider_job_id not like 'pending:%'
     or job_row.video_phase <> 'launching'
     or job_row.lease_token is distinct from launch_token
     or job_row.billing_receipt = '{}'::jsonb
  then
    return query select 'launch_conflict'::text, to_jsonb(job_row);
    return;
  end if;

  event_id := nullif(trim(coalesce(
    job_row.billing_receipt ->> 'eventId', ''
  )), '');
  payment_source := lower(trim(coalesce(
    job_row.billing_receipt ->> 'paymentSource', ''
  )));
  -- Provider rejection and unknown acceptance both settle customer-first.
  -- The input flag is retained for API compatibility and audit metadata, but
  -- cannot suppress a refund for an included-use or credit-backed receipt.
  if not job_row.billing_refunded then
    if payment_source = 'credits' then
      if coalesce(event_id, '') !~* (
        '^credit:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
        || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      ) then
        raise exception 'Failed video launch credit receipt is invalid'
          using errcode = '22023';
      end if;
      perform 1 from public.refund_credit_spend(
        p_user_id,
        substring(event_id from 8)::uuid,
        jsonb_build_object(
          'reason', 'video_provider_launch_failed',
          'mediaJobId', p_job_id,
          'providerAcceptance', acceptance
        )
      );
      refunded := true;
    elsif payment_source = 'included' then
      if coalesce(event_id, '') !~* (
        '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
        || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      ) then
        raise exception 'Failed video launch usage receipt is invalid'
          using errcode = '22023';
      end if;
      delete from public.usage_events as usage
      where usage.id = event_id::uuid and usage.user_id = p_user_id;
      refunded := true;
    elsif payment_source in ('internal', 'subscription')
          and event_id is null then
      refunded := false;
    else
      raise exception 'Failed video launch payment source is invalid'
        using errcode = '22023';
    end if;
  end if;

  update public.media_jobs as current_job
  set status = 'failed',
      error_message = left(coalesce(nullif(trim(p_message), ''), 'Video generation failed.'), 500),
      estimated_provider_cost_cents = case
        when acceptance = 'rejected' then 0
        else current_job.estimated_provider_cost_cents
      end,
      billing_refunded = current_job.billing_refunded or refunded,
      video_phase = 'failed',
      lease_token = null,
      lease_expires_at = null,
      metadata = (current_job.metadata - 'launchToken' - 'launchExpiresAt')
        || jsonb_build_object(
          'videoPhase', 'failed',
          'providerAccepted', false,
          'providerAcceptance', acceptance,
          'providerFailureCode', left(coalesce(p_failure_code, ''), 120),
          'refundRequested', coalesce(p_refund_eligible, false),
          'refundEligible', false
        ),
      updated_at = now()
  where current_job.id = p_job_id
    and current_job.user_id = p_user_id
    and current_job.idempotency_key = normalized_key
    and current_job.request_fingerprint = normalized_fingerprint
    and current_job.video_phase = 'launching'
    and current_job.lease_token = launch_token
  returning * into updated_row;
  if updated_row.id is null then
    raise exception 'Video provider launch changed during failure settlement'
      using errcode = '40001';
  end if;
  return query select 'failed'::text, to_jsonb(updated_row);
end;
$$;

create or replace function public.claim_video_finalization(
  p_user_id uuid,
  p_job_id uuid,
  p_idempotency_key text,
  p_request_fingerprint text,
  p_finalization_token text,
  p_lease_seconds integer,
  p_terminal_outcome text,
  p_refund_eligible boolean
)
returns table(outcome text, job jsonb)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  updated_row public.media_jobs%rowtype;
  normalized_key text := trim(coalesce(p_idempotency_key, ''));
  normalized_fingerprint text := lower(trim(coalesce(p_request_fingerprint, '')));
  terminal_outcome text := lower(trim(coalesce(p_terminal_outcome, '')));
  finalization_token uuid;
begin
  if p_user_id is null or p_job_id is null then
    raise exception 'Video finalization identity is required' using errcode = '22023';
  end if;
  if normalized_key = '' or length(normalized_key) > 160 then
    raise exception 'Video idempotency key is invalid' using errcode = '22023';
  end if;
  if normalized_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'Video request fingerprint is invalid' using errcode = '22023';
  end if;
  begin
    finalization_token := trim(coalesce(p_finalization_token, ''))::uuid;
  exception when invalid_text_representation then
    raise exception 'Video finalization token is invalid' using errcode = '22023';
  end;
  if finalization_token is null then
    raise exception 'Video finalization token is required' using errcode = '22023';
  end if;
  if coalesce(p_lease_seconds, 0) < 60 or p_lease_seconds > 1800 then
    raise exception 'Video finalization lease is invalid' using errcode = '22023';
  end if;
  if terminal_outcome not in ('ready', 'failed') then
    raise exception 'Video terminal outcome is invalid' using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(
      'askcrump-video-owner-billing-v1:' || p_user_id::text,
      0
    )
  );
  if not pg_try_advisory_xact_lock(
    hashtextextended('video-finalization:' || p_job_id::text, 0)
  ) then
    return query select 'busy'::text, '{}'::jsonb;
    return;
  end if;
  select * into job_row
  from public.media_jobs as current_job
  where current_job.id = p_job_id and current_job.user_id = p_user_id
  for update skip locked;
  if not found then
    if exists (
      select 1 from public.media_jobs as visible_job
      where visible_job.id = p_job_id and visible_job.user_id = p_user_id
    ) then
      return query select 'busy'::text, '{}'::jsonb;
    else
      return query select 'missing'::text, '{}'::jsonb;
    end if;
    return;
  end if;
  if job_row.idempotency_key is distinct from normalized_key
     or job_row.request_fingerprint is distinct from normalized_fingerprint then
    return query select 'request_conflict'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.video_phase in ('ready', 'failed')
     and job_row.status in ('ready', 'failed') then
    return query select 'current'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.status <> 'processing'
     or job_row.provider_job_id is null
     or trim(job_row.provider_job_id) = ''
     or job_row.provider_job_id like 'pending:%'
     or job_row.billing_receipt = '{}'::jsonb
     or job_row.billing_refunded then
    return query select 'phase_conflict'::text, to_jsonb(job_row);
    return;
  end if;

  if job_row.video_phase = 'processing'
     and job_row.provider_started_at <= now() - interval '24 hours' then
    return query select 'expired'::text, to_jsonb(job_row);
    return;
  end if;

  if job_row.video_phase = 'finalizing'
     and job_row.finalization_started_at <= now() - interval '1 hour' then
    return query select 'expired'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.video_phase = 'finalizing'
     and job_row.lease_expires_at is not null
     and job_row.lease_expires_at > now() then
    if job_row.lease_token = finalization_token then
      return query select 'claimed'::text, to_jsonb(job_row);
    else
      return query select 'in_progress'::text, to_jsonb(job_row);
    end if;
    return;
  end if;
  if job_row.video_phase = 'finalizing'
     and coalesce(job_row.metadata ->> 'finalizationOutcome', '')
       is distinct from terminal_outcome then
    return query select 'finalization_conflict'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.video_phase not in ('processing', 'finalizing') then
    return query select 'phase_conflict'::text, to_jsonb(job_row);
    return;
  end if;

  update public.media_jobs as current_job
  set video_phase = 'finalizing',
      lease_token = finalization_token,
      lease_expires_at = least(
        now() + make_interval(secs => p_lease_seconds),
        coalesce(current_job.finalization_started_at, now())
          + interval '1 hour'
      ),
      sweep_retry_after = '-infinity'::timestamptz,
      finalization_started_at = coalesce(
        current_job.finalization_started_at,
        now()
      ),
      metadata = (
        current_job.metadata
        - 'finalizationOutcome'
        - 'finalizationRefundEligible'
        - 'finalizationStartedAt'
        - 'finalizationExpiresAt'
      ) || jsonb_build_object(
        'videoPhase', 'finalizing',
        'finalizationOutcome', terminal_outcome,
        'finalizationRefundEligible', case
          when current_job.video_phase = 'finalizing' then
            coalesce(
              (current_job.metadata ->> 'finalizationRefundEligible')::boolean,
              true
            ) and coalesce(p_refund_eligible, true)
          else coalesce(p_refund_eligible, true)
        end,
        'finalizationStartedAt', to_jsonb(coalesce(
          current_job.finalization_started_at,
          now()
        )),
        'finalizationExpiresAt',
          to_jsonb(coalesce(
            current_job.finalization_started_at,
            now()
          ) + interval '1 hour')
      ),
      updated_at = now()
  where current_job.id = p_job_id
    and current_job.user_id = p_user_id
    and current_job.idempotency_key = normalized_key
    and current_job.request_fingerprint = normalized_fingerprint
    and current_job.status = 'processing'
    and (
      current_job.video_phase = 'processing'
      or (
        current_job.video_phase = 'finalizing'
        and (
          current_job.lease_expires_at is null
          or current_job.lease_expires_at <= now()
        )
      )
    )
  returning * into updated_row;
  if updated_row.id is null then
    raise exception 'Video finalization lease changed during claim'
      using errcode = '40001';
  end if;
  return query select 'claimed'::text, to_jsonb(updated_row);
end;
$$;

create or replace function public.complete_video_finalization(
  p_user_id uuid,
  p_job_id uuid,
  p_idempotency_key text,
  p_request_fingerprint text,
  p_finalization_token text,
  p_file_id uuid,
  p_provider_asset_reference text,
  p_provider_asset_expires_at timestamptz,
  p_stored_bytes bigint,
  p_file_metadata jsonb
)
returns table(outcome text, job jsonb)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  updated_row public.media_jobs%rowtype;
  stored_file public.user_files%rowtype;
  normalized_key text := trim(coalesce(p_idempotency_key, ''));
  normalized_fingerprint text := lower(trim(coalesce(p_request_fingerprint, '')));
  finalization_token uuid;
begin
  if p_user_id is null or p_job_id is null or p_file_id is null then
    raise exception 'Completed video finalization identity is required'
      using errcode = '22023';
  end if;
  if p_file_id is distinct from p_job_id then
    raise exception 'Completed video file identity must match its job'
      using errcode = '22023';
  end if;
  if normalized_key = '' or length(normalized_key) > 160 then
    raise exception 'Video idempotency key is invalid' using errcode = '22023';
  end if;
  if normalized_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'Video request fingerprint is invalid' using errcode = '22023';
  end if;
  begin
    finalization_token := trim(coalesce(p_finalization_token, ''))::uuid;
  exception when invalid_text_representation then
    raise exception 'Video finalization token is invalid' using errcode = '22023';
  end;
  if finalization_token is null then
    raise exception 'Video finalization token is required' using errcode = '22023';
  end if;
  if coalesce(p_stored_bytes, 0) <= 0 or p_stored_bytes > 104857600 then
    raise exception 'Stored video size is invalid' using errcode = '22023';
  end if;
  if jsonb_typeof(coalesce(p_file_metadata, '{}'::jsonb)) <> 'object'
     or octet_length(coalesce(p_file_metadata, '{}'::jsonb)::text) > 32768
  then
    raise exception 'Stored video metadata is invalid' using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(
      'askcrump-video-owner-billing-v1:' || p_user_id::text,
      0
    )
  );
  if not pg_try_advisory_xact_lock(
    hashtextextended('video-finalization:' || p_job_id::text, 0)
  ) then
    return query select 'busy'::text, '{}'::jsonb;
    return;
  end if;
  select * into job_row
  from public.media_jobs as current_job
  where current_job.id = p_job_id and current_job.user_id = p_user_id
  for update skip locked;
  if not found then
    if exists (
      select 1 from public.media_jobs as visible_job
      where visible_job.id = p_job_id and visible_job.user_id = p_user_id
    ) then
      return query select 'busy'::text, '{}'::jsonb;
    else
      return query select 'missing'::text, '{}'::jsonb;
    end if;
    return;
  end if;
  if job_row.idempotency_key is distinct from normalized_key
     or job_row.request_fingerprint is distinct from normalized_fingerprint then
    return query select 'request_conflict'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.video_phase = 'ready'
     and job_row.status = 'ready'
     and job_row.file_id = p_file_id then
    return query select 'existing'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.video_phase <> 'finalizing'
     or job_row.status <> 'processing'
     or job_row.lease_token is distinct from finalization_token
     or coalesce(job_row.metadata ->> 'finalizationOutcome', '') <> 'ready'
  then
    return query select 'finalization_conflict'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.finalization_started_at <= now() - interval '1 hour'
     or job_row.lease_expires_at is null
     or job_row.lease_expires_at <= now() then
    return query select 'expired'::text, to_jsonb(job_row);
    return;
  end if;

  -- The storage object already exists at this deterministic private path.
  -- Publish its file row and bind the media job in this same transaction so
  -- a deadline sweep can never expose a free/orphaned ready file.
  insert into public.user_files (
    id,
    user_id,
    chat_id,
    message_id,
    storage_path,
    file_name,
    mime_type,
    size_bytes,
    kind,
    status,
    metadata,
    updated_at,
    deleted_at
  ) values (
    p_file_id,
    p_user_id,
    null,
    null,
    p_user_id::text || '/' || p_file_id::text || '.mp4',
    'crump-video-' || p_file_id::text || '.mp4',
    'video/mp4',
    p_stored_bytes,
    'generated_video',
    'ready',
    coalesce(p_file_metadata, '{}'::jsonb)
      || jsonb_build_object(
        'mediaJobId', p_job_id,
        'finalizationBoundAt', to_jsonb(now())
      ),
    now(),
    null
  )
  on conflict (id) do update
  set storage_path = excluded.storage_path,
      file_name = excluded.file_name,
      mime_type = excluded.mime_type,
      size_bytes = excluded.size_bytes,
      kind = excluded.kind,
      status = excluded.status,
      metadata = excluded.metadata,
      updated_at = excluded.updated_at,
      deleted_at = null
  where user_files.user_id = excluded.user_id
    and user_files.kind = 'generated_video'
  returning * into stored_file;
  if stored_file.id is null then
    raise exception 'Stored video file identity conflicts with another owner'
      using errcode = '23505';
  end if;

  update public.media_jobs as current_job
  set status = 'ready',
      video_phase = 'ready',
      lease_token = null,
      lease_expires_at = null,
      finalization_started_at = null,
      sweep_retry_after = '-infinity'::timestamptz,
      file_id = p_file_id,
      provider_asset_reference = nullif(
        left(trim(coalesce(p_provider_asset_reference, '')), 2000), ''
      ),
      provider_asset_expires_at = p_provider_asset_expires_at,
      error_message = null,
      metadata = (
        current_job.metadata
        - 'finalizationOutcome'
        - 'finalizationRefundEligible'
        - 'finalizationStartedAt'
        - 'finalizationExpiresAt'
      ) || jsonb_build_object(
        'videoPhase', 'ready',
        'providerCompleted', true,
        'refundEligible', false,
        'storedBytes', p_stored_bytes,
        'finalizedAt', to_jsonb(now())
      ),
      updated_at = now()
  where current_job.id = p_job_id
    and current_job.user_id = p_user_id
    and current_job.idempotency_key = normalized_key
    and current_job.request_fingerprint = normalized_fingerprint
    and current_job.video_phase = 'finalizing'
    and current_job.lease_token = finalization_token
  returning * into updated_row;
  if updated_row.id is null then
    raise exception 'Video finalization changed during completion'
      using errcode = '40001';
  end if;
  return query select 'completed'::text, to_jsonb(updated_row);
end;
$$;

create or replace function public.fail_video_finalization(
  p_user_id uuid,
  p_job_id uuid,
  p_idempotency_key text,
  p_request_fingerprint text,
  p_finalization_token text,
  p_message text,
  p_failure_code text,
  p_refund_eligible boolean
)
returns table(outcome text, job jsonb)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  updated_row public.media_jobs%rowtype;
  normalized_key text := trim(coalesce(p_idempotency_key, ''));
  normalized_fingerprint text := lower(trim(coalesce(p_request_fingerprint, '')));
  finalization_token uuid;
  event_id text;
  payment_source text;
  refunded boolean := false;
  refund_allowed boolean := false;
begin
  if p_user_id is null or p_job_id is null then
    raise exception 'Failed video finalization identity is required'
      using errcode = '22023';
  end if;
  if normalized_key = '' or length(normalized_key) > 160 then
    raise exception 'Video idempotency key is invalid' using errcode = '22023';
  end if;
  if normalized_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'Video request fingerprint is invalid' using errcode = '22023';
  end if;
  begin
    finalization_token := trim(coalesce(p_finalization_token, ''))::uuid;
  exception when invalid_text_representation then
    raise exception 'Video finalization token is invalid' using errcode = '22023';
  end;
  if finalization_token is null then
    raise exception 'Video finalization token is required' using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(
      'askcrump-video-owner-billing-v1:' || p_user_id::text,
      0
    )
  );

  if not pg_try_advisory_xact_lock(
    hashtextextended('video-finalization:' || p_job_id::text, 0)
  ) then
    return query select 'busy'::text, '{}'::jsonb;
    return;
  end if;
  select * into job_row
  from public.media_jobs as current_job
  where current_job.id = p_job_id and current_job.user_id = p_user_id
  for update skip locked;
  if not found then
    if exists (
      select 1 from public.media_jobs as visible_job
      where visible_job.id = p_job_id and visible_job.user_id = p_user_id
    ) then
      return query select 'busy'::text, '{}'::jsonb;
    else
      return query select 'missing'::text, '{}'::jsonb;
    end if;
    return;
  end if;
  if job_row.idempotency_key is distinct from normalized_key
     or job_row.request_fingerprint is distinct from normalized_fingerprint then
    return query select 'request_conflict'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.video_phase = 'failed' and job_row.status = 'failed' then
    return query select 'existing'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.video_phase <> 'finalizing'
     or job_row.status <> 'processing'
     or job_row.lease_token is distinct from finalization_token
  then
    return query select 'finalization_conflict'::text, to_jsonb(job_row);
    return;
  end if;
  if job_row.finalization_started_at <= now() - interval '1 hour'
     or job_row.lease_expires_at is null
     or job_row.lease_expires_at <= now() then
    return query select 'expired'::text, to_jsonb(job_row);
    return;
  end if;

  event_id := nullif(trim(coalesce(
    job_row.billing_receipt ->> 'eventId', ''
  )), '');
  payment_source := lower(trim(coalesce(
    job_row.billing_receipt ->> 'paymentSource', ''
  )));
  refund_allowed := coalesce(
    (job_row.metadata ->> 'finalizationRefundEligible')::boolean,
    true
  ) and coalesce(p_refund_eligible, true);
  if not job_row.billing_refunded then
    if payment_source = 'credits' then
      if coalesce(event_id, '') !~* (
        '^credit:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
        || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      ) then
        raise exception 'Failed video finalization credit receipt is invalid'
          using errcode = '22023';
      end if;
      if refund_allowed then
        perform 1 from public.refund_credit_spend(
          p_user_id,
          substring(event_id from 8)::uuid,
          jsonb_build_object(
            'reason', 'video_finalization_failed',
            'mediaJobId', p_job_id
          )
        );
        refunded := true;
      end if;
    elsif payment_source = 'included' then
      if coalesce(event_id, '') !~* (
        '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
        || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      ) then
        raise exception 'Failed video finalization usage receipt is invalid'
          using errcode = '22023';
      end if;
      if refund_allowed then
        delete from public.usage_events as usage
        where usage.id = event_id::uuid and usage.user_id = p_user_id;
        refunded := true;
      end if;
    elsif payment_source in ('internal', 'subscription')
          and event_id is null then
      refunded := false;
    else
      raise exception 'Failed video finalization payment source is invalid'
        using errcode = '22023';
    end if;
  end if;

  update public.media_jobs as current_job
  set status = 'failed',
      video_phase = 'failed',
      lease_token = null,
      lease_expires_at = null,
      finalization_started_at = null,
      sweep_retry_after = '-infinity'::timestamptz,
      error_message = left(
        coalesce(nullif(trim(p_message), ''), 'Video delivery failed.'),
        500
      ),
      billing_refunded = current_job.billing_refunded or refunded,
      metadata = (
        current_job.metadata
        - 'finalizationOutcome'
        - 'finalizationRefundEligible'
        - 'finalizationStartedAt'
        - 'finalizationExpiresAt'
      ) || jsonb_build_object(
        'videoPhase', 'failed',
        'providerCompleted',
          coalesce(job_row.metadata ->> 'finalizationOutcome', '') = 'ready',
        'providerAccepted', true,
        'providerAcceptance', 'confirmed',
        'providerFailureCode', left(coalesce(p_failure_code, ''), 120),
        'refundEligible', false,
        'finalizedAt', to_jsonb(now())
      ),
      updated_at = now()
  where current_job.id = p_job_id
    and current_job.user_id = p_user_id
    and current_job.idempotency_key = normalized_key
    and current_job.request_fingerprint = normalized_fingerprint
    and current_job.video_phase = 'finalizing'
    and current_job.lease_token = finalization_token
  returning * into updated_row;
  if updated_row.id is null then
    raise exception 'Video finalization changed during failure settlement'
      using errcode = '40001';
  end if;
  return query select 'failed'::text, to_jsonb(updated_row);
end;
$$;

create or replace function public.claim_video_reconciliation_batch(
  p_limit integer default 10,
  p_stale_seconds integer default 120,
  p_backoff_seconds integer default 600
)
returns table(
  id uuid,
  user_id uuid,
  video_phase text,
  lease_token uuid
)
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if coalesce(p_limit, 0) < 1 or p_limit > 25 then
    raise exception 'Video reconciliation batch size is invalid'
      using errcode = '22023';
  end if;
  if coalesce(p_stale_seconds, 0) < 60 or p_stale_seconds > 3600 then
    raise exception 'Video reconciliation stale window is invalid'
      using errcode = '22023';
  end if;
  if coalesce(p_backoff_seconds, 0) < 300 or p_backoff_seconds > 1800 then
    raise exception 'Video reconciliation backoff is invalid'
      using errcode = '22023';
  end if;

  return query
  with candidates as materialized (
    select candidate.id
    from public.media_jobs as candidate
    where candidate.kind = 'video'
      and candidate.status = 'processing'
      and candidate.sweep_retry_after <= now()
      and (
        (
          candidate.video_phase = 'finalizing'
          and candidate.lease_expires_at is not null
          and candidate.lease_expires_at <= now()
          and candidate.finalization_started_at > now() - interval '1 hour'
        )
        or (
          candidate.video_phase = 'processing'
          and candidate.updated_at
            <= now() - make_interval(secs => p_stale_seconds)
          and candidate.provider_started_at > now() - interval '24 hours'
        )
      )
    order by
      candidate.sweep_retry_after asc,
      coalesce(candidate.lease_expires_at, candidate.updated_at) asc,
      candidate.id asc
    for update skip locked
    limit p_limit
  ), claimed as (
    update public.media_jobs as current_job
    set sweep_retry_after = greatest(
          current_job.sweep_retry_after,
          least(
            now() + make_interval(secs => p_backoff_seconds),
            case current_job.video_phase
              when 'processing' then
                current_job.provider_started_at + interval '24 hours'
              else
                current_job.finalization_started_at + interval '1 hour'
            end
          )
        ),
        updated_at = now()
    from candidates
    where current_job.id = candidates.id
    returning current_job.id, current_job.user_id,
      current_job.video_phase, current_job.lease_token
  )
  select claimed.id, claimed.user_id, claimed.video_phase,
    claimed.lease_token
  from claimed;
end;
$$;

create or replace function public.sweep_expired_video_leases(
  p_limit integer default 100,
  p_user_id uuid default null,
  p_job_id uuid default null
)
returns table(
  outcome text,
  scanned integer,
  released integer,
  completed integer,
  failed integer,
  refunded integer,
  errors integer
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  job_row public.media_jobs%rowtype;
  stored_file public.user_files%rowtype;
  scanned_count integer := 0;
  released_count integer := 0;
  completed_count integer := 0;
  failed_count integer := 0;
  refunded_count integer := 0;
  error_count integer := 0;
  event_id text;
  payment_source text;
  refund_allowed boolean;
  refunded_this boolean;
  compatibility_recovery_settled boolean;
  failure_code text;
  failure_message text;
  provider_acceptance text;
  stored_asset_expires_at timestamptz;
begin
  if coalesce(p_limit, 0) < 1 or p_limit > 500 then
    raise exception 'Video sweep batch size is invalid' using errcode = '22023';
  end if;
  if p_job_id is not null and p_user_id is null then
    raise exception 'Exact video sweep requires an owner identity'
      using errcode = '22023';
  end if;
  if p_user_id is null then
    if not pg_try_advisory_xact_lock(
      hashtextextended('askcrump-video-lease-sweep-v1', 0)
    ) then
      return query select 'busy'::text, 0, 0, 0, 0, 0, 0;
      return;
    end if;
  else
    perform pg_advisory_xact_lock(
      hashtextextended(
        'askcrump-video-owner-billing-v1:' || p_user_id::text,
        0
      )
    );
  end if;

  for job_row in
    select candidate.*
    from public.media_jobs as candidate
    where candidate.kind = 'video'
      and (p_user_id is null or candidate.user_id = p_user_id)
      and (p_job_id is null or candidate.id = p_job_id)
      and (
        candidate.sweep_retry_after <= now()
        or (p_user_id is not null and p_job_id is null)
      )
      and (
        (
          candidate.video_phase in (
            'reserved_unbilled', 'ready_to_launch', 'launching', 'finalizing'
          )
          and candidate.lease_expires_at is not null
          and candidate.lease_expires_at <= now()
          and (
            candidate.video_phase <> 'finalizing'
            or candidate.finalization_started_at <= now() - interval '1 hour'
          )
        )
        or (
          candidate.video_phase = 'processing'
          and candidate.status = 'processing'
          and candidate.provider_started_at is not null
          and candidate.provider_started_at <= now() - interval '24 hours'
        )
        or (
          candidate.video_phase = 'failed'
          and candidate.status = 'failed'
          and not candidate.billing_refunded
          and candidate.billing_receipt <> '{}'::jsonb
          and coalesce(
            candidate.metadata ->> 'compatibilityOrigin', ''
          ) = 'pre-atomic'
          and (
            not (candidate.metadata ? 'refundEligible')
            or jsonb_typeof(candidate.metadata -> 'refundEligible')
              <> 'boolean'
            or candidate.metadata -> 'refundEligible' = 'true'::jsonb
          )
        )
      )
    order by
      candidate.sweep_retry_after asc,
      coalesce(
        candidate.lease_expires_at,
        candidate.provider_started_at,
        candidate.updated_at
      ) asc,
      candidate.id asc
    for update skip locked
    limit p_limit
  loop
    -- The unscoped cron locks candidate rows before their owner is known.
    -- Never wait while holding that row: an owner transaction may already
    -- hold the owner lock and be checking for skipped refundable work.
    if p_user_id is null and not pg_try_advisory_xact_lock(
      hashtextextended(
        'askcrump-video-owner-billing-v1:' || job_row.user_id::text,
        0
      )
    ) then
      continue;
    end if;
    scanned_count := scanned_count + 1;
    begin

    if job_row.video_phase = 'reserved_unbilled' then
      delete from public.media_jobs as current_job
      where current_job.id = job_row.id
        and current_job.user_id = job_row.user_id
        and current_job.idempotency_key = job_row.idempotency_key
        and current_job.request_fingerprint = job_row.request_fingerprint
        and current_job.video_phase = 'reserved_unbilled'
        and current_job.lease_token = job_row.lease_token
        and current_job.billing_receipt = '{}'::jsonb
        and current_job.lease_expires_at <= now();
      if found then
        released_count := released_count + 1;
      end if;
      continue;
    end if;

    -- A process may have stored the deterministic job-id file and crashed
    -- before binding it. Deliver that exact owner-scoped file instead of
    -- refunding and leaving an orphan.
    if job_row.video_phase = 'finalizing'
       and coalesce(job_row.metadata ->> 'finalizationOutcome', '') = 'ready'
    then
      select * into stored_file
      from public.user_files as candidate_file
      where candidate_file.id = job_row.id
        and candidate_file.user_id = job_row.user_id
        and candidate_file.kind = 'generated_video'
        and candidate_file.status = 'ready'
        and candidate_file.deleted_at is null;
      if found then
        stored_asset_expires_at := null;
        if nullif(
          stored_file.metadata ->> 'providerAssetExpiresAt', ''
        ) is not null then
          begin
            stored_asset_expires_at := (
              stored_file.metadata ->> 'providerAssetExpiresAt'
            )::timestamptz;
          exception
            when invalid_datetime_format or datetime_field_overflow then
              stored_asset_expires_at := null;
          end;
        end if;
        update public.media_jobs as current_job
        set status = 'ready',
            video_phase = 'ready',
            lease_token = null,
            lease_expires_at = null,
            finalization_started_at = null,
            sweep_retry_after = '-infinity'::timestamptz,
            file_id = stored_file.id,
            provider_asset_reference = nullif(
              stored_file.metadata ->> 'providerAssetReference', ''
            ),
            provider_asset_expires_at = stored_asset_expires_at,
            error_message = null,
            metadata = (
              current_job.metadata
              - 'finalizationOutcome'
              - 'finalizationRefundEligible'
              - 'finalizationStartedAt'
              - 'finalizationExpiresAt'
            ) || jsonb_build_object(
              'videoPhase', 'ready',
              'providerCompleted', true,
              'refundEligible', false,
              'storedBytes', stored_file.size_bytes,
              'finalizedAt', to_jsonb(now()),
              'finalizedBy', 'expired-lease-sweep'
            ),
            updated_at = now()
        where current_job.id = job_row.id
          and current_job.user_id = job_row.user_id
          and current_job.idempotency_key = job_row.idempotency_key
          and current_job.request_fingerprint = job_row.request_fingerprint
          and current_job.video_phase = 'finalizing'
          and current_job.lease_token = job_row.lease_token
          and current_job.lease_expires_at <= now()
          and current_job.finalization_started_at <= now() - interval '1 hour';
        if found then
          completed_count := completed_count + 1;
          continue;
        end if;
      end if;
    end if;

    event_id := nullif(job_row.billing_receipt ->> 'eventId', '');
    payment_source := coalesce(job_row.billing_receipt ->> 'paymentSource', '');
    if job_row.video_phase = 'failed'
       and job_row.metadata ? 'refundEligible'
       and jsonb_typeof(job_row.metadata -> 'refundEligible') <> 'boolean'
    then
      raise exception 'Compatibility video refund eligibility is invalid'
        using errcode = '22023';
    end if;
    refund_allowed := case
      when job_row.video_phase = 'finalizing' then coalesce(
        (job_row.metadata ->> 'finalizationRefundEligible')::boolean,
        true
      )
      when job_row.video_phase = 'failed' then coalesce(
        (job_row.metadata ->> 'refundEligible')::boolean,
        true
      )
      else true
    end;
    refunded_this := false;
    compatibility_recovery_settled := false;
    if refund_allowed
       and not job_row.billing_refunded
       and payment_source = 'credits' then
      if coalesce(event_id, '') !~* (
        '^credit:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
        || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      ) then
        raise exception 'Expired video credit receipt is invalid'
          using errcode = '22023';
      end if;
      perform 1 from public.refund_credit_spend(
        job_row.user_id,
        substring(event_id from 8)::uuid,
        jsonb_build_object(
          'reason', 'expired_video_lease',
          'mediaJobId', job_row.id,
          'videoPhase', job_row.video_phase
        )
      );
      refunded_this := true;
      compatibility_recovery_settled := job_row.video_phase = 'failed';
    elsif refund_allowed
          and not job_row.billing_refunded
          and payment_source = 'included' then
      if coalesce(event_id, '') !~* (
        '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
        || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      ) then
        raise exception 'Expired video usage receipt is invalid'
          using errcode = '22023';
      end if;
      delete from public.usage_events as usage
      where usage.id = event_id::uuid and usage.user_id = job_row.user_id;
      refunded_this := true;
      compatibility_recovery_settled := job_row.video_phase = 'failed';
    elsif refund_allowed
          and not job_row.billing_refunded
          and payment_source in ('internal', 'subscription')
          and event_id is null then
      compatibility_recovery_settled := job_row.video_phase = 'failed';
    elsif refund_allowed and not job_row.billing_refunded then
      raise exception 'Expired video payment source is invalid'
        using errcode = '22023';
    end if;

    failure_code := case job_row.video_phase
      when 'ready_to_launch' then 'VIDEO_PROVIDER_LAUNCH_NOT_STARTED'
      when 'launching' then 'VIDEO_PROVIDER_LAUNCH_UNCONFIRMED'
      when 'processing' then 'VIDEO_PROVIDER_PROCESSING_EXPIRED'
      when 'failed' then coalesce(
        nullif(job_row.metadata ->> 'providerFailureCode', ''),
        'VIDEO_COMPATIBILITY_REFUND_RECOVERED'
      )
      else 'VIDEO_FINALIZATION_EXPIRED'
    end;
    failure_message := case job_row.video_phase
      when 'ready_to_launch' then
        'Ask Crump could not start the provider before the safety window closed. No refundable charge remains.'
      when 'launching' then
        'Ask Crump could not confirm the provider launch. It was not retried, and no refundable charge remains.'
      when 'processing' then
        'The video provider did not finish within the 24-hour safety window. Ask Crump closed the job and returned any refundable allowance or credits.'
      when 'failed' then coalesce(
        nullif(job_row.error_message, ''),
        'Ask Crump recovered an interrupted refund for this failed video.'
      )
      else
        'Ask Crump could not finish binding the completed video before the recovery window closed. No refundable charge remains.'
    end;
    provider_acceptance := case job_row.video_phase
      when 'ready_to_launch' then 'not-started'
      when 'launching' then 'unknown'
      when 'failed' then coalesce(
        nullif(job_row.metadata ->> 'providerAcceptance', ''),
        case
          when job_row.provider_job_id like 'pending:%' then 'unknown'
          else 'confirmed'
        end
      )
      else 'confirmed'
    end;

    update public.media_jobs as current_job
    set status = 'failed',
        video_phase = 'failed',
        lease_token = null,
        lease_expires_at = null,
        finalization_started_at = null,
        sweep_retry_after = '-infinity'::timestamptz,
        error_message = failure_message,
        estimated_provider_cost_cents = case
          when job_row.video_phase = 'ready_to_launch' then 0
          else current_job.estimated_provider_cost_cents
        end,
        billing_refunded = case
          when job_row.video_phase = 'failed' then
            current_job.billing_refunded or compatibility_recovery_settled
          else current_job.billing_refunded or refunded_this
        end,
        metadata = (
          current_job.metadata
          - 'launchReadyExpiresAt'
          - 'launchToken'
          - 'launchExpiresAt'
          - 'finalizationOutcome'
          - 'finalizationRefundEligible'
          - 'finalizationStartedAt'
          - 'finalizationExpiresAt'
        ) || jsonb_build_object(
          'videoPhase', 'failed',
          'providerAccepted', provider_acceptance = 'confirmed',
          'providerAcceptance', provider_acceptance,
          'providerFailureCode', failure_code,
          'refundEligible', false,
          'settledBy', 'expired-lease-sweep'
        ),
        updated_at = now()
    where current_job.id = job_row.id
      and current_job.user_id = job_row.user_id
      and current_job.idempotency_key = job_row.idempotency_key
      and current_job.request_fingerprint = job_row.request_fingerprint
      and current_job.video_phase = job_row.video_phase
      and current_job.lease_token is not distinct from job_row.lease_token
      and (
        current_job.sweep_retry_after <= now()
        or (p_user_id is not null and p_job_id is null)
      )
      and (
        (
          job_row.video_phase = 'processing'
          and current_job.video_phase = 'processing'
          and current_job.provider_started_at is not null
          and current_job.provider_started_at <= now() - interval '24 hours'
        )
        or (
          job_row.video_phase <> 'processing'
          and job_row.video_phase <> 'failed'
          and current_job.lease_expires_at <= now()
          and (
            current_job.video_phase <> 'finalizing'
            or current_job.finalization_started_at <= now() - interval '1 hour'
          )
        )
        or (
          job_row.video_phase = 'failed'
          and current_job.video_phase = 'failed'
          and current_job.status = 'failed'
          and not current_job.billing_refunded
          and current_job.billing_receipt <> '{}'::jsonb
            and coalesce(
              current_job.metadata ->> 'compatibilityOrigin', ''
            ) = 'pre-atomic'
            and (
              not (current_job.metadata ? 'refundEligible')
              or jsonb_typeof(current_job.metadata -> 'refundEligible')
                <> 'boolean'
              or current_job.metadata -> 'refundEligible' = 'true'::jsonb
            )
        )
      );
    if found then
      failed_count := failed_count + 1;
      if refunded_this then
        refunded_count := refunded_count + 1;
      end if;
    end if;
    exception when others then
      -- One malformed legacy/corrupt row must not roll back and starve the
      -- entire oldest-first batch forever. Quarantine only the exact fenced
      -- row for a bounded review window and return a content-free error count.
      error_count := error_count + 1;
      update public.media_jobs as current_job
      set sweep_retry_after = now() + interval '24 hours',
          metadata = current_job.metadata || jsonb_build_object(
            'sweepNeedsReview', true,
            'sweepRetryAfter', to_jsonb(now() + interval '24 hours')
          ),
          updated_at = now()
      where current_job.id = job_row.id
        and current_job.user_id = job_row.user_id
        and current_job.video_phase = job_row.video_phase
        and current_job.lease_token is not distinct from job_row.lease_token
        and (
          current_job.sweep_retry_after <= now()
          or (p_user_id is not null and p_job_id is null)
        )
        and (
          (
            job_row.video_phase = 'processing'
            and current_job.provider_started_at is not null
            and current_job.provider_started_at <= now() - interval '24 hours'
          )
          or (
            job_row.video_phase <> 'processing'
            and job_row.video_phase <> 'failed'
            and current_job.lease_expires_at <= now()
            and (
              current_job.video_phase <> 'finalizing'
              or current_job.finalization_started_at
                <= now() - interval '1 hour'
            )
          )
          or (
            job_row.video_phase = 'failed'
            and current_job.status = 'failed'
            and not current_job.billing_refunded
            and current_job.billing_receipt <> '{}'::jsonb
            and coalesce(
              current_job.metadata ->> 'compatibilityOrigin', ''
            ) = 'pre-atomic'
            and (
              not (current_job.metadata ? 'refundEligible')
              or jsonb_typeof(current_job.metadata -> 'refundEligible')
                <> 'boolean'
              or current_job.metadata -> 'refundEligible' = 'true'::jsonb
            )
          )
        );
    end;
  end loop;

  -- A scoped owner settlement is the decisive prebilling barrier. SKIP
  -- LOCKED prevents a deadlock with an old application write that obtained a
  -- row lock before this migration's trigger requested the owner lock. If any
  -- eligible row was skipped (or remains quarantined), fail closed so the
  -- caller cannot consume credits against stale allowance state.
  if p_user_id is not null
     and p_job_id is null
     and exists (
       select 1
       from public.media_jobs as remaining
       where remaining.kind = 'video'
         and remaining.user_id = p_user_id
         and (
           (
             remaining.video_phase in (
               'reserved_unbilled', 'ready_to_launch', 'launching', 'finalizing'
             )
             and remaining.lease_expires_at is not null
             and remaining.lease_expires_at <= now()
             and (
               remaining.video_phase <> 'finalizing'
               or remaining.finalization_started_at
                 <= now() - interval '1 hour'
             )
           )
           or (
             remaining.video_phase = 'processing'
             and remaining.status = 'processing'
             and remaining.provider_started_at is not null
             and remaining.provider_started_at
               <= now() - interval '24 hours'
           )
           or (
             remaining.video_phase = 'failed'
             and remaining.status = 'failed'
             and not remaining.billing_refunded
             and remaining.billing_receipt <> '{}'::jsonb
             and coalesce(
               remaining.metadata ->> 'compatibilityOrigin', ''
             ) = 'pre-atomic'
             and (
               not (remaining.metadata ? 'refundEligible')
               or jsonb_typeof(remaining.metadata -> 'refundEligible')
                 <> 'boolean'
               or remaining.metadata -> 'refundEligible' = 'true'::jsonb
             )
           )
         )
     )
  then
    return query select 'pending'::text, scanned_count, released_count,
      completed_count, failed_count, refunded_count, error_count;
    return;
  end if;

  return query select 'completed'::text, scanned_count, released_count,
    completed_count, failed_count, refunded_count, error_count;
end;
$$;

revoke all on function public.authorize_video_reservation_capacity(
  uuid, uuid, text, text, text, integer, integer, integer, integer, boolean
) from public, anon, authenticated;
grant execute on function public.authorize_video_reservation_capacity(
  uuid, uuid, text, text, text, integer, integer, integer, integer, boolean
) to service_role;

revoke all on function public.consume_video_reservation(
  uuid, uuid, text, text, text, text, text, text, integer, integer,
  text, text, text, integer, integer, jsonb
) from public, anon, authenticated;
grant execute on function public.consume_video_reservation(
  uuid, uuid, text, text, text, text, text, text, integer, integer,
  text, text, text, integer, integer, jsonb
) to service_role;

revoke all on function public.claim_video_provider_launch(
  uuid, uuid, text, text, text, integer, boolean
) from public, anon, authenticated;
grant execute on function public.claim_video_provider_launch(
  uuid, uuid, text, text, text, integer, boolean
) to service_role;

revoke all on function public.release_video_reservation(
  uuid, uuid, text, text, text, text
) from public, anon, authenticated;
grant execute on function public.release_video_reservation(
  uuid, uuid, text, text, text, text
) to service_role;

revoke all on function public.complete_video_provider_launch(
  uuid, uuid, text, text, text, text
) from public, anon, authenticated;
grant execute on function public.complete_video_provider_launch(
  uuid, uuid, text, text, text, text
) to service_role;

revoke all on function public.fail_video_provider_launch(
  uuid, uuid, text, text, text, text, text, boolean, text
) from public, anon, authenticated;
grant execute on function public.fail_video_provider_launch(
  uuid, uuid, text, text, text, text, text, boolean, text
) to service_role;

revoke all on function public.claim_video_finalization(
  uuid, uuid, text, text, text, integer, text, boolean
) from public, anon, authenticated;
grant execute on function public.claim_video_finalization(
  uuid, uuid, text, text, text, integer, text, boolean
) to service_role;

revoke all on function public.complete_video_finalization(
  uuid, uuid, text, text, text, uuid, text, timestamptz, bigint, jsonb
) from public, anon, authenticated;
grant execute on function public.complete_video_finalization(
  uuid, uuid, text, text, text, uuid, text, timestamptz, bigint, jsonb
) to service_role;

revoke all on function public.fail_video_finalization(
  uuid, uuid, text, text, text, text, text, boolean
) from public, anon, authenticated;
grant execute on function public.fail_video_finalization(
  uuid, uuid, text, text, text, text, text, boolean
) to service_role;

revoke all on function public.claim_video_reconciliation_batch(
  integer, integer, integer
)
  from public, anon, authenticated;
grant execute on function public.claim_video_reconciliation_batch(
  integer, integer, integer
)
  to service_role;

revoke all on function public.sweep_expired_video_leases(integer, uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.sweep_expired_video_leases(integer, uuid, uuid)
  to service_role;

comment on function public.authorize_video_reservation_capacity(
  uuid, uuid, text, text, text, integer, integer, integer, integer, boolean
) is 'Service-role-only serialized active-job and provider-budget authorization before video billing.';

comment on function public.consume_video_reservation(
  uuid, uuid, text, text, text, text, text, text, integer, integer,
  text, text, text, integer, integer, jsonb
) is 'Service-role-only atomic video allowance/credit consumption and receipt binding.';
comment on function public.claim_video_provider_launch(
  uuid, uuid, text, text, text, integer, boolean
) is 'Service-role-only video launch lease; expired ambiguous launches fail and refund without relaunch.';
comment on function public.release_video_reservation(
  uuid, uuid, text, text, text, text
) is 'Service-role-only token-conditional deletion of an unbilled video reservation.';
comment on function public.complete_video_provider_launch(
  uuid, uuid, text, text, text, text
) is 'Service-role-only idempotent provider task binding after video launch acceptance.';
comment on function public.fail_video_provider_launch(
  uuid, uuid, text, text, text, text, text, boolean, text
) is 'Service-role-only terminal provider launch failure with atomic idempotent customer refund.';
comment on function public.claim_video_finalization(
  uuid, uuid, text, text, text, integer, text, boolean
) is 'Service-role-only renewable terminal-result lease preventing concurrent video file finalization.';
comment on function public.complete_video_finalization(
  uuid, uuid, text, text, text, uuid, text, timestamptz, bigint, jsonb
) is 'Service-role-only token-fenced atomic publication and job binding of one deterministic generated-video file.';
comment on function public.fail_video_finalization(
  uuid, uuid, text, text, text, text, text, boolean
) is 'Service-role-only token-fenced finalization failure with atomic idempotent customer refund.';
comment on function public.claim_video_reconciliation_batch(
  integer, integer, integer
) is
  'Service-role-only atomic, skip-locked claim of content-free video reconciliation identities with monotonic retry spacing.';
comment on function public.sweep_expired_video_leases(integer, uuid, uuid) is
  'Service-role-only bounded lease settlement; never starts or retries a provider job.';

comment on column public.media_jobs.request_fingerprint is
  'Lowercase 64-hex immutable request identity: SHA-256 for atomic requests, or a content-free row-UUID fence for tagged pre-atomic compatibility rows.';
comment on column public.media_jobs.video_phase is
  'Authoritative durable phase for video billing, provider launch, and file-finalization recovery.';
comment on column public.media_jobs.lease_token is
  'Authoritative reservation, provider-launch, or file-finalization fencing token.';
comment on column public.media_jobs.lease_expires_at is
  'Authoritative deadline for the current reservation, launch, or file-finalization phase.';
comment on column public.media_jobs.provider_started_at is
  'Immutable database-owned start of provider processing and its absolute 24-hour safety horizon.';
comment on column public.media_jobs.sweep_retry_after is
  'Monotonic scheduling/quarantine boundary for protected background reconciliation.';

commit;
