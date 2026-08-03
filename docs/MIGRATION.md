# Migration Notes

## Scope

The current architecture replaces multiple client and server storage paths with one FastAPI backend and one Supabase conversation model.

## Session migration

Legacy session credentials are not converted. Existing users sign in once after deployment and receive a new opaque session credential. Normal activity then renews the session according to `SESSION_DAYS`.

## Conversation identifiers

Non-UUID conversation identifiers are mapped deterministically during migration. This preserves stable identity across repeated migration runs and prevents duplicate copies of the same legacy conversation.

## Client cache

Legacy browser cache data is imported only when the stored owner can be matched to the authenticated account. New cache keys include the user identifier. Device cache is never treated as proof of account ownership.

## Rollback

Before production migration:

1. capture a Supabase backup;
2. retain legacy tables;
3. record the deployed commit and environment configuration;
4. validate representative accounts in staging;
5. define the traffic rollback process in Vercel.

A rollback should restore the application deployment and database state together. Do not point the legacy application at a partially migrated schema.
