# Autonomous Crump: reviewable execution foundation

Date: 2026-10-15

## Outcome and boundary

This change strengthens the existing AskCrump monorepo engineering workspace. It does not create
a separate product, migrate the established stack, or change pricing. Autonomous Crump remains
disabled behind both `CODE_WORKSPACE_PUBLIC_RELEASED=false` and
`CRUMP_ENABLE_CODE_WORKSPACE=false`. No production migration, paid model call, or live Sandbox
was performed during this implementation. IONWAKE and the other Clever Crump products were not
modified.

The customer story is: prepare a project-bound public-repository task, explicitly approve its
run and any credit quote, execute within a pinned budget, then inspect the patch, checks and
activity before applying anything. No source repository is pushed, merged or deployed.

## Implemented controls

- Atomic server-derived allowance/confirmed-credit charge, canonical receipt, dispatch token and
  audit event in one transaction. Retrying the same task with a fresh HTTP request token returns
  the original dispatch without a second charge. Failed transactions roll back the debit.
- Durable model reservations with per-call/run/account/global caps, pinned exact model/prices,
  bounded request bytes/output tokens, stable call key and request digest. Fixed
  global/account/task lock order protects admission; no floating-point money arithmetic.
- Daily aggregates retain cost and the strictest admitted cap when tasks are deleted. Account
  deletion removes account identifiers but cannot free the identifier-free global daily budget.
- Reserve, begin, settle and pre-dispatch release have distinct semantics. Only a newly confirmed
  begin permits the provider POST. Lost/uncertain begin or provider outcomes retain the full hold;
  a new worker lease cannot replay a started execution. Valid idempotent settlement replays are
  accepted only when the canonical reservation is settled.
- Refund eligibility and reversal share the task lock with provider begin. A pre-provider
  cancellation can refund; cancellation after begin retains original charge and cost accounting.
- Signed, pinned RS256 workload identity before claim/provisioning. Bounded public JWKS fetch,
  rotation/cache behavior and failure handling; no token or arbitrary claim logging.
- Budget/model configuration before task claim, exact pinned policy before Sandbox provisioning,
  and fresh admission before each model call. Missing or drifted policy fails closed.
- Scheduled bounded task/approval expiry, expired-started-lease retirement and pending-refund
  reconciliation before shared-cron early returns, even when Code is disabled. Live lease state
  is rechecked atomically, so a concurrent extension wins over an old scan.
- Failed, missing or unknown check results never claim a verified implementation. Incomplete
  patch/changed-file artifacts fail closed. Verification caches stay outside the repository;
  final changed-file inventory is checked again before packaging. Ignored writes are rejected;
  NUL-delimited Git inventory validates both sides of renames and refuses incomplete records.

## Workbench

The warm paper/charcoal visual system extends the existing app. The workbench has mobile
Brief/Progress/Review navigation, preserved keyboard focus/disclosures/scroll during polling,
busy controls through refreshed states, explicit check outcomes, and file-by-file text diffs.
Patch content is inert text, never HTML. Preview limits bound characters, files, rows and line
length; the full original patch remains downloadable. Valid hunk content resembling diff headers
does not corrupt filenames or line counts.

`tests/fixtures/autonomous-workbench.html` intercepts every API request and prohibits network
connections via CSP. All scenarios are labelled synthetic. It proves rendering/client behavior,
not real agent capability or production API integration. The verifier produces ignored local
desktop and mobile screenshots in `artifacts/autonomous-workbench/`.

## Reproducible evidence

Final local result: **1,965 Python tests passed**, **57/57 browser verifiers passed**,
**16/16 SQL scenarios passed**, **54/54 visual scenarios passed**, and **33/33 public
accessibility scenarios passed**. Ruff, application compilation, JavaScript contracts, production
preflight, native web-bundle construction, smoke dry-run, client secret scan and diff checks passed.
Preflight's PATH-based Python discovery skipped its compile substep on this Windows host; the
application was compiled separately with the verified Python 3.12 runtime. The Python suite reports
one upstream Starlette/AnyIO deprecation warning.

- Python: signed identity, feature/route admission, atomic service contracts, budget validation,
  no model POST or Sandbox provisioning after refused admission, uncertainty/no-replay behavior,
  expiry/lease/refund maintenance, honest verification, complete artifact bounds and smoke parity.
