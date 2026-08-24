-- Ask Crump 5.9.8
-- Measure the first authenticated launchpad choice without storing user content.

begin;

alter table public.product_events
  drop constraint if exists product_events_event_name_check;

alter table public.product_events
  add constraint product_events_event_name_check check (event_name in (
    'AccountCreated',
    'OnboardingCompleted',
    'WorkspaceOpened',
    'StarterIntentReached',
    'ActivationReached',
    'AhaReached',
    'PlanIntentReached',
    'ResponseShared',
    'SubscriptionCheckoutOpened',
    'SubscriptionCheckoutCompleted',
    'BillingPortalOpened',
    'SubscriptionStatusChanged'
  ));

comment on table public.product_events is
  'Server-only, allowlisted product milestones. No prompts, responses, filenames, emails, payment details, or arbitrary metadata. Deleted with the owning account.';

commit;
