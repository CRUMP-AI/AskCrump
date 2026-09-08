# Lifecycle durable facts and demo-readiness release

Released: 2026-09-08  
Product commits: `6c31ddd`, `a7a3e05`  
Supabase migrations: `20260908131528`, `20260908131539`  
Production deployment: `dpl_H1htU5WaxH3yFgzozF4vffsBAZuo`

## Outcome

Ask Crump now uses durable, content-free product facts when deciding whether an
in-product lifecycle guide is still useful. A successfully completed chat job can
establish first value even if its best-effort analytics write was missed; a ready,
nonempty generated file can establish an artifact; and actual Project attachments
can establish durable continuity. An empty Project shell does not count as completed
continuity.

The server also rechecks the selected lifecycle message family's control immediately
before it records `shown`. A missing or disabled control fails closed with the existing
`channel-disabled` reason, so a still-live decision cannot appear after an operator
turns that family off.

The internal demo-account utility now supports a read-only `--require-ready` release
gate. It exits unsuccessfully when the protected account is not recording-ready and
names missing operator environment variables without exposing values. It remains
read-only unless `--replace` is explicitly supplied.

## Truth and privacy boundaries

- No lifecycle copy, ordering, frequency cap, 20% account-stable holdout, consent,
  email, push, price, entitlement, or client payload changed.
- No table or policy was created or altered. The migrations replace three existing
  app-owned functions only.
- `lifecycle_prompt_facts`, `product_weekly_lifecycle_export`, and
  `record_lifecycle_prompt_action` remain `SECURITY INVOKER`, use an empty
  `search_path`, and are executable only by `service_role` (plus the database owner).
- The weekly export returns counts only. It exposes no account, decision, Project,
  conversation, file, prompt, response, filename, URL, or customer-content field.
- Verification did not call the decision, claim, or action RPC for any account and did
  not create a lifecycle state or event.
- No demo, customer, or founder account was inspected, reset, deleted, recreated, or
  signed into. No password or receipt was created.

## Exact database evidence

The remote migration ledger was checked immediately before release and remained at
`20260907184049 rough_to_useful_attribution`. The two transactional function-only
migrations then applied successfully as:

1. `20260908131528 lifecycle_durable_product_facts`
2. `20260908131539 lifecycle_prompt_delivery_kill_switch`

Post-release definition checks found all three expected release markers, unchanged
function signatures, `prosecdef=false`, `search_path=""`, and ACLs containing only
the database owner and `service_role`.

A service-role, content-free production aggregate found two externally eligible
accounts. Both have durable first requests and completed responses; neither has an
active Project, Aha, or artifact. This verifies the specific missed-event correction
without identifying an account or selecting customer content. The 30-day lifecycle
export remains empty, so there is no prompt conversion, retention, or lift claim.

All five existing message-family controls remained enabled at their unchanged 20%
holdout. No control was toggled for proof.

Post-DDL Supabase advisors reported only the project's existing informational
RLS-with-no-policy and unused-index notices. The affected private tables remain
deliberately inaccessible to public, anonymous, and authenticated roles; this release
did not weaken that boundary. References:

- <https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy>
- <https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index>

## Demo-readiness audit

The authoritative pre-release main was `dd3896c` on READY deployment
`dpl_EXQhYdcLHh1jwnKeQBpA1RRR9uU1`. Vercel visibly contains the names
`SUPABASE_SERVICE_KEY` for Production and Preview and `SUPABASE_URL` for all
environments; values were not revealed or read. This trusted local process contains
neither variable, and the guarded inspection exits `1` naming those two missing
variables only. The production schema has no service-role workflow-proof,
demo-proof, or recording-proof RPC.

Therefore no live demo inspection was attempted and no
`ask-crump-demo-clean-state/v1` receipt was created. A separately credentialed
operator process must run:

```powershell
python scripts/manage_demo_account.py --require-ready --receipt <new-content-free-path>
```

The destination must not already exist. If the read-only inspection does not pass,
the operator must stop; any reset remains a separate, explicit, interactive action.

## Validation

- Focused demo/lifecycle suite: 32 passed.
- Full Python suite: 861 passed, 2 environment-dependent skips.
- JavaScript contract: 49 files plus all 6 attribution runtime cases passed.
- Ruff, Python compilation, production preflight, native web bundle, and diff
  integrity passed.
- The isolated worktree lacks generated Android/iOS platform folders and store keys,
  so local native-release verification correctly reported that limitation. No native
  source or runtime asset changed, and path-filtered Android/iOS workflows did not run.
- Main CI run `34231531814` passed in 38 seconds.
- The main push caused the normal automatic Git deployment; no separate manual
  website deployment was started for the operator-only CLI change. Deployment
  `dpl_H1htU5WaxH3yFgzozF4vffsBAZuo` is READY on all six aliases with no alias error.
- Both Ask Crump health URLs and both Clever Crump home URLs returned HTTP 200 with
  canonical redirects intact.
- The release window contained no runtime-error cluster and no
  warning/error/fatal deployment log.

## Next evidence gate

Keep lifecycle email off and do not change static copy from an empty cohort. Observe
only legitimate in-product prompt/holdout outcomes after enough time has elapsed. The
sanitized demo-account blocker remains open until a separately credentialed trusted
operator completes the read-only inspection and preserves a passing content-free
receipt.
