-- Ask Crump 5.8.4
-- Add a privacy-safe response-sharing milestone without storing response content.

begin;

alter table public.product_events
  drop constraint if exists product_events_event_name_check;

alter table public.product_events
  add constraint product_events_event_name_check check (event_name in (
    'AccountCreated',
    'OnboardingCompleted',
    'WorkspaceOpened',
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
