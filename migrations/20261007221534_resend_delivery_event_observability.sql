-- Ask Crump 5.9.76
-- Signed, idempotent, content-free Resend delivery-event observability.
-- Raw webhook bodies, provider IDs, recipient addresses, subjects, message
-- content, URLs, tokens, headers, IP addresses, and arbitrary metadata are
-- intentionally excluded.

begin;

set local lock_timeout = '5s';

-- Keep raw operational receipts outside the exposed Data API schema. Public
-- contains only the two explicitly granted service-role RPCs below.
create schema if not exists private;
revoke all on schema private from public, anon, authenticated, service_role;

create table if not exists private.resend_delivery_events (
  provider_event_hash text primary key,
  provider_email_hash text not null,
  payload_fingerprint text not null unique,
  environment text not null,
  message_kind text not null,
  event_type text not null,
  outcome_class text not null,
  occurred_at timestamptz not null,
  received_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint resend_delivery_events_provider_event_hash_check check (
    provider_event_hash ~ '^[0-9a-f]{64}$'
  ),
  constraint resend_delivery_events_provider_email_hash_check check (
    provider_email_hash ~ '^[0-9a-f]{64}$'
  ),
  constraint resend_delivery_events_payload_fingerprint_check check (
    payload_fingerprint ~ '^[0-9a-f]{64}$'
  ),
  constraint resend_delivery_events_environment_check check (
    environment in ('production', 'preview', 'development', 'test')
  ),
  constraint resend_delivery_events_message_kind_check check (
    message_kind in ('verification', 'password_reset')
  ),
  constraint resend_delivery_events_event_type_check check (
    event_type in (
      'email.sent',
      'email.delivered',
      'email.delivery_delayed',
      'email.bounced',
      'email.failed',
      'email.suppressed',
      'email.complained'
    )
  ),
  constraint resend_delivery_events_outcome_class_check check (
    outcome_class in (
      'accepted', 'delivered', 'transient', 'permanent',
      'failed', 'suppressed', 'complaint'
    )
  ),
  constraint resend_delivery_events_event_outcome_pair_check check (
    (event_type = 'email.sent' and outcome_class = 'accepted')
    or (event_type = 'email.delivered' and outcome_class = 'delivered')
    or (event_type = 'email.delivery_delayed' and outcome_class = 'transient')
    or (
      event_type = 'email.bounced'
      and outcome_class in ('permanent', 'transient', 'failed')
    )
    or (event_type = 'email.failed' and outcome_class = 'failed')
    or (event_type = 'email.suppressed' and outcome_class = 'suppressed')
    or (event_type = 'email.complained' and outcome_class = 'complaint')
  ),
  constraint resend_delivery_events_occurred_at_check check (
    occurred_at <= received_at + interval '10 minutes'
  )
);

create index if not exists resend_delivery_events_window_idx
  on private.resend_delivery_events (environment, occurred_at, message_kind)
  include (event_type, provider_email_hash);

alter table private.resend_delivery_events enable row level security;
alter table private.resend_delivery_events force row level security;
revoke all on table private.resend_delivery_events
  from public, anon, authenticated, service_role;

comment on table private.resend_delivery_events is
  'Content-free, account-unlinked Resend delivery events. Stores only lowercase SHA-256 fingerprints and allowlisted operational labels; no raw provider IDs, recipient hash/address, subject, body, URL, token, header, IP address, or webhook payload.';
comment on column private.resend_delivery_events.provider_event_hash is
  'Lowercase SHA-256 of the verified Svix event ID; never the raw provider event ID.';
comment on column private.resend_delivery_events.provider_email_hash is
  'Lowercase SHA-256 of the Resend email ID; never an address or recipient-derived hash.';
comment on column private.resend_delivery_events.payload_fingerprint is
  'Lowercase SHA-256 of the signature-verified raw request bytes; the bytes are never stored.';

