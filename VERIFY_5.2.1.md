# Ask Crump 5.2.1 Verification

1. Upload the same EDEN DOCX and send a short message such as `👀` or `Can you read this?`.
   - Expected: Crump acknowledges and uses the manuscript rather than claiming no attachment exists.
   - Expected: the DOCX card remains in the conversation after refresh.

2. Open Plan & credits and tap anywhere on the 50-credit card or its Add credits button.
   - Expected: Ask Crump sends POST /api/billing/credits/checkout.
   - Expected: Safari navigates to Stripe Checkout showing the 50-credit product and $4.99.
   - Stop before completing payment for the smoke test.

3. Recheck a normal text conversation, image upload, and generated DOCX to ensure no regression.
