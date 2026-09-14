# Project save offer measurement release — 2026-09-14

## Outcome

Ask Crump can now measure whether an account was shown a usable result-to-Project action before it
measures save intent. This closes the missing denominator between activation and durable Project
continuity without changing the user interface.

## Product boundary

- Conversation results emit `ProjectSaveOfferShown` only after the ownership lookup confirms the
  conversation is not already saved.
- Generated document, presentation, image, and other file results emit the same event from the
  visible artifact action.
- The only accepted sources are `conversation_result` and `artifact_result`.
- The browser sends the fixed key `project-save-offer-shown`; the authenticated server replaces it
  with `project-save-offer-shown:<source>:<server UTC day>`.
- Re-rendering a result cannot create more than one database row per account, source, environment,
  and UTC day.
- Existing “Open Project” actions do not emit a new save offer.

## Privacy and reporting boundary

The event cannot carry a plan, artifact type, acquisition tuple, prompt, response, filename, URL,
Project ID, conversation ID, message ID, or arbitrary metadata. Database constraints enforce the
fixed key shape and sources.

`product_project_continuity_snapshot` remains service-role-only and `security invoker`. It adds:

- `offer_measurement_since`;
- `project_save_offer_shown`;
- `project_save_offer_to_intent`;
- `project_save_offer_without_later_intent`;
- `project_save_intent_without_prior_offer`; and
- `offer_to_intent_rate_pct`.

The comparable exposure funnel begins at `2026-09-14 18:34:14+00`. Earlier result-save intent is
preserved in the existing journey fields but is not retroactively paired with an unobserved offer.

## Verification before production

- focused product analytics, Project continuity, and button-integrity tests: passing;
- JavaScript parse checks for every changed browser file: passing;
- fail-closed browser-control matrix: **48/48**;
- conversation result flow: offer → intent → visible success/recovery states verified;
- generated artifact flow: conversation and artifact offers remain independently classified before
  one bounded save intent.

No production event is backfilled, and no interface or pricing claim is changed by this release.