- `node scripts/verify-code-budget-sql.mjs`: 16 actual SQL scenarios against a fresh in-memory
  PGlite database, applying existing wallet/allowance functions and the actual new migration.
  Set `PGLITE_MODULE` to an already-installed PGlite module if it is not on this checkout's path.
  It never reads a production database URL. Scenarios cover debit rollback, cross-request replay,
  allowance exhaustion, budget levels, cancellation/begin ordering, uncertainty, expired leases,
  original-lease settlement, deletion-independent daily aggregates and service-only privileges.
  The real durable `delete_user_account` wrapper keeps its storage-cleanup job semantics and now
  locks its parent user before child cleanup to match dispatch/refund lock ordering. Both overloads
  are exercised, including an idempotent retry after deletion.
- `node scripts/verify-autonomous-workbench.cjs`: 11 browser groups, including explicit run
  confirmation, safe patch rendering/full-download parity, both themes, keyboard/polling recovery,
  and accessibility in every mobile pane at 390 and 320 pixels.
- Existing app regression: 54 visual scenarios and 33 public-page accessibility scenarios;
  JavaScript contracts, production preflight, native web bundle and client secret scan.

PGlite executes PostgreSQL semantics but does not prove real multi-session lock contention,
deadlock behavior, Supabase/PostgREST deployment privileges, or provider billing. The fixed
four-case scripted orchestration benchmark remains a plumbing test and is not a model fix rate.

## Deployment order and remaining acceptance evidence

1. Keep both locks closed. Review/test the migration on a disposable local/staging PostgreSQL
   database with independent concurrent sessions, including same-task requests, competing tasks
   at account/global caps, begin versus cancel/refund, UTC rollover and commit-response loss.
2. Apply `20261015230059_atomic_code_dispatch_provider_budget.sql`, then deploy the reviewed
   application. The migration intentionally revokes the legacy dispatch RPC; older rolling
   instances must fail closed. Retain additive schema during rollback and use a disabled app.
3. Configure explicit workload trust and approved model price/budget values documented in
   `CRUMP_CODE_OPERATIONS.md`. Verify intended environment, deployment, team and project bindings.
4. Perform the separately approved fixed-source Sandbox smoke and end-to-end cancellation,
   retained-cost/refund, expiry, destruction, monitoring and rollback drills. Verify physical
   iOS Safari/WKWebView, download behavior, keyboard and VoiceOver.
5. Freeze at least 20 representative real failing tasks with held-out acceptance checks. Measure
   actual no-human-intervention fix rate, patch validity, regressions, security, p50/p95 latency,
   and model plus Sandbox cost per task type. Do not substitute scripted offline results.
6. Measure queue/backlog fairness with account deletion/manuscript work and define operational
   thresholds. Only open the source lock and operator switch after the evidence and explicit
   activation decision support release.

Muse provided product critique and correctly emphasized real completion reliability, total unit
cost and adversarial budget-race evidence. Older product memories were treated as leads and
checked against source/live behavior. Codex implemented and tested the code; Muse did not verify
the new source or run the test suite.

## Continuation: integrated feature and capability acceptance scorecard

This section records the subsequent capability/UI workshop. The foundation evidence totals above
belong to the prior reviewed change; they are not a measurement of the continuation or a claim
that Ask Crump matches another assistant. Autonomous Crump is an **added feature inside Ask
Crump**, sharing its account, Projects, files, navigation, entitlement and billing. There is no
second product account or separate Project/task store.

### How to read the evidence

- **Source implemented** means the inspected repository contains the behavior. It does not mean
  the feature is enabled in production or a real model completes useful tasks reliably.
- **Local proof** means a deterministic unit, SQL, scripted orchestration, browser or reference
  test exercised its stated contract. Synthetic fixtures cannot establish model capability.
- **Actual-model evidence** requires the real model/tool loop against frozen tasks with an
  independent acceptance oracle. No such run was performed in this workshop.
- **Live acceptance** additionally requires the approved identity, Sandbox, billing, cancellation,
  destruction, deployment and device drills. These gates remain open items; both Code locks stay
  closed. “Not measured” is not a zero score and must not become a parity percentage.

### Capability and evidence inventory

