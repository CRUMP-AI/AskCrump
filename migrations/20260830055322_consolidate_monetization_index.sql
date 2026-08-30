-- Ask Crump 5.9.76
-- Replace overlapping Plan-conversion indexes with one covering index for
-- subscription, credit, and recovery reporting.

begin;

drop index if exists public.product_events_monetization_recovery_idx;
drop index if exists public.product_events_plan_conversion_idx;

create index product_events_plan_conversion_idx
  on public.product_events(environment, event_name, user_id, created_at)
  include (source)
  where event_name in (
    'PlanCenterViewed',
    'SubscriptionCheckoutOpened',
    'SubscriptionCheckoutCompleted',
    'CreditCheckoutOpened',
    'CreditCheckoutCompleted'
  );

commit;