create or replace function public.record_resend_delivery_event(
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
begin
  if coalesce(p_provider_event_hash, '') !~ '^[0-9a-f]{64}$'
     or coalesce(p_provider_email_hash, '') !~ '^[0-9a-f]{64}$'
     or coalesce(p_payload_fingerprint, '') !~ '^[0-9a-f]{64}$'
  then
    raise exception 'Invalid Resend event fingerprint.' using errcode = '22023';
  end if;

  if coalesce(p_environment, '') not in (
    'production', 'preview', 'development', 'test'
  ) then
    raise exception 'Invalid Resend event environment.' using errcode = '22023';
  end if;

  if coalesce(p_message_kind, '') not in ('verification', 'password_reset') then
    raise exception 'Invalid Resend message kind.' using errcode = '22023';
  end if;

  if not coalesce((
    (p_event_type = 'email.sent' and p_outcome_class = 'accepted')
    or (p_event_type = 'email.delivered' and p_outcome_class = 'delivered')
    or (
      p_event_type = 'email.delivery_delayed'
      and p_outcome_class = 'transient'
    )
    or (
      p_event_type = 'email.bounced'
      and p_outcome_class in ('permanent', 'transient', 'failed')
    )
    or (p_event_type = 'email.failed' and p_outcome_class = 'failed')
    or (p_event_type = 'email.suppressed' and p_outcome_class = 'suppressed')
    or (p_event_type = 'email.complained' and p_outcome_class = 'complaint')
  ), false) then
    raise exception 'Invalid Resend event outcome.' using errcode = '22023';
  end if;

  if p_occurred_at is null
     or p_occurred_at > pg_catalog.clock_timestamp() + interval '10 minutes'
  then
    raise exception 'Invalid Resend event timestamp.' using errcode = '22023';
  end if;

  insert into private.resend_delivery_events (
    provider_event_hash,
    provider_email_hash,
    payload_fingerprint,
    environment,
    message_kind,
    event_type,
    outcome_class,
    occurred_at
  ) values (
    p_provider_event_hash,
    p_provider_email_hash,
    p_payload_fingerprint,
    p_environment,
    p_message_kind,
    p_event_type,
    p_outcome_class,
    p_occurred_at
  )
  on conflict do nothing;

  if found then
    return true;
  end if;

  -- Automatic retries and manual provider replays are success-equivalent only
  -- when the signed payload fingerprint and every normalized field agree. A
  -- reused event ID with changed payload/semantics fails closed.
  if exists (
    select 1
    from private.resend_delivery_events as existing
    where (
      existing.provider_event_hash = p_provider_event_hash
      or existing.payload_fingerprint = p_payload_fingerprint
    )
      and not (
        existing.payload_fingerprint = p_payload_fingerprint
        and existing.provider_email_hash = p_provider_email_hash
        and existing.environment = p_environment
        and existing.message_kind = p_message_kind
        and existing.event_type = p_event_type
        and existing.outcome_class = p_outcome_class
        and existing.occurred_at = p_occurred_at
      )
  ) then
    raise exception 'Resend event replay mismatch.' using errcode = '22023';
  end if;

  return false;
end;
$function$;

create or replace function public.resend_delivery_event_aggregate(
  p_since timestamptz,
  p_until timestamptz,
  p_environment text default 'production'
)
returns table (
  message_kind text,
  provider_events bigint,
  provider_messages bigint,
  sent_messages bigint,
  delivered_messages bigint,
  delivery_delayed_messages bigint,
  bounced_messages bigint,
  failed_messages bigint,
  suppressed_messages bigint,
  complained_messages bigint
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if p_since is null or p_until is null or p_since >= p_until then
    raise exception 'A valid half-open reporting window is required.'
      using errcode = '22023';
  end if;

  if coalesce(p_environment, '') not in (
    'production', 'preview', 'development', 'test'
  ) then
    raise exception 'Invalid Resend event environment.' using errcode = '22023';
  end if;

  return query
  with message_kinds(message_kind) as (
    values ('verification'::text), ('password_reset'::text)
  ),
  scoped as (
    select events.*
    from private.resend_delivery_events as events
    where events.environment = p_environment
      and events.occurred_at >= p_since
      and events.occurred_at < p_until
  )
  select
    kinds.message_kind,
    count(scoped.provider_event_hash)::bigint,
    count(distinct scoped.provider_email_hash)::bigint,
    count(distinct scoped.provider_email_hash)
      filter (where scoped.event_type = 'email.sent')::bigint,
    count(distinct scoped.provider_email_hash)
      filter (where scoped.event_type = 'email.delivered')::bigint,
    count(distinct scoped.provider_email_hash)
      filter (where scoped.event_type = 'email.delivery_delayed')::bigint,
    count(distinct scoped.provider_email_hash)
      filter (where scoped.event_type = 'email.bounced')::bigint,
    count(distinct scoped.provider_email_hash)
      filter (where scoped.event_type = 'email.failed')::bigint,
    count(distinct scoped.provider_email_hash)
      filter (where scoped.event_type = 'email.suppressed')::bigint,
    count(distinct scoped.provider_email_hash)
      filter (where scoped.event_type = 'email.complained')::bigint
  from message_kinds as kinds
  left join scoped on scoped.message_kind = kinds.message_kind
  group by kinds.message_kind
  order by kinds.message_kind;
end;
$function$;

revoke all on function public.record_resend_delivery_event(
  text, text, text, text, text, text, text, timestamptz
) from public, anon, authenticated, service_role;
revoke all on function public.resend_delivery_event_aggregate(
  timestamptz, timestamptz, text
) from public, anon, authenticated, service_role;

grant execute on function public.record_resend_delivery_event(
  text, text, text, text, text, text, text, timestamptz
) to service_role;
grant execute on function public.resend_delivery_event_aggregate(
  timestamptz, timestamptz, text
) to service_role;

comment on function public.record_resend_delivery_event(
  text, text, text, text, text, text, text, timestamptz
) is
  'Service-role-only idempotent insert for a signature-verified, content-free Resend delivery event. Returns true only for a newly stored event.';
comment on function public.resend_delivery_event_aggregate(
  timestamptz, timestamptz, text
) is
  'Service-role-only half-open Resend delivery aggregate. Returns counts by allowlisted message kind and never identifiers or customer content.';

commit;