| User capability | Inspected Ask Crump implementation/evidence | Remaining acceptance or gap |
| --- | --- | --- |
| One Project home for chat and coding work | [Projects view](../public/crump-vision-projects-1.0.js), `bindAutonomousEntry`; [shared navigation](../public/crump-navigation-5.9.30.js), `openCode(options)`; [Code routes](../backend/routes/code.py) use the same authenticated owner and Project service. | New Project action requires server configuration **and** entitlement, forwards the selected Project, and does not start a run. Local browser proof covers two Projects, keyboard entry, mobile return focus, fresh denial and logout. Live gated integration is not exercised. |
| Inspect and edit a public repository | [Runner](../backend/code_runner.py), `_tool_definitions`, `SandboxWorkspace`: tracked-file inventory/read/search, bounded text writes, exact-match edit and deletion in the current working tree. | Edit/delete and repair-loop work is a continuation under test, not a measured model result. No authenticated/private repository checkout, local filesystem access, unrestricted terminal or dependency installation is provided by this feature. |
| Verify, use failure feedback, then review | [Runner](../backend/code_runner.py), `_agent_loop` and `_verify_candidate`, perform bounded verification/repair; [workbench](../public/crump-code-5.9.35.js), `taskOutcome`, keeps terminal receipts authoritative. | Demonstrate genuine failed-check → model repair → independently passing final source on the frozen corpus. Scripted tool responses only establish orchestration behavior. A completed plan is not evidence of a tested code change. |
| Understand active work on a phone | The existing Brief/Progress/Review workbench has text status, check exit codes, approvals, cancellation and activity history. `progressLabel`/`eventLabel` display `verification.completed` with `status=repair_required` as a repair need, while the durable task remains `running`. | No invented repair task status, progress percentage or hidden reasoning. A request for repair is not a passed result. Physical iOS/Safari/WKWebView, VoiceOver and device download checks remain unmeasured. |
| Inspect every proposed file change | [Workbench](../public/crump-code-5.9.35.js), `parsePatch`/`renderPatch`, renders inert text with bounded characters/rows/files and complete original download. The [browser verifier](../scripts/verify-autonomous-workbench.cjs) checks markup injection, hunk edge cases, focus and download equality. | Review UI proof does not establish patch correctness. No apply-to-repository, push, merge or deployment action is implemented in this workbench. |
| Durable task recovery and spending boundaries | [Task service](../backend/code_service.py), [worker](../backend/code_worker.py), [reconciliation](../backend/code_reconciliation.py), budget/identity controls and foundation SQL tests. The [PostgreSQL 17 CI job](https://github.com/CRUMP-AI/AskCrump/actions/runs/38827096554/job/116736970571) passed ten bounded concurrency scenarios at `760b1609750d06cf618253090c38bc994822709f`. | Durable task/receipt state is not a resumable conversational coding session. The real-database proof covers 16-way charge/allowance/account/global/call-reserve/provider-begin, begin-versus-cancel and deletion-versus-refund/settlement, with distinct blocked backend PIDs and no observed deadlock. It does not establish production load, provider settlement or the remaining live operational drills. |
| Continue/steer a long coding session | Current tasks use a bounded isolated run, configured step limit, cooperative cancellation and reviewed retry/approval semantics. [Configuration](../backend/config.py) bounds runtime to 30–240 seconds and steps to 1–12. The runner's `bounded_messages` automatically compacts the transcript by pruning/truncating earlier pairs to a byte bound while retaining the objective and recent tool pairing; omitted source must be reread. | This implemented deterministic compaction is not a durable conversational session or a model-generated memory summary. No in-flight conversational steering, persistent code-session memory, terminal resumption or indefinite autonomous work is implemented. These need their own storage, budget, interruption and acceptance design. |
| General Ask chat with context | [Intelligence orchestration](../backend/intelligence_service.py), `prepare`, selects owner-scoped memories/preferences, task strategy and optional planning/review; [chat route](../backend/routes/chat.py) invokes the answer model. | Source and evaluator-contract tests are evidence of wiring. The `route="code"` classification does not itself delegate to the Autonomous runner. Actual answer quality, memory relevance and coding quality have not been measured here. |
| Current research and source checking | [AI service](../backend/ai_service.py), `chat`/`search_web`, and `verify_answer` in intelligence orchestration use server-owned lookup policy and supplied evidence, with honest unavailable/unreviewed cases. | This is bounded lookup/answer review, not an interactive browser agent. Fresh source accuracy, source quality and claim-level support need actual-model candidate evaluation. |
| Documents and other durable outputs | [Chat route](../backend/routes/chat.py) invokes the existing artifact/manuscript/file services and records packaging recovery instead of claiming a missing file succeeded. | Autonomous patches are reviewed downloads, not automatically applied Project files or executable previews. General artifact quality is separate from repository repair quality. |
| External tools and parallel specialists | The coding feature has its explicit repository/verification tools and a single bounded agent loop. | No generic MCP connector runtime, user-installed agent skills, delegated coding subagents, browser/computer control, cross-tool workflow or multi-agent synthesis is implemented for Autonomous. Do not imply those capabilities from this development session's Codex/Muse collaboration. |

### Official reference scope, not a competitive score

Reviewed 2026-10-15: the [OpenAI Agents API overview](https://developers.openai.com/api/docs/guides/agents-api/overview)
describes a managed Codex harness with durable sessions, steering, compaction, tools/MCP and
subagents. The [Claude Code overview](https://code.claude.com/docs/en/overview) describes repository
reading/editing, command execution, development-tool integration and multi-file work. The
[Gemini CLI tools reference](https://geminicli.com/docs/reference/tools/) documents its tool surface.
These primary documents inform the capability categories above; they are not head-to-head results,
an integration decision, proof of available account access, or a recommendation to replace the
current Ask Crump stack. No Grok or Muse parity claim is made without equivalent inspected
capability and task evidence.

### Twenty-task actual-model acceptance target

The continuation adds a separately owned, frozen **20-case original sanitized regression corpus**
under [real_tasks_v2](../benchmarks/crump_code/real_tasks_v2/manifest.json), with a manifest freeze,
visible workspaces, evaluator-only oracles and last-solvable references. The directory's name does
not mean these are twenty production incidents or twenty successful model runs. Provenance
motivates adapted exercises; it is not a claim that every fixture literally reproduces historical
production code. See the corpus's own claim and evaluator contracts for the current scope.

The released local corpus evidence contains 114 inventoried files and difficulty strata of five
bounded, six integration and nine adversarial cases. All twenty authored baseline/reference
self-check pairs distinguish a failing starting workspace from a passing known repair, and 79
evaluator/security tests passed. The [solvability record](../benchmarks/crump_code/real_tasks_v2/solvability.v2.json)
records per-fixture evidence; the manifest SHA-256 is
`59451dadb2e312ddda5fe12b35b80a20f597f4587a373580015c9a846ccc3f43`.
These are corpus/evaluator checks, with **zero actual-model or live runs**.

The [v2 evaluator](../scripts/evaluate_crump_code_v2.py) separates candidate admission from an
evaluator-owned isolated execution seam. That seam is a callback contract: the actual model-to-corpus
runner and hardened isolated hidden-oracle executor are **not implemented or wired together** here.
Without an `execute_isolated` implementation, `evaluate_case` explicitly returns `not_evaluated`
with `reason=isolated_executor_required`. Completing that integration is an engineering prerequisite,
separate from obtaining credentials or approving spend. Reference self-checks prove that a task can
distinguish a broken baseline from a known repair. They do not prove that a model found that repair. The older
four-case offline/scripted benchmark and checked-in intelligence passing fixture retain their
original, narrower meanings.

| Gate | Required evidence | Workshop state |
| --- | --- | --- |
| Corpus integrity | Exactly 20 frozen original cases, file hashes, difficulty labels, failing baselines and passing references; prohibit candidate changes to oracle/reference files. | Corpus/evaluator work is separately owned and locally testable; reference checks are not model results. |
| Actual coding execution | Implement the model-to-corpus runner and connect the real bounded model/tool loop to all 20 cases, with objective + allowed workspace only; keep evaluator-only oracles and references inaccessible to the agent. Pin source, model, prices, tools, budget and attempt policy. | **Integration missing; not run.** This is not blocked solely by credentials/spend. No model fix rate is available. |
| Independent correctness | Implement the evaluator-owned isolated hidden-oracle executor and apply each admitted candidate there after agent access ends. Record held-out checks, regressions, scope/patch validity, interruption and failure categories. Model prose or uploaded “passed” receipts cannot substitute. | Callback/trust contract only; the hardened executor and end-to-end integration remain to be built and verified. |
| Repeatability and cost | Predeclare repetition/attempt policy; report per-case and per-stratum outcomes, p50/p95 latency and full model + Sandbox cost, including failed/uncertain work. Keep product credit accounting distinct. | **Not measured.** Reference/scripted timing and costs cannot fill these fields. |
| General assistant quality | Produce fresh synthetic candidate responses through actual Ask chat and evaluate the existing [intelligence gate](INTELLIGENCE_EVALUATION_MVP.md), including grounding, memory, instruction fidelity, artifacts and recovery. | Only evaluator contracts are established here; no new actual-model candidate set was generated. |
| Comparative statements | Use the same frozen task/acceptance conditions, documented tool permissions and complete cost/latency records for each compared system; disclose material setup differences. | No head-to-head runs. No “Codex/Muse/Gemini/Claude Code/Grok level” or overall parity score. |
| Activation | Preserve the foundation's live identity/Sandbox/billing/concurrency/rollback and physical-device gates, then record the explicit activation decision. | **Not accepted for activation.** Source hardlock and operator stop remain closed. |

### Workshop priorities and design critique

1. Make the existing Project the entry and return point for Autonomous: the same Project context,
   readable goal, inspectable progress, check results and patch review. This continuation implements
   that narrow UI improvement without creating a separate product or starting compute.
2. Build and verify the model-to-corpus runner and isolated hidden-oracle executor, then validate
   the bounded verification/repair loop and obtain actual-model evidence under an explicitly
   approved spend envelope. Expand task difficulty based on measured
   failures rather than adding untested feature labels.
3. Measure operational/device behavior before increasing autonomy. Muse's proposed interruption
   within three seconds and “Try it” preview are **future acceptance goals**: neither a guaranteed
   latency nor an executable preview exists in the current feature. Existing cancellation is
   cooperative at guarded boundaries, and the UI must retain that distinction.

Muse's latest contribution was conceptual product critique: one Project home, a plain goal,
glanceable Brief/Progress/Review and a finished-output flow of summary → checks → next steps. Muse
did not inspect this continuation's source or run its browser, evaluator or model tests. The local
integration fixture is visibly synthetic and intercepts all requests; it cannot enable Code or
create paid/production work.

### Continuation verification and bounded repository eligibility

The stronger PostgreSQL run at `4685915b37f727be88b871cd4ebf363ed60ce5d7`
([CI evidence](https://github.com/CRUMP-AI/AskCrump/actions/runs/38828062972/job/116740090357))
passed the same ten scenarios with every actor using `service_role`. Sixteen-way scenarios use
sixteen independent backend sessions and demonstrate overlapping blocked sessions; the log
reports the actual observed count, rather than claiming every actor was blocked simultaneously.
This establishes the bounded SQL race/privilege exercise, not production throughput.

The final targeted runner suite passed 140 regressions. Controlled Python helpers use isolated
imports; automatic compilation keeps bytecode outside the checkout. Actual content hashes bind
checks and patch packaging to the original Git base, detect test-hook source changes and reject
index concealment or moved HEAD. Intentionally removed compiler targets can be retired without
discarding behavioral checks. These controls do not turn repository tests into an independent
semantic correctness oracle.

The current runner accepts at most 10,000 regular tracked files and 64 MiB of complete tracked
plus nonignored untracked bytes, in addition to its 80 changed-file/200 KB patch bounds. Source
symlinks, submodules, concealed index entries and configured Git clean/process filters fail closed.
**Inherited Git LFS configuration also fails closed**, even if no LFS path is used. The live
Sandbox image's Git configuration and workload eligibility have not been verified; that remains
an activation gate. The authored local fixtures isolate their system/global Git configuration so
they test source-local filter rejection without inheriting the developer laptop's settings.

The separate chat cleanup removes only the bordered “Continue this work later” card, following
the user's clarification. Response content, receipts, feedback and copy/share/download/retry
controls are preserved. Existing explicit Project actions retain restoration, owner checks,
deduplication and recovery; a detached action does not emit a false displayed-offer metric.
