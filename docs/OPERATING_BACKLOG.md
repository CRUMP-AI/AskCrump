# Ask Crump operating backlog

Last updated: 2026-08-27

## Operating standard

Ask Crump's north-star outcome is a user completing valuable work, keeping it, and returning
to continue it. Revenue and user growth should follow verified activation, durable value,
retention, and referral behavior. No acquisition spend should scale on impressions alone.

Every item below needs four things before it is called shipped: an accountable product
outcome, privacy and safety constraints, automated coverage, and production evidence.

## Verified releases

| Outcome | Evidence | State |
| --- | --- | --- |
| Conversational document delivery | Commit `c4ef9ee`; explicit follow-up delivery requests cannot be downgraded to clarification; targeted regressions pass; the fix is present in every current production build; no `/api/chat` runtime error cluster was reported in the seven-day production scan on 2026-08-27. | Verified |
| Professional presentation exports | Commit `b98d82a`; dark/light editorial rhythm, executive layouts, improved tables, native editable charts, and strict OOXML chart compatibility; full backend suite, JavaScript validation, production preflight, native build, and a ten-slide render review passed; production health returned HTTP 200 after deployment. | Verified |
| Private artifact journey telemetry | Commit `f497ab0`; entitled request, successful packaging, packaging failure, and first-download events are server-authoritative and content-free; Supabase migration `artifact_journey` is recorded; anonymous and authenticated roles cannot execute the aggregate report while `service_role` can; 265 backend tests, JavaScript validation, production preflight, production health, and post-deploy runtime checks passed. | Verified |

## Ranked execution backlog

### P0 — Review the first complete artifact journey cohort

**Evidence:** artifact-journey instrumentation reached production on 2026-08-27. Its first
service-role production snapshot returned no rows, which is the correct pre-traffic baseline;
Ask Crump will not insert synthetic production events to make the report look populated.

**Outcome:** use real traffic to identify the largest request-to-package or package-to-download
drop by artifact category. Keep reporting limited to aggregate stage counts and rates—never
prompts, responses, filenames, URLs, customer data, or arbitrary error text.

**Release gate:** at least one real production request and a written reconciliation of requested,
packaged, packaging-failed, and downloaded counts. Treat a small first sample as operational
evidence, not a statistically reliable conversion benchmark.

### P0 — Build the safe foundation for Crump Code

**Evidence:** Projects already retain instructions and files, but the product has no isolated
code-execution service, repository workspace, terminal tool contract, patch review flow, or
coding-agent API. A chat shortcut that says “Help me with code” is not an agentic coding product.

**Outcome:** a project-scoped coding workspace with a file tree, read/search tools, patch-based
edits, test execution, diffs, durable task history, and explicit approval for destructive or
external actions. Execution must occur in an isolated, resource-limited runtime with no ambient
production credentials and with auditable tool calls.

**Release gate:** threat model, sandbox boundary tests, path traversal and command-injection
coverage, cancellation/time limits, redacted logs, human-visible diffs, rollback behavior, and
an end-to-end benchmark suite. Do not advertise Codex or Claude Code parity until measured tasks
show comparable completion quality and safety.

### P1 — Close the organic acquisition loop

**Evidence:** the Search Console domain property and DNS verification record were created, but
verification and sitemap submission still depend on DNS propagation.

**Outcome:** verified domain ownership, one canonical sitemap submitted, valid canonical URLs,
and indexed landing pages tied to privacy-safe account-creation attribution.

**Release gate:** Search Console verification succeeds, `https://www.askcrump.com/sitemap.xml`
is accepted, canonical inspection is clean, and indexed-page coverage is reviewed after Google
has had time to crawl.

### P1 — Observe the new activation and referral funnel before scaling spend

**Evidence:** starter intent, activation, durable value, useful-result feedback, recent-work
continuation, response sharing, checkout, and paid status are now measurable, but the comparable
production cohort is new.

**Outcome:** a weekly operating review of account creation → workspace open → starter intent →
activation → durable value → useful outcome → return/share → checkout → paid.

**Release gate:** at least one fully elapsed D7 cohort, explicit denominators, internal accounts
excluded, and a written decision for the largest observed drop-off. Treat small samples as
directional rather than statistically conclusive.

### P2 — Prove the advertising creative system

**Evidence:** Deevid has produced promising video candidates, but the two newest candidate files
have not yet received a completed frame-by-frame review because screen control was paused.

**Outcome:** a restrained campaign library organized by hook, audience, duration, CTA, and funnel
stage, with branding added in post to prevent generated-logo distortion.

**Release gate:** creative QA, licensed audio/visual provenance, mobile-safe text, platform-native
aspect ratios, one measurable CTA, and controlled tests against activation—not view count alone.

## Next operating decision

Observe the first real artifact-journey traffic while defining the Crump Code sandbox boundary.
Do not expose an execution endpoint until the isolation, credential, filesystem, networking,
resource, approval, audit, cancellation, and rollback contracts are explicit and testable.
