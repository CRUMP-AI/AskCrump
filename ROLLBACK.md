# Rollback

The revamp is designed as a repository overlay and does not alter the database.

If a production problem appears after deployment:

1. In GitHub, revert the single `Ask Crump V1 interface revamp` commit.
2. Let Vercel redeploy the reverted commit.
3. Open a new browser tab / relaunch the PWA so the previous shell service worker can activate.

Do **not** roll back Supabase, Stripe, or user data for a presentation-layer issue.
The V1 package contains no database migration and no environment-variable changes.
