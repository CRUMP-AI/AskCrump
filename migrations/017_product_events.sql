-- Ask Crump 5.8.2
-- Privacy-minimized, server-only product funnel milestones.

begin;

create table if not exists public.product_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  event_name text not null check (event_name in (
    'AccountCreated',
    'OnboardingCompleted',
    'WorkspaceOpened',
    'ActivationReached',
    'AhaReached',
    'PlanIntentReached',
    'SubscriptionCheckoutOpened',
    'SubscriptionCheckoutCompleted',
    'BillingPortalOpened',
    'SubscriptionStatusChanged'
  )),
  event_key text not null check (
    char_length(event_key) between 1 and 160
    and event_key ~ '^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$'
  ),
  environment text not null check (environment in ('production', 'preview', 'development')),
  client_platform text not null check (client_platform in ('web', 'ios', 'android')),
  source text check (
    source is null
    or (char_length(source) between 1 and 32 and source ~ '^[a-z0-9_-]{1,32}$')
  ),
  plan text check (plan is null or plan in ('professional', 'enterprise')),
  artifact_type text check (artifact_type is null or artifact_type in (
    'document', 'image', 'video', 'manuscript', 'code',
    'spreadsheet', 'presentation', 'pdf', 'project', 'file'
  )),
  created_at timestamptz not null default now(),
  unique (user_id, event_name, event_key, environment)
);

create index if not exists product_events_funnel_idx
  on public.product_events(environment, event_name, created_at desc);
create index if not exists product_events_user_journey_idx
  on public.product_events(user_id, created_at asc);

alter table public.product_events enable row level security;
revoke all on table public.product_events from public, anon, authenticated;
grant all on table public.product_events to service_role;

comment on table public.product_events is
  'Server-only, allowlisted product milestones. No prompts, filenames, emails, payment details, or arbitrary metadata. Deleted with the owning account.';

create or replace function public.record_product_event(
  p_user_id uuid,
  p_event_name text,
  p_event_key text,
  p_environment text,
  p_client_platform text,
  p_source text default null,
  p_plan text default null,
  p_artifact_type text default null
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.product_events (
    user_id,
    event_name,
    event_key,
    environment,
    client_platform,
    source,
    plan,
    artifact_type
  ) values (
    p_user_id,
    p_event_name,
    p_event_key,
    p_environment,
    p_client_platform,
    p_source,
    p_plan,
    p_artifact_type
  )
  on conflict (user_id, event_name, event_key, environment) do nothing;

  return found;
end;
$$;

revoke all on function public.record_product_event(uuid, text, text, text, text, text, text, text)
  from public, anon, authenticated;
grant execute on function public.record_product_event(uuid, text, text, text, text, text, text, text)
  to service_role;

comment on function public.record_product_event(uuid, text, text, text, text, text, text, text) is
  'Idempotently records one allowlisted product milestone through the server service role.';

commit;
