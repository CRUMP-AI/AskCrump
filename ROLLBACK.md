# Rollback — Ask Crump V1 New Body

This release is a frontend overlay. It contains no Supabase migration and does not alter Stripe secrets, environment variables, or stored user data.

If a production regression appears after deployment:

1. Revert the single `Rebuild Ask Crump V1 application body` commit in GitHub.
2. Allow Vercel to redeploy the reverted commit.
3. Relaunch the PWA / open a new browser tab so the previous service worker can reclaim the shell.
4. Do not roll back Supabase or payment data for a presentation-layer regression.
