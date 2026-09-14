# Privacy-safe operating snapshot release — 2026-09-14

## Outcome

Ask Crump now has one operator command for collecting the product evidence needed to make weekly
reliability, activation, retention, monetization, and demo-readiness decisions. The command is
read-only and combines nine existing protected aggregate functions without adding a table,
migration, public endpoint, scheduler, customer-content field, or browser credential.

## Included evidence

- account funnel and exact eligible populations;
- immutable first-touch acquisition cohorts and D1/D7 retention denominators;
- document, presentation, and other artifact request-to-download progress;
- result-to-Project save and later-continuation progress;
- Plan center, subscription, credit, and recovery intent;
- bounded outcome issue categories;
- in-product lifecycle exposure, action, completion, retention, and suppression aggregates;
- the dormant production-only Project-limit plan experiment;
- boolean-only sanitized demo recording readiness.

Finance inputs remain visibly unavailable unless an authoritative aggregate source supplies them.
The report never converts Checkout diagnostics into payer or revenue claims.

## Privacy and access boundary

The exporter requires server-side `SUPABASE_SERVICE_KEY` access and calls only functions already
restricted to `service_role`. It rejects rows containing account identifiers, email, prompts,
responses, filenames, Projects, chats, messages, URLs, referrers, session/device identifiers,
payment objects, arbitrary metadata, or storage paths. It does not write to Supabase.

Supabase's current Data API guidance confirms that function access is controlled with explicit
`EXECUTE` grants and that service-role credentials belong only in trusted server/operator
contexts. The 2026 changelog was checked before implementation: the current Node 22 requirement,
new-object Data API exposure change, OAuth response-code change, and client-library GET retry
behavior do not alter this server-side POST-to-RPC operator path.

## Verification

The protected production database was queried read-only on 2026-09-14 at approximately
18:01 UTC. All nine aggregate functions returned their expected content-free shapes. The current
comparable cohort contained one external production account: account creation, event coverage,
verification, workspace open, starter intent, and activation were observed. No account was yet
D1-eligible, and no durable value, Project save/resume, artifact journey, payer, or demo-proof
milestone was observed. This is baseline evidence, not a lift or retention claim.

Automated coverage proves:

- exact arguments and complete nine-section collection;
- invalid/reversed/equal windows and invalid environments fail before the first RPC;
- nonproduction reports cannot call the production-only experiment;
- service-role headers and exact JSON payloads are used;
- a non-project or non-HTTPS origin is rejected before the service key can be transmitted;
- transient failures retry at most three times while permanent HTTP failures do not retry;
- incomplete, unexpected, malformed, or sensitive aggregate output fails closed;
- the command is directly executable and retains the weekly growth calculation contract.

Focused validation passed 24 tests, the complete backend suite passed, all 54 JavaScript files
validated, the two changed Python files passed Ruff, and the diff passed its whitespace guard.

## Release proof

- Git commit: `66517d4df814f82a6078abd53967fdc663679e39`
- GitHub CI: run `34878791239`; Python 3.12 and JavaScript jobs passed.
- Production deployment: `dpl_7t64CWdEPFXF8MX8233LwZ8VMA9H`; state `READY`, with the canonical
  Ask Crump and Clever Crump domains assigned.
- Post-deploy observability: the one-hour grouped production runtime-error scan returned no error
  cluster.

## Honest next decision

Do not increase acquisition spend or claim D1/D7 retention from this baseline. Refresh the report
after accounts become eligible, then use the exact eligible denominators to decide whether the
activation and continuity experience is ready for broader acquisition. The absent Project,
artifact, and demo proof remains the highest-value evidence gap.
