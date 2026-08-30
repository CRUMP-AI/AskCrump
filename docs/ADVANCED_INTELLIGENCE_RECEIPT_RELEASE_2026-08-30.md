# Advanced Intelligence receipt release — 2026-08-30

## Outcome

Ask Crump now shows a restrained answer-level receipt when Advanced Intelligence actually ran:
**Thought longer** appears only when the planning pass returned a usable checklist, and **Reviewed**
appears only when the answer-review pass returned a result. The receipt survives conversation reload
and cross-device sync for newly generated responses.

This makes the paid capability tangible without exposing hidden reasoning or claiming work that did
not occur. Existing conversations are unchanged.

## Decision context

The production evidence refresh showed acquisition, not feature breadth, remains the largest current
constraint. The post-instrumentation Supabase account, artifact, and plan cohorts were empty. Vercel
Web Analytics showed 17 visitors and 149 page views in the latest 24-hour window, with three visitors
creating nine `SignupIntent` events and no observed `SignupStarted` or `AccountCreated` event. The
sample is too small to justify an authentication rewrite or pricing change.

The Advanced Intelligence audit found that Think Longer and Always Review already execute real
planner and verifier paths behind the Professional entitlement, but the result was invisible to the
customer and absent from persisted assistant messages. This release closes that value-visibility gap
without changing models, providers, entitlements, quotas, prices, credits, or checkout behavior.

## Privacy and trust boundary

- The durable receipt stores only two booleans: `plannerUsed` and `verifierUsed`.
- No prompt, answer, plan, memory, source, model, provider, token count, cost, or chain-of-thought is
  added to the receipt.
- The sync sanitizer accepts only literal `true` values for those two allowlisted keys.
- User messages cannot carry a receipt, and string/number lookalikes are discarded.
- The UI renders a receipt only from literal booleans and gives it an accessible status label.
- No production model call, response, message, account, artifact, payment, checkout, or credit event
  was created during verification.

## Verification

- Feature commit: `8116d33bd167efd5d37f5e2e9dffe5e973bf8239`
- Python: all **567** collected tests passed.
- JavaScript: all **45** application files passed the integration validator.
- Production build preflight passed.
- Native web bundle completed with the receipt-versioned assets.
- `git diff --check` passed.
- An isolated real-Edge fixture at 1,440 by 900 and 390 by 844 proved:
  - exactly one receipt for a planner-and-verifier result;
  - both expected signals;
  - no receipt for false values, string/number lookalikes, or a user message;
  - no receipt or page overflow;
  - the exact accessible label `Advanced Intelligence used: Thought longer and Reviewed`;
  - zero browser errors in the final run.

## Production evidence

- Deployment: `dpl_3y1MtRWGDouV4TxxA7xhdsQuqYWK`
- State: `READY`
- All six production aliases were attached without alias error.
- `www.askcrump.com`, `askcrump.com`, `www.clevercrump.com`, and `clevercrump.com` returned HTTP 200
  at their canonical destinations; `/app` and `/api/health` returned HTTP 200.
- The live app loads `5.9.76-intelligence-receipt-1` for the deferred runtime, message renderer,
  conversation styles, and app state handler.
- The live service worker serves cache `ask-crump-new-body-v1-r159`.
- Direct production checks found both receipt signals and the receipt CSS in the exact live assets.
- The signed-in production workspace retained Ask, Chats, Projects, Create, Library, You, the
  Intelligence control, and the working launchpad.
- The release window had no grouped runtime error and no warning, error, or fatal deployment log.

## Commercial interpretation and next gate

This is verified product and plan-value delivery, not evidence of conversion or retention lift. Do
not manufacture a response to make the receipt appear and do not broaden acquisition conclusions
from the owner's signed-in session. The next evidence gate remains legitimate external traffic and a
real first-visit → signup → useful result → durable keep or return journey. Search Console sitemap
submission and social publication remain owner-confirmed external actions.

## Rollback

Revert commit `8116d33` and redeploy. The receipt is additive and bounded; removing it does not alter
conversation content, account data, billing, entitlements, provider routing, or existing AI output.
