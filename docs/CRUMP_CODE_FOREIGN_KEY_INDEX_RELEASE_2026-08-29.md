# Crump Code foreign-key index release

Date: 2026-08-29  
Behavior commit: `9a7b482`  
Production deployment: `dpl_3qWoBXYnzpxUzv8ACDytxEY2FVyR`  
Supabase migration: `20260829223925 code_task_foreign_key_indexes`

## Accountable outcome

Project and account cleanup can use bounded index lookups across the append-only Crump Code event
and approval ledgers as those tables grow. The release adds one narrow index for each independent
`user_id` and `project_id` foreign key on `code_task_events` and `code_task_approvals`.

The existing task-first indexes remain responsible for task-history reads. No table, row-level
security rule, grant, API, entitlement, price, provider, credit rule, analytics event, or customer
record changed.

## Evidence that selected the work

The trailing production error review found no current customer-facing non-success defect. The two
404s were automated requests for `/.git/config`; the 401 and 422 were deliberate read-only probes;
and the three manuscript 503s belonged to an older deployment already corrected by the replay-safe
claim release. The minute manuscript schedule remains necessary because one invocation advances at
most one provider call or durable step.

Supabase's advisors contained no warning or error. Its only actionable deterministic finding was
four informational [unindexed foreign-key notices](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys),
all on Crump Code's ownership references. Those missing indexes would otherwise make a future
cascading Project or account deletion scan the complete audit tables.

## Security boundary

- All 35 public tables have row-level security enabled.
- All 35 intentionally have no client policy because the authenticated API is the sole database
  gateway.
- None grants `SELECT`, `INSERT`, `UPDATE`, or `DELETE` directly to `anon` or `authenticated`.
- The lone public view grants neither browser role direct read access.
- No production account, Project, code task, event, approval, message, artifact, payment, checkout,
  or synthetic analytics event was created for verification.

## Verification

- All 484 Python tests passed.
- All 45 JavaScript files passed the repository validation contract.
- Production preflight passed.
- The native web bundle regenerated successfully.
- Store metadata source checks passed.
- Supabase migration `20260829223925` applied successfully.
- Exact catalog inspection found all four expected btree indexes.
- The post-migration performance advisor reports zero unindexed foreign keys.
- Security advisors remain informational only, with no warning or error.
- Deployment `dpl_3qWoBXYnzpxUzv8ACDytxEY2FVyR` reached `READY` for `main` commit `9a7b482`.
- The canonical health endpoint returned HTTP 200 with service `Ask Crump` and version `5.9.76`.
- The initial release window contained no runtime error cluster.

## Observation boundary

The 47 remaining `unused_index` notices are informational and now include the four new indexes.
Do not remove indexes from a young, low-traffic schema without a representative workload window.
Reassess index usage after material Crump Code traffic or when table growth makes write overhead
measurable; preserve ownership and cascade indexes unless query and constraint evidence supports a
different covering index.
