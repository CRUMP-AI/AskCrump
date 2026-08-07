# Ask Crump 5.2.2 verification

1. Open Plan & credits.
2. Tap the 50-credit card or its Add credits button.
3. Expected: a POST to `/api/billing/credits/checkout`, then Stripe Checkout. Do not complete a real payment during smoke testing.
4. Send a prompt that produces a long answer.
5. Expected: when Crump's reply arrives, the top of the new reply is placed near the top of the reading area exactly once.
6. Read and scroll normally.
7. Expected: no repeated micro-jumps or bottom chasing.
8. Scroll upward until the newest-message button appears.
9. Expected: button is clearly visible with a gold surface and dark arrow.
10. Tap it.
11. Expected: one immediate jump to the newest content.
