# Ask Crump 5.8.0

## Revenue conversion foundation

Ask Crump already had working Stripe-hosted subscriptions, durable Crump Credits, and a customer billing portal. This release makes that business model legible to prospective customers and removes the largest activation detour.

### Customer-facing improvements

- Transparent Free, Professional, Enterprise, and credit-pack pricing on the Clever Crump site.
- “Start free” calls to action that open account creation directly, with no card required.
- Current, confident product language and a 5.8 release presentation.
- Responsive pricing cards and credit-pack disclosure designed for desktop and mobile.

### Measurement

- First-party Vercel Web Analytics page views.
- Non-PII events for marketing CTA clicks, signup intent, signup submission, and account creation.
- Source and plan-intent properties are restricted to short, sanitized labels.

### Safety

- Live Stripe Checkout creation and purchases were not invoked during verification.
- Existing hosted Checkout, customer portal, dynamic payment-method behavior, and webhook signature verification remain unchanged.
